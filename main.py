"""Punto de entrada. Abre la interfaz gráfica directamente."""

from __future__ import annotations

import sys
import queue
import logging
import re
import threading
import warnings
import asyncio
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

# pytchat usa APIs de asyncio deprecadas.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="asyncio")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pytchat")
warnings.filterwarnings("ignore", message=".*get_event_loop.*")

from config import (
    APP_NAME, APP_VERSION, app_dir,
    TIPO_TEXTO, TIPO_SUPERCHAT, TIPO_STICKER, TIPO_MIEMBRO,
    configurar_logging, cargar_configuracion, cargar_sonidos,
)
configurar_logging()

logger = logging.getLogger(__name__)

from tts_worker import TTSWorker, sanitizar, construir_tts
import sound_player as _snd


# Traducción pytchat → tipos internos.
_TIPO_MAP = {
    "textMessage":  TIPO_TEXTO,
    "superChat":    TIPO_SUPERCHAT,
    "superSticker": TIPO_STICKER,
    "newSponsor":   TIPO_MIEMBRO,
}


# ── Instancia única ──────────────────────────────────────────────────────────
# Mutex de Windows para impedir que se abran dos ventanas a la vez. Se usa
# ctypes (en vez de win32event) para no añadir otra dependencia.

_mutex_handle = None


def _verificar_instancia_unica() -> bool:
    global _mutex_handle
    try:
        import ctypes
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, "YTChatTTS_SingleInstance_Mutex")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return False
    except Exception:
        pass  # fuera de Windows, dejamos que arranque igualmente
    return True


# ── Extracción de URL / ID de YouTube ────────────────────────────────────────

_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def extraer_video_id(entrada: str) -> str:
    entrada = entrada.strip()
    if _ID_RE.match(entrada):
        return entrada
    try:
        parsed = urlparse(entrada if "://" in entrada else "https://" + entrada)
        host = parsed.netloc.lower()
        if "youtube.com" in host:
            qs = parse_qs(parsed.query)
            if "v" in qs and _ID_RE.match(qs["v"][0]):
                return qs["v"][0]
            m = re.search(r"/(?:live|shorts|embed|v|e)/([A-Za-z0-9_-]{11})(?:[/?#]|$)", parsed.path)
            if m:
                return m.group(1)
        elif "youtu.be" in host:
            m = re.match(r"^/([A-Za-z0-9_-]{11})(?:[/?#]|$)", parsed.path)
            if m:
                return m.group(1)
    except Exception:
        pass
    m = re.search(r"[/=]([A-Za-z0-9_-]{11})(?:[?&/#]|$)", entrada)
    if m and _ID_RE.match(m.group(1)):
        return m.group(1)
    return entrada


def obtener_titulo(video_id: str, timeout: float = 8.0) -> str:
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/watch?v={video_id}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "es-ES,es;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read(65536).decode("utf-8", errors="ignore")
        m = re.search(r'"videoDetails"[^}]{0,200}"title"\s*:\s*"([^"]+)"', html)
        if m:
            return m.group(1).replace("\\u0026", "&").replace("\\n", " ").replace("\\/", "/").strip()
        m = re.search(r"<title>([^<]+)</title>", html)
        if m:
            t = m.group(1).replace(" - YouTube", "").strip()
            if t and t.lower() != "youtube":
                return t
    except Exception as exc:
        logger.debug("obtener_titulo: %s", exc)
    return ""


# ── Estadísticas ─────────────────────────────────────────────────────────────

class Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.recibidos = self.leidos = self.filtrados = 0
        self.descartados = self.reconexiones = self.filtrados_nuevo = 0
        self.superchats = 0
        self.inicio = datetime.now()

    def inc(self, campo, n=1):
        with self._lock:
            setattr(self, campo, getattr(self, campo) + n)


# ── Cola y filtros ───────────────────────────────────────────────────────────

def encolar(cola, item, config, stats):
    if config["estrategia"] == "todas":
        cola.put(item); return
    max_q = config["tamanio_maximo"]
    n = 0
    while cola.qsize() >= max_q:
        try:    cola.get_nowait(); n += 1
        except queue.Empty: break
    if n: stats.inc("descartados", n)
    try:    cola.put_nowait(item)
    except queue.Full: stats.inc("descartados")


def permitido(autor: str, mensaje: str, config: dict) -> bool:
    al = autor.lower().strip()
    if any(u in al for u in config["usuarios_silenciados"]): return False
    if al in config.get("silenciados_ocultar", set()): return False
    ml = mensaje.lower()
    if any(p in ml for p in config["palabras_silenciadas"]): return False
    return True


def debe_leer_tts(autor: str, config: dict) -> bool:
    if config.get("silenciar_lectura", False):
        return False
    return autor.lower().strip() not in config.get("silenciados_runtime", set())


# ── Captura de chat ──────────────────────────────────────────────────────────

_ERRORES_PERMANENTES = (
    "invalid video id", "private", "members only",
    "finished", "unavailable", "does not exist",
)


def _es_error_permanente(exc):
    return any(p in str(exc).lower() for p in _ERRORES_PERMANENTES)


def captura_con_reconexion(video_id, cola, config, parada, stats, on_message=None,
                           on_estado=None):
    """on_estado(tipo, texto) informa al GUI de cambios de estado."""
    intentos = 0
    while not parada.is_set():
        err = _captura(video_id, cola, config, parada, stats, on_message, on_estado)
        if parada.is_set():
            break
        if not config["reconectar"]:
            if on_estado: on_estado("error", "La conexión se cerró y la reconexión está desactivada.")
            parada.set(); break
        if err is not None and _es_error_permanente(err):
            msg = _mensaje_error_amigable(err)
            if on_estado: on_estado("error_permanente", msg)
            _snd.reproducir("error")
            parada.set(); break
        intentos += 1
        mi = config["max_intentos"]
        if mi > 0 and intentos >= mi:
            if on_estado: on_estado("error", f"Se agotaron los {mi} intentos de reconexión.")
            _snd.reproducir("error")
            parada.set(); break
        sfx = f" de {mi}" if mi else ""
        espera = config["espera_entre_intentos"]
        if on_estado: on_estado("reintentando", f"Reintentando en {espera} segundos (intento {intentos}{sfx})...")
        stats.inc("reconexiones")
        _snd.reproducir("conectando")
        parada.wait(timeout=espera)


def _captura(video_id, cola, config, parada, stats, on_message=None, on_estado=None):
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        import pytchat
    except ImportError:
        if on_estado: on_estado("error_permanente", "No se encontró la librería pytchat. Ejecuta instalar.bat.")
        _snd.reproducir("error")
        parada.set(); return None

    if on_estado: on_estado("conectando", "Conectando al directo...")
    _snd.reproducir("conectando")

    try:
        chat = pytchat.create(video_id=video_id, interruptable=False)
    except Exception as exc:
        msg = _mensaje_error_amigable(exc)
        if on_estado: on_estado("error_conexion", msg)
        _snd.reproducir("error")
        return exc

    if on_estado: on_estado("conectado", "Conectado. Esperando mensajes...")
    _snd.reproducir("conectado")
    logger.info("Conectado al directo.")

    inicio = datetime.now(timezone.utc)
    umbral = config.get("umbral_solo_nombre", 0)
    err_con, MAX_ERR = 0, 5
    ultimo_error = None

    try:
        while chat.is_alive() and not parada.is_set():
            try:
                for c in chat.get().sync_items():
                    if parada.is_set(): break
                    if not _nuevo(c, inicio):
                        stats.inc("filtrados_nuevo"); continue

                    autor    = _str(getattr(c, "author", None) and c.author.name, "Usuario")
                    mensaje  = _str(getattr(c, "message", None), "")
                    tipo_raw = _str(getattr(c, "type", None), "textMessage")
                    tipo     = _TIPO_MAP.get(tipo_raw, None)
                    if tipo is None: continue
                    stats.inc("recibidos")

                    monto = ""
                    if tipo in (TIPO_SUPERCHAT, TIPO_STICKER):
                        monto = _str(getattr(c, "amountString", None), "")
                        stats.inc("superchats")

                    if not permitido(autor, mensaje, config):
                        stats.inc("filtrados"); continue

                    ml = sanitizar(mensaje, config["limpiar_emojis"],
                                   config["eliminar_urls"], config["max_longitud_mensaje"])

                    if tipo == TIPO_TEXTO and not ml.strip():
                        stats.inc("filtrados"); continue

                    if tipo == TIPO_SUPERCHAT and monto:
                        tts_text = f"Super Chat de {autor}: {monto}. {ml}" if ml else f"Super Chat de {autor}: {monto}"
                    elif tipo == TIPO_MIEMBRO:
                        tts_text = f"Nuevo miembro: {autor}"
                    elif umbral > 0 and cola.qsize() >= umbral:
                        tts_text = sanitizar(autor, config["limpiar_emojis"], False, 50) or "Usuario"
                    else:
                        tts_text = construir_tts(autor, ml or mensaje, config)

                    hora = datetime.now().strftime('%H:%M:%S')
                    if on_message:
                        on_message(autor, mensaje, hora, tipo, monto)

                    if debe_leer_tts(autor, config):
                        encolar(cola, {"texto_tts": tts_text}, config, stats)
                        stats.inc("leidos")

                err_con = 0
            except Exception as exc:
                if parada.is_set(): break
                err_con += 1
                ultimo_error = exc
                logger.warning("Error ciclo chat (%d/%d): %s", err_con, MAX_ERR, exc)
                if err_con >= MAX_ERR:
                    if on_estado: on_estado("error", "Demasiados errores consecutivos.")
                    break
            if not parada.is_set():
                time.sleep(0.1)
    except Exception as exc:
        if not parada.is_set():
            ultimo_error = exc
            logger.error("Error en captura: %s", exc)
    finally:
        if not parada.is_set():
            try:    chat.raise_for_status()
            except Exception as exc:
                ultimo_error = exc
            if on_estado: on_estado("desconectado", "El directo ha terminado o se perdió la conexión.")
            _snd.reproducir("desconectado")
    return ultimo_error


def _nuevo(c, inicio):
    try:
        ts = c.timestamp
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1_000, tz=timezone.utc) >= inicio
        if isinstance(ts, datetime):
            if ts.tzinfo is None: ts = ts.astimezone(timezone.utc)
            return ts >= inicio
    except Exception: pass
    return True


def _str(v, d):
    if v is None: return d
    r = str(v).strip()
    return r if r else d


def _mensaje_error_amigable(exc) -> str:
    t = str(exc).lower()
    if "invalid video id" in t:
        return "El ID de vídeo no es válido. Revisa la URL."
    if "private" in t:
        return "Este directo es privado. No se puede acceder."
    if "members only" in t:
        return "El chat está restringido a miembros del canal."
    if "finished" in t or "unavailable" in t:
        return "El directo ha terminado o no está disponible."
    if "does not exist" in t:
        return "El vídeo no existe. Revisa la URL."
    return f"No se pudo conectar: {exc}"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not _verificar_instancia_unica():
        # Ya hay una instancia abierta. Intentamos informar al usuario.
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"{APP_NAME} ya se está ejecutando.\nCierra la otra ventana antes de abrir una nueva.",
                APP_NAME,
                0x40  # MB_ICONINFORMATION
            )
        except Exception:
            pass
        sys.exit(0)

    config = cargar_configuracion()

    config.setdefault("silenciados_runtime", set())
    config.setdefault("silenciados_ocultar", set())

    sonidos_config = cargar_sonidos()
    try:    _snd.cargar(sonidos_config)
    except Exception as exc:
        logger.warning("No se pudo cargar sonidos: %s", exc)
    if config.get("silenciar_sonidos", False):
        _snd.silenciar_todo(True)

    cola   = queue.Queue()
    stats  = Stats()
    worker = TTSWorker(cola=cola, config=config)
    worker.start()
    if not worker.esperar_inicio(timeout=10.0):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "No se pudo iniciar el motor de voz (SAPI5).\n\n"
                "Comprueba que tienes al menos una voz instalada en\n"
                "Configuración → Hora e idioma → Voz.",
                APP_NAME,
                0x10  # MB_ICONERROR
            )
        except Exception:
            pass
        _snd.reproducir("error")
        sys.exit(1)

    parada = threading.Event()

    try:
        import wx
        from gui import iniciar_gui
    except ImportError as exc:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"wxPython no está instalado.\nEjecuta instalar.bat.\n\n{exc}",
                APP_NAME,
                0x10
            )
        except Exception:
            pass
        sys.exit(1)

    _estado = {"parada_sesion": None}

    def _cb_conectar(url_raw):
        import gui as _gm
        vid = extraer_video_id(url_raw)
        ps  = threading.Event()
        _estado["parada_sesion"] = ps

        def _on_msg(autor, mensaje, hora, tipo=TIPO_TEXTO, monto=""):
            if _gm._gui_frame and _gm._gui_frame._alive:
                wx.CallAfter(_gm._gui_frame.agregar_mensaje_chat,
                             autor, mensaje, hora, tipo, monto)

        def _on_estado(tipo_estado, texto):
            if not _gm._gui_frame or not _gm._gui_frame._alive:
                return
            if tipo_estado == "conectado":
                wx.CallAfter(_gm._gui_frame.set_conectado, True)
            elif tipo_estado in ("error_permanente", "error", "desconectado"):
                wx.CallAfter(_gm._gui_frame.set_conectado, False)
                wx.CallAfter(_gm._gui_frame.set_titulo_stream, "")
            # Todos los estados se anuncian al lector de pantalla.
            from gui import anunciar
            wx.CallAfter(anunciar, texto)

        def _run():
            titulo = obtener_titulo(vid)
            if _gm._gui_frame and titulo:
                wx.CallAfter(_gm._gui_frame.set_titulo_stream, titulo)
            captura_con_reconexion(vid, cola, config, ps, stats,
                                   on_message=_on_msg, on_estado=_on_estado)
            if _gm._gui_frame and not parada.is_set():
                wx.CallAfter(_gm._gui_frame.set_conectado, False)
                wx.CallAfter(_gm._gui_frame.set_titulo_stream, "")

        threading.Thread(target=_run, daemon=True, name="Chat").start()

    def _cb_desconectar():
        ps = _estado.get("parada_sesion")
        if ps and not ps.is_set():
            ps.set()

    iniciar_gui(
        config=config, cola=cola, stats=stats, worker=worker, parada=parada,
        iniciar_captura_cb=_cb_conectar,
        detener_captura_cb=_cb_desconectar,
    )

    _snd.cerrar()
    sys.exit(0)


if __name__ == "__main__":
    main()
