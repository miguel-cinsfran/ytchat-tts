import unittest

from obs_vigilante import PLAZO_FRESCURA, dato_fresco


class TestFrescura(unittest.TestCase):

    def test_dato_recien_tomado_sirve(self):
        self.assertTrue(dato_fresco(100.0, 100.1))

    def test_dato_justo_en_el_limite_sirve(self):
        self.assertTrue(dato_fresco(100.0, 100.0 + PLAZO_FRESCURA))

    def test_dato_pasado_no_sirve(self):
        self.assertFalse(dato_fresco(100.0, 100.0 + PLAZO_FRESCURA + 0.1))

    def test_sin_sondeo_previo_no_sirve(self):
        self.assertFalse(dato_fresco(None, 100.0))
