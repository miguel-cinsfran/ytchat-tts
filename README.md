# YTChat TTS

Lector del chat de YouTube Live con las voces SAPI5 de Windows, pensado para
streamers ciegos o con baja visión. Toda la interfaz se maneja con teclado y
está probada con NVDA.

Versión 1.0.0 · Windows 10/11. Historial de cambios en [CHANGELOG.md](CHANGELOG.md).

## Qué hace

Pegas la URL de un directo (o de un vídeo normal) y la app se conecta sola:

- **Chat en vivo**: lee cada mensaje con una voz SAPI5, con sonidos distintos
  para mensajes, Super Chats y membresías. Se puede pausar, cambiar de voz y
  de velocidad al vuelo, filtrar por palabras o usuarios, y silenciar a alguien
  en el momento desde el menú contextual.
- **Comentarios**: si la URL es un vídeo subido, muestra sus comentarios y los
  lee con la misma voz. Con sesión iniciada se puede comentar y responder.
- **Reproductor integrado**: ve el directo o el vídeo dentro de la app (libVLC),
  con calidad seleccionable, pantalla completa y volumen propio, todo por
  teclado. Es minimalista por defecto; los botones en pantalla son opcionales.
- **Moderación** (opcional, con la API oficial de YouTube): expulsar o banear
  usuarios del chat y enviar mensajes al directo.
- **Pestaña Información**: canal, vistas, fecha y descripción del vídeo, con
  los enlaces clicables.
- **Directos de TikTok** (en desarrollo, saldrá en la 2.0): pega una URL tipo
  `tiktok.com/@usuario/live` y lee el chat, los regalos y las suscripciones
  con la misma voz, con el vídeo del directo en el reproductor. Solo lectura:
  en TikTok no se puede comentar ni moderar desde la app.

Los anuncios importantes se envían al lector de pantalla (NVDA/JAWS) y cada
control tiene nombre accesible. Hay navegación por regiones con F6 y una barra
de menú nativa donde se ven todos los atajos.

## Cómo usarla

**Con el ejecutable** (lo normal): descomprime el ZIP en cualquier carpeta y
abre `YTChatTTS.exe`. No necesita Python ni instalación; libVLC ya viene
incluido. Solo hace falta tener al menos una voz SAPI5 en Windows
(*Configuración → Hora e idioma → Voz*).

**Desde el código fuente**: instala [uv](https://docs.astral.sh/uv/) y ejecuta
`instalar.bat` (crea el entorno e instala las dependencias) y después
`ejecutar.bat`. Para generar el ZIP distribuible: `construir.bat`.

Una vez abierta: pega la URL, Enter o el botón **Conectar**, y listo. F6 cambia
de región (conexión / contenido / reproductor), Ctrl+Tab cambia de pestaña, y
la tecla Aplicaciones abre el menú contextual sobre el chat o los comentarios.

## Atajos principales

El modificador indica el área: **Ctrl** para el reproductor, **Alt** para la
conexión y el chat, **teclas F** para la voz. Se editan en Preferencias → Atajos.

- Alt+C / Alt+D — conectar / desconectar.
- F5 — pausar o reanudar la lectura. F8 — callar la voz actual.
- F9/F10 y F11/F12 — velocidad y volumen del TTS.
- Ctrl+P — reproducir/pausa. Ctrl+← / Ctrl+→ — retroceder/avanzar 1 minuto.
- Ctrl+↑ / Ctrl+↓ — volumen del reproductor. Ctrl+F — pantalla completa.
- F2 — anunciar el estado por voz.

La lista completa está en la barra de menú, junto a cada acción.

## Configuración

Casi todo se ajusta en **Herramientas → Preferencias** (voz, lectura, filtros,
atajos, API) y se aplica al momento. Por debajo queda en `config.ini` y
`sounds.ini`, editables con el Bloc de notas; si se borran, se regeneran.

Las funciones de la API de YouTube (comentarios, moderación, enviar al chat)
son opcionales y usan credenciales propias de cada usuario. La guía paso a
paso, pensada para lectores de pantalla, está en
[docs/CONFIGURACION_API.md](docs/CONFIGURACION_API.md).

## Problemas frecuentes

- **No hay voces**: añade una en *Configuración → Hora e idioma → Voz*. Las
  voces neurales de Windows 11 no aparecen en SAPI5 por defecto; la herramienta
  gratuita *TTSVoicePatcher* las expone.
- **"Windows protegió tu PC"** al abrir el exe: es SmartScreen porque el
  ejecutable no está firmado. *Más información → Ejecutar de todos modos*.
- **El antivirus marca el exe**: falso positivo típico de PyInstaller; añade
  la carpeta a las exclusiones.
- **Algo falla**: `ytchat.log`, junto al ejecutable, guarda los errores. En
  operación normal está vacío.

## Pruebas

```
uv run python -m unittest discover -s tests   # lógica pura, corre en cualquier SO
uv run python smoke_test.py                   # imports de GUI + árbol de accesibilidad (Windows)
```

## Licencia

MIT — ver [LICENSE](LICENSE).
