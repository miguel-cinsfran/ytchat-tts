import logging
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import diagnostico


class DiagnosticoTest(unittest.TestCase):
    def test_manejador_detallado_tiene_nivel_rotacion_y_formato(self):
        with tempfile.TemporaryDirectory() as tmp:
            manejador = diagnostico.crear_manejador_detallado(Path(tmp) / "x.log")
            try:
                self.assertEqual(manejador.level, logging.DEBUG)
                self.assertEqual(manejador.maxBytes, 5 * 1024 * 1024)
                self.assertEqual(manejador.backupCount, 3)
                self.assertIn("%(threadName)s", manejador.formatter._fmt)
                self.assertIn("%(name)s", manejador.formatter._fmt)
            finally:
                manejador.close()

    def test_volcado_incluye_datos_y_faltantes(self):
        texto = diagnostico.componer_volcado_entorno(
            "2.0.0", vlc_version="3.0", ytdlp_version="2025.1", gpu="Placa",
            lector="NVDA")
        self.assertIn("Versión de la aplicación: 2.0.0", texto)
        self.assertIn("Versión de libVLC: 3.0", texto)
        self.assertIn("Placa de vídeo: Placa", texto)
        self.assertIn("ENTORNO inicio", texto)

    def test_censo_incluye_hilo_actual(self):
        self.assertIn(threading.current_thread().name, diagnostico.censo_hilos())
        self.assertIn("vivos=", diagnostico.componer_censo_hilos())

    def test_configuracion_instala_registro_detallado_si_esta_activado(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "config.ini").write_text(
                "[diagnostico]\nregistro_detallado = true\n", encoding="utf-8")
            raiz = logging.getLogger()
            previos = list(raiz.handlers)
            for manejador in previos:
                raiz.removeHandler(manejador)
            try:
                with patch.object(config, "app_dir", return_value=Path(tmp)):
                    config.configurar_logging()
                self.assertTrue(any(
                    isinstance(m, logging.handlers.RotatingFileHandler)
                    and Path(m.baseFilename).name == "ytchat-debug.log"
                    for m in raiz.handlers))
            finally:
                for manejador in raiz.handlers[:]:
                    raiz.removeHandler(manejador)
                    manejador.close()
                for manejador in previos:
                    raiz.addHandler(manejador)
