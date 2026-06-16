"""Tests de helpers de captura de main: errores, cola y filtros."""

import queue
import unittest

from main import (
    _mensaje_error_amigable, _es_error_permanente,
    encolar, permitido, debe_leer_tts, Stats,
)


class TestErrores(unittest.TestCase):

    def test_id_invalido(self):
        self.assertIn("no es válido", _mensaje_error_amigable("Invalid video id"))

    def test_privado(self):
        self.assertIn("privado", _mensaje_error_amigable("This live is private"))

    def test_miembros(self):
        self.assertIn("miembros", _mensaje_error_amigable("members only chat"))

    def test_generico(self):
        self.assertIn("No se pudo conectar", _mensaje_error_amigable("kaboom"))

    def test_es_permanente(self):
        self.assertTrue(_es_error_permanente("Invalid video id"))
        self.assertTrue(_es_error_permanente("members only"))

    def test_no_es_permanente(self):
        self.assertFalse(_es_error_permanente("timeout temporal de red"))


class TestEncolar(unittest.TestCase):

    def test_estrategia_todas_no_descarta(self):
        cola = queue.Queue()
        stats = Stats()
        cfg = {"estrategia": "todas", "tamanio_maximo": 2}
        for i in range(5):
            encolar(cola, {"texto_tts": str(i)}, cfg, stats)
        self.assertEqual(cola.qsize(), 5)
        self.assertEqual(stats.descartados, 0)

    def test_estrategia_limite_descarta_viejos(self):
        cola = queue.Queue()
        stats = Stats()
        cfg = {"estrategia": "limite", "tamanio_maximo": 2}
        for i in range(5):
            encolar(cola, {"texto_tts": str(i)}, cfg, stats)
        self.assertLessEqual(cola.qsize(), 2)
        self.assertGreater(stats.descartados, 0)


class TestFiltros(unittest.TestCase):

    def _cfg(self, **kw):
        base = {
            "usuarios_silenciados": [],
            "palabras_silenciadas": [],
            "silenciados_ocultar": set(),
            "silenciados_runtime": set(),
            "silenciar_lectura": False,
        }
        base.update(kw)
        return base

    def test_permitido_normal(self):
        self.assertTrue(permitido("Ana", "hola", self._cfg()))

    def test_usuario_silenciado_parcial(self):
        self.assertFalse(
            permitido("SpamBot99", "hola", self._cfg(usuarios_silenciados=["spambot"])))

    def test_palabra_silenciada(self):
        self.assertFalse(
            permitido("Ana", "compra ya en MiWeb", self._cfg(palabras_silenciadas=["miweb"])))

    def test_oculto_runtime(self):
        self.assertFalse(
            permitido("Ana", "hola", self._cfg(silenciados_ocultar={"ana"})))

    def test_debe_leer_tts_silencio_global(self):
        self.assertFalse(debe_leer_tts("Ana", self._cfg(silenciar_lectura=True)))

    def test_debe_leer_tts_silenciado_individual(self):
        self.assertFalse(
            debe_leer_tts("Ana", self._cfg(silenciados_runtime={"ana"})))

    def test_debe_leer_tts_normal(self):
        self.assertTrue(debe_leer_tts("Ana", self._cfg()))


if __name__ == "__main__":
    unittest.main()
