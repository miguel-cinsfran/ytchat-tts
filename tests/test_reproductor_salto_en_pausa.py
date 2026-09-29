"""Salto en pausa con el VOD por relevo de ffmpeg.

En pausa no se reabre el relevo ni se toca VLC: el destino se guarda y la
búsqueda queda confirmada ahí. Al reanudar se reabre el relevo desde ese
destino reproduciendo, sin pasar por cargar ni por set_pause.
"""

import unittest
from unittest import mock

from ytchat.player import reproductor
from ytchat.player.busqueda_video import EstadoBusqueda


def _info_vod():
    return {"is_live": False, "duration": 3600, "formats": [
        {"url": "https://video", "height": 1080, "vcodec": "avc", "acodec": "none"},
        {"url": "https://audio", "vcodec": "none", "acodec": "opus", "abr": 128},
    ]}


class _Aplazada:
    """CallLater falso: se vence a mano y se puede cancelar."""

    def __init__(self, fn):
        self.fn = fn
        self.detendida = False

    def Stop(self):
        self.detendida = True


def _panel_pausa(confirmada=41_000):
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._listo = True
    panel._video_id = "j906Pf7n7Sg"
    panel._url_flujo = ""
    panel._info = _info_vod()
    panel._player = mock.Mock()
    panel._player.get_state.return_value = "paused"
    panel._player.get_length.return_value = 0
    panel._player.get_time.return_value = 1145
    panel._estado_busqueda = EstadoBusqueda(confirmada=confirmada)
    panel._tiene_esclavo = False
    panel._usando_cache_local = False
    panel._intencion_reproducir = False
    panel._orden_transporte = None
    panel._relevo_ffmpeg = mock.Mock()
    panel._relevo_fuentes = ("https://video", "https://audio")
    panel._relevo_desfase = 0
    panel._relevo_ventana = None
    panel._relevo_vod_base_ms = 40_000
    panel._vod_por_relevo = True
    panel._relevo_vod_reapertura = None
    panel._relevo_vod_destino_en_pausa = None
    panel._relevo_vod_recuperaciones = 0
    panel._relevo_vod_ultima = 41_000
    panel._gen = 0
    panel._relevo_gen = 0
    panel._config = {"cache_video_mb": 1024}
    panel._timer = mock.Mock()
    panel._timer_progreso = mock.Mock()
    panel.lbl_tiempo = mock.Mock()
    panel.sld_pos = mock.Mock()
    return panel


class PruebasSaltoEnPausa(unittest.TestCase):
    """Dos flechas en pausa no tocan VLC y dejan el destino confirmado."""

    def test_dos_pulsaciones_en_pausa_guardan_y_confirman_sin_reabrir(self):
        panel = _panel_pausa()
        agendadas = []
        diferidas = []

        def call_later(_ms, fn, *args):
            aplazada = _Aplazada(lambda: fn(*args))
            agendadas.append((fn, args))
            return aplazada

        def call_after(fn, *args):
            diferidas.append((fn, args))
            return mock.Mock()

        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch.object(reproductor.wx, "CallLater",
                                  side_effect=call_later), \
                mock.patch.object(reproductor.wx, "CallAfter",
                                  side_effect=call_after), \
                mock.patch.object(panel, "_arrancar_relevo") as arrancar:
            panel._buscar_rel(+10_000)
            panel._buscar_rel(+10_000)
            arrancar.assert_not_called()
            # No se agenda ninguna reapertura con debounce (lo único que
            # puede agendarse es la caducidad propia de _marcar_destino).
            self.assertIsNone(panel._relevo_vod_reapertura)
            reaperturas = [e for e in agendadas
                           if getattr(e[0], "__name__", "") == "_reabrir_relevo_vod"]
            self.assertEqual(reaperturas, [])
            # El destino se guarda para reanudar desde ahí.
            self.assertEqual(panel._relevo_vod_destino_en_pausa, 61_000)
            # La confirmación va diferida, como pide el diseño.
            self.assertEqual(len(diferidas), 2)
            for fn, args in diferidas:
                fn(*args)
            # Ni siquiera al vencer la caducidad agendada por _marcar_destino.
            for fn, args in agendadas:
                fn(*args)
        arrancar.assert_not_called()
        self.assertIsNone(panel._relevo_vod_reapertura)
        panel._player.set_time.assert_not_called()
        self.assertEqual(panel._relevo_vod_destino_en_pausa, 61_000)
        self.assertEqual(panel._estado_busqueda.confirmada, 61_000)
        self.assertFalse(panel._estado_busqueda.pendiente)
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertNotIn("No se pudo mover el vídeo", frases)
        self.assertEqual(frases.count("Moviendo a 51 segundos"), 1)
        self.assertEqual(frases.count("Moviendo a 1 minuto 1 segundo"), 1)

    def test_evaluar_despues_de_confirmar_no_falla_ni_retrocede(self):
        panel = _panel_pausa()
        diferidas = []

        def call_after(fn, *args):
            diferidas.append((fn, args))
            return mock.Mock()

        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch.object(reproductor.wx, "CallAfter",
                                  side_effect=call_after), \
                mock.patch.object(panel, "_arrancar_relevo"):
            panel._buscar_rel(+10_000)
            for fn, args in diferidas:
                fn(*args)
            panel._evaluar_busqueda()
        self.assertEqual(panel._estado_busqueda.confirmada, 51_000)
        self.assertFalse(panel._estado_busqueda.pendiente)
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertNotIn("No se pudo mover el vídeo", frases)


class PruebasReanudarTrasSaltoEnPausa(unittest.TestCase):
    """Reanudar reabre el relevo desde el destino guardado, reproduciendo."""

    def test_reanudar_reabre_desde_el_destino_sin_cargar_ni_despausar(self):
        panel = _panel_pausa(confirmada=61_000)
        panel._relevo_vod_destino_en_pausa = 61_000
        panel._asegurar_player = mock.Mock(return_value=True)
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch.object(panel, "_arrancar_relevo") as arrancar, \
                mock.patch.object(panel, "cargar") as cargar:
            panel._toggle_play()
        arrancar.assert_called_once_with(
            "https://video", "https://audio", True, inicio_ms=61_000)
        cargar.assert_not_called()
        panel._player.set_pause.assert_not_called()
        self.assertIsNone(panel._relevo_vod_destino_en_pausa)
        self.assertTrue(panel._intencion_reproducir)
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertIn("Reanudando", frases)
        self.assertNotIn("Cargando vídeo", frases)


class PruebasSaltoSonandoIgualQueAntes(unittest.TestCase):
    """Reproduciendo, una flecha sigue agendando la reapertura con debounce."""

    def test_sonando_agenda_reapertura_con_debounce(self):
        panel = _panel_pausa()
        panel._intencion_reproducir = True
        panel._relevo_vod_destino_en_pausa = None
        agendadas = []

        def call_later(_ms, fn, *args):
            aplazada = _Aplazada(lambda: fn(*args))
            agendadas.append((fn, args))
            return aplazada

        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch.object(reproductor.wx, "CallLater",
                                  side_effect=call_later), \
                mock.patch.object(reproductor.wx, "CallAfter",
                                  side_effect=lambda fn, *a: mock.Mock()), \
                mock.patch.object(panel, "_arrancar_relevo") as arrancar:
            panel._buscar_rel(+10_000)
            self.assertIsNotNone(panel._relevo_vod_reapertura)
            self.assertIsNone(panel._relevo_vod_destino_en_pausa)
            arrancar.assert_not_called()
            reaperturas = [e for e in agendadas
                           if getattr(e[0], "__name__", "") == "_reabrir_relevo_vod"]
            self.assertEqual(len(reaperturas), 1)
            reaperturas[0][0](*reaperturas[0][1])
        arrancar.assert_called_once_with(
            "https://video", "https://audio", True, inicio_ms=51_000)


class PruebasDestinoNoSobreviveAOtroVideo(unittest.TestCase):
    """Cambiar de vídeo limpia el destino guardado en pausa."""

    def test_set_video_limpia_el_destino(self):
        panel = _panel_pausa()
        panel._relevo_vod_destino_en_pausa = 61_000
        panel._fijar_estado = mock.Mock()
        with mock.patch.object(reproductor, "anunciar"):
            panel.set_video("B" * 11, autoplay=False)
        self.assertIsNone(panel._relevo_vod_destino_en_pausa)


if __name__ == "__main__":
    unittest.main()
