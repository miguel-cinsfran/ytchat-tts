"""Ciclo de vida de subprocesos con cancelación y tope."""

import logging
import os
import subprocess
import threading
import time
from enum import Enum


logger = logging.getLogger(__name__)


class Estado(str, Enum):
    exito = "exito"
    fallo = "fallo"
    cancelado = "cancelado"
    vencido = "vencido"


def terminar_arbol(proceso):
    """Corta el proceso y a sus hijos. Nunca lanza excepciones.

    En Windows ejecuta taskkill con /T (árbol) y /F ANTES de que el padre
    muera, porque si el padre ya murió /T no encuentra a los hijos, y
    después espera al proceso con tope. Fuera de Windows usa terminate
    y kill como antes.
    """
    try:
        pid = getattr(proceso, "pid", None)
        if os.name == "nt" and isinstance(pid, int):
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as exc:
                logger.debug("taskkill del árbol: %s", exc)
            try:
                proceso.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                pass
            except Exception as exc:
                logger.debug("espera del árbol: %s", exc)
                return
            try:
                proceso.kill()
            except Exception as exc:
                logger.debug("kill del árbol: %s", exc)
            try:
                proceso.wait(timeout=5)
            except Exception as exc:
                logger.debug("espera final del árbol: %s", exc)
            return
        try:
            proceso.terminate()
        except OSError:
            pass
        except Exception as exc:
            logger.debug("terminate: %s", exc)
        try:
            proceso.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            pass
        except Exception as exc:
            logger.debug("espera: %s", exc)
            return
        try:
            proceso.kill()
        except OSError:
            pass
        except Exception as exc:
            logger.debug("kill: %s", exc)
        try:
            proceso.wait()
        except Exception as exc:
            logger.debug("espera final: %s", exc)
    except Exception as exc:
        logger.debug("terminar árbol: %s", exc)


def _terminar(proceso):
    terminar_arbol(proceso)


_JOB_APP = None
_BLOQUEO_JOB = threading.Lock()


def _job_app():
    """Job Object único de la app, o None si no se pudo crear."""
    global _JOB_APP
    with _BLOQUEO_JOB:
        if _JOB_APP is not None:
            return _JOB_APP
        try:
            import ctypes
            from ctypes import wintypes
            nucleo = ctypes.WinDLL("kernel32", use_last_error=True)
            trabajo = nucleo.CreateJobObjectW(None, None)
            if not trabajo:
                logger.debug("CreateJobObjectW devolvió NULL")
                return None

            class _LimitesBasicos(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class _Contadores(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class _LimitesExtendidos(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", _LimitesBasicos),
                    ("IoInfo", _Contadores),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            info = _LimitesExtendidos()
            ctypes.memset(ctypes.byref(info), 0, ctypes.sizeof(info))
            info.BasicLimitInformation.LimitFlags = 0x2000
            nucleo.SetInformationJobObject.argtypes = [
                wintypes.HANDLE, ctypes.c_int,
                wintypes.LPVOID, wintypes.DWORD,
            ]
            nucleo.SetInformationJobObject.restype = wintypes.BOOL
            if not nucleo.SetInformationJobObject(
                    trabajo, 9, ctypes.byref(info),
                    ctypes.sizeof(info)):
                logger.debug("SetInformationJobObject falló")
                try:
                    nucleo.CloseHandle(trabajo)
                except Exception:
                    pass
                return None
            # Se guarda a nivel de módulo y su handle no se cierra nunca:
            # al cerrarse el proceso de la app, Windows mata a los
            # procesos asignados.
            _JOB_APP = trabajo
            return _JOB_APP
        except Exception as exc:
            logger.debug("job de la app: %s", exc)
            return None


def vincular_a_la_app(proceso):
    """Ata el proceso a la vida de la app. Nunca lanza ni impide lanzar.

    En Windows asigna el proceso al Job Object único con
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: cuando la app termina por
    cualquier motivo, Windows mata a ese proceso y a los que él haya
    creado. Fuera de Windows no hace nada.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        trabajo = _job_app()
        if not trabajo:
            return
        nucleo = ctypes.WinDLL("kernel32", use_last_error=True)
        nucleo.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE, wintypes.HANDLE,
        ]
        nucleo.AssignProcessToJobObject.restype = wintypes.BOOL
        handle = getattr(proceso, "_handle", None)
        if isinstance(handle, int) and handle:
            if not nucleo.AssignProcessToJobObject(
                    trabajo, wintypes.HANDLE(handle)):
                logger.debug("AssignProcessToJobObject falló")
            return
        pid = getattr(proceso, "pid", None)
        if not isinstance(pid, int):
            return
        nucleo.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
        ]
        nucleo.OpenProcess.restype = wintypes.HANDLE
        handle = nucleo.OpenProcess(0x0100 | 0x0001, False, pid)
        if not handle:
            logger.debug("OpenProcess falló para pid=%s", pid)
            return
        try:
            if not nucleo.AssignProcessToJobObject(
                    trabajo, handle):
                logger.debug("AssignProcessToJobObject falló")
        finally:
            try:
                nucleo.CloseHandle(handle)
            except Exception:
                pass
    except Exception as exc:
        logger.debug("vincular a la app: %s", exc)


def ejecutar(argumentos, cancel_event=None, tope_segundos=3600, **opciones):
    """Lanza argumentos con Popen y espera con cancelación y tope.

    Devuelve un Estado entre éxito, fallo, cancelado y vencido.
    Toda ruta posterior a un Popen exitoso garantiza wait.
    """
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flag = subprocess.CREATE_NO_WINDOW
        if "creationflags" in opciones:
            opciones["creationflags"] = opciones["creationflags"] | flag
        else:
            opciones["creationflags"] = flag

    try:
        proceso = subprocess.Popen(argumentos, **opciones)
    except OSError:
        return Estado.fallo
    try:
        vincular_a_la_app(proceso)
    except Exception:
        pass

    inicio = time.monotonic()
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _terminar(proceso)
                return Estado.cancelado
            if time.monotonic() - inicio >= tope_segundos:
                _terminar(proceso)
                return Estado.vencido
            codigo = proceso.poll()
            if codigo is not None:
                if cancel_event is not None and cancel_event.is_set():
                    proceso.wait()
                    return Estado.cancelado
                proceso.wait()
                if codigo == 0:
                    return Estado.exito
                return Estado.fallo
            time.sleep(0.05)
    finally:
        # Garantiza recolección si por algún motivo se sale sin wait.
        # Si poll falla por error de programación, igual se termina el hijo y se propaga.
        try:
            esta_vivo = proceso.poll() is None
        except Exception:
            _terminar(proceso)
            raise
        if esta_vivo:
            _terminar(proceso)
        else:
            proceso.wait()
