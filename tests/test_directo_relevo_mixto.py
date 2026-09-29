"""Directo de YouTube con HLS mixto va siempre por el relevo.

Un directo a veces entrega solo formatos HLS mixtos (una URL con vídeo y
audio juntos, como el 96 del directo 4xDzrJKXOOY): sin relevo VLC lo
reproduce directo y las flechas caen en destinos sin sentido con la
duración de la ventana. Ahora arranca el relevo con una sola entrada, y si
aun así queda sin relevo las flechas avisan en vez de buscar.
"""

import unittest
from unittest import mock

from ytchat.player import reproductor
from ytchat.player.busqueda_video import busqueda_permitida


def _panel(info, url_flujo=""):
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._info = info
    panel._url_flujo = url_flujo
    panel._video_id = "D" * 11
    panel._player = mock.Mock()
    panel._vol = 75
    panel._muted = False
    panel._timer = mock.Mock()
    panel.lbl_estado = mock.Mock()
    panel._gen = 0
    panel._relevo_gen = 0
    panel._relevo_ffmpeg = None
    panel._relevo_fuentes = None
    panel._relevo_ventana = None
    panel._tiene_esclavo = False
    panel._usando_cache_local = False
    panel._asegurar_player = mock.Mock(return_value=True)
    panel._cancelar_busqueda = mock.Mock()
    panel._detener_relevo_ffmpeg = mock.Mock()
    panel._continuar_reproducir_calidad = mock.Mock()
    panel._error_carga = mock.Mock()
    panel._mostrar_pausa = mock.Mock()
    panel._estado_busqueda = reproductor.EstadoBusqueda(confirmada=0)
    return panel


class PruebasEsHls(unittest.TestCase):

    def test_formato_m3u8_es_hls(self):
        info = {"formats": [
            {"url": "https://x/hls.m3u8", "protocol": "m3u8_native"},
        ]}
        self.assertTrue(reproductor._es_hls(info, "https://x/hls.m3u8"))

    def test_formato_https_no_es_hls(self):
        info = {"formats": [
            {"url": "https://x/video.mp4", "protocol": "https"},
        ]}
        self.assertFalse(reproductor._es_hls(info, "https://x/video.mp4"))

    def test_url_superior_mira_el_protocolo_de_nivel_superior(self):
        info = {"url": "https://x/mixto.m3u8", "protocol": "m3u8_native",
                "formats": []}
        self.assertTrue(reproductor._es_hls(info, "https://x/mixto.m3u8"))
        info2 = {"url": "https://x/mixto.mp4", "protocol": "https",
                 "formats": []}
        self.assertFalse(reproductor._es_hls(info2, "https://x/mixto.mp4"))

    def test_url_desconocida_no_es_hls(self):
        info = {"formats": [
            {"url": "https://x/otro.m3u8", "protocol": "m3u8_native"},
        ]}
        self.assertFalse(reproductor._es_hls(info, "https://x/nada"))


class PruebasCableadoDirectoMixto(unittest.TestCase):

    def test_directo_hls_mixto_arranca_el_relevo_con_audio_vacio(self):
        info = {"is_live": True, "url": "https://x/mixto.m3u8",
                "protocol": "m3u8_native", "formats": [
                    {"url": "https://x/mixto.m3u8", "protocol": "m3u8_native",
                     "vcodec": "avc1", "acodec": "mp4a", "height": 720},
                ]}
        panel = _panel(info)
        with mock.patch.object(panel, "_arrancar_relevo") as arrancar:
            panel._reproducir_calidad(None, True)
        arrancar.assert_called_once_with("https://x/mixto.m3u8", "", True)
        panel._continuar_reproducir_calidad.assert_not_called()
        panel._error_carga.assert_not_called()

    def test_directo_con_pistas_separadas_igual_que_hoy(self):
        info = {"is_live": True, "formats": [
            {"vcodec": "avc1", "acodec": "none", "height": 720,
             "protocol": "m3u8_native", "url": "video-hls"},
            {"vcodec": "none", "acodec": "mp4a",
             "protocol": "m3u8_native", "url": "audio-hls"},
        ]}
        panel = _panel(info)
        with mock.patch.object(panel, "_arrancar_relevo") as arrancar, \
                mock.patch.object(reproductor.relevo_ffmpeg,
                                   "leer_ventana_hls", return_value=None):
            panel._reproducir_calidad(None, True)
        arrancar.assert_called_once_with("video-hls", "audio-hls", True)
        panel._continuar_reproducir_calidad.assert_not_called()

    def test_directo_no_hls_sin_slave_igual_que_hoy(self):
        info = {"is_live": True, "url": "https://x/video.mp4",
                "protocol": "https", "formats": []}
        panel = _panel(info)
        with mock.patch.object(panel, "_arrancar_relevo") as arrancar:
            panel._reproducir_calidad(None, True)
        arrancar.assert_not_called()
        panel._continuar_reproducir_calidad.assert_called_once()


class PruebasDirectoSinRelevo(unittest.TestCase):

    def test_busqueda_en_directo_sin_relevo_no_permitida(self):
        self.assertFalse(busqueda_permitida(True, False, False, False))

    def _panel_sin_relevo(self, url_flujo=""):
        info = {"is_live": True, "formats": []}
        panel = _panel(info, url_flujo=url_flujo)
        panel._ir_a = mock.Mock()
        panel._duracion_actual = mock.Mock(return_value=30000)
        return panel

    def test_buscar_rel_en_directo_youtube_avisa_y_no_busca(self):
        panel = self._panel_sin_relevo()
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._buscar_rel(-10_000)
        anunciar.assert_called_once_with(
            "En este directo no se puede adelantar ni retroceder")
        panel._ir_a.assert_not_called()
        panel._player.set_time.assert_not_called()

    def test_buscar_rel_en_tiktok_dice_la_frase_de_tiktok(self):
        panel = self._panel_sin_relevo(url_flujo="https://tiktok/flv")
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._buscar_rel(-10_000)
        anunciar.assert_called_once_with(
            "En un directo de TikTok no se puede adelantar ni retroceder")
        panel._ir_a.assert_not_called()
        panel._player.set_time.assert_not_called()


if __name__ == "__main__":
    unittest.main()
