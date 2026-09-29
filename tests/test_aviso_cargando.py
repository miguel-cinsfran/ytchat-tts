"""Aviso «Cargando vídeo» mientras el reproductor está cargando.

Mientras un vídeo todavía se está cargando, una flecha o un salto decía
«En este directo no se puede adelantar ni retroceder» o «No se puede mover
este vídeo mientras usa la fuente de internet», información falsa dos
segundos después. Ahora esos rechazos dicen «Cargando vídeo».
"""

import unittest
from unittest import mock

from ytchat.player import reproductor


def _panel(info, url_flujo="", cargando=False):
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._info = info
    panel._url_flujo = url_flujo
    panel._video_id = "D" * 11
    panel._player = mock.Mock()
    panel._cargando = cargando
    panel._ir_a = mock.Mock()
    panel._duracion_actual = mock.Mock(return_value=30000)
    panel._relevo_ffmpeg = None
    panel._relevo_fuentes = None
    panel._usando_cache_local = False
    panel._tiene_esclavo = False
    panel._estado_busqueda = reproductor.EstadoBusqueda(confirmada=0)
    return panel


class PruebasAvisoCargando(unittest.TestCase):

    def test_directo_cargando_avisa_cargando_y_no_busca(self):
        panel = _panel({"is_live": True, "formats": []}, cargando=True)
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._buscar_rel(-10_000)
        anunciar.assert_called_once_with("Cargando vídeo")
        panel._ir_a.assert_not_called()
        panel._player.set_time.assert_not_called()

    def test_directo_sin_cargar_mantiene_frase_vieja(self):
        panel = _panel({"is_live": True, "formats": []}, cargando=False)
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._buscar_rel(-10_000)
        anunciar.assert_called_once_with(
            "En este directo no se puede adelantar ni retroceder")
        panel._ir_a.assert_not_called()

    def test_tiktok_cargando_mantiene_frase_de_tiktok(self):
        panel = _panel({"is_live": True, "formats": []},
                       url_flujo="https://tiktok/flv", cargando=True)
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._buscar_rel(-10_000)
        anunciar.assert_called_once_with(
            "En un directo de TikTok no se puede adelantar ni retroceder")
        panel._ir_a.assert_not_called()

    def test_grabado_sin_permiso_cargando_avisa_cargando(self):
        panel = _panel({}, cargando=True)
        panel._tiene_esclavo = True
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._buscar_rel(-10_000)
        anunciar.assert_called_once_with("Cargando vídeo")
        panel._ir_a.assert_not_called()

    def test_porcentaje_cargando_avisa_cargando(self):
        panel = _panel({"is_live": True, "formats": []}, cargando=True)
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._buscar_porcentaje(50)
        anunciar.assert_called_once_with("Cargando vídeo")
        panel._ir_a.assert_not_called()


if __name__ == "__main__":
    unittest.main()
