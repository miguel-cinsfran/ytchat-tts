"""Pruebas de los avisos de los controles del reproductor."""

import unittest
from unittest import mock
import types
import sys

import reproductor


class RelojMonotonic:
    def __init__(self, primero, despues):
        self._llamadas = 0
        self._primero = primero
        self._despues = despues

    def __call__(self):
        self._llamadas += 1
        return self._primero if self._llamadas == 1 else self._despues


FORMATOS_SEPARADOS = [
    {"format_id": "233", "height": None, "vcodec": "none",
     "acodec": None, "abr": None, "tbr": None, "url": "audio-233"},
    {"format_id": "234", "height": None, "vcodec": "none",
     "acodec": None, "abr": None, "tbr": None, "url": "audio-234"},
    {"format_id": "269", "height": 144, "vcodec": "avc1.42C00B",
     "acodec": "none", "abr": 0, "tbr": 269.034, "url": "video-144"},
    {"format_id": "229", "height": 240, "vcodec": "avc1.4D4015",
     "acodec": "none", "abr": 0, "tbr": 507.418, "url": "video-240"},
    {"format_id": "230", "height": 360, "vcodec": "avc1.4D401E",
     "acodec": "none", "abr": 0, "tbr": 1000.0, "url": "video-360"},
    {"format_id": "231", "height": 480, "vcodec": "avc1.4D401F",
     "acodec": "none", "abr": 0, "tbr": 1500.0, "url": "video-480"},
    {"format_id": "232", "height": 720, "vcodec": "avc1.4D401F",
     "acodec": "none", "abr": 0, "tbr": 2500.0, "url": "video-720"},
    {"format_id": "270", "height": 1080, "vcodec": "avc1.640028",
     "acodec": "none", "abr": 0, "tbr": 4500.0, "url": "video-1080"},
]


class TestSeleccionFormatos(unittest.TestCase):

    def test_elige_audio_con_acodec_nulo(self):
        self.assertIn(
            reproductor._mejor_audio({"formats": FORMATOS_SEPARADOS}),
            ("audio-233", "audio-234"),
        )

    def test_elige_video_1080_sin_progresivo(self):
        self.assertEqual(
            reproductor._video_para_altura(
                {"formats": FORMATOS_SEPARADOS}, 10000),
            ("video-1080", False),
        )

    def test_elige_video_480_sin_progresivo(self):
        self.assertEqual(
            reproductor._video_para_altura(
                {"formats": FORMATOS_SEPARADOS}, 480),
            ("video-480", False),
        )

    def test_a_igual_altura_gana_mayor_tbr(self):
        formatos = [
            {"vcodec": "avc1", "acodec": "none", "height": 720,
             "tbr": 2000, "url": "video-720-lento"},
            {"vcodec": "avc1", "acodec": "none", "height": 720,
             "tbr": 3000, "url": "video-720-rapido"},
        ]
        self.assertEqual(
            reproductor._video_para_altura({"formats": formatos}, 1000),
            ("video-720-rapido", False),
        )

    def test_sin_progresivo_elige_la_menor_altura_no_superior(self):
        formatos = [
            {"vcodec": "avc1", "acodec": "none", "height": 720,
             "url": "video-720"},
            {"vcodec": "avc1", "acodec": "none", "height": 1080,
             "url": "video-1080"},
        ]
        self.assertEqual(
            reproductor._video_para_altura({"formats": formatos}, 480),
            ("video-720", False),
        )

    def test_sin_progresivo_elige_la_menor_altura_disponible(self):
        formatos = [
            {"vcodec": "avc1", "acodec": "none", "height": 720,
             "url": "video-720"},
            {"vcodec": "avc1", "acodec": "none", "height": 1080,
             "url": "video-1080"},
        ]
        self.assertEqual(
            reproductor._video_para_altura({"formats": formatos}, 144),
            ("video-720", False),
        )

    def test_descarta_guion_grafico_como_audio(self):
        formato = {"vcodec": "none", "acodec": "none", "url": "grafico"}
        self.assertEqual(reproductor._mejor_audio({"formats": [formato]}), "")

    def test_conserva_la_seleccion_progresiva(self):
        formatos = [
            {"vcodec": "avc1", "acodec": "mp4a", "height": 360,
             "url": "progresivo-360"},
            {"vcodec": "avc1", "acodec": "mp4a", "height": 720,
             "url": "progresivo-720"},
        ]
        self.assertEqual(
            reproductor._video_para_altura({"formats": formatos}, 720),
            ("progresivo-720", True),
        )

    def test_prefiere_idioma_alto_antes_que_bitrate(self):
        formatos = [
            {"vcodec": "none", "acodec": None, "abr": 320,
             "language_preference": 1, "url": "doblaje"},
            {"vcodec": "none", "acodec": None, "abr": 128,
             "language_preference": 10, "url": "original"},
        ]
        self.assertEqual(
            reproductor._mejor_audio({"formats": formatos}), "original")


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


class TestOpcionesMedio(unittest.TestCase):

    def test_grabado_tiene_mas_colchon_de_red_que_directo(self):
        grabado = dict(opcion[1:].split("=", 1)
                       for opcion in reproductor.opciones_medio(False))
        directo = dict(opcion[1:].split("=", 1)
                       for opcion in reproductor.opciones_medio(True))
        self.assertGreater(int(grabado["network-caching"]),
                           int(directo["network-caching"]))

    def test_ambos_medios_declaran_las_dos_opciones_de_buffer(self):
        for es_directo in (False, True):
            opciones = reproductor.opciones_medio(es_directo)
            self.assertEqual(len(opciones), 2)
            self.assertTrue(any(opcion.startswith(":network-caching=")
                                for opcion in opciones))
            self.assertTrue(any(opcion.startswith(":live-caching=")
                                for opcion in opciones))


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
            reloj = RelojMonotonic(1.0, 1.25)
            with mock.patch.object(reproductor, "_carpeta_vlc_empaquetada",
                                   return_value=None), \
                    mock.patch.object(reproductor.time, "monotonic",
                                      side_effect=reloj), \
                    mock.patch.object(reproductor.diagnostico.logger, "info") as registrar:
                reproductor._preparar_vlc()
            registrar.assert_any_call(
                "VLC_PRECALENTAMIENTO tramo=%s ms=%.0f", "preparar_dll", 250)
            self.assertEqual(sum(llamada.args[1] == "preparar_dll"
                                 for llamada in registrar.call_args_list), 1)
        finally:
            reproductor._VLC_PREPARADO = anterior

    def test_importar_modulo_registra_su_tramo(self):
        anterior = reproductor._vlc
        try:
            reproductor._vlc = None
            reloj = RelojMonotonic(2.0, 2.5)
            with mock.patch.object(reproductor, "_preparar_vlc"), \
                    mock.patch.object(reproductor.time, "monotonic",
                                      side_effect=reloj), \
                    mock.patch.object(reproductor.diagnostico.logger, "info") as registrar, \
                    mock.patch.dict(sys.modules, {"vlc": types.SimpleNamespace()}):
                self.assertTrue(reproductor._cargar_vlc())
            registrar.assert_any_call(
                "VLC_PRECALENTAMIENTO tramo=%s ms=%.0f", "importar_modulo", 500)
            self.assertEqual(sum(llamada.args[1] == "importar_modulo"
                                 for llamada in registrar.call_args_list), 1)
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
            reloj = RelojMonotonic(3.0, 3.75)
            with mock.patch.object(reproductor, "_cargar_vlc", return_value=True), \
                    mock.patch.object(reproductor.time, "monotonic",
                                      side_effect=reloj), \
                    mock.patch.object(reproductor.diagnostico.logger, "info") as registrar:
                self.assertTrue(panel._asegurar_instancia())
            registrar.assert_any_call(
                "VLC_PRECALENTAMIENTO tramo=%s ms=%.0f", "crear_instancia", 750)
            self.assertEqual(sum(llamada.args[1] == "crear_instancia"
                                 for llamada in registrar.call_args_list), 1)
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

class TestCategoriasDeVolumen(unittest.TestCase):

    def test_los_dos_ajustes_de_volumen_declaran_su_categoria(self):
        panel = types.SimpleNamespace(_aplicar_volumen=lambda _delta: 42)
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            reproductor.ReproductorPanel.ajustar_volumen(panel, 1)
            reproductor.ReproductorPanel._vol_flecha(panel, -1)

        self.assertEqual(anunciar.call_args_list, [
            mock.call("Volumen reproductor 42 por ciento", "volumen"),
            mock.call("Volumen 42", "volumen"),
        ])


if __name__ == "__main__":
    unittest.main()
