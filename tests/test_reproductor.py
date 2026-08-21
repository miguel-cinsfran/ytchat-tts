"""Pruebas de los avisos de los controles del reproductor."""

import unittest
from unittest import mock
import types
import sys

import reproductor


class _YoutubeDL:
    def __init__(self, opciones):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, *args, **kwargs):
        return {"formats": [{"vcodec": "avc1", "height": 720}]}


class TestInfoVideo(unittest.TestCase):

    def test_info_video_con_programa_no_importa_el_modulo(self):
        info = {"formats": [{"vcodec": "avc1", "height": 1080}]}
        with mock.patch.object(reproductor.ytdlp_bin, "info_video", return_value=info), \
                mock.patch.dict(sys.modules, {"yt_dlp": None}):
            self.assertIs(info, reproductor._info_video("A" * 11))

    def test_info_video_sin_programa_usa_el_modulo(self):
        modulo = types.SimpleNamespace(YoutubeDL=_YoutubeDL)
        with mock.patch.object(reproductor.ytdlp_bin, "info_video", return_value=None), \
                mock.patch.dict(sys.modules, {"yt_dlp": modulo}):
            self.assertEqual(
                {"formats": [{"vcodec": "avc1", "height": 720}]},
                reproductor._info_video("A" * 11),
            )


class TestAvisoReproductor(unittest.TestCase):

    def test_sin_reproductor(self):
        self.assertEqual(
            reproductor.aviso_reproductor(False, False),
            "El reproductor no está disponible")

    def test_reproductor_sin_medio(self):
        self.assertEqual(
            reproductor.aviso_reproductor(True, False),
            "No hay ningún vídeo cargado")

    def test_reproductor_con_medio(self):
        self.assertEqual(reproductor.aviso_reproductor(True, True), "")


class TestAvisoAlReproducir(unittest.TestCase):

    def test_reproducir_sin_medio_anuncia(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = ""
        panel._url_flujo = ""
        panel._asegurar_player = lambda: True
        panel._player = mock.Mock()
        panel._player.get_state.return_value = object()

        estados = mock.Mock(Playing=object(), Paused=object())
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch.object(reproductor, "_vlc", State=estados):
            panel._toggle_play()

        anunciar.assert_called_once_with("No hay ningún vídeo cargado")

    def _panel_sin_medio(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = ""
        panel._url_flujo = ""
        panel._player = None
        return panel

    def test_silenciar_sin_medio_anuncia(self):
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            self._panel_sin_medio()._toggle_mute()
        anunciar.assert_called_once_with("No hay ningún vídeo cargado")

    def test_silenciar_sin_reproductor_anuncia_indisponible(self):
        panel = self._panel_sin_medio()
        panel._listo = False
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._toggle_mute()
        anunciar.assert_called_once_with("El reproductor no está disponible")

    def test_buscar_sin_medio_anuncia(self):
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            self._panel_sin_medio()._buscar_rel(10_000)
        anunciar.assert_called_once_with("No hay ningún vídeo cargado")

    def test_pantalla_completa_sin_reproductor_anuncia(self):
        panel = self._panel_sin_medio()
        panel._listo = False
        panel._asegurar_player = lambda: False
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel.alternar_pantalla_completa()
        anunciar.assert_called_once_with("El reproductor no está disponible")

    def test_reproducir_sin_reproductor_anuncia(self):
        panel = self._panel_sin_medio()
        panel._listo = False
        panel._asegurar_player = lambda: False
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._toggle_play()
        anunciar.assert_called_once_with("El reproductor no está disponible")

    def test_reproducir_con_medio_no_anuncia_falta_de_medio(self):
        panel = self._panel_sin_medio()
        panel._video_id = "video-cargado"
        panel._asegurar_player = lambda: False
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._toggle_play()
        anunciar.assert_not_called()

        panel._video_id = ""
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._toggle_play()
        anunciar.assert_called_once_with("No hay ningún vídeo cargado")

    def test_reproducir_con_flujo_no_anuncia_falta_de_medio(self):
        panel = self._panel_sin_medio()
        panel._url_flujo = "https://flujo.example/stream"
        panel._asegurar_player = lambda: False
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._toggle_play()
        anunciar.assert_not_called()

if __name__ == "__main__":
    unittest.main()
