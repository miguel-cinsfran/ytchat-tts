"""Tests de extracción de ID de vídeo de YouTube (main.extraer_video_id)."""

import unittest

from main import extraer_video_id


class TestExtraerVideoId(unittest.TestCase):

    ID = "dQw4w9WgXcQ"

    def test_id_pelado(self):
        self.assertEqual(extraer_video_id(self.ID), self.ID)

    def test_id_con_espacios(self):
        self.assertEqual(extraer_video_id(f"  {self.ID}  "), self.ID)

    def test_watch_url(self):
        self.assertEqual(
            extraer_video_id(f"https://www.youtube.com/watch?v={self.ID}"), self.ID)

    def test_watch_url_con_parametros_extra(self):
        self.assertEqual(
            extraer_video_id(f"https://www.youtube.com/watch?v={self.ID}&t=30s"), self.ID)

    def test_youtu_be(self):
        self.assertEqual(extraer_video_id(f"https://youtu.be/{self.ID}"), self.ID)

    def test_youtu_be_con_query(self):
        self.assertEqual(extraer_video_id(f"https://youtu.be/{self.ID}?si=abc"), self.ID)

    def test_live_url(self):
        self.assertEqual(
            extraer_video_id(f"https://www.youtube.com/live/{self.ID}"), self.ID)

    def test_shorts_url(self):
        self.assertEqual(
            extraer_video_id(f"https://www.youtube.com/shorts/{self.ID}"), self.ID)

    def test_embed_url(self):
        self.assertEqual(
            extraer_video_id(f"https://www.youtube.com/embed/{self.ID}"), self.ID)

    def test_sin_esquema(self):
        self.assertEqual(extraer_video_id(f"youtube.com/watch?v={self.ID}"), self.ID)

    def test_entrada_no_reconocible_se_devuelve_tal_cual(self):
        # Si no parece una URL/ID válida, se devuelve la entrada sin tocar
        # (la capa de conexión informará el error de forma amigable).
        self.assertEqual(extraer_video_id("no-es-una-url"), "no-es-una-url")


if __name__ == "__main__":
    unittest.main()
