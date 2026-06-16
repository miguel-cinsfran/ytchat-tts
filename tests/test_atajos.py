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

    def test_ctrl_letra(self):
        self.assertEqual(_normalizar_atajo("ctrl+d"), "ctrl+d")

    def test_teclas_con_nombre(self):
        self.assertEqual(_normalizar_atajo("ctrl+left"), "ctrl+left")
        self.assertEqual(_normalizar_atajo("alt+enter"), "alt+enter")
        self.assertEqual(_normalizar_atajo("ctrl+up"), "ctrl+up")

    def test_modificador_no_soportado(self):
        # Shift y combinaciones multi-modificador no se admiten en el editor.
        self.assertIsNone(_normalizar_atajo("shift+u"))
        self.assertIsNone(_normalizar_atajo("ctrl+shift+x"))

    def test_tecla_nombre_desconocida(self):
        self.assertIsNone(_normalizar_atajo("ctrl+home"))


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
        atajos = parsear_atajos({"pausa": "f3", "detener_tts": "f3"})
        teclas = [a.tecla for a in atajos.values()]
        # 'f3' aparece una sola vez.
        self.assertEqual(teclas.count("f3"), 1)

    def test_override_valido(self):
        atajos = parsear_atajos({"pausa": "alt+j"})
        self.assertEqual(atajos["pausa"].texto, "alt+j")

    def test_ctrl_y_alt_misma_letra_no_chocan(self):
        # 'ctrl+d' (rep_detener) y 'alt+d' (desconectar) conviven.
        atajos = parsear_atajos({})
        self.assertEqual(atajos["rep_detener"].texto, "ctrl+d")
        self.assertEqual(atajos["desconectar"].texto, "alt+d")


if __name__ == "__main__":
    unittest.main()
