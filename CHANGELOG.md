# Changelog de YTChat TTS

Los cambios notables de cada versión. Las versiones siguen el esquema
mayor.menor.parche; las 0.8.x fueron internas (previas a la primera release
pública).

## Sin publicar (será la 2.0.0)

En `main`, pendiente de pulido y de pruebas con NVDA antes de lanzarse.

### Añadido
- **Directos de TikTok** (solo lectura, sin login): pegando una URL
  `tiktok.com/@usuario/live` se lee el chat, los regalos (con su valor en
  diamantes, anunciando el total al final de cada racha) y las suscripciones,
  y el vídeo del directo se ve en el reproductor integrado (flujo HLS directo
  en libVLC, sin yt-dlp). Usa la librería no oficial TikTokLive; en TikTok no
  hay comentarios de vídeo, ni envío al chat, ni moderación.
- Los anuncios al lector de pantalla ahora van también a la **línea braille**
  (mismo patrón que TWBlue).

### Interno
- Pipeline común de mensajes entrantes (`procesar_entrante`) compartido por
  YouTube y TikTok: filtros, texto TTS, GUI y cola en un solo sitio.

## 1.0.0 — 2026-07-08

Primera release pública. (Se publicó brevemente con el número 0.1.0 por un
error de numeración; es la misma versión.)

### Añadido
- Selector de **voz** también en Preferencias → Lectura (antes solo estaba en
  el menú Voz → Seleccionar voz).

### Corregido
- La lista del chat se desalineaba al superar los 500 mensajes: copiar,
  releer, silenciar o **banear** podían caer sobre el mensaje equivocado, y el
  último mensaje dejaba de responder. El modelo de la lista ahora vive en un
  módulo puro con tests (`lista_chat.py`).
- Alt+F4 en la pantalla completa del reproductor dejaba el vídeo dibujando en
  una ventana muerta y rompía el siguiente intento de pantalla completa.
- Un directo o vídeo de una sesión anterior ya no puede colar su sonido de
  conexión ni lecturas TTS tras desconectar (el token de sesión cubre ahora
  también la cola de lectura).
- Ajustar velocidad/volumen del TTS muy rápido podía anunciar y guardar un
  valor desfasado del real.
- `construir.bat` creaba un archivo basura por una redirección accidental.
- Los menús contextuales acumulaban manejadores de eventos con cada apertura.
- «Cargar más» comentarios quedaba desactivado tras un error transitorio.
- Etiquetas del editor de atajos: retroceder/avanzar es 1 minuto, no 10 s.

### Cambiado
- README reescrito: corto y directo.
- Los tests ya no ensucian el `ytchat.log` real.

## 0.8.x — junio 2026 (internas)

- 0.8.2: comentarios por menú contextual, fix del volumen del reproductor,
  reset total al desconectar, reproductor minimalista con botones ocultables.
- 0.8.1: reproductor precalentado, fix de reconexión, layout 3:2.
- 0.8.0 y anteriores: rediseño a menú + pestañas, reproductor libVLC,
  moderación por API oficial, panel de información del vídeo, temas de sonido.
