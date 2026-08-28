"""Pruebas de los avisos periódicos de espera."""

import unittest

from progreso import aviso_de_espera


class TestAvisoDeEspera(unittest.TestCase):

    def test_antes_del_umbral_no_dice_nada(self):
        self.assertEqual(aviso_de_espera(1.9, None), "")

    def test_en_el_umbral_avisa(self):
        self.assertEqual(aviso_de_espera(2, None),
                         "Buscando el vídeo, 2 segundos")

    def test_entre_avisos_no_repite(self):
        self.assertEqual(aviso_de_espera(4, 2), "")

    def test_pasada_la_cadencia_vuelve_a_avisar(self):
        self.assertEqual(aviso_de_espera(5, 2),
                         "Buscando el vídeo, 5 segundos")

    def test_al_cruzar_veinte_segundos_cambia_la_frase(self):
        self.assertEqual(
            aviso_de_espera(20, 17),
            "Sigue buscando el vídeo, 20 segundos. Está tardando más de lo normal.")

    def test_los_segundos_son_enteros_y_nunca_negativos(self):
        self.assertEqual(aviso_de_espera(-2.7, None), "")
        self.assertEqual(aviso_de_espera(2.9, None),
                         "Buscando el vídeo, 2 segundos")


if __name__ == "__main__":
    unittest.main()
