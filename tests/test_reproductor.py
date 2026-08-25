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


class TestPrecalentamiento(unittest.TestCase):

    def _panel(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._precalentamiento_cancelado = False
        return panel

    def test_anuncia_antes_del_trabajo_y_al_terminar(self):
        panel = self._panel()
        orden = []
        hilo = mock.Mock()

        def crear(target, _nombre):
            hilo.target = target
            return hilo

        def iniciar():
            hilo.target()

        hilo.start.side_effect = iniciar
        panel._asegurar_instancia = lambda: orden.append("trabajo") or True
        with mock.patch.object(reproductor, "anunciar",
                               side_effect=lambda texto: orden.append(texto)), \
                mock.patch.object(reproductor.diagnostico, "crear_hilo",
                                  side_effect=crear), \
                mock.patch.object(reproductor.wx, "CallAfter",
                                  side_effect=lambda fn: fn()):
            panel._precalentar()

        self.assertEqual(orden, [
            "Preparando el reproductor", "trabajo", "Reproductor listo"])

    def test_si_falla_no_anuncia_que_esta_listo(self):
        panel = self._panel()
        hilo = mock.Mock()
        def crear(target, _nombre):
            hilo.target = target
            return hilo
        hilo.start.side_effect = lambda: hilo.target()
        panel._asegurar_instancia = mock.Mock(side_effect=RuntimeError("fallo"))
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch.object(reproductor.diagnostico, "crear_hilo",
                                  side_effect=crear):
            panel._precalentar()

        anunciar.assert_called_once_with("Preparando el reproductor")

    def test_si_se_cierra_no_anuncia_que_esta_listo(self):
        panel = self._panel()
        callbacks = []
        hilo = mock.Mock()
        def crear(target, _nombre):
            hilo.target = target
            return hilo
        hilo.start.side_effect = lambda: hilo.target()
        panel._asegurar_instancia = mock.Mock(return_value=True)
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch.object(reproductor.diagnostico, "crear_hilo",
                                  side_effect=crear), \
                mock.patch.object(reproductor.wx, "CallAfter",
                                  side_effect=lambda fn: callbacks.append(fn)):
            panel._precalentar()
            panel._precalentamiento_cancelado = True
            callbacks[0]()

        anunciar.assert_called_once_with("Preparando el reproductor")

    def test_el_constructor_no_precalienta(self):
        with mock.patch.object(reproductor.wx.Panel, "__init__", return_value=None), \
                mock.patch.object(reproductor.ReproductorPanel, "SetBackgroundColour"), \
                mock.patch.object(reproductor.ReproductorPanel, "SetForegroundColour"), \
                mock.patch.object(reproductor, "disponible", return_value=True), \
                mock.patch.object(reproductor.ReproductorPanel, "_build_ui"), \
                mock.patch.object(reproductor.ReproductorPanel, "_precalentar") as precalentar:
            reproductor.ReproductorPanel(None, {})

        precalentar.assert_not_called()

    def test_preparar_dll_registra_su_tramo(self):
        anterior = reproductor._VLC_PREPARADO
        try:
            reproductor._VLC_PREPARADO = False
            with mock.patch.object(reproductor, "_carpeta_vlc_empaquetada",
                                   return_value=None), \
                    mock.patch.object(reproductor.time, "monotonic",
                                      side_effect=[1.0, 1.25]), \
                    mock.patch.object(reproductor.diagnostico.logger, "info") as registrar:
                reproductor._preparar_vlc()
            registrar.assert_called_once_with(
                "VLC_PRECALENTAMIENTO tramo=%s ms=%.0f", "preparar_dll", 250)
        finally:
            reproductor._VLC_PREPARADO = anterior

    def test_importar_modulo_registra_su_tramo(self):
        anterior = reproductor._vlc
        try:
            reproductor._vlc = None
            with mock.patch.object(reproductor, "_preparar_vlc"), \
                    mock.patch.object(reproductor.time, "monotonic",
                                      side_effect=[2.0, 2.5]), \
                    mock.patch.object(reproductor.diagnostico.logger, "info") as registrar, \
                    mock.patch.dict(sys.modules, {"vlc": types.SimpleNamespace()}):
                self.assertTrue(reproductor._cargar_vlc())
            self.assertEqual(registrar.call_args.args[1:], ("importar_modulo", 500))
        finally:
            reproductor._vlc = anterior

    def test_crear_instancia_registra_su_tramo(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._inst = None
        panel._listo = True
        panel._inst_lock = mock.Mock()
        panel._inst_lock.__enter__ = mock.Mock(return_value=panel._inst_lock)
        panel._inst_lock.__exit__ = mock.Mock(return_value=False)
        instancia = object()
        anterior = reproductor._vlc
        try:
            reproductor._vlc = types.SimpleNamespace(Instance=lambda *_: instancia)
            with mock.patch.object(reproductor, "_cargar_vlc", return_value=True), \
                    mock.patch.object(reproductor.time, "monotonic",
                                      side_effect=[3.0, 3.75]), \
                    mock.patch.object(reproductor.diagnostico.logger, "info") as registrar:
                self.assertTrue(panel._asegurar_instancia())
            self.assertEqual(registrar.call_args.args[1:], ("crear_instancia", 750))
        finally:
            reproductor._vlc = anterior


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
