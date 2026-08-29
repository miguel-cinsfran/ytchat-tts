"""Herramientas de diagnóstico de bajo volumen para YTChat TTS."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import ytdlp_bin


FORMATO_DETALLADO = (
    "%(asctime)s.%(msecs)03d %(levelname)-8s %(threadName)s %(name)s: %(message)s"
)
FECHA_DETALLADA = "%Y-%m-%d %H:%M:%S"
INTERVALO_CENSO_HILOS_S = 30
UMBRAL_BLOQUEO_INTERFAZ_MS = 500
RAIZ_LOGGER = "ytchat"
_ARCHIVO_FALLOS = None


def obtener_logger(nombre: str) -> logging.Logger:
    """Devuelve el logger del modulo, colgado del arbol de la aplicacion."""
    return logging.getLogger(f"{RAIZ_LOGGER}.{nombre}")


logger = obtener_logger(__name__)


def componer_cabecera_fallos(version: str, momento: datetime) -> str:
    """Compone la separación visible de una sesión de fallos."""
    marca = momento.isoformat(timespec="seconds")
    return (f"=== INICIO YTChat TTS v{version} {marca} ===\n"
            "Este archivo anota sucesos internos de Windows; muchos son inofensivos y la aplicación sigue funcionando. Si ves «CIERRE LIMPIO», la sesión terminó bien.")


def componer_cierre_fallos(momento: datetime) -> str:
    """Compone la marca de un cierre normal."""
    marca = momento.isoformat(timespec="seconds")
    return f"=== CIERRE LIMPIO {marca} ==="


def crear_manejador_detallado(ruta: str | Path) -> RotatingFileHandler:
    """Arma el manejador del registro detallado, sin instalarlo."""
    ruta = Path(ruta)
    manejador = RotatingFileHandler(
        ruta, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    if ruta.exists() and ruta.stat().st_size:
        manejador.doRollover()
    manejador.setLevel(logging.DEBUG)
    manejador.setFormatter(logging.Formatter(FORMATO_DETALLADO, FECHA_DETALLADA))
    # Solo entra lo propio, sin mantener una lista de librerias de terceros.
    manejador.addFilter(logging.Filter(RAIZ_LOGGER))
    return manejador


def censo_hilos() -> tuple[str, ...]:
    """Devuelve los nombres de los hilos vivos en un orden estable."""
    return tuple(sorted(
        hilo.name for hilo in threading.enumerate() if hilo.is_alive()
    ))


def componer_censo_hilos() -> str:
    nombres = censo_hilos()
    return f"HILOS vivos={len(nombres)} nombres={', '.join(nombres)}"


def decidir_bloqueo_interfaz(
    marca_latido: float, ahora: float, ya_registrado: bool
) -> tuple[bool, bool]:
    """Decide si corresponde registrar el estado actual del latido."""
    demora_ms = (ahora - marca_latido) * 1000
    if demora_ms < UMBRAL_BLOQUEO_INTERFAZ_MS:
        return False, False
    return not ya_registrado, True


def componer_bloqueo_interfaz(demora_ms: float, pila: str) -> str:
    return f"INTERFAZ bloqueada_ms={demora_ms:.0f}\n{pila.rstrip()}"


def pila_hilo_interfaz(marcos: dict[int, object], identificador: int | None) -> str:
    marco = marcos.get(identificador)
    return "".join(traceback.format_stack(marco)).rstrip() if marco else "no disponible"


def vigilar_hilo_interfaz(obtener_marca, parada: threading.Event) -> None:
    """Registra una pila del hilo principal mientras su latido está atrasado."""
    ya_registrado = False
    while not parada.wait(0.1):
        ahora = time.monotonic()
        marca_latido = obtener_marca()
        registrar, ya_registrado = decidir_bloqueo_interfaz(
            marca_latido, ahora, ya_registrado)
        if registrar:
            demora_ms = (ahora - marca_latido) * 1000
            pila = pila_hilo_interfaz(
                sys._current_frames(), threading.main_thread().ident)
            logger.warning("%s", componer_bloqueo_interfaz(demora_ms, pila))


_hilos_vivos: set[threading.Thread] = set()
_bloqueo_hilos = threading.Lock()


def hilos_vivos_de_la_aplicacion() -> tuple[str, ...]:
    """Devuelve los nombres de los hilos vivos registrados, ordenados y sin repetir."""
    with _bloqueo_hilos:
        vivos = [hilo for hilo in list(_hilos_vivos) if hilo.is_alive()]
    return tuple(sorted({hilo.name for hilo in vivos}))


def crear_hilo(target, nombre: str, *, args=(), daemon=True) -> threading.Thread:
    """Crea un hilo que deja constancia de su vida completa."""
    logger = obtener_logger(__name__)

    def ejecutar():
        # El alta va dentro de ejecutar y no en crear_hilo para que un hilo
        # creado pero nunca arrancado no quede registrado para siempre.
        hilo_actual = threading.current_thread()
        with _bloqueo_hilos:
            _hilos_vivos.add(hilo_actual)
        logger.info("HILO inicia nombre=%s", nombre)
        try:
            target(*args)
        finally:
            logger.info("HILO termina nombre=%s", nombre)
            with _bloqueo_hilos:
                _hilos_vivos.discard(hilo_actual)

    return threading.Thread(target=ejecutar, daemon=daemon, name=nombre)


def debe_censar_hilos(marca_anterior: float, marca_actual: float | None = None):
    actual = time.monotonic() if marca_actual is None else marca_actual
    if actual - marca_anterior < INTERVALO_CENSO_HILOS_S:
        return None
    return actual, componer_censo_hilos()


def marcar_incidencia() -> str:
    marca = datetime.now().astimezone().isoformat(timespec="milliseconds")
    logger.warning("INCIDENCIA usuario marca=%s", marca)
    return marca


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
            capture_output=True, text=True, timeout=5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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


def instalar_capturadores(ruta_fallos: str | Path, version: str = "desconocida") -> None:
    """Conserva excepciones no capturadas y fallos nativos en archivos."""
    global _ARCHIVO_FALLOS
    logger = obtener_logger(__name__)
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
        _ARCHIVO_FALLOS.write(
            componer_cabecera_fallos(version, datetime.now().astimezone()) + "\n")
        _ARCHIVO_FALLOS.flush()
        faulthandler.enable(_ARCHIVO_FALLOS)
    except Exception as exc:
        logger.warning("No se pudo activar faulthandler: %s", exc)


def registrar_cierre_fallos(momento: datetime | None = None) -> None:
    """Escribe y vacía la marca de cierre si el archivo está disponible."""
    if _ARCHIVO_FALLOS is None:
        return
    marca = momento or datetime.now().astimezone()
    try:
        _ARCHIVO_FALLOS.write(componer_cierre_fallos(marca) + "\n")
        _ARCHIVO_FALLOS.flush()
    except Exception as exc:
        logger.warning("No se pudo registrar el cierre de fallos: %s", exc)


def registrar_entorno(version: str) -> None:
    """Escribe una sola vez el entorno disponible durante el arranque."""
    gpu, motivo_gpu = _placa_video()
    ruta_ytdlp = ytdlp_bin.ruta_ytdlp()
    ytdlp = ytdlp_bin.version_ytdlp(ruta_ytdlp) if ruta_ytdlp else None
    motivo_ytdlp = None if ytdlp else "no disponible al arrancar"
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
    obtener_logger(__name__).info("%s", texto)


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
