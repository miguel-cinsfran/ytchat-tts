import unittest

from obs_audio import elegir_microfono, frase_microfono


class ElegirMicrofonoTest(unittest.TestCase):
    def test_prefiere_el_nombre_guardado(self):
        self.assertEqual(elegir_microfono(("Mic/Aux", "Otro"), "Otro"), "Otro")

    def test_el_preferido_gana_a_una_fuente_con_mic(self):
        self.assertEqual(elegir_microfono(("Mic/Aux", "Audio USB"), "Audio USB"),
                         "Audio USB")

    def test_elije_la_primera_fuente_con_mic_sin_tildes(self):
        self.assertEqual(elegir_microfono(
            ("Audio del escritorio", "Mícrofono USB"), ""), "Mícrofono USB")

    def test_usa_la_primera_fuente_si_no_hay_microfono(self):
        self.assertEqual(elegir_microfono(("Audio del escritorio", "Auxiliar"), ""),
                         "Audio del escritorio")

    def test_devuelve_vacio_sin_fuentes(self):
        self.assertEqual(elegir_microfono((), "Mic/Aux"), "")


class FraseMicrofonoTest(unittest.TestCase):
    def test_anuncia_microfono_silenciado(self):
        self.assertEqual(frase_microfono("Mic/Aux", True), "Micrófono silenciado")

    def test_anuncia_microfono_activado(self):
        self.assertEqual(frase_microfono("Mic/Aux", False), "Micrófono activado")

    def test_nombra_la_fuente_que_no_es_microfono(self):
        self.assertEqual(frase_microfono("Audio del escritorio", True),
                         "Audio del escritorio silenciado")

    def test_anuncia_la_ausencia_de_fuentes(self):
        self.assertEqual(frase_microfono("", False),
                         "OBS no tiene ninguna fuente de audio")


if __name__ == "__main__":
    unittest.main()
