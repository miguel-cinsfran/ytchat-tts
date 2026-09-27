"""VOD dividido por el relevo de ffmpeg en modo grabado.

Cada salto reabre el relevo desde el destino y la posición que ve el
usuario es la del vídeo real (base del relevo más la lectura de VLC).
"""

import re
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ytchat.player import reproductor
from ytchat.player.busqueda_video import EstadoBusqueda
from ytchat.player import relevo_ffmpeg
from ytchat.downloads import ffmpeg_bin


def _info_vod_dividido():
    return {"is_live": False, "duration": 3600, "formats": [
        {"url": "https://video", "height": 1080, "vcodec": "avc", "acodec": "none"},
        {"url": "https://audio", "vcodec": "none", "acodec": "opus", "abr": 128},
    ]}


class PruebasArranqueVodRelevo(unittest.TestCase):
    """Un VOD con esclavo arranca el relevo en modo grabado desde 0."""

    def _panel(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = "A" * 11
        panel._cargando = False
        panel._asegurar_player = mock.Mock(return_value=True)
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
        panel._calidad_sel = 1080
        panel._vol = 80
        panel._muted = False
        panel._audio_local = None
        panel._descargar_video_cache = mock.Mock()
        panel._info = _info_vod_dividido()
        panel._inst = mock.Mock()
        panel._inst.media_new.return_value = mock.Mock()
        panel._player = mock.Mock()
        panel._mostrar_pausa = mock.Mock()
        panel._fijar_estado = mock.Mock()
        panel._error_carga = mock.Mock()
        return panel

    def test_vod_con_esclavo_arranca_relevo_con_inicio_cero(self):
        panel = self._panel()
        with mock.patch.object(panel, "_arrancar_relevo") as arrancar, \
                mock.patch.object(reproductor, "anunciar"):
            panel._reproducir_calidad(1080, True)
        arrancar.assert_called_once_with(
            "https://video", "https://audio", True, inicio_ms=0)
        self.assertFalse(panel._tiene_esclavo)

    def test_vod_fuente_unica_no_usa_relevo(self):
        panel = self._panel()
        panel._info = {"is_live": False, "duration": 3600, "formats": [
            {"url": "https://progresivo", "height": 1080,
             "vcodec": "avc", "acodec": "opus"},
        ]}
        with mock.patch.object(panel, "_arrancar_relevo") as arrancar, \
                mock.patch.object(panel, "_continuar_reproducir_calidad") as continuar, \
                mock.patch.object(reproductor, "anunciar"):
            panel._reproducir_calidad(1080, True)
        arrancar.assert_not_called()
        continuar.assert_called_once()
        args = continuar.call_args.args
        self.assertEqual(args[0], "https://progresivo")
        self.assertFalse(args[2])


class PruebasSaltoVodRelevo(unittest.TestCase):
    """Tres flechas seguidas producen una sola reapertura al destino acumulado."""

    def _panel(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = "A" * 11
        panel._url_flujo = ""
        panel._info = _info_vod_dividido()
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 0  # lo que da VLC con el relevo
        panel._player.get_time.return_value = 1500
        panel._estado_busqueda = EstadoBusqueda(confirmada=10_000)
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._intencion_reproducir = True
        panel._relevo_ffmpeg = mock.Mock()
        panel._relevo_fuentes = ("https://video", "https://audio")
        panel._relevo_desfase = 0
        panel._relevo_ventana = None
        panel._relevo_vod_base_ms = 10_000
        panel._vod_por_relevo = True
        panel._relevo_vod_reapertura = None
        panel._relevo_vod_recuperaciones = 0
        panel._relevo_vod_ultima = 10_000
        panel._gen = 0
        panel._config = {"cache_video_mb": 1024}
        panel._inst = mock.Mock()
        panel._fijar_tiempo = mock.Mock()
        panel._timer = mock.Mock()
        panel.sld_pos = mock.Mock()
        return panel

    def test_tres_flechas_una_sola_reapertura_al_destino_acumulado(self):
        panel = self._panel()
        llamadas = []
        pendientes = []

        class _Aplazada:
            def __init__(self, fn):
                self.fn = fn
                self.detendida = False

            def Stop(self):
                self.detendida = True

        def call_later(_ms, fn, *args):
            aplazada = _Aplazada(lambda: fn(*args))
            llamadas.append((fn, args))
            pendientes.append(aplazada)
            return aplazada

        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch.object(reproductor.wx, "CallLater",
                                  side_effect=call_later), \
                mock.patch.object(panel, "_arrancar_relevo") as arrancar:
            panel._buscar_rel(+10_000)
            panel._buscar_rel(+10_000)
            panel._buscar_rel(+10_000)
            # Sin relevo de VOD esto llamaría a set_time; con relevo no.
            panel._player.set_time.assert_not_called()
            # Tres pulsaciones, tres marcas inmediatas al destino acumulado.
            self.assertEqual(panel._estado_busqueda.destino, 40_000)
            # Solo la última reapertura agendada vale: se vencen las anteriores.
            self.assertTrue(pendientes[0].detendida)
            self.assertTrue(pendientes[1].detendida)
            self.assertFalse(pendientes[2].detendida)
            # Al vencer, una sola reapertura al último destino.
            pendientes[2].fn()
        arrancar.assert_called_once_with(
            "https://video", "https://audio", True, inicio_ms=40_000)

    def test_lectura_cruda_suma_la_base(self):
        panel = self._panel()
        self.assertEqual(panel._lectura_cruda(), 11_500)
        panel._player.get_time.return_value = 0
        self.assertEqual(panel._lectura_cruda(), -1)

    def test_duracion_actual_sale_de_la_info(self):
        panel = self._panel()
        self.assertEqual(panel._duracion_actual(), 3_600_000)
        panel._info = {"is_live": False}
        panel._player.get_length.return_value = 60_000
        self.assertEqual(panel._duracion_actual(), 60_000)

    def test_cache_lista_detiene_el_relevo(self):
        from ytchat.player.tarea_cache_video import TareaCacheVideo
        panel = self._panel()
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "video.mp4"
            destino.write_bytes(b"x" * 1024)
            tarea = TareaCacheVideo(panel._video_id, panel._gen, destino)
            panel._tarea_cache_video = tarea
            panel._gen = tarea.generacion
            panel._relevo_vod_reapertura = mock.Mock()
            panel._vol = 80
            panel._muted = False
            relevo_viejo = panel._relevo_ffmpeg
            reapertura_vieja = panel._relevo_vod_reapertura
            with mock.patch("ytchat.voice.sound_player.reproducir"):
                panel._cache_video_lista(tarea, True)
        relevo_viejo.detener.assert_called_once()
        self.assertIsNone(panel._relevo_ffmpeg)
        self.assertIsNone(panel._relevo_vod_base_ms)
        reapertura_vieja.Stop.assert_called_once()
        self.assertTrue(panel._usando_cache_local)


class PruebasFronteraRealFfmpeg(unittest.TestCase):
    """El relevo en modo grabado entrega vídeo+audio desde el segundo 20.

    Se lee el flujo entero hasta que ffmpeg cierra (las fuentes duran 30 s
    y el relevo arranca en el 20, así que son unos 10 s) exigiendo al menos
    64 KB. La duración se mide decodificando cada pista: el matroska que
    sale por TCP no trae duración en la cabecera (Duration: N/A) porque
    ffmpeg no puede rebobinar el socket para escribirla al cerrar.
    """

    def _generar_fuentes(self, ffmpeg, carpeta):
        video_src = str(Path(carpeta) / "solo_video.mp4")
        audio_src = str(Path(carpeta) / "solo_audio.m4a")
        # -g 20: un fotograma clave cada 2 s, como los flujos reales. Con el
        # intervalo por defecto del x264 (250 fotogramas) la búsqueda de
        # entrada cae 20 s antes del destino y el matroska local sale entero.
        proc = subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi",
             "-i", "testsrc=size=128x128:rate=10",
             "-t", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-g", "20", video_src],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode != 0 or not Path(video_src).is_file():
            proc = subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi",
                 "-i", "testsrc=size=128x128:rate=10",
                 "-t", "30", "-c:v", "mpeg4", "-g", "20", video_src],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
             "-c:a", "aac", audio_src],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return video_src, audio_src

    @staticmethod
    def _segundos(horas, minutos, segundos):
        return int(horas) * 3600 + int(minutos) * 60 + float(segundos)

    def _duracion_pista(self, ffmpeg, volcado, mapa):
        sonda = subprocess.run(
            [ffmpeg, "-i", volcado, "-map", mapa, "-f", "null", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        tiempos = re.findall(r"time=(\d+):(\d+):([\d.]+)", sonda.stderr)
        self.assertTrue(tiempos, sonda.stderr[-500:])
        return self._segundos(*tiempos[-1])

    def test_relevo_grabado_sirve_flujo_con_video_y_audio(self):
        ffmpeg = ffmpeg_bin.ruta_ffmpeg()
        if not ffmpeg:
            self.skipTest("sin ffmpeg")
        with tempfile.TemporaryDirectory() as carpeta:
            video_src, audio_src = self._generar_fuentes(ffmpeg, carpeta)
            if not Path(video_src).is_file() or not Path(audio_src).is_file():
                self.skipTest("ffmpeg no pudo generar las fuentes")
            volcado = str(Path(carpeta) / "relevo.mkv")
            relevo = relevo_ffmpeg.RelevoFfmpeg(
                video_src, audio_src, inicio_ms=20000)
            try:
                direccion = relevo.iniciar()
                self.assertIsNotNone(direccion)
                self.assertTrue(relevo.esperar_listo(timeout=20))
                puerto = int(direccion.rsplit(":", 1)[1])
                datos = b""
                with socket.create_connection(
                        ("127.0.0.1", puerto), timeout=10) as cliente:
                    cliente.settimeout(10)
                    try:
                        while True:
                            tramo = cliente.recv(65536)
                            if not tramo:
                                break
                            datos += tramo
                            if len(datos) > 8 * 1024 * 1024:
                                break
                    except socket.timeout:
                        pass
                self.assertGreaterEqual(len(datos), 65536)
                Path(volcado).write_bytes(datos)
                sonda = subprocess.run(
                    [ffmpeg, "-i", volcado],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                texto = sonda.stderr
                self.assertIn("Video:", texto)
                self.assertIn("Audio:", texto)
                # Arrancó en el segundo 20 de 30: quedan unos 10 s.
                dur_video = self._duracion_pista(ffmpeg, volcado, "0:v:0")
                dur_audio = self._duracion_pista(ffmpeg, volcado, "0:a:0")
                self.assertLess(dur_video, 12)
                self.assertLess(dur_audio, 12)
                self.assertGreater(dur_video, 5)
                self.assertGreater(dur_audio, 5)
            finally:
                relevo.detener()


class PruebasVentanaReaperturaVodRelevo(unittest.TestCase):
    """Durante la reapertura el panel sigue en modo relevo grabado.

    Replica cómo arma el panel PruebasSaltoVodRelevo, pero con el relevo
    a medio reabrir: bandera de modo relevo en verdadero, base en None y
    carga en curso.
    """

    def _panel_en_reapertura(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = "A" * 11
        panel._url_flujo = ""
        panel._info = _info_vod_dividido()
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 0
        panel._player.get_time.return_value = 1500
        panel._estado_busqueda = EstadoBusqueda(confirmada=10_000)
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._intencion_reproducir = True
        panel._relevo_ffmpeg = None
        panel._relevo_fuentes = ("https://video", "https://audio")
        panel._relevo_desfase = 0
        panel._relevo_ventana = None
        panel._vod_por_relevo = True
        panel._relevo_vod_base_ms = None
        panel._relevo_vod_reapertura = None
        panel._relevo_vod_recuperaciones = 0
        panel._relevo_vod_ultima = 10_000
        panel._cargando = True
        panel._gen = 0
        panel._config = {"cache_video_mb": 1024}
        panel._inst = mock.Mock()
        panel._fijar_tiempo = mock.Mock()
        panel._timer = mock.Mock()
        panel.sld_pos = mock.Mock()
        return panel

    def test_buscar_en_reapertura_reagenda_sin_tocar_el_flujo_viejo(self):
        panel = self._panel_en_reapertura()
        llamadas = []

        class _Aplazada:
            def Stop(self):
                pass

        def call_later(_ms, fn, *args):
            llamadas.append((fn, args))
            return _Aplazada()

        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch.object(reproductor.wx, "CallLater",
                                  side_effect=call_later):
            panel._buscar_rel(+10_000)
        panel._player.set_time.assert_not_called()
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertNotIn("No se puede buscar en este momento", frases)
        self.assertEqual(panel._estado_busqueda.destino, 20_000)
        self.assertEqual(len(llamadas), 1)
        self.assertEqual(llamadas[0][1], (20_000,))

    def _panel_timer(self, estado):
        panel = self._panel_en_reapertura()
        panel._muted = False
        panel._estado_inicio = mock.Mock(requiere=False)
        panel._orden_transporte = None
        panel._estado_vlc_actual = mock.Mock(return_value=estado)
        panel._evaluar_transporte = mock.Mock()
        panel._evaluar_busqueda = mock.Mock()
        panel._detener = mock.Mock()
        panel._fallo_reproduccion = reproductor.ReproductorPanel._fallo_reproduccion.__get__(panel)
        panel._fijar_estado = mock.Mock()
        panel._vol = 80
        return panel

    def test_timer_en_reapertura_con_ended_no_anuncia_fin(self):
        panel = self._panel_timer("ended")
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._on_timer(None)
        panel._detener.assert_not_called()
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertNotIn("Fin del vídeo", frases)

    def test_timer_en_reapertura_con_error_no_detiene(self):
        panel = self._panel_timer("error")
        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch("ytchat.voice.sound_player.reproducir"):
            panel._on_timer(None)
        panel._detener.assert_not_called()

    def test_cache_lista_apaga_el_modo_relevo(self):
        from ytchat.player.tarea_cache_video import TareaCacheVideo
        panel = self._panel_en_reapertura()
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "video.mp4"
            destino.write_bytes(b"x" * 1024)
            tarea = TareaCacheVideo(panel._video_id, panel._gen, destino)
            panel._tarea_cache_video = tarea
            panel._vol = 80
            panel._muted = False
            panel._player = mock.Mock()
            panel._inst = mock.Mock()
            panel._inst.media_new.return_value = mock.Mock()
            with mock.patch("ytchat.voice.sound_player.reproducir"):
                panel._cache_video_lista(tarea, True)
        self.assertFalse(panel._vod_por_relevo)

    def test_reproducir_calidad_con_fuente_unica_deja_modo_relevo_en_falso(self):
        panel = self._panel_en_reapertura()
        panel._info = {"is_live": False, "duration": 3600, "formats": [
            {"url": "https://progresivo", "height": 1080,
             "vcodec": "avc", "acodec": "opus"},
        ]}
        panel._asegurar_player = mock.Mock(return_value=True)
        panel._cancelar_busqueda = mock.Mock()
        panel._cancelar_transporte = mock.Mock()
        panel._continuar_reproducir_calidad = mock.Mock()
        with mock.patch.object(reproductor, "anunciar"):
            panel._reproducir_calidad(1080, True)
        self.assertFalse(panel._vod_por_relevo)


def _info_vod_con_hls_y_normales():
    return {"is_live": False, "duration": 3600, "formats": [
        {"format_id": "136", "protocol": "https", "vcodec": "avc",
         "acodec": "none", "height": 1080, "tbr": 1500,
         "url": "https://video"},
        {"format_id": "233", "protocol": "m3u8_native", "vcodec": "none",
         "acodec": "mp4a", "abr": 48, "language_preference": None,
         "url": "https://audio233"},
        {"format_id": "234", "protocol": "m3u8_native", "vcodec": "none",
         "acodec": "mp4a", "abr": 120, "language_preference": None,
         "url": "https://audio234"},
        {"format_id": "140", "protocol": "https", "vcodec": "none",
         "acodec": "mp4a", "abr": 128, "language_preference": -1,
         "url": "https://audio140"},
        {"format_id": "251", "protocol": "https", "vcodec": "none",
         "acodec": "opus", "abr": 160, "language_preference": -1,
         "url": "https://audio251"},
    ]}


class PruebasVodRelevoEvitaHls(unittest.TestCase):
    """El VOD por relevo arma sus fuentes con pistas que no son HLS."""

    def _panel(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = "A" * 11
        panel._cargando = False
        panel._asegurar_player = mock.Mock(return_value=True)
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
        panel._calidad_sel = 1080
        panel._vol = 80
        panel._muted = False
        panel._audio_local = None
        panel._descargar_video_cache = mock.Mock()
        panel._info = _info_vod_con_hls_y_normales()
        panel._inst = mock.Mock()
        panel._inst.media_new.return_value = mock.Mock()
        panel._player = mock.Mock()
        panel._mostrar_pausa = mock.Mock()
        panel._fijar_estado = mock.Mock()
        panel._error_carga = mock.Mock()
        return panel

    def test_reproducir_calidad_pasa_audio_no_hls_al_relevo(self):
        panel = self._panel()
        with mock.patch.object(panel, "_arrancar_relevo") as arrancar, \
                mock.patch.object(reproductor, "anunciar"):
            panel._reproducir_calidad(1080, True)
        arrancar.assert_called_once_with(
            "https://video", "https://audio251", True, inicio_ms=0)


class PruebasVodRelevoCaidaAEsclavo(unittest.TestCase):
    """Si el relevo nunca llega a sonar, tras dos intentos se sigue con el
    camino anterior (esclavo de audio, sin salto) en vez de reintentar."""

    def _panel_bucle(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._video_id = "A" * 11
        panel._cargando = False
        panel._gen = 0
        panel._relevo_gen = 0
        panel._info = {"is_live": False, "duration": 3600}
        panel._vod_por_relevo = True
        panel._relevo_ffmpeg = mock.Mock()
        panel._relevo_fuentes = ("https://video", "https://audio251")
        panel._relevo_vod_base_ms = 0
        panel._relevo_vod_ultima = 0
        panel._relevo_vod_recuperaciones = 0
        panel._intencion_reproducir = True
        panel._estado_busqueda = EstadoBusqueda(confirmada=0)
        panel._pos_ms = 0
        panel._tiene_esclavo = False
        panel._cancelar_transporte = mock.Mock()
        panel._detener_relevo_ffmpeg = mock.Mock(
            side_effect=self._detener_relevo(panel))
        panel._detener = mock.Mock()
        panel._arrancar_relevo = mock.Mock()
        panel._continuar_reproducir_calidad = mock.Mock()
        return panel

    @staticmethod
    def _detener_relevo(panel):
        def _cerrar():
            panel._relevo_ffmpeg = None
            panel._relevo_vod_base_ms = None
        return _cerrar

    def _listo_exitoso(self, panel):
        relevo = mock.Mock()
        relevo.activo.return_value = True
        panel._continuar_reproducir_calidad = mock.Mock()
        with mock.patch.object(reproductor, "anunciar"):
            panel._relevo_listo(relevo, "tcp://relevo:1", panel._relevo_gen,
                                panel._gen, panel._video_id, "https://video",
                                "https://audio251", True, 0, None, None, 0)

    def test_tras_dos_recuperaciones_sin_sonar_cae_al_esclavo(self):
        panel = self._panel_bucle()
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._fin_flujo_vod()
            self.assertEqual(panel._relevo_vod_recuperaciones, 1)
            self._listo_exitoso(panel)
            self.assertEqual(panel._relevo_vod_recuperaciones, 1)
            panel._relevo_ffmpeg = mock.Mock()
            panel._fin_flujo_vod()
            self.assertEqual(panel._relevo_vod_recuperaciones, 2)
            self._listo_exitoso(panel)
            self.assertEqual(panel._relevo_vod_recuperaciones, 2)
            panel._relevo_ffmpeg = mock.Mock()
            panel._continuar_reproducir_calidad = mock.Mock()
            panel._fin_flujo_vod()
        panel._continuar_reproducir_calidad.assert_called_once_with(
            "https://video", "https://audio251", False, True)
        self.assertFalse(panel._vod_por_relevo)
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertNotIn("Se cortó el vídeo", frases)

    def test_con_lectura_que_avanzo_agotar_el_tope_corta(self):
        panel = self._panel_bucle()
        panel._relevo_vod_base_ms = 0
        panel._relevo_vod_ultima = 60_000
        panel._relevo_vod_recuperaciones = 2
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._fin_flujo_vod()
        panel._continuar_reproducir_calidad.assert_not_called()
        frases = [c.args[0] for c in anunciar.call_args_list]
        self.assertIn("Se cortó el vídeo", frases)


if __name__ == "__main__":
    unittest.main()
