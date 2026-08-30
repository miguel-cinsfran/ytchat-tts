"""Pruebas de las decisiones puras del reproductor."""

import unittest
import time
from unittest import mock
from types import SimpleNamespace

from busqueda_video import (
    CADUCIDAD_DESTINO_MS, TOLERANCIA_ATRAS_MS, TOLERANCIA_DESTINO_MS,
    accion_play_pausa, destino_acumulado, destino_alcanzado, destino_vigente,
    posicion_a_mostrar, posicion_confiable,
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

    def test_orden_reciente_contraria_en_reproduccion(self):
        self.assertEqual(accion_play_pausa("playing", True, False, True), "en_curso")

    def test_orden_reciente_contraria_en_pausa(self):
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
        panel._destino_pendiente = None
        panel._ultima_posicion_confiable = 10_000
        panel._marca_destino_pendiente = None
        panel._fijar_tiempo = mock.Mock()

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
        panel._destino_pendiente = None
        panel._marca_destino_pendiente = None
        panel._ultima_posicion_confiable = 31_038
        panel._fijar_tiempo = mock.Mock()

        panel._buscar_rel(-10_000)

        panel._player.set_time.assert_called_once_with(21_038)

    def test_salto_siguiente_conserva_como_referencia_el_destino_anterior(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 60_000
        panel._player.get_time.side_effect = [5_000, 8_000]
        panel._destino_pendiente = None
        panel._ultima_posicion_confiable = 5_000
        panel._marca_destino_pendiente = None
        panel._fijar_tiempo = mock.Mock()

        panel._buscar_rel(20_000)
        panel._marca_destino_pendiente = time.monotonic() - (
            CADUCIDAD_DESTINO_MS + 1) / 1000

        panel._buscar_rel(10_000)

        self.assertEqual(panel._player.set_time.call_args_list,
                         [mock.call(25_000), mock.call(35_000)])

    def test_on_timer_con_salto_en_vuelo_conserva_el_destino_pendiente(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 60_000
        panel._player.get_time.return_value = 10_000
        panel._destino_pendiente = 30_000
        panel._muted = False
        panel._marca_url = None
        panel._fijar_tiempo = mock.Mock()
        panel.sld_pos = mock.Mock()

        estado_vlc = SimpleNamespace(State=SimpleNamespace(
            Playing="playing", Ended="ended"))
        with mock.patch.object(reproductor, "_vlc", estado_vlc):
            with mock.patch.object(reproductor.wx.Window, "FindFocus",
                                   return_value=None):
                panel._on_timer(None)

        self.assertEqual(panel._destino_pendiente, 30_000)
        panel._fijar_tiempo.assert_called_once_with(
            30_000, 60_000, mover_slider=True, anunciar_t=False)

    def test_on_timer_al_alcanzar_el_salto_limpia_el_destino_pendiente(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 60_000
        panel._player.get_time.return_value = 29_000
        panel._player.get_state.return_value = "paused"
        panel._destino_pendiente = 30_000
        panel._muted = False
        panel._marca_url = None
        panel._fijar_tiempo = mock.Mock()
        panel.sld_pos = mock.Mock()

        estado_vlc = SimpleNamespace(State=SimpleNamespace(
            Playing="playing", Ended="ended"))
        with mock.patch.object(reproductor, "_vlc", estado_vlc):
            with mock.patch.object(reproductor.wx.Window, "FindFocus",
                                   return_value=None):
                with mock.patch.object(
                        reproductor, "destino_alcanzado",
                        wraps=destino_alcanzado) as destino_consultado:
                    panel._on_timer(None)

        self.assertIsNone(panel._destino_pendiente)
        destino_consultado.assert_called_once_with(
            30_000, 29_000, TOLERANCIA_DESTINO_MS)

    def test_buscar_rel_caso_real_con_duracion_atrasada_no_retrocede(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 3_600_000
        panel._player.get_time.return_value = 3_615_868
        panel._destino_pendiente = None
        panel._marca_destino_pendiente = None
        panel._ultima_posicion_confiable = 3_615_868
        panel._marcar_destino = mock.Mock()
        panel._fijar_tiempo = mock.Mock()

        panel._buscar_rel(60_000)

        panel._player.set_time.assert_called_once_with(3_615_868)
        panel._marcar_destino.assert_called_once_with(3_615_868)
        panel._fijar_tiempo.assert_called_once_with(
            3_615_868, 3_600_000, mover_slider=True, anunciar_t=True)
        for nombre, llamada in [
            ("set_time", panel._player.set_time),
            ("_marcar_destino", panel._marcar_destino),
            ("_fijar_tiempo", panel._fijar_tiempo),
        ]:
            with self.subTest(receptor=nombre):
                args = llamada.call_args[0] if llamada.call_args else ()
                kwargs = llamada.call_args[1] if llamada.call_args else {}
                valores = list(args) + list(kwargs.values())
                self.assertNotIn(3_600_000, valores[0:1] if nombre != "_fijar_tiempo" else valores[0:1],
                                 f"{nombre} recibió 3.600.000 en lugar de 3.615.868")
                self.assertIn(3_615_868, valores)


class TestCableadoPlayPausa(unittest.TestCase):

    def test_orden_en_curso_no_invierte_ni_anuncia(self):
        import reproductor

        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._player = mock.Mock()
        panel._player.get_state.return_value = SimpleNamespace(name="playing")
        panel._video_id = "video-cargado"
        panel._url_flujo = ""
        panel._intencion_reproducir = False
        panel._ultima_orden_transporte = __import__("time").monotonic()
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
        panel._asegurar_player = mock.Mock(return_value=True)
        panel._mostrar_pausa = mock.Mock()
        panel._timer = mock.Mock()
        panel.cargar = mock.Mock()

        with mock.patch.object(reproductor, "anunciar"):
            panel._toggle_play()

        panel._player.set_pause.assert_called_once_with(1)
        panel.cargar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
