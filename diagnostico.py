"""Herramientas de diagnóstico de bajo volumen para YTChat TTS."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


FORMATO_DETALLADO = (
    "%(asctime)s.%(msecs)03d %(levelname)-8s %(threadName)s %(name)s: %(message)s"
)
FECHA_DETALLADA = "%Y-%m-%d %H:%M:%S"
INTERVALO_CENSO_HILOS_S = 30
_ARCHIVO_FALLOS = None


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
        from accessible_output2.outputs.auto import Auto
        for salida in getattr(Auto(), "outputs", []):
            if salida.is_active() and "sapi" not in type(salida).__name__.lower():
                return type(salida).__name__, None
        return None, "no se detectó un lector de pantalla activo"
    except Exception as exc:
        return None, str(exc)


def _placa_video() -> tuple[str | None, str | None]:
    if os.name != "nt":
        return None, "solo disponible en Windows"
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController | "
             "Select-Object -ExpandProperty Name) -join ', '"],
            capture_output=True, text=True, timeout=5, check=False)
        nombre = resultado.stdout.strip()
        if nombre:
            return nombre, None
        return None, resultado.stderr.strip() or "la consulta no devolvió datos"
    except Exception as exc:
        return None, str(exc)


def _version_paquete(nombre: str) -> tuple[str | None, str | None]:
    try:
        modulo = __import__(nombre)
        version = getattr(modulo, "__version__", None)
        if version is None and nombre == "yt_dlp":
            version = getattr(getattr(modulo, "version", None), "__version__", None)
        return (str(version), None) if version else (None, "el paquete no informa versión")
    except Exception as exc:
        return None, str(exc)


def instalar_capturadores(ruta_fallos: str | Path) -> None:
    """Conserva excepciones no capturadas y fallos nativos en archivos."""
    global _ARCHIVO_FALLOS
    logger = logging.getLogger(__name__)
    anterior_sys = sys.excepthook
    anterior_hilos = threading.excepthook

    def _sys_hook(tipo, valor, traza):
        logger.critical("Excepción no capturada del proceso", exc_info=(tipo, valor, traza))
        anterior_sys(tipo, valor, traza)

    def _hilo_hook(args):
        logger.critical("Excepción no capturada en hilo %s", args.thread.name,
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        anterior_hilos(args)

    sys.excepthook = _sys_hook
    threading.excepthook = _hilo_hook
    try:
        import faulthandler
        _ARCHIVO_FALLOS = open(ruta_fallos, "a", encoding="utf-8")
        faulthandler.enable(_ARCHIVO_FALLOS)
    except Exception as exc:
        logger.warning("No se pudo activar faulthandler: %s", exc)


def registrar_entorno(version: str) -> None:
    """Escribe una sola vez el entorno disponible durante el arranque."""
    gpu, motivo_gpu = _placa_video()
    ytdlp, motivo_ytdlp = _version_paquete("yt_dlp")
    vlc, motivo_vlc = _version_paquete("vlc")
    texto = componer_volcado_entorno(
        version, vlc_version=vlc, ytdlp_version=ytdlp, gpu=gpu)
    if motivo_gpu:
        texto = texto.replace("Placa de vídeo: no se pudo obtener",
                              f"Placa de vídeo: no se pudo obtener ({motivo_gpu})")
    if motivo_vlc:
        texto = texto.replace("Versión de libVLC: no se pudo obtener",
                              f"Versión de libVLC: no se pudo obtener ({motivo_vlc})")
    if motivo_ytdlp:
        texto = texto.replace("Versión de yt-dlp: no se pudo obtener",
                              f"Versión de yt-dlp: no se pudo obtener ({motivo_ytdlp})")
    logging.getLogger(__name__).info("%s", texto)


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
