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
    TIPO_TEXTO, TIPO_SUPERCHAT, TIPO_STICKER, TIPO_MIEMBRO, TIPO_ENTRADA,
    configurar_logging, cargar_configuracion, cargar_sonidos,
)

logger = logging.getLogger(__name__)

from tts_worker import TTSWorker, sanitizar, construir_tts
import sound_player as _snd
import deteccion
import tiktok_captura


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
        # use_last_error + get_last_error: leer GetLastError «a mano» tras una
        # llamada ctypes no es fiable (el propio ctypes puede pisarlo entre medias).
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _mutex_handle = kernel32.CreateMutexW(None, False, "YTChatTTS_SingleInstance_Mutex")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
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


def _descargar_watch(video_id: str, timeout: float = 8.0) -> str:
    """Descarga (parcial) el HTML del watch. Cadena vacía si falla."""
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/watch?v={video_id}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "es-ES,es;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            # Más bytes que antes: las banderas de directo aparecen algo después
            # del título dentro de videoDetails.
            return r.read(200_000).decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.debug("_descargar_watch: %s", exc)
        return ""


def _parsear_titulo(html: str) -> str:
    if not html:
        return ""
    m = re.search(r'"videoDetails"[^}]{0,200}"title"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1).replace("\\u0026", "&").replace("\\n", " ").replace("\\/", "/").strip()
    m = re.search(r"<title>([^<]+)</title>", html)
    if m:
        t = m.group(1).replace(" - YouTube", "").strip()
        if t and t.lower() != "youtube":
            return t
    return ""


def obtener_titulo(video_id: str, timeout: float = 8.0) -> str:
    return _parsear_titulo(_descargar_watch(video_id, timeout))


def _clasificar_por_api(video_id: str) -> str:
    """Reserva: si hay API key, clasifica con la Data API. Si no, desconocido."""
    try:
        import credenciales
        import youtube_api
        if not (youtube_api.google_disponible() and credenciales.hay_lectura()):
            return deteccion.DESCONOCIDO
        cli = youtube_api.ClienteYouTube(credenciales.cargar())
        resp = cli._lectura().videos().list(
            part="snippet", id=video_id).execute()
        items = resp.get("items", []) or []
        if not items:
            return deteccion.DESCONOCIDO
        lbc = items[0].get("snippet", {}).get("liveBroadcastContent")
        return deteccion.clasificar_desde_api(lbc)
    except Exception as exc:
        logger.debug("_clasificar_por_api: %s", exc)
        return deteccion.DESCONOCIDO


def _tipo_desde_ytdlp(info: dict) -> str:
    ls = (info.get("live_status") or "").strip()
    if ls == "is_live":
        return deteccion.LIVE
    if ls == "is_upcoming":
        return deteccion.UPCOMING
    if ls in ("was_live", "not_live", "post_live"):
        return deteccion.VOD
    if info.get("is_live"):
        return deteccion.LIVE
    return deteccion.DESCONOCIDO


def _metadatos_desde_ytdlp(info: dict) -> dict:
    """Saca del dict de yt-dlp los metadatos que muestra el panel de información.
    La extracción `process=False` ya los trae (canal, vistas, descripción…), así
    que no cuesta ninguna petición extra. Campos ausentes quedan en None/"" y el
    panel los omite."""
    return {
        "titulo":      (info.get("title") or "").strip(),
        "canal":       (info.get("uploader") or info.get("channel") or "").strip(),
        "vistas":      info.get("view_count"),
        "me_gusta":    info.get("like_count"),
        "comentarios": info.get("comment_count"),
        "fecha":       (info.get("upload_date") or "").strip(),   # YYYYMMDD
        "duracion":    info.get("duration"),                      # segundos
        "en_vivo":     bool(info.get("is_live")),
        "descripcion": (info.get("description") or "").strip(),
    }


def obtener_info_video(video_id: str) -> tuple[str, str, dict]:
    """Devuelve (titulo, tipo, metadatos). tipo: live/upcoming/vod/desconocido.

    Se usa yt-dlp (process=False, ~1 s): es robusto ante la página de
    consentimiento que YouTube sirve al scraping directo, y ya trae `title`,
    `live_status` y la metadata del panel de información (canal, vistas,
    descripción…). Si no está yt-dlp, se cae al scraping (que puede no funcionar
    y deja la metadata vacía, con solo el título si se pudo sacar)."""
    try:
        import yt_dlp
        # socket_timeout: que una red lenta no cuelgue indefinidamente la
        # detección live/VOD al conectar (sin él yt-dlp puede esperar mucho).
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "noplaylist": True, "socket_timeout": 20}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}",
                                    download=False, process=False)
        titulo = (info.get("title") or "").strip()
        tipo = _tipo_desde_ytdlp(info)
        if titulo or tipo != deteccion.DESCONOCIDO:
            return titulo, tipo, _metadatos_desde_ytdlp(info)
    except Exception as exc:
        logger.debug("obtener_info_video (yt-dlp): %s", exc)

    html = _descargar_watch(video_id)
    titulo = _parsear_titulo(html)
    tipo = deteccion.clasificar_desde_html(html)
    if tipo == deteccion.DESCONOCIDO:
        tipo = _clasificar_por_api(video_id)
    return titulo, tipo, {"titulo": titulo}


def _resolver_live_chat_id(video_id: str) -> None:
    """Si hay API key, resuelve el id del chat en vivo y se lo pasa al GUI.

    Es totalmente opcional: cualquier fallo se ignora y la captura del chat
    (que va por pytchat, sin API) sigue funcionando igual.
    """
    try:
        import credenciales
        import youtube_api
        if not (youtube_api.google_disponible() and credenciales.hay_lectura()):
            return
        cli = youtube_api.ClienteYouTube(credenciales.cargar())
        lcid = cli.resolver_live_chat_id(video_id)
        if not lcid:
            return
        import wx
        import gui as _gm
        if _gm._gui_frame and _gm._gui_frame._alive:
            wx.CallAfter(_gm._gui_frame.set_live_chat_id, lcid)
    except Exception as exc:
        logger.debug("resolver_live_chat_id: %s", exc)


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

    def reset(self):
        """Vuelve los contadores a cero: al desconectar empezamos de limpio,
        como si la app se acabara de abrir."""
        with self._lock:
            self.recibidos = self.leidos = self.filtrados = 0
            self.descartados = self.reconexiones = self.filtrados_nuevo = 0
            self.superchats = 0
            self.inicio = datetime.now()


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


def procesar_entrante(autor, mensaje, tipo, monto, canal_id, cola, config, stats,
                      on_message=None, sesion_activa=None,
                      etiqueta_monto="Super Chat"):
    """Pipeline común de cada mensaje entrante (YouTube y TikTok): contadores,
    filtros, texto TTS, aviso a la GUI y encolado de lectura.

    etiqueta_monto: cómo llamar al mensaje con importe al leerlo («Super Chat»
    en YouTube, «Regalo» en TikTok). sesion_activa() evita que un hilo rezagado
    cuele lecturas de una sesión anterior; el descarte de GUI lo hace on_message.
    """
    stats.inc("recibidos")
    if tipo in (TIPO_SUPERCHAT, TIPO_STICKER):
        stats.inc("superchats")

    if not permitido(autor, mensaje, config):
        stats.inc("filtrados"); return

    ml = sanitizar(mensaje, config["limpiar_emojis"],
                   config["eliminar_urls"], config["max_longitud_mensaje"])
    if tipo == TIPO_TEXTO and not ml.strip():
        stats.inc("filtrados"); return

    umbral = config.get("umbral_solo_nombre", 0)
    if tipo == TIPO_SUPERCHAT and monto:
        tts_text = (f"{etiqueta_monto} de {autor}: {monto}. {ml}" if ml
                    else f"{etiqueta_monto} de {autor}: {monto}")
    elif tipo == TIPO_MIEMBRO:
        tts_text = f"Nuevo miembro: {autor}"
    elif tipo == TIPO_ENTRADA:
        tts_text = f"{autor} entró"
    elif umbral > 0 and cola.qsize() >= umbral:
        tts_text = sanitizar(autor, config["limpiar_emojis"], False, 50) or "Usuario"
    else:
        tts_text = construir_tts(autor, ml or mensaje, config)

    hora = datetime.now().strftime('%H:%M:%S')
    if on_message:
        on_message(autor, mensaje, hora, tipo, monto, canal_id)

    if debe_leer_tts(autor, config) and (sesion_activa is None or sesion_activa()):
        item = {"texto_tts": tts_text}
        # Multi-voz: los eventos (Super Chats, regalos, miembros, entradas) se
        # leen con otra voz si está activado; los mensajes normales, con la base.
        if config.get("multivoz") and tipo in (TIPO_SUPERCHAT, TIPO_STICKER,
                                               TIPO_MIEMBRO, TIPO_ENTRADA):
            try:    item["voz"] = int(config.get("voz_eventos", 0))
            except (TypeError, ValueError): pass
        encolar(cola, item, config, stats)
        stats.inc("leidos")


# ── Captura de chat ──────────────────────────────────────────────────────────

_ERRORES_PERMANENTES = (
    "invalid video id", "private", "members only",
    "finished", "unavailable", "does not exist",
)


def _es_error_permanente(exc):
    return any(p in str(exc).lower() for p in _ERRORES_PERMANENTES)


def captura_con_reconexion(video_id, cola, config, parada, stats, on_message=None,
                           on_estado=None, sesion_activa=None):
    """on_estado(tipo, texto) informa al GUI de cambios de estado.
    sesion_activa() (opcional) dice si esta sesión sigue siendo la vigente: un
    hilo viejo que despierta tarde no debe encolar TTS de la sesión anterior."""
    intentos = 0
    while not parada.is_set():
        err = _captura(video_id, cola, config, parada, stats, on_message, on_estado,
                       sesion_activa)
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


def _captura(video_id, cola, config, parada, stats, on_message=None, on_estado=None,
             sesion_activa=None):
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
    err_con, MAX_ERR = 0, 5
    ultimo_error = None

    try:
        while chat.is_alive() and not parada.is_set():
            try:
                for c in chat.get().sync_items():
                    if parada.is_set(): break
                    if not _nuevo(c, inicio):
                        stats.inc("filtrados_nuevo"); continue

                    autor_obj = getattr(c, "author", None)
                    autor    = _str(autor_obj and autor_obj.name, "Usuario")
                    canal_id = _str(autor_obj and getattr(autor_obj, "channelId", None), "")
                    mensaje  = _str(getattr(c, "message", None), "")
                    tipo_raw = _str(getattr(c, "type", None), "textMessage")
                    tipo     = _TIPO_MAP.get(tipo_raw, None)
                    if tipo is None: continue

                    monto = ""
                    if tipo in (TIPO_SUPERCHAT, TIPO_STICKER):
                        monto = _str(getattr(c, "amountString", None), "")

                    procesar_entrante(autor, mensaje, tipo, monto, canal_id,
                                      cola, config, stats,
                                      on_message=on_message,
                                      sesion_activa=sesion_activa)

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
            # El sonido de desconexión lo emite la GUI (set_conectado(False)),
            # para que suene también al desconectar a mano y sin duplicarse.
            if on_estado: on_estado("desconectado", "El directo ha terminado o se perdió la conexión.")
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
    # Aquí y no al importar el módulo: así los tests y el smoke test pueden
    # importar main sin crear el handler de ytchat.log (contaminaba el log real).
    configurar_logging()

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

    # gen: identifica la sesión de conexión activa. Cada conexión nueva lo
    # incrementa; un hilo de captura anterior que aún siga vivo (bloqueado en una
    # lectura de red) tendrá un gen distinto y sus mensajes/estados se descartan,
    # para que no se solapen con el directo nuevo.
    _estado = {"parada_sesion": None, "gen": 0}

    def _cb_conectar(url_raw):
        import gui as _gm
        # ¿Es una URL de TikTok? Va por su propia rama de captura (fase 1:
        # chat + reproductor, sin comentarios ni moderación).
        usuario_tt = tiktok_captura.usuario_de_url(url_raw)
        if usuario_tt:
            _conectar_tiktok(usuario_tt)
            return
        vid = extraer_video_id(url_raw)
        # Validar el formato ANTES de tocar la red: si no es un ID de 11
        # caracteres, es basura. Se rechaza al instante (sin esperas ni freeze).
        if not _ID_RE.match(vid):
            if _gm._gui_frame:
                wx.CallAfter(_gm._gui_frame.url_invalida)
            return
        ps  = threading.Event()
        _estado["parada_sesion"] = ps
        _estado["gen"] += 1
        gen = _estado["gen"]

        def _on_msg(autor, mensaje, hora, tipo=TIPO_TEXTO, monto="", canal_id=""):
            if gen != _estado["gen"]:
                return  # mensaje de una sesión anterior: descartar
            if _gm._gui_frame and _gm._gui_frame._alive:
                wx.CallAfter(_gm._gui_frame.agregar_mensaje_chat,
                             autor, mensaje, hora, tipo, monto, canal_id)

        def _on_estado(tipo_estado, texto):
            if gen != _estado["gen"]:
                return  # estado de una sesión anterior: descartar
            if not _gm._gui_frame or not _gm._gui_frame._alive:
                return
            if tipo_estado == "conectado":
                # set_conectado ya anuncia un mensaje claro según el tipo; no
                # repetimos el texto genérico aquí.
                wx.CallAfter(_gm._gui_frame.set_conectado, True)
                return
            if tipo_estado in ("error_permanente", "error", "desconectado"):
                wx.CallAfter(_gm._gui_frame.set_conectado, False)
                wx.CallAfter(_gm._gui_frame.set_titulo_stream, "")
            # El resto de estados (conectando, reintentando, errores) se anuncian.
            from gui import anunciar
            wx.CallAfter(anunciar, texto)

        def _run():
            # Una sola descarga del watch para sacar título, tipo y metadatos.
            titulo, tipo, metadatos = obtener_info_video(vid)
            # Si mientras buscábamos info se desconectó o se conectó a otro vídeo,
            # esta sesión ya no vale: no tocar la GUI (si no, pisaríamos la nueva).
            if gen != _estado["gen"]:
                return
            frame = _gm._gui_frame
            if frame:
                if titulo:
                    wx.CallAfter(frame.set_titulo_stream, titulo)
                wx.CallAfter(frame.set_tipo_video, tipo, vid)
                wx.CallAfter(frame.set_metadatos, metadatos)
                # Registrar en el historial (canal desde los metadatos de yt-dlp).
                wx.CallAfter(frame.registrar_historial, "youtube", vid,
                             f"https://www.youtube.com/watch?v={vid}",
                             titulo, (metadatos or {}).get("canal", ""))

            if deteccion.tiene_chat_en_vivo(tipo):
                # Directo (o tipo no determinado): capturamos el chat con pytchat.
                # Resolver el id del chat en vivo en paralelo (red opcional).
                threading.Thread(target=_resolver_live_chat_id, args=(vid,),
                                 daemon=True, name="LiveChatId").start()
                captura_con_reconexion(vid, cola, config, ps, stats,
                                       on_message=_on_msg, on_estado=_on_estado,
                                       sesion_activa=lambda: gen == _estado["gen"])
                # Solo refrescar la UI a «desconectado» si seguimos siendo la
                # sesión activa: un hilo viejo que termina tarde no debe apagar el
                # directo nuevo.
                if gen == _estado["gen"] and frame and not parada.is_set():
                    wx.CallAfter(frame.set_conectado, False)
                    wx.CallAfter(frame.set_titulo_stream, "")
            else:
                # Vídeo subido o directo programado: no hay chat en vivo. No se
                # arranca pytchat; quedan disponibles comentarios y reproductor.
                # El sonido también va tras el guard: una sesión ya descartada
                # no debe sonar como si conectara.
                if gen == _estado["gen"] and frame:
                    wx.CallAfter(frame.set_conectado, True)
                    _snd.reproducir("conectado")

        threading.Thread(target=_run, daemon=True, name="Chat").start()

    def _conectar_tiktok(usuario):
        """Rama TikTok: mismo esquema de sesión (ps + gen) que YouTube, con la
        captura de tiktok_captura y el pipeline común procesar_entrante."""
        import gui as _gm
        ps = threading.Event()
        _estado["parada_sesion"] = ps
        _estado["gen"] += 1
        gen = _estado["gen"]

        def _on_msg(autor, mensaje, hora, tipo=TIPO_TEXTO, monto="", canal_id=""):
            if gen != _estado["gen"]:
                return
            if _gm._gui_frame and _gm._gui_frame._alive:
                wx.CallAfter(_gm._gui_frame.agregar_mensaje_chat,
                             autor, mensaje, hora, tipo, monto, canal_id)

        def _on_evento(autor, mensaje, tipo, monto, canal_id):
            if gen != _estado["gen"]:
                return
            procesar_entrante(autor, mensaje, tipo, monto, canal_id,
                              cola, config, stats, on_message=_on_msg,
                              sesion_activa=lambda: gen == _estado["gen"],
                              etiqueta_monto="Regalo")

        def _on_estado(tipo_estado, texto):
            if gen != _estado["gen"]:
                return
            frame = _gm._gui_frame
            if not frame or not frame._alive:
                return
            # Los sonidos van aquí (no en tiktok_captura, que queda sin wx ni
            # audio): mismo mapa de eventos que la captura de YouTube.
            if tipo_estado in ("conectando", "reintentando"):
                _snd.reproducir("conectando")
                if tipo_estado == "reintentando":
                    stats.inc("reconexiones")
            elif tipo_estado == "conectado":
                _snd.reproducir("conectado")
                wx.CallAfter(frame.set_conectado, True)
                return  # set_conectado ya anuncia el mensaje adecuado
            elif tipo_estado in ("error_permanente", "error"):
                _snd.reproducir("error")
                wx.CallAfter(frame.set_conectado, False)
                wx.CallAfter(frame.set_titulo_stream, "")
            elif tipo_estado == "desconectado":
                wx.CallAfter(frame.set_conectado, False)
                wx.CallAfter(frame.set_titulo_stream, "")
            from gui import anunciar
            wx.CallAfter(anunciar, texto)

        def _on_info(meta):
            # Llega al conectar, con título, espectadores y la URL HLS del
            # directo (clave interna que consume el reproductor, no el panel).
            if gen != _estado["gen"]:
                return
            frame = _gm._gui_frame
            if not frame or not frame._alive:
                return
            url_flujo = meta.pop("_url_flujo", "")
            titulo = (meta.get("titulo") or "").strip() or f"TikTok de @{usuario}"
            wx.CallAfter(frame.set_titulo_stream, titulo)
            wx.CallAfter(frame.configurar_tiktok, usuario, url_flujo)
            wx.CallAfter(frame.set_metadatos, meta)
            # Registrar en el historial (TikTok reconecta por @usuario/live).
            wx.CallAfter(frame.registrar_historial, "tiktok", usuario,
                         f"https://www.tiktok.com/@{usuario}/live",
                         titulo, (meta.get("canal") or ""))

        def _on_espectadores(n):
            if gen != _estado["gen"]:
                return
            if _gm._gui_frame and _gm._gui_frame._alive:
                wx.CallAfter(_gm._gui_frame.set_espectadores, n)

        def _run():
            tiktok_captura.capturar_con_reconexion(
                usuario, config, ps,
                on_evento=_on_evento, on_estado=_on_estado, on_info=_on_info,
                on_espectadores=_on_espectadores)
            # Igual que en YouTube: solo apagar la UI si seguimos siendo la
            # sesión activa (un hilo viejo no debe pisar el directo nuevo).
            if gen == _estado["gen"] and _gm._gui_frame and not parada.is_set():
                wx.CallAfter(_gm._gui_frame.set_conectado, False)
                wx.CallAfter(_gm._gui_frame.set_titulo_stream, "")

        threading.Thread(target=_run, daemon=True, name="TikTok").start()

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
