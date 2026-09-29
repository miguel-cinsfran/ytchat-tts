"""Árbol de procesos y atadura a la vida de la app (solo Windows, sin red)."""

import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from ctypes import wintypes
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
FORMATO_CACHE = ("bv*[height<=720][protocol=https]+ba[protocol=https]"
                 "[ext=m4a]/b[height<=720]/bv*+ba/b")

CODIGO_PADRE_ARBOL = (
    "import subprocess, sys, time\n"
    "hijo = subprocess.Popen([sys.executable, '-c', "
    "'import time; time.sleep(60)'])\n"
    "open(sys.argv[1], 'w').write(str(hijo.pid))\n"
    "time.sleep(60)\n"
)

CODIGO_INTERMEDIO_JOB = (
    "import os, subprocess, sys\n"
    "from ytchat.core import subprocesos\n"
    "nieto = subprocess.Popen([sys.executable, '-c', "
    "'import time; time.sleep(60)'])\n"
    "subprocesos.vincular_a_la_app(nieto)\n"
    "open(sys.argv[1], 'w').write(str(nieto.pid))\n"
    "os._exit(0)\n"
)


def _sigue_vivo(pid: int) -> bool:
    """Dice si el pid sigue vivo, por código de salida y no por lista."""
    nucleo = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = nucleo.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        codigo = wintypes.DWORD()
        if not nucleo.GetExitCodeProcess(handle, ctypes.byref(codigo)):
            return False
        return codigo.value == 259
    finally:
        try:
            nucleo.CloseHandle(handle)
        except Exception:
            pass


def _esperar_pid(archivo: Path, tope: float = 15.0) -> int:
    """Espera a que el hijo escriba su pid y lo devuelve."""
    limite = time.monotonic() + tope
    while time.monotonic() < limite:
        try:
            texto = archivo.read_text(encoding="utf-8").strip()
        except OSError:
            texto = ""
        if texto.isdigit():
            return int(texto)
        time.sleep(0.1)
    raise AssertionError("el hijo no escribió su pid a tiempo")


def _esperar_muerte(pid: int, tope: float = 3.0) -> bool:
    """True si el pid deja de vivir dentro del tope."""
    limite = time.monotonic() + tope
    while time.monotonic() < limite:
        if not _sigue_vivo(pid):
            return True
        time.sleep(0.1)
    return not _sigue_vivo(pid)


@unittest.skipUnless(os.name == "nt", "solo Windows")
class PruebasArbolProcesos(unittest.TestCase):

    def test_cancelar_mata_al_hijo_del_proceso_lanzado(self):
        from ytchat.core.subprocesos import Estado, ejecutar
        with tempfile.TemporaryDirectory() as carpeta:
            pid_archivo = Path(carpeta) / "hijo.pid"
            evento = threading.Event()
            resultado = {}

            def _correr():
                resultado["estado"] = ejecutar(
                    [sys.executable, "-c", CODIGO_PADRE_ARBOL,
                     str(pid_archivo)],
                    cancel_event=evento, tope_segundos=60,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            hilo = threading.Thread(target=_correr, daemon=True)
            hilo.start()
            try:
                pid_hijo = _esperar_pid(pid_archivo)
                self.assertTrue(_sigue_vivo(pid_hijo),
                                "el hijo debía vivir antes de cancelar")
                evento.set()
                hilo.join(timeout=15)
                self.assertFalse(hilo.is_alive(),
                                 "ejecutar no volvió tras cancelar")
                self.assertEqual(Estado.cancelado, resultado.get("estado"))
                self.assertTrue(_esperar_muerte(pid_hijo, tope=3.0),
                                f"el hijo {pid_hijo} siguió vivo tras cancelar")
            finally:
                evento.set()
                hilo.join(timeout=15)

    def test_nieto_atado_muere_con_el_intermedio(self):
        with tempfile.TemporaryDirectory() as carpeta:
            pid_archivo = Path(carpeta) / "nieto.pid"
            intermedio = subprocess.Popen(
                [sys.executable, "-c", CODIGO_INTERMEDIO_JOB,
                 str(pid_archivo)],
                cwd=str(RAIZ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                intermedio.wait(timeout=15)
            except subprocess.TimeoutExpired:
                intermedio.kill()
                self.fail("el intermedio no terminó a tiempo")
            pid_nieto = _esperar_pid(pid_archivo)
            self.assertTrue(_esperar_muerte(pid_nieto, tope=3.0),
                            f"el nieto {pid_nieto} sobrevivió al intermedio")


class PruebasFormatoCache(unittest.TestCase):

    def test_cache_pide_720p_y_mantiene_limite(self):
        from ytchat.downloads import ytdlp_bin
        with tempfile.TemporaryDirectory() as carpeta:
            temporal = Path(carpeta) / ".ytcache-x.mp4"
            args = ytdlp_bin._argumentos_video_cache(
                "yt-dlp.exe", temporal, "j906Pf7n7Sg")
        self.assertIn(FORMATO_CACHE, args)
        self.assertIn("--limit-rate", args)
        self.assertIn(ytdlp_bin.LIMITE_CACHE, args)


if __name__ == "__main__":
    unittest.main()
