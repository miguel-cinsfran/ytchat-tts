"""Gestor de descargas con yt-dlp (módulo puro, sin wx).

Frontera pura/plataforma: este módulo no importa `wx` ni el módulo de yt-dlp.

NO se acopla con las 2 llamadas yt-dlp existentes en `main.obtener_info_video`
ni en `reproductor._info_video`: este módulo hace sus PROPIAS llamadas a
el programa independiente, en su propio hilo.

Modos soportados:
  - mp4  : bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best
  - webm : bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best
  - mp3  : bestaudio + conversión a mp3
  - m4a  : bestaudio + conversión a m4a
"""
from __future__ import annotations

import logging
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from config import app_dir, obtener_opciones_descarga
import ytdlp_bin
from progreso_ytdlp import PLANTILLA, analizar_linea_progreso

logger = logging.getLogger(__name__)

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

INTERVALO_PROGRESO_S = 0.5


def _vigilar_cancelacion(proceso, cancel_event, intervalo=0.2) -> bool:
    while proceso.poll() is None:
        if cancel_event.wait(intervalo):
            proceso.kill()
            return True
    return False


def debe_emitir_progreso(ultimo_ts, ahora, pct):
    """Decide si toca avisar del progreso, para no inundar la interfaz."""
    return (ultimo_ts is None or pct >= 100.0 or
            ahora - ultimo_ts >= INTERVALO_PROGRESO_S)

def formato_a_ydl(formato: str, bitrate: int) -> str:
    """Selector que se pasa a YoutubeDL como `format`.

    mp4/webm piden el mejor stream de vídeo con esa extensión combinada con el
    mejor audio compatible, y caen a un fallback genérico si no hay.
    mp3/m4a piden solo el mejor audio y `descargar()` añade la conversión.
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

    Pide los datos al programa independiente. Si no está disponible, devuelve
    el mismo error que se informaba cuando faltaba el módulo de Python.
    """
    ruta = ytdlp_bin.ruta_ytdlp()
    if ruta is None:
        return {"tipo": "error", "id": "", "titulo": "", "cuenta": 0,
                "mensaje": "yt-dlp no está instalado"}
    try:
        resultado = subprocess.run(
            [ruta, "--dump-json", "--quiet", "--no-warnings", "--skip-download",
             "--no-playlist", "--socket-timeout", "20", url],
            capture_output=True, text=True, creationflags=_sin_ventana(),
            check=False,
        )
        if resultado.returncode:
            return {"tipo": "error", "id": "", "titulo": "", "cuenta": 0,
                    "mensaje": resultado.stderr.strip() or "yt-dlp falló"}
        info = json.loads(resultado.stdout)
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as exc:
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


def _sin_ventana() -> int:
    """Evita una ventana de consola en Windows al ejecutar yt-dlp."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def argumentos_descarga(url, opciones, enumerar, ffmpeg_location=None) -> list[str]:
    """Arma los argumentos de una descarga, sin ejecutar programas."""
    f = (opciones.get("formato") or "mp4").lower().strip()
    bitrate = int(opciones.get("bitrate") or 192)
    argumentos = ["--newline", "--no-warnings", "--progress-template", PLANTILLA,
                  "-f", formato_a_ydl(f, bitrate), "-o",
                  construir_outtmpl(opciones, enumerar)]
    if f in ("mp3", "m4a"):
        argumentos.extend(["-x", "--audio-format", f,
                           "--audio-quality", f"{bitrate}K"])
    if ffmpeg_location is None and getattr(sys, "frozen", False):
        ffmpeg_location = app_dir()
    if ffmpeg_location is not None:
        argumentos.extend(["--ffmpeg-location", str(ffmpeg_location)])
    argumentos.extend(["--", url])
    return argumentos


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
    ruta = ytdlp_bin.ruta_ytdlp()
    if ruta is None:
        estado_cb("error", "yt-dlp no está instalado")
        return

    if not tiene_ffmpeg():
        # Error CLARO (no el genérico de yt-dlp) para que el usuario ciego
        # sepa exactamente qué falta. La GUI ya hace 3-vías con este mensaje.
        estado_cb("error",
                   "ffmpeg no encontrado. La descarga necesita ffmpeg para "
                   "unir audio y vídeo o extraer audio. Usa la versión "
                   "empaquetada o instala ffmpeg. En desarrollo, alcanza "
                   "con tener ffmpeg en el PATH.")
        return

    enumerar = bool(opciones.get("enumerar", False))
    ultimo_progreso_ts = None

    estado_cb("descargando", "")
    try:
        proceso = subprocess.Popen(
            [ruta, *argumentos_descarga(url, opciones, enumerar)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=_sin_ventana(),
        )
        if cancel_event.is_set():
            proceso.kill()
            proceso.wait()
            estado_cb("cancelado", "Descarga cancelada")
            return
        threading.Thread(
            target=_vigilar_cancelacion,
            args=(proceso, cancel_event),
            daemon=True,
            name="Vigilante-cancelacion",
        ).start()
        for linea in iter(proceso.stdout.readline, ""):
            if cancel_event.is_set():
                proceso.kill()
                proceso.wait()
                estado_cb("cancelado", "Descarga cancelada")
                return
            datos = analizar_linea_progreso(linea)
            if datos is None:
                continue
            ahora = time.monotonic()
            if not debe_emitir_progreso(ultimo_progreso_ts, ahora, datos["pct"]):
                continue
            ultimo_progreso_ts = ahora
            try:
                progreso_cb(datos["pct"], datos["velocidad"], datos["eta"],
                            datos["nombre"])
            except Exception as exc:
                logger.debug("progreso_cb lanzó: %s", exc)
        proceso.wait()
        if cancel_event.is_set():
            estado_cb("cancelado", "Descarga cancelada")
        elif proceso.returncode == 0:
            estado_cb("completado", "")
        else:
            estado_cb("error", f"yt-dlp terminó con código {proceso.returncode}")
    except OSError as exc:
        logger.warning("descargar falló: %s", exc)
        estado_cb("error", str(exc) or exc.__class__.__name__)
    except Exception as exc:
        logger.warning("descargar falló: %s", exc)
        estado_cb("error", str(exc) or exc.__class__.__name__)


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
        it = ItemDescarga(id=item_id, url=url, tipo="video", nombre=url)
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
                info = analizar_url(url)
                it.tipo = info.get("tipo", "video")
                titulo = info.get("titulo") or ""
                if titulo:
                    _cb_progreso(it.progreso, "", "", titulo)
                descargar(url, self._opciones, _cb_progreso, _cb_estado, ev)
            except Exception as exc:
                logger.warning("hilo descarga: %s", exc)
                _cb_estado("error", str(exc) or exc.__class__.__name__)

        hilo = threading.Thread(target=_run, daemon=True, name=f"Descarga-{item_id}")
        hilo.start()
        return item_id

    def cancelar(self, item_id: str) -> None:
        """Marca el evento de cancelación para que termine el proceso."""
        ev = self._eventos.get(item_id)
        if ev is not None:
            ev.set()

    def obtener(self, item_id: str) -> Optional[ItemDescarga]:
        with self._lock:
            return self._items.get(item_id)

    def lista(self) -> list[ItemDescarga]:
        with self._lock:
            return [self._items[i] for i in self._orden if i in self._items]
