"""Pruebas de los avisos de carga del reproductor."""

import unittest
from unittest import mock

import reproductor


class TestCargaReproductor(unittest.TestCase):

    def _panel(self, video_id, cargando):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = video_id
        panel._cargando = cargando
        panel._asegurar_player = mock.Mock(return_value=True)
        return panel

    @mock.patch.object(reproductor, "anunciar")
    def test_segunda_pulsacion_anuncia_que_sigue_cargando(self, anunciar):
        panel = self._panel("A" * 11, True)

        panel.cargar()

        anunciar.assert_called_once_with("Cargando vídeo")

    @mock.patch.object(reproductor, "anunciar")
    def test_sin_video_sigue_sin_anunciar(self, anunciar):
        panel = self._panel("", False)

        panel.cargar()

        anunciar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
