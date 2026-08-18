import logging
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        self.assertIn("Lector de pantalla activo: NVDA", texto)

    def test_censo_incluye_hilo_actual(self):
        self.assertIn(threading.current_thread().name, diagnostico.censo_hilos())
        self.assertIn("vivos=", diagnostico.componer_censo_hilos())

    def test_vigilante_informa_bloqueo_sobre_umbral(self):
        with patch.object(diagnostico.sys, "_current_frames", return_value={}):
            texto = diagnostico.vigilar_hilo_interfaz(10.0, 10.6)
        self.assertIn("bloqueada_ms=600", texto)

    def test_vigilante_no_informa_demora_normal(self):
        self.assertIsNone(diagnostico.vigilar_hilo_interfaz(10.0, 10.4))

    def test_hilo_de_aplicacion_registra_inicio_y_fin(self):
        llamadas = []
        with patch.object(diagnostico.logger, "info") as registrar:
            hilo = diagnostico.crear_hilo(lambda: llamadas.append(True), "HiloPrueba")
            hilo.start()
            hilo.join()
        self.assertEqual(llamadas, [True])
        mensajes = [llamada.args[0] for llamada in registrar.call_args_list]
        self.assertEqual(mensajes, ["HILO inicia nombre=%s", "HILO termina nombre=%s"])
        self.assertEqual(registrar.call_args_list[1].args[1], "HiloPrueba")

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

    def test_capturadores_registran_excepciones_de_hilos(self):
        anterior_sys = sys.excepthook
        anterior_hilos = threading.excepthook
        try:
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    with patch.object(sys, "excepthook"), \
                         patch.object(threading, "excepthook"), \
                         patch("faulthandler.enable") as activar, \
                         patch.object(diagnostico.logging.getLogger("diagnostico"),
                                      "critical") as registrar:
                        diagnostico.instalar_capturadores(Path(tmp) / "fallos.log")
                        error = RuntimeError("prueba")
                        hilo = MagicMock()
                        hilo.name = "HiloPrueba"
                        args = MagicMock(exc_type=RuntimeError, exc_value=error,
                                         exc_traceback=None, thread=hilo)
                        threading.excepthook(args)
                        self.assertIn("HiloPrueba", registrar.call_args.args[1])
                        activar.assert_called_once()
                finally:
                    if diagnostico._ARCHIVO_FALLOS is not None:
                        diagnostico._ARCHIVO_FALLOS.close()
                        diagnostico._ARCHIVO_FALLOS = None
        finally:
            sys.excepthook = anterior_sys
            threading.excepthook = anterior_hilos
