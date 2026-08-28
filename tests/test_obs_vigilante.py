import unittest

from obs_vigilante import EstadoObs, PLAZO_FRESCURA, VigilanteObs, dato_fresco


class TestFrescura(unittest.TestCase):

    def test_dato_recien_tomado_sirve(self):
        self.assertTrue(dato_fresco(100.0, 100.1))

    def test_dato_justo_en_el_limite_sirve(self):
        self.assertTrue(dato_fresco(100.0, 100.0 + PLAZO_FRESCURA))

    def test_dato_pasado_no_sirve(self):
        self.assertFalse(dato_fresco(100.0, 100.0 + PLAZO_FRESCURA + 0.1))

    def test_sin_sondeo_previo_no_sirve(self):
        self.assertFalse(dato_fresco(None, 100.0))

    def test_estado_con_sondeo_reciente_devuelve_estado_guardado(self):
        vigilante = VigilanteObs()
        vigilante._estado = EstadoObs(escena="Escena actual")
        vigilante._ultimo_sondeo = 100.0

        self.assertEqual(vigilante.estado(100.1), vigilante._estado)

    def test_estado_con_sondeo_caducado_devuelve_none(self):
        vigilante = VigilanteObs()
        vigilante._estado = EstadoObs(escena="Escena vieja")
        vigilante._ultimo_sondeo = 100.0

        self.assertIsNone(vigilante.estado(100.0 + PLAZO_FRESCURA + 0.1))
