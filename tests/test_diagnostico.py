import importlib
import logging
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
import diagnostico


MODULOS_OMITIDOS = {
    # Son herramientas ejecutables, no módulos de la aplicación.
    "generar_docs", "smoke_test", "sound_gen",
}


class DiagnosticoTest(unittest.TestCase):
    def test_obtener_logger_cuelga_del_arbol_de_la_aplicacion(self):
        logger = diagnostico.obtener_logger("descargas")
        self.assertTrue(logger.name.startswith("ytchat."))

    def test_los_loggers_de_la_aplicacion_cuelgan_del_arbol_ytchat(self):
        raiz = Path(__file__).resolve().parent.parent
        for ruta in raiz.glob("*.py"):
            if ruta.stem in MODULOS_OMITIDOS:
                continue
            modulo = importlib.import_module(ruta.stem)
            logger = getattr(modulo, "logger", None)
            if isinstance(logger, logging.Logger):
                self.assertTrue(
                    logger.name.startswith("ytchat."),
                    f"El logger del módulo {ruta.stem} está fuera del árbol ytchat: "
                    f"{logger.name}")

    def test_compone_marcas_de_inicio_y_cierre_con_zona_horaria(self):
        momento = datetime(2026, 8, 25, 21, 52, 9,
                           tzinfo=timezone(timedelta(hours=-4)))
        inicio = diagnostico.componer_cabecera_fallos("2.0.1", momento)
        cierre = diagnostico.componer_cierre_fallos(momento)
        self.assertEqual(inicio,
                         "=== INICIO YTChat TTS v2.0.1 2026-08-25T21:52:09-04:00 ===")
        self.assertEqual(cierre, "=== CIERRE LIMPIO 2026-08-25T21:52:09-04:00 ===")
        self.assertNotEqual(inicio, cierre)

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

    def test_manejador_detallado_acepta_registro_propio(self):
        with patch.object(diagnostico, "RotatingFileHandler", return_value=logging.Handler()):
            manejador = diagnostico.crear_manejador_detallado("x.log")
        registro = logging.LogRecord(
            "ytchat.loquesea", logging.DEBUG, "", 0, "prueba", (), None)
        self.assertTrue(manejador.filter(registro))

    def test_manejador_detallado_rechaza_registro_de_websockets(self):
        with patch.object(diagnostico, "RotatingFileHandler", return_value=logging.Handler()):
            manejador = diagnostico.crear_manejador_detallado("x.log")
        registro = logging.LogRecord(
            "websockets.client", logging.DEBUG, "", 0, "prueba", (), None)
        self.assertFalse(manejador.filter(registro))

    def test_manejador_detallado_rota_el_registro_anterior_al_arrancar(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "x.log"
            ruta.write_text("sesion anterior", encoding="utf-8")
            manejador = diagnostico.crear_manejador_detallado(ruta)
            try:
                self.assertEqual(ruta.read_text(encoding="utf-8"), "")
                self.assertEqual(
                    ruta.with_name("x.log.1").read_text(encoding="utf-8"),
                    "sesion anterior")
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
        registrar, activo = diagnostico.decidir_bloqueo_interfaz(10.0, 10.6, False)
        texto = diagnostico.componer_bloqueo_interfaz(600, "pila de interfaz")
        self.assertTrue(registrar)
        self.assertTrue(activo)
        self.assertIn("bloqueada_ms=600", texto)

    def test_vigilante_no_informa_demora_normal(self):
        self.assertEqual(
            diagnostico.decidir_bloqueo_interfaz(10.0, 10.4, False), (False, False))

    def test_vigilante_registra_un_solo_bloqueo_largo(self):
        self.assertEqual(
            diagnostico.decidir_bloqueo_interfaz(10.0, 11.0, False), (True, True))
        self.assertEqual(
            diagnostico.decidir_bloqueo_interfaz(10.0, 11.5, True), (False, True))

    def test_pila_del_vigilante_toma_el_marco_del_hilo_principal(self):
        principal = object()
        vigilante = object()
        with patch.object(
                diagnostico.traceback, "format_stack",
                side_effect=lambda marco: ["GUI"] if marco is principal else ["VIGILANTE"]):
            pila = diagnostico.pila_hilo_interfaz({101: principal, 202: vigilante}, 101)
        self.assertEqual(pila, "GUI")

    def test_pila_no_usa_el_marco_del_vigilante(self):
        with patch.object(diagnostico.traceback, "format_stack", return_value=["VIGILANTE"]):
            pila = diagnostico.pila_hilo_interfaz({202: object()}, 101)
        self.assertEqual(pila, "no disponible")

    def test_vigilante_no_repite_un_bloqueo_largo(self):
        class Parada:
            def __init__(self):
                self.llamadas = 0

            def wait(self, _intervalo):
                self.llamadas += 1
                return self.llamadas > 2

        with patch.object(diagnostico.time, "monotonic", side_effect=[1.0, 1.1]), \
                patch.object(diagnostico.sys, "_current_frames", return_value={}), \
                patch.object(diagnostico.logger, "warning") as registrar:
            diagnostico.vigilar_hilo_interfaz(lambda: 0.0, Parada())
        registrar.assert_called_once()

    def test_vigilante_retrata_el_hilo_principal_desde_otro_hilo(self):
        principal = threading.main_thread().ident
        identificadores = []

        class Parada:
            def __init__(self):
                self.llamadas = 0

            def wait(self, _intervalo):
                self.llamadas += 1
                return self.llamadas > 1

        def recordar(_marcos, identificador):
            identificadores.append(identificador)
            return "pila"

        with patch.object(diagnostico.time, "monotonic", return_value=1.0), \
                patch.object(diagnostico.sys, "_current_frames", return_value={}), \
                patch.object(diagnostico, "pila_hilo_interfaz", side_effect=recordar), \
                patch.object(diagnostico.logger, "warning"):
            hilo = threading.Thread(
                target=diagnostico.vigilar_hilo_interfaz,
                args=(lambda: 0.0, Parada()))
            hilo.start()
            hilo.join()

        self.assertEqual(identificadores, [principal])
        self.assertNotEqual(principal, hilo.ident)

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

    def test_marcar_incidencia_escribe_marca_visible(self):
        with patch.object(diagnostico.logger, "warning") as registrar:
            marca = diagnostico.marcar_incidencia()
        self.assertTrue(marca)
        registrar.assert_called_once_with("INCIDENCIA usuario marca=%s", marca)

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
                         patch.object(diagnostico.logger, "critical") as registrar:
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

    def test_capturadores_escriben_cabecera_antes_de_activar_faulthandler(self):
        anterior = diagnostico._ARCHIVO_FALLOS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ruta = Path(tmp) / "fallos.log"
                with patch("faulthandler.enable"):
                    diagnostico.instalar_capturadores(ruta, version="2.0.1")
                self.assertIn("INICIO YTChat TTS v2.0.1", ruta.read_text(encoding="utf-8"))
                diagnostico._ARCHIVO_FALLOS.close()
                diagnostico._ARCHIVO_FALLOS = None
        finally:
            if diagnostico._ARCHIVO_FALLOS is not None:
                diagnostico._ARCHIVO_FALLOS.close()
            diagnostico._ARCHIVO_FALLOS = anterior

    def test_hilo_creado_aparece_mientras_corre_y_desaparece_al_terminar(self):
        inicio = threading.Event()
        fin = threading.Event()

        def tarea():
            inicio.set()
            fin.wait()

        hilo = diagnostico.crear_hilo(tarea, "HiloPruebaVivo")
        hilo.start()
        self.assertTrue(inicio.wait(timeout=2))
        self.assertIn("HiloPruebaVivo", diagnostico.hilos_vivos_de_la_aplicacion())
        fin.set()
        hilo.join(timeout=2)
        self.assertNotIn("HiloPruebaVivo", diagnostico.hilos_vivos_de_la_aplicacion())

    def test_hilo_creado_y_no_arrancado_no_aparece(self):
        hilo = diagnostico.crear_hilo(lambda: None, "HiloNoArrancadoUnico")
        self.assertNotIn("HiloNoArrancadoUnico", diagnostico.hilos_vivos_de_la_aplicacion())
        self.assertNotIn(hilo, diagnostico._hilos_vivos)
        # No se arranca a proposito: no debe quedar registrado.
        del hilo

    def test_dos_hilos_con_mismo_nombre_se_cuentan_por_separado(self):
        inicio1 = threading.Event()
        inicio2 = threading.Event()
        fin1 = threading.Event()
        fin2 = threading.Event()

        def tarea1():
            inicio1.set()
            fin1.wait()

        def tarea2():
            inicio2.set()
            fin2.wait()

        hilo1 = diagnostico.crear_hilo(tarea1, "HiloDuplicado")
        hilo2 = diagnostico.crear_hilo(tarea2, "HiloDuplicado")
        hilo1.start()
        hilo2.start()
        self.assertTrue(inicio1.wait(timeout=2))
        self.assertTrue(inicio2.wait(timeout=2))
        self.assertIn("HiloDuplicado", diagnostico.hilos_vivos_de_la_aplicacion())
        fin1.set()
        hilo1.join(timeout=2)
        self.assertIn("HiloDuplicado", diagnostico.hilos_vivos_de_la_aplicacion())
        fin2.set()
        hilo2.join(timeout=2)
        self.assertNotIn("HiloDuplicado", diagnostico.hilos_vivos_de_la_aplicacion())

    def test_crear_hilo_da_de_baja_el_registro_interno_al_terminar(self):
        listo = threading.Event()

        def tarea():
            listo.set()

        hilo = diagnostico.crear_hilo(tarea, "HiloBajaRegistroUnico")
        hilo.start()
        self.assertTrue(listo.wait(timeout=2))
        hilo.join(timeout=2)
        try:
            with diagnostico._bloqueo_hilos:
                self.assertNotIn(hilo, diagnostico._hilos_vivos)
        finally:
            with diagnostico._bloqueo_hilos:
                diagnostico._hilos_vivos.discard(hilo)
