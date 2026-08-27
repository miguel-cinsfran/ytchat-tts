"""Pruebas de las decisiones del ajuste fino."""

import unittest

import ajuste_fino


class TestAjusteFino(unittest.TestCase):

    def test_flecha_izquierda_mueve_a_la_izquierda(self):
        self.assertEqual(ajuste_fino.resolver(314, False, False), ("mover", -10, 0))

    def test_flecha_derecha_mueve_a_la_derecha(self):
        self.assertEqual(ajuste_fino.resolver(316, False, False), ("mover", 10, 0))

    def test_flecha_arriba_mueve_hacia_arriba(self):
        self.assertEqual(ajuste_fino.resolver(315, False, False), ("mover", 0, -10))

    def test_flecha_abajo_mueve_hacia_abajo(self):
        self.assertEqual(ajuste_fino.resolver(317, False, False), ("mover", 0, 10))

    def test_control_usa_paso_grande(self):
        self.assertEqual(ajuste_fino.resolver(316, True, False), ("mover", 50, 0))

    def test_mayusculas_usa_paso_fino(self):
        self.assertEqual(ajuste_fino.resolver(316, False, True), ("mover", 1, 0))

    def test_control_manda_sobre_mayusculas(self):
        self.assertEqual(ajuste_fino.resolver(316, True, True), ("mover", 50, 0))

    def test_intro_confirma(self):
        self.assertEqual(ajuste_fino.resolver(13, False, False), ("confirmar", 0, 0))

    def test_escape_cancela(self):
        self.assertEqual(ajuste_fino.resolver(27, False, False), ("cancelar", 0, 0))

    def test_tab_sale(self):
        self.assertEqual(ajuste_fino.resolver(9, False, False), ("salir", 0, 0))

    def test_otra_tecla_se_ignora(self):
        self.assertEqual(ajuste_fino.resolver(ord("A"), False, False), ("ignorar", 0, 0))

    def test_etiqueta_activa(self):
        self.assertEqual(ajuste_fino.etiqueta_boton(True, "Ajuste &fino"),
                         "Ajustando, flechas para mover")

    def test_etiqueta_inactiva(self):
        self.assertEqual(ajuste_fino.etiqueta_boton(False, "Ajuste &fino"),
                         "Ajuste &fino")

    def test_texto_de_entrada(self):
        self.assertEqual(ajuste_fino.texto_de_entrada(),
                         "Ajuste fino. Flechas para mover, Control para pasos grandes, "
                         "Mayúsculas para pasos de un píxel. Intro confirma, Escape deshace, "
                         "Tab sale.")


if __name__ == "__main__":
    unittest.main()
