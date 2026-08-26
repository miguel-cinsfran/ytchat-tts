# Configurar la API de YouTube en YTChat TTS

Esta guía explica cómo activar las funciones online de YTChat TTS:

- **Leer comentarios** de cualquier vídeo (no solo directos).
- **Moderar** el chat en vivo (expulsar o banear usuarios).
- **Enviar mensajes** al chat del directo.
- **Publicar y responder** comentarios.

Todo se gestiona desde el botón **Configuración** de la aplicación; no hay que
editar archivos a mano. Lo único que se hace fuera de la app, una sola vez, es
crear tus credenciales en Google Cloud, y eso es lo que cubre esta guía.

> **Por qué cada usuario crea sus propias credenciales.** YouTube reparte la
> cuota de uso *por proyecto*. Si cada persona usa las suyas, tiene su propia
> cuota diaria completa, no necesita que Google verifique nada y no comparte
> límites con nadie. Es la forma más sana y privada de usar la API.

La parte de moderar/comentar es opcional. Si solo quieres **leer comentarios**,
te basta con la **API key** (pasos 1 a 3); puedes saltarte el OAuth.

---

## Antes de empezar

- Necesitas una **cuenta de Google** (la misma del canal de YouTube si vas a
  moderar tu propio directo).
- Es **gratis**. La API no cuesta dinero dentro de la cuota diaria (10.000
  unidades, de sobra para uso personal).
- La consola de Google Cloud no es la web más accesible del mundo. Ve con calma,
  usa la búsqueda del navegador (Ctrl+F) para encontrar los botones por su texto,
  y sigue los pasos en orden.

---

## Paso 1 — Crear un proyecto en Google Cloud

1. Entra en <https://console.cloud.google.com/>.
2. Arriba, junto al logo, hay un **selector de proyecto**. Ábrelo y elige
   **Nuevo proyecto** ("New project").
3. Ponle un nombre, por ejemplo `YTChat TTS`, y pulsa **Crear** ("Create").
4. Espera unos segundos y asegúrate de que ese proyecto queda **seleccionado**
   en el selector de arriba.

## Paso 2 — Activar la YouTube Data API v3

1. En el buscador superior de la consola, escribe **YouTube Data API v3**.
2. Entra en el resultado y pulsa **Habilitar** ("Enable").

## Paso 3 — Crear la API key (para leer comentarios)

1. Ve al menú **APIs y servicios → Credenciales** ("APIs & Services →
   Credentials"). Puedes buscar "Credenciales" en el buscador superior.
2. Pulsa **Crear credenciales → Clave de API** ("Create credentials → API key").
3. Se generará una clave larga. **Cópiala.** Esta es tu **API key**.
4. (Recomendado) Pulsa **Restringir clave** y, en restricciones de API,
   limítala a "YouTube Data API v3". No es obligatorio pero es más seguro.

> **Para volver a ver una clave que ya existe.** En la lista de
> **Credenciales**, la columna con el valor de la clave está a la derecha del
> todo y puede quedar fuera de la pantalla: hay que desplazar la tabla en
> horizontal hasta encontrar el enlace **Mostrar clave**. La ficha que se abre
> al pulsar el *nombre* de la clave sirve para editarla, pero **no** muestra su
> valor.

➡️ Con esto ya puedes **leer comentarios**. Abre YTChat TTS, pulsa
**Configuración**, pega la clave en el campo **API key**, pulsa **Guardar
claves** y cierra. Si solo quieres leer, has terminado.

---

## Paso 4 — Configurar la pantalla de consentimiento (solo para moderar/comentar)

Esto es obligatorio antes de crear el cliente OAuth.

> **Google cambió esta parte.** Lo que antes se llamaba "Pantalla de
> consentimiento de OAuth" ahora es **Google Auth Platform**, y son cuatro
> pasos numerados dentro de una sola página en vez de un formulario largo. Los
> textos que se indican abajo son los de la consola en agosto de 2026.

1. Ve a **APIs y servicios → Pantalla de consentimiento de OAuth**. El enlace
   sigue funcionando y lleva a **Google Auth Platform**.
2. Si el proyecto no tiene nada configurado, aparece "Aún no se configuró
   Google Auth Platform". Pulsa **Comenzar**.
3. **1 Información de la app.** Escribe el **Nombre de la aplicación**, por
   ejemplo `YTChat TTS`, y elige tu correo en **Correo electrónico de
   asistencia al usuario**, que es una lista desplegable con tus direcciones.
   Pulsa **Siguiente**.
4. **2 Público.** Elige **Usuarios externos** y pulsa **Siguiente**.
5. **3 Información de contacto.** Escribe tu dirección de correo en
   **Direcciones de correo electrónico** y pulsa **Siguiente**.
6. **4 Finalizar.** Marca la casilla **Acepto la Política de Datos del Usuario
   de los Servicios de las APIs de Google** y pulsa **Continuar**.
7. Pulsa **Crear**. Aparece el aviso "Se creó la configuración de OAuth".

### Añadir tu cuenta como usuario de prueba

Sin esto el inicio de sesión se rechaza, aunque la cuenta sea la tuya.

1. En el menú de la izquierda, entra en **Público**.
2. Baja hasta **Usuarios de prueba** y pulsa **Add users**.
3. Escribe tu dirección de Gmail y pulsa **Guardar**. El contador de arriba
   tiene que pasar a decir "1 usuario (1 de prueba)".

> **Importante (la caducidad de 7 días).** Mientras la app esté en modo
> "Prueba" ("Testing"), tu sesión caduca cada **7 días** y tendrás que volver a
> pulsar "Iniciar sesión" en Configuración. Es un clic, no se pierde nada. Si te
> molesta, puedes pulsar **Publicar app** en la página **Público**: entonces no
> caduca, pero la primera vez verás un aviso de "app no verificada" que hay que
> aceptar manualmente. Cualquiera de las dos opciones sirve.

## Paso 5 — Crear el cliente OAuth (para moderar/comentar)

1. En **Google Auth Platform**, entra en **Clientes** y pulsa **Crear cliente
   de OAuth**. (También se llega desde **APIs y servicios → Credenciales →
   Crear credenciales → ID de cliente de OAuth**.)
2. En **Tipo de aplicación** elige **App de escritorio**.
3. Ponle un nombre, por ejemplo `YTChat TTS escritorio`, y pulsa **Crear**.
4. Se abre un cuadro con el **ID de cliente** y el **Secreto del cliente**, cada
   uno con su botón de copiar. **Cópialos los dos antes de cerrarlo**: el propio
   cuadro avisa de que el secreto no se puede volver a ver ni descargar una vez
   que se cierra. Si se pierde, hay que crear otro cliente.

---

## Paso 6 — Meter los datos en la aplicación

1. Abre YTChat TTS y pulsa el botón **Configuración**.
2. Pega:
   - La **API key** en su campo (paso 3).
   - El **ID de cliente OAuth** y el **Secreto de cliente OAuth** (paso 5).
3. Pulsa **Guardar claves**.
4. Pulsa **Iniciar sesión**. Se abrirá el navegador: elige tu cuenta de Google,
   acepta los permisos y vuelve a la aplicación. Oirás "Sesión iniciada
   correctamente".

A partir de aquí, el estado en Configuración dirá "sesión iniciada" y se
activan la moderación, el envío al chat y publicar comentarios.

---

## Cómo se usan las funciones

- **Leer comentarios:** conéctate a un vídeo en la barra superior y abre la
  pestaña **Comentarios**. Elige el orden y pulsa **Recargar comentarios**.
  Navega la lista con las flechas; **Enter** lo lee con la voz y **Ctrl+C** lo
  copia. Para más acciones, abre el menú contextual (tecla **Aplicaciones** o
  **Mayúsculas+F10**): **Leer con TTS**, **Copiar** y **Responder**. **Cargar
  más** trae la página siguiente. (Con orden «Más relevantes» YouTube puede
  devolver páginas repetidas; se descartan y se avisa «No hay comentarios
  nuevos». «Más recientes» pagina de forma más estable.)
- **Responder / Comentar:** con la sesión iniciada, **Responder** está en el
  menú contextual de un comentario seleccionado; **Comentar en el vídeo** es un
  botón. Nota: la API de YouTube **no permite dar «me gusta» a comentarios**
  (solo a vídeos), así que esa acción no existe en la app.
- **Moderar el chat en vivo:** conéctate a un directo del que seas dueño o
  moderador. En la lista del chat, abre el menú contextual de un mensaje (tecla
  Aplicaciones o Mayúsculas+F10): aparecerán **Expulsar 5 minutos** y **Banear
  del directo**. Se pide confirmación antes de actuar.
- **Enviar un mensaje al chat del directo:** botón **Enviar al chat** (se activa
  al conectarte a un directo con sesión iniciada).

---

## Preguntas frecuentes

**¿Es peligroso para mi cuenta?**
El permiso solo cubre acciones de YouTube (leer, comentar, moderar como tu
canal). No puede cambiar tu contraseña, leer tu correo ni borrar tu cuenta.
Puedes revocarlo cuando quieras desde
<https://myaccount.google.com/permissions>.

**¿Dónde se guardan mis claves?**
En un archivo `credenciales.json` junto al programa, solo en tu equipo. Nunca se
sube a internet ni al repositorio (está excluido por `.gitignore`).

**¿Se nota que escribo desde una aplicación?**
Para los espectadores, no: tus mensajes y comentarios salen como tu canal, sin
etiqueta. El único matiz es que YouTube a veces retiene o filtra los comentarios
publicados por API más que los hechos desde la web.

**Se agotó la cuota.**
Cada acción de escritura gasta unas 50 unidades y leer comentarios gasta muy
poco. Si agotas las 10.000 del día (uso muy intenso), se renueva al día
siguiente.

**Me pide iniciar sesión otra vez.**
Normal si dejaste la app en modo "Prueba": la sesión caduca a los 7 días. Pulsa
"Iniciar sesión" de nuevo, o publica la app (paso 4) para que no caduque.
