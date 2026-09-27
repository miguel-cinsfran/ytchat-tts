"""Ubicación de cada archivo y carpeta, en un solo lugar.

Es el ÚNICO módulo de la aplicación que sabe dónde vive cada archivo:
ningún otro arma rutas de datos o de instalación por su cuenta. Solo usa
biblioteca estándar, para no provocar imports circulares.

Dos raíces: `carpeta_instalacion` (lo que viene con el programa) y
`carpeta_datos` (lo que escribe el usuario). Hoy coinciden; cuando los datos
se muden a una subcarpeta se cambia solo `carpeta_datos`. Ninguna función de
este módulo crea nada en disco, solo devuelve rutas.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# Depende de la ubicación de este archivo: vive en `ytchat/core/`, así que
# la raíz en desarrollo está tres niveles arriba.
_RAIZ_DESARROLLO = Path(__file__).resolve().parent.parent.parent

# Nombres que antes vivían duplicados en cada módulo que los usaba.
NOMBRE_CREDENCIALES = "credenciales.json"
NOMBRE_FFMPEG = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
NOMBRE_YTDLP = "yt-dlp.exe"


def carpeta_instalacion() -> Path:
    """Lo que viene con el programa: junto al .exe, o la raíz en desarrollo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return _RAIZ_DESARROLLO


def carpeta_datos() -> Path:
    """Lo que escribe el usuario. Hoy es la misma carpeta que la instalación."""
    return carpeta_instalacion()


# ── Datos (los escribe el usuario) ───────────────────────────────────────────

def config_ini() -> Path:
    return carpeta_datos() / "config.ini"


def credenciales() -> Path:
    return carpeta_datos() / NOMBRE_CREDENCIALES


def historial_lives() -> Path:
    return carpeta_datos() / "historial_lives.json"


def historial_descargas() -> Path:
    return carpeta_datos() / "historial_descargas.json"


def alias() -> Path:
    return carpeta_datos() / "alias.json"


def mensajes_programados() -> Path:
    return carpeta_datos() / "mensajes_programados.json"


def sounds_ini() -> Path:
    # Va con los datos porque la app lo escribe al cambiar el tema.
    return carpeta_datos() / "sounds.ini"


def log_principal() -> Path:
    return carpeta_datos() / "ytchat.log"


def log_detallado() -> Path:
    return carpeta_datos() / "ytchat-debug.log"


def log_fallos() -> Path:
    return carpeta_datos() / "ytchat-fallos.log"


def cache_audio() -> Path:
    return carpeta_datos() / "cache-audio"


def cache_video() -> Path:
    return carpeta_datos() / "cache-video"


def descargas_por_defecto() -> Path:
    return carpeta_datos() / "Descargas"


# ── Instalación (viene con el programa) ──────────────────────────────────────

def carpeta_sonidos() -> Path:
    return carpeta_instalacion() / "sounds"


def pagina_overlay() -> Path:
    return carpeta_instalacion() / "web" / "chat.html"


def config_predeterminada_ini() -> Path:
    return carpeta_instalacion() / "config.predeterminado.ini"


def ffmpeg_empaquetado() -> Path:
    return carpeta_instalacion() / NOMBRE_FFMPEG


def ytdlp_empaquetado() -> Path:
    return carpeta_instalacion() / NOMBRE_YTDLP


def carpeta_vlc_empaquetada() -> Path:
    return carpeta_instalacion() / "vlc"


def carpeta_interna() -> Path:
    return carpeta_instalacion() / "_internal"
