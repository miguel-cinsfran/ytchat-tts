"""Pruebas de la consulta de información de vídeos."""

import sys
import types
import unittest
from unittest import mock

import main


class _YoutubeDL:
    def __init__(self, opciones):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, *args, **kwargs):
        return {"title": "Vídeo de prueba", "live_status": "not_live"}


class TestObtenerInfoVideo(unittest.TestCase):

    def test_fallo_de_los_dos_caminos_va_a_los_metadatos(self):
        modulo = types.SimpleNamespace(YoutubeDL=mock.Mock(side_effect=RuntimeError(
            "Sign in to confirm you're not a bot")))

        def falla_watch(video_id, timeout=8.0, al_fallar=None):
            al_fallar(RuntimeError("HTTP Error 429: Too Many Requests"))
            return ""

        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main, "_descargar_watch", side_effect=falla_watch):
            titulo, tipo, metadatos = main.obtener_info_video("A" * 11)

        self.assertEqual((titulo, tipo), ("", main.deteccion.DESCONOCIDO))
        self.assertEqual(
            metadatos["fallo"],
            "El servicio está recibiendo demasiadas solicitudes. "
            "Vuelve a intentarlo en unos minutos.")

    def test_consulta_exitosa_no_agrega_fallo(self):
        modulo = types.SimpleNamespace(YoutubeDL=_YoutubeDL)
        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main, "_descargar_watch") as respaldo:
            titulo, tipo, metadatos = main.obtener_info_video("A" * 11)

        self.assertEqual(titulo, "Vídeo de prueba")
        self.assertEqual(tipo, main.deteccion.VOD)
        self.assertNotIn("fallo", metadatos)
        respaldo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
