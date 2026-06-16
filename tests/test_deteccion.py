"""Tests de la clasificación de tipo de vídeo (deteccion.py)."""

import unittest

from deteccion import (
    LIVE, UPCOMING, VOD, DESCONOCIDO,
    clasificar_desde_html, clasificar_desde_api, tiene_chat_en_vivo,
)


class TestClasificarHtml(unittest.TestCase):

    def test_vacio(self):
        self.assertEqual(clasificar_desde_html(""), DESCONOCIDO)
        self.assertEqual(clasificar_desde_html(None), DESCONOCIDO)

    def test_directo_en_curso(self):
        html = '...,"isLiveContent":true,"isLive":true,"isUpcoming":false,...'
        self.assertEqual(clasificar_desde_html(html), LIVE)

    def test_directo_por_broadcast(self):
        html = 'algo "liveBroadcastContent":"live" mas'
        self.assertEqual(clasificar_desde_html(html), LIVE)

    def test_programado(self):
        html = '"isLive":false,"isUpcoming":true,"isLiveContent":true'
        self.assertEqual(clasificar_desde_html(html), UPCOMING)

    def test_programado_por_broadcast(self):
        self.assertEqual(
            clasificar_desde_html('"liveBroadcastContent":"upcoming"'), UPCOMING)

    def test_vod_normal(self):
        html = '"isLiveContent":false,"isLive":false,"isUpcoming":false'
        self.assertEqual(clasificar_desde_html(html), VOD)

    def test_directo_terminado_es_vod(self):
        # Fue directo (isLiveContent true) pero ya no emite ni está programado.
        html = '"isLiveContent":true,"isLive":false,"isUpcoming":false'
        self.assertEqual(clasificar_desde_html(html), VOD)

    def test_vod_por_broadcast_none(self):
        self.assertEqual(
            clasificar_desde_html('"liveBroadcastContent":"none"'), VOD)

    def test_sin_senales(self):
        self.assertEqual(clasificar_desde_html("<html>nada util</html>"),
                         DESCONOCIDO)

    def test_directo_gana_a_programado(self):
        html = '"isUpcoming":true,"isLive":true'
        self.assertEqual(clasificar_desde_html(html), LIVE)

    def test_espacios_en_json(self):
        html = '"isLive" : true'
        self.assertEqual(clasificar_desde_html(html), LIVE)


class TestClasificarApi(unittest.TestCase):

    def test_live(self):
        self.assertEqual(clasificar_desde_api("live"), LIVE)

    def test_upcoming(self):
        self.assertEqual(clasificar_desde_api("upcoming"), UPCOMING)

    def test_none_es_vod(self):
        self.assertEqual(clasificar_desde_api("none"), VOD)

    def test_mayusculas_y_espacios(self):
        self.assertEqual(clasificar_desde_api("  LIVE "), LIVE)

    def test_vacio_o_none(self):
        self.assertEqual(clasificar_desde_api(""), DESCONOCIDO)
        self.assertEqual(clasificar_desde_api(None), DESCONOCIDO)
        self.assertEqual(clasificar_desde_api("otra_cosa"), DESCONOCIDO)


class TestTieneChatEnVivo(unittest.TestCase):

    def test_live_y_desconocido_si(self):
        # Desconocido también intenta pytchat: es el comportamiento actual.
        self.assertTrue(tiene_chat_en_vivo(LIVE))
        self.assertTrue(tiene_chat_en_vivo(DESCONOCIDO))

    def test_vod_y_upcoming_no(self):
        self.assertFalse(tiene_chat_en_vivo(VOD))
        self.assertFalse(tiene_chat_en_vivo(UPCOMING))


if __name__ == "__main__":
    unittest.main()
