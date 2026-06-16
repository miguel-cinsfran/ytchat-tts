"""Tests del parseo de atajos de teclado (config.parsear_atajos)."""

import unittest

from config import _normalizar_atajo, parsear_atajos, ATAJOS_DEFAULTS


class TestNormalizarAtajo(unittest.TestCase):

    def test_none(self):
        self.assertIsNone(_normalizar_atajo(None))

    def test_vacio(self):
        self.assertIsNone(_normalizar_atajo("  "))

    def test_alt_letra(self):
        self.assertEqual(_normalizar_atajo("alt+u"), "alt+u")

    def test_alt_letra_mayuscula_y_espacios(self):
        self.assertEqual(_normalizar_atajo(" ALT + U "), "alt+u")

    def test_fkey(self):
        self.assertEqual(_normalizar_atajo("f5"), "f5")
        self.assertEqual(_normalizar_atajo("F12"), "f12")

    def test_fkey_fuera_de_rango(self):
        self.assertIsNone(_normalizar_atajo("f13"))

    def test_simbolo_permitido(self):
        self.assertEqual(_normalizar_atajo("alt+."), "alt+.")

    def test_modificador_no_soportado(self):
        self.assertIsNone(_normalizar_atajo("ctrl+u"))


class TestParsearAtajos(unittest.TestCase):

    def test_defaults_completos(self):
        atajos = parsear_atajos({})
        # Todas las acciones por defecto quedan resueltas.
        self.assertEqual(set(atajos.keys()), set(ATAJOS_DEFAULTS.keys()))

    def test_desactivar_con_valor_vacio(self):
        atajos = parsear_atajos({"pausa": ""})
        self.assertNotIn("pausa", atajos)

    def test_valor_invalido_cae_al_default(self):
        atajos = parsear_atajos({"pausa": "ctrl+shift+x"})
        # Inválido -> usa el default de pausa (f5).
        self.assertIn("pausa", atajos)
        self.assertEqual(atajos["pausa"].texto, ATAJOS_DEFAULTS["pausa"])

    def test_conflicto_descarta_el_segundo(self):
        # Dos acciones reclamando la misma tecla: la segunda se descarta.
        atajos = parsear_atajos({"url": "alt+z", "conectar": "alt+z"})
        teclas = [a.tecla for a in atajos.values()]
        # 'z' aparece una sola vez.
        self.assertEqual(teclas.count("z"), 1)

    def test_override_valido(self):
        atajos = parsear_atajos({"pausa": "alt+j"})
        self.assertEqual(atajos["pausa"].texto, "alt+j")


if __name__ == "__main__":
    unittest.main()
