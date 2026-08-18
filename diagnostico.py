"""Herramientas de diagnóstico de bajo volumen para YTChat TTS."""

from __future__ import annotations

import logging
import os
import platform
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


FORMATO_DETALLADO = (
    "%(asctime)s.%(msecs)03d %(levelname)-8s %(threadName)s %(name)s: %(message)s"
)
FECHA_DETALLADA = "%Y-%m-%d %H:%M:%S"
INTERVALO_CENSO_HILOS_S = 30


def crear_manejador_detallado(ruta: str | Path) -> RotatingFileHandler:
    """Arma el manejador del registro detallado, sin instalarlo."""
    manejador = RotatingFileHandler(
        ruta, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    manejador.setLevel(logging.DEBUG)
    manejador.setFormatter(logging.Formatter(FORMATO_DETALLADO, FECHA_DETALLADA))
    return manejador


def censo_hilos() -> tuple[str, ...]:
    """Devuelve los nombres de los hilos vivos en un orden estable."""
    return tuple(sorted(
        hilo.name for hilo in threading.enumerate() if hilo.is_alive()
    ))


def componer_censo_hilos() -> str:
    nombres = censo_hilos()
    return f"HILOS vivos={len(nombres)} nombres={', '.join(nombres)}"


def _dato(nombre: str, valor, motivo: str | None = None) -> str:
    if valor is not None and str(valor).strip():
        return f"{nombre}: {valor}"
    return f"{nombre}: no se pudo obtener" + (f" ({motivo})" if motivo else "")


def _memoria_total() -> tuple[str | None, str | None]:
    if os.name != "nt":
        return None, "solo disponible en Windows"
    try:
        import ctypes

        class EstadoMemoria(ctypes.Structure):
            _fields_ = [("longitud", ctypes.c_ulong), ("carga", ctypes.c_ulong),
                        ("total_fisica", ctypes.c_ulonglong),
                        ("libre_fisica", ctypes.c_ulonglong),
                        ("total_archivo", ctypes.c_ulonglong),
                        ("libre_archivo", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong),
                        ("libre_virtual", ctypes.c_ulonglong),
                        ("libre_virtual_ext", ctypes.c_ulonglong)]

        estado = EstadoMemoria()
        estado.longitud = ctypes.sizeof(EstadoMemoria)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
            return None, "GlobalMemoryStatusEx devolvió error"
        return f"{estado.total_fisica / (1024 ** 3):.2f} GiB", None
    except Exception as exc:
        return None, str(exc)


def _lector_activo() -> tuple[str | None, str | None]:
    try:
        import accessible_output2
        return accessible_output2.__name__, None
    except Exception as exc:
        return None, str(exc)


def componer_volcado_entorno(version: str, *, vlc_version=None,
                             ytdlp_version=None, gpu=None,
                             lector=None) -> str:
    """Compone todas las líneas del entorno, incluyendo datos no disponibles."""
    memoria, motivo_memoria = _memoria_total()
    lector_detectado, motivo_lector = _lector_activo()
    win = platform.win32_ver()
    windows = " ".join(x for x in win[:2] if x) or None
    edicion = win[0] or None
    lineas = [
        "ENTORNO inicio",
        _dato("Versión de la aplicación", version),
        _dato("Versión de Python", platform.python_version()),
        _dato("Empaquetado", getattr(sys, "frozen", False)),
        _dato("Windows", windows, "platform.win32_ver sin datos"),
        _dato("Edición de Windows", edicion, "platform.win32_ver sin datos"),
        _dato("Arquitectura", platform.architecture()[0]),
        _dato("Núcleos", os.cpu_count(), "os.cpu_count sin datos"),
        _dato("Memoria total", memoria, motivo_memoria),
        _dato("Placa de vídeo", gpu, "no hay consulta estándar disponible"),
        _dato("Versión de libVLC", vlc_version, "no disponible al arrancar"),
        _dato("Versión de yt-dlp", ytdlp_version, "no disponible al arrancar"),
        _dato("Lector de pantalla activo", lector if lector is not None else lector_detectado,
              motivo_lector),
        "ENTORNO fin",
    ]
    return "\n".join(lineas)
