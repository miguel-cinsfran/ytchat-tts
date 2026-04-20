# YTChat TTS

Lee en voz alta el chat de cualquier directo de YouTube usando las voces SAPI5 instaladas en Windows. Pensada para streamers ciegos o con baja visión, con interfaz completamente navegable por teclado y compatibilidad con NVDA y JAWS.

**Versión 0.5 · Solo Windows 10 y 11**

---

## Índice

1. [Qué hace y para quién](#qué-hace-y-para-quién)
2. [Características](#características)
3. [Requisitos](#requisitos)
4. [Instalación](#instalación)
5. [Uso](#uso)
6. [Atajos de teclado](#atajos-de-teclado)
7. [Configuración](#configuración)
   - [config.ini](#configini)
   - [sounds.ini](#soundsini)
8. [Sonidos](#sonidos)
9. [Problemas frecuentes](#problemas-frecuentes)
10. [Diagnóstico](#diagnóstico)

---

## Qué hace y para quién

YTChat TTS se conecta a un directo de YouTube, captura los mensajes del chat conforme van llegando y los lee con una voz del sistema. Muestra los mensajes en una lista que puedes recorrer con el teclado, permite pausar y reanudar la lectura, cambiar de voz al vuelo y ajustar la velocidad sin interrumpir el flujo del directo.

Está construida sobre todo para gente que emite en directo y no puede estar mirando la pantalla: streamers ciegos, con fatiga visual o que simplemente quieren escuchar el chat mientras trabajan o juegan. Toda la interfaz es navegable con Tab y flechas, cada control tiene un nombre accesible, y los anuncios importantes (conectando, conectado, voz cambiada, etc.) los recibe el lector de pantalla en paralelo con un breve efecto sonoro.

---

## Características

**Lectura del chat**

- Voces SAPI5 nativas de Windows, cualquiera que tengas instalada.
- Super Chats, stickers y nuevas membresías diferenciados al leer.
- Cola configurable con estrategia de descarte cuando hay saturación.
- Cambio de voz y velocidad en tiempo real, sin reconectar.
- Filtros por palabras y por usuarios desde el archivo de configuración.
- Posibilidad de silenciar a un usuario durante la sesión (solo en el TTS o también ocultando sus mensajes de la lista).
- Detener el mensaje en curso y vaciar la cola con un atajo (Alt+D), útil contra el spam o mensajes excesivamente largos.

**Accesibilidad**

- Todos los controles tienen etiquetas y son alcanzables con Tab.
- Integración con NVDA y JAWS: anuncios breves al conectar, al cambiar de voz, al filtrar, al copiar un mensaje.
- Atajos de teclado configurables, todos basados en Alt+letra para no chocar con NVDA (que usa Insert) ni con atajos estándar de Windows.
- Tema oscuro Catppuccin Mocha y tamaño de fuente del chat configurable.

**Sonidos de retroalimentación**

- Doce sonidos cortos para eventos clave (conectar, mensaje nuevo, Super Chat, nuevo miembro, error, pausa, reanudar, copiar...).
- Se pueden reemplazar por archivos WAV propios manteniendo el nombre.
- Varios sonidos pueden solaparse sin interrumpirse: la campana de un Super Chat no corta el tick de un mensaje anterior.

**Otras**

- Reconexión automática configurable si se pierde el directo.
- Solo se puede abrir una instancia a la vez.
- Registro a archivo (`ytchat.log`) solo para advertencias y errores; en funcionamiento normal permanece vacío.

---

## Requisitos

- Windows 10 (22H2 o posterior) o Windows 11.
- Al menos una voz SAPI5 instalada. Windows trae una o dos por defecto; puedes añadir más en *Configuración → Hora e idioma → Voz*.
- Opcional pero recomendado: NVDA o JAWS activos para recibir los anuncios por voz.

---

## Instalación

1. Descarga el archivo ZIP y descomprímelo en la carpeta que prefieras.
2. Abre la carpeta y ejecuta `YTChat-TTS.exe`.

No requiere instalación. El ejecutable es portable: puedes moverlo a cualquier carpeta o unidad.

> **Nota sobre el antivirus:** Algunos antivirus pueden marcar el ejecutable como sospechoso. Es un falso positivo conocido en binarios de este tipo. Si lo deseas, puedes añadir la carpeta a las exclusiones de tu antivirus.

---

## Uso

Al abrir la aplicación, pega la URL del directo en el campo de texto y pulsa Enter o el botón Conectar. La aplicación intentará conectarse, anunciará el resultado y empezará a leer los mensajes.

Acepta URL completa, URL acortada (`youtu.be/…`) o el ID de vídeo de 11 caracteres. Si la URL no es válida o el directo no está disponible, la aplicación lo indica claramente.

Una vez conectado, los mensajes aparecen en la lista. Pulsa Enter sobre uno para copiarlo al portapapeles. La tecla de menú (o Mayúsculas+F10) abre el menú contextual con más opciones: copiar la línea completa, releer con TTS, abrir el enlace del mensaje, silenciar al autor.

---

## Atajos de teclado

Todos son configurables en `config.ini`, sección `[atajos]`.

| Atajo  | Acción                                       |
| ------ | -------------------------------------------- |
| Alt+U  | Saltar al campo URL                          |
| Alt+C  | Conectar o desconectar                       |
| Alt+P  | Pausar o reanudar el TTS                     |
| Alt+L  | Saltar a la lista del chat                   |
| Alt+V  | Saltar al selector de voz                    |
| Alt+F  | Saltar al filtro de mensajes                 |
| Alt+D  | Detener el mensaje actual y vaciar la cola   |
| Alt+T  | Silenciar o reactivar la lectura TTS         |
| Alt+M  | Silenciar o reactivar los sonidos            |
| Alt+X  | Vaciar la cola de lectura                    |
| Alt+.  | Subir la velocidad del TTS                   |
| Alt+,  | Bajar la velocidad del TTS                   |
| Alt+S  | Salir                                        |

Todos usan Alt como modificador por diseño, para no chocar con NVDA (que usa Insert) ni con los atajos estándar de Windows basados en Ctrl.

Para cambiar un atajo, edita `config.ini`: `pausa = alt+j` reasigna la pausa a Alt+J. Para desactivar uno, deja el valor vacío: `pausa = `. Si dos acciones comparten la misma tecla, la segunda se ignora y queda una nota en `ytchat.log`.

---

## Configuración

El programa lee dos archivos que puedes editar con el Bloc de notas. Cualquier cambio requiere reiniciar la aplicación.

### config.ini

- **`[voz]`** — Qué voz usar (por índice o por nombre parcial), velocidad en palabras por minuto y volumen (de 0.0 a 1.0).
- **`[cola]`** — Si hay saturación: `estrategia = limite` descarta los mensajes viejos; `estrategia = todas` los lee en orden aunque se acumule retraso. `tamanio_maximo` fija el tope.
- **`[reconexion]`** — Si reintentar al perder la conexión, cada cuántos segundos y cuántos intentos como máximo (0 para infinito).
- **`[lectura]`** — `nombre_mensaje`, `solo_mensaje` o `solo_nombre`, según prefieras que lea "Juan: hola", solo "hola" o solo "Juan".
- **`[filtros]`** — Palabras prohibidas y usuarios ignorados, separados por coma.
- **`[texto]`** — Si limpiar emojis y URLs antes de leer, y longitud máxima del mensaje.
- **`[atajos]`** — Los atajos de teclado (ver sección anterior).
- **`[ui]`** — Tamaño de fuente de la lista del chat y si mostrar el total acumulado de Super Chats en la barra de estado.

Si borras el archivo, al siguiente arranque se regenera con los valores por defecto. Si lo editas y queda con un error de sintaxis, la aplicación muestra un mensaje claro antes de cerrarse.

### sounds.ini

- **`activar`** — `true` o `false` para el sistema de sonidos completo.
- **`volumen`** — De 0.0 a 1.0, independiente del volumen del TTS.
- **Rutas de cada WAV** — Por si quieres usar un archivo propio: `superchat = C:\Audio\mi_campana.wav`.

Para desactivar un sonido concreto sin tocar el resto, deja su línea vacía: `mensaje_nuevo = `.

---

## Sonidos

Hay doce eventos con su sonido asociado:

| Evento          | Cuándo suena                                        |
| --------------- | --------------------------------------------------- |
| `app_inicio`    | Al abrirse la aplicación                            |
| `conectando`    | Al pulsar Conectar o al reintentar                  |
| `conectado`     | Cuando la conexión se ha establecido                |
| `desconectado`  | Al cerrar la sesión o terminar el directo           |
| `mensaje_nuevo` | Con cada mensaje de texto (sonido muy suave)        |
| `superchat`     | Con cada Super Chat o sticker                       |
| `nuevo_miembro` | Con cada nueva membresía                            |
| `error`         | Ante un error de conexión o reintentos agotados     |
| `pausa`         | Al pausar el TTS                                    |
| `reanudar`      | Al reanudar el TTS                                  |
| `copiar`        | Al copiar un mensaje al portapapeles                |
| `voz_cambiada`  | Al aplicar un cambio de voz                         |

Para sustituir un sonido, reemplaza el archivo WAV correspondiente en la carpeta `sounds/` con el tuyo, manteniendo el mismo nombre de archivo.

Para silenciar los sonidos sin tocar ningún archivo, pulsa Alt+M. Para desactivarlos permanentemente, edita `sounds.ini` y pon `activar = false`.

---

## Problemas frecuentes

**No hay voces disponibles**
Ve a *Configuración → Hora e idioma → Voz* y añade al menos una. Si tienes Windows 11 y las voces neurales no aparecen en la aplicación, consulta el apartado siguiente.

**Las voces neurales de Windows 11 no aparecen**
Windows las guarda en una rama del registro separada que SAPI5 no lee por defecto. La herramienta gratuita *TTSVoicePatcher* (dipisoft) las expone a SAPI5; tras aplicarla, aparecerán en el selector de voz con su índice normal.

**La URL no conecta o da error**
La aplicación informa del motivo (URL inválida, directo privado, sin chat, exclusivo para miembros...). Si la URL es correcta pero sigue fallando, prueba a copiar solo el ID de 11 caracteres que aparece tras `v=` en la URL.

**El chat conecta pero no suena nada**
Comprueba que el volumen de la voz no esté a 0 en `config.ini` y que los sonidos no estén silenciados (Alt+M para alternar). Si el TTS no suena en absoluto, verifica en *Configuración → Hora e idioma → Voz* que la voz seleccionada funciona en la vista previa del sistema.

**Los mensajes "Could not import comtypes.gen" al arrancar**
Son normales la primera vez y desaparecen a partir del segundo arranque. No afectan al funcionamiento.

**NVDA no anuncia los cambios de la barra de estado**
Los lectores de pantalla no leen automáticamente las actualizaciones de la barra de estado. Para consultarla, pulsa Insert+End (NVDA) o Insert+Av Pág (JAWS). Los cambios importantes (conexión, voz, velocidad) se anuncian por voz independientemente.

**El antivirus marca el ejecutable como sospechoso**
Es un falso positivo conocido. Puedes añadir la carpeta de la aplicación a las exclusiones del antivirus con total tranquilidad.

---

## Diagnóstico

Si algo no va bien, el archivo `ytchat.log` (en la misma carpeta que el programa) recoge las advertencias y errores. En funcionamiento normal está vacío o con apenas una o dos líneas. Cuando se llena, suele bastar con abrirlo y buscar la primera línea de error para saber qué ocurre.
