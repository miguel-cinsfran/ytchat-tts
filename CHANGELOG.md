# Novedades de YTChat TTS

Qué cambia en cada versión, en lenguaje llano. El detalle técnico está en el
historial de git.

## 2.1.0 — agosto de 2026

Esta versión añade un panel de chat para mostrar en la emisión, la posibilidad
de escribir en el chat desde la propia aplicación, y simplifica la
personalización de los atajos.

- **Un panel de chat para que lo vean los espectadores.** Los mensajes aparecen
  en una página con fondo transparente que puede añadirse a la emisión, de modo
  que quien mira el directo lee el chat sin salir del vídeo. El panel se
  enciende desde el menú Herramientas.
- **Colocar el panel en la escena sin ver la pantalla.** Menú Herramientas →
  *Transmisión*, o `Ctrl+Mayúsculas+T`. La ventana se comunica con OBS y permite
  elegir la escena, llevar el panel a cualquiera de las nueve posiciones
  habituales (por ejemplo, inferior derecha), cambiar su tamaño, mostrarlo u
  ocultarlo, fijarlo para que no se mueva sin querer y ponerlo por delante de
  lo demás.

  Cada cambio se anuncia en voz alta con lo que hace falta saber: en qué
  posición quedó, qué tamaño tiene, qué parte de la pantalla ocupa, si se sale
  del borde y, sobre todo, **si alguna otra fuente lo está tapando y cuánto**.
  Esa es la pregunta que no puede responderse mirando.

  Hay además un modo de ajuste fino: se activa con un botón y a partir de ahí
  las flechas mueven el panel, en pasos normales, grandes con `Control` o de un
  píxel con `Mayúsculas`. `Intro` confirma y `Escape` deshace. Y un botón
  guarda una captura de la escena, para poder enseñársela a alguien que vea.

  También hay una explicación de qué es el lienzo, para quien no haya usado
  antes un programa de emisión.
- **El panel deja de mostrar mensajes viejos si la aplicación se cierra.** Antes
  se quedaba con lo último que había recibido, y esos mensajes seguían viéndose
  en la emisión como si el chat siguiera vivo.
- **`F2` dice cuánta gente está viendo el directo y cuánto lleva emitiendo.** El
  número de espectadores estaba mal: decía cero aunque hubiera gente. Ahora es
  correcto y se actualiza solo cada minuto.
- **Conectarse volvió a ser rápido.** Se había vuelto lento, entre veinte y
  treinta segundos en algunos equipos, por la forma en que se pedían los datos
  del vídeo.
- **Ya se puede escribir en el chat en vivo.** Debajo de la lista de mensajes
  hay un cuadro de escritura con su botón *Enviar*. `Intro` envía el mensaje y
  `Mayúsculas+Intro` inserta un salto de línea. Tras enviarlo, el cuadro se
  vacía y el foco permanece dentro, de modo que puede escribirse el siguiente
  sin tabular. Cuando falta la conexión o la sesión de Google, el cuadro y el
  botón siguen alcanzándose con el tabulador y el motivo forma parte del nombre
  del botón, para que el lector de pantalla lo anuncie.
- **Comentar y responder en los vídeos.** En la pestaña *Comentarios*, los
  botones *Comentar en el vídeo* y *Responder* abren ese mismo cuadro en una
  ventana.
- **El vídeo de los directos vuelve a cargarse.** YouTube dejó de ofrecer un
  único flujo con imagen y sonido juntos, y la aplicación seguía esperándolo.
  Los directos mostraban «No se pudo cargar el vídeo» aunque el chat funcionara.
- **`Intro` copia el mensaje seleccionado.** En la lista del chat y en la de
  comentarios no hacía nada.
- **Los atajos se cambian en un solo paso.** Antes se abría una ventana aparte y
  había que confirmar en un botón. Ahora se activa el botón de la acción, se
  pulsa la combinación y queda guardada de inmediato, sin salir de la lista.
  `Intro` a solas deja la acción sin atajo y `Escape` cancela. Si la combinación
  no es válida o ya está en uso, se indica el motivo por voz y en un aviso en
  pantalla, y el botón sigue esperando otra.
- **Restablecer los atajos.** Un botón al final de la lista devuelve todas las
  combinaciones personalizables a sus valores originales.
- **Tres atajos nuevos para abrir ventanas**: `Ctrl+Mayúsculas+P` abre
  Preferencias, `Ctrl+Mayúsculas+H` el historial de directos y
  `Ctrl+Mayúsculas+I` marca una incidencia en el registro.
- **El registro detallado viene desactivado.** Es una opción de diagnóstico y
  estaba activa de fábrica, lo que hacía crecer el archivo de registro sin
  necesidad.
- **La guía de configuración de la API está reescrita.** Cada paso indica la
  dirección exacta de la pantalla de Google Cloud correspondiente, y se explican
  los tres puntos en los que es fácil quedarse atascado con un lector de
  pantalla.

## 2.0.1 — agosto de 2026

Versión de arreglos. No trae funciones nuevas grandes: trae que las que ya
había molesten menos y avisen mejor.

- **El diagnóstico dejó de hablar solo.** Cada treinta segundos anunciaba por
  voz cuántos hilos había vivos. Era información para arreglar problemas, no
  para escucharla mientras miras un directo. Ahora se sigue guardando en el
  registro, pero callado.
- **Los controles del reproductor ya no se quedan mudos.** Pulsar reproducir,
  silenciar o buscar sin tener un vídeo cargado no hacía absolutamente nada, ni
  siquiera decirlo. Ahora contestan «No hay ningún vídeo cargado» o «El
  reproductor no está disponible», según el caso.
- **Los atajos del reproductor funcionan siempre.** Estaban apagados hasta
  conectarte a algo, así que las siete combinaciones de Control parecían rotas.
- **Avisa al pulsar reproducir.** Antes había un silencio largo mientras
  cargaba, que parecía que se había colgado. Ahora dice «Cargando vídeo».
- **Avisos claros cuando falla la red.** Antes, si YouTube no contestaba o el
  vídeo era privado, no se oía nada. Ahora lo dice con palabras: que la red no
  responde, que el vídeo no está disponible, o que hay que esperar unos minutos
  porque se hicieron demasiadas consultas.
- **Los atajos de Preferencias van agrupados.** Los veinte botones colgaban
  sueltos; ahora el lector anuncia a qué grupo pertenece cada uno, «Reproductor»
  o «Conexión y chat».
- **yt-dlp se puede actualizar desde la aplicación.** Menú Herramientas →
  Actualizar yt-dlp. Es la pieza que se rompe cuando YouTube cambia algo por
  dentro, y hasta ahora había que esperar a una versión nueva del programa
  entero. Comprueba qué versión hay publicada, la compara con la instalada y la
  descarga solo si hace falta, verificando que el archivo sea el auténtico.
- **Las descargas usan ese mismo yt-dlp.** Antes el gestor de descargas llevaba
  su propia copia por dentro, que se quedaba vieja aunque actualizaras. Ahora
  todo usa el mismo, y la versión que muestra la aplicación es la de verdad.
- **Se arregló una fuga que dejaba el chat leyéndose dos veces por dentro.** Si
  te reconectabas a otro directo sin desconectar antes, la conexión anterior
  seguía viva pidiéndole mensajes a YouTube para siempre, en silencio, hasta
  cerrar el programa.
- **La carpeta de descargas ya no se guarda sola.** Se escribía en la
  configuración una ruta de la máquina donde se compiló el programa.
- Se quitó una entrada de menú que ya no llevaba a ninguna parte, y los avisos
  también salen por línea braille.

## 2.0.0 — julio de 2026

- **Directos de TikTok, ya finos.** La primera versión los estrenó y esta los
  deja fiables: se leen todos los comentarios con su autor, se oye el vídeo del
  directo, y F2 muestra los espectadores en vivo. Opcional: leer quién entra al
  directo (desactivado por defecto, en Preferencias → Lectura).
- **Historial de directos** (menú Archivo): guarda lo que has visto, en dos
  pestañas (YouTube y TikTok), para volver a un directo con Enter sin recordar
  el enlace. Los directos se marcan como tales, porque al terminar pueden dejar
  de existir.
- **Búsqueda por letras en el chat y los comentarios**: escribe unas letras
  seguidas («mig») y salta al mensaje que empieza así, anunciándolo. Da la
  vuelta a la lista si hace falta y avisa si no hay coincidencias.
- **Segunda voz para los eventos** (opcional): los Super Chats, regalos y
  miembros nuevos pueden leerse con una voz distinta de la de los mensajes.
- **Atajos que se capturan pulsándolos**: en Preferencias → Atajos ya no se
  escribe la combinación a mano; pulsas el botón de la acción y luego las
  teclas, y la app comprueba sola que sea válida y no choque con otra.
- **Estado por voz (F2) configurable**: dice los datos del directo (título,
  canal, espectadores, mensajes leídos, aportes…) y en Preferencias → Estado
  se elige exactamente qué cuenta.
- **Chat más fluido con el lector de pantalla**: navegar la lista con las
  flechas mientras llegan mensajes ya no se traba.
- **Menús coherentes**: las acciones que necesitan conexión se deshabilitan
  cuando no la hay, y desconectar es instantáneo (antes podía congelar la
  ventana unos segundos).
- **Reconexión de YouTube más robusta**: un error de red que dejaba la
  conexión rota hasta reconectar a mano ya se recupera solo.
- **Reproductor pulido**: reanudar un directo tras pausarlo vuelve al momento
  actual, la pantalla completa lleva el título del vídeo, y en los directos se
  indica «En directo» en lugar de una barra de progreso confusa.

## 1.0.0 — julio de 2026

Primera versión. Lectura del chat de YouTube Live con voces SAPI5; comentarios
de vídeos con lectura, respuesta y publicación; reproductor de vídeo integrado
con pantalla completa manejable por teclado; moderación y envío al chat con la
API oficial; pestaña de información del vídeo; y directos de TikTok (solo
lectura). Interfaz navegable por teclado, con anuncios por voz y braille.
