"""Gestor de descargas con yt-dlp (módulo puro, sin wx).

Frontera pura/plataforma: este módulo no importa `wx` y la importación de
`yt_dlp` es GUARDADA (None si falta). Eso permite que los tests corran en
Linux/WSL sin yt-dlp instalado, parcheando `descargas.yt_dlp`.

NO se acopla con las 2 llamadas yt-dlp existentes en `main.obtener_info_video`
ni en `reproductor._info_video`: este módulo hace sus PROPIAS llamadas a
`YoutubeDL`, en su propio hilo y con su propio postprocesador
(FFmpegExtractAudio cuando el formato es mp3/m4a).

Modos soportados:
  - mp4  : bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best
  - webm : bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best
  - mp3  : bestaudio + ExtractAudio(mp3)   (postprocesador FFmpegExtractAudio)
  - m4a  : bestaudio + ExtractAudio(m4a)   (postprocesador FFmpegExtractAudio)
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from config import app_dir, obtener_opciones_descarga

logger = logging.getLogger(__name__)

# Import guardado: yt-dlp puede no estar instalado (entornos de tests en Linux).
# Si falla, queda None y los tests parchean `descargas.yt_dlp` con un mock.
try:
    import yt_dlp  # type: ignore
except ImportError:
    yt_dlp = None  # type: ignore


class DownloadCancelled(Exception):
    """Lanzada desde el progress hook de yt-dlp para abortar una descarga."""


@dataclass
class ItemDescarga:
    """Una descarga encolada. El estado se va mutando desde el hilo de descarga."""
    id: str
    url: str
    tipo: str                # "video" | "playlist" | "error"
    estado: str = "en_cola"  # en_cola | descargando | completado | error | cancelado
    progreso: float = 0.0    # 0..100
    mensaje: str = ""
    nombre: str = ""


# ── Helpers puros (testeables en Linux) ──────────────────────────────────────

def formato_a_ydl(formato: str, bitrate: int) -> str:
    """Selector que se pasa a YoutubeDL como `format`.

    mp4/webm piden el mejor stream de vídeo con esa extensión combinada con el
    mejor audio compatible, y caen a un fallback genérico si no hay.
    mp3/m4a piden solo el mejor audio; la conversión la hace el postprocesador
    FFmpegExtractAudio que añade `descargar()`.
    """
    f = (formato or "").lower().strip()
    if f == "mp4":
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    if f == "webm":
        return "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best"
    if f in ("mp3", "m4a"):
        return "bestaudio"
    return "best"


def construir_outtmpl(opciones: dict, enumerar: bool) -> str:
    """Plantilla de nombre de archivo para yt-dlp.

    El directorio se pasa en `opciones["carpeta"]`; yt-dlp lo une con el nombre.
    Con `enumerar=True` yt-dlp prefijará 01_, 02_, etc. SOLO si el resultado es
    una playlist; en vídeos sueltos el prefijo no aparece.
    """
    carpeta = str(opciones.get("carpeta") or (app_dir() / "Descargas"))
    if enumerar:
        nombre = "%(playlist_index)02d - %(title)s [%(id)s].%(ext)s"
    else:
        nombre = "%(title)s [%(id)s].%(ext)s"
    return str(Path(carpeta) / nombre)


def analizar_url(url: str) -> dict:
    """Inspecciona una URL y devuelve tipo / id / título / cuenta.

    Crea su PROPIA instancia de YoutubeDL (no acopla con main.obtener_info_video
    ni con reproductor._info_video, ver decisiones.md). Si yt_dlp no está,
    devuelve un dict con tipo 'error'.
    """
    if yt_dlp is None:
        return {"tipo": "error", "id": "", "titulo": "", "cuenta": 0,
                "mensaje": "yt-dlp no está instalado"}
    try:
        ydl_opts = {"quiet": True, "skip_download": True, "extract_flat": False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        logger.warning("analizar_url falló: %s", exc)
        return {"tipo": "error", "id": "", "titulo": "", "cuenta": 0,
                "mensaje": str(exc)}
    if not info:
        return {"tipo": "error", "id": "", "titulo": "", "cuenta": 0,
                "mensaje": "URL vacía"}
    tipo = info.get("_type")
    if tipo == "playlist" or "entries" in info:
        return {"tipo": "playlist",
                "id": info.get("id", ""),
                "titulo": info.get("title", ""),
                "cuenta": len(info.get("entries") or [])}
    return {"tipo": "video",
            "id": info.get("id", ""),
            "titulo": info.get("title", ""),
            "cuenta": 1}


def _postprocessors_para(formato: str, bitrate: int) -> list:
    """Postprocesadores que se aplican tras la descarga.

    Solo audio (mp3, m4a) lleva FFmpegExtractAudio. Si yt_dlp no está
    disponible, devolvemos lista vacía (descargar() ya habrá abortado antes).
    """
    f = (formato or "").lower().strip()
    if f not in ("mp3", "m4a"):
        return []
    if yt_dlp is None:
        return []
    return [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": f,
        "preferredquality": str(bitrate or 192),
    }]


def descargar(url: str, opciones: dict,
              progreso_cb: Callable, estado_cb: Callable,
              cancel_event: threading.Event) -> None:
    """Lanza la descarga en el HILO ACTUAL.

    Pensada para correr dentro de `threading.Thread(target=descargar, ...)` que
    crea `GestorDescargas.encolar`. El hilo SIEMPRE termina: las excepciones se
    convierten en `estado_cb("error" | "cancelado", mensaje)` y se hace
    `return`. NUNCA se re-lanza fuera del hilo.

    Callbacks:
      - progreso_cb(pct: float, velocidad, eta, nombre) — se invoca desde el
        progress hook de yt-dlp cada vez que hay actualización de bytes.
      - estado_cb(estado: str, mensaje: str) — transiciones de estado: primero
        "descargando", luego uno de "completado" | "cancelado" | "error".
    """
    if yt_dlp is None:
        estado_cb("error", "yt-dlp no está instalado")
        return

    if not tiene_ffmpeg():
        # Error CLARO (no el genérico de yt-dlp) para que el usuario ciego
        # sepa exactamente qué falta. La GUI ya hace 3-vías con este mensaje.
        estado_cb("error",
                   "ffmpeg no encontrado. La descarga necesita ffmpeg para "
                   "unir audio y vídeo o extraer audio. Usá la versión "
                   "empaquetada o instalá ffmpeg.")
        return

    formato = (opciones.get("formato") or "mp4")
    bitrate = int(opciones.get("bitrate") or 192)
    enumerar = bool(opciones.get("enumerar", False))

    fmt = formato_a_ydl(formato, bitrate)
    outtmpl = construir_outtmpl(opciones, enumerar)
    postprocs = _postprocessors_para(formato, bitrate)

    def _hook(d):
        # El hook se ejecuta dentro del hilo de yt-dlp. Si el evento está
        # marcado, levantamos DownloadCancelled; yt-dlp la propaga y la
        # capturamos fuera del `with` para terminar limpio.
        if cancel_event.is_set():
            raise DownloadCancelled("cancelado por el usuario")
        if d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        descargado = d.get("downloaded_bytes") or 0
        pct = (descargado * 100.0 / total) if total else 0.0
        try:
            progreso_cb(pct, d.get("speed"), d.get("eta"), d.get("filename", ""))
        except Exception as exc:
            logger.debug("progreso_cb lanzó: %s", exc)

    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_hook],
        "postprocessors": postprocs,
    }

    estado_cb("descargando", "")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadCancelled:
        estado_cb("cancelado", "Descarga cancelada")
    except Exception as exc:
        logger.warning("descargar falló: %s", exc)
        estado_cb("error", str(exc) or exc.__class__.__name__)
    else:
        estado_cb("completado", "")


def tiene_ffmpeg() -> bool:
    """¿Hay ffmpeg disponible? Busca junto al .exe (frozen) o en el PATH."""
    if getattr(sys, "frozen", False):
        nombre = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        if (app_dir() / nombre).exists():
            return True
    return shutil.which("ffmpeg") is not None


# ── Gestor de cola ───────────────────────────────────────────────────────────

class GestorDescargas:
    """Cola de descargas. Cada ítem corre en su propio hilo (daemon).

    Los callbacks que recibe `encolar` llevan el `item_id` como primer
    argumento, así la capa de GUI puede actualizar la fila correspondiente
    de su `wx.ListCtrl` sin tener que mantener un mapping externo.
    """

    def __init__(self, opciones: Optional[dict] = None) -> None:
        self._opciones: dict = dict(opciones) if opciones else obtener_opciones_descarga()
        self._items: dict[str, ItemDescarga] = {}
        self._eventos: dict[str, threading.Event] = {}
        self._orden: list[str] = []
        self._lock = threading.Lock()

    def set_opciones(self, op: dict) -> None:
        """Reemplaza las opciones que se pasan a cada descarga nueva."""
        with self._lock:
            self._opciones = dict(op)

    def encolar(self, url: str, progreso_cb: Callable, estado_cb: Callable) -> str:
        """Crea un ItemDescarga, lo deja en 'en_cola' y lanza su hilo.

        `progreso_cb(item_id, pct, velocidad, eta, nombre)` y
        `estado_cb(item_id, estado, mensaje)` reciben el id del ítem.
        """
        item_id = uuid.uuid4().hex[:12]
        # analizar_url es opcional aquí: si yt_dlp falta, igualmente creamos
        # el item con tipo "error" y nombre = url para que la cola no se
        # rompa; el hilo de descarga informará el error 3-vías.
        info = analizar_url(url) if yt_dlp is not None else \
            {"tipo": "video", "id": "", "titulo": url, "cuenta": 1}
        it = ItemDescarga(id=item_id, url=url,
                          tipo=info.get("tipo", "video"),
                          nombre=info.get("titulo") or url)
        ev = threading.Event()
        with self._lock:
            self._items[item_id] = it
            self._eventos[item_id] = ev
            self._orden.append(item_id)

        def _cb_estado(estado: str, mensaje: str = "") -> None:
            it.estado = estado
            it.mensaje = mensaje
            try:
                estado_cb(item_id, estado, mensaje)
            except Exception as exc:
                logger.debug("estado_cb lanzó: %s", exc)

        def _cb_progreso(pct: float, vel, eta, nombre: str) -> None:
            it.progreso = max(0.0, min(100.0, float(pct)))
            if nombre:
                it.nombre = nombre
            try:
                progreso_cb(item_id, it.progreso, vel, eta, it.nombre)
            except Exception as exc:
                logger.debug("progreso_cb lanzó: %s", exc)

        def _run() -> None:
            # Doble red de seguridad: capturar lo que sea que se escape.
            try:
                descargar(url, self._opciones, _cb_progreso, _cb_estado, ev)
            except Exception as exc:
                logger.warning("hilo descarga: %s", exc)
                _cb_estado("error", str(exc) or exc.__class__.__name__)

        hilo = threading.Thread(target=_run, daemon=True, name=f"Descarga-{item_id}")
        hilo.start()
        return item_id

    def cancelar(self, item_id: str) -> None:
        """Marca el evento de cancelación. El progress hook lo verá y lanzará
        DownloadCancelled; el estado del ítem pasa a 'cancelado'."""
        ev = self._eventos.get(item_id)
        if ev is not None:
            ev.set()

    def obtener(self, item_id: str) -> Optional[ItemDescarga]:
        with self._lock:
            return self._items.get(item_id)

    def lista(self) -> list[ItemDescarga]:
        with self._lock:
            return [self._items[i] for i in self._orden if i in self._items]
