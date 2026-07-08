"""Tests de la lógica pura de tiktok_captura (detección de URLs y errores)."""

import unittest

from tiktok_captura import usuario_de_url, _mensaje_error, _es_error_permanente


class TestUsuarioDeUrl(unittest.TestCase):

    def test_url_live_completa(self):
        self.assertEqual(
            usuario_de_url("https://www.tiktok.com/@tv_asahi_news/live"),
            "tv_asahi_news")

    def test_url_sin_live(self):
        self.assertEqual(
            usuario_de_url("https://www.tiktok.com/@usuario.x"), "usuario.x")

    def test_url_sin_esquema_ni_www(self):
        self.assertEqual(usuario_de_url("tiktok.com/@pepe/live"), "pepe")

    def test_url_movil(self):
        self.assertEqual(usuario_de_url("https://m.tiktok.com/@pepe/live"), "pepe")

    def test_con_query(self):
        self.assertEqual(
            usuario_de_url("https://www.tiktok.com/@pepe/live?lang=es"), "pepe")

    def test_usuario_suelto_no_vale(self):
        # Un "@usuario" sin dominio chocaría con los handles de YouTube.
        self.assertEqual(usuario_de_url("@pepe"), "")

    def test_youtube_no_es_tiktok(self):
        self.assertEqual(usuario_de_url("https://www.youtube.com/watch?v=abc"), "")
        self.assertEqual(usuario_de_url("https://youtu.be/dQw4w9WgXcQ"), "")

    def test_vacio_y_basura(self):
        self.assertEqual(usuario_de_url(""), "")
        self.assertEqual(usuario_de_url("   "), "")
        self.assertEqual(usuario_de_url("cualquier cosa"), "")

    def test_dominio_parecido_no_vale(self):
        self.assertEqual(usuario_de_url("https://notiktok.com/@pepe/live"), "")


class TestMensajesDeError(unittest.TestCase):

    def _exc(self, nombre, texto=""):
        return type(nombre, (Exception,), {})(texto)

    def test_offline_es_permanente_y_amigable(self):
        exc = self._exc("UserOfflineError", "user is offline")
        self.assertTrue(_es_error_permanente(exc))
        self.assertIn("no está en directo", _mensaje_error(exc))

    def test_usuario_inexistente(self):
        exc = self._exc("UserNotFoundError", "user not found")
        self.assertTrue(_es_error_permanente(exc))
        self.assertIn("No se encontró", _mensaje_error(exc))

    def test_error_generico_no_es_permanente(self):
        exc = Exception("connection reset by peer")
        self.assertFalse(_es_error_permanente(exc))
        self.assertIn("No se pudo conectar", _mensaje_error(exc))

    def test_error_de_firma(self):
        exc = self._exc("SignAPIError", "sign server unavailable")
        self.assertFalse(_es_error_permanente(exc))
        self.assertIn("firmas", _mensaje_error(exc))


if __name__ == "__main__":
    unittest.main()
