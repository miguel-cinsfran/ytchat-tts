"""Pruebas del cableado de las trazas del reproductor."""

import unittest
from unittest import mock

import reproductor


class TestTrazaReproductor(unittest.TestCase):

    def _panel(self):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = "A" * 11
        panel._url_flujo = None
        panel._intencion_reproducir = True
        panel._player = mock.Mock()
        panel._asegurar_player = mock.Mock(return_value=True)
        panel._mostrar_pausa = mock.Mock()
        panel._timer = mock.Mock()
        panel._fijar_tiempo = mock.Mock()
        panel._aviso_sin_barra = mock.Mock()
        return panel

    def test_toggle_registra_antes_de_pausar(self):
        panel = self._panel()
        panel._player.get_state.return_value.name = "playing"
        panel._player.can_pause.return_value = 1
        panel._player.is_seekable.return_value = 1
        orden = []

        def pausar(_valor):
            self.assertTrue(any(
                "TRANSPORTE estado=playing accion=pausar" in registro.getMessage()
                for registro in capturas.records))
            orden.append("pausar")

        panel._player.set_pause.side_effect = pausar
        with mock.patch.object(reproductor, "anunciar"), \
                self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            panel._toggle_play()

        self.assertEqual(orden, ["pausar"])

    def test_toggle_sigue_pausando_si_falla_can_pause(self):
        panel = self._panel()
        panel._player.get_state.return_value.name = "playing"
        panel._player.can_pause.side_effect = RuntimeError("fallo")
        panel._player.is_seekable.return_value = 1

        with mock.patch.object(reproductor, "anunciar"), \
                self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            panel._toggle_play()

        self.assertIn("puede_pausar=desconocido", capturas.output[0])
        panel._player.set_pause.assert_called_once_with(1)

    def test_buscar_rel_registra_el_pendiente_anterior(self):
        panel = self._panel()
        from busqueda_video import EstadoBusqueda
        panel._estado_busqueda = EstadoBusqueda(confirmada=0)
        panel._estado_busqueda.destino = 4000
        panel._estado_busqueda.marca_destino = __import__("time").monotonic()
        panel._player.get_length.return_value = 10000
        panel._player.get_time.return_value = 5000

        with self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            panel._buscar_rel(-1000)

        # ahora pos es la confirmada (0), no la lectura cruda
        self.assertTrue(any(
            "SALTO origen=relativo pendiente=4000 pos=0 delta=-1000 destino=3000 dur=10000" in out
            for out in capturas.output))

    def test_buscar_rel_sin_barra_no_registra_salto(self):
        panel = self._panel()
        panel._player.get_length.return_value = 0

        with self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            panel._buscar_rel(1000)

        self.assertIn("SALTO_SIN_BARRA origen=relativo dur=0", capturas.output[0])
        self.assertNotIn("SALTO origen=", capturas.output[0])

    def test_porcentaje_y_deslizador_registran_su_origen(self):
        panel = self._panel()
        panel._player.get_length.return_value = 10000
        panel._player.get_time.return_value = 0
        from busqueda_video import EstadoBusqueda
        panel._estado_busqueda = EstadoBusqueda(confirmada=0)
        panel.sld_pos = mock.Mock()
        panel.sld_pos.GetValue.return_value = 500

        with self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            panel._buscar_porcentaje(20)
            panel._on_sld_pos(None)

        self.assertTrue(any("SALTO origen=porcentaje" in out for out in capturas.output))
        self.assertTrue(any("SALTO origen=deslizador" in out for out in capturas.output))
        self.assertTrue(any("BUSQUEDA_ORDEN" in out for out in capturas.output))

    def test_asegurar_player_existente_no_registra_player_nuevo(self):
        panel = self._panel()
        del panel._asegurar_player

        with self.assertNoLogs("ytchat.reproductor", "DEBUG"):
            self.assertTrue(panel._asegurar_player())

    def test_asegurar_player_nuevo_registra_la_creacion(self):
        panel = self._panel()
        del panel._asegurar_player
        panel._player = None
        panel._asegurar_instancia = mock.Mock(return_value=True)
        panel._inst = mock.Mock()
        panel._video = mock.Mock()
        panel._fijar_salida = mock.Mock()

        with mock.patch.object(reproductor, "_registro_detallado_activo", return_value=False), \
                self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            self.assertTrue(panel._asegurar_player())

        self.assertIn("PLAYER_NUEVO", capturas.output[0])

    def test_cargar_en_curso_no_registra_carga(self):
        panel = self._panel()
        panel._cargando = True

        with mock.patch.object(reproductor, "anunciar"), \
                self.assertNoLogs("ytchat.reproductor", "DEBUG"):
            panel.cargar()

    @mock.patch.object(reproductor.diagnostico, "crear_hilo")
    def test_cargar_registra_carga_real(self, crear_hilo):
        panel = self._panel()
        panel._cargando = False
        panel._gen = 0
        panel._calidad_sel = None
        panel.lbl_estado = mock.Mock()
        panel._timer_progreso = mock.Mock()
        crear_hilo.return_value.start = mock.Mock()

        with mock.patch.object(reproductor, "anunciar"), \
                self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            panel.cargar(reproducir=False)

        self.assertIn("CARGA video=AAAAAAAAAAA reproducir=no", capturas.output[0])


class TestBusquedaCableado(unittest.TestCase):

    def _panel_busqueda(self, confirmada=0):
        import reproductor
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = "A" * 11
        panel._url_flujo = ""
        panel._tiene_esclavo = False
        panel._usando_cache_local = False
        panel._gen = 0
        panel._cargando = False
        panel._config = {"cache_video_mb": 1024}
        panel._marca_url = None
        panel._marca_reproduccion = None
        panel._marca_extraccion = None
        panel._muted = False
        panel._vol = 80
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 100000
        panel._player.get_time.return_value = confirmada
        panel._player.get_state.return_value = mock.Mock(name="playing")
        try:
            panel._player.get_state.return_value.name = "playing"
        except Exception:
            pass
        panel._player.audio_get_volume.return_value = 80
        panel._player.can_pause.return_value = 1
        panel._player.is_seekable.return_value = 1
        panel._inst = mock.Mock()
        panel._gestor_eventos_vlc = None
        panel._tarea_cache_video = None
        panel._fijar_tiempo = mock.Mock()
        panel._fijar_salida = mock.Mock()
        panel._mostrar_pausa = mock.Mock()
        panel.sld_pos = mock.Mock()
        panel.sld_pos.GetValue.return_value = 500
        panel.sld_vol = mock.Mock()
        panel.lbl_tiempo = mock.Mock()
        panel.lbl_estado = mock.Mock()
        panel._timer = mock.Mock()
        panel._timer_progreso = mock.Mock()
        from busqueda_video import EstadoBusqueda
        panel._estado_busqueda = EstadoBusqueda(confirmada=confirmada)
        panel._transporte_pendiente = False
        panel._intencion_reproducir = True
        return panel

    def test_pulsaciones_rapidas_acumulan_sin_cambiar_confirmada(self):
        import reproductor
        panel = self._panel_busqueda(confirmada=10_000)
        panel._player.get_length.return_value = 100_000
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._buscar_rel(10_000)
            self.assertEqual(panel._estado_busqueda.destino, 20_000)
            self.assertEqual(panel._estado_busqueda.confirmada, 10_000)
            self.assertEqual(anunciar.call_args[0][0], "Moviendo a 20 segundos")
            anunciar.reset_mock()
            panel._buscar_rel(10_000)
            self.assertEqual(panel._estado_busqueda.destino, 30_000)
            self.assertEqual(panel._estado_busqueda.confirmada, 10_000)
            self.assertEqual(anunciar.call_args[0][0], "Moviendo a 30 segundos")

    def test_exito_anuncia_posicion_una_vez(self):
        import reproductor
        panel = self._panel_busqueda(confirmada=0)
        panel._player.get_length.return_value = 100_000
        panel._player.get_state.return_value.name = "playing"
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            panel._buscar_rel(60_000)
            anunciar.assert_called_once()
            anunciar.reset_mock()
            bus = panel._estado_busqueda
            bus.candidato = 60_000
            panel._player.get_time.return_value = 60_300
            panel._player.get_state.return_value.name = "playing"
            with mock.patch.object(reproductor.wx.Window, "FindFocus", return_value=None):
                panel._on_timer(None)
            anunciar.assert_called_once()
            self.assertIn("Posición", anunciar.call_args[0][0])

    def test_fallo_anuncia_no_se_pudo_mover(self):
        import reproductor
        panel = self._panel_busqueda(confirmada=10_000)
        panel._player.get_length.return_value = 100_000
        panel._player.get_time.return_value = 10_000
        panel._player.get_state.return_value.name = "playing"
        with mock.patch.object(reproductor, "anunciar"):
            panel._buscar_rel(50_000)
        panel._estado_busqueda.marca_destino = __import__("time").monotonic() - 9
        panel._player.get_time.return_value = 0
        panel._player.get_state.return_value.name = "playing"
        with mock.patch.object(reproductor, "anunciar") as anunciar:
            with mock.patch.object(reproductor.wx.Window, "FindFocus", return_value=None):
                panel._on_timer(None)
            anunciar.assert_called_once_with("No se pudo mover el vídeo")
            self.assertEqual(panel._estado_busqueda.confirmada, 0)

    def test_restauracion_cache_no_anuncia(self):
        import reproductor
        panel = self._panel_busqueda(confirmada=15_000)
        panel._inst = mock.Mock()
        panel._player = mock.Mock()
        panel._player.get_length.return_value = 100_000
        panel._player.get_time.return_value = 15_000
        from pathlib import Path
        import tempfile, os
        destino = Path(tempfile.gettempdir()) / "ytchat_test_cache.mp4"
        try:
            destino.write_bytes(b"0")
            from tarea_cache_video import TareaCacheVideo
            tarea = TareaCacheVideo("vid", 0, destino)
            panel._tarea_cache_video = tarea
            panel._gen = 0
            panel._video_id = "vid"
            panel._inst.media_new.return_value = mock.Mock()
            panel._player.set_media = mock.Mock()
            panel._player.audio_set_volume = mock.Mock()
            panel._player.audio_set_mute = mock.Mock()
            panel._player.play = mock.Mock()
            panel._player.set_time = mock.Mock()
            with mock.patch.object(reproductor, "anunciar") as anunciar, \
                    self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
                panel._cache_video_lista(tarea, True)
                anunciar.assert_not_called()
            orden = [l for l in capturas.output if "BUSQUEDA_ORDEN" in l]
            self.assertEqual(len(orden), 1, capturas.output)
            self.assertIn("topologia=local", orden[0].lower())
        finally:
            try:
                os.remove(destino)
            except Exception:
                pass

    def test_todos_los_origenes_usam_misma_busqueda(self):
        import reproductor
        for origen in ("relativo", "porcentaje", "deslizador"):
            panel = self._panel_busqueda(confirmada=20_000)
            panel._player.get_length.return_value = 100_000
            panel._player.get_state.return_value.name = "playing"
            with mock.patch.object(reproductor, "anunciar"):
                if origen == "relativo":
                    panel._buscar_rel(10_000)
                elif origen == "porcentaje":
                    panel._buscar_porcentaje(30)
                else:
                    panel.sld_pos.GetValue.return_value = 300
                    panel._on_sld_pos(None)
            self.assertIsNotNone(panel._estado_busqueda.destino)
            self.assertEqual(panel._estado_busqueda.confirmada, 20_000)

    def test_detener_cargar_cambiar_flujo_cancelan(self):
        import reproductor
        for accion in ("detener", "cargar", "flujo"):
            panel = self._panel_busqueda(confirmada=10_000)
            panel._player.get_length.return_value = 100_000
            with mock.patch.object(reproductor, "anunciar"):
                panel._buscar_rel(20_000)
            self.assertIsNotNone(panel._estado_busqueda.destino)
            if accion == "detener":
                panel._timer = mock.Mock()
                panel._timer_progreso = mock.Mock()
                panel.btn_play = mock.Mock()
                panel._mostrar_pausa = mock.Mock()
                panel._fijar_tiempo = mock.Mock()
                panel._detener(silencioso=True)
            elif accion == "cargar":
                panel._cargando = False
                panel._gen = 0
                panel._calidad_sel = None
                panel.lbl_estado = mock.Mock()
                panel._timer_progreso = mock.Mock()
                panel._asegurar_player = mock.Mock(return_value=True)
                with mock.patch.object(reproductor, "anunciar"), mock.patch.object(reproductor.diagnostico, "crear_hilo") as crear:
                    crear.return_value.start = mock.Mock()
                    panel.cargar(reproducir=False)
            else:
                panel._url_flujo = "http://example.com/stream.m3u8"
                panel._asegurar_player = mock.Mock(return_value=True)
                panel._inst = mock.Mock()
                panel._inst.media_new.return_value = mock.Mock()
                panel._player.set_media = mock.Mock()
                panel._player.audio_set_volume = mock.Mock()
                panel._player.audio_set_mute = mock.Mock()
                panel._player.play = mock.Mock()
                panel._mostrar_pausa = mock.Mock()
                panel._timer = mock.Mock()
                with mock.patch.object(reproductor, "anunciar"):
                    panel._reproducir_flujo()
            self.assertIsNone(panel._estado_busqueda.destino)
            self.assertIsNone(panel._estado_busqueda.candidato)

    def test_cancelacion_cableada_traza_unica(self):
        import reproductor
        panel = self._panel_busqueda(confirmada=10_000)
        panel._player.get_length.return_value = 100_000
        with mock.patch.object(reproductor, "anunciar"):
            panel._buscar_rel(20_000)
        self.assertIsNotNone(panel._estado_busqueda.destino)
        panel._timer = mock.Mock()
        panel._timer_progreso = mock.Mock()
        panel.btn_play = mock.Mock()
        panel._mostrar_pausa = mock.Mock()
        panel._fijar_tiempo = mock.Mock()
        with self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            with mock.patch.object(reproductor, "anunciar"):
                panel._detener(silencioso=True)
        lineas = [l for l in capturas.output if "BUSQUEDA_CANCELADO" in l]
        self.assertEqual(len(lineas), 1, capturas.output)
        salida = lineas[0].lower()
        self.assertIn("topologia=", salida)
        self.assertIn("estado=", salida)
        self.assertIn("confirmada=", salida)
        self.assertIn("destino=", salida)
        self.assertIn("muestra=", salida)
        self.assertIn("edad=", salida)
        self.assertIsNone(panel._estado_busqueda.destino)
        self.assertIsNone(panel._estado_busqueda.candidato)
        # sin pendiente no registra nada
        with self.assertNoLogs("ytchat.reproductor", "DEBUG"):
            panel._detener(silencioso=True)

    def test_trazas_contienen_topologia_sin_url(self):
        import reproductor
        panel = self._panel_busqueda(confirmada=0)
        panel._player.get_length.return_value = 100_000
        panel._tiene_esclavo = True
        with self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            with mock.patch.object(reproductor, "anunciar"):
                panel._buscar_rel(10_000)
        salida = "\n".join(capturas.output)
        self.assertIn("topologia=dividida", salida.lower())
        self.assertNotIn("http", salida.lower())
        self.assertNotIn("googlevideo", salida.lower())


if __name__ == "__main__":
    unittest.main()
