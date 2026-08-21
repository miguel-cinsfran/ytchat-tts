"""Pruebas de la salida accesible de los registros."""

import logging
import unittest
from unittest import mock

import gui


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


if __name__ == "__main__":
    unittest.main()
