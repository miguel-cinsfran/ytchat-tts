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
APP_VERSION = "0.5"

# ── Tipos de mensaje ──────────────────────────────────────────────────────────

TIPO_TEXTO     = "text"
TIPO_SUPERCHAT = "superchat"
TIPO_STICKER   = "sticker"
TIPO_MIEMBRO   = "member"

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
# Solo Alt+X: NVDA usa Insert, Ctrl se reserva a los estándar, Shift+Alt
# colisiona con atajos de idioma de Windows.

ATAJOS_DEFAULTS = {
    "url": "alt+u", "conectar": "alt+c", "pausa": "alt+p",
    "chat": "alt+l", "voz": "alt+v", "filtro": "alt+f",
    "salir": "alt+s", "velocidad_mas": "alt+.",
    "velocidad_menos": "alt+,", "detener_tts": "alt+d",
    "silenciar_sonidos": "alt+m", "vaciar_cola": "alt+x",
    "volumen_mas": "alt+n", "volumen_menos": "alt+-",
    "silenciar_lectura": "alt+t", "aplicar_voz": "alt+a",
    "copiar_mensaje": "alt+k", "copiar_todo": "alt+o",
    "releer": "alt+r", "abrir_enlace": "alt+e",
}

_SIMBOLOS_PERMITIDOS = {",", ".", ";", "'", "[", "]", "/", "-"}
_RE_ATAJO = re.compile(r"^alt\+(.)$", re.IGNORECASE)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Atajo:
    accion: str
    texto:  str
    tecla:  str


def _normalizar_atajo(valor: str | None) -> str | None:
    if valor is None:
        return None
    valor = valor.strip().lower().replace(" ", "")
    if not valor:
        return None
    m = _RE_ATAJO.match(valor)
    if not m:
        return None
    ch = m.group(1)
    if len(ch) == 1 and ch.isascii() and (ch.isalnum() or ch in _SIMBOLOS_PERMITIDOS):
        return f"alt+{ch}"
    return None


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

        tecla = normalizado.split("+", 1)[1]
        if tecla in teclas_usadas:
            logger.warning("atajos: conflicto — %r y %r usan %r. Desactivando %r.",
                           teclas_usadas[tecla], accion, normalizado, accion)
            continue
        teclas_usadas[tecla] = accion
        resultado[accion] = Atajo(accion=accion, texto=normalizado, tecla=tecla)
    return resultado


def atajos_a_tuplas_wx(atajos: dict[str, Atajo], ids_por_accion: dict[str, int]):
    """Adapta el dict a la forma que espera wx.AcceleratorTable."""
    import wx
    tuplas = []
    for accion, atajo in atajos.items():
        wid = ids_por_accion.get(accion)
        if wid is None:
            continue
        ch = atajo.tecla
        keycode = ord(ch.upper()) if ch.isalnum() else ord(ch)
        tuplas.append((wx.ACCEL_ALT, keycode, wid))
    return tuplas


# ── Carga de config.ini ──────────────────────────────────────────────────────

_DEF = {
    "voz": "0", "velocidad": "175", "volumen": "1.0",
    "estrategia": "limite", "tamanio_maximo": "15", "umbral_solo_nombre": "0",
    "reconectar": "true", "espera_entre_intentos": "10", "max_intentos": "5",
    "formato_prefijo": "nombre_mensaje",
    "palabras_silenciadas": "", "usuarios_silenciados": "",
    "limpiar_emojis": "true", "eliminar_urls": "true", "max_longitud_mensaje": "200",
    "tamanio_fuente_chat": "12", "mostrar_total_superchats": "true",
    "guardar_historial": "no",
    "filtro_activo": "todos", "silenciar_lectura": "false", "silenciar_sonidos": "false",
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
[atajos]
url = alt+u
conectar = alt+c
pausa = alt+p
chat = alt+l
voz = alt+v
filtro = alt+f
salir = alt+s
velocidad_mas = alt+.
velocidad_menos = alt+,
detener_tts = alt+d
silenciar_sonidos = alt+m
vaciar_cola = alt+x
volumen_mas = alt+n
volumen_menos = alt+-
silenciar_lectura = alt+t
aplicar_voz = alt+a
copiar_mensaje = alt+k
copiar_todo = alt+o
releer = alt+r
abrir_enlace = alt+e
[ui]
tamanio_fuente_chat = 12
mostrar_total_superchats = true
filtro_activo = todos
silenciar_sonidos = false
[sesion]
guardar_historial = no
silenciar_lectura = false
"""

_SOUNDS_FALLBACK = """\
[sonidos]
activar = true
volumen = 0.7
app_inicio = sounds/app_inicio.wav
conectando = sounds/conectando.wav
conectado = sounds/conectado.wav
desconectado = sounds/desconectado.wav
mensaje_nuevo = sounds/mensaje.wav
superchat = sounds/superchat.wav
nuevo_miembro = sounds/miembro.wav
error = sounds/error.wav
pausa = sounds/pausa.wav
reanudar = sounds/reanudar.wav
copiar = sounds/copiar.wav
voz_cambiada = sounds/voz_cambiada.wav
"""

_EVENTOS_SONIDO = [
    "app_inicio", "conectando", "conectado", "desconectado",
    "mensaje_nuevo", "superchat", "nuevo_miembro", "error",
    "pausa", "reanudar", "copiar", "voz_cambiada",
]


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
    if not p.has_option("sesion", "silenciar_lectura"):
        guardar_opcion(ruta, "sesion", "silenciar_lectura", "false")

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
        "filtro_activo": filtro_activo,
        "silenciar_sonidos": _pb(p, "ui", "silenciar_sonidos"),
        "guardar_historial": guardar,
        "silenciar_lectura": _pb(p, "sesion", "silenciar_lectura"),
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

    activar, volumen = True, 0.7
    if p.has_section("sonidos"):
        try:    activar = p.getboolean("sonidos", "activar", fallback=True)
        except Exception: pass
        try:    volumen = max(0.0, min(1.0, float(p.get("sonidos", "volumen", fallback="0.7"))))
        except Exception: pass

    eventos: dict[str, Path | None] = {}
    for ev in _EVENTOS_SONIDO:
        raw = p.get("sonidos", ev, fallback="").strip()
        if not raw:
            eventos[ev] = None
            continue
        ruta_ev = Path(raw)
        if not ruta_ev.is_absolute():
            ruta_ev = base / ruta_ev
        eventos[ev] = ruta_ev

    return {"activar": activar, "volumen": volumen, "eventos": eventos}
