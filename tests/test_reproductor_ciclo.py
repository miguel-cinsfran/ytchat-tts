"""Pruebas del ciclo de vida del reproductor VLC (reproductor_ciclo)."""

import threading
import time
import unittest
from unittest import mock

import reproductor
import reproductor_ciclo


class TestCicloPuro(unittest.TestCase):

    def test_iniciar_retirada_activa_en_retirada(self):
        ciclo = reproductor_ciclo.CicloReproductor()
        self.assertFalse(ciclo.en_retirada)
        rid = ciclo.iniciar_retirada()
        self.assertTrue(ciclo.en_retirada)
        self.assertEqual(ciclo.id_actual, rid)

    def test_finalizar_con_id_correcto_libera(self):
        ciclo = reproductor_ciclo.CicloReproductor()
        rid = ciclo.iniciar_retirada()
        self.assertTrue(ciclo.finalizar_retirada(rid))
        self.assertFalse(ciclo.en_retirada)

    def test_callback_viejo_no_libera_nueva(self):
        ciclo = reproductor_ciclo.CicloReproductor()
        rid1 = ciclo.iniciar_retirada()
        # Simula callback viejo que intenta finalizar después de nueva retirada
        # En uso real se inicia otra retirada sin haber finalizado la anterior?
        # Probamos que rid viejo no libera si ya hay nuevo id.
        rid2 = ciclo.iniciar_retirada()
        self.assertNotEqual(rid1, rid2)
        self.assertFalse(ciclo.finalizar_retirada(rid1))
        self.assertTrue(ciclo.en_retirada)
        self.assertEqual(ciclo.id_actual, rid2)
        self.assertTrue(ciclo.finalizar_retirada(rid2))
        self.assertFalse(ciclo.en_retirada)

    def test_diferir_reemplaza_y_conserva_ultima(self):
        ciclo = reproductor_ciclo.CicloReproductor()
        ciclo.iniciar_retirada()
        ciclo.diferir_video("AAA", True)
        ciclo.diferir_video("BBB", False)
        pendiente = ciclo.tomar_pendiente()
        self.assertEqual(pendiente.tipo, "video")
        self.assertEqual(pendiente.valor, "BBB")
        self.assertFalse(pendiente.autoplay)

    def test_dos_reconexiones_ejecutan_solo_ultima(self):
        ciclo = reproductor_ciclo.CicloReproductor()
        ciclo.iniciar_retirada()
        ciclo.diferir_video("uno", True)
        ciclo.diferir_video("dos", True)
        ciclo.diferir_flujo("https://flujo", True)
        pendiente = ciclo.tomar_pendiente()
        self.assertEqual(pendiente.tipo, "flujo")

    def test_cancelar_pendiente_deja_sin_intencion(self):
        ciclo = reproductor_ciclo.CicloReproductor()
        ciclo.iniciar_retirada()
        ciclo.diferir_video("AAA", True)
        ciclo.cancelar_pendiente()
        self.assertIsNone(ciclo.tomar_pendiente())

    def test_anuncio_solo_una_vez(self):
        ciclo = reproductor_ciclo.CicloReproductor()
        ciclo.iniciar_retirada()
        self.assertTrue(ciclo.diferir_video("AAA", True))
        self.assertFalse(ciclo.diferir_video("BBB", True))
        self.assertTrue(ciclo.anuncio_hecho)

    def test_nueva_retirada_rearma_anuncio(self):
        ciclo = reproductor_ciclo.CicloReproductor()
        rid1 = ciclo.iniciar_retirada()
        ciclo.diferir_video("AAA", True)
        ciclo.finalizar_retirada(rid1)
        rid2 = ciclo.iniciar_retirada()
        self.assertFalse(ciclo.anuncio_hecho)
        self.assertTrue(ciclo.diferir_video("BBB", True))

    def test_tomar_pendiente_vacia_despues(self):
        ciclo = reproductor_ciclo.CicloReproductor()
        ciclo.iniciar_retirada()
        ciclo.diferir_video("AAA", True)
        ciclo.tomar_pendiente()
        self.assertIsNone(ciclo.tomar_pendiente())


def _panel_base(player=None, inst=None):
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._config = {}
    panel._video_id = ""
    panel._url_flujo = ""
    panel._gen = 0
    panel._ciclo = reproductor_ciclo.CicloReproductor()
    panel._listo = True
    panel._cargando = False
    panel._precalentamiento_cancelado = False
    panel._estado_busqueda = mock.Mock()
    panel._estado_busqueda.pendiente = False
    panel._estado_inicio = mock.Mock(cancelar=mock.Mock())
    panel._tiene_esclavo = False
    panel._usando_cache_local = False
    panel._transporte_pendiente = False
    panel._orden_transporte = None
    panel._intencion_reproducir = False
    panel._vol = 80
    panel._muted = False
    panel._calidad_sel = None
    panel._alturas = []
    panel._inst = inst
    panel._inst_lock = threading.Lock()
    panel._player = player
    panel._gestor_eventos_vlc = object()
    panel._info = None
    panel._audio_local = None
    panel._tarea_cache_video = None
    panel._marca_reproduccion = None
    panel._marca_extraccion = None
    panel._marca_url = None
    panel._inicio_progreso = None
    panel._ultimo_aviso_progreso = None
    panel._fs = None
    panel._timer = mock.Mock(Stop=mock.Mock(), Start=mock.Mock())
    panel._timer_progreso = mock.Mock(Stop=mock.Mock(), Start=mock.Mock())
    panel._video = mock.Mock(GetHandle=mock.Mock(return_value=999))
    panel.lbl_estado = mock.Mock(SetLabel=mock.Mock())
    panel.btn_play = mock.Mock(SetBitmap=mock.Mock(), SetLabel=mock.Mock())
    panel._mostrar_pausa = mock.Mock()
    panel._fijar_tiempo = mock.Mock()
    panel._cancelar_busqueda = mock.Mock()
    panel._cancelar_transporte = mock.Mock()
    panel._fijar_salida = mock.Mock()
    panel._enganchar_eventos_vlc = mock.Mock()
    panel._asegurar_instancia = mock.Mock(return_value=True)
    # evitar que _detener intente usar _timer no existente
    return panel


class TestCableadoRetirada(unittest.TestCase):

    def test_bloquea_media_player_new_durante_retirada(self):
        evento = threading.Event()
        player_viejo = mock.Mock()
        player_viejo.set_hwnd = mock.Mock()
        player_viejo.stop.side_effect = lambda: evento.wait(timeout=2)
        player_viejo.release = mock.Mock()
        nuevo_player = mock.Mock()
        nuevo_player.set_hwnd = mock.Mock()
        nuevo_player.event_manager.return_value = mock.Mock(event_attach=mock.Mock())
        inst = mock.Mock()
        inst.media_player_new.return_value = nuevo_player
        panel = _panel_base(player=player_viejo, inst=inst)
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=123))
        app_mock = mock.Mock()
        with mock.patch.object(reproductor.wx, "GetApp", return_value=app_mock), \
             mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda fn, *a, **kw: None):
            panel.detener_todo()
            time.sleep(0.05)
            self.assertTrue(panel._ciclo.en_retirada)
            self.assertIsNone(panel._player)
            inst.media_player_new.reset_mock()
            # llamada directa durante retirada debe bloquear
            resultado = panel._asegurar_player()
            inst.media_player_new.assert_not_called()
            self.assertFalse(resultado)
            player_viejo.release.assert_not_called()
            # liberar y dejar terminar el trabajador
            evento.set()
            time.sleep(0.15)
            player_viejo.release.assert_called_once()
            # sigue sin haber creado player nuevo porque CallAfter es no-op
            inst.media_player_new.assert_not_called()

    def test_release_antes_de_new_player(self):
        evento = threading.Event()
        orden = []
        player_viejo = mock.Mock()
        player_viejo.set_hwnd = mock.Mock()
        def stop_bloqueante():
            orden.append("stop")
            evento.wait(timeout=2)
        player_viejo.stop.side_effect = stop_bloqueante
        def release_bloqueante():
            orden.append("release")
        player_viejo.release.side_effect = release_bloqueante
        nuevo_player = mock.Mock()
        inst = mock.Mock()
        def new_player_fn():
            orden.append("new")
            return nuevo_player
        inst.media_player_new.side_effect = new_player_fn
        panel = _panel_base(player=player_viejo, inst=inst)
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=123))
        app_mock = mock.Mock()
        with mock.patch.object(reproductor.wx, "GetApp", return_value=app_mock), \
             mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda fn, *a, **kw: None):
            panel.detener_todo()
            time.sleep(0.05)
            # intentar video durante retirada
            with mock.patch.object(reproductor, "anunciar"):
                panel.set_video("VID", autoplay=True)
            self.assertNotIn("new", orden)
            evento.set()
            time.sleep(0.15)
            self.assertIn("stop", orden)
            self.assertIn("release", orden)
            self.assertNotIn("new", orden)
            rid = panel._ciclo.id_actual
            # simular reanudación que sí crea player
            panel._inst = inst
            panel._video = mock.Mock(GetHandle=mock.Mock(return_value=123))
            panel._fijar_salida = mock.Mock()
            panel._enganchar_eventos_vlc = mock.Mock()
            panel._asegurar_instancia = mock.Mock(return_value=True)
            with mock.patch.object(reproductor, "anunciar"):
                with mock.patch.object(panel, "cargar", wraps=panel.cargar) as cargar_wrap:
                    # para evitar hilo de info, parcheamos diagnostico.crear_hilo para el segundo hilo
                    with mock.patch.object(reproductor.diagnostico, "crear_hilo") as crear_hilo_mock:
                        hilo_fake = mock.Mock(start=mock.Mock())
                        crear_hilo_mock.return_value = hilo_fake
                        panel._al_retirar(rid)
                        # cargar fue llamado, y dentro cargar llamó _asegurar_player -> new
                        # como mockeamos crear_hilo, no se ejecutó _run, pero _asegurar_player sí
                        self.assertIn("new", orden)
                        self.assertLess(orden.index("release"), orden.index("new"))

    def test_dos_reconexiones_solo_ultima(self):
        player_viejo = mock.Mock(set_hwnd=mock.Mock(), stop=mock.Mock(), release=mock.Mock())
        inst = mock.Mock(media_player_new=mock.Mock(return_value=mock.Mock(set_hwnd=mock.Mock(), event_manager=mock.Mock(return_value=mock.Mock(event_attach=mock.Mock())))))
        panel = _panel_base(player=player_viejo, inst=inst)
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=1))
        app_mock = mock.Mock()
        # detener con hilo real pero stop no bloquea mucho
        with mock.patch.object(reproductor.wx, "GetApp", return_value=app_mock), \
             mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda fn, *a, **kw: None), \
             mock.patch.object(reproductor, "anunciar"):
            panel.detener_todo()
            time.sleep(0.05)
            panel.set_video("UNO", autoplay=True)
            panel.set_video("DOS", autoplay=True)
            self.assertEqual(panel._ciclo.pendiente.valor, "DOS")
            panel.set_flujo("https://flujo", autoplay=True)
            self.assertEqual(panel._ciclo.pendiente.valor, "https://flujo")
            self.assertEqual(panel._ciclo.pendiente.tipo, "flujo")

    def test_desconectar_cancela_carga_diferida(self):
        player_viejo = mock.Mock(set_hwnd=mock.Mock(), stop=mock.Mock(), release=mock.Mock())
        inst = mock.Mock(media_player_new=mock.Mock(return_value=mock.Mock(set_hwnd=mock.Mock(), event_manager=mock.Mock(return_value=mock.Mock(event_attach=mock.Mock())))))
        panel = _panel_base(player=player_viejo, inst=inst)
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=1))
        app_mock = mock.Mock()
        with mock.patch.object(reproductor.wx, "GetApp", return_value=app_mock), \
             mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda fn, *a, **kw: None), \
             mock.patch.object(reproductor, "anunciar"):
            panel.detener_todo()
            time.sleep(0.05)
            panel.set_video("PENDIENTE", autoplay=True)
            self.assertIsNotNone(panel._ciclo.pendiente)
            panel.detener_todo()
            self.assertIsNone(panel._ciclo.pendiente)
            # el segundo detener_todo no debe crear nueva retirada porque player ya es None
            self.assertTrue(panel._ciclo.en_retirada)
            rid = panel._ciclo.id_actual
            with mock.patch.object(panel, "cargar") as cargar_mock, \
                 mock.patch.object(panel, "set_flujo") as flujo_mock:
                panel._al_retirar(rid)
                cargar_mock.assert_not_called()
                flujo_mock.assert_not_called()

    def test_callback_viejo_inerte(self):
        panel = _panel_base(player=mock.Mock(set_hwnd=mock.Mock(), stop=mock.Mock(), release=mock.Mock()), inst=mock.Mock())
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=1))
        # simular dos retiradas: primera con rid1, segunda con rid2
        rid1 = panel._ciclo.iniciar_retirada()
        panel._ciclo.diferir_video("VID1", True)
        rid2 = panel._ciclo.iniciar_retirada()
        panel._ciclo.diferir_video("VID2", True)
        with mock.patch.object(panel, "set_video") as sv, \
             mock.patch.object(panel, "set_flujo") as sf:
            panel._al_retirar(rid1)
            sv.assert_not_called()
            sf.assert_not_called()
            panel._al_retirar(rid2)
            sv.assert_called_once_with("VID2", autoplay=True)

    def test_sin_retirada_ruta_inmediata(self):
        inst = mock.Mock(media_player_new=mock.Mock(return_value=mock.Mock(set_hwnd=mock.Mock(), event_manager=mock.Mock(return_value=mock.Mock(event_attach=mock.Mock())))))
        panel = _panel_base(player=None, inst=inst)
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=1))
        panel._fijar_salida = mock.Mock()
        panel._enganchar_eventos_vlc = mock.Mock()
        panel._asegurar_instancia = mock.Mock(return_value=True)
        self.assertFalse(panel._ciclo.en_retirada)
        with mock.patch.object(reproductor, "anunciar"):
            with mock.patch.object(reproductor.diagnostico, "crear_hilo") as crear:
                crear.return_value = mock.Mock(start=mock.Mock())
                panel.set_video("INMEDIATO", autoplay=False)
                # set_video con autoplay False no llama a cargar, pero debe haber pasado por _detener y no diferir
                self.assertIsNone(panel._ciclo.pendiente)
            # flujo inmediato
            panel.set_flujo("https://flujo", autoplay=False)
            self.assertIsNone(panel._ciclo.pendiente)

    def test_no_callafter_sin_app(self):
        evento = threading.Event()
        player_viejo = mock.Mock(set_hwnd=mock.Mock(), stop=mock.Mock(side_effect=lambda: evento.wait(timeout=0.01)), release=mock.Mock())
        inst = mock.Mock(media_player_new=mock.Mock(return_value=mock.Mock()))
        panel = _panel_base(player=player_viejo, inst=inst)
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=1))
        with mock.patch.object(reproductor.wx, "GetApp", return_value=None), \
             mock.patch.object(reproductor.wx, "CallAfter") as ca:
            panel.detener_todo()
            evento.set()
            time.sleep(0.1)
            ca.assert_not_called()
            self.assertTrue(panel._ciclo.en_retirada)
            # aun con callback pendiente, si app desaparece, _al_retirar no se programa
            # al volver app, el siguiente _al_retirar con rid correcto sí debe funcionar
            rid = panel._ciclo.id_actual
            with mock.patch.object(reproductor.wx, "GetApp", return_value=mock.Mock()), \
                 mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda fn, *a, **kw: fn(*a, **kw)):
                # simular que ahora sí hay app y se llama manualmente
                panel._al_retirar(rid)
                self.assertFalse(panel._ciclo.en_retirada)

    def test_anuncio_una_vez_y_no_reemplaza_reproduciendo(self):
        player_viejo = mock.Mock(set_hwnd=mock.Mock(), stop=mock.Mock(), release=mock.Mock())
        inst = mock.Mock(media_player_new=mock.Mock(return_value=mock.Mock(set_hwnd=mock.Mock(), event_manager=mock.Mock(return_value=mock.Mock(event_attach=mock.Mock())))))
        panel = _panel_base(player=player_viejo, inst=inst)
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=1))
        app_mock = mock.Mock()
        with mock.patch.object(reproductor.wx, "GetApp", return_value=app_mock), \
             mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda fn, *a, **kw: None), \
             mock.patch.object(reproductor, "anunciar") as anunciar:
            panel.detener_todo()
            time.sleep(0.05)
            panel.set_video("A", autoplay=True)
            panel.set_video("B", autoplay=True)
            panel.set_flujo("https://x", autoplay=True)
            # solo un anuncio de cerrando
            cerrando_calls = [c for c in anunciar.call_args_list if "Cerrando" in str(c)]
            self.assertEqual(len(cerrando_calls), 1)
            self.assertEqual(panel.lbl_estado.SetLabel.call_count, 3)
        # al reanudar con vídeo, cargar anuncia Cargando vídeo, no Reproducindo aún
        panel2 = _panel_base(player=mock.Mock(set_hwnd=mock.Mock(), stop=mock.Mock(), release=mock.Mock()), inst=inst)
        panel2._video = mock.Mock(GetHandle=mock.Mock(return_value=1))
        app_mock2 = mock.Mock()
        with mock.patch.object(reproductor.wx, "GetApp", return_value=app_mock2), \
             mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda fn, *a, **kw: None), \
             mock.patch.object(reproductor, "anunciar") as anunciar2:
            panel2.detener_todo()
            time.sleep(0.05)
            panel2.set_video("VID_RESUME", autoplay=True)
            rid = panel2._ciclo.id_actual
            with mock.patch.object(panel2, "cargar") as cargar_mock:
                def fake_cargar(reproducir=True):
                    anunciar2("Cargando vídeo")
                cargar_mock.side_effect = fake_cargar
                panel2._al_retirar(rid)
                anunciar2.assert_any_call("Cargando vídeo")
                # no debe anunciar Reproducindo en este punto
                repro_calls = [c for c in anunciar2.call_args_list if "Reproduc" in str(c)]
                self.assertEqual(len(repro_calls), 0)

    def test_cableado_detener_y_set_video_con_evento_real(self):
        # caso obligatorio: atraviesa detener_todo y set_video con trabajador real bloqueado
        evento = threading.Event()
        player_viejo = mock.Mock(set_hwnd=mock.Mock(), stop=mock.Mock(side_effect=lambda: evento.wait(timeout=2)), release=mock.Mock())
        nuevo = mock.Mock(set_hwnd=mock.Mock(), event_manager=mock.Mock(return_value=mock.Mock(event_attach=mock.Mock())))
        inst = mock.Mock(media_player_new=mock.Mock(return_value=nuevo))
        panel = _panel_base(player=player_viejo, inst=inst)
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=7))
        panel._fijar_salida = mock.Mock()
        panel._enganchar_eventos_vlc = mock.Mock()
        panel._asegurar_instancia = mock.Mock(return_value=True)
        app_mock = mock.Mock()
        with mock.patch.object(reproductor.wx, "GetApp", return_value=app_mock), \
             mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda fn, *a, **kw: None), \
             mock.patch.object(reproductor, "anunciar"):
            panel.detener_todo()
            time.sleep(0.05)
            self.assertTrue(panel._ciclo.en_retirada)
            panel.set_video("REAL", autoplay=True)
            self.assertIsNotNone(panel._ciclo.pendiente)
            # liberar
            evento.set()
            time.sleep(0.15)
            rid = panel._ciclo.id_actual
            with mock.patch.object(reproductor.diagnostico, "crear_hilo") as crear_hilo:
                crear_hilo.return_value = mock.Mock(start=mock.Mock())
                panel._al_retirar(rid)
                # al retirar debe haber intentado cargar (que llama _asegurar_player -> new)
                # verificamos que se llamó a media_player_new a través de cargar
                # como mockeamos crear_hilo, _asegurar_player se ejecuta dentro de cargar
                self.assertFalse(panel._ciclo.en_retirada)
                self.assertIsNone(panel._ciclo.pendiente)

    def test_cableado_detener_y_set_flujo(self):
        evento = threading.Event()
        player_viejo = mock.Mock(set_hwnd=mock.Mock(), stop=mock.Mock(side_effect=lambda: evento.wait(timeout=2)), release=mock.Mock())
        nuevo = mock.Mock(set_hwnd=mock.Mock(), event_manager=mock.Mock(return_value=mock.Mock(event_attach=mock.Mock())))
        inst = mock.Mock(media_player_new=mock.Mock(return_value=nuevo))
        panel = _panel_base(player=player_viejo, inst=inst)
        panel._video = mock.Mock(GetHandle=mock.Mock(return_value=7))
        panel._fijar_salida = mock.Mock()
        panel._enganchar_eventos_vlc = mock.Mock()
        panel._asegurar_instancia = mock.Mock(return_value=True)
        app_mock = mock.Mock()
        with mock.patch.object(reproductor.wx, "GetApp", return_value=app_mock), \
             mock.patch.object(reproductor.wx, "CallAfter", side_effect=lambda fn, *a, **kw: None), \
             mock.patch.object(reproductor, "anunciar"):
            panel.detener_todo()
            time.sleep(0.05)
            panel.set_flujo("https://flujo-real", autoplay=True)
            self.assertEqual(panel._ciclo.pendiente.tipo, "flujo")
            evento.set()
            time.sleep(0.15)
            rid = panel._ciclo.id_actual
            with mock.patch.object(panel, "_reproducir_flujo") as rep_mock:
                panel._al_retirar(rid)
                rep_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
