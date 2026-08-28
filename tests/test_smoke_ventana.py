"""Pruebas de identificación segura de la ventana del smoke."""

import unittest

from smoke_test import ventana_es_de_la_aplicacion


class VentanaEsDeLaAplicacionTest(unittest.TestCase):

    def test_acepta_titulo_y_python(self):
        self.assertTrue(ventana_es_de_la_aplicacion("YTChat TTS", "python.exe"))

    def test_rechaza_explorador_con_titulo_correcto(self):
        self.assertFalse(ventana_es_de_la_aplicacion(
            "YTChat TTS - para probar", "explorer.exe"))

    def test_rechaza_titulo_distinto_con_proceso_correcto(self):
        self.assertFalse(ventana_es_de_la_aplicacion("Otra ventana", "python.exe"))

    def test_compara_el_proceso_sin_mayusculas(self):
        self.assertTrue(ventana_es_de_la_aplicacion("YTChat TTS", "PYTHONW.EXE"))
