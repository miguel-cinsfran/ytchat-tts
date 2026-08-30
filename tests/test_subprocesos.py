import subprocess
import sys
import time
import threading
import unittest
from unittest.mock import patch

import subprocesos
from subprocesos import Estado, ejecutar


class PruebasSubprocesos(unittest.TestCase):

    def test_hijo_cero_exito_y_recolectado(self):
        capturados = []
        real = subprocess.Popen

        def envolver(*a, **k):
            p = real(*a, **k)
            capturados.append(p)
            return p

        with patch.object(subprocesos.subprocess, "Popen", side_effect=envolver):
            estado = ejecutar([sys.executable, "-c", "import sys; sys.exit(0)"],
                              tope_segundos=5)
        self.assertEqual(Estado.exito, estado)
        self.assertTrue(capturados)
        for p in capturados:
            self.assertIsNotNone(p.poll(), "hijo no recolectado")
            self.assertEqual(0, p.returncode)

    def test_hijo_distinto_de_cero_fallo(self):
        estado = ejecutar([sys.executable, "-c", "import sys; sys.exit(2)"],
                          tope_segundos=5)
        self.assertEqual(Estado.fallo, estado)

    def test_hijo_dormido_evento_desde_otro_hilo_cancelado(self):
        evento = threading.Event()
        capturados = []
        real = subprocess.Popen

        def envolver(*a, **k):
            p = real(*a, **k)
            capturados.append(p)
            return p

        def marcar():
            time.sleep(0.2)
            evento.set()

        hilo = threading.Thread(target=marcar)
        hilo.start()
        inicio = time.monotonic()
        with patch.object(subprocesos.subprocess, "Popen", side_effect=envolver):
            estado = ejecutar([sys.executable, "-c", "import time; time.sleep(10)"],
                              cancel_event=evento, tope_segundos=10)
        duracion = time.monotonic() - inicio
        hilo.join(timeout=2)
        self.assertEqual(Estado.cancelado, estado)
        self.assertLess(duracion, 4, f"tardó {duracion:.2f}s, debe volver rápido")
        for p in capturados:
            self.assertIsNotNone(p.poll(), "hijo cancelado no recolectado")

    def test_hijo_dormido_supera_tope_vencido(self):
        capturados = []
        real = subprocess.Popen

        def envolver(*a, **k):
            p = real(*a, **k)
            capturados.append(p)
            return p

        inicio = time.monotonic()
        with patch.object(subprocesos.subprocess, "Popen", side_effect=envolver):
            estado = ejecutar([sys.executable, "-c", "import time; time.sleep(10)"],
                              tope_segundos=1)
        duracion = time.monotonic() - inicio
        self.assertEqual(Estado.vencido, estado)
        self.assertLess(duracion, 4, f"tardó {duracion:.2f}s")
        self.assertGreaterEqual(duracion, 0.8)
        for p in capturados:
            self.assertIsNotNone(p.poll(), "hijo vencido no recolectado")

    def test_evento_ya_marcado_lanza_y_cancela(self):
        # Frontera real: evento marcado antes de lanzar debe igual lanzar y recolectar
        evento = threading.Event()
        evento.set()
        capturados = []
        real = subprocess.Popen

        def envolver(*a, **k):
            p = real(*a, **k)
            capturados.append(p)
            return p

        inicio = time.monotonic()
        with patch.object(subprocesos.subprocess, "Popen", side_effect=envolver):
            estado = ejecutar([sys.executable, "-c", "import time; time.sleep(10)"],
                              cancel_event=evento, tope_segundos=10)
        duracion = time.monotonic() - inicio
        self.assertEqual(Estado.cancelado, estado)
        self.assertLess(duracion, 4)
        self.assertTrue(capturados)
        for p in capturados:
            self.assertIsNotNone(p.poll())

    def test_os_error_al_arrancar_devuelve_fallo(self):
        with patch.object(subprocesos.subprocess, "Popen", side_effect=OSError("no existe")):
            estado = ejecutar(["no_existe_binario_xyz"], tope_segundos=2)
        self.assertEqual(Estado.fallo, estado)

    def test_excepcion_de_programacion_en_poll_propaga_y_no_deja_hijo_vivo(self):
        capturados = []
        real_popen = subprocess.Popen

        def envolver(*args, **kwargs):
            proceso = real_popen(*args, **kwargs)
            capturados.append(proceso)
            original_poll = proceso.poll

            def poll_falla(*a, **k):
                raise RuntimeError("falla de programación")

            proceso.poll = poll_falla
            proceso._poll_original = original_poll
            return proceso

        with patch.object(subprocesos.subprocess, "Popen", side_effect=envolver):
            with self.assertRaises(RuntimeError):
                ejecutar([sys.executable, "-c", "import time; time.sleep(10)"],
                         tope_segundos=5)

        self.assertTrue(capturados)
        for proceso in capturados:
            try:
                if hasattr(proceso, "_poll_original"):
                    proceso.poll = proceso._poll_original
                self.assertIsNotNone(proceso.poll(), "hijo sigue vivo tras excepción de programación")
            finally:
                try:
                    proceso.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass


if __name__ == "__main__":
    unittest.main()
