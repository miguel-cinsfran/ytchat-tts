# AGENTS.md — YTChat TTS (contraparte de Gentle-AI / OpenCode)

> Adaptado de `CLAUDE.md` de Claude Code (que vive en Windows y está en
> `.gitignore`, por lo que **no se clona**). Este es el mapa para que
> **Gentle-AI (OpenCode)** y Claude trabajen en el mismo repo sin pisarse.
> Combinado con la revisión de código del 2026-07-13 sobre la rama
> `wip/gentle-ai`.

---

## Qué es

Lector accesible del chat de YouTube Live (y TikTok) con voz SAPI5, para
**streamers ciegos** en Windows 10/11. Herramienta real, probada con NVDA.
Además del chat: comentarios de vídeos, moderación por API oficial de YouTube,
y un reproductor de vídeo (libVLC). La usa un amigo del dueño.

Repo: `miguel-cinsfran/ytchat-tts` (público).

## Regla de oro

**No rompas la accesibilidad con NVDA.** Es la prioridad nº 1. Cada control de
la GUI debe tener nombre accesible (`name=` en wx), ser alcanzable con Tab, y las
acciones importantes se anuncian con `anunciar()` (voz **y** braille vía
`accessible_output2`). Antes de tocar GUI, mirá cómo lo hace el código existente
y replicarlo (`&` en etiquetas, `name=`, sonidos `_snd`, `anunciar`). El usuario
es ciego y usa el lector en "modo lector": sin arte ASCII ni `clear`, salida
sobria. **Cuidado**: dar color a una casilla/radio en Windows rompe su rol de
accesibilidad (ver `.claude/atajos-y-diseno.md` en Windows).

**CUIDADO con `gui.py`**: es un "dios-frame" de ~1882 líneas en una sola clase
`YTChatFrame`. Cualquier feature de UI lo infla y es riesgo alto de regresión.
Extraé sub-dialogs/panels (como ya hacen `gui_preferencias.py` /
`gui_historial.py`) en vez de meter todo ahí. `main.py` (~808 líneas) también
mezcla orquestación + extracción de URL + bucle de captura; no empeorarlo.

## Entorno y cómo ejecutar

- **Python 3.11+ de 64 bits.** El dueño usa **uv** (`uv run python ...`).
- **Windows nativo, NO WSL** para GUI/SAPI5/accesibilidad/VLC.
- En **WSL (este entorno)** la GUI no corre (wxPython/Windows). **SÍ** corren:
  los tests de lógica pura y `smoke_test.py` fases 1 y 2. La fase 3 (pywinauto +
  árbol de accesibilidad real) necesita Windows.
- Dependencias: `pip install -r requirements.txt`. Sonidos (1ª vez):
  `python sound_gen.py`. Arrancar: `python main.py`. Empaquetar: `construir.bat`.

## Verificación (lo automatizable)

1. **Tests de lógica pura:** `python -m unittest discover -s tests` (deben dar
   OK). Lógica nueva aislable → módulo puro + tests (como `montos.py`,
   `deteccion.py`).
2. **Smoke + accesibilidad:** `python smoke_test.py`
   - F1: importa lógica pura. F2: importa la GUI (caza NameError/atributos
     faltantes). F3 (con `pywinauto`, solo Windows): lanza la app, recorre el
     árbol de accesibilidad (UI Automation, lo que lee NVDA) y avisa de controles
     interactivos sin nombre. `--no-gui` salta las fases con ventana.

Lo que **NO** se puede verificar aquí: oír NVDA/SAPI5, login OAuth, **ver la
ventana** (este entorno no renderiza: capturas negras), ni el "feeling" real.
Sí: que los controles existen y están etiquetados, que el código corre, conducir
flujos con pywinauto, y verificar iconos/paleta dibujando a PNG.

## Convenciones del código (mapeadas de la revisión)

- **Español en todo**: identificadores y strings de UI. No hay i18n, todo
  hardcodeado en español. Imitá la densidad de comentarios y el estilo del
  archivo que editás.
- **Frontera pura / plataforma**: lo testeable sin wx/Windows va a un módulo
  puro (`deteccion.py`, `montos.py`, `lista_chat.py`, `metadatos.py`,
  `estado_sesion.py`, parsers de `youtube_api.py`, etc.); la GUI solo invoca.
  Por eso los 214 tests de `tests/` corren en Linux. Mantené esa frontera para
  no romper CI.
- **Errores SIEMPRE por 3 vías**: sonido `_snd.reproducir("error")` + `anunciar()`
  al lector de pantalla + texto en la GUI. **Nunca** tirar el hilo de captura;
  reintentar y reconectar con contador (`_ERRORES_PERMANENTES`, `MAX_ERR`).
- **Config**: `config.ini` / `sounds.ini` en `app_dir()`. Usar
  `guardar_opcion()` (reescribe línea a línea) para **preservar comentarios**; no
  volcar el parser entero. `credenciales.json` y `historial_lives.json` van
  aparte y están en `.gitignore`.
- **wx**: `wx.CallAfter(...)` **obligatorio** para mutar la GUI desde hilos de
  captura. Comparar el `gen` de sesión (`_estado["gen"]`) para descartar mensajes
  de sesiones obsoletas.
- **Estilo**: docstrings y comentarios en español, type hints en casi todo
  (`from __future__ import annotations`), 4 espacios. Constantes en MAYÚSCULA.

## Ramas / workflow (IMPORTANTE — reconciliar con Claude)

- **Regla del dueño** (en `CLAUDE.md`): trabajar SIEMPRE en `main`, nunca crear
  otras ramas; commitear y pushear a `main`.
- **Excepción de esta colaboración**: el usuario pidió explícitamente una rama
  secundaria `wip/gentle-ai` para evaluar a Gentle-AI sin tocar `main`. Por
  ahora: **todo el trabajo de Gentle-AI va a `wip/gentle-ai`**. Al cerrar la
  evaluación, reconciliar con Claude (que sigue la regla de `main`) antes de
  mezclar. **No romper la regla de `main` sin confirmación del dueño.**
- Commits/mensajes en español. Empaquetar y commitear solo cuando se pida.

## Versionado

En `main` está la **2.0.0** (`APP_VERSION` ya bumpeada; TikTok fiable,
historial, multi-voz, captura de atajos, búsqueda por letras…). La v1.0.0 quedó
tageada/publicada en GitHub pero su ZIP nunca se subió. A partir de aquí:
arreglos → 2.0.1, 2.0.2…; funciones nuevas → 2.1, 2.2… El bump se hace en el
commit de release; tag y release cuando el dueño lo confirme.

## Documentación (README + CHANGELOG + HTML)

- El historial de versiones vive en **`CHANGELOG.md`** (desde la 2.0.0), una
  entrada por versión, en lenguaje llano y sin tecnicismos (el detalle está en
  los commits). El README enlaza «qué hay de nuevo».
- **HTML para el usuario final:** los `.md` son para nosotros/GitHub; el amigo
  que usa la app no sabe abrir Markdown. `generar_docs.py` convierte README,
  CHANGELOG y la guía de la API a HTML autocontenido (pandoc) en `docs/`.
  Regenerar y commitear los HTML **junto** con el `.md`:
  `uv run python generar_docs.py`.

## Lecciones de otros proyectos (no reinventar la rueda)

- **TWBlue (MCV-Software/TWBlue)**: LA referencia de app wxPython accesible por
  y para ciegos. De ahí salió que `anunciar()` mande voz **y braille**. Explorar
  con `gh api repos/MCV-Software/TWBlue/contents/src`.
- **eleven-tts-studio (tonygeb23)**: app TTS + wxPython de dev ciego. De su
  `set_accessible_name` salió nuestro `gui.nombre_accesible(ctrl, nombre)`
  (SetName + `wx.Accessible` que solo nombra el control, no sus filas, + HelpText).
  **NO tocar** el `_PosAccesible` del deslizador de posición (ya da nombre Y
  valor).
- **bellbird (miguel-cinsfran/bellbird)**: otro proyecto del dueño (cliente
  accesible de LLMs, wxPython). De su `core/status_formatter.py` salió
  `estado_sesion.py` (snapshot puro + toggles + modo corto/largo) y la pestaña
  Preferencias → Estado (F2).
- Nuestro filtro de SAPI en `_ao2_init` (no anunciar por SAPI si no hay lector
  activo) es deliberado y mejor que lo de TWBlue para este caso: **no quitarlo**.

## TikTok (gotchas)

- Dependencias: TikTokLive 6.x exige `betterproto` beta (pin explícito o uv no lo
  instala) y `httpx<1` para convivir con pytchat.
- **NO usar `evento.user`** (crashea con betterproto 2.0.0b7: `to_pydict` devuelve
  camelCase). Leer el autor con `tiktok_captura.autor_de_evento` (campo real
  `nick_name`) + `_parchear_extended_user()`. Se perdían comentarios por esto.
- Reproducir el **FLV** (`flv_pull_url`), no el HLS (da timeout). Ver
  `tiktok_captura._mejor_flujo`.
- Cuentas de prueba (los lives son efímeros): `@tv_asahi_news` (japonés, a veces
  off), `@larzock` (activo).
- **Fase 2 (comentar/moderar) descartada** por ahora (sin API oficial, riesgo de
  baneo).

## Referencias internas NO presentes en este clon

Viven en Windows y están en `.gitignore`. Si hace falta profundidad, pedir que
las peguen o explorarlas desde los repos referenciados:

- `.claude/arquitectura.md`, `.claude/empaquetado.md`, `.claude/atajos-y-diseno.md`,
  `.claude/decisiones.md` — mapas de módulos, build/libVLC, atajos/diseño, captura/credenciales.
- `estado.md` (raíz) — tablero de control: versión actual, qué falta, pruebas NVDA.
- `INFORME_CLAUDE.md`, `INFORME_TIKTOK.md`, `INFORME_UI.md` — informes internos.
