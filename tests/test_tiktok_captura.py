"""Tests de la lógica pura de tiktok_captura (detección de URLs y errores)."""

import unittest

from tiktok_captura import (usuario_de_url, _mensaje_error, _es_error_permanente,
                            _mejor_flujo)


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


class TestMejorFlujo(unittest.TestCase):
    """Se prefiere el FLV: el HLS de TikTok suele dar timeout en el reproductor."""

    def test_prefiere_flv_hd_sobre_sd_y_hls(self):
        stream = {"flv_pull_url": {"HD1": "http://x/hd.flv", "SD1": "http://x/sd.flv"},
                  "hls_pull_url": "http://x/i.m3u8"}
        self.assertEqual(_mejor_flujo(stream), "http://x/hd.flv")

    def test_cae_a_sd_si_no_hay_hd(self):
        self.assertEqual(_mejor_flujo({"flv_pull_url": {"SD1": "http://x/sd.flv"}}),
                         "http://x/sd.flv")

    def test_cae_a_hls_si_no_hay_flv(self):
        self.assertEqual(_mejor_flujo({"hls_pull_url": "http://x/i.m3u8"}),
                         "http://x/i.m3u8")

    def test_rtmp_como_ultimo_recurso(self):
        self.assertEqual(_mejor_flujo({"rtmp_pull_url": "http://x/s.flv"}),
                         "http://x/s.flv")

    def test_vacio_si_no_hay_nada(self):
        self.assertEqual(_mejor_flujo({}), "")
        self.assertEqual(_mejor_flujo({"flv_pull_url": {}}), "")


if __name__ == "__main__":
    unittest.main()
