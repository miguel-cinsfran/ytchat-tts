"""Pruebas de las decisiones puras del reproductor."""

import unittest
import time
from unittest import mock
from types import SimpleNamespace

from busqueda_video import (
    CADUCIDAD_DESTINO_MS, EstadoBusqueda, PROGRESO_MINIMO_MS,
    TOLERANCIA_ATRAS_MS, TOLERANCIA_DESTINO_MS, TOPE_BUSQUEDA_MS,
    accion_play_pausa, destino_acumulado, destino_alcanzado, destino_vigente,
    posicion_a_mostrar, posicion_confiable, transporte_confirmado,
)


class TestDestinoAcumulado(unittest.TestCase):

    def test_empieza_en_la_posicion_real_si_no_hay_salto_pendiente(self):
        self.assertEqual(destino_acumulado(None, 10_000, 10_000, 60_000), 20_000)

    def test_acumula_sobre_el_salto_pendiente(self):
        self.assertEqual(destino_acumulado(20_000, 10_000, 10_000, 60_000), 30_000)

    def test_recorta_en_los_dos_extremos(self):
        self.assertEqual(destino_acumulado(None, 1_000, -10_000, 60_000), 0)
        self.assertEqual(destino_acumulado(None, 59_000, 10_000, 60_000), 60_000)

    def test_caso_real_sin_destino_pendiente_con_duracion_atrasada_conserva_base(self):
        self.assertEqual(destino_acumulado(None, 3_615_868, 60_000, 3_600_000), 3_615_868)

    def test_caso_real_con_destino_pendiente_con_duracion_atrasada_conserva_base(self):
        self.assertEqual(destino_acumulado(3_615_868, 3_000_000, 60_000, 3_600_000), 3_615_868)

    def test_avance_con_duracion_por_delante_recorta_a_duracion(self):
        self.assertEqual(destino_acumulado(None, 50_000, 20_000, 60_000), 60_000)

    def test_avance_con_destino_pendiente_y_duracion_por_delante_recorta(self):
        self.assertEqual(destino_acumulado(50_000, 10_000, 20_000, 60_000), 60_000)

    def test_avance_no_retrocede_monotonia(self):
        for base, delta, dur in [
            (3_615_868, 60_000, 3_600_000),
            (50_000, 20_000, 60_000),
            (10_000, 5_000, 60_000),
            (0, 10_000, 5_000),
        ]:
            with self.subTest(base=base, delta=delta, dur=dur):
                destino = destino_acumulado(None, base, delta, dur)
                self.assertGreaterEqual(destino, base)

    def test_retroceso_no_avanza_monotonia(self):
        for base, delta, dur in [
            (3_615_868, -10_000, 3_600_000),
            (50_000, -20_000, 60_000),
            (10_000, -5_000, 60_000),
        ]:
            with self.subTest(base=base, delta=delta, dur=dur):
                destino = destino_acumulado(None, base, delta, dur)
                self.assertLessEqual(destino, base)

    def test_retroceso_con_duracion_atrasada_recorta_por_duracion(self):
        self.assertEqual(destino_acumulado(None, 3_615_868, -10_000, 3_600_000), 3_600_000)

    def test_retroceso_respeta_limite_cero(self):
        self.assertEqual(destino_acumulado(None, 5_000, -10_000, 60_000), 0)

    def test_acumulacion_sobre_destino_pendiente_respeta_monotonia_avance(self):
        destino = destino_acumulado(3_615_868, 3_600_000, 60_000, 3_600_000)
        self.assertGreaterEqual(destino, 3_615_868)


class TestDestinoAlcanzado(unittest.TestCase):

    def test_sin_destino_pendiente_esta_alcanzado(self):
        self.assertTrue(destino_alcanzado(None, 0, TOLERANCIA_DESTINO_MS))

    def test_acepta_la_tolerancia_en_ambos_sentidos(self):
        self.assertTrue(destino_alcanzado(10_000, 8_500, TOLERANCIA_DESTINO_MS))
        self.assertTrue(destino_alcanzado(10_000, 11_500, TOLERANCIA_DESTINO_MS))
        self.assertFalse(destino_alcanzado(10_000, 8_499, TOLERANCIA_DESTINO_MS))


class TestPosicionAMostrar(unittest.TestCase):

    def test_prioriza_el_destino_pendiente(self):
        self.assertEqual(posicion_a_mostrar(20_000, 10_000), 20_000)

    def test_usa_la_posicion_real_sin_destino(self):
        self.assertEqual(posicion_a_mostrar(None, 10_000), 10_000)


class TestAccionPlayPausa(unittest.TestCase):

    def test_sin_medio_carga(self):
        self.assertEqual(accion_play_pausa("playing", False, True), "cargar")

    def test_estados_estables(self):
        self.assertEqual(accion_play_pausa("playing", True, True), "pausar")
        self.assertEqual(accion_play_pausa("paused", True, False), "reanudar")

    def test_estados_finales_recargan(self):
        for estado in ("ended", "stopped", "error", "nothingspecial"):
            with self.subTest(estado=estado):
                self.assertEqual(accion_play_pausa(estado, True, False), "cargar")

    def test_estados_transitorios_siguen_la_intencion(self):
        for estado in ("opening", "buffering", "futuro"):
            with self.subTest(estado=estado):
                self.assertEqual(accion_play_pausa(estado, True, True), "pausar")
                self.assertEqual(accion_play_pausa(estado, True, False), "reanudar")

    def test_orden_pendiente_contraria_en_reproduccion(self):
        self.assertEqual(accion_play_pausa("playing", True, False, True), "en_curso")

    def test_orden_pendiente_contraria_en_pausa(self):
        self.assertEqual(accion_play_pausa("paused", True, True, True), "en_curso")

    def test_orden_vencida_devuelve_el_estado_real(self):
        self.assertEqual(accion_play_pausa("playing", True, False, False), "pausar")

    def test_propiedad_valores_conocidos(self):
        estados = ("playing", "paused", "opening", "buffering", "ended", "stopped", "error", "nothingspecial", "otro")
        for estado in estados:
            for intencion in (False, True):
                for reciente in (False, True):
                    with self.subTest(estado=estado, intencion=intencion, reciente=reciente):
                        self.assertIn(accion_play_pausa(estado, True, intencion, reciente),
                                      {"cargar", "pausar", "reanudar", "en_curso"})


class TestTransporteConfirmado(unittest.TestCase):

    def test_pausa_solo_paused_confirma(self):
        self.assertTrue(transporte_confirmado("paused", False))
        self.assertFalse(transporte_confirmado("playing", False))
        self.assertFalse(transporte_confirmado("opening", False))
        self.assertFalse(transporte_confirmado("buffering", False))
        for estado in ("ended", "stopped", "error", "nothingspecial", "otro"):
            with self.subTest(estado=estado):
                self.assertFalse(transporte_confirmado(estado, False))

    def test_reanudacion_solo_playing_confirma(self):
        self.assertTrue(transporte_confirmado("playing", True))
        self.assertFalse(transporte_confirmado("paused", True))
        self.assertFalse(transporte_confirmado("opening", True))
        self.assertFalse(transporte_confirmado("buffering", True))
        for estado in ("ended", "stopped", "error", "nothingspecial", "otro"):
            with self.subTest(estado=estado):
                self.assertFalse(transporte_confirmado(estado, True))


class TestAccionConPendiente(unittest.TestCase):

    def test_pendiente_pausa_con_playing_da_en_curso(self):
        self.assertEqual(accion_play_pausa("playing", True, False, True), "en_curso")

    def test_pendiente_reanudar_con_paused_da_en_curso(self):
        self.assertEqual(accion_play_pausa("paused", True, True, True), "en_curso")

    def test_transitorio_con_pendiente_da_en_curso(self):
        for estado in ("opening", "buffering", "otro"):
            with self.subTest(estado=estado):
                self.assertEqual(accion_play_pausa(estado, True, True, True), "en_curso")
                self.assertEqual(accion_play_pausa(estado, True, False, True), "en_curso")

    def test_pendiente_no_bloquea_estados_finales(self):
        for estado in ("ended", "stopped", "error", "nothingspecial"):
            with self.subTest(estado=estado):
                self.assertEqual(accion_play_pausa(estado, True, False, True), "cargar")
                self.assertEqual(accion_play_pausa(estado, True, True, True), "cargar")

    def test_pendiente_confirmado_no_bloquea(self):
        self.assertEqual(accion_play_pausa("paused", True, False, True), "reanudar")
        self.assertEqual(accion_play_pausa("playing", True, True, True), "pausar")

    def test_sin_pendiente_transitorio_sigue_intencion(self):
        self.assertEqual(accion_play_pausa("opening", True, True, False), "pausar")
        self.assertEqual(accion_play_pausa("buffering", True, False, False), "reanudar")


class TestPosicionConfiable(unittest.TestCase):

    def test_retroceso_a_cero_se_descarta(self):
        self.assertEqual(posicion_confiable(31038, 0, 2000), 31038)

    def test_retroceso_grande_se_descarta(self):
        self.assertEqual(posicion_confiable(31038, 18812, 2000), 31038)

    def test_retroceso_dentro_de_tolerancia_se_conserva(self):
        self.assertEqual(posicion_confiable(31038, 30000, 2000), 30000)

    def test_avance_se_conserva(self):
        self.assertEqual(posicion_confiable(31038, 41000, 2000), 41000)

    def test_sin_ultima_lectura_acepta_cero(self):
        self.assertEqual(posicion_confiable(None, 0, 2000), 0)


class TestDestinoVigente(unittest.TestCase):

    def test_destino_vencido_caduca(self):
        self.assertIsNone(destino_vigente(776139, 43000, 5000))

    def test_destino_reciente_se_conserva(self):
        self.assertEqual(destino_vigente(776139, 1200, 5000), 776139)

    def test_sin_destino_sigue_vacio(self):
        self.assertIsNone(destino_vigente(None, 43000, 5000))


class TestCableadoBusqueda(unittest.TestCase):

    def test_pulsaciones_rapidas_acumulan_desde_el_destino_pendiente(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 60_000
        panel._player.get_time.return_value = 10_000
        panel._estado_busqueda = reproductor.EstadoBusqueda(confirmada=10_000)
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._url_flujo = ""
        panel._fijar_tiempo = mock.Mock()
        panel.sld_pos = mock.Mock()

        with mock.patch.object(reproductor, "anunciar"):
            panel._buscar_rel(10_000)
            panel._buscar_rel(10_000)

        self.assertEqual(panel._player.set_time.call_args_list,
                         [mock.call(20_000), mock.call(30_000)])

    def test_salto_no_vuelve_a_cero_con_lectura_atrasada(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 60_000
        panel._player.get_time.return_value = 0
        panel._estado_busqueda = reproductor.EstadoBusqueda(confirmada=31_038)
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._url_flujo = ""
        panel._fijar_tiempo = mock.Mock()

        panel._buscar_rel(-10_000)

        panel._player.set_time.assert_called_once_with(21_038)

    def test_salto_siguiente_conserva_como_referencia_el_destino_anterior(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 60_000
        panel._estado_busqueda = reproductor.EstadoBusqueda(confirmada=5_000)
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._url_flujo = ""
        panel._fijar_tiempo = mock.Mock()

        panel._buscar_rel(20_000)
        # aún pendiente, acumula sobre destino anterior
        panel._buscar_rel(10_000)

        self.assertEqual(panel._player.set_time.call_args_list,
                         [mock.call(25_000), mock.call(35_000)])

    def test_on_timer_con_salto_en_vuelo_conserva_el_destino_pendiente(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 60_000
        panel._player.get_time.return_value = 10_000
        panel._player.get_state.return_value = SimpleNamespace(name="playing")
        panel._estado_busqueda = reproductor.EstadoBusqueda(confirmada=0)
        panel._estado_busqueda.destino = 30_000
        panel._estado_busqueda.marca_destino = __import__("time").monotonic()
        panel._estado_busqueda._gen = 1
        panel._muted = False
        panel._marca_url = None
        panel._fijar_tiempo = mock.Mock()
        panel.sld_pos = mock.Mock()
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._url_flujo = ""

        estado_vlc = SimpleNamespace(State=SimpleNamespace(
            Playing="playing", Ended="ended"))
        with mock.patch.object(reproductor, "_vlc", estado_vlc):
            with mock.patch.object(reproductor.wx.Window, "FindFocus",
                                   return_value=None):
                panel._on_timer(None)

        self.assertEqual(panel._estado_busqueda.destino, 30_000)
        panel._fijar_tiempo.assert_called_once_with(
            0, 60_000, mover_slider=True, anunciar_t=False)

    def test_on_timer_al_alcanzar_el_salto_limpia_el_destino_pendiente(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 60_000
        panel._player.get_time.return_value = 29_000
        panel._player.get_state.return_value = SimpleNamespace(name="playing")
        panel._muted = False
        panel._marca_url = None
        panel._fijar_tiempo = mock.Mock()
        panel.sld_pos = mock.Mock()
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._url_flujo = ""
        bus = reproductor.EstadoBusqueda(confirmada=0)
        bus.solicitar(30_000, __import__("time").monotonic() - 0.1)
        bus.candidato = 29_000
        panel._estado_busqueda = bus

        estado_vlc = SimpleNamespace(State=SimpleNamespace(
            Playing="playing", Ended="ended"))
        with mock.patch.object(reproductor, "_vlc", estado_vlc):
            with mock.patch.object(reproductor.wx.Window, "FindFocus",
                                   return_value=None):
                with mock.patch.object(reproductor, "anunciar") as anunciar:
                    panel._player.get_time.return_value = 29_300
                    panel._player.get_state.return_value = SimpleNamespace(name="playing")
                    panel._on_timer(None)

        self.assertIsNone(panel._estado_busqueda.destino)
        self.assertEqual(panel._estado_busqueda.confirmada, 29_300)
        anunciar.assert_called_once()
        self.assertIn("Posición", anunciar.call_args[0][0])

    def test_buscar_rel_caso_real_con_duracion_atrasada_no_retrocede(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 3_600_000
        panel._player.get_time.return_value = 3_615_868
        panel._estado_busqueda = reproductor.EstadoBusqueda(confirmada=3_615_868)
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._url_flujo = ""
        panel._fijar_tiempo = mock.Mock()
        panel.sld_pos = mock.Mock()
        panel._tiene_esclavo = False

        with mock.patch.object(reproductor, "anunciar"):
            panel._buscar_rel(60_000)

        panel._player.set_time.assert_called_once_with(3_615_868)
        self.assertEqual(panel._estado_busqueda.destino, 3_615_868)
        self.assertEqual(panel._fijar_tiempo.call_args[0][0], 3_615_868)
        self.assertEqual(panel._fijar_tiempo.call_args[0][1], 3_600_000)

    def test_deslizador_con_busqueda_pendiente_es_absoluto(self):
        import reproductor
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 100_000
        panel._player.get_time.return_value = 10_000
        panel._estado_busqueda = reproductor.EstadoBusqueda(confirmada=10_000)
        panel._estado_busqueda.solicitar(20_000, time.monotonic())
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._url_flujo = ""
        panel._fijar_tiempo = mock.Mock()
        panel.sld_pos = mock.Mock()
        panel.sld_pos.GetValue.return_value = 300
        with mock.patch.object(reproductor, "anunciar"):
            panel._on_sld_pos(None)
        panel._player.set_time.assert_called_once_with(30_000)
        self.assertEqual(panel._estado_busqueda.destino, 30_000)

    def test_porcentaje_con_busqueda_pendiente_es_absoluto(self):
        import reproductor
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 100_000
        panel._estado_busqueda = reproductor.EstadoBusqueda(confirmada=10_000)
        panel._estado_busqueda.solicitar(20_000, time.monotonic())
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._url_flujo = ""
        panel._fijar_tiempo = mock.Mock()
        panel.sld_pos = mock.Mock()
        with mock.patch.object(reproductor, "anunciar"):
            panel._buscar_porcentaje(30)
        panel._player.set_time.assert_called_once_with(30_000)
        self.assertEqual(panel._estado_busqueda.destino, 30_000)


class TestCableadoPlayPausa(unittest.TestCase):

    def test_orden_en_curso_no_invierte_ni_anuncia(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_state.return_value = SimpleNamespace(name="playing")
        panel._video_id = "video-cargado"
        panel._url_flujo = ""
        panel._intencion_reproducir = False
        panel._transporte_pendiente = True
        panel._asegurar_player = mock.Mock(return_value=True)
        panel._timer = mock.Mock()
        panel._mostrar_pausa = mock.Mock()

        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch("sound_player.reproducir") as sonido:
            panel._toggle_play()

        panel._player.set_pause.assert_not_called()
        panel._timer.stop.assert_not_called()
        anunciar.assert_not_called()
        sonido.assert_called_once_with("transporte_en_curso")

    def test_buffering_pausa_sin_recargar_el_video(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_state.return_value = SimpleNamespace(name="Buffering")
        panel._video_id = "video-cargado"
        panel._url_flujo = ""
        panel._intencion_reproducir = True
        panel._transporte_pendiente = False
        panel._asegurar_player = mock.Mock(return_value=True)
        panel._mostrar_pausa = mock.Mock()
        panel._timer = mock.Mock()
        panel.cargar = mock.Mock()

        with mock.patch.object(reproductor, "anunciar"):
            panel._toggle_play()

        panel._player.set_pause.assert_called_once_with(1)
        panel.cargar.assert_not_called()


class TestPendienteSecuencial(unittest.TestCase):

    def _panel_pausa(self):
        import reproductor
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_state.return_value = SimpleNamespace(name="playing")
        panel._player.can_pause.return_value = 1
        panel._player.is_seekable.return_value = 1
        panel._listo = True
        panel._video_id = "video-cargado"
        panel._url_flujo = ""
        panel._intencion_reproducir = True
        panel._transporte_pendiente = False
        panel._asegurar_player = mock.Mock(return_value=True)
        panel._mostrar_pausa = mock.Mock()
        panel._timer = mock.Mock()
        panel.cargar = mock.Mock()
        panel._reproducir_flujo = mock.Mock()
        return panel

    def _panel_reanudar(self):
        import reproductor
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_state.return_value = SimpleNamespace(name="paused")
        panel._player.can_pause.return_value = 1
        panel._player.is_seekable.return_value = 1
        panel._listo = True
        panel._video_id = "video-cargado"
        panel._url_flujo = ""
        panel._intencion_reproducir = False
        panel._transporte_pendiente = False
        panel._asegurar_player = mock.Mock(return_value=True)
        panel._mostrar_pausa = mock.Mock()
        panel._timer = mock.Mock()
        panel.cargar = mock.Mock()
        panel._reproducir_flujo = mock.Mock()
        return panel

    def test_secuencia_pausa_permanece_pendiente_mucho_despues_de_tres_segundos(self):
        import reproductor
        panel = self._panel_pausa()
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch("sound_player.reproducir") as sonido:
            panel._toggle_play()
            self.assertEqual(panel._player.set_pause.call_count, 1)
            self.assertEqual(panel._player.set_pause.call_args[0][0], 1)
            self.assertFalse(panel._intencion_reproducir)
            self.assertTrue(panel._transporte_pendiente)
            anunciar.assert_called_once_with("Pausa")
            panel._mostrar_pausa.assert_called_once_with(False)
            anunciar.reset_mock()
            panel._mostrar_pausa.reset_mock()
            sonido.reset_mock()
            # Mucho después de tres segundos, VLC sigue en playing sin confirmar
            panel._player.set_pause.reset_mock()
            with mock.patch.object(reproductor.time, "monotonic", return_value=99999):
                panel._toggle_play()
            panel._player.set_pause.assert_not_called()
            anunciar.assert_not_called()
            panel._mostrar_pausa.assert_not_called()
            sonido.assert_called_once_with("transporte_en_curso")
            self.assertTrue(panel._transporte_pendiente)
            sonido.reset_mock()
            # VLC por fin informa paused: la siguiente pulsación libera y reanuda
            panel._player.get_state.return_value = SimpleNamespace(name="paused")
            panel._player.set_pause.reset_mock()
            panel._toggle_play()
            panel._player.set_pause.assert_called_once_with(0)
            self.assertTrue(panel._intencion_reproducir)
            self.assertTrue(panel._transporte_pendiente)
            anunciar.assert_called_once_with("Reproduciendo")
            panel._mostrar_pausa.assert_called_once_with(True)

    def test_secuencia_reanudar_permanece_pendiente_mucho_despues(self):
        import reproductor
        panel = self._panel_reanudar()
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch("sound_player.reproducir") as sonido:
            panel._toggle_play()
            self.assertEqual(panel._player.set_pause.call_args[0][0], 0)
            self.assertTrue(panel._intencion_reproducir)
            self.assertTrue(panel._transporte_pendiente)
            anunciar.assert_called_once_with("Reproduciendo")
            anunciar.reset_mock()
            panel._mostrar_pausa.reset_mock()
            sonido.reset_mock()
            panel._player.set_pause.reset_mock()
            # Mantener paused sin confirmar, incluso muy tarde
            with mock.patch.object(reproductor.time, "monotonic", return_value=99999):
                panel._toggle_play()
            panel._player.set_pause.assert_not_called()
            anunciar.assert_not_called()
            sonido.assert_called_once_with("transporte_en_curso")
            sonido.reset_mock()
            # VLC informa playing
            panel._player.get_state.return_value = SimpleNamespace(name="playing")
            panel._player.set_pause.reset_mock()
            panel._toggle_play()
            panel._player.set_pause.assert_called_once_with(1)
            self.assertFalse(panel._intencion_reproducir)
            anunciar.assert_called_once_with("Pausa")

    def test_transitorio_no_confirma_y_mantiene_en_curso(self):
        import reproductor
        panel = self._panel_pausa()
        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch("sound_player.reproducir"):
            panel._toggle_play()
        self.assertTrue(panel._transporte_pendiente)
        panel._player.get_state.return_value = SimpleNamespace(name="opening")
        panel._player.set_pause.reset_mock()
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch("sound_player.reproducir") as sonido:
            panel._toggle_play()
        panel._player.set_pause.assert_not_called()
        anunciar.assert_not_called()
        sonido.assert_called_once_with("transporte_en_curso")
        # buffering tampoco confirma
        panel._player.get_state.return_value = SimpleNamespace(name="buffering")
        panel._player.set_pause.reset_mock()
        sonido.reset_mock()
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch("sound_player.reproducir") as sonido:
            panel._toggle_play()
        panel._player.set_pause.assert_not_called()
        sonido.assert_called_once_with("transporte_en_curso")

    def test_cancelacion_al_detener_y_cargar(self):
        import reproductor
        # Al detener
        panel = self._panel_pausa()
        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch("sound_player.reproducir"):
            panel._toggle_play()
        self.assertTrue(panel._transporte_pendiente)
        panel._timer_progreso = mock.Mock()
        panel._gen = 0
        panel._tarea_cache_video = None
        panel.lbl_estado = mock.Mock()
        panel.btn_play = mock.Mock()
        panel._fijar_tiempo = mock.Mock()
        panel._detener(silencioso=True)
        self.assertFalse(panel._transporte_pendiente)
        # Siguiente toggle sin pendiente debe actuar normal
        panel._player.get_state.return_value = SimpleNamespace(name="paused")
        panel._intencion_reproducir = False
        panel._transporte_pendiente = False
        panel._player.set_pause.reset_mock()
        with mock.patch.object(reproductor, "anunciar") as anunciar, \
                mock.patch("sound_player.reproducir") as sonido:
            panel._toggle_play()
        panel._player.set_pause.assert_called_once_with(0)
        anunciar.assert_called_once_with("Reproduciendo")
        # Al cargar otro medio
        panel2 = self._panel_pausa()
        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch("sound_player.reproducir"):
            panel2._toggle_play()
        self.assertTrue(panel2._transporte_pendiente)
        panel2._cargando = False
        panel2._gen = 0
        panel2.lbl_estado = mock.Mock()
        panel2._timer_progreso = mock.Mock()
        panel2._asegurar_player = mock.Mock(return_value=True)
        # restaurar el método real de cargar para probar la cancelación
        panel2.cargar = reproductor.ReproductorPanel.cargar.__get__(panel2, reproductor.ReproductorPanel)
        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch.object(reproductor.diagnostico, "crear_hilo") as crear:
            crear.return_value.start = mock.Mock()
            panel2.cargar(reproducir=True)
        self.assertFalse(panel2._transporte_pendiente)

    def test_estado_final_no_queda_bloqueado_por_pendiente(self):
        import reproductor
        panel = self._panel_pausa()
        with mock.patch.object(reproductor, "anunciar"), \
                mock.patch("sound_player.reproducir"):
            panel._toggle_play()
        self.assertTrue(panel._transporte_pendiente)
        for estado in ("ended", "stopped", "error", "nothingspecial"):
            panel._player.get_state.return_value = SimpleNamespace(name=estado)
            panel.cargar = mock.Mock()
            with mock.patch.object(reproductor, "anunciar"), \
                    mock.patch("sound_player.reproducir") as sonido:
                panel._toggle_play()
            panel.cargar.assert_called_once_with(reproducir=True)
            sonido.assert_not_called()
            panel.cargar.reset_mock()


class TestEstadoBusquedaFronteras(unittest.TestCase):

    def test_muestra_igual_no_confirma(self):
        bus = EstadoBusqueda(confirmada=10_000)
        ahora = time.monotonic()
        bus.solicitar(60_000, ahora)
        ev, _ = bus.observar(60_000, 300_000, "playing", ahora + 0.5)
        self.assertEqual(ev, "candidato")
        self.assertEqual(bus.confirmada, 10_000)
        ev, _ = bus.observar(60_000, 300_000, "playing", ahora + 1.0)
        self.assertIsNone(ev)
        self.assertEqual(bus.confirmada, 10_000)
        self.assertIsNotNone(bus.destino)

    def test_dos_muestras_con_250_confirman(self):
        bus = EstadoBusqueda(confirmada=5_000)
        ahora = time.monotonic()
        bus.solicitar(60_000, ahora)
        ev, _ = bus.observar(60_000, 300_000, "playing", ahora + 0.2)
        self.assertEqual(ev, "candidato")
        ev, valor = bus.observar(60_300, 300_000, "playing", ahora + 0.7)
        self.assertEqual(ev, "confirmado")
        self.assertEqual(valor, 60_300)
        self.assertEqual(bus.confirmada, 60_300)
        self.assertIsNone(bus.destino)
        self.assertIsNone(bus.candidato)

    def test_volver_a_cero_lejos_falla(self):
        bus = EstadoBusqueda(confirmada=75_082)
        ahora = time.monotonic()
        bus.solicitar(85_082, ahora)
        ev, valor = bus.observar(0, 300_000, "playing", ahora + 0.5)
        self.assertIsNone(ev)
        self.assertEqual(bus.confirmada, 75_082)
        self.assertEqual(bus.destino, 85_082)
        self.assertIsNone(bus.candidato)
        self.assertEqual(bus._ultima_valida, 0)
        ev, valor = bus.observar(0, 300_000, "playing", ahora + 8.5)
        self.assertEqual(ev, "vencido")
        self.assertEqual(valor, 0)
        self.assertEqual(bus.confirmada, 0)

    def test_destino_cero_confirma_normal(self):
        bus = EstadoBusqueda(confirmada=10_000)
        ahora = time.monotonic()
        bus.solicitar(0, ahora)
        ev, _ = bus.observar(0, 300_000, "playing", ahora + 0.2)
        self.assertEqual(ev, "candidato")
        ev, valor = bus.observar(300, 300_000, "playing", ahora + 0.6)
        self.assertEqual(ev, "confirmado")
        self.assertEqual(valor, 300)
        self.assertEqual(bus.confirmada, 300)

    def test_final_cercano_confirma_sin_250(self):
        dur = 300_000
        dest = 299_000  # a 1000 del final
        bus = EstadoBusqueda(confirmada=10_000)
        ahora = time.monotonic()
        bus.solicitar(dest, ahora)
        ev, valor = bus.observar(299_500, dur, "playing", ahora + 0.5)
        self.assertEqual(ev, "confirmado")
        self.assertEqual(valor, 299_500)
        self.assertIsNone(bus.destino)

    def test_pausa_no_confirma(self):
        bus = EstadoBusqueda(confirmada=5_000)
        ahora = time.monotonic()
        bus.solicitar(20_000, ahora)
        ev, _ = bus.observar(20_000, 100_000, "paused", ahora + 0.5)
        self.assertIsNone(ev)
        self.assertEqual(bus.destino, 20_000)
        self.assertIsNone(bus.candidato)

    def test_lectura_negativa_no_altera(self):
        bus = EstadoBusqueda(confirmada=5_000)
        ahora = time.monotonic()
        bus.solicitar(20_000, ahora)
        ev, _ = bus.observar(-1, 100_000, "playing", ahora + 0.5)
        self.assertIsNone(ev)
        self.assertEqual(bus.confirmada, 5_000)
        self.assertEqual(bus.destino, 20_000)

    def test_estado_final_incompatible_falla(self):
        for estado in ("ended", "stopped", "error", "nothingspecial"):
            with self.subTest(estado=estado):
                bus = EstadoBusqueda(confirmada=10_000)
                ahora = time.monotonic()
                bus.solicitar(20_000, ahora)
                ev, valor = bus.observar(20_000, 100_000, estado, ahora + 0.5)
                self.assertEqual(ev, "fallo")
                self.assertEqual(bus.confirmada, 20_000)

    def test_vencimiento_antes_y_despues_de_8000(self):
        bus = EstadoBusqueda(confirmada=0)
        ahora = time.monotonic()
        bus.solicitar(50_000, ahora)
        ev, _ = bus.observar(10_000, 100_000, "playing", ahora + 7.999)
        # a 7999 ms aún pendiente, lectura lejana ya falla antes del tope, pero probamos con lectura cercana sin progreso
        # usar lectura cercana para no fallar por lejanía
        bus2 = EstadoBusqueda(confirmada=0)
        bus2.solicitar(50_000, ahora)
        bus2.candidato = 50_000
        ev, _ = bus2.observar(50_000, 100_000, "playing", ahora + 7.999)
        self.assertIsNone(ev)
        ev, valor = bus2.observar(50_000, 100_000, "playing", ahora + 8.001)
        self.assertEqual(ev, "vencido")
        self.assertEqual(valor, 50_000)

    def test_pulsaciones_rapidas_acumulan_sin_cambiar_confirmada(self):
        bus = EstadoBusqueda(confirmada=10_000)
        ahora = time.monotonic()
        bus.solicitar(20_000, ahora)
        self.assertEqual(bus.confirmada, 10_000)
        # nueva pulsación acumula sobre destino, reinicia candidato
        bus.solicitar(30_000, ahora + 0.1)
        self.assertEqual(bus.destino, 30_000)
        self.assertIsNone(bus.candidato)
        self.assertEqual(bus.confirmada, 10_000)

    def test_cancelar_limpia_destino_y_candidato(self):
        bus = EstadoBusqueda(confirmada=5_000)
        ahora = time.monotonic()
        bus.solicitar(20_000, ahora)
        bus.candidato = 20_000
        bus.cancelar()
        self.assertIsNone(bus.destino)
        self.assertIsNone(bus.candidato)
        self.assertEqual(bus.confirmada, 5_000)

    def test_generacion_no_revive(self):
        bus = EstadoBusqueda(confirmada=0)
        ahora = time.monotonic()
        bus.solicitar(10_000, ahora)
        gen = bus.generacion
        bus.cancelar()
        # observar tardío con destino viejo no debe revivir
        ev, _ = bus.observar(10_000, 100_000, "playing", ahora + 0.5)
        self.assertIsNone(ev)
        self.assertIsNone(bus.destino)
        self.assertGreater(bus.generacion, gen)

    def test_posicion_a_mostrar_mientras_pendiente(self):
        bus = EstadoBusqueda(confirmada=5_000)
        ahora = time.monotonic()
        bus.solicitar(20_000, ahora)
        self.assertEqual(bus.posicion_a_mostrar(20_000), 5_000)
        self.assertEqual(bus.posicion_a_mostrar(9999), 5_000)
        bus.candidato = 20_000
        self.assertEqual(bus.posicion_a_mostrar(20_100), 5_000)
        bus.confirmada = 20_300
        bus.destino = None
        bus.candidato = None
        self.assertEqual(bus.posicion_a_mostrar(20_300), 20_300)

    def test_fallo_adopta_lectura_aunque_menor(self):
        bus = EstadoBusqueda(confirmada=30_000)
        ahora = time.monotonic()
        bus.solicitar(60_000, ahora)
        ev, _ = bus.observar(0, 300_000, "playing", ahora + 0.5)
        self.assertIsNone(ev)
        self.assertEqual(bus.confirmada, 30_000)
        self.assertEqual(bus._ultima_valida, 0)
        ev, _ = bus.observar(0, 300_000, "playing", ahora + 8.5)
        self.assertEqual(ev, "vencido")
        self.assertEqual(bus.confirmada, 0)

    def test_fallo_sin_lectura_valida_conserva_confirmada(self):
        bus = EstadoBusqueda(confirmada=30_000)
        ahora = time.monotonic()
        bus.solicitar(60_000, ahora)
        ev, _ = bus.observar(-1, 300_000, "playing", ahora + 8.5)
        self.assertEqual(ev, "vencido")
        self.assertIsNone(_)
        self.assertEqual(bus.confirmada, 30_000)


class TestEstadoBusquedaMuestrasLejanas(unittest.TestCase):

    def test_muestra_a_05_queda_pendiente_conserva_confirmada(self):
        bus = EstadoBusqueda(confirmada=10_000)
        bus.solicitar(60_000, ahora=0.0)
        ev, val = bus.observar(10_000, 120_000, "playing", ahora=0.5)
        self.assertIsNone(ev)
        self.assertEqual(bus.confirmada, 10_000)
        self.assertTrue(bus.pendiente)
        self.assertEqual(bus.destino, 60_000)

    def test_cero_lejos_pendiente_y_vencimiento_adopta(self):
        bus = EstadoBusqueda(confirmada=10_000)
        ahora = 0.0
        bus.solicitar(60_000, ahora)
        ev, _ = bus.observar(0, 120_000, "playing", ahora + 0.5)
        self.assertIsNone(ev)
        self.assertEqual(bus.confirmada, 10_000)
        ev, val = bus.observar(0, 120_000, "playing", ahora + 8.5)
        self.assertEqual(ev, "vencido")
        self.assertEqual(val, 0)
        self.assertEqual(bus.confirmada, 0)
        self.assertFalse(bus.pendiente)
        ev2, _ = bus.observar(0, 120_000, "playing", ahora + 9)
        self.assertIsNone(ev2)

    def test_lejana_luego_dos_cercanas_confirma(self):
        bus = EstadoBusqueda(confirmada=5_000)
        ahora = 0.0
        bus.solicitar(60_000, ahora)
        ev, _ = bus.observar(10_000, 120_000, "playing", ahora + 0.2)
        self.assertIsNone(ev)
        self.assertIsNone(bus.candidato)
        ev, _ = bus.observar(60_000, 120_000, "playing", ahora + 0.4)
        self.assertEqual(ev, "candidato")
        ev, val = bus.observar(60_300, 120_000, "playing", ahora + 0.7)
        self.assertEqual(ev, "confirmado")
        self.assertEqual(val, 60_300)

    def test_cercana_luego_lejana_descarta_candidato(self):
        bus = EstadoBusqueda(confirmada=5_000)
        ahora = 0.0
        bus.solicitar(60_000, ahora)
        ev, _ = bus.observar(60_000, 120_000, "playing", ahora + 0.2)
        self.assertEqual(ev, "candidato")
        ev, _ = bus.observar(10_000, 120_000, "playing", ahora + 0.4)
        self.assertIsNone(ev)
        self.assertIsNone(bus.candidato)
        self.assertEqual(bus._ultima_valida, 10_000)
        self.assertTrue(bus.pendiente)
        ev, _ = bus.observar(60_100, 120_000, "playing", ahora + 0.6)
        self.assertEqual(ev, "candidato")
        ev, val = bus.observar(60_400, 120_000, "playing", ahora + 0.9)
        self.assertEqual(ev, "confirmado")
        self.assertEqual(val, 60_400)

    def test_misma_muestra_repetida_no_confirma(self):
        bus = EstadoBusqueda(confirmada=0)
        ahora = 0.0
        bus.solicitar(60_000, ahora)
        ev, _ = bus.observar(60_000, 120_000, "playing", ahora + 0.2)
        self.assertEqual(ev, "candidato")
        ev, _ = bus.observar(60_000, 120_000, "playing", ahora + 0.4)
        self.assertIsNone(ev)
        self.assertTrue(bus.pendiente)

    def test_pausa_y_negativa_no_alteran(self):
        bus = EstadoBusqueda(confirmada=10_000)
        ahora = 0.0
        bus.solicitar(20_000, ahora)
        ev, _ = bus.observar(20_000, 100_000, "paused", ahora + 0.5)
        self.assertIsNone(ev)
        self.assertEqual(bus.destino, 20_000)
        ev, _ = bus.observar(-1, 100_000, "playing", ahora + 0.6)
        self.assertIsNone(ev)
        self.assertEqual(bus.destino, 20_000)
        self.assertEqual(bus.confirmada, 10_000)

    def test_estado_final_falla_inmediato(self):
        for est in ("ended", "stopped", "error", "nothingspecial"):
            bus = EstadoBusqueda(confirmada=10_000)
            bus.solicitar(20_000, 0.0)
            ev, val = bus.observar(20_000, 100_000, est, 0.5)
            self.assertEqual(ev, "fallo")
            self.assertEqual(bus.confirmada, 20_000)
            self.assertFalse(bus.pendiente)

    def test_destino_cero_y_final_video(self):
        bus = EstadoBusqueda(confirmada=10_000)
        bus.solicitar(0, 0.0)
        ev, _ = bus.observar(0, 120_000, "playing", 0.2)
        self.assertEqual(ev, "candidato")
        ev, val = bus.observar(300, 120_000, "playing", 0.6)
        self.assertEqual(ev, "confirmado")
        # cerca del final sin 250
        bus2 = EstadoBusqueda(confirmada=0)
        bus2.solicitar(119_000, 0.0)
        ev, val = bus2.observar(119_500, 120_000, "playing", 0.5)
        self.assertEqual(ev, "confirmado")

    def test_pulsaciones_acumulan_sin_alterar_confirmada(self):
        bus = EstadoBusqueda(confirmada=10_000)
        bus.solicitar(20_000, 0.0)
        self.assertEqual(bus.confirmada, 10_000)
        bus.solicitar(30_000, 0.1)
        self.assertEqual(bus.destino, 30_000)
        self.assertEqual(bus.confirmada, 10_000)
        self.assertIsNone(bus.candidato)

    def test_generacion_no_revive_y_doble_anuncio(self):
        import reproductor
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = "a"
        panel._url_flujo = ""
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._estado_busqueda = EstadoBusqueda(confirmada=0)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 100_000
        panel._player.get_time.return_value = 60_000
        panel._player.get_state.return_value = mock.Mock(name="playing")
        panel._player.get_state.return_value.name = "playing"
        panel.sld_pos = mock.Mock()
        panel.lbl_tiempo = mock.Mock()
        panel._fijar_tiempo = mock.Mock()
        panel._topologia_actual = lambda: "unica"
        panel._estado_vlc_actual = lambda: "playing"
        bus = panel._estado_busqueda
        bus.solicitar(60_000, time.monotonic())
        gen = bus.generacion
        bus.candidato = 60_000
        panel._player.get_time.return_value = 60_300
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            with mock.patch.object(reproductor.wx.Window, "FindFocus", return_value=None):
                panel._evaluar_busqueda()
                self.assertEqual(anunciar.call_count, 1)
                anunciar.reset_mock()
                panel._evaluar_busqueda()
                anunciar.assert_not_called()
                self.assertGreater(bus.generacion, gen)
                self.assertFalse(bus.pendiente)
        # prueba real del callback tardío vía CallLater
        panel2 = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel2._listo = True
        panel2._video_id = "a"
        panel2._url_flujo = ""
        panel2._tiene_esclavo = False
        panel2._usando_cache_local = False
        panel2._estado_busqueda = EstadoBusqueda(confirmada=0)
        panel2._player = mock.Mock()
        panel2._player.get_length.return_value = 100_000
        panel2._player.get_time.return_value = 10_000
        panel2._player.get_state.return_value = mock.Mock(name="playing")
        panel2._player.get_state.return_value.name = "playing"
        panel2.sld_pos = mock.Mock()
        panel2.lbl_tiempo = mock.Mock()
        panel2._fijar_tiempo = mock.Mock()
        panel2._topologia_actual = lambda: "unica"
        panel2._estado_vlc_actual = lambda: "playing"
        callbacks = []

        def fake_call_later(ms, func):
            callbacks.append(func)
            return mock.Mock()

        app_mock = mock.Mock()
        with mock.patch.object(reproductor.wx, "GetApp", return_value=app_mock), \
                mock.patch.object(reproductor.wx, "CallLater", side_effect=fake_call_later), \
                mock.patch.object(reproductor, "anunciar") as anunciar:
            panel2._marcar_destino(60_000, anunciar_usuario=True)
            self.assertEqual(len(callbacks), 1)
            cb_viejo = callbacks[0]
            gen1 = panel2._estado_busqueda.generacion
            self.assertEqual(panel2._estado_busqueda.destino, 60_000)
            anunciar.reset_mock()
            panel2._marcar_destino(70_000, anunciar_usuario=True)
            self.assertEqual(len(callbacks), 2)
            gen2 = panel2._estado_busqueda.generacion
            self.assertGreater(gen2, gen1)
            self.assertEqual(panel2._estado_busqueda.destino, 70_000)
            anunciar.reset_mock()
            with mock.patch.object(panel2, "_evaluar_busqueda") as evaluar:
                cb_viejo()
                evaluar.assert_not_called()
            anunciar.assert_not_called()
            self.assertEqual(panel2._estado_busqueda.destino, 70_000)
            self.assertEqual(panel2._estado_busqueda.generacion, gen2)
            # confirmar el segundo destino por camino normal
            panel2._estado_busqueda.candidato = 70_000
            panel2._player.get_time.return_value = 70_300
            with mock.patch.object(reproductor.wx.Window, "FindFocus", return_value=None):
                panel2._evaluar_busqueda()
            self.assertEqual(anunciar.call_count, 1)
            self.assertIn("Posición", anunciar.call_args[0][0])
            self.assertFalse(panel2._estado_busqueda.pendiente)
            anunciar.reset_mock()
            with mock.patch.object(reproductor.wx.Window, "FindFocus", return_value=None):
                panel2._evaluar_busqueda()
            anunciar.assert_not_called()
            cb_viejo()
            anunciar.assert_not_called()
            callbacks[1]()
            anunciar.assert_not_called()
            self.assertFalse(panel2._estado_busqueda.pendiente)

    def test_trazas_topologia_sin_url(self):
        from traza_transporte import traza_busqueda_orden, traza_busqueda_desenlace
        linea = traza_busqueda_orden("dividida", "playing", 0, 60000, 0, 100)
        self.assertIn("topologia=dividida", linea)
        self.assertNotIn("http", linea.lower())
        linea2 = traza_busqueda_desenlace("local", "playing", 0, 1000, 0, 10, "confirmado")
        self.assertIn("topologia=local", linea2)
        self.assertNotIn("googlevideo", linea2.lower())


class TestEstadoBusquedaConstantes(unittest.TestCase):

    def test_constantes_puras(self):
        self.assertEqual(TOPE_BUSQUEDA_MS, 8000)
        self.assertEqual(PROGRESO_MINIMO_MS, 250)


class TestBusquedaPermitida(unittest.TestCase):

    def test_vod_remoto_dividido_no_permitida(self):
        from busqueda_video import busqueda_permitida
        self.assertFalse(busqueda_permitida(False, False, True))

    def test_vod_local_dividido_si_permitida(self):
        from busqueda_video import busqueda_permitida
        self.assertTrue(busqueda_permitida(False, True, True))

    def test_vod_remoto_unica_si_permitida(self):
        from busqueda_video import busqueda_permitida
        self.assertTrue(busqueda_permitida(False, False, False))

    def test_vod_local_unica_si_permitida(self):
        from busqueda_video import busqueda_permitida
        self.assertTrue(busqueda_permitida(False, True, False))

    def test_directo_remoto_dividido_si_permitida(self):
        from busqueda_video import busqueda_permitida
        self.assertTrue(busqueda_permitida(True, False, True))

    def test_directo_local_si_permitida(self):
        from busqueda_video import busqueda_permitida
        self.assertTrue(busqueda_permitida(True, True, True))
        self.assertTrue(busqueda_permitida(True, True, False))

    def test_directo_remoto_unica_si_permitida(self):
        from busqueda_video import busqueda_permitida
        self.assertTrue(busqueda_permitida(True, False, False))


class TestEstadoBusquedaDirectoBorde(unittest.TestCase):

    def test_vod_finito_confirma_sin_progreso(self):
        bus = EstadoBusqueda(confirmada=10_000)
        ahora = time.monotonic()
        bus.solicitar(299_000, ahora)
        ev, valor = bus.observar(299_500, 300_000, "playing", ahora + 0.5, es_directo=False)
        self.assertEqual(ev, "confirmado")
        self.assertEqual(valor, 299_500)

    def test_directo_borde_no_confirma_con_una_muestra_inmovil(self):
        bus = EstadoBusqueda(confirmada=10_000)
        ahora = time.monotonic()
        bus.solicitar(845_000, ahora)
        ev, _ = bus.observar(845_000, 845_000, "playing", ahora + 0.5, es_directo=True)
        self.assertEqual(ev, "candidato")
        self.assertEqual(bus.confirmada, 10_000)
        ev2, _ = bus.observar(845_000, 845_000, "playing", ahora + 0.6, es_directo=True)
        self.assertIsNone(ev2)
        self.assertTrue(bus.pendiente)

    def test_directo_borde_confirma_tras_progreso_suficiente(self):
        bus = EstadoBusqueda(confirmada=5_000)
        ahora = time.monotonic()
        bus.solicitar(845_000, ahora)
        ev, _ = bus.observar(845_000, 845_000, "playing", ahora + 0.2, es_directo=True)
        self.assertEqual(ev, "candidato")
        ev, valor = bus.observar(845_300, 845_000, "playing", ahora + 0.7, es_directo=True)
        self.assertEqual(ev, "confirmado")
        self.assertEqual(valor, 845_300)

    def test_directo_borde_vence_sin_progreso(self):
        bus = EstadoBusqueda(confirmada=0)
        ahora = 0.0
        bus.solicitar(845_000, ahora)
        ev, _ = bus.observar(845_000, 845_000, "playing", ahora + 0.3, es_directo=True)
        self.assertEqual(ev, "candidato")
        ev, valor = bus.observar(845_000, 845_000, "playing", ahora + 8.5, es_directo=True)
        self.assertEqual(ev, "vencido")
        self.assertEqual(bus.confirmada, 845_000)


class TestEstadoInicioReproduccion(unittest.TestCase):

    def test_playing_inmovil_no_anuncia(self):
        from busqueda_video import EstadoInicioReproduccion
        est = EstadoInicioReproduccion()
        est.iniciar()
        self.assertFalse(est.observar("playing", 1000))
        self.assertFalse(est.observar("playing", 1000))
        self.assertFalse(est.anunciado)
        self.assertTrue(est.requiere)

    def test_dos_muestras_con_avance_anuncian_una_vez(self):
        from busqueda_video import EstadoInicioReproduccion
        est = EstadoInicioReproduccion()
        est.iniciar()
        self.assertFalse(est.observar("playing", 2000))
        self.assertTrue(est.observar("playing", 2300))
        self.assertTrue(est.anunciado)
        self.assertFalse(est.requiere)
        self.assertFalse(est.observar("playing", 2600))

    def test_no_playing_no_cuenta(self):
        from busqueda_video import EstadoInicioReproduccion
        est = EstadoInicioReproduccion()
        est.iniciar()
        self.assertFalse(est.observar("paused", 1000))
        self.assertFalse(est.observar("buffering", 1000))
        self.assertFalse(est.observar("playing", 1000))
        self.assertFalse(est.observar("playing", 1100))
        self.assertTrue(est.observar("playing", 1300))

    def test_cancelar_no_anuncia(self):
        from busqueda_video import EstadoInicioReproduccion
        est = EstadoInicioReproduccion()
        est.iniciar()
        est.cancelar()
        self.assertFalse(est.observar("playing", 1000))
        self.assertFalse(est.observar("playing", 1300))


if __name__ == "__main__":
    unittest.main()
