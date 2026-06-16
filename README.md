# YTChat TTS

> Lector de chat de YouTube Live con voces SAPI5 de Windows.
> Pensado para streamers ciegos o con baja visión.

**Versión 0.6 · Windows 10/11 · Python 3.11+ 64-bit**

---

## Índice

- [Qué hace](#qué-hace)
- [Características](#características)
- [Stack técnico](#stack-técnico)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Requisitos](#requisitos)
- [Instalación desde código fuente](#instalación-desde-código-fuente)
- [Uso](#uso)
- [Atajos de teclado](#atajos-de-teclado)
- [Configuración](#configuración)
  - [config.ini](#configini)
  - [sounds.ini](#soundsini)
- [Sonidos](#sonidos)
- [Problemas frecuentes](#problemas-frecuentes)
- [Diagnóstico](#diagnóstico)

---

## Qué hace

YTChat TTS se conecta a un directo de YouTube mediante la InnerTube API (pytchat), captura los mensajes conforme van llegando y los lee con una voz SAPI5 del sistema. Muestra los mensajes en una lista navegable por teclado, permite pausar y reanudar la lectura, cambiar de voz al vuelo y ajustar la velocidad sin interrumpir el directo.

Está pensada principalmente para streamers que no pueden estar mirando la pantalla: la interfaz entera es navegable con Tab y flechas, cada control tiene nombre accesible, y los anuncios importantes se envían al lector de pantalla (NVDA/JAWS) en paralelo con un efecto sonoro.

---

## Características

**Lectura del chat**

- Voces SAPI5 nativas de Windows, cualquiera que esté instalada.
- Super Chats, stickers y nuevas membresías diferenciados al leer.
- Cola con estrategia de descarte configurable para directos con mucho tráfico.
- Cambio de voz y velocidad en tiempo real, sin reconectar.
- Filtros por palabras y por usuarios en `config.ini`.
- Silencio por usuario en sesión (solo TTS o también ocultar de la lista).
- Alt+D vacía la cola al instante, útil contra spam o mensajes muy largos.

**Accesibilidad**

- Todos los controles tienen etiquetas accesibles y son alcanzables con Tab.
- Integración con NVDA y JAWS vía `accessible_output2`: anuncios al conectar, cambiar voz, filtrar, copiar.
- Atajos todos en `Alt+X` para no chocar con Insert (NVDA) ni Ctrl (Windows).
- Tema oscuro Catppuccin Mocha; tamaño de fuente del chat configurable.

**Sonidos de retroalimentación**

- 12 sonidos WAV para eventos clave generados con Python stdlib (sin dependencias de audio).
- Reproducción simultánea sin bloqueo vía `winmm.dll` (MCI): los sonidos se solapan.
- Sustituibles por WAV propios manteniendo el nombre de archivo.

**Funciones online (opcionales, API de YouTube)**

- Leer y navegar los comentarios de cualquier vídeo (no solo directos), con TTS.
- Moderar el chat en vivo: expulsar (timeout) o banear usuarios, con confirmación.
- Enviar mensajes al chat del directo.
- Publicar y responder comentarios.
- Se gestionan desde el botón **Configuración** dentro de la app; las claves se
  guardan en `credenciales.json` (local, nunca en el repositorio).
- Si las dependencias de Google no están instaladas, estas funciones se
  desactivan solas y el resto de la aplicación funciona igual.

**Otras**

- Reconexión automática configurable.
- Mutex de instancia única (`CreateMutexW`).
- Log a `ytchat.log` solo para warnings/errores; vacío en operación normal.

---

## Funciones online (API de YouTube)

Leer comentarios, moderar el chat en vivo, enviar mensajes al directo y
publicar/responder comentarios usan la **YouTube Data API v3 oficial**. Son
opcionales y vienen desactivadas: requieren instalar las dependencias de Google
(ver `requirements.txt`) y crear tus credenciales una sola vez.

Todo se configura desde el botón **Configuración** de la aplicación, sin editar
archivos. La guía paso a paso (pensada para lectores de pantalla) está en
**[docs/CONFIGURACION_API.md](docs/CONFIGURACION_API.md)**.

Resumen: leer comentarios solo necesita una **API key**; moderar y comentar
necesitan además **iniciar sesión** (OAuth). Cada usuario usa sus propias
credenciales, así que dispone de su cuota diaria completa y no requiere
verificación de Google.

---

## Stack técnico

| Capa         | Tecnología                                      |
| ------------ | ----------------------------------------------- |
| GUI          | wxPython 4.2+, tema Catppuccin Mocha            |
| TTS          | win32com / SAPI5 (pywin32), hilo COM/STA propio |
| Chat         | pytchat (InnerTube API de YouTube)              |
| Online       | YouTube Data API v3 (OAuth2, google-api-python-client; opcional) |
| Accesibilidad| accessible_output2 (NVDA/JAWS, opcional)        |
| Audio        | ctypes + winmm.dll (MCI), sin pygame/numpy      |
| Empaquetado  | PyInstaller + `build.bat`                       |

---

## Estructura del proyecto

```
ytchat-tts/
├── main.py            # Entrada, orquestación, captura de chat
├── gui.py             # Ventana wxPython, eventos, persistencia runtime
├── gui_config.py      # Diálogo de Configuración (API key + OAuth)
├── gui_comentarios.py # Ventana de comentarios de vídeos
├── tts_worker.py      # Hilo TTS (COM/STA), sanitización, volumen
├── config.py          # Constantes, logging, INI, atajos, guardar_opcion()
├── montos.py          # Parseo del importe de Super Chats (locale-aware)
├── youtube_api.py     # YouTube Data API v3 (comentarios, OAuth, moderación)
├── credenciales.py    # Almacén de claves/token (credenciales.json, gitignored)
├── sound_player.py    # Reproductor asíncrono vía winmm.dll
├── sound_gen.py       # Generador de WAV stdlib (setup / regenerar)
├── config.ini         # Configuración de usuario (editable)
├── sounds.ini         # Configuración de sonidos (editable)
├── sounds/            # Archivos WAV de retroalimentación
├── tests/             # Pruebas de la lógica pura (unittest, sin Windows)
├── docs/              # Documentación (guía de la API de YouTube)
├── requirements.txt
└── instalar.bat       # Instalador de dependencias + generación de sonidos
```

---

## Requisitos

- Windows 10 (22H2 o posterior) o Windows 11.
- **Python 3.11 o superior, de 64 bits.** Con Python 32-bit, SAPI5 no verá las voces modernas.
- Al menos una voz SAPI5 instalada (*Configuración → Hora e idioma → Voz*).
- Dependencias Python: `wxPython`, `pytchat`, `pywin32`, `accessible_output2` (ver `instalar.bat`).

---

## Instalación desde código fuente

```bash
# Clonar o descargar el repositorio y entrar en la carpeta
instalar.bat
```

`instalar.bat` hace lo siguiente:

1. Comprueba que Python esté instalado y sea de 64 bits.
2. Instala las dependencias (`wxPython`, `pytchat`, `pywin32`, `accessible_output2`).
3. Pregunta si instalar el fork alternativo de pytchat (útil con ciertos directos).
4. Genera los sonidos de retroalimentación con `sound_gen.py`.
5. Pregunta si abrir la aplicación ahora.

### Instalación manual (sin `instalar.bat`)

Los scripts `.bat` no se incluyen al clonar desde GitHub. Para instalar a mano,
con Python 3.11+ de 64 bits:

```bash
pip install -r requirements.txt
python sound_gen.py          # genera los WAV del tema por defecto (sounds/themes/default/)
python main.py               # arranca la aplicación
```

Para ejecutar directamente en desarrollo:

```bash
python main.py
```

Para regenerar los sonidos:

```bash
python sound_gen.py --forzar
```

---

## Uso

Abre la aplicación. Pega la URL del directo en el campo de texto y pulsa Enter o el botón Conectar. Acepta URL completa, URL acortada (`youtu.be/…`) o el ID de vídeo de 11 caracteres.

Una vez conectado, los mensajes aparecen en la lista. Enter sobre uno lo copia al portapapeles. La tecla de menú (o Mayúsculas+F10) abre el menú contextual: copiar línea completa, releer con TTS, abrir enlace del mensaje, silenciar autor.

---

## Atajos de teclado

Configurables en `config.ini`, sección `[atajos]`. Los atajos de navegación usan `Alt`; las acciones de control en tiempo real usan teclas de función (sin modificador).

**Navegación**

| Atajo  | Acción                                       |
| ------ | -------------------------------------------- |
| Alt+U  | Saltar al campo URL                          |
| Alt+C  | Conectar o desconectar                       |
| Alt+L  | Saltar a la lista del chat                   |
| Alt+V  | Saltar al selector de voz                    |
| Alt+F  | Saltar al filtro de mensajes                 |
| Alt+X  | Vaciar la cola de lectura                    |
| Alt+S  | Salir                                        |

**Control en tiempo real**

| Atajo  | Acción                                       |
| ------ | -------------------------------------------- |
| F5     | Pausar o reanudar el TTS                     |
| F6     | Silenciar o reactivar la lectura TTS         |
| F7     | Silenciar o reactivar los sonidos WAV        |
| F8     | Detener mensaje actual y vaciar cola         |
| F9     | Bajar velocidad del TTS                      |
| F10    | Subir velocidad del TTS                      |
| F11    | Bajar volumen del TTS                        |
| F12    | Subir volumen del TTS                        |

Para reasignar: `pausa = alt+j` o `pausa = f3` en `config.ini`. Para desactivar: `pausa = ` (valor vacío). Si dos acciones comparten tecla, la segunda se ignora y se registra en `ytchat.log`.

---

## Configuración

Dos archivos editables con el Bloc de notas. Cualquier cambio requiere reiniciar.

### config.ini

| Sección        | Qué controla                                                                 |
| -------------- | ---------------------------------------------------------------------------- |
| `[voz]`        | Voz (índice o nombre parcial), velocidad (ppm) y volumen (0.0–1.0)          |
| `[cola]`       | Estrategia de descarte (`limite` / `todas`) y tamaño máximo de cola         |
| `[reconexion]` | Reintentos automáticos, intervalo y máximo (0 = infinito)                   |
| `[lectura]`    | Formato: `nombre_mensaje`, `solo_mensaje` o `solo_nombre`                   |
| `[filtros]`    | Palabras prohibidas y usuarios ignorados (separados por coma)               |
| `[texto]`      | Limpiar emojis/URLs antes de leer; longitud máxima del mensaje              |
| `[atajos]`     | Teclas de cada acción                                                        |
| `[ui]`         | Tamaño de fuente del chat; mostrar total de Super Chats en barra de estado  |

Si se borra el archivo, se regenera con valores por defecto al arrancar. Un error de sintaxis produce un mensaje claro antes de cerrar.

### sounds.ini

- `activar` — `true` / `false` para todo el sistema de sonidos.
- `volumen` — De 0.0 a 1.0, independiente del volumen TTS.
- `tema` — Nombre de la carpeta de sonidos a usar dentro de `sounds/themes/`
  (por defecto `default`). Ver «[Temas de sonido](#temas-de-sonido)».
- Override por evento (avanzado) — `superchat = C:\Audio\mi_campana.wav`. Tiene
  prioridad sobre el tema. Vacío (`copiar =`) desactiva ese sonido.

---

## Sonidos

| Evento          | Cuándo suena                                    |
| --------------- | ----------------------------------------------- |
| `app_inicio`    | Al abrirse la aplicación                        |
| `conectando`    | Al pulsar Conectar o al reintentar              |
| `conectado`     | Cuando la conexión se establece                 |
| `desconectado`  | Al cerrar sesión o terminar el directo          |
| `mensaje_nuevo` | Con cada mensaje de texto                       |
| `superchat`     | Con cada Super Chat o sticker                   |
| `nuevo_miembro` | Con cada nueva membresía                        |
| `error`         | Error de conexión o reintentos agotados         |
| `pausa`         | Al pausar el TTS                                |
| `reanudar`      | Al reanudar el TTS                              |
| `copiar`        | Al copiar un mensaje al portapapeles            |
| `voz_cambiada`  | Al aplicar un cambio de voz                     |
| `enviado`       | Al enviar un mensaje al chat del directo        |
| `comentario`    | Al publicar o responder un comentario           |
| `moderacion`    | Al banear o expulsar a un usuario               |
| `cola_vaciada`  | Al vaciar la cola de lectura                    |

Para regenerar los sonidos: `python sound_gen.py --forzar`.
Para silenciar temporalmente: F7. Para desactivar en permanente: `activar = false` en `sounds.ini`.

### Temas de sonido

Los sonidos se agrupan en **temas**: carpetas dentro de `sounds/themes/`, cada
una con un WAV por evento nombrado igual que el evento (`mensaje_nuevo.wav`,
`superchat.wav`, …). El tema activo se elige con `tema = ` en `sounds.ini`.

Para crear el tuyo:

1. Copia `sounds/themes/default` a `sounds/themes/mi_tema`.
2. Reemplaza los WAV que quieras (mismo nombre de archivo). Formato
   recomendado: WAV PCM 16-bit, 44100 Hz, breve (< 1 s).
3. Pon `tema = mi_tema` en `sounds.ini` y reinicia.

---

## Problemas frecuentes

**No hay voces disponibles**
Ocurre normalmente con Python 32-bit en Windows 64-bit. Reinstala Python eligiendo la versión de 64 bits. Si aun así no aparecen, ve a *Configuración → Hora e idioma → Voz* y añade una.

**Las voces neurales de Windows 11 no aparecen**
Windows las guarda en `Speech_OneCore`, rama del registro que SAPI5 no lee por defecto. La herramienta gratuita *TTSVoicePatcher* (dipisoft) las expone; tras aplicarla aparecen en el selector con su índice normal.

**La URL no conecta o da error**
La aplicación informa el motivo (URL inválida, directo privado, sin chat, exclusivo para miembros…). Si la URL es correcta pero falla, prueba solo el ID de 11 caracteres tras `v=`. Si el problema persiste, `instalar.bat` ofrece el fork alternativo de pytchat.

**El chat conecta pero no suena nada**
Comprueba volumen en `config.ini` y que los sonidos no estén silenciados (Alt+M). Si el TTS no suena en absoluto, verifica la voz en *Configuración → Hora e idioma → Voz*.

**"Could not import comtypes.gen" al arrancar**
Normal la primera vez; desaparece en arranques posteriores. No afecta al funcionamiento.

**NVDA no anuncia los cambios de la barra de estado**
Los lectores de pantalla no monitorizan la barra de estado automáticamente. Consulta con Insert+End (NVDA) o Insert+Av Pág (JAWS). Los eventos importantes se anuncian por voz de forma independiente.

**El ejecutable lo marca el antivirus como sospechoso**
Falso positivo conocido de PyInstaller. Añade `dist\YTChat-TTS\` a las exclusiones del antivirus.

---

## Diagnóstico

`ytchat.log` (junto al ejecutable) recoge warnings y errores. En operación normal está vacío. Cuando contiene entradas, la primera línea de error suele indicar la causa.

---

## Pruebas

La lógica que no depende de Windows (extracción de ID de vídeo, sanitización
de texto, formato de lectura, parseo de atajos, carga de `config.ini`, parseo
de importes de Super Chat y filtros de la cola) está cubierta por una batería
de tests con `unittest`, sin dependencias externas:

```bash
python -m unittest discover -s tests
```

No requieren `wxPython`, `pytchat` ni un lector de pantalla, así que corren en
cualquier sistema operativo (útil para CI desde Linux/WSL). El TTS SAPI5, el
audio MCI y la GUI wx se prueban a mano en Windows.

Además, `smoke_test.py` hace una verificación más amplia (pensada para Windows):

```bash
python smoke_test.py            # importa todo y, si hay pywinauto, revisa accesibilidad
python smoke_test.py --no-gui   # solo importaciones, sin abrir la ventana
```

Importa los módulos de GUI (caza errores que la compilación no ve) y, con
`pywinauto` instalado, lanza la app y recorre el árbol de UI Automation —el
mismo que lee NVDA— avisando de controles interactivos sin nombre accesible.

---

## Licencia

MIT — ver archivo [LICENSE](LICENSE).
