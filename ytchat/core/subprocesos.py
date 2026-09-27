"""Ciclo de vida de subprocesos con cancelación y tope."""

import subprocess
import time
from enum import Enum


class Estado(str, Enum):
    exito = "exito"
    fallo = "fallo"
    cancelado = "cancelado"
    vencido = "vencido"


def _terminar(proceso):
    try:
        proceso.terminate()
    except OSError:
        pass
    try:
        proceso.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        proceso.kill()
    except OSError:
        pass
    proceso.wait()


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
