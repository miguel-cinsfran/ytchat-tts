# YTChat TTS

Lector del chat de YouTube Live con las voces SAPI5 de Windows, pensado para
personas ciegas o con baja visión que transmiten en directo. La interfaz
completa se maneja con el teclado y está probada con NVDA.

Versión 2.0.1 · Windows 10 y 11 · [novedades de cada versión](CHANGELOG.md).

## Índice

- [Qué hace](#qué-hace)
- [Requisitos](#requisitos)
- [Puesta en marcha](#puesta-en-marcha)
- [Primeros pasos](#primeros-pasos)
- [Lectura del chat](#lectura-del-chat)
- [Comentarios de vídeos](#comentarios-de-vídeos)
- [Reproductor](#reproductor)
- [Panel de chat para transmitir](#panel-de-chat-para-transmitir)
- [Mensajes automáticos](#mensajes-automáticos)
- [Gestor de descargas](#gestor-de-descargas)
- [Historial de directos](#historial-de-directos)
- [Estado por voz](#estado-por-voz)
- [Directos de TikTok](#directos-de-tiktok)
- [Funciones con la API de YouTube](#funciones-con-la-api-de-youtube)
- [Atajos de teclado](#atajos-de-teclado)
- [Accesibilidad](#accesibilidad)
- [Configuración](#configuración)
- [Problemas frecuentes](#problemas-frecuentes)
- [Licencia](#licencia)

## Qué hace

La aplicación toma la dirección de un directo o de un vídeo de YouTube, se
conecta y lee el chat en voz alta con una voz SAPI5 de Windows. Alrededor de esa
función principal ofrece un reproductor de vídeo integrado, lectura de
comentarios, moderación del chat, un panel para mostrar el chat a los
espectadores durante una transmisión, envío automático de mensajes al chat,
descarga de vídeo y audio, e historial de directos vistos.

También admite directos de TikTok, en modo de solo lectura.

## Requisitos

- Windows 10 o Windows 11.
- Al menos una voz SAPI5 instalada. Se comprueba en *Configuración, Hora e
  idioma, Voz*.
- Conexión a internet.

No hace falta instalar Python ni ningún reproductor: la versión distribuible
incluye todo, libVLC incluido.

## Puesta en marcha

**Con el ejecutable**, que es la forma habitual: descomprimir el archivo ZIP en
cualquier carpeta y abrir `YTChatTTS.exe`. No requiere instalación ni permisos
de administrador.

**Desde el código fuente**: se necesita [uv](https://docs.astral.sh/uv/).
Ejecutar `instalar.bat` para crear el entorno e instalar las dependencias, y
después `ejecutar.bat` para abrir la aplicación. El archivo `construir.bat`
genera el ZIP distribuible.

## Primeros pasos

Al abrir la aplicación, el foco queda en el campo de la dirección. Se pega ahí
el enlace del directo o del vídeo y se pulsa Intro, o el botón **Conectar**.
También sirve `Alt+C`.

La ventana está dividida en tres regiones, que se recorren con `F6` y
`Mayús+F6`: conexión, contenido y reproductor. Dentro de la región de contenido,
`Ctrl+Tab` cambia entre las pestañas de chat, comentarios e información. Cada
cambio de región y de pestaña se anuncia.

La tecla Aplicaciones abre el menú contextual sobre la lista de chat o la de
comentarios.

## Lectura del chat

Cada mensaje se lee con la voz configurada y va acompañado de un sonido, que es
distinto según se trate de un mensaje normal, un Super Chat o una membresía.

Dentro de la lista de mensajes:

- Las flechas recorren los mensajes uno a uno.
- Escribir varias letras seguidas salta al primer mensaje cuyo autor empieza
  así. Por ejemplo, escribir «mig» lleva a los mensajes de Miguel.
- El menú contextual permite copiar el mensaje, silenciar al autor durante la
  sesión y, con sesión de Google iniciada, expulsarlo o vetarlo del chat.

La lectura se pausa y se reanuda con `F5`, y `F8` interrumpe la frase en curso.
La velocidad se ajusta con `F9` y `F10`, y el volumen de la voz con `F11` y
`F12`. `F4` silencia la lectura sin desconectar, y `F7` silencia los sonidos.

En *Herramientas, Preferencias, Filtros* se configuran las palabras y los
usuarios que no deben leerse. En *Preferencias, Lectura* se elige el formato de
lo que se lee (nombre y mensaje, solo el mensaje o solo el nombre), y se puede
activar una **segunda voz para los eventos**, de modo que los Super Chats, los
regalos, las membresías y las entradas se distingan de los mensajes normales.

## Comentarios de vídeos

Cuando la dirección corresponde a un vídeo ya publicado y no a un directo, la
pestaña de comentarios muestra los comentarios del vídeo y los lee con la misma
voz. Con sesión de Google iniciada también permite publicar un comentario nuevo
y responder a uno existente.

## Reproductor

El vídeo del directo o del vídeo cargado se ve dentro de la propia aplicación,
mediante libVLC. Se maneja por completo con el teclado:

- `Ctrl+P` reproduce y pausa.
- `Ctrl+Flecha izquierda` y `Ctrl+Flecha derecha` retroceden y avanzan un
  minuto.
- `Ctrl+Flecha arriba` y `Ctrl+Flecha abajo` suben y bajan el volumen del
  reproductor, que es independiente del volumen de la voz.
- `Ctrl+D` detiene la reproducción y `Ctrl+M` silencia el audio.
- `Ctrl+F` activa la pantalla completa.

La calidad se elige en el propio panel. Los botones en pantalla están ocultos de
forma predeterminada, porque toda la funcionalidad está disponible por menú y
por atajo; se muestran desde el menú *Reproductor*.

Dentro del deslizador de posición, las flechas mueven la reproducción diez
segundos, y el deslizador anuncia el tiempo transcurrido en lugar de un número
sin contexto.

La primera vez que se abre la aplicación, el reproductor tarda unos segundos en
quedar disponible. Durante esa preparación se anuncia «Preparando el
reproductor», y al terminar, «Reproductor listo».

## Panel de chat para transmitir

Muestra el chat solo, en grande y sin el resto de la interfaz, para que lo vean
los espectadores de la transmisión. Está pensado para añadirse como fuente de
navegador en un programa de emisión como OBS Studio, Streamlabs o Prism Live
Studio.

Se activa en *Herramientas, Panel de chat para transmitir*. Al activarlo se
anuncia el puerto en el que queda disponible, y la dirección que hay que
indicar en el programa de emisión es:

    http://127.0.0.1:8730/chat

El panel muestra cada mensaje en una tarjeta con la inicial del autor, un color
propio por persona y una etiqueta que indica la plataforma. Las donaciones se
distinguen en dorado y muestran el importe. Los mensajes entran por abajo y los
más antiguos se desvanecen.

### Dónde se coloca el panel, y qué significa quedarse fuera

El programa de emisión compone lo que ven los espectadores sobre un rectángulo
de tamaño fijo, llamado lienzo. No es la pantalla del equipo ni la ventana del
juego: es una página en blanco sobre la que se pegan las fuentes. Su tamaño
habitual es de 1600 por 900 o de 1920 por 1080 píxeles.

Cada fuente es un rectángulo pegado sobre esa página: el juego, la cámara y
también este panel. Lo que queda dentro de la página se emite. Lo que sobresale
del borde no se emite. Sigue estando en la escena, pero los espectadores no lo
ven.

Una fuente puede quedar medio fuera. En ese caso se emite la parte que está
dentro y se recorta la que sobresale, sin ningún aviso. Es el error más fácil de
cometer y el más difícil de notar sin ver la pantalla.

Que dos fuentes se superpongan, en cambio, no es necesariamente un problema. El
fondo de este panel es transparente: solo se ven las tarjetas de los mensajes, y
solo tapan lo que hay justo debajo de ellas. El resto del rectángulo deja pasar
la imagen.

El panel se coloca desde el programa de emisión. En OBS Studio, las propiedades
de la fuente permiten escribir la anchura y la altura, y el diálogo de
transformación, que se abre con `Ctrl+E`, permite escribir la posición en
píxeles en lugar de arrastrar con el ratón.

Como no es posible comprobar visualmente si el panel se está mostrando, esa
información se consulta por voz: `F2` indica si el panel está activo, en qué
puerto, y si algún programa lo está mostrando en ese momento o no. Esa distinción
es la forma de detectar que el programa de emisión perdió la conexión.

El servidor solo escucha en el equipo local, de modo que el chat no sale de la
máquina. Si el puerto configurado está ocupado, el panel no se activa y se
anuncia el motivo, en lugar de cambiar de puerto en silencio: la dirección
indicada en el programa de emisión dejaría de funcionar sin aviso.

El estado del panel se recuerda entre sesiones. Si queda activado, se activa
solo al abrir la aplicación.

## Mensajes automáticos

Permiten enviar mensajes al chat del directo cada cierto tiempo, sin
intervención: por ejemplo, las redes sociales cada diez minutos, o información
sobre la transmisión cada quince.

Se configuran en *Herramientas, Preferencias, Mensajes automáticos*. Cada
mensaje tiene su propio texto, su intervalo y una casilla que permite dejarlo
preparado sin enviarlo. El intervalo puede ser **fijo**, indicando el mismo
valor como mínimo y como máximo, o **variable**, indicando un rango: en ese caso
cada envío se programa en un momento distinto dentro del rango.

Condiciones y límites, que conviene tener presentes:

- Requiere sesión de Google iniciada y un directo de YouTube conectado. En
  TikTok no funciona, porque no existe una interfaz oficial para escribir.
- El intervalo mínimo admitido son cinco minutos.
- Cada mensaje admite doscientos caracteres como máximo.
- YouTube suele bloquear los enlaces en el chat en vivo. Al escribir un mensaje
  que contiene una dirección web se muestra un aviso; conviene indicar el nombre
  de usuario en lugar de la dirección completa.

Cuando un mensaje se envía correctamente no se anuncia nada: el mensaje aparece
en el chat del directo y se lee como cualquier otro, de modo que anunciarlo
además supondría escucharlo dos veces. `F2` indica cuánto falta para el próximo
envío.

Si el servicio de YouTube devuelve un error, los mensajes automáticos se
detienen y se anuncia una sola vez. No se reintenta: insistir ante un error de
límite de frecuencia es lo que puede acarrear restricciones en la cuenta.
Reanudarlos es una decisión del usuario, desde la misma casilla de Preferencias.

## Gestor de descargas

Descarga vídeos, audio o listas de reproducción completas. Se abre con `Ctrl+S`
o desde *Herramientas, Gestor de descargas*, y funciona sin necesidad de estar
conectado a ningún directo.

Admite vídeo en MP4 o WebM y audio en MP3 o M4A, con calidad de audio
seleccionable entre 192, 256 y 320 kbps. Permite elegir la carpeta de destino y
numerar los elementos de una lista de reproducción. Las descargas en curso se
pueden cancelar.

La herramienta de descarga se actualiza desde *Herramientas, Actualizar yt-dlp*.
Si ya está al día se indica en una ventana; si hay una versión nueva, se muestra
el progreso con el porcentaje y un botón para cancelar.

## Historial de directos

El menú *Archivo* da acceso al historial de lo visto, organizado en dos
pestañas, una para YouTube y otra para TikTok, con el título y el canal de cada
entrada. Permite volver a un directo sin recordar la dirección. Los directos ya
terminados aparecen señalados como tales, porque su enlace deja de servir.

## Estado por voz

`F2` anuncia un resumen de la situación actual: estado de la conexión, título
del directo, canal, espectadores en ese momento, mensajes leídos, donaciones
recibidas, y el estado del panel de chat y de los mensajes automáticos cuando
están activos.

Qué se incluye en ese resumen se elige en *Herramientas, Preferencias, Estado
(F2)*, de modo que sea posible dejar solo lo relevante y que el anuncio no se
alargue.

## Directos de TikTok

Se admiten direcciones con el formato `tiktok.com/@usuario/live`. La aplicación
lee el chat, los regalos y las suscripciones con la misma voz, y muestra el
vídeo del directo en el reproductor.

Es una modalidad de **solo lectura**: TikTok no ofrece una interfaz oficial que
permita comentar ni moderar, de modo que esas funciones no están disponibles.
Opcionalmente puede anunciarse la entrada de cada espectador, desde
*Preferencias, Lectura*.

## Escribir en el chat

En la pestaña *Chat en vivo*, debajo de la lista de mensajes, hay un cuadro de
escritura con su botón **Enviar** al lado. El orden de tabulación es lista,
cuadro y botón, que es el orden en que se usan.

Se llega de dos formas: tabulando desde la lista, o con `Alt+Intro` desde
cualquier parte de la ventana.

Dentro del cuadro, `Intro` envía el mensaje y `Mayúsculas+Intro` inserta un
salto de línea. Tras enviarlo, el cuadro se vacía y el foco permanece dentro,
de modo que puede escribirse el siguiente sin tabular.

Escribir en el chat requiere estar conectado a un directo de YouTube con chat
en vivo y con la sesión de Google iniciada. **Cuando falta alguno de esos
requisitos, el cuadro y el botón siguen presentes y siguen alcanzándose con el
tabulador**, y el motivo concreto forma parte del nombre del botón, de modo que
el lector de pantalla lo anuncia al llegar. Activarlo lo repite con voz sin
enviar nada. Deshabilitar el botón lo habría sacado del orden de tabulación, y
entonces el motivo habría quedado fuera del alcance de quien no ve la pantalla.

El mismo cuadro se abre, esta vez en una ventana, al pulsar **Comentar en el
vídeo** o **Responder** en la pestaña *Comentarios*.

El límite de un mensaje del chat en vivo es de 200 caracteres, y lo impone la
API de YouTube. Si se supera, se avisa al enviar indicando la longitud actual.

## Funciones con la API de YouTube

Tres funciones requieren credenciales propias y sesión de Google iniciada:

- **Moderar el chat**: expulsar temporalmente o vetar a un usuario, desde el
  menú contextual de la lista.
- **Escribir en el chat del directo**, desde el cuadro que hay debajo
  de la lista, en la pestaña *Chat en vivo*.
- **Publicar y responder comentarios** en vídeos ya publicados.

Cada usuario emplea credenciales propias, creadas en su cuenta de Google. La
guía paso a paso, redactada para leerse con lector de pantalla, está en
[docs/CONFIGURACION_API.md](docs/CONFIGURACION_API.md).

Sin credenciales, la aplicación funciona igual para todo lo demás: leer el chat,
el reproductor, las descargas, el panel de transmisión y el historial no las
necesitan.

## Atajos de teclado

El modificador indica el área a la que pertenece cada acción: **Ctrl** para el
reproductor, **Alt** para la conexión y el chat, **Ctrl+Mayúsculas** para abrir
ventanas y paneles, y las **teclas de función** para la voz y la lectura. Esa
correspondencia se respeta también al personalizarlos.

Conexión y chat:

- `Alt+C` conectar, `Alt+D` desconectar.
- `Alt+Intro` llevar el foco al cuadro de escritura del chat.
- `Alt+L` ir a la lista de mensajes.

Voz y lectura:

- `F5` pausar o reanudar la lectura.
- `F8` interrumpir la frase en curso.
- `F9` y `F10` velocidad de la voz.
- `F11` y `F12` volumen de la voz.
- `F4` silenciar la lectura, `F7` silenciar los sonidos.
- `F2` anunciar el estado.

Reproductor:

- `Ctrl+P` reproducir o pausar.
- `Ctrl+Flecha izquierda` y `Ctrl+Flecha derecha` retroceder y avanzar un
  minuto.
- `Ctrl+Flecha arriba` y `Ctrl+Flecha abajo` volumen del reproductor.
- `Ctrl+D` detener, `Ctrl+M` silenciar el audio.
- `Ctrl+F` pantalla completa.
- `Ctrl+S` abrir el gestor de descargas.

Ventanas y paneles:

- `Ctrl+Mayúsculas+P` abrir Preferencias.
- `Ctrl+Mayúsculas+H` abrir el historial de directos.
- `Ctrl+Mayúsculas+I` marcar una incidencia en el registro.

Navegación, no personalizables:

- `F6` y `Mayús+F6` cambiar de región.
- `Ctrl+Tab` cambiar de pestaña.
- `Alt+F4` salir.

Los atajos se personalizan en *Herramientas, Preferencias, Atajos*. Cada acción
tiene su botón, y el nombre del botón incluye el atajo asignado en ese momento,
de modo que el lector de pantalla lo anuncia al recorrer la lista.

Para cambiar uno se activa su botón y se pulsa la combinación deseada: queda
guardada de inmediato, sin ningún paso de confirmación, y el foco permanece en
el mismo botón. `Intro` sin ninguna otra tecla deja la acción sin atajo, y
`Escape` sale sin cambiar nada.

La aplicación comprueba que la combinación sea válida para su área y que no
coincida con otra ya asignada. Si no lo es, se indica el motivo por voz y en un
aviso en pantalla, y el botón sigue esperando otra combinación, de modo que no
hay que volver a empezar. Las combinaciones de navegación y la de salir aparecen
en la lista como fijas y no pueden cambiarse.

Al final de la lista, el botón **Restablecer los atajos a los valores de
fábrica** devuelve todas las combinaciones personalizables a su valor original.
El cambio no se escribe hasta pulsar *Guardar*, de modo que *Cancelar* lo
deshace.

Todos los atajos figuran además junto a su acción en la barra de menú.

## Accesibilidad

Es el criterio principal del proyecto, no un añadido posterior.

- Todos los controles tienen nombre accesible y se alcanzan con Tab y flechas.
- La barra de menú es nativa y muestra el atajo de cada acción a su lado.
- La navegación por regiones y por pestañas anuncia cada cambio.
- Los avisos relevantes se envían al lector de pantalla por voz y por línea
  braille, acompañados de un sonido.
- El diálogo de preferencias conserva la apariencia nativa de Windows a
  propósito: dar color a una casilla de verificación cambia la forma en que el
  sistema la expone, y el lector de pantalla dejaría de indicar si está marcada.
- Se comprueba con NVDA en Windows 10 y 11.

El panel de chat para transmitir es la única excepción deliberada: no recibe
foco ni aparece en el recorrido del teclado, porque es una salida destinada a
los espectadores. El chat accesible es la lista de la ventana principal.

## Configuración

Casi todo se ajusta en *Herramientas, Preferencias*, repartido en pestañas de
interfaz, lectura, estado, filtros, atajos, API y mensajes automáticos. Los
cambios se aplican en el momento.

Los ajustes se guardan en `config.ini` y `sounds.ini`, junto al ejecutable.
Ambos son archivos de texto que pueden editarse con el Bloc de notas, y si se
eliminan se regeneran con los valores predeterminados. Los mensajes automáticos
se guardan aparte, en `mensajes_programados.json`.

## Problemas frecuentes

**No hay voces disponibles.** Se añade una en *Configuración, Hora e idioma,
Voz*. Las voces neurales de Windows 11 no aparecen en SAPI5 de forma
predeterminada; la herramienta gratuita *TTSVoicePatcher* permite exponerlas.

**Aparece «Windows protegió tu PC» al abrir el ejecutable.** Es el filtro
SmartScreen, porque el ejecutable no está firmado digitalmente. Se continúa con
*Más información, Ejecutar de todos modos*.

**El antivirus señala el ejecutable.** Es un falso positivo habitual en los
programas empaquetados con PyInstaller. Se resuelve añadiendo la carpeta a las
exclusiones.

**El panel de chat no se ve en el programa de emisión.** Conviene comprobar con
`F2` si el panel está activo y si algo lo está mostrando. Si indica que nadie lo
muestra, el problema está en la fuente de navegador del programa de emisión, no
en la aplicación.

**Los mensajes automáticos no se envían.** Requieren, a la vez, el interruptor
general activado, sesión de Google iniciada y un directo de YouTube conectado.
Si faltó alguna de las tres, no se envía nada y no se anuncia.

**Algo falla.** El archivo `ytchat.log`, junto al ejecutable, recoge los
errores. En funcionamiento normal está vacío.

## Licencia

MIT. Ver [LICENSE](LICENSE).
