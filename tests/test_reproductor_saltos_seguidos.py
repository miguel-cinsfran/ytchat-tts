"""Saltos seguidos en directo y confirmación única en grabado.

Directo por relevo: pulsar las flechas dos o tres veces seguidas acumula
los desfases (cada pulsación anuncia al instante) y ffmpeg se reinicia una
sola vez con el último desfase, gracias al debounce de 400 ms. Grabado por
relevo: el salto confirma solo con la posición, sin «Reproduciendo».
"""

import time
import unittest
from unittest import mock

from ytchat.player import reproductor
from ytchat.player.busqueda_video import EstadoBusqueda, EstadoInicioReproduccion


class _Aplazada:
    """CallLater falso: se vence a mano y se puede cancelar."""

    def __init__(self, fn):
        self.fn = fn
        self.detendida = False

    def Stop(self):
        self.detendida = True


def _panel_directo(desfase=2):
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._listo = True
    panel._video_id = "D" * 11
    panel._url_flujo = ""
    panel._info = {"is_live": True, "duration": 0, "formats": []}
    panel._player = mock.Mock()
    panel._player.get_state.return_value = None
    panel._estado_busqueda = EstadoBusqueda(confirmada=0)
    panel._tiene_esclavo = False
    panel._usando_cache_local = False
    panel._intencion_reproducir = True
    panel._cargando = False
    panel._gen = 0
    panel._relevo_gen = 0
    # En pleno reinicio: ffmpeg aún no está arriba pero las fuentes sí.
    panel._relevo_ffmpeg = None
    panel._relevo_fuentes = ("video-hls", "audio-hls")
    panel._relevo_desfase = desfase
    panel._relevo_ventana = (5.0, 720)
    panel._relevo_vod_reapertura = None
    panel._relevo_directo_reapertura = None
    panel._vod_por_relevo = False
    panel._cancelar_busqueda = mock.Mock()
    panel._cancelar_transporte = mock.Mock()
    panel._fijar_estado = mock.Mock()
    return panel


def _call_later_falso(agendadas, pendientes):
    def call_later(_ms, fn, *args):
        aplazada = _Aplazada(lambda: fn(*args))
        agendadas.append((fn, args))
        pendientes.append(aplazada)
        return aplazada
    return call_later


class PruebasSaltosSeguidosEnDirecto(unittest.TestCase):
    """Tres flechas seguidas en pleno reinicio anuncian tres frases
    crecientes y dejan el desfase acumulado, sin «No se puede buscar»."""

    def test_tres_pulsaciones_acumulan_desfase_y_anuncian_tres_frases(self):
        panel = _panel_directo(desfase=2)
        agendadas = []
        pendientes = []
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch.object(reproductor.wx, "CallLater",
                                  side_effect=_call_later_falso(
                                      agendadas, pendientes)), \
                mock.patch.object(panel, "_arrancar_relevo"):
            panel._buscar_rel(-10_000)
            panel._buscar_rel(-10_000)
            panel._buscar_rel(-10_000)
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertEqual(frases, [
            "20 segundos por detrás del directo",
            "30 segundos por detrás del directo",
            "40 segundos por detrás del directo",
        ])
        self.assertNotIn("No se puede buscar en este momento", frases)
        self.assertNotIn("Cargando vídeo", frases)
        self.assertEqual(panel._relevo_desfase, 8)
        panel._player.set_time.assert_not_called()

    def test_tres_pulsaciones_dejan_una_sola_reapertura_con_el_ultimo_desfase(self):
        panel = _panel_directo(desfase=2)
        pendientes = []
        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch.object(reproductor.wx, "CallLater",
                                  side_effect=_call_later_falso([], pendientes)), \
                mock.patch.object(panel, "_arrancar_relevo") as arrancar:
            panel._buscar_rel(-10_000)
            panel._buscar_rel(-10_000)
            panel._buscar_rel(-10_000)
            self.assertEqual(len(pendientes), 3)
            self.assertTrue(pendientes[0].detendida)
            self.assertTrue(pendientes[1].detendida)
            self.assertFalse(pendientes[2].detendida)
            arrancar.assert_not_called()
            pendientes[2].fn()
        arrancar.assert_called_once_with(
            "video-hls", "audio-hls", True, desfase=8,
            anuncio="40 segundos por detrás del directo")

    def test_sin_fuentes_en_carga_inicial_sigue_diciendo_cargando(self):
        panel = _panel_directo(desfase=0)
        panel._cargando = True
        panel._relevo_fuentes = None
        with mock.patch.object(reproductor.relevo_ffmpeg, "RelevoFfmpeg") as clase, \
                mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._saltar_en_relevo(-10_000)
        clase.assert_not_called()
        anunciar.assert_called_once_with("Cargando vídeo")

    def test_buscar_rel_en_reinicio_va_al_directo_y_no_a_sin_barra(self):
        panel = _panel_directo(desfase=2)
        with mock.patch.object(panel, "_saltar_en_relevo") as saltar, \
                mock.patch.object(panel, "_aviso_sin_barra") as sin_barra:
            panel._buscar_rel(-10_000)
        saltar.assert_called_once_with(-10_000)
        sin_barra.assert_not_called()


def _panel_vod_relevo(bus):
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._listo = True
    panel._video_id = "A" * 11
    panel._url_flujo = ""
    panel._info = {"is_live": False, "duration": 3600, "formats": [
        {"url": "https://video", "height": 1080, "vcodec": "avc", "acodec": "none"},
        {"url": "https://audio", "vcodec": "none", "acodec": "opus", "abr": 128},
    ]}
    panel._player = mock.Mock()
    panel._player.get_state.return_value = None
    panel._player.get_length.return_value = 0
    panel._player.get_time.return_value = 1500
    panel._estado_busqueda = bus
    panel._estado_inicio = EstadoInicioReproduccion()
    panel._tiene_esclavo = False
    panel._usando_cache_local = False
    panel._intencion_reproducir = True
    panel._cargando = True
    panel._gen = 0
    panel._relevo_gen = 0
    panel._relevo_ffmpeg = None
    panel._relevo_fuentes = ("https://video", "https://audio")
    panel._relevo_desfase = 0
    panel._relevo_ventana = None
    panel._relevo_vod_base_ms = None
    panel._vod_por_relevo = True
    panel._relevo_vod_reapertura = None
    panel._relevo_vod_recuperaciones = 0
    panel._relevo_vod_ultima = None
    panel._audio_local = None
    panel._vol = 80
    panel._muted = False
    panel._inst = mock.Mock()
    panel._inst.media_new.return_value = mock.Mock()
    panel._mostrar_pausa = mock.Mock()
    panel._fijar_estado = mock.Mock()
    panel._timer = mock.Mock()
    panel.lbl_tiempo = mock.Mock()
    panel.sld_pos = mock.Mock()
    return panel


def _relevo_vivo():
    relevo = mock.Mock()
    relevo.activo.return_value = True
    return relevo


class PruebasSaltoGrabadoSinReproduciendo(unittest.TestCase):
    """Al sonar el relevo reabierto por un salto no se anuncia
    «Reproduciendo»; la carga inicial sí lo conserva."""

    def test_con_busqueda_pendiente_cancela_el_inicio(self):
        bus = EstadoBusqueda(confirmada=10_000)
        bus.solicitar(20_000, time.monotonic())
        panel = _panel_vod_relevo(bus)
        relevo = _relevo_vivo()
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch.object(reproductor.wx, "CallLater",
                                  side_effect=lambda _ms, fn, *a: _Aplazada(
                                      lambda: fn(*a))):
            panel._relevo_listo(relevo, "tcp://127.0.0.1:6000",
                                panel._relevo_gen, panel._gen, panel._video_id,
                                "https://video", "https://audio", True,
                                0, None, None, 20_000)
        self.assertFalse(panel._estado_inicio.requiere)
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertNotIn("Reproduciendo", frases)

    def test_en_carga_inicial_conserva_el_reproduciendo(self):
        panel = _panel_vod_relevo(EstadoBusqueda(confirmada=0))
        relevo = _relevo_vivo()
        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch.object(reproductor.wx, "CallLater",
                                  side_effect=lambda _ms, fn, *a: _Aplazada(
                                      lambda: fn(*a))):
            panel._relevo_listo(relevo, "tcp://127.0.0.1:6000",
                                panel._relevo_gen, panel._gen, panel._video_id,
                                "https://video", "https://audio", True,
                                0, None, None, 0)
        self.assertTrue(panel._estado_inicio.requiere)


if __name__ == "__main__":
    unittest.main()
