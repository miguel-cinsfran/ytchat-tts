"""VOD en calidad automática por el relevo con pistas que no son HLS.

Cubre el encargo 40: altura efectiva, cableado de la rama automática,
audio de respaldo en segundo plano y recarga tras fallo de apertura.
"""

import threading
import time
import unittest
from unittest import mock

from ytchat.player import reproductor


def _formato_video(fid, protocolo, altura, tbr, url=None):
    return {"format_id": fid, "protocol": protocolo, "vcodec": "avc",
            "acodec": "none", "height": altura, "tbr": tbr,
            "url": url or f"https://{fid}"}


def _formato_audio(fid, protocolo, abr, lang, url=None, acodec="mp4a",
                   ext=None):
    pista = {"format_id": fid, "protocol": protocolo, "acodec": acodec,
             "vcodec": "none", "abr": abr, "language_preference": lang,
             "url": url or f"https://{fid}"}
    if ext is not None:
        pista["ext"] = ext
    return pista


class PruebasAlturaAutoVod(unittest.TestCase):
    def test_casos_fijos(self):
        self.assertEqual(
            reproductor._altura_auto_vod([2160, 1440, 1080, 720]), 1080)
        self.assertEqual(reproductor._altura_auto_vod([720, 480]), 720)
        self.assertEqual(reproductor._altura_auto_vod([1440]), 1440)
        self.assertIsNone(reproductor._altura_auto_vod([]))

    def test_propiedad_pertenece_y_es_la_mayor_bajo_el_tope(self):
        casos = [[1080], [720, 480], [2160, 1440], [1440, 1080, 720],
                 [360], [2160], [480, 360, 240], [1080, 720, 480, 360],
                 [2160, 1440, 1080, 720, 480]]
        for alturas in casos:
            with self.subTest(alturas=alturas):
                resultado = reproductor._altura_auto_vod(alturas)
                self.assertIn(resultado, alturas)
                menores = [a for a in alturas if a <= 1080]
                if menores:
                    self.assertEqual(resultado, max(menores))
                else:
                    self.assertEqual(resultado, min(alturas))


def _panel_calidad(info, calidad_sel=None, es_directo=False):
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._listo = True
    panel._video_id = "A" * 11
    panel._url_flujo = ""
    panel._cargando = False
    panel._asegurar_player = mock.Mock(return_value=True)
    panel._cancelar_busqueda = mock.Mock()
    panel._cancelar_transporte = mock.Mock()
    panel._detener_relevo_ffmpeg = mock.Mock()
    panel._timer_progreso = mock.Mock()
    panel._timer = mock.Mock()
    panel.lbl_estado = mock.Mock()
    panel._gen = 0
    panel._relevo_gen = 0
    panel._relevo_ffmpeg = None
    panel._relevo_fuentes = None
    panel._relevo_desfase = 0
    panel._relevo_ventana = None
    panel._relevo_vod_base_ms = None
    panel._vod_por_relevo = False
    panel._relevo_vod_reapertura = None
    panel._relevo_vod_recuperaciones = 0
    panel._relevo_vod_ultima = None
    panel._calidad_sel = calidad_sel
    panel._vol = 80
    panel._muted = False
    panel._audio_local = None
    panel._info = info
    panel._inst = mock.Mock()
    panel._inst.media_new.return_value = mock.Mock()
    panel._player = mock.Mock()
    panel._mostrar_pausa = mock.Mock()
    panel._fijar_estado = mock.Mock()
    panel._error_carga = mock.Mock()
    panel._continuar_reproducir_calidad = mock.Mock()
    return panel


def _info_auto_vod():
    return {"is_live": False, "formats": [
        _formato_video("616", "m3u8_native", 1080, 3000,
                       "https://video-hls-1080"),
        _formato_video("137", "https", 1080, 1500, "https://video-1080"),
        _formato_video("136", "https", 720, 1000, "https://video-720"),
        _formato_audio("233", "m3u8_native", 48, None,
                       "https://audio-hls"),
        _formato_audio("140", "https", 128, -1, "https://audio140",
                       ext="m4a"),
        _formato_audio("251", "https", 160, -1, "https://audio251",
                       acodec="opus", ext="webm"),
    ]}


class PruebasCableadoAutoVod(unittest.TestCase):
    def test_automatica_usa_video_https_1080_y_audio_140(self):
        panel = _panel_calidad(_info_auto_vod(), calidad_sel=None)
        with mock.patch.object(panel, "_arrancar_relevo") as arrancar, \
                mock.patch.object(reproductor, "anunciar"):
            panel._reproducir_calidad(None, True)
        arrancar.assert_called_once_with(
            "https://video-1080", "https://audio140", True, inicio_ms=0)
        self.assertIsNone(panel._calidad_sel)

    def test_con_maximo_720_elige_solo_720_y_no_progresivo_360(self):
        info = {"is_live": False, "formats": [
            _formato_video("136", "https", 720, 1000, "https://solo-720"),
            {"format_id": "18", "protocol": "https", "vcodec": "avc",
             "acodec": "opus", "height": 360, "url": "https://prog-360"},
            _formato_audio("140", "https", 128, -1, "https://audio140",
                           ext="m4a"),
        ]}
        panel = _panel_calidad(info, calidad_sel=None)
        with mock.patch.object(panel, "_arrancar_relevo") as arrancar, \
                mock.patch.object(reproductor, "anunciar"):
            panel._reproducir_calidad(None, True)
        arrancar.assert_called_once_with(
            "https://solo-720", "https://audio140", True, inicio_ms=0)

    def test_directo_en_automatica_sigue_por_fuentes_para_directo(self):
        info = {"is_live": True, "formats": [
            _formato_video("616", "m3u8_native", 1080, 3000,
                           "https://video-hls"),
            _formato_audio("140", "https", 128, -1, "https://audio140",
                           ext="m4a"),
        ]}
        panel = _panel_calidad(info, calidad_sel=None)
        with mock.patch.object(reproductor, "fuentes_para_directo",
                               return_value=("https://directo",
                                             "")) as fuentes, \
                mock.patch.object(reproductor, "anunciar"):
            panel._reproducir_calidad(None, True)
        fuentes.assert_called_once_with(info)


class PruebasAudioRespaldoNoBloquea(unittest.TestCase):
    def _panel_carga(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = "A" * 11
        panel._url_flujo = ""
        panel._gen = 0
        panel._cargando = False
        panel._asegurar_player = mock.Mock(return_value=True)
        panel._timer_progreso = mock.Mock()
        panel._fijar_estado = mock.Mock()
        panel._cancelar_busqueda = mock.Mock()
        panel._cancelar_transporte = mock.Mock()
        panel._estado_inicio = mock.Mock()
        panel._estado_inicio.cancelar.return_value = 1
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._vod_por_relevo = False
        panel._relevo_vod_recuperaciones = 0
        panel._relevo_vod_ultima = None
        panel._intencion_reproducir = False
        panel._info = None
        panel._audio_local = None
        panel._marca_reproduccion = None
        panel._marca_extraccion = None
        panel._inicio_progreso = None
        panel._ultimo_aviso_progreso = None
        return panel

    def test_info_listo_agendado_antes_y_audio_despues(self):
        panel = self._panel_carga()
        evento = threading.Event()
        info = {"is_live": False, "formats": []}

        def preparar(info_rec, vid):
            evento.wait(timeout=5)
            return "AUDIO-NUEVO"

        llamadas = []
        real_asignar = reproductor.ReproductorPanel._asignar_audio_local.__get__(
            panel)
        panel._info_listo = mock.Mock()

        def call_after(fn, *args):
            llamadas.append((fn, args))
            if fn is panel._asignar_audio_local or \
                    getattr(fn, "__name__", "") == "_asignar_audio_local":
                return fn(*args)
            try:
                return fn(*args)
            except Exception:
                return None

        panel._asignar_audio_local = real_asignar
        with mock.patch.object(reproductor, "_info_video",
                               return_value=info), \
                mock.patch.object(reproductor, "_preparar_audio_local",
                                  side_effect=preparar), \
                mock.patch.object(reproductor.wx, "CallAfter",
                                  side_effect=call_after), \
                mock.patch.object(reproductor, "anunciar") as anunciar:
            panel.cargar(reproducir=True)
            limite = time.monotonic() + 5
            while time.monotonic() < limite and not any(
                    getattr(fn, "__name__", "") == "_info_listo"
                    or fn is panel._info_listo for fn, _a in llamadas):
                time.sleep(0.02)
            self.assertTrue(
                any(fn is panel._info_listo for fn, _a in llamadas),
                "info_listo no quedó agendado mientras el audio esperaba")
            self.assertIsNone(panel._audio_local)
            evento.set()
            limite = time.monotonic() + 5
            while time.monotonic() < limite \
                    and panel._audio_local != "AUDIO-NUEVO":
                time.sleep(0.02)
        self.assertEqual(panel._audio_local, "AUDIO-NUEVO")
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertFalse(any("Preparando el audio" in f for f in frases))

    def test_audio_no_se_asigna_si_cambio_la_generacion(self):
        panel = self._panel_carga()
        evento = threading.Event()
        info = {"is_live": False, "formats": []}

        def preparar(info_rec, vid):
            evento.wait(timeout=5)
            return "AUDIO-NUEVO"

        panel._info_listo = mock.Mock()
        with mock.patch.object(reproductor, "_info_video",
                               return_value=info), \
                mock.patch.object(reproductor, "_preparar_audio_local",
                                  side_effect=preparar), \
                mock.patch.object(reproductor.wx, "CallAfter",
                                  side_effect=lambda fn, *a: fn(*a)), \
                mock.patch.object(reproductor, "anunciar"):
            panel.cargar(reproducir=True)
            limite = time.monotonic() + 5
            while time.monotonic() < limite \
                    and panel._info_listo.call_count == 0:
                time.sleep(0.02)
            self.assertEqual(panel._info_listo.call_count, 1)
            panel._gen += 1
            panel._video_id = "B" * 11
            evento.set()
            time.sleep(0.5)
        self.assertIsNone(panel._audio_local)


def _panel_timer(estado, requiere):
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._video_id = "A" * 11
    panel._url_flujo = ""
    panel._info = {"is_live": False}
    panel._player = mock.Mock()
    panel._muted = True
    panel._vol = 80
    inicio = mock.Mock()
    inicio.requiere = requiere
    inicio.primera = None
    inicio.observar.return_value = False
    panel._estado_inicio = inicio
    panel._estado_vlc_actual = mock.Mock(return_value=estado)
    panel._lectura_cruda = mock.Mock(return_value=1000)
    panel._topologia_actual = mock.Mock(return_value="vod")
    panel._evaluar_transporte = mock.Mock()
    panel._evaluar_busqueda = mock.Mock()
    panel._vod_por_relevo = False
    panel._cargando = False
    panel._relevo_ffmpeg = None
    panel._relevo_vod_base_ms = None
    panel._orden_transporte = None
    panel._estado_busqueda = mock.Mock(pendiente=False)
    panel._timer = mock.Mock()
    panel._intencion_reproducir = True
    panel._recargas_apertura = 0
    panel._recargas_directo = 0
    panel._listo = True
    panel._calidad_sel = None
    panel._alturas = []
    panel._gen = 0
    panel._detener = mock.Mock()
    panel._fijar_estado = mock.Mock()
    panel.cargar = mock.Mock()
    return panel


class PruebasFalloAperturaVod(unittest.TestCase):
    def test_ended_primera_recarga_segunda_falla(self):
        panel = _panel_timer("ended", True)
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._on_timer(None)
        panel.cargar.assert_called_once_with(reproducir=True)
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertNotIn("Fin del vídeo", frases)
        self.assertEqual(panel._recargas_apertura, 1)
        panel.cargar.reset_mock()
        anunciar.reset_mock()
        with mock.patch.object(reproductor, "anunciar") as anunciar2, \
                mock.patch("ytchat.voice.sound_player.reproducir") as sonido:
            panel._on_timer(None)
        panel.cargar.assert_not_called()
        panel._detener.assert_called_with(silencioso=True)
        sonido.assert_called_once_with("error")
        frases = [c.args[0] for c in anunciar2.call_args_list]
        self.assertIn("No se pudo reproducir el vídeo", frases)
        self.assertNotIn("Fin del vídeo", frases)

    def test_error_primera_recarga_segunda_falla(self):
        panel = _panel_timer("error", True)
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._on_timer(None)
        panel.cargar.assert_called_once_with(reproducir=True)
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertNotIn("No se pudo reproducir el vídeo", frases)
        panel.cargar.reset_mock()
        with mock.patch.object(reproductor, "anunciar") as anunciar2, \
                mock.patch("ytchat.voice.sound_player.reproducir"):
            panel._on_timer(None)
        panel.cargar.assert_not_called()
        frases = [c.args[0] for c in anunciar2.call_args_list]
        self.assertIn("No se pudo reproducir el vídeo", frases)

    def test_set_video_reinicia_el_contador(self):
        panel = _panel_timer("ended", True)
        panel._recargas_apertura = 1
        panel._detener = mock.Mock()
        panel._fijar_estado = mock.Mock()
        with mock.patch.object(reproductor, "anunciar"):
            panel.set_video("B" * 11, autoplay=False)
        self.assertEqual(panel._recargas_apertura, 0)
        panel.cargar.reset_mock()
        with mock.patch.object(reproductor, "anunciar"):
            panel._on_timer(None)
        panel.cargar.assert_called_once_with(reproducir=True)

    def test_con_requiere_falso_ended_anuncia_fin_como_antes(self):
        panel = _panel_timer("ended", False)
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._on_timer(None)
        panel.cargar.assert_not_called()
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertIn("Fin del vídeo", frases)


if __name__ == "__main__":
    unittest.main()
