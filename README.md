# YTChat TTS

> Lector de chat de YouTube Live con voces SAPI5 de Windows.
> Pensado para streamers ciegos o con baja visión.

**Versión 0.5 · Windows 10/11 · Python 3.11+ 64-bit**

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
- Integración con NVDA y JAWS vía `cytolk`: anuncios al conectar, cambiar voz, filtrar, copiar.
- Atajos todos en `Alt+X` para no chocar con Insert (NVDA) ni Ctrl (Windows).
- Tema oscuro Catppuccin Mocha; tamaño de fuente del chat configurable.

**Sonidos de retroalimentación**

- 12 sonidos WAV para eventos clave generados con Python stdlib (sin dependencias de audio).
- Reproducción simultánea sin bloqueo vía `winmm.dll` (MCI): los sonidos se solapan.
- Sustituibles por WAV propios manteniendo el nombre de archivo.

**Otras**

- Reconexión automática configurable.
- Mutex de instancia única (`CreateMutexW`).
- Log a `ytchat.log` solo para warnings/errores; vacío en operación normal.

---

## Stack técnico

| Capa         | Tecnología                                      |
| ------------ | ----------------------------------------------- |
| GUI          | wxPython 4.2+, tema Catppuccin Mocha            |
| TTS          | win32com / SAPI5 (pywin32), hilo COM/STA propio |
| Chat         | pytchat (InnerTube API de YouTube)              |
| Accesibilidad| cytolk (NVDA/JAWS, opcional)                    |
| Audio        | ctypes + winmm.dll (MCI), sin pygame/numpy      |
| Empaquetado  | PyInstaller + `build.bat`                       |

---

## Estructura del proyecto

```
ytchat-tts/
├── main.py          # Entrada, orquestación, captura de chat
├── gui.py           # Ventana wxPython, eventos, persistencia runtime
├── tts_worker.py    # Hilo TTS (COM/STA), sanitización, volumen
├── config.py        # Constantes, logging, INI, atajos, guardar_opcion()
├── sound_player.py  # Reproductor asíncrono vía winmm.dll
├── sound_gen.py     # Generador de WAV stdlib (setup / regenerar)
├── config.ini       # Configuración de usuario (editable)
├── sounds.ini       # Configuración de sonidos (editable)
├── sounds/          # Archivos WAV de retroalimentación
├── requirements.txt
└── instalar.bat     # Instalador de dependencias + generación de sonidos
```

---

## Requisitos

- Windows 10 (22H2 o posterior) o Windows 11.
- **Python 3.11 o superior, de 64 bits.** Con Python 32-bit, SAPI5 no verá las voces modernas.
- Al menos una voz SAPI5 instalada (*Configuración → Hora e idioma → Voz*).
- Dependencias Python: `wxPython`, `pytchat`, `pywin32`, `cytolk` (ver `instalar.bat`).

---

## Instalación desde código fuente

```bash
# Clonar o descargar el repositorio y entrar en la carpeta
instalar.bat
```

`instalar.bat` hace lo siguiente:

1. Comprueba que Python esté instalado y sea de 64 bits.
2. Instala las dependencias (`wxPython`, `pytchat`, `pywin32`, `cytolk`).
3. Pregunta si instalar el fork alternativo de pytchat (útil con ciertos directos).
4. Genera los 12 sonidos de retroalimentación con `sound_gen.py`.
5. Pregunta si abrir la aplicación ahora.

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

Configurables en `config.ini`, sección `[atajos]`. Todos usan `Alt` para no chocar con Insert (NVDA) ni Ctrl (Windows).

| Atajo  | Acción                                       |
| ------ | -------------------------------------------- |
| Alt+U  | Saltar al campo URL                          |
| Alt+C  | Conectar o desconectar                       |
| Alt+P  | Pausar o reanudar el TTS                     |
| Alt+L  | Saltar a la lista del chat                   |
| Alt+V  | Saltar al selector de voz                    |
| Alt+F  | Saltar al filtro de mensajes                 |
| Alt+D  | Detener mensaje actual y vaciar cola         |
| Alt+T  | Silenciar o reactivar la lectura TTS         |
| Alt+M  | Silenciar o reactivar los sonidos WAV        |
| Alt+X  | Vaciar la cola de lectura                    |
| Alt+.  | Subir velocidad del TTS                      |
| Alt+,  | Bajar velocidad del TTS                      |
| Alt+S  | Salir                                        |

Para reasignar: `pausa = alt+j` en `config.ini`. Para desactivar: `pausa = ` (valor vacío). Si dos acciones comparten tecla, la segunda se ignora y se registra en `ytchat.log`.

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
- Ruta de cada WAV — `superchat = C:\Audio\mi_campana.wav`. Vacío desactiva ese sonido.

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

Para sustituir un sonido: reemplaza el WAV en `sounds/` manteniendo el nombre.
Para regenerar los originales: `python sound_gen.py --forzar`.
Para silenciar temporalmente: Alt+M. Para desactivar en permanente: `activar = false` en `sounds.ini`.

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

## Licencia

MIT — ver archivo [LICENSE](LICENSE).
