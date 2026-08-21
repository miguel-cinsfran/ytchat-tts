"""Pruebas de la salida accesible de los registros."""

import logging
import unittest
from unittest import mock

import gui


class GrabadorDeVoz:
    """Ocupa el lugar del lector de pantalla y anota lo que se le diría."""

    def __init__(self):
        self.hablado = []
        self.brailleado = []

    def speak(self, texto, interrupt=None):
        self.hablado.append(texto)

    def braille(self, texto):
        self.brailleado.append(texto)


class TestRegistroEsAnunciable(unittest.TestCase):

    def test_descarta_diagnostico_y_sus_hijos(self):
        self.assertFalse(gui.registro_es_anunciable("diagnostico"))
        self.assertFalse(gui.registro_es_anunciable("diagnostico.hilos"))

    def test_no_descarta_nombres_parecidos(self):
        self.assertTrue(gui.registro_es_anunciable("diagnosticador"))

    def test_anuncia_el_resto_y_nombres_vacios(self):
        self.assertTrue(gui.registro_es_anunciable("aplicacion"))
        self.assertTrue(gui.registro_es_anunciable(""))
        self.assertTrue(gui.registro_es_anunciable(None))

    def test_manejador_consulta_el_nombre_del_registro(self):
        manejador = gui.WxAnnouncingHandler()
        registro = logging.LogRecord(
            "diagnostico.hilos", logging.INFO, __file__, 1, "oculto", (), None)
        with mock.patch.object(gui, "registro_es_anunciable", return_value=False) as decidir:
            with mock.patch.object(gui, "anunciar") as anunciar:
                manejador.emit(registro)
        decidir.assert_called_once_with("diagnostico.hilos")
        anunciar.assert_not_called()

    def test_anunciar_envia_el_texto_completo(self):
        grabador = GrabadorDeVoz()
        with mock.patch.object(gui, "_ao2", grabador):
            gui.anunciar("hola")

        self.assertEqual(grabador.hablado, ["hola"])
        self.assertEqual(grabador.brailleado, ["hola"])

    def test_manejador_omite_diagnostico_sin_parchear_anunciar(self):
        grabador = GrabadorDeVoz()
        registro = logging.LogRecord(
            "diagnostico.hilos", logging.INFO, __file__, 1, "oculto", (), None)
        with mock.patch.object(gui, "_ao2", grabador):
            gui.WxAnnouncingHandler().emit(registro)

        self.assertEqual(grabador.hablado, [])
        self.assertEqual(grabador.brailleado, [])

    def test_manejador_anuncia_mensaje_de_aplicacion(self):
        grabador = GrabadorDeVoz()
        registro = logging.LogRecord(
            "aplicacion", logging.INFO, __file__, 1, "conectado", (), None)
        with mock.patch.object(gui, "_ao2", grabador):
            gui.WxAnnouncingHandler().emit(registro)

        self.assertEqual(grabador.hablado, ["conectado"])


class _BarraDeMenu:

    def __init__(self):
        self.llamadas = []

    def EnableTop(self, *args):
        self.llamadas.append(args)


class _ControlMenu:

    def Enable(self, habilitado):
        pass


class TestMenusPorConexion(unittest.TestCase):

    def test_no_apaga_menu_reproductor_sin_conexion(self):
        frame = mock.Mock()
        frame._conectado = False
        frame._mi_ver_conexion = []
        frame._mi_voz_conexion = []
        frame._mi_filtro_sub = _ControlMenu()
        frame._es_tiktok = False
        frame._rep_panel = None
        frame.mi_descargar_este = _ControlMenu()
        barra = _BarraDeMenu()
        frame.GetMenuBar.return_value = barra

        gui.YTChatFrame._actualizar_menus_por_conexion(frame)

        self.assertEqual(barra.llamadas, [])


if __name__ == "__main__":
    unittest.main()
