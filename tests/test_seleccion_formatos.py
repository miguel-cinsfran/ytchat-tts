"""Selección de formatos para el VOD por relevo.

El relevo de ffmpeg no tolera audio HLS por TCP, así que el VOD evita las
pistas m3u8 cuando hay alternativas normales. El directo no cambia.
"""

import unittest

from ytchat.player import reproductor


def _audio(fid, protocolo, abr, lang, url=None):
    return {"format_id": fid, "protocol": protocolo, "acodec": "mp4a",
            "vcodec": "none", "abr": abr, "language_preference": lang,
            "url": url or f"https://{fid}"}


class PruebasMejorAudioSinHls(unittest.TestCase):
    def _info_j906(self):
        return {"formats": [
            _audio("233", "m3u8_native", 48, None),
            _audio("234", "m3u8_native", 120, None),
            _audio("140", "https", 128, -1),
            _audio("251", "https", 160, -1),
        ]}

    def test_evitando_hls_elige_251(self):
        url = reproductor._mejor_audio(self._info_j906(), evitar_hls=True)
        self.assertEqual(url, "https://251")

    def test_sin_evitando_hls_elige_una_hls_como_hoy(self):
        url = reproductor._mejor_audio(self._info_j906())
        self.assertIn(url, ("https://233", "https://234"))

    def test_doblaje_gana_la_original_aunque_tenga_menos_bitrate(self):
        info = {"formats": [
            _audio("dub", "https", 200, -1),
            _audio("orig", "https", 128, 10),
        ]}
        url = reproductor._mejor_audio(info, evitar_hls=True)
        self.assertEqual(url, "https://orig")

    def test_solo_hls_devuelve_una_hls(self):
        info = {"formats": [
            _audio("233", "m3u8_native", 48, None),
            _audio("234", "m3u8_native", 120, None),
        ]}
        url = reproductor._mejor_audio(info, evitar_hls=True)
        self.assertIn(url, ("https://233", "https://234"))


class PruebasVideoParaAlturaSinHls(unittest.TestCase):
    def test_a_720_prefiere_136_https_antes_que_232_hls(self):
        info = {"formats": [
            {"format_id": "232", "protocol": "m3u8_native", "vcodec": "avc",
             "acodec": "none", "height": 720, "tbr": 3000,
             "url": "https://232"},
            {"format_id": "136", "protocol": "https", "vcodec": "avc",
             "acodec": "none", "height": 720, "tbr": 1500,
             "url": "https://136"},
        ]}
        url, prog = reproductor._video_para_altura(info, 720)
        self.assertEqual(url, "https://136")
        self.assertFalse(prog)


if __name__ == "__main__":
    unittest.main()
