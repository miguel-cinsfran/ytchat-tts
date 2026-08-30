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
        panel._destino_pendiente = None
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
        panel._destino_pendiente = 4000
        panel._player.get_length.return_value = 10000
        panel._player.get_time.return_value = 0
        panel._player.get_time.return_value = 5000

        with self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            panel._buscar_rel(-1000)

        self.assertIn(
            "SALTO origen=relativo pendiente=4000 pos=5000 delta=-1000 "
            "destino=3000 dur=10000", capturas.output[0])

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
        panel.sld_pos = mock.Mock()
        panel.sld_pos.GetValue.return_value = 500

        with self.assertLogs("ytchat.reproductor", "DEBUG") as capturas:
            panel._buscar_porcentaje(20)
            panel._on_sld_pos(None)

        self.assertIn("SALTO origen=porcentaje", capturas.output[0])
        self.assertIn("SALTO origen=deslizador", capturas.output[1])

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


if __name__ == "__main__":
    unittest.main()
