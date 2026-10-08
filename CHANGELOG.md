# Novedades de YTChat TTS

Qué cambia en cada versión, en lenguaje llano. El detalle técnico está en el
historial de git.

## 2.1.0, octubre de 2026

Esta versión añade un panel de chat para la emisión, la posibilidad de
escribir en el chat desde la propia aplicación y una ventana para componer la
escena de OBS sin ver la pantalla. El reproductor hace caso mucho mejor, las
descargas se ordenan y avisan cuando terminan, y los datos de la aplicación
pasan a una carpeta propia.

### Reproductor

- **El reproductor obedece al instante.** Después de adelantar o retroceder,
  el pausar y el reproducir se perdían durante diez o veinte segundos: se
  anunciaba «pausar» tres veces seguidas y el vídeo seguía andando. En los
  vídeos de YouTube el audio viaja por separado del vídeo, y al reproductor le
  llegaban los dos por la red: el audio frenaba todo lo demás. Ahora el audio
  se guarda antes en el disco, en la carpeta `cache-audio` dentro de la
  carpeta `data`, y las órdenes se cumplen todas. De paso, el vídeo empieza a
  verse en menos de un segundo en vez de en seis.
- **Los directos ya no se congelan cada minuto y medio.** El vídeo y el audio
  de un directo llegaban por separado y el reproductor perdía la sincronía
  entre ambos cada 60 o 90 segundos, quedándose parado entre 25 y 50 segundos.
  Ahora se juntan antes de reproducirse, con ffmpeg, un programa que viene
  incluido en la aplicación. Si ffmpeg tarda en arrancar, el reproductor
  espera a que esté listo en vez de fallar en silencio. Si el directo se
  corta, lo dice y vuelve a conectar solo, hasta dos veces.
- **Retroceder y adelantar funcionan en los directos.** Los botones de un
  minuto y las flechas de diez segundos no hacían nada cuando el directo llega
  con las pistas separadas. Ahora cada salto reinicia la unión de vídeo y
  audio unos segundos antes del borde del directo, con un corte de dos o tres
  segundos. Las flechas seguidas se acumulan, y cada una anuncia dónde queda:
  «20 segundos por detrás del directo», «En el directo». En los directos con
  pistas separadas se puede retroceder hasta una hora, que es lo que YouTube
  guarda. Mover el deslizador o pedir un porcentaje no está disponible en
  estos directos, y la aplicación lo dice.
- **Los directos que YouTube sirve con vídeo y audio juntos también se mueven,
  con menos margen.** Solo permiten retroceder unos 30 segundos. Cuando un
  directo no admite saltos, las flechas lo dicen en vez de fallar con un aviso
  confuso.
- **Ir al directo con `Ctrl+Fin`.** Después de retroceder, el menú
  *Reproductor* tiene «Ir al directo», con `Ctrl+Fin`, que vuelve al borde de
  una vez. Si ya estás en el directo, lo dice.
- **El deslizador y `F2` dicen cuánto por detrás del directo vas.** Antes el
  deslizador decía «En directo» aunque se hubiera retrocedido. Ahora dice «40
  segundos por detrás del directo», y `F2` lo anuncia también cuando vas por
  detrás.
- **Retroceder en un directo ya no salta dos horas atrás.** El reproductor
  usaba una duración equivocada, y un retroceso de un minuto acababa al
  principio de la ventana del directo.
- **Buscar con el vídeo cargando o detenido dice el motivo.** Si pides un
  salto mientras el vídeo carga, se dice «Cargando vídeo» y no que no se puede
  adelantar. Con el vídeo detenido se dice «El vídeo está detenido». Vale para
  los directos y para los vídeos grabados.
- **Mover el vídeo en pausa guarda el destino.** Si mueves el vídeo estando en
  pausa, al reanudar sigue desde la posición nueva y no desde el principio.
- **Los vídeos divididos en pistas se reproducen.** Algunos vídeos grabados
  llegan con el vídeo y el audio en pistas separadas. Ahora se reproducen, y
  se puede saltar sin esperar a que termine la descarga. Si un vídeo no
  empieza a sonar, se vuelve a cargar una vez antes de avisar de que no se
  pudo reproducir.
- **El vídeo de los directos vuelve a cargarse.** YouTube dejó de ofrecer un
  único flujo con imagen y sonido juntos y la aplicación seguía esperándolo.
  Ahora junta el vídeo y el audio cuando llegan por separado, y si aun así no
  puede, deja anotado en el registro qué encontró.
- **La caché de vídeo respeta su tope.** Un vídeo que no cabe en el tope
  configurado ya no se baja entero: la descarga se corta enseguida y no deja
  archivos. La caché baja los vídeos en 720p, y los restos de descargas
  interrumpidas se borran solos.
- **La caché de audio ya no puede colgarse.** Si la descarga del audio se
  queda sin avanzar, se corta por tiempo.
- **Pulsar muchas veces para adelantar ya no desfasa el reproductor.** Algunas
  pulsaciones se perdían y el tiempo anunciado retrocedía solo. Y pulsar
  reproducir o pausa mientras el vídeo cargaba lo hacía empezar de cero.
- **El vídeo se corta menos.** El colchón de red era muy pequeño y cualquier
  fluctuación de la conexión interrumpía la reproducción.

### Chat y voz

- **Pausar la lectura (`F5`) pausa de verdad la frase en curso**, y mientras
  está en pausa se atienden cambios de voz, velocidad y volumen.
- **El primer mensaje tras reconectar ya no se corta.** Una orden de callar
  pendiente se aplicaba al mensaje siguiente.
- **La voz configurada que ya no existe no impide arrancar.** Se usa la
  primera disponible y se anota en el registro.
- **Los avisos ya no se cortan a la mitad, tampoco en los menús.** Antes el
  texto de un aviso se perdía si se pulsaba otra tecla enseguida. Ahora se oye
  entero. Los únicos que no interrumpen son los que se repiten solos: el aviso
  de que un vídeo sigue cargando y el de que se está consultando a OBS.
- **Los sonidos largos de temas personalizados ya no se cortan a los 5
  segundos.**
- **Los Super Chats en yenes, wones o rupias suman bien.** «¥1,000» sumaba 1.
- **Al reconectar a un directo distinto, nada del chat anterior llega al
  nuevo.** Los mensajes automáticos y el cuadro de escritura ya no pueden
  acabar en el chat que se cerró, ni los comentarios del vídeo anterior en el
  nuevo.
- **Reconectar de verdad cuenta.** Con la wifi inestable, cinco microcortes
  repartidos en horas agotaban los intentos aunque cada reconexión hubiera
  funcionado. Ahora solo cuentan los fallos seguidos. Los valores de fábrica
  son 15 segundos entre intentos y 20 intentos, unos cinco minutos en total, y
  se cambian en *Preferencias, Conexión*.
- **Avisa cuando se están perdiendo mensajes.** Si entra más chat del que la
  voz puede leer, la aplicación descarta los más viejos. Ahora lo dice una vez
  por sesión, recuerda que esos mensajes siguen escritos en la lista del chat
  y sugiere activar la lectura solo del nombre, que es lo que hace que la voz
  alcance. `F2` puede decir además cuántos van, si se activa ese dato en
  *Preferencias*.
- **Una forma más de que le lean el chat: primero el mensaje, después quién lo
  escribió.** En *Preferencias, Lectura*, junto a las tres que ya había. Se
  oye «hola a todos, de Lucía». Sirve cuando llegan muchos mensajes seguidos:
  se oye el contenido antes que el nombre y puede decidirse si interesa sin
  esperar.
- **Alias para los nombres imposibles de escuchar.** Muchos nombres de YouTube
  son cadenas de letras y números que la voz lee enteras en cada mensaje.
  Ahora puede ponérseles un nombre corto: en la lista del chat, menú
  contextual sobre un mensaje y *Poner alias*. Desde ese momento, ese usuario
  se lee y se ve con el alias. Para quitarlo, se abre lo mismo y se deja el
  campo vacío. El nombre real no se pierde: expulsar, banear, silenciar y
  responder siguen actuando sobre la cuenta de verdad.
- **Los fallos de la voz quedan anotados.** Si el sintetizador falla al
  anunciar algo, antes no quedaba ni rastro.

### TikTok

- **Los directos de TikTok vuelven a conectar con la versión 6.6.6 de la
  librería.** Con la versión que instala hoy el proyecto, la conexión se
  quedaba en «Conectando al directo de TikTok» sin llegar a nada. Ahora
  conecta, y si algo falla al prepararse, lo dice en vez de quedarse callada.
  Un usuario que no está en directo se informa como tal.

### YouTube

- **Si la sesión de YouTube caduca, la aplicación lo dice con voz.** Antes se
  leía el texto técnico de Google y la aplicación seguía creyendo que había
  sesión. Ahora avisa, borra la sesión caducada y pide volver a entrar en
  *Preferencias, API y sesión*. Si el fallo vino de algo que hiciste tú,
  ofrece abrir esa categoría. Los mensajes automáticos solo avisan.
- **Iniciar sesión otra vez tras cerrarla vuelve a funcionar.** Antes Google
  devolvía un permiso incompleto y moderar, comentar o escribir en el chat
  fallaba con un error de formato.
- **Moderar actúa sobre el usuario de la fila elegida.** Antes la moderación
  buscaba al usuario por el nombre visible.
- **Ya se puede escribir en el chat en vivo.** Debajo de la lista de mensajes
  hay un cuadro de escritura con su botón *Enviar*. `Intro` envía el mensaje y
  `Mayúsculas+Intro` inserta un salto de línea. Tras enviarlo, el cuadro se
  vacía y el foco permanece dentro, de modo que puede escribirse el siguiente
  sin tabular. Cuando falta la conexión o la sesión de Google, el cuadro y el
  botón siguen alcanzándose con el tabulador, y el motivo forma parte del
  nombre del botón.
- **Cuando no se puede escribir en el chat, ahora dice por qué.** Distingue si
  falta la clave de la API, si el vídeo no existe, si no es un directo o si el
  directo tiene el chat desactivado.
- **Comentar y responder en los vídeos.** En la pestaña *Comentarios*, los
  botones *Comentar en el vídeo* y *Responder* abren el mismo cuadro en una
  ventana.
- **Publicar un comentario y responder a uno ya funcionan.** No hacían nada:
  se escribía el texto, se pulsaba *Publicar*, la ventana se cerraba y no se
  enviaba ni se avisaba de nada.
- **En un vídeo con los comentarios cerrados ya no deja escribir uno.** Antes
  se podía redactar entero y solo al publicarlo se descubría que no se podía.
- **`Intro` copia el mensaje seleccionado, y `Alt+Intro` abre el cuadro de
  escritura.** Antes, en las listas del chat y de comentarios, `Intro` no
  hacía nada.
- **Conectarse volvió a ser rápido.** Se había vuelto lento, de veinte a
  treinta segundos en algunos equipos.
- **Desconectar mientras dice «Conectando…» es posible**, y cerrar la
  aplicación no espera a que termine una consulta a YouTube.
- **`F2` dice cuánta gente está viendo el directo y cuánto lleva emitiendo.**
  El número de espectadores estaba mal y decía cero aunque hubiera gente.
  Ahora es correcto y se actualiza solo cada minuto.
- **La guía de configuración de la API está reescrita.** Cada paso indica la
  dirección exacta de la pantalla de Google Cloud correspondiente, y se
  explican los puntos en los que es fácil quedarse atascado con un lector de
  pantalla.

### OBS y transmisión

- **Un panel de chat para que lo vean los espectadores.** Los mensajes
  aparecen en una página con fondo transparente que puede añadirse a la
  emisión, de modo que quien mira el directo lee el chat sin salir del vídeo.
  El panel se enciende en la ventana *Transmisión*, con la casilla *Panel de
  chat para transmitir*, que se abre desde el menú *Transmisión, Panel de
  transmisión…* o con `Ctrl+Mayúsculas+T`. Si queda encendido al cerrar la
  aplicación, se enciende solo al abrirla de nuevo.
- **El panel de chat no repite mensajes ni muestra los viejos.** Al encender y
  apagar rápido no se repiten mensajes, y si la aplicación se cierra deja de
  mostrar los que había recibido.
- **Componer la escena sin ver la pantalla.** En la ventana *Transmisión* se
  elige la escena y **cualquiera de sus fuentes** (el panel de chat, la
  cámara, la captura del juego), se la lleva a cualquiera de las nueve
  posiciones habituales, se cambia su tamaño, se muestra u oculta, se fija
  para que no se mueva sin querer y se pone por delante de lo demás.

  Cada cambio se anuncia en voz alta con lo que hace falta saber: en qué
  posición quedó, qué tamaño tiene, qué parte de la pantalla ocupa, si se sale
  del borde y, sobre todo, **si alguna otra fuente lo está tapando y cuánto**.
  Esa es la pregunta que no puede responderse mirando.

  Hay además un modo de ajuste fino: se activa con un botón y a partir de ahí
  las flechas mueven el panel, en pasos normales, grandes con `Control` o de
  un píxel con `Mayúsculas`. `Intro` confirma y `Escape` deshace. Y un botón
  guarda una captura de la escena, para poder enseñársela a alguien que vea.

  Así puede armarse una escena completa a ciegas: el juego en el centro, la
  cámara en un recuadro más pequeño arriba a la derecha y el chat en una
  esquina.
- **Transmitir, grabar y poner una escena al aire desde la misma ventana.**
  Hay botones para empezar y parar la transmisión y la grabación, pausar, y
  poner al aire la escena elegida. `F2` puede decir también si OBS está
  transmitiendo, grabando o con una escena al aire, si esos datos se activan
  en *Preferencias, Estado (F2)*.
- **Silenciar el micrófono de OBS con `Ctrl+Mayúsculas+M`.** La aplicación
  consulta y alterna el silencio de la fuente de micrófono que se elige en
  *Preferencias, Transmisión*.
- **La casilla del panel de chat funciona aunque OBS no esté.** Antes dejaba
  de responder si OBS no contestaba, aunque el panel no necesita OBS para
  nada.
- **El servidor de OBS se activa desde aquí.** *Preferencias, Transmisión*,
  botón *Activar el servidor websocket de OBS*, sin tener que buscarlo en los
  menús de OBS.
- **Cuando OBS no se puede activar, dice por qué.** Antes salía un mensaje
  vacío de contenido.
- **Recorrer un desplegable ya no cambia nada.** En la ventana *Transmisión*,
  pasar por las nueve posiciones con las flechas movía el panel dentro de OBS
  una vez por flecha, en directo. Ahora se elige la posición y se aplica con
  su botón.
- **La ventana *Transmisión* explica dónde está el panel en castellano
  llano.** Antes mezclaba tres porcentajes que medían cosas distintas. Hay un
  botón nuevo que explica en qué orden se usa la ventana.
- **La ventana *Transmisión* no se queda bloqueada** si la fuente elegida ha
  desaparecido en OBS o si OBS cierra la conexión: avisa y deja seguir.
  «Aplicar tamaño» sobre un panel escalado ya no lo encoge a la mitad.
- **OBS: el tiempo de transmisión era mil veces mayor.** Un minuto se
  anunciaba como «16 horas 40 minutos».

### Descargas

- **Como mucho dos descargas a la vez.** Antes, encolar diez descargas las
  lanzaba todas a la vez. Ahora corren dos, las demás esperan en «en cola», en
  el orden en que se pidieron, y se pueden cancelar mientras esperan.
- **Cancelar ya no deja programas colgados.** Al cancelar una descarga, o al
  cerrar la aplicación, los programas que estaban bajando el archivo, incluido
  ffmpeg, se cierran con ella.
- **El nombre de cada descarga es el del archivo final.** Antes se anunciaba
  el de un trozo temporal. Y «Enumerar» ya no pone «NA - » delante de los
  vídeos sueltos.
- **Las descargas terminadas tienen su propio historial.** La cola y el
  historial están en dos pestañas del gestor, y el historial se conserva entre
  sesiones. Al reabrir la ventana, el progreso de las descargas en curso sigue
  ahí.
- **Las descargas avisan cuando terminan**, esté abierto o cerrado el gestor,
  y la cola ya no se olvida al cerrar la ventana.
- **La carpeta Descargas siempre está junto a la aplicación.** Antes dependía
  de desde dónde se abriera el programa.
- **En las descargas se lee primero el progreso.** Las columnas pasaron a ser
  progreso, estado y nombre, que es el orden en que interesan.

### Preferencias y atajos

- **Preferencias se recorre con una lista de categorías**, no con pestañas.
  Con lector de pantalla, las flechas anuncian cada categoría al pasar por
  ella. Son trece, repartidas por tema.
- **Preferencias guarda de forma segura y avisa si no pudo guardar.** Antes
  escribía directamente sobre el archivo de configuración y anunciaba
  «Preferencias guardadas» pasara lo que pasara. Ahora, si el disco no acepta
  la escritura, lo dice con el sonido de error: las opciones siguen aplicadas
  hasta cerrar la aplicación, pero se perderán al cerrarla.
- **Los atajos se cambian en un solo paso, y se aplican al pulsar *Guardar*.**
  Se activa el botón de la acción y se pulsa la combinación, sin salir de la
  lista. La ventana avisa de que el cambio se aplica al pulsar *Guardar*, y
  *Cancelar* lo descarta. `Intro` a solas deja la acción sin atajo y `Escape`
  cancela. Si la combinación no es válida o ya está en uso, se indica el
  motivo por voz y en un aviso en pantalla, y el botón sigue esperando otra.
- **Restablecer los atajos.** Un botón al final de la lista devuelve todas las
  combinaciones personalizables a sus valores originales, y también se aplica
  al pulsar *Guardar*.
- **Tres atajos nuevos para abrir ventanas**: `Ctrl+Mayúsculas+P` abre
  Preferencias, `Ctrl+Mayúsculas+H` el historial de directos y
  `Ctrl+Mayúsculas+I` marca una incidencia en el registro.
- **Nueve opciones que existían y no se podían tocar.** Cómo se comporta la
  cola de lectura cuando el chat se acelera, la reconexión automática, el
  puerto del panel de chat, el micrófono de OBS que silencia el atajo, y el
  registro detallado, que hasta ahora solo se encendía editando un archivo a
  mano.
- **Los contadores numéricos se pueden reescribir sin borrar antes.** Al
  entrar en uno, su contenido queda seleccionado.
- **Nueva paleta clara, de tonos crema y verde salvia.** La ventana principal
  tiene ahora un tamaño mínimo, y los avisos largos se ajustan al ancho en vez
  de salirse de la ventana.
- **Los textos que lee el lector de pantalla llevan sus tildes.** Quince
  estaban escritos sin ellas, así que se oían mal pronunciados: «maxímo» por
  «máximo», «transmisiòn» por «transmisión».
- **Preferencias: la categoría Atajos se ve entera.** Antes dos tercios de los
  botones quedaban fuera de la ventana. Ahora la ventana se puede agrandar.
- **El modo de contraste alto de Windows se respeta.** La aplicación dejaba de
  aplicar sus colores fijos encima del tema del sistema.

### Datos e instalación

- **Los datos se mudan solos a la carpeta `data`.** La configuración, las
  credenciales, el historial, los alias, los mensajes automáticos y los
  registros estaban junto al programa. Al abrir la versión nueva, esos
  archivos se mueven a la carpeta `data` sin hacer nada. La carpeta Descargas
  sigue junto al programa.
- **Los archivos que la aplicación guarda se escriben de forma segura.** Es el
  caso del historial, las credenciales, los mensajes automáticos y la
  configuración de OBS: un cierre a mitad ya no los deja vacíos.
- **Se atacaron dos defectos de los cierres inesperados al salir.** El
  reproductor dejaba cabos sueltos al cerrarse, que encajan con los cierres
  bruscos que aparecían en el registro. No se puede dar por curado hasta
  usarlo un tiempo, pero el registro ahora deja rastro de ese cierre en vez de
  callarse.
- **El registro detallado viene desactivado.** Es una opción de diagnóstico y
  estaba activa de fábrica, lo que hacía crecer el archivo de registro sin
  necesidad.
- **El registro de diagnóstico dejó de llenarse de ruido.** Nueve de cada diez
  líneas eran de librerías internas, y con una sesión larga ese ruido borraba
  el principio del archivo, que es justo donde suele estar el problema.
- **El archivo de fallos ya no asusta.** Recoge sucesos internos de Windows, y
  muchos son inofensivos. Ahora cada arranque escribe una línea que lo explica
  y dice cuál es la señal de que la sesión terminó bien.
- **Ya no se abre una ventana negra al arrancar.** Aparecía un instante y le
  robaba el foco al lector de pantalla. Ahora la consulta se hace por detrás.

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
