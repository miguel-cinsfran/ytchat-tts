"""Constantes, carga de configuración, atajos de teclado y logging."""

from __future__ import annotations

import configparser
import logging
import re
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path


# ── Identidad ─────────────────────────────────────────────────────────────────

APP_NAME    = "YTChat TTS"
APP_VERSION = "1.0.0"

# ── Tipos de mensaje ──────────────────────────────────────────────────────────

TIPO_TEXTO     = "text"
TIPO_SUPERCHAT = "superchat"
TIPO_STICKER   = "sticker"
TIPO_MIEMBRO   = "member"
TIPO_ENTRADA   = "entrada"   # alguien entra al directo (solo TikTok, opcional)

FILTROS = [
    ("Todos",        None),
    ("Solo texto",   TIPO_TEXTO),
    ("Super Chats",  TIPO_SUPERCHAT),
    ("Membresías",   TIPO_MIEMBRO),
]


# ── Carpeta base ──────────────────────────────────────────────────────────────
# Cuando se empaqueta con PyInstaller (onedir), los archivos editables
# (config.ini, sounds.ini, sounds/) viven junto al .exe, no dentro de
# _MEIPASS. Esta función resuelve la ruta correcta en ambos contextos.

def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


# ── Logging ───────────────────────────────────────────────────────────────────

def configurar_logging(nivel_consola: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(nivel_consola)
    ch.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(ch)

    log_path = app_dir() / "ytchat.log"
    try:
        fh = RotatingFileHandler(log_path, maxBytes=1_048_576, backupCount=1, encoding="utf-8")
        fh.setLevel(logging.WARNING)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(fh)
    except Exception as exc:
        logging.getLogger(__name__).warning("No se pudo crear ytchat.log: %s", exc)

    # httpx (dep de pytchat) ensucia la consola con cada petición HTTP.
    for _lib in ("httpx", "httpcore", "httpcore.http11", "httpcore.connection", "hpack", "h2"):
        logging.getLogger(_lib).setLevel(logging.WARNING)


# ── Atajos de teclado ─────────────────────────────────────────────────────────
# Esquema por ÁREA: el modificador indica la zona, para que sea intuitivo.
#   Ctrl  → Reproductor (vídeo/audio), como las apps de medios.
#   Alt   → Conexión y chat (acciones sobre el directo).
#   F     → Voz/lectura TTS (ajustes en caliente) y navegación.
# Se muestran como aceleradores en la barra de menú (NVDA los lee). No chocan
# con los mnemónicos de menú (Alt+inicial) porque usamos otras letras.
#
# Fijos (no editables): F9/F10 velocidad y F11/F12 volumen del TTS, y la
# navegación entre regiones F6 / Shift+F6 (esta última no está aquí: la gestiona
# la ventana directamente).

ATAJOS_DEFAULTS = {
    # Reproductor (Ctrl)
    "rep_play":          "ctrl+p",
    "rep_retro":         "ctrl+left",
    "rep_avanz":         "ctrl+right",
    "rep_detener":       "ctrl+d",
    "rep_mute":          "ctrl+m",
    "rep_vol_menos":     "ctrl+down",
    "rep_vol_mas":       "ctrl+up",
    # Conexión y chat (Alt)
    "conectar":          "alt+c",
    "desconectar":       "alt+d",
    "enviar_chat":       "alt+enter",
    # Voz / lectura (teclas F)
    "pausa":             "f5",
    "detener_tts":       "f8",
    "velocidad_menos":   "f9",
    "velocidad_mas":     "f10",
    "volumen_menos":     "f11",
    "volumen_mas":       "f12",
    "silenciar_lectura": "f4",
    "silenciar_sonidos": "f7",
    "anunciar_estado":   "f2",
}

# Acciones cuya tecla NO debe poder cambiarse en el editor de atajos.
ATAJOS_FIJOS = {"velocidad_menos", "velocidad_mas", "volumen_menos", "volumen_mas"}

# Agrupación para el editor de Preferencias (título de grupo, acciones).
ATAJOS_GRUPOS = [
    ("Reproductor (Ctrl)",
     ["rep_play", "rep_retro", "rep_avanz", "rep_detener", "rep_mute",
      "rep_vol_menos", "rep_vol_mas"]),
    ("Conexión y chat (Alt)",
     ["conectar", "desconectar", "enviar_chat"]),
    ("Voz y lectura (teclas F)",
     ["pausa", "detener_tts", "velocidad_menos", "velocidad_mas",
      "volumen_menos", "volumen_mas", "silenciar_lectura",
      "silenciar_sonidos", "anunciar_estado"]),
]

# Modificador obligatorio por acción: reproductor → Ctrl, app → Alt, voz → F.
# Así el atajo es global y único, sin depender del panel con foco.
_AREA_POR_GRUPO = ("ctrl", "alt", "f")
ATAJOS_AREA = {ac: _AREA_POR_GRUPO[i]
               for i, (_titulo, acs) in enumerate(ATAJOS_GRUPOS) for ac in acs}

_SIMBOLOS_PERMITIDOS = {",", ".", ";", "'", "[", "]", "/", "-"}
# Teclas con nombre admitidas (además de una letra/símbolo o una tecla F).
_TECLAS_NOMBRE = {"enter", "left", "right", "up", "down", "space"}
_RE_ATAJO = re.compile(r"^(ctrl|alt)\+(.+)$", re.IGNORECASE)
_RE_FKEY  = re.compile(r"^f(1[0-2]|[1-9])$", re.IGNORECASE)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Atajo:
    accion: str
    texto:  str
    tecla:  str


def _normalizar_atajo(valor: str | None) -> str | None:
    """Normaliza a 'ctrl+x' / 'alt+enter' / 'ctrl+left' / 'f5'. None si no vale.

    Modificador único (ctrl o alt) + tecla, o una tecla F sin modificador.
    """
    if valor is None:
        return None
    valor = valor.strip().lower().replace(" ", "")
    if not valor:
        return None
    if _RE_FKEY.match(valor):
        return valor
    m = _RE_ATAJO.match(valor)
    if not m:
        return None
    mod, key = m.group(1), m.group(2)
    if key in _TECLAS_NOMBRE:
        return f"{mod}+{key}"
    if len(key) == 1 and key.isascii() and (key.isalnum() or key in _SIMBOLOS_PERMITIDOS):
        return f"{mod}+{key}"
    return None


def atajo_valido_para_area(accion: str, normalizado: str | None) -> bool:
    """¿El atajo respeta el modificador del área de la acción?

    Reproductor → Ctrl, app → Alt, voz → tecla F. Vacío (desactivado) o acción
    sin área definida se aceptan sin restricción.
    """
    area = ATAJOS_AREA.get(accion)
    if not normalizado or area is None:
        return True
    if area == "f":
        return bool(_RE_FKEY.match(normalizado))
    return normalizado.startswith(area + "+")


def parsear_atajos(raw: dict | None) -> dict[str, Atajo]:
    raw = {} if raw is None else {k.lower(): v for k, v in raw.items()}
    resultado: dict[str, Atajo] = {}
    teclas_usadas: dict[str, str] = {}

    for accion, default in ATAJOS_DEFAULTS.items():
        valor_usuario = raw.get(accion)
        if valor_usuario is not None and valor_usuario.strip() == "":
            continue  # desactivado explícitamente

        normalizado = _normalizar_atajo(valor_usuario)
        if valor_usuario is not None and normalizado is None:
            logger.warning("atajos: valor inválido para %r: %r. Usando default %r.",
                           accion, valor_usuario, default)
            normalizado = _normalizar_atajo(default)
        elif normalizado is None:
            normalizado = _normalizar_atajo(default)
        if normalizado is None:
            continue

        # El conflicto se mide por la combinación COMPLETA: 'ctrl+d' y 'alt+d'
        # son atajos distintos y no chocan; dos 'alt+d' sí.
        if normalizado in teclas_usadas:
            logger.warning("atajos: conflicto — %r y %r usan %r. Desactivando %r.",
                           teclas_usadas[normalizado], accion, normalizado, accion)
            continue
        teclas_usadas[normalizado] = accion
        tecla = normalizado.split("+", 1)[-1]
        resultado[accion] = Atajo(accion=accion, texto=normalizado, tecla=tecla)
    return resultado


# ── Carga de config.ini ──────────────────────────────────────────────────────

_DEF = {
    "voz": "0", "velocidad": "175", "volumen": "1.0",
    "estrategia": "limite", "tamanio_maximo": "15", "umbral_solo_nombre": "0",
    "reconectar": "true", "espera_entre_intentos": "10", "max_intentos": "5",
    "formato_prefijo": "nombre_mensaje",
    "palabras_silenciadas": "", "usuarios_silenciados": "",
    "limpiar_emojis": "true", "eliminar_urls": "true", "max_longitud_mensaje": "200",
    "tamanio_fuente_chat": "12", "mostrar_total_superchats": "true",
    "guardar_historial": "no", "autoplay_reproductor": "true",
    "filtro_activo": "todos", "silenciar_lectura": "false", "silenciar_sonidos": "false",
    "mostrar_botones_reproductor": "false", "mostrar_metadatos": "true",
    "anunciar_entradas": "false",
}

_CONFIG_FALLBACK = """\
[voz]
voz = 0
velocidad = 175
volumen = 1.0
[cola]
estrategia = limite
tamanio_maximo = 15
umbral_solo_nombre = 0
[reconexion]
reconectar = true
espera_entre_intentos = 10
max_intentos = 5
[lectura]
formato_prefijo = nombre_mensaje
[filtros]
palabras_silenciadas =
usuarios_silenciados =
[texto]
limpiar_emojis = true
eliminar_urls = true
max_longitud_mensaje = 200
# Atajos por área: Ctrl = reproductor, Alt = conexión/chat, F = voz/lectura.
# Editables desde Preferencias > Atajos (salvo F9-F12, fijos).
[atajos]
rep_play = ctrl+p
rep_retro = ctrl+left
rep_avanz = ctrl+right
rep_detener = ctrl+d
rep_mute = ctrl+m
rep_vol_menos = ctrl+down
rep_vol_mas = ctrl+up
conectar = alt+c
desconectar = alt+d
enviar_chat = alt+enter
pausa = f5
detener_tts = f8
velocidad_menos = f9
velocidad_mas = f10
volumen_menos = f11
volumen_mas = f12
silenciar_lectura = f4
silenciar_sonidos = f7
anunciar_estado = f2
[ui]
tamanio_fuente_chat = 12
mostrar_total_superchats = true
autoplay_reproductor = true
filtro_activo = todos
silenciar_sonidos = false
mostrar_botones_reproductor = false
mostrar_metadatos = true
[sesion]
guardar_historial = no
silenciar_lectura = false
[tiktok]
# Leer por voz quien entra al directo (solo TikTok). En directos grandes puede
# ser muchisimo, por eso viene desactivado. Editable en Preferencias > Lectura.
anunciar_entradas = false
# Componentes que anuncia F2 (estado de sesion). Editable en
# Preferencias > Estado (F2). true = se dice; false = no.
[estado]
estado = true
titulo = true
canal = true
espectadores = true
mensajes_leidos = true
aportes = true
en_cola = false
voz = false
lectura_silenciada = true
"""

_SOUNDS_FALLBACK = """\
[sonidos]
activar = true
volumen = 0.7

# Tema de sonido: carpeta dentro de sounds/themes/ con un WAV por evento,
# nombrado igual que el evento (p. ej. mensaje_nuevo.wav). Para crear tu
# propio tema, copia sounds/themes/default a sounds/themes/mi_tema,
# reemplaza los .wav que quieras y pon aquí:  tema = mi_tema
tema = default

# Opcional (avanzado): puedes forzar un archivo concreto para un evento
# escribiendo su ruta aquí; tiene prioridad sobre el tema. Por ejemplo:
#   superchat = sounds/mis_efectos/caja.wav
"""

_EVENTOS_SONIDO = [
    "app_inicio", "conectando", "conectado", "desconectado",
    "mensaje_nuevo", "superchat", "nuevo_miembro", "error",
    "pausa", "reanudar", "copiar", "voz_cambiada",
    # v0.6 online y acciones que antes reutilizaban otros sonidos:
    "enviado", "comentario", "moderacion", "cola_vaciada",
]

# Carpeta base de temas y tema por defecto.
_TEMAS_DIR   = "themes"
_TEMA_DEFECTO = "default"


def _mk_parser() -> configparser.ConfigParser:
    return configparser.ConfigParser(inline_comment_prefixes=("#", ";"), default_section="__none__")

def _gs(p, sec, k):       return p.get(sec, k, fallback=_DEF.get(k, "")).strip()
def _gi(v, d):
    try:    return int(str(v).strip())
    except Exception: return d
def _gf(v, d):
    try:    return float(str(v).strip())
    except Exception: return d
def _pi(p, sec, k, lo=0, hi=None):
    v = max(lo, _gi(_gs(p, sec, k), int(_DEF.get(k, "0"))))
    return min(hi, v) if hi is not None else v
def _pf(p, sec, k, lo=0.0, hi=1.0):
    return max(lo, min(hi, _gf(_gs(p, sec, k), float(_DEF.get(k, "1.0")))))
def _pb(p, sec, k):
    try:    return p.getboolean(sec, k)
    except Exception: return _DEF.get(k, "true").strip().lower() in ("true", "yes", "1", "on")
def _lista(v: str) -> list:
    return [x.strip().lower() for x in v.split(",") if x.strip()]


def guardar_opcion(ruta: Path | None, seccion: str, clave: str, valor: str) -> None:
    """Actualiza una clave en el INI preservando comentarios y orden."""
    if ruta is None:
        return
    try:
        txt = ruta.read_text(encoding="utf-8")
    except Exception as exc:
        logger.debug("guardar_opcion: no se pudo leer %s: %s", ruta, exc)
        return

    lines = txt.splitlines(keepends=True)
    sec_lower = seccion.lower()
    clave_lower = clave.lower()
    nueva = f"{clave} = {valor}\n"
    in_sec = False
    insert_pos = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            if in_sec:
                if insert_pos is None:
                    insert_pos = i
                break
            in_sec = stripped.lower() == f"[{sec_lower}]"
        elif in_sec:
            k = stripped.split("=", 1)[0].strip().lower() if "=" in stripped else ""
            if k == clave_lower:
                lines[i] = nueva
                try:    ruta.write_text("".join(lines), encoding="utf-8")
                except Exception as exc:
                    logger.debug("guardar_opcion: no se pudo escribir: %s", exc)
                return
            insert_pos = i + 1

    if in_sec:
        if insert_pos is None:
            insert_pos = len(lines)
        lines.insert(insert_pos, nueva)
    elif insert_pos is None:
        lines.append(f"\n[{seccion}]\n{nueva}")

    try:    ruta.write_text("".join(lines), encoding="utf-8")
    except Exception as exc:
        logger.debug("guardar_opcion: no se pudo escribir: %s", exc)


def cargar_configuracion() -> dict:
    ruta = app_dir() / "config.ini"
    if not ruta.exists():
        logger.warning("config.ini no encontrado. Creando con valores por defecto.")
        try:    ruta.write_text(_CONFIG_FALLBACK, encoding="utf-8")
        except Exception as exc: logger.error("No se pudo crear config.ini: %s", exc)

    p = _mk_parser()
    try:
        if not p.read(ruta, encoding="utf-8"):
            logger.error("No se pudo leer config.ini."); sys.exit(1)
    except configparser.Error as exc:
        logger.error("Error de sintaxis en config.ini: %s", exc)
        logger.error("Borra config.ini y vuelve a abrir la aplicación para regenerarlo.")
        sys.exit(1)

    estrategia = _gs(p, "cola", "estrategia").lower()
    if estrategia not in ("todas", "limite"): estrategia = "limite"
    formato = _gs(p, "lectura", "formato_prefijo").lower()
    if formato not in ("nombre_mensaje", "solo_mensaje", "solo_nombre"): formato = "nombre_mensaje"
    guardar = _gs(p, "sesion", "guardar_historial").lower()
    if guardar not in ("no", "csv", "txt"): guardar = "no"

    atajos_raw = {}
    if p.has_section("atajos"):
        atajos_raw = {k.strip().lower(): (v or "").strip() for k, v in p.items("atajos")}

    # Inyectar en el INI los atajos nuevos ausentes (actualización desde versiones anteriores).
    atajos_nuevos = [k for k in ATAJOS_DEFAULTS if k not in atajos_raw]
    if atajos_nuevos:
        for accion in atajos_nuevos:
            guardar_opcion(ruta, "atajos", accion, ATAJOS_DEFAULTS[accion])
            atajos_raw[accion] = ATAJOS_DEFAULTS[accion]
        logger.info("Atajos nuevos añadidos a config.ini: %s", ", ".join(atajos_nuevos))

    # Inyectar claves nuevas de secciones existentes si faltan.
    if not p.has_option("ui", "filtro_activo"):
        guardar_opcion(ruta, "ui", "filtro_activo", "todos")
    if not p.has_option("ui", "silenciar_sonidos"):
        guardar_opcion(ruta, "ui", "silenciar_sonidos", "false")
    if not p.has_option("ui", "autoplay_reproductor"):
        guardar_opcion(ruta, "ui", "autoplay_reproductor", "true")
    if not p.has_option("ui", "mostrar_botones_reproductor"):
        guardar_opcion(ruta, "ui", "mostrar_botones_reproductor", "false")
    if not p.has_option("ui", "mostrar_metadatos"):
        guardar_opcion(ruta, "ui", "mostrar_metadatos", "true")
    if not p.has_option("sesion", "silenciar_lectura"):
        guardar_opcion(ruta, "sesion", "silenciar_lectura", "false")
    if not p.has_option("tiktok", "anunciar_entradas"):
        guardar_opcion(ruta, "tiktok", "anunciar_entradas", "false")

    # Estado (F2): un booleano por componente. Si falta la sección, se crea con
    # los valores por defecto (lo relevante activado; lo técnico apagado).
    from estado_sesion import COMPONENTES as _EST_COMP, ACTIVOS_DEFECTO as _EST_DEF
    if not p.has_section("estado"):
        for comp in _EST_COMP:
            guardar_opcion(ruta, "estado", comp, "true" if comp in _EST_DEF else "false")
    estado_toggles = set()
    for comp in _EST_COMP:
        try:    activo = p.getboolean("estado", comp)
        except Exception: activo = comp in _EST_DEF
        if activo:
            estado_toggles.add(comp)

    filtro_activo = _gs(p, "ui", "filtro_activo").lower()
    if filtro_activo not in ("todos", "texto", "superchat", "miembro"):
        filtro_activo = "todos"

    return {
        "voz": _gs(p, "voz", "voz"),
        "velocidad": _pi(p, "voz", "velocidad", lo=50, hi=500),
        "volumen": _pf(p, "voz", "volumen"),
        "estrategia": estrategia,
        "tamanio_maximo": _pi(p, "cola", "tamanio_maximo", lo=1),
        "umbral_solo_nombre": _pi(p, "cola", "umbral_solo_nombre"),
        "reconectar": _pb(p, "reconexion", "reconectar"),
        "espera_entre_intentos": _pi(p, "reconexion", "espera_entre_intentos", lo=1),
        "max_intentos": _pi(p, "reconexion", "max_intentos"),
        "formato_prefijo": formato,
        "palabras_silenciadas": _lista(_gs(p, "filtros", "palabras_silenciadas")),
        "usuarios_silenciados": _lista(_gs(p, "filtros", "usuarios_silenciados")),
        "limpiar_emojis": _pb(p, "texto", "limpiar_emojis"),
        "eliminar_urls": _pb(p, "texto", "eliminar_urls"),
        "max_longitud_mensaje": _pi(p, "texto", "max_longitud_mensaje"),
        "tamanio_fuente_chat": _pi(p, "ui", "tamanio_fuente_chat", lo=8, hi=24),
        "mostrar_total_superchats": _pb(p, "ui", "mostrar_total_superchats"),
        "autoplay_reproductor": _pb(p, "ui", "autoplay_reproductor"),
        "mostrar_botones_reproductor": _pb(p, "ui", "mostrar_botones_reproductor"),
        "mostrar_metadatos": _pb(p, "ui", "mostrar_metadatos"),
        "filtro_activo": filtro_activo,
        "silenciar_sonidos": _pb(p, "ui", "silenciar_sonidos"),
        "guardar_historial": guardar,
        "silenciar_lectura": _pb(p, "sesion", "silenciar_lectura"),
        "tiktok_anunciar_entradas": _pb(p, "tiktok", "anunciar_entradas"),
        "estado_toggles": estado_toggles,
        "atajos_raw": atajos_raw,
        "ruta_config": ruta,
    }


def cargar_sonidos() -> dict:
    """Devuelve dict para `sound_player.cargar()`."""
    base = app_dir()
    ruta = base / "sounds.ini"
    if not ruta.exists():
        logger.warning("sounds.ini no encontrado. Creando con valores por defecto.")
        try:    ruta.write_text(_SOUNDS_FALLBACK, encoding="utf-8")
        except Exception as exc: logger.error("No se pudo crear sounds.ini: %s", exc)

    p = _mk_parser()
    try:
        if not p.read(ruta, encoding="utf-8"):
            return {"activar": False, "volumen": 0.7, "eventos": {}}
    except configparser.Error as exc:
        logger.warning("Error en sounds.ini: %s. Sonidos desactivados.", exc)
        return {"activar": False, "volumen": 0.7, "eventos": {}}

    activar, volumen, tema = True, 0.7, _TEMA_DEFECTO
    if p.has_section("sonidos"):
        try:    activar = p.getboolean("sonidos", "activar", fallback=True)
        except Exception: pass
        try:    volumen = max(0.0, min(1.0, float(p.get("sonidos", "volumen", fallback="0.7"))))
        except Exception: pass
        try:    tema = (p.get("sonidos", "tema", fallback=_TEMA_DEFECTO).strip()
                        or _TEMA_DEFECTO)
        except Exception: pass

    carpeta_tema = base / "sounds" / _TEMAS_DIR / tema

    eventos: dict[str, Path | None] = {}
    for ev in _EVENTOS_SONIDO:
        # 1) Ruta explícita en sounds.ini (override avanzado, máxima prioridad).
        raw = p.get("sonidos", ev, fallback="").strip()
        if raw:
            ruta_ev = Path(raw)
            if not ruta_ev.is_absolute():
                ruta_ev = base / ruta_ev
            eventos[ev] = ruta_ev
            continue
        # 2) Si no, el archivo del tema: sounds/themes/<tema>/<evento>.wav
        eventos[ev] = carpeta_tema / f"{ev}.wav"

    return {"activar": activar, "volumen": volumen, "eventos": eventos}


# ── Helpers de temas de sonido (para el diálogo de Preferencias) ──────────────

def listar_temas_sonido() -> list[str]:
    """Nombres de carpeta dentro de sounds/themes/ (cada una es un tema)."""
    carpeta = app_dir() / "sounds" / _TEMAS_DIR
    try:
        temas = sorted(d.name for d in carpeta.iterdir() if d.is_dir())
    except Exception:
        temas = []
    if _TEMA_DEFECTO not in temas:
        temas.insert(0, _TEMA_DEFECTO)
    return temas


def tema_sonido_actual() -> str:
    """Lee el tema activo de sounds.ini (o el por defecto)."""
    ruta = app_dir() / "sounds.ini"
    p = _mk_parser()
    try:
        p.read(ruta, encoding="utf-8")
        return (p.get("sonidos", "tema", fallback=_TEMA_DEFECTO).strip()
                or _TEMA_DEFECTO)
    except Exception:
        return _TEMA_DEFECTO
