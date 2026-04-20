# Arquitectura técnica — YTChat TTS

Referencia detallada para sesiones que necesiten contexto profundo.
Lee `CLAUDE.md` primero; este documento amplía lo que allí se resume.

## Modelo de hilos

```
Hilo principal (GUI)   wx.MainLoop(), eventos, AcceleratorTable
      │
      ├─ TTSWorker (daemon)   COM/STA, SpVoice.Speak() asíncrono
      │    └─ cola: queue.Queue  {texto_tts: str}
      │    └─ _cmds: queue.Queue  ("voice"|"rate_delta"|"purge", val)
      │
      ├─ Chat (daemon)        pytchat, asyncio loop propio
      │    └─ llama on_message(autor, msg, hora, tipo, monto)
      │    └─ llama on_estado(tipo_estado, texto)
      │
      └─ SoundSweeper (daemon)  cierra aliases MCI viejos cada 500 ms
```

Regla crítica: **todo lo que toca wx debe viajar por `wx.CallAfter()`**
cuando viene de un hilo que no sea el principal.

## Flujo de conexión

```
Usuario pulsa Conectar
  → gui._on_conectar()
      → desactiva botón, anuncia "Conectando"
      → llama on_conectar_cb(url)  [definido en main.py]

main._cb_conectar(url)
  → extrae video_id
  → lanza hilo Chat
      → obtener_titulo()   [HTTP, puede fallar silenciosamente]
          → wx.CallAfter(frame.set_titulo_stream, titulo)
      → captura_con_reconexion()
          → llama on_estado("conectando", ...)  → snd + anunciar
          → pytchat.create()
              [éxito]  → on_estado("conectado", ...)
                            → wx.CallAfter(frame.set_conectado, True)
              [fallo]  → on_estado("error_conexion", msg_amigable)
                            → wx.CallAfter(frame.set_conectado, False)
          → bucle de mensajes
          → [fin o error] → on_estado("desconectado"|"error", ...)
                            → wx.CallAfter(frame.set_conectado, False)
```

## Responsabilidades de sonido por evento

| Evento | Quién llama reproducir() |
|---|---|
| app_inicio | `gui.iniciar_gui()` al mostrar la ventana |
| conectando | `main._captura()` al iniciar + al reintentar |
| conectado | `main._captura()` al confirmar pytchat.create |
| desconectado | `main._captura()` en bloque finally |
| error | `main._captura()` y `main.captura_con_reconexion()` |
| mensaje_nuevo / superchat / nuevo_miembro | `gui.agregar_mensaje_chat()` |
| pausa / reanudar | `gui._on_pausa()` |
| copiar | `gui._copiar_mensaje()` y `gui._copiar_todo()` |
| voz_cambiada | `gui._on_aplicar_voz()` |

La norma es: **los sonidos de estado de sesión** los gestiona `main.py`
(donde vive el hilo de captura); **los sonidos de acción de usuario**
los gestiona `gui.py` (donde ocurren los eventos de botones/teclado).

## TTSWorker: flujo de Speak asíncrono

```python
self._voz.Speak(texto, SVSF_ASYNC | SVSF_IS_NOT_XML)
while True:
    terminado = self._voz.WaitUntilDone(100)  # poll 100ms
    if terminado: break
    self._procesar_comandos()          # aplica voice/rate/volume/purge
    if self._purge_pending.is_set():   # alt+D
        self._voz.Speak("", SVSF_ASYNC | SVSF_PURGE_BEFORE)
        break
    if not self._active.is_set():      # pausado
        self._active.wait()
```

`SVSFPurgeBeforeSpeak` (valor 2) vacía la cola interna de SAPI5 y
detiene inmediatamente el habla en curso.

## Resolución de rutas (PyInstaller)

```python
# config.py
def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent   # junto al .exe
    return Path(__file__).parent             # junto al .py
```

Al empaquetar con onedir, `sys._MEIPASS` apunta a `_internal/` pero
los archivos editables (`config.ini`, `sounds.ini`, `sounds/`) viven
junto al `.exe`. Por eso usamos `sys.executable` y no `sys._MEIPASS`.

## Atajos: cómo se construye la AcceleratorTable

1. `config.cargar_configuracion()` devuelve `atajos_raw` (dict crudo del INI).
   Si faltan acciones respecto a `ATAJOS_DEFAULTS`, se auto-inyectan en el INI
   preservando los valores personalizados del usuario (compatibilidad hacia atrás).
2. `config.parsear_atajos(atajos_raw)` valida, detecta conflictos y
   devuelve `{accion: Atajo(accion, texto, tecla)}`.
3. `config.atajos_a_tuplas_wx(atajos, ids)` convierte a
   `[(ACCEL_ALT, keycode, wx_id), ...]`.
4. `gui._bind_events()` construye la `wx.AcceleratorTable` con esas tuplas
   y enlaza cada `wx_id` a su handler.

20 acciones definidas (v0.5): url, conectar, pausa, chat, voz, filtro, salir,
velocidad_mas, velocidad_menos, detener_tts, silenciar_sonidos, vaciar_cola,
volumen_mas, volumen_menos, silenciar_lectura, aplicar_voz, copiar_mensaje,
copiar_todo, releer, abrir_enlace.

Todos los atajos usan `ACCEL_ALT`. El módulo de atajos rechaza todo lo
que no sea ASCII + símbolo permitido para evitar sorpresas con teclados
no-QWERTY.

## Silenciado en caliente: tres niveles

```
config["silenciados_runtime"]  → set de nombres en minúsculas
    main.debe_leer_tts(autor) devuelve False → no se encola al TTS
    El mensaje sí llega a on_message() → sí aparece en la lista del GUI

config["silenciados_ocultar"]  → set de nombres en minúsculas
    main.permitido(autor, ...) devuelve False → ni se encola ni llega al GUI
    gui.agregar_mensaje_chat() comprueba _autor_esta_oculto() como segundo
    filtro (porque el GUI puede recibir el mensaje antes de que el set
    se haya actualizado si hay concurrencia)

config["silenciar_lectura"]  → bool, toggle global Alt+T
    main.debe_leer_tts() devuelve False para TODOS los autores
    Los mensajes siguen apareciendo en lb_chat (no afecta a permitido())
    Se persiste en [sesion] silenciar_lectura del config.ini
    La barra de estado muestra "[sin TTS]" en el campo de estado
```

Los sets de usuarios no se persisten en `config.ini`. Para silenciados
permanentes, el usuario usa `[filtros] usuarios_silenciados` en el INI.

## Estructura del .spec para PyInstaller

Puntos críticos:
- `console=False` → sin ventana CMD
- `collect_all('cytolk')` → DLLs de lector de pantalla
- `collect_submodules('pytchat')` + `collect_submodules('emoji')` → submódulos
  que pytchat importa por string en runtime
- `win32com.client.Dispatch` (no `EnsureDispatch`) evita dependencia de gen_py
- config.ini, sounds.ini, sounds/, README.md van FUERA del bundle
  (build.bat los copia a dist/ después)

## Persistencia de cambios runtime: guardar_opcion

`config.guardar_opcion(ruta, seccion, clave, valor)` edita el INI sin
`ConfigParser.write()` (que destruye comentarios). Trabaja línea a línea:
localiza `[seccion]`, busca la clave dentro de ella, reemplaza in-place o
inserta antes de la siguiente sección. Si `ruta=None` es no-op.

Se llama desde gui.py para persistir al instante cada cambio de usuario:
- velocidad y volumen TTS → `[voz]`
- voz seleccionada → `[voz]`
- filtro activo → `[ui]`
- silenciar_sonidos → `[ui]`
- silenciar_lectura → `[sesion]`

## Barra de estado: 7 campos (v0.5)

| Pos | Contenido |
|---|---|
| 0 | Estado / "[sin TTS]" si silenciar_lectura activo |
| 1 | Vel: N |
| 2 | Voz: nombre |
| 3 | Cola: N |
| 4 | Leídos: N |
| 5 | Vol: N% |
| 6 | SC: importe (si mostrar_total_superchats=true) |

## Acumulación de Super Chats en la barra de estado

`gui._sumar_superchat(monto)` parsea el `amountString` de pytchat
(que varía por locale: "€15.50", "5,00 €", "1.234,56 EUR").
Normaliza separadores decimales y acumula por divisa en
`self._sc_totales: dict[str, float]`.
`gui._formato_total_sc()` formatea para mostrar en el campo 5 de la
barra de estado.
