"""Captura del chat de TikTok LIVE (fase 1: solo lectura, sin login).

Usa la librería no oficial TikTokLive (el «pytchat de TikTok»): se conecta a
cualquier directo público con el @usuario del streamer y entrega comentarios,
regalos y suscripciones en tiempo real. La firma de la conexión pasa por el
servidor de Euler Stream (tier gratuito, de sobra para uso personal). No hay
API oficial de TikTok para esto; los riesgos y la decisión de no implementar
escritura/moderación están en INFORME_TIKTOK.md.

Diseño espejo de la captura de YouTube en main.py:
  - `usuario_de_url()` es lógica pura (testeable sin la librería).
  - `capturar_con_reconexion()` bloquea en un hilo propio y reporta por
    callbacks: `on_info(dict)` al conectar (título, espectadores, URL HLS que
    reproduce libVLC tal cual), `on_evento(...)` por cada mensaje y
    `on_estado(tipo, texto)` para la GUI. El filtrado, el TTS y la cola los
    decide quien llama (main), igual que con pytchat.
  - Todo degrada tras guardas: sin TikTokLive instalado, `disponible()` es
    False y la app avisa sin romperse.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import re
import sys

from config import TIPO_TEXTO, TIPO_SUPERCHAT, TIPO_MIEMBRO

logger = logging.getLogger(__name__)

# tiktok.com/@usuario[/live]. Los usuarios de TikTok llevan letras, números,
# guion bajo y punto. No se aceptan "@usuario" sueltos (chocarían con los
# handles de YouTube); hace falta la URL con dominio.
_URL_RE = re.compile(
    r"(?<![\w.-])(?:https?://)?(?:(?:www|m)\.)?tiktok\.com/@([\w.]+)(?:/live)?(?:[/?#]|$)",
    re.IGNORECASE)


def usuario_de_url(entrada: str) -> str:
    """@usuario si la entrada es una URL de TikTok; cadena vacía si no lo es."""
    m = _URL_RE.search((entrada or "").strip())
    return m.group(1) if m else ""


def disponible() -> bool:
    """¿Está instalada TikTokLive? Sin importarla, para no frenar el arranque."""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "_internal", "TikTokLive")
        return os.path.isdir(base)
    try:
        return importlib.util.find_spec("TikTokLive") is not None
    except Exception:
        return False


# ── Sesión de captura ─────────────────────────────────────────────────────────

def _info_de_sala(client) -> dict:
    """Metadatos de la sala en el formato del panel de información + la URL HLS
    del directo (clave interna `_url_flujo`, la consume el reproductor)."""
    info = client.room_info or {}
    stream = info.get("stream_url") or {}
    owner = info.get("owner") or {}
    return {
        "titulo":      (info.get("title") or "").strip(),
        "canal":       (owner.get("nickname") or "").strip(),
        "vistas":      info.get("user_count"),   # espectadores actuales
        "en_vivo":     True,
        "_url_flujo":  (stream.get("hls_pull_url") or "").strip(),
    }


async def _vigilar_parada(client, parada) -> None:
    """Convierte el Event de parada (mundo de hilos) en un disconnect (asyncio)."""
    try:
        while not parada.is_set():
            await asyncio.sleep(0.3)
        await client.disconnect()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.debug("vigilar_parada: %s", exc)


def _sesion(usuario, parada, on_evento, on_estado, on_info):
    """Una conexión completa (bloquea hasta desconectar). Devuelve la excepción
    de conexión si la hubo, o None si terminó con normalidad."""
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import (ConnectEvent, CommentEvent, GiftEvent,
                                   SubscribeEvent, DisconnectEvent, LiveEndEvent)

    client = TikTokLiveClient(unique_id=usuario)
    error: list = [None]

    def _autor(evento) -> tuple[str, str]:
        u = getattr(evento, "user", None)
        nombre = (getattr(u, "nickname", "") or getattr(u, "username", "")
                  or "Usuario").strip() or "Usuario"
        canal_id = str(getattr(u, "id", "") or "")
        return nombre, canal_id

    @client.on(ConnectEvent)
    async def _on_connect(evento):
        try:
            if on_info:
                on_info(_info_de_sala(client))
        except Exception as exc:
            logger.debug("info de sala: %s", exc)
        if on_estado:
            on_estado("conectado", "Conectado al directo de TikTok.")

    @client.on(CommentEvent)
    async def _on_comment(evento):
        autor, canal_id = _autor(evento)
        on_evento(autor, (evento.comment or "").strip(), TIPO_TEXTO, "", canal_id)

    @client.on(GiftEvent)
    async def _on_gift(evento):
        # Los regalos «en racha» disparan un evento por repetición: solo se
        # anuncia el final de la racha, con el total, para no inundar el TTS.
        if getattr(evento, "streaking", False):
            return
        autor, canal_id = _autor(evento)
        gift = getattr(evento, "gift", None)
        nombre = (getattr(gift, "name", "") or "regalo").strip()
        diamantes = int(getattr(gift, "diamond_count", 0) or 0)
        repes = max(1, int(getattr(evento, "repeat_count", 1) or 1))
        total = diamantes * repes
        detalle = f"{nombre} x{repes}" if repes > 1 else nombre
        monto = f"{total} diamantes" if total else ""
        on_evento(autor, detalle, TIPO_SUPERCHAT, monto, canal_id)

    @client.on(SubscribeEvent)
    async def _on_subscribe(evento):
        autor, canal_id = _autor(evento)
        on_evento(autor, "", TIPO_MIEMBRO, "", canal_id)

    @client.on(LiveEndEvent)
    async def _on_live_end(evento):
        if on_estado and not parada.is_set():
            on_estado("desconectado", "El directo de TikTok ha terminado.")

    @client.on(DisconnectEvent)
    async def _on_disconnect(evento):
        pass  # el cierre ordenado lo gestiona quien llama

    async def _correr():
        vigia = asyncio.create_task(_vigilar_parada(client, parada))
        try:
            await client.connect(fetch_room_info=True)
        finally:
            vigia.cancel()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_correr())
    except Exception as exc:
        error[0] = exc
        logger.debug("sesión TikTok: %s", exc)
    finally:
        # Drenar lo pendiente (cierre del websocket, keepalives) antes de
        # cerrar el loop; si no, asyncio escupe «Task was destroyed but it
        # is pending» al terminar cada sesión.
        try:
            pendientes = asyncio.all_tasks(loop)
            for t in pendientes:
                t.cancel()
            if pendientes:
                loop.run_until_complete(
                    asyncio.gather(*pendientes, return_exceptions=True))
        except Exception:
            pass
        try:    loop.close()
        except Exception: pass
    return error[0]


def _mensaje_error(exc) -> str:
    t = f"{type(exc).__name__}: {exc}".lower()
    if "offline" in t or "not live" in t or "not currently live" in t:
        return "Ese usuario de TikTok no está en directo ahora mismo."
    if "notfound" in t or "not found" in t or "user_not_found" in t:
        return "No se encontró ese usuario de TikTok. Revisa la URL."
    if "sign" in t or "euler" in t or "rate" in t and "limit" in t:
        return ("El servidor de firmas de TikTok no responde o alcanzó su "
                "límite. Espera un momento y reintenta.")
    if "captcha" in t or "blocked" in t:
        return "TikTok pidió verificación (captcha). Reintenta más tarde."
    return f"No se pudo conectar al directo de TikTok: {exc}"


def _es_error_permanente(exc) -> bool:
    t = f"{type(exc).__name__}: {exc}".lower()
    return any(p in t for p in ("offline", "not live", "notfound", "not found"))


def capturar_con_reconexion(usuario, config, parada, on_evento,
                            on_estado=None, on_info=None) -> None:
    """Bucle de captura con reintentos, con el mismo contrato de estados que la
    captura de YouTube (conectando/conectado/reintentando/error…). Bloquea:
    llamar desde un hilo aparte."""
    if not disponible():
        if on_estado:
            on_estado("error_permanente",
                      "Falta la librería TikTokLive. Ejecuta instalar.bat.")
        parada.set()
        return

    intentos = 0
    while not parada.is_set():
        if on_estado:
            on_estado("conectando", f"Conectando al directo de TikTok de @{usuario}...")
        err = _sesion(usuario, parada, on_evento, on_estado, on_info)
        if parada.is_set():
            break
        if err is not None and _es_error_permanente(err):
            if on_estado:
                on_estado("error_permanente", _mensaje_error(err))
            parada.set()
            break
        if err is None:
            # Conexión que terminó sola (fin del directo): no reintentamos.
            if on_estado:
                on_estado("desconectado", "El directo de TikTok ha terminado.")
            parada.set()
            break
        if not config.get("reconectar", True):
            if on_estado:
                on_estado("error", _mensaje_error(err))
            parada.set()
            break
        intentos += 1
        mi = config.get("max_intentos", 0)
        if mi > 0 and intentos >= mi:
            if on_estado:
                on_estado("error", f"Se agotaron los {mi} intentos de reconexión.")
            parada.set()
            break
        espera = config.get("espera_entre_intentos", 10)
        sfx = f" de {mi}" if mi else ""
        if on_estado:
            on_estado("reintentando",
                      f"Reintentando en {espera} segundos (intento {intentos}{sfx})...")
        parada.wait(timeout=espera)
