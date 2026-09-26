"""Localiza el ejecutable de ffmpeg: un único resolvedor para toda la app.

Lo usan el gestor de descargas (mux de yt-dlp), el relevo de directos y la
caché de vídeo. Antes cada uno buscaba por su cuenta (PATH, imageio_ffmpeg o
la carpeta del .exe) y no coincidían: se podía «tener» ffmpeg para descargar
y no encontrarlo para el relevo, o al revés.

Orden de búsqueda:
  1. Empaquetada: el ffmpeg.exe que construir.bat deja junto al .exe.
  2. imageio_ffmpeg (en desarrollo trae un ffmpeg portable en site-packages;
     el paquete lo excluye porque ya lleva la copia del punto 1).
  3. Un ffmpeg en el PATH.
"""

from __future__ import annotations

import shutil
import sys

import paths

NOMBRE_BINARIO = paths.NOMBRE_FFMPEG


def ruta_ffmpeg() -> str | None:
    """Ruta al ejecutable de ffmpeg, o None si no hay ninguno."""
    if getattr(sys, "frozen", False):
        candidato = paths.ffmpeg_empaquetado()
        if candidato.is_file():
            return str(candidato)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return shutil.which("ffmpeg")
