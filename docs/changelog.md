# Changelog — YTChat TTS

Historial de cambios para orientar sesiones futuras con Claude Code.
Al terminar una sesión significativa, añade una entrada aquí con los
archivos tocados y los motivos del cambio.

---

## v0.5 — Abril 2026

**Sesión con Claude Sonnet 4.6** — persistencia de config, volumen TTS,
silenciado global de lectura, 8 atajos nuevos, reinicio semántico de versión.

### config.py
- `APP_VERSION = "0.5"` (era "2.2" — reinicio semántico del versionado).
- `ATAJOS_DEFAULTS` ampliado de 12 a 20 acciones: `volumen_mas` (Alt+N),
  `volumen_menos` (Alt+-), `silenciar_lectura` (Alt+T), `aplicar_voz`
  (Alt+A), `copiar_mensaje` (Alt+K), `copiar_todo` (Alt+O), `releer`
  (Alt+R), `abrir_enlace` (Alt+E).
- Nueva función `guardar_opcion(ruta, seccion, clave, valor)`: edita el INI
  línea a línea preservando comentarios. Usada en toda la app para persistir
  cambios runtime. Reemplaza el regex inline que había en `_on_aplicar_voz`.
- `_DEF` y `_CONFIG_FALLBACK` ampliados con `filtro_activo`, `silenciar_lectura`,
  `silenciar_sonidos`.
- `cargar_configuracion()`: auto-inyecta atajos ausentes al INI (compatibilidad
  con configs de v2.2); lee los tres nuevos campos.

### tts_worker.py
- Nuevo comando interno `volume_delta` en `_procesar_comandos`.
- Nuevo método público `cambiar_volumen(delta: int)` (patrón igual a `cambiar_rate`).

### main.py
- `debe_leer_tts()`: comprueba `config["silenciar_lectura"]`; si True,
  descarta el mensaje del TTS pero el GUI sigue recibiéndolo.
- Aplica `silenciar_sonidos` al arranque si estaba activo en la sesión anterior.

### gui.py
- Barra de estado: **7 campos** (añadido `Vol:` en pos 5).
- `_bind_events`: 8 nuevos bindings.
- `_on_aplicar_voz`: usa `guardar_opcion` (era regex inline).
- `_on_filtro`: persiste `filtro_activo` al INI.
- `_ajustar_rate`: persiste velocidad (WPM) al INI tras cada Alt+./Alt+,.
- Nuevo `_ajustar_volume(delta)`: `cambiar_volumen` + persiste volumen.
- `_toggle_silenciar_sonidos`: persiste estado al INI.
- Nuevo `_toggle_silenciar_lectura()`: toggle + persiste en `[sesion]`.
- 4 handlers delegados globales: `_copiar_atajo`, `_copiar_todo_atajo`,
  `_releer_atajo`, `_abrir_enlace_atajo` (anuncian "Sin selección" si no
  hay elemento activo en lb_chat).
- `iniciar_gui`: restaura `filtro_activo` y `silenciar_sonidos` al arrancar.

---

## v2.2 — Abril 2026

**Sesión web con Claude Sonnet 4.6** — reestructuración mayor.

### Módulos
- De 13 archivos .py a **6 archivos .py** por fusión:
  - `config.py`: absorbió `models.py`, `config_loader.py`, `atajos.py`,
    `logging_setup.py`
  - `tts_worker.py`: absorbió `text_utils.py`
  - `main.py`: absorbió `url_utils.py`
- Eliminados: `list_voices.py`, `test_tts.py`, `iniciar.bat`,
  `instalar_fork_pytchat.bat`

### Nuevas funcionalidades
- **Instancia única**: mutex con ctypes, `_verificar_instancia_unica()`
  en `main.py`. Muestra MessageBox si ya hay una instancia abierta.
- **Validación de conexión**: callback `on_estado(tipo, texto)` que el
  hilo de captura usa para notificar cambios al GUI. El usuario recibe
  mensajes amigables ("El chat está restringido a miembros del canal")
  en vez de reintentos silenciosos.
- **Alt+D** (detener TTS): interrumpe el mensaje en curso mediante
  `SVSFPurgeBeforeSpeak` + polling en `_hablar()`.
- **Alt+M** (silenciar sonidos): toggle en caliente.
- **Alt+X** (vaciar cola sin detener TTS).
- **Silenciar usuarios en caliente**: menú contextual → "solo TTS" o
  "ocultar y TTS". Dos sets: `silenciados_runtime` y `silenciados_ocultar`.
- **Título dinámico**: ventana muestra el título del directo cuando
  está conectada.
- **Barra de estado 6 campos**: estado, velocidad, voz, cola, leídos,
  total Super Chats.
- **Total Super Chats**: acumulado por divisa en la barra de estado.
- **Sonidos estéreo**: los 12 WAVs se generan en 2ch / 16-bit / 44100 Hz.
- **Mensajes amigables**: errores de conexión con texto legible para
  el usuario, no tracebacks.
- **Sin ventana CMD**: `console=False` en el spec de PyInstaller.

### Audio
- Cambiado de `winsound.PlaySound` a **ctypes + winmm.dll + MCI aliases**.
  Permite reproducción simultánea (el tick de mensaje no corta la campana
  del Super Chat).
- `sound_player.py`: sweeper daemon que cierra aliases MCI viejos cada
  500 ms para liberar memoria del driver de audio.

### TTS
- Cambiado de `Speak(texto, 0)` síncrono a `Speak(texto, SVSFlagsAsync)`
  + polling `WaitUntilDone(100ms)`. Permite interrumpir mid-sentence.
- `SVSF_IS_NOT_XML` incluido en los flags para evitar que SAPI interprete
  mensajes que empiezan con `<` como XML.

### Empaquetado
- `app_dir()` en `config.py`: resuelve rutas correctamente tanto en
  desarrollo como en bundle PyInstaller (usa `sys.executable.parent`
  cuando frozen).
- `build.bat` mejorado: verifica Python 64 bits, instala PyInstaller si
  falta, limpia builds anteriores, copia README.md al dist/.
- `instalar.bat` unificado: instala deps + ofrece fork pytchat +
  genera sonidos + pregunta si lanzar.

### Config
- Nueva sección `[ui]` en `config.ini`: `tamanio_fuente_chat`,
  `mostrar_total_superchats`.
- Nueva sección `[sesion]`: `guardar_historial` (preparado, no
  implementado todavía).
- Todos los valores tienen clamps de rango para evitar crasheos por
  valores inválidos.

### Accesibilidad
- Todos los controles llevan `name=` para que NVDA/JAWS lean una
  etiqueta coherente.
- `sounds.ini`: sonidos desactivables individualmente (dejar vacío).
- Alt+M para silenciar/reactivar sonidos en caliente.

---

## v2.1 — Abril 2026 (baseline)

Versión funcional de partida. Características principales heredadas:
- GUI wxPython tema oscuro Catppuccin Mocha
- TTS vía SAPI5/win32com, hilo dedicado COM/STA
- Super Chats, stickers, membresías con pytchat
- Cambio de voz en tiempo real
- Filtro de mensajes por tipo
- Copiar mensaje con Enter + fallback ctypes
- Menú contextual en el chat
- cytolk para anuncios a NVDA/JAWS
- Reconexión automática configurable
- Logging a ytchat.log (solo warnings+)
- Alt+] / Alt+[ para velocidad (cambiados a Alt+. / Alt+, en v2.2)

---

## Cómo actualizar este archivo

Al terminar una sesión de trabajo significativa en Claude Code:

```
/checkpoint
```

Ese comando (definido en `.claude/commands/checkpoint.md`) te ayudará
a redactar la entrada del changelog y actualizar este archivo.

Alternativamente, al principio de una sesión nueva puedes pedir:
"Actualiza docs/changelog.md con los cambios de la sesión anterior".
