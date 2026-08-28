"""Pruebas de los avisos de carga del reproductor."""

import unittest
from unittest import mock

import reproductor


class TestCargaReproductor(unittest.TestCase):

    def _panel(self, video_id, cargando):
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._listo = True
        panel._video_id = video_id
        panel._cargando = cargando
        panel._asegurar_player = mock.Mock(return_value=True)
        panel._timer_progreso = mock.Mock()
        panel.lbl_estado = mock.Mock()
        panel._gen = 0
        panel._calidad_sel = None
        return panel

    @mock.patch.object(reproductor, "anunciar")
    def test_segunda_pulsacion_anuncia_que_sigue_cargando(self, anunciar):
        panel = self._panel("A" * 11, True)

        panel.cargar()

        anunciar.assert_called_once_with("Cargando vídeo")

    @mock.patch.object(reproductor, "anunciar")
    def test_sin_video_sigue_sin_anunciar(self, anunciar):
        panel = self._panel("", False)

        panel.cargar()

        anunciar.assert_not_called()

    @mock.patch.object(reproductor.diagnostico, "crear_hilo")
    @mock.patch.object(reproductor, "anunciar")
    def test_empezar_carga_arranca_el_temporizador(self, _anunciar, crear_hilo):
        panel = self._panel("A" * 11, False)
        crear_hilo.return_value.start = mock.Mock()

        panel.cargar()

        panel._timer_progreso.Start.assert_called_once_with(250)

    def test_carga_lista_detiene_el_temporizador(self):
        panel = self._panel("A" * 11, True)
        panel._reproducir_calidad = mock.Mock()

        panel._info_listo({}, True, "A" * 11, 0)

        panel._timer_progreso.Stop.assert_called_once_with()

    def test_carga_descartada_detiene_el_temporizador(self):
        panel = self._panel("A" * 11, True)

        panel._info_listo({}, True, "A" * 11, 1)

        panel._timer_progreso.Stop.assert_called_once_with()

    @mock.patch.object(reproductor, "anunciar")
    def test_error_de_carga_detiene_el_temporizador(self, _anunciar):
        panel = self._panel("A" * 11, True)
        with mock.patch.dict("sys.modules", {"sound_player": mock.Mock()}):
            panel._error_carga()

        panel._timer_progreso.Stop.assert_called_once_with()

    def test_detener_cancela_el_temporizador_de_progreso(self):
        panel = self._panel("A" * 11, True)
        panel._player = None

        panel._detener(silencioso=True)

        panel._timer_progreso.Stop.assert_called_once_with()

    @mock.patch.object(reproductor.time, "monotonic", return_value=5)
    @mock.patch.object(reproductor, "anunciar")
    def test_golpe_del_temporizador_anuncia_progreso(self, anunciar, _monotonic):
        panel = self._panel("A" * 11, True)
        panel._inicio_progreso = 0
        panel._ultimo_aviso_progreso = None

        panel._on_timer_progreso(None)

        anunciar.assert_called_once_with("Buscando el vídeo, 5 segundos", "progreso")


if __name__ == "__main__":
    unittest.main()
