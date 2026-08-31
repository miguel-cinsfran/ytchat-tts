import unittest
import sys
import types
from unittest.mock import Mock, patch

import main


class ConexionFalsa:
    def __init__(self, *args):
        self.llamadas = []

    def conectar(self, url):
        self.llamadas.append(("conectar", url))

    def desconectar(self):
        self.llamadas.append(("desconectar",))


class PruebasCableadoMain(unittest.TestCase):
    def test_main_registra_el_entorno_en_un_hilo(self):
        message_box = Mock()
        ctypes_falso = types.SimpleNamespace(
            windll=types.SimpleNamespace(
                user32=types.SimpleNamespace(MessageBoxW=message_box)))
        with patch.object(main, "_verificar_instancia_unica", return_value=False), \
                patch.object(main, "configurar_logging"), \
                patch.object(main.diagnostico, "instalar_capturadores"), \
                patch.object(main.diagnostico, "registrar_entorno_en_hilo") as registrar, \
                patch.object(main.diagnostico, "registrar_entorno") as bloquear, \
                patch.dict(sys.modules, {"ctypes": ctypes_falso}), \
                patch.object(sys, "exit", side_effect=SystemExit(0)):
            with self.assertRaises(SystemExit):
                main.main()

        registrar.assert_called_once_with(main.APP_VERSION)
        bloquear.assert_not_called()

    def test_main_no_registra_el_entorno_de_forma_bloqueante(self):
        message_box = Mock()
        ctypes_falso = types.SimpleNamespace(
            windll=types.SimpleNamespace(
                user32=types.SimpleNamespace(MessageBoxW=message_box)))
        with patch.object(main, "_verificar_instancia_unica", return_value=False), \
                patch.object(main, "configurar_logging"), \
                patch.object(main.diagnostico, "instalar_capturadores"), \
                patch.object(main.diagnostico, "registrar_entorno_en_hilo"), \
                patch.object(main.diagnostico, "registrar_entorno") as bloquear, \
                patch.dict(sys.modules, {"ctypes": ctypes_falso}), \
                patch.object(sys, "exit", side_effect=SystemExit(0)):
            with self.assertRaises(SystemExit):
                main.main()

        bloquear.assert_not_called()

    def test_aviso_de_instancia_usa_banderas_de_primer_plano(self):
        message_box = Mock()
        ctypes_falso = types.SimpleNamespace(
            windll=types.SimpleNamespace(
                user32=types.SimpleNamespace(MessageBoxW=message_box)))

        with patch.object(main, "_verificar_instancia_unica", return_value=False), \
                patch.object(main, "configurar_logging"), \
                patch.object(main.diagnostico, "instalar_capturadores"), \
                patch.object(main.diagnostico, "registrar_entorno_en_hilo"), \
                patch.dict(sys.modules, {"ctypes": ctypes_falso}), \
                patch.object(sys, "exit", side_effect=SystemExit(0)):
            with self.assertRaises(SystemExit):
                main.main()

        banderas = message_box.call_args.args[3]
        self.assertEqual(banderas, 0x40 | 0x00010000 | 0x00040000)

    def test_los_callbacks_comparten_el_registro_de_conexiones(self):
        with patch.object(main.conexion, "Conexiones", ConexionFalsa):
            conectar, desconectar = main.armar_callbacks_captura(
                object(), {}, object(), object())

        conectar("directo")
        desconectar()
        self.assertIs(conectar.__self__, desconectar.__self__)
        self.assertEqual(conectar.__self__.llamadas,
                         [("conectar", "directo"), ("desconectar",)])

    def test_iniciar_interfaz_cierra_sonidos_sin_marcar_limpio_al_volver(self):
        orden = []
        conectar = object()
        desconectar = object()

        def armar(*args):
            orden.append("callbacks")
            return conectar, desconectar

        def iniciar(**kwargs):
            orden.append(("gui", kwargs["iniciar_captura_cb"],
                          kwargs["detener_captura_cb"]))

        with patch.object(main, "armar_callbacks_captura", side_effect=armar), \
                patch.object(main.diagnostico, "registrar_cierre_fallos",
                             side_effect=lambda: orden.append("cierre")), \
                patch.object(main._snd, "cerrar", side_effect=lambda: orden.append("sonido")):
            main.iniciar_interfaz({}, object(), object(), object(), object(), iniciar)

        self.assertEqual(orden, ["callbacks", ("gui", conectar, desconectar),
                                 "sonido"])
        self.assertNotIn("cierre", orden)

    def test_iniciar_interfaz_no_duplica_marca_limpia_y_cierra_sonidos(self):
        conectar = object()
        desconectar = object()
        registro = Mock()

        def gui_falsa(**kwargs):
            registro()

        def armar(*a):
            return conectar, desconectar

        with patch.object(main, "armar_callbacks_captura", side_effect=armar), \
                patch.object(main.diagnostico, "registrar_cierre_fallos", registro), \
                patch.object(main._snd, "cerrar") as cerrar:
            main.iniciar_interfaz({}, object(), object(), object(), object(), gui_falsa)

        self.assertEqual(registro.call_count, 1)
        cerrar.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
