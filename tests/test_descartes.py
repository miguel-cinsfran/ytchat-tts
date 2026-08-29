import unittest

import descartes


class TestAviso(unittest.TestCase):

    def test_no_avisa_antes_del_umbral(self):
        self.assertFalse(descartes.hay_que_avisar(2, False))

    def test_avisa_al_llegar_al_umbral(self):
        self.assertTrue(descartes.hay_que_avisar(3, False))

    def test_no_avisa_dos_veces_en_la_misma_sesion(self):
        self.assertFalse(descartes.hay_que_avisar(10, True))

    def test_acepta_un_umbral_distinto(self):
        self.assertTrue(descartes.hay_que_avisar(2, False, umbral=2))


class TestFrases(unittest.TestCase):

    def test_aviso_invita_a_activar_solo_el_nombre_si_esta_apagado(self):
        texto = descartes.frase_aviso(0)
        self.assertIn("retraso", texto)
        self.assertIn("descartando mensajes", texto)
        self.assertIn("lista del chat", texto)
        self.assertIn("Preferencias", texto)

    def test_aviso_no_repite_la_opcion_si_ya_esta_activa(self):
        texto = descartes.frase_aviso(5)
        self.assertIn("lista del chat", texto)
        self.assertNotIn("Preferencias", texto)

    def test_estado_vacio_si_no_hubo_descartes(self):
        self.assertEqual(descartes.frase_estado(0), "")

    def test_estado_muestra_el_numero_de_descartes(self):
        self.assertEqual(descartes.frase_estado(12), "Mensajes descartados: 12")


if __name__ == "__main__":
    unittest.main()
