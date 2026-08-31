"""Pruebas de caché de vídeo con identidad por tarea y cancelación."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import reproductor
from busqueda_video import EstadoBusqueda
from tarea_cache_video import TareaCacheVideo


class TestReproductorCache(unittest.TestCase):

    def _panel(self, video_id="VID12345678", gen=0):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._config = {"cache_video_mb": 1024}
        panel._gen = gen
        panel._video_id = video_id
        panel._tarea_cache_video = None
        panel._intencion_reproducir = True
        panel._vol = 80
        panel._muted = False
        panel._inst = mock.Mock()
        panel._player = mock.Mock()
        panel._player.audio_set_volume = mock.Mock()
        panel._player.audio_set_mute = mock.Mock()
        panel._player.play = mock.Mock()
        panel._player.set_time = mock.Mock()
        panel._player.set_pause = mock.Mock()
        panel._player.set_media = mock.Mock()
        panel._player.get_time = mock.Mock(return_value=1000)
        panel._marcar_destino = mock.Mock()
        panel._podar_cache_video = mock.Mock()
        panel._cargando = False
        panel._estado_busqueda = EstadoBusqueda(confirmada=0)
        panel._transporte_pendiente = False
        panel._timer_progreso = mock.Mock()
        panel._timer = mock.Mock()
        panel.lbl_estado = mock.Mock()
        panel.btn_play = mock.Mock()
        panel._fijar_tiempo = mock.Mock()
        return panel

    def test_A_recibe_su_propio_evento(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = self._panel()
            hilos = []
            callbacks = []
            entro = threading.Event()
            capturado = {}

            def fake_descargar(video_id, destino, cancel_event=None, **kw):
                capturado["event"] = cancel_event
                entro.set()
                cancel_event.wait(timeout=2)
                Path(destino).parent.mkdir(parents=True, exist_ok=True)
                Path(destino).write_bytes(b"x")
                return True

            def fake_crear_hilo(target, nombre, *, args=(), daemon=True):
                t = threading.Thread(target=target, daemon=daemon, name=nombre)
                hilos.append(t)
                return t

            try:
                with mock.patch.object(reproductor.diagnostico, "crear_hilo", side_effect=fake_crear_hilo), \
                     mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda f, *a, **k: callbacks.append((f, a, k))), \
                     mock.patch.object(reproductor._cfg, "app_dir", return_value=Path(tmp)), \
                     mock.patch.object(reproductor.ytdlp_bin, "descargar_video_cache", side_effect=fake_descargar):
                    panel._descargar_video_cache(panel._video_id, panel._gen)
                    tarea_a = panel._tarea_cache_video
                    self.assertIsNotNone(tarea_a)
                    self.assertIsInstance(tarea_a.cancelacion, threading.Event)
                    self.assertTrue(entro.wait(timeout=2))
                    self.assertIs(capturado["event"], tarea_a.cancelacion)
                    tarea_a.cancelacion.set()
                    for t in hilos:
                        t.join(timeout=2)
                    self.assertFalse(any(t.is_alive() for t in hilos))
                    self.assertEqual(len(callbacks), 1)
            finally:
                for t in hilos:
                    if t.is_alive():
                        if "event" in capturado and capturado["event"] is not None:
                            capturado["event"].set()
                        t.join(timeout=2)
                for t in hilos:
                    self.assertFalse(t.is_alive())

    def test_B_cancela_A_y_recibe_evento_distinto(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = self._panel(gen=5)
            panel._video_id = "VID_B_12345"
            hilos = []
            callbacks = []
            entro_a = threading.Event()
            entro_b = threading.Event()
            liberar_b = threading.Event()
            capturado = {}

            def fake_descargar(video_id, destino, cancel_event=None, **kw):
                if video_id == "VID_A_12345":
                    capturado["a"] = cancel_event
                    entro_a.set()
                    cancel_event.wait(timeout=2)
                    Path(destino).parent.mkdir(parents=True, exist_ok=True)
                    Path(destino).write_bytes(b"a")
                    return True
                capturado["b"] = cancel_event
                entro_b.set()
                liberar_b.wait(timeout=2)
                Path(destino).parent.mkdir(parents=True, exist_ok=True)
                Path(destino).write_bytes(b"b")
                return True

            def fake_crear_hilo(target, nombre, *, args=(), daemon=True):
                t = threading.Thread(target=target, daemon=daemon, name=nombre)
                hilos.append(t)
                return t

            try:
                with mock.patch.object(reproductor.diagnostico, "crear_hilo", side_effect=fake_crear_hilo), \
                     mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda f, *a, **k: callbacks.append((f, a, k))), \
                     mock.patch.object(reproductor._cfg, "app_dir", return_value=Path(tmp)), \
                     mock.patch.object(reproductor.ytdlp_bin, "descargar_video_cache", side_effect=fake_descargar):
                    panel._descargar_video_cache("VID_A_12345", 5)
                    tarea_a = panel._tarea_cache_video
                    self.assertTrue(entro_a.wait(timeout=2))
                    self.assertIs(capturado["a"], tarea_a.cancelacion)
                    self.assertTrue(hilos[0].is_alive())
                    panel._descargar_video_cache("VID_B_12345", 5)
                    tarea_b = panel._tarea_cache_video
                    self.assertTrue(tarea_a.cancelacion.is_set())
                    self.assertIsNot(tarea_a, tarea_b)
                    self.assertIsNot(tarea_a.cancelacion, tarea_b.cancelacion)
                    self.assertTrue(entro_b.wait(timeout=2))
                    self.assertIs(capturado["b"], tarea_b.cancelacion)
                    hilos[0].join(timeout=2)
                    self.assertFalse(hilos[0].is_alive())
                    self.assertTrue(hilos[1].is_alive())
                    self.assertEqual(len(callbacks), 1)
                    func, args, _k = callbacks[0]
                    with mock.patch.object(panel, "_podar_cache_video") as podar, \
                         mock.patch("sound_player.reproducir"):
                        func(*args)
                        podar.assert_not_called()
                        panel._player.set_media.assert_not_called()
                        self.assertIs(panel._tarea_cache_video, tarea_b)
                    liberar_b.set()
                    hilos[1].join(timeout=2)
                    self.assertFalse(hilos[1].is_alive())
                    self.assertEqual(len(callbacks), 2)
                    func2, args2, _k2 = callbacks[1]
                    panel._estado_busqueda = EstadoBusqueda(confirmada=999)
                    panel._inst.media_new = mock.Mock(return_value=mock.Mock(add_option=mock.Mock()))
                    with mock.patch.object(panel, "_podar_cache_video") as podar, \
                         mock.patch("sound_player.reproducir"):
                        func2(*args2)
                        podar.assert_called_once()
                        panel._player.set_media.assert_called_once()
                        self.assertIsNone(panel._tarea_cache_video)
                    for t in hilos:
                        self.assertFalse(t.is_alive())
            finally:
                liberar_b.set()
                if "a" in capturado:
                    capturado["a"].set()
                if "b" in capturado:
                    capturado["b"].set()
                for t in hilos:
                    t.join(timeout=2)
                for t in hilos:
                    self.assertFalse(t.is_alive())

    def test_finalizacion_invertida_A_no_afecta_B(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            panel = self._panel(video_id="VID_B_12345", gen=5)
            panel._video_id = "VID_B_12345"
            panel._gen = 5
            dest_a = carpeta / "VID_A_12345.mp4"
            dest_b = carpeta / "VID_B_12345.mp4"
            dest_a.write_bytes(b"x" * 100)
            dest_b.write_bytes(b"y" * 100)
            tarea_a = TareaCacheVideo("VID_A_12345", 5, dest_a)
            tarea_b = TareaCacheVideo("VID_B_12345", 5, dest_b)
            panel._tarea_cache_video = tarea_b
            panel._inst.media_new = mock.Mock(return_value=mock.Mock(add_option=mock.Mock()))
            with mock.patch.object(panel, "_podar_cache_video") as podar, \
                 mock.patch("sound_player.reproducir") as snd:
                panel._player.set_media.reset_mock()
                reproductor.ReproductorPanel._cache_video_lista(panel, tarea_a, True)
                podar.assert_not_called()
                panel._player.set_media.assert_not_called()
                snd.assert_not_called()
                self.assertTrue(dest_a.is_file())
                self.assertTrue(dest_b.is_file())
                self.assertIs(panel._tarea_cache_video, tarea_b)
                panel._estado_busqueda = EstadoBusqueda(confirmada=999)
                reproductor.ReproductorPanel._cache_video_lista(panel, tarea_b, True)
                podar.assert_called_once()
                panel._player.set_media.assert_called_once()
                self.assertIsNone(panel._tarea_cache_video)

    def test_mismo_video_id_A_no_borra_destino_de_B(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            dest = carpeta / "VID_SAME.mp4"
            dest.write_bytes(b"contenido")
            panel = self._panel(video_id="VID_SAME", gen=0)
            tarea_a = TareaCacheVideo("VID_SAME", 0, dest)
            tarea_b = TareaCacheVideo("VID_SAME", 0, dest)
            panel._tarea_cache_video = tarea_b
            panel._inst.media_new = mock.Mock(return_value=mock.Mock(add_option=mock.Mock()))
            with mock.patch.object(panel, "_podar_cache_video") as podar:
                reproductor.ReproductorPanel._cache_video_lista(panel, tarea_a, True)
                podar.assert_not_called()
                panel._player.set_media.assert_not_called()
                self.assertTrue(dest.is_file())
                self.assertIs(panel._tarea_cache_video, tarea_b)

    def test_detener_marca_evento_y_deja_inerte_callback(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = self._panel()
            panel._gen = 0
            panel._tarea_cache_video = None
            panel._mostrar_pausa = mock.Mock()
            panel._fijar_tiempo = mock.Mock()
            panel._ic_play = mock.Mock()
            panel._ic_pause = mock.Mock()
            panel._timer = mock.Mock()
            panel._timer_progreso = mock.Mock()
            hilos = []
            callbacks = []
            entro = threading.Event()
            capturado = {}

            def fake_descargar(video_id, destino, cancel_event=None, **kw):
                capturado["event"] = cancel_event
                entro.set()
                cancel_event.wait()
                Path(destino).parent.mkdir(parents=True, exist_ok=True)
                Path(destino).write_bytes(b"data")
                return True

            def fake_crear_hilo(target, nombre, *, args=(), daemon=True):
                t = threading.Thread(target=target, daemon=daemon, name=nombre)
                hilos.append(t)
                return t

            dest_esperado = None
            try:
                with mock.patch.object(reproductor.diagnostico, "crear_hilo", side_effect=fake_crear_hilo), \
                     mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda f, *a, **k: callbacks.append((f, a, k))), \
                     mock.patch.object(reproductor._cfg, "app_dir", return_value=Path(tmp)), \
                     mock.patch.object(reproductor.ytdlp_bin, "descargar_video_cache", side_effect=fake_descargar):
                    panel._descargar_video_cache(panel._video_id, panel._gen)
                    tarea = panel._tarea_cache_video
                    dest_esperado = tarea.destino
                    self.assertTrue(entro.wait(timeout=2))
                    self.assertIs(capturado["event"], tarea.cancelacion)
                    self.assertTrue(hilos[0].is_alive())
                    panel._detener(silencioso=True)
                    self.assertTrue(tarea.cancelacion.is_set())
                    self.assertIsNone(panel._tarea_cache_video)
                    for t in hilos:
                        t.join(timeout=2)
                    self.assertFalse(any(t.is_alive() for t in hilos))
                    self.assertEqual(len(callbacks), 1)
                    func, args, _k = callbacks[0]
                    with mock.patch.object(panel, "_podar_cache_video") as podar:
                        func(*args)
                        podar.assert_not_called()
                    self.assertTrue(Path(dest_esperado).is_file() if dest_esperado else True)
                    self.assertFalse(any(t.is_alive() for t in hilos))
            finally:
                if "event" in capturado:
                    capturado["event"].set()
                for t in hilos:
                    t.join(timeout=2)
                for t in hilos:
                    self.assertFalse(t.is_alive())

    def test_cancelar_dos_veces_idempotente(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = self._panel()
            hilos = []
            callbacks = []

            def fake_crear_hilo(target, nombre, *, args=(), daemon=True):
                t = mock.Mock()
                t.start = mock.Mock()
                return t

            with mock.patch.object(reproductor.diagnostico, "crear_hilo", side_effect=fake_crear_hilo), \
                 mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda f, *a, **k: callbacks.append((f, a, k))), \
                 mock.patch.object(reproductor._cfg, "app_dir", return_value=Path(tmp)), \
                 mock.patch.object(reproductor.ytdlp_bin, "descargar_video_cache", return_value=True):
                panel._descargar_video_cache("VID_A_12345", 0)
                tarea_a = panel._tarea_cache_video
                panel._descargar_video_cache("VID_B_12345", 0)
                tarea_b = panel._tarea_cache_video
                self.assertTrue(tarea_a.cancelacion.is_set())
                tarea_a.cancelacion.set()
                self.assertFalse(tarea_b.cancelacion.is_set())
                tarea_b.cancelacion.set()
                tarea_b.cancelacion.set()
                self.assertTrue(tarea_b.cancelacion.is_set())
                self.assertIs(panel._tarea_cache_video, tarea_b)

    def test_cargar_otro_video_y_cambiar_flujo_pasan_por_detener(self):
        dest = Path(tempfile.gettempdir()) / "VID_OLD.mp4"
        tarea = TareaCacheVideo("VID_OLD", 0, dest)
        real_panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        real_panel._config = {"cache_video_mb": 1024}
        real_panel._gen = 0
        real_panel._video_id = "VID_OLD"
        real_panel._url_flujo = ""
        real_panel._listo = True
        real_panel._cargando = False
        real_panel._tarea_cache_video = tarea
        real_panel._estado_busqueda = EstadoBusqueda(confirmada=0)
        real_panel._transporte_pendiente = False
        real_panel._intencion_reproducir = True
        real_panel._timer_progreso = mock.Mock()
        real_panel._timer = mock.Mock()
        real_panel._player = None
        real_panel._inst = mock.Mock()
        real_panel.lbl_estado = mock.Mock()
        real_panel.btn_play = mock.Mock()
        real_panel._mostrar_pausa = mock.Mock()
        real_panel._fijar_tiempo = mock.Mock()
        real_panel.cargar = mock.Mock()
        real_panel._asegurar_player = mock.Mock(return_value=True)
        real_panel._ic_play = mock.Mock()
        real_panel._ic_pause = mock.Mock()
        real_panel._info = None
        real_panel._calidad_sel = None
        real_panel._alturas = []
        real_panel._audio_local = None
        real_panel.set_video("VID_NEW", autoplay=False)
        self.assertTrue(tarea.cancelacion.is_set())
        self.assertIsNone(real_panel._tarea_cache_video)
        tarea2 = TareaCacheVideo("VID_NEW", real_panel._gen, Path(tempfile.gettempdir()) / "VID_NEW.mp4")
        real_panel._tarea_cache_video = tarea2
        real_panel.set_flujo("https://example.com/stream.m3u8", autoplay=False)
        self.assertTrue(tarea2.cancelacion.is_set())
        self.assertIsNone(real_panel._tarea_cache_video)

    def test_callback_A_con_completa_false_no_limpia_B(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest_b = Path(tmp) / "VID_B_12345.mp4"
            dest_b.write_bytes(b"b")
            dest_a = Path(tmp) / "VID_A_12345.mp4"
            panel = self._panel(video_id="VID_B_12345", gen=1)
            tarea_a = TareaCacheVideo("VID_A_12345", 1, dest_a)
            tarea_b = TareaCacheVideo("VID_B_12345", 1, dest_b)
            panel._tarea_cache_video = tarea_b
            panel._inst.media_new = mock.Mock(return_value=mock.Mock(add_option=mock.Mock()))
            with mock.patch.object(panel, "_podar_cache_video") as podar:
                reproductor.ReproductorPanel._cache_video_lista(panel, tarea_a, False)
                podar.assert_not_called()
                panel._player.set_media.assert_not_called()
                self.assertIs(panel._tarea_cache_video, tarea_b)

    def test_guardas_validas_conservan_cambio_a_archivo_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "VID12345678.mp4"
            dest.write_bytes(b"video")
            panel = self._panel(video_id="VID12345678", gen=7)
            panel._gen = 7
            panel._video_id = "VID12345678"
            panel._tarea_cache_video = TareaCacheVideo("VID12345678", 7, dest)
            tarea = panel._tarea_cache_video
            medio = mock.Mock()
            medio.add_option = mock.Mock()
            panel._inst.media_new = mock.Mock(return_value=medio)
            panel._estado_busqueda = EstadoBusqueda(confirmada=55555)
            panel._intencion_reproducir = False
            panel._vol = 42
            panel._muted = True
            with mock.patch("sound_player.reproducir") as snd:
                reproductor.ReproductorPanel._cache_video_lista(panel, tarea, True)
            medio.add_option.assert_any_call(":network-caching=3000")
            medio.add_option.assert_any_call(":live-caching=1500")
            panel._inst.media_new.assert_called_once_with(str(dest))
            panel._player.set_media.assert_called_once_with(medio)
            panel._player.audio_set_volume.assert_called_once_with(42)
            panel._player.audio_set_mute.assert_called_once_with(True)
            panel._player.play.assert_called_once()
            panel._player.set_time.assert_called_once_with(55555)
            panel._player.set_pause.assert_called_once_with(1)
            panel._marcar_destino.assert_called_once_with(55555, anunciar_usuario=False)
            snd.assert_called_once_with("transporte_en_curso")
            panel._podar_cache_video.assert_called_once_with(dest.parent)
            self.assertIsNone(panel._tarea_cache_video)
            dest2 = Path(tmp) / "VID99999999.mp4"
            dest2.write_bytes(b"v2")
            panel2 = self._panel(video_id="VID99999999", gen=7)
            panel2._gen = 7
            panel2._video_id = "VID99999999"
            tarea2 = TareaCacheVideo("VID99999999", 7, dest2)
            panel2._tarea_cache_video = tarea2
            medio2 = mock.Mock()
            medio2.add_option = mock.Mock()
            panel2._inst.media_new = mock.Mock(return_value=medio2)
            panel2._estado_busqueda = EstadoBusqueda(confirmada=111)
            panel2._intencion_reproducir = True
            panel2._vol = 80
            panel2._muted = False
            with mock.patch("sound_player.reproducir"):
                reproductor.ReproductorPanel._cache_video_lista(panel2, tarea2, True)
            panel2._player.set_pause.assert_not_called()

    def test_trabajador_conserva_poda_carpeta_nombre_hilo_y_excepcion(self):
        panel = self._panel()
        orden = []

        def fake_podar(carpeta):
            orden.append("podar")

        def fake_descargar(video_id, destino, cancel_event=None, **kw):
            orden.append("descargar")
            self.assertIs(cancel_event, panel._tarea_cache_video.cancelacion)
            raise OSError("fallo simulado")

        panel._podar_cache_video = fake_podar
        hilos = []
        callbacks = []

        def fake_crear_hilo(target, nombre, *, args=(), daemon=True):
            self.assertEqual(nombre, "ReproductorCacheVideo")
            t = threading.Thread(target=target, daemon=daemon, name=nombre)
            hilos.append(t)
            return t

        try:
            with mock.patch.object(reproductor.diagnostico, "crear_hilo", side_effect=fake_crear_hilo), \
                 mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda f, *a, **k: callbacks.append((f, a, k))), \
                 mock.patch.object(reproductor._cfg, "app_dir", return_value=Path(tempfile.gettempdir()) / "ytchat-test-cache2"), \
                 mock.patch.object(reproductor.ytdlp_bin, "descargar_video_cache", side_effect=fake_descargar):
                panel._descargar_video_cache(panel._video_id, panel._gen)
                for t in hilos:
                    t.join(timeout=2)
                self.assertFalse(any(t.is_alive() for t in hilos))
                self.assertEqual(orden, ["podar", "descargar"])
                self.assertEqual(len(callbacks), 1)
                func, args, _k = callbacks[0]
                self.assertEqual(func.__func__, reproductor.ReproductorPanel._cache_video_lista)
                self.assertIs(func.__self__, panel)
                tarea, completa = args
                self.assertIs(tarea, panel._tarea_cache_video)
                self.assertFalse(completa)
        finally:
            for t in hilos:
                t.join(timeout=2)
            for t in hilos:
                self.assertFalse(t.is_alive())


if __name__ == "__main__":
    unittest.main()
