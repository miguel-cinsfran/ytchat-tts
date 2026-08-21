"""Pruebas del anuncio de fallos de información de vídeo."""

import unittest
from unittest import mock

import main


class TestAnuncioDeFalloVideo(unittest.TestCase):

    @mock.patch("gui.anunciar")
    def test_anuncia_el_fallo_una_sola_vez(self, anunciar):
        call_after = mock.Mock()
        fallo = "No se pudo consultar la información del vídeo. Inténtalo de nuevo más tarde."

        main._anunciar_fallo_video({"titulo": "", "fallo": fallo}, call_after)

        call_after.assert_called_once_with(anunciar, fallo)
        anunciar.assert_not_called()

    @mock.patch("gui.anunciar")
    def test_no_anuncia_si_no_hay_fallo(self, anunciar):
        call_after = mock.Mock()

        main._anunciar_fallo_video({"titulo": "Vídeo disponible"}, call_after)

        call_after.assert_not_called()
        anunciar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
