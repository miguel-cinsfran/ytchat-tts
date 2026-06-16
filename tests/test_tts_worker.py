"""Tests de la lógica pura de tts_worker (sanitización, formato, rate)."""

import unittest

from tts_worker import sanitizar, construir_tts, _wpm_a_rate


class TestSanitizar(unittest.TestCase):

    def test_vacio(self):
        self.assertEqual(sanitizar("", True, True, 200), "")

    def test_colapsa_espacios(self):
        self.assertEqual(sanitizar("hola    mundo", True, True, 200), "hola mundo")

    def test_elimina_urls(self):
        self.assertEqual(
            sanitizar("mira esto http://example.com/x ya", True, True, 200),
            "mira esto ya")

    def test_conserva_urls_si_se_pide(self):
        out = sanitizar("ve a http://example.com", True, False, 200)
        self.assertIn("http://example.com", out)

    def test_elimina_emojis(self):
        self.assertEqual(sanitizar("hola 😀🎉 mundo", True, True, 200), "hola mundo")

    def test_conserva_emojis_si_se_pide(self):
        out = sanitizar("hola 😀 mundo", False, True, 200)
        self.assertIn("😀", out)

    def test_elimina_caracteres_de_control(self):
        self.assertEqual(sanitizar("a\x00b\x07c", True, True, 200), "abc")

    def test_truncado_por_palabra(self):
        texto = "palabra " * 50  # 400 chars aprox
        out = sanitizar(texto.strip(), True, True, 40)
        self.assertTrue(out.endswith("..."))
        self.assertLessEqual(len(out), 43)

    def test_sin_truncado_si_maxlen_cero(self):
        texto = "x" * 500
        self.assertEqual(sanitizar(texto, True, True, 0), texto)


class TestConstruirTTS(unittest.TestCase):

    def _cfg(self, fmt="nombre_mensaje"):
        return {"limpiar_emojis": True, "formato_prefijo": fmt}

    def test_nombre_mensaje(self):
        self.assertEqual(construir_tts("Juan", "hola", self._cfg()), "Juan: hola")

    def test_solo_mensaje(self):
        self.assertEqual(
            construir_tts("Juan", "hola", self._cfg("solo_mensaje")), "hola")

    def test_solo_nombre(self):
        self.assertEqual(
            construir_tts("Juan", "hola", self._cfg("solo_nombre")), "Juan")

    def test_autor_vacio_usa_placeholder(self):
        self.assertEqual(construir_tts("", "hola", self._cfg()), "Usuario: hola")


class TestWpmARate(unittest.TestCase):

    def test_valor_neutro(self):
        self.assertEqual(_wpm_a_rate(180), 0)

    def test_limite_inferior(self):
        # El rate SAPI5 nunca baja de -10 por mucho que se reduzca el wpm.
        self.assertEqual(_wpm_a_rate(-100), -10)

    def test_limite_superior(self):
        self.assertEqual(_wpm_a_rate(10000), 10)

    def test_rapido(self):
        self.assertEqual(_wpm_a_rate(220), 2)


if __name__ == "__main__":
    unittest.main()
