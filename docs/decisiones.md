# Decisiones de diseño — YTChat TTS

Registro de por qués. Útil cuando se plantea cambiar algo y hay que
entender si la restricción existe por buena razón o por inercia.

## Audio: winmm.dll (MCI) en vez de winsound o pygame

**Decisión**: usar `ctypes + winmm.dll + mciSendString` con aliases únicos.

**Por qué no winsound**: `winsound.PlaySound` con `SND_ASYNC` solo permite
un sonido a la vez en Windows. El segundo sonido corta al primero. En un
stream activo, el tick de un mensaje nuevo llegaba mientras sonaba la
campana de un Super Chat.

**Por qué no pygame**: añadiría ~15 MB al bundle, requeriría inicializar
SDL (que puede interferir con el audio del sistema), y es una dependencia
pesada para algo que solo reproduce WAVs de 50-400 ms.

**winmm.dll**: disponible en todos los Windows desde XP, ya en `ctypes`
(stdlib), permite múltiples aliases simultáneos, latencia < 5 ms. La
única complejidad es el sweeper que cierra los aliases viejos.

## TTS: SVSFlagsAsync + WaitUntilDone(100ms) en vez de Speak(0) síncrono

**Decisión anterior (v2.1)**: `Speak(texto, 0)` — síncrono, bloquea el hilo
hasta que termina la frase.

**Problema**: no se podía interrumpir. Alt+D habría tenido que esperar al
final de la frase actual.

**Nueva decisión**: `Speak(texto, SVSF_ASYNC)` + polling con
`WaitUntilDone(100ms)`. Entre cada poll se procesan los comandos entrantes.
Si llega `purge`, se llama `Speak("", SVSF_PURGE_BEFORE)` que corta
inmediatamente.

**Trade-off**: el hilo TTS consume más CPU (polling activo), pero dado que
pasa la mayor parte del tiempo esperando en `WaitUntilDone`, el impacto
es mínimo.

## Solo Alt+X como atajos

**Decisión**: todos los atajos del programa son `Alt+letra`.

**Por qué no Ctrl**: los lectores de pantalla virtualizan algunas
combinaciones con Ctrl. Además, Ctrl+C/V/Z/A son convenciones del sistema.

**Por qué no Insert**: NVDA usa Insert como tecla modificadora principal.

**Por qué no Shift+Alt**: en Windows, Shift+Alt cambia el idioma del teclado
en muchas configuraciones. Aparecería el popup de idioma o silenciosamente
cambiaría el layout.

**Consecuencia**: el espacio de atajos está limitado a ~36 teclas
(a-z, 0-9 y algunos símbolos). Para el scope actual de la app es suficiente.

## Instancia única: mutex con ctypes en vez de archivo .lock

**Alternativa descartada**: archivo `ytchat.pid` con el PID del proceso.
Problemas: si el proceso se cae brutalmente, el archivo queda y bloquea
el siguiente arranque hasta que el usuario lo borre manualmente.

**Decisión**: `CreateMutexW` del kernel de Windows. El mutex se libera
automáticamente cuando el proceso termina, sea como sea. Sin archivos
residuales.

**Por qué ctypes y no win32event**: `win32event.CreateMutex` requiere
pywin32, que ya es dependencia del proyecto. Pero se carga en `main.py`
antes de que pywin32 esté verificado. ctypes es stdlib pura y no falla.

## Módulos: 6 archivos en vez de 13

**Decisión en v2.2**: fusionar módulos pequeños con un único consumidor.

Regla aplicada: si un módulo solo lo importa un archivo y no tiene lógica
independiente testeable, va dentro de ese archivo.

- `text_utils` → `tts_worker.py` (solo el TTS lo usa)
- `url_utils` → `main.py` (solo main lo usa)
- `logging_setup` → `config.py` (setup de infraestructura, junto al resto)
- `models` → `config.py` (constantes, junto a la configuración)
- `atajos` → `config.py` (parseado de INI, mismo momento de carga)

Los que tienen lógica independiente o los usan múltiples módulos se mantienen:
`sound_player`, `sound_gen`, `tts_worker`, `gui`.

## on_estado en vez de llamadas directas al GUI desde main

**Problema anterior**: `main.py` importaba `gui` directamente para llamar
`_gui_frame.set_conectado(True)`. Eso creaba un acoplamiento directo y
hacía difícil testear la lógica de captura sin un GUI activo.

**Decisión**: callback `on_estado(tipo, texto)` que main define y pasa a
`captura_con_reconexion`. El hilo de captura no sabe nada de wxPython;
solo llama al callback. El callback (definido en main como closure) hace
`wx.CallAfter`.

**Beneficio**: la lógica de captura es testeable sin wx. El GUI puede
cambiar sin tocar main. Los mensajes amigables al usuario viven en main
(`_mensaje_error_amigable()`), separados del código de captura.

## Persistencia runtime: guardar_opcion en vez de ConfigParser.write

**Problema**: `ConfigParser.write()` destruye todos los comentarios del INI
al reescribirlo. El usuario tiene comentarios en su `config.ini` y los perdería
en la primera pulsación de Alt+. (velocidad).

**Alternativa descartada**: re-leer con ConfigParser, modificar, y escribir
con `write()`. Rápido de implementar pero rompe la experiencia del usuario
que edita el INI a mano.

**Decisión**: `guardar_opcion(ruta, seccion, clave, valor)` — edición quirúrgica
línea a línea. Lee todas las líneas, localiza la sección y la clave, reemplaza
solo esa línea, escribe de vuelta. Coste: <1 ms en SSD. Preserva comentarios,
orden, y espacios en blanco.

**Por qué no debounce**: los handlers de atajos son síncronos en el hilo GUI.
Una tormenta de Alt+. escribe el archivo varias veces, pero cada escritura es
tan rápida que el usuario no lo notará. Si en el futuro resultara lento (HDD,
red), añadir un `wx.Timer` de 500 ms de debounce — sin cambiar la firma.

## CLAUDE.md separado de docs/

**Decisión**: CLAUDE.md es corto (~100 líneas) con lo universalmente
necesario. Los detalles técnicos viven en `docs/` y Claude los lee
bajo demanda (cuando la tarea lo requiere).

**Por qué**: CLAUDE.md se carga en CADA sesión. Si pesa 500 líneas,
consume contexto siempre, aunque la tarea sea "cambia el color de un
botón". Los docs/ solo se leen cuando se necesitan.

## PyInstaller: onedir, no onefile

**onefile**: crea un solo .exe que al arrancar descomprime todo en
`%TEMP%\_MEIxxxxxx`. Problemas: arranque lento (2-4 s extra),
más falsos positivos de antivirus, win32com puede fallar con DLLs
en carpeta temporal.

**onedir**: carpeta con el .exe y sus dependencias. Arranca en ~0.5 s,
menos falsos positivos, win32com funciona fiablemente. Para distribución
se comprime la carpeta en un ZIP — no es mucho más complejo para el usuario.
