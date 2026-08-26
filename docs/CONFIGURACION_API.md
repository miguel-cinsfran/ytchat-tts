# Configurar la API de YouTube en YTChat TTS

Esta guía explica cómo activar las funciones online de YTChat TTS:

- **Leer comentarios** de cualquier vídeo (no solo directos).
- **Moderar** el chat en vivo (expulsar o banear usuarios).
- **Enviar mensajes** al chat del directo.
- **Publicar y responder** comentarios.

Todo se gestiona desde el botón **Configuración** de la aplicación; no hay que
editar archivos a mano. Lo único que se hace fuera de la app, una sola vez, es
crear las credenciales en Google Cloud, y eso es lo que cubre esta guía.

> **Por qué cada usuario crea sus propias credenciales.** YouTube reparte la
> cuota de uso *por proyecto*. Si cada persona usa las suyas, tiene su propia
> cuota diaria completa, no necesita que Google verifique nada y no comparte
> límites con nadie. Es la forma más sana y privada de usar la API.

La parte de moderar y comentar es opcional. Para **leer comentarios** basta con
la API key, o sea los pasos 1 a 3; el resto se puede saltar.

---

## Cómo seguir esta guía con lector de pantalla

La consola de Google Cloud es incómoda de recorrer: tiene menús que se
despliegan, tablas que se desplazan en horizontal y un selector de proyecto que
cuesta manejar. Estas cuatro cosas evitan casi todo eso.

**Ir por enlace directo, no por los menús.** Cada paso de esta guía trae la
dirección exacta de su pantalla. Pegarla en la barra de direcciones lleva
directo, sin recorrer ningún menú.

**Añadir el proyecto a la dirección para saltarse el selector.** Una vez creado
el proyecto, su identificador se puede pegar al final de cualquier dirección de
la consola. Si el identificador es `ytchat-tts`, entonces
`https://console.cloud.google.com/apis/credentials?project=ytchat-tts` abre las
credenciales de ese proyecto sin tocar el selector. Los enlaces de esta guía
llevan un hueco `TU-PROYECTO` para reemplazar.

**Buscar los botones por su texto con Ctrl+F.** Los nombres exactos de esta
guía son los de la consola en agosto de 2026, en español.

**La consola tarda.** Varias pantallas se quedan unos segundos en blanco antes
de dibujar la tabla. No es que no haya nada: conviene esperar y volver a
recorrer antes de dar por hecho que falta algo.

---

## Antes de empezar

- Hace falta una **cuenta de Google**, la misma del canal de YouTube si se va a
  moderar el propio directo.
- Es **gratis**. La API no cuesta dinero dentro de la cuota diaria de 10.000
  unidades, de sobra para uso personal.
- El proceso completo son unos diez minutos y se hace una sola vez.

---

## Paso 1 — Crear el proyecto

Dirección directa: <https://console.cloud.google.com/projectcreate>

1. En **Nombre del proyecto**, escribir por ejemplo `YTChat TTS`.
2. Debajo del campo, la consola muestra una línea que dice **ID del proyecto**
   seguida del identificador que ha generado. **Conviene anotarlo ahora**: es
   lo que se pega en las direcciones del resto de la guía, y no se puede
   cambiar después. Junto a esa línea hay un enlace **Editar** por si se
   prefiere elegirlo a mano.
3. Pulsar **Crear** y esperar unos segundos.

> Si ya existe un proyecto de una vez anterior, no hace falta crear otro. La
> lista de proyectos, con sus identificadores, está en
> <https://console.cloud.google.com/cloud-resource-manager>

## Paso 2 — Activar la YouTube Data API v3

Dirección directa, reemplazando el identificador:

    https://console.cloud.google.com/apis/library/youtube.googleapis.com?project=TU-PROYECTO

Pulsar **Habilitar**. Si el botón dice **Administrar** en vez de Habilitar, ya
estaba activada y no hay que hacer nada.

## Paso 3 — Crear la API key

Dirección directa:

    https://console.cloud.google.com/apis/credentials?project=TU-PROYECTO

1. Pulsar **Crear credenciales** y, en el menú que se abre, **Clave de API**.
2. Se abre un cuadro con la clave recién creada y un botón para copiarla.
   **Copiarla ahora.**
3. Recomendado, no obligatorio: pulsar **Restringir clave** y, en las
   restricciones de API, limitarla a "YouTube Data API v3".

> **Para recuperar una clave que ya existe.** Esto tiene una trampa que cuesta
> encontrar. En la lista de **Credenciales**, la tabla de claves de API es más
> ancha que la pantalla, y el enlace **Mostrar clave** está en la última
> columna, fuera de la vista: hay que desplazar **la tabla** en horizontal para
> alcanzarlo. Pulsar el *nombre* de la clave abre su ficha de edición, que
> permite restringirla y renombrarla pero **no muestra su valor**.

Con esto ya se pueden **leer comentarios**. En YTChat TTS: botón
**Configuración**, pegar la clave en el campo **API key**, pulsar **Guardar
claves** y cerrar. Quien solo quiera leer ha terminado aquí.

---

## Paso 4 — Configurar la pantalla de consentimiento

Obligatorio antes de crear el cliente OAuth, y solo hace falta para moderar,
comentar y enviar mensajes al chat.

> **Google cambió esta parte.** Lo que antes se llamaba "Pantalla de
> consentimiento de OAuth" ahora es **Google Auth Platform**, y son cuatro
> pasos numerados dentro de una misma página en vez de un formulario largo.

Dirección directa:

    https://console.cloud.google.com/auth/overview?project=TU-PROYECTO

1. Si el proyecto no tiene nada configurado, la página dice "Aún no se
   configuró Google Auth Platform". Pulsar **Comenzar**.
2. **Paso 1, Información de la app.** Escribir el **Nombre de la aplicación**,
   por ejemplo `YTChat TTS`. En **Correo electrónico de asistencia al usuario**
   hay una lista desplegable: elegir la propia dirección. Pulsar **Siguiente**.
3. **Paso 2, Público.** Elegir **Usuarios externos** y pulsar **Siguiente**.
4. **Paso 3, Información de contacto.** Escribir la propia dirección de correo
   en **Direcciones de correo electrónico** y pulsar **Siguiente**.
5. **Paso 4, Finalizar.** Marcar la casilla **Acepto la Política de Datos del
   Usuario de los Servicios de las APIs de Google** y pulsar **Continuar**.
6. Pulsar **Crear**. Aparece el aviso "Se creó la configuración de OAuth".

### Añadir la propia cuenta como usuario de prueba

**Este paso es obligatorio y es el que más se olvida.** Sin él, el inicio de
sesión se rechaza aunque la cuenta sea la dueña del proyecto.

Dirección directa:

    https://console.cloud.google.com/auth/audience?project=TU-PROYECTO

1. Bajar hasta el apartado **Usuarios de prueba** y pulsar **Add users**.
2. Escribir la dirección de Gmail y pulsar **Guardar**.
3. Comprobar que el contador de la página pasa a decir "1 usuario (1 de
   prueba)". Si sigue en cero, no se guardó.

> **La caducidad de 7 días.** Mientras la app esté en estado "Prueba", la
> sesión caduca cada **7 días** y hay que volver a pulsar "Iniciar sesión" en
> Configuración. Es un clic y no se pierde nada. En esa misma página hay un
> botón **Publicar app** que quita la caducidad; a cambio, la primera vez
> aparece un aviso de "app no verificada" que hay que aceptar a mano.
> Cualquiera de las dos opciones sirve.

## Paso 5 — Crear el cliente OAuth

Dirección directa:

    https://console.cloud.google.com/auth/clients?project=TU-PROYECTO

1. Pulsar **Crear cliente de OAuth**.
2. En **Tipo de aplicación**, elegir **App de escritorio**. La lista trae otras
   opciones (Aplicación web, Android, Extensión de Chrome, iOS, TVs); ninguna
   de ellas sirve para esta aplicación.
3. En **Nombre**, escribir por ejemplo `YTChat TTS escritorio`, y pulsar
   **Crear**.
4. Se abre un cuadro titulado "Se creó el cliente de OAuth" con el **ID de
   cliente** y el **Secreto del cliente**, cada uno con su botón de copiar.

> **Copiar los dos antes de cerrar ese cuadro.** El propio cuadro lo advierte:
> el secreto **no se puede volver a ver ni descargar** una vez que se cierra.
> Si se pierde, no hay forma de recuperarlo y hay que crear otro cliente. El ID
> de cliente sí queda visible después, en la lista de clientes.

---

## Paso 6 — Meter los datos en la aplicación

1. Abrir YTChat TTS y pulsar el botón **Configuración**.
2. Pegar la **API key** del paso 3, y el **ID de cliente** y el **Secreto de
   cliente** del paso 5, cada uno en su campo.
3. Pulsar **Guardar claves**.
4. Pulsar **Iniciar sesión**. Se abre el navegador.

En el navegador, la secuencia es de tres pantallas:

1. **"Elegir una cuenta"**: pulsar sobre la cuenta.
2. **"Google no verificó esta app"**: pulsar **Continuar**. Este aviso es
   normal y aparece porque la app está en estado "Prueba"; el enlace grande que
   dice "Volver a un sitio seguro" es el que **no** hay que pulsar.
3. **"YTChat TTS requiere acceso a tu Cuenta de Google"**: pulsar
   **Continuar**. El permiso que se concede es solo de YouTube.

Al terminar, el navegador muestra "Sesión iniciada. Ya puedes volver a la
aplicación", y la aplicación anuncia que la sesión se inició correctamente.

A partir de aquí, el estado en Configuración dice "sesión iniciada" y se
activan la moderación, el envío al chat y publicar comentarios.

---

## Si algo sale mal

**"Error 403: access_denied" al iniciar sesión.** Falta el usuario de prueba.
Volver al paso 4, apartado de usuarios de prueba, y comprobar que el contador
dice "1 usuario (1 de prueba)".

**Se perdió el secreto de cliente.** No se puede recuperar. Hay que crear otro
cliente OAuth con el paso 5; el anterior se puede borrar desde la lista de
clientes.

**Pide iniciar sesión otra vez a los pocos días.** Es la caducidad de 7 días
del estado "Prueba". Se resuelve con un clic en "Iniciar sesión", o publicando
la app como explica el paso 4.

**"Se agotó la cuota".** Cada acción de escritura gasta unas 50 unidades y leer
comentarios gasta muy poco. Agotar las 10.000 diarias requiere un uso muy
intenso. Se renueva al día siguiente.

**No aparece la clave de API en la lista.** Es la trampa de la tabla ancha del
paso 3: el enlace "Mostrar clave" está en una columna que queda fuera de la
pantalla y hay que desplazar la tabla en horizontal.

---

## Cómo se usan las funciones

- **Leer comentarios:** conectarse a un vídeo en la barra superior y abrir la
  pestaña **Comentarios**. Elegir el orden y pulsar **Recargar comentarios**.
  La lista se recorre con las flechas; **Enter** lo lee con la voz y **Ctrl+C**
  lo copia. Para más acciones, el menú contextual (tecla **Aplicaciones** o
  **Mayúsculas+F10**): **Leer con TTS**, **Copiar** y **Responder**. **Cargar
  más** trae la página siguiente. Con el orden "Más relevantes", YouTube puede
  devolver páginas repetidas; se descartan y se avisa "No hay comentarios
  nuevos". "Más recientes" pagina de forma más estable.
- **Responder y comentar:** con la sesión iniciada, **Responder** está en el
  menú contextual de un comentario seleccionado, y **Comentar en el vídeo** es
  un botón. La API de YouTube **no permite dar "me gusta" a comentarios**, solo
  a vídeos, así que esa acción no existe en la aplicación.
- **Moderar el chat en vivo:** conectarse a un directo del que se sea dueño o
  moderador. En la lista del chat, el menú contextual de un mensaje (tecla
  Aplicaciones o Mayúsculas+F10) ofrece **Expulsar 5 minutos** y **Banear del
  directo**. Se pide confirmación antes de actuar.
- **Enviar un mensaje al chat del directo:** menú **Enviar mensaje al chat del
  directo**, que se activa al conectarse a un directo de YouTube con la sesión
  iniciada.

---

## Preguntas frecuentes

**¿Es peligroso para la cuenta?**
El permiso solo cubre acciones de YouTube: leer, comentar y moderar como el
propio canal. No puede cambiar la contraseña, leer el correo ni borrar la
cuenta. Se puede revocar en cualquier momento desde
<https://myaccount.google.com/permissions>

**¿Dónde se guardan las claves?**
En un archivo `credenciales.json` junto al programa, solo en ese equipo. Nunca
se sube a internet ni al repositorio: está excluido por `.gitignore`. Eso
significa también que **no viajan a otro ordenador**: en una segunda máquina
hay que repetir el paso 6, aunque el proyecto de Google ya esté creado y sirva
el mismo ID de cliente.

**¿Se nota que los mensajes salen de una aplicación?**
Para los espectadores, no: salen como el propio canal, sin etiqueta. El único
matiz es que YouTube a veces retiene o filtra los comentarios publicados por
API más que los hechos desde la web.
