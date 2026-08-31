"""Comprobación headless con libVLC real para la búsqueda."""

import os
import tempfile
import time
import unittest
import wave
from unittest import mock


def _crear_wav_temporal(duracion_s=5):
    fd, ruta = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    framerate = 44100
    nframes = int(framerate * duracion_s)
    with wave.open(ruta, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(b"\x00\x00" * nframes)
    return ruta


class TestReproductorVLCBusqueda(unittest.TestCase):

    def test_panel_con_vlc_real_cableado_misma_evaluacion(self):
        try:
            import vlc
            import wx
        except Exception as exc:
            self.skipTest(f"vlc/wx no disponible: {exc}")
        ruta = _crear_wav_temporal(6)
        instancia = None
        player = None
        try:
            instancia = vlc.Instance("--quiet", "--aout=dummy", "--vout=dummy")
            self.assertIsNotNone(instancia, "no se pudo crear instancia VLC")
            player = instancia.media_player_new()
            media = instancia.media_new(ruta)
            player.set_media(media)
            player.play()
            inicio = time.monotonic()
            while time.monotonic() - inicio < 5:
                st = player.get_state()
                nombre = getattr(st, "name", str(st)).rsplit(".", 1)[-1].lower()
                if nombre == "playing":
                    break
                time.sleep(0.05)
            else:
                self.fail("VLC no entró en playing con archivo local")
            dur = player.get_length()
            self.assertGreater(dur, 2000, f"duración inesperada {dur}")
            import reproductor
            from busqueda_video import EstadoBusqueda
            panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
            panel._listo = True
            panel._video_id = "test"
            panel._url_flujo = ""
            panel._tiene_esclavo = False
            panel._usando_cache_local = False
            panel._gen = 0
            panel._cargando = False
            panel._config = {}
            panel._vol = 80
            panel._muted = False
            panel._marca_url = None
            panel._marca_reproduccion = None
            panel._marca_extraccion = None
            panel._inst = instancia
            panel._player = player
            panel._estado_busqueda = EstadoBusqueda(confirmada=0)
            panel._transporte_pendiente = False
            panel._intencion_reproducir = True
            panel.sld_pos = mock.Mock()
            panel.sld_pos.GetValue.return_value = 0
            panel.lbl_tiempo = mock.Mock()
            panel.lbl_estado = mock.Mock()
            panel._timer = mock.Mock()
            panel._timer_progreso = mock.Mock()

            def fijar(pos, d, mover_slider, anunciar_t):
                panel._pos_ms = pos
                panel._dur_ms = d

            panel._fijar_tiempo = fijar
            destino = 1000
            with mock.patch.object(reproductor, "anunciar"):
                panel._buscar_rel(destino)
            self.assertEqual(panel._estado_busqueda.destino, destino)
            self.assertEqual(panel._estado_busqueda.confirmada, 0)
            self.assertTrue(panel._estado_busqueda.pendiente)
            with mock.patch.object(reproductor.wx.Window, "FindFocus", return_value=None):
                with mock.patch.object(reproductor, "anunciar") as anunciar:
                    panel._evaluar_busqueda()
                    self.assertTrue(panel._estado_busqueda.pendiente)
                    self.assertEqual(panel._estado_busqueda.confirmada, 0)
                    anunciar.assert_not_called()
                    inicio_espera = time.monotonic()
                    confirmado = False
                    while time.monotonic() - inicio_espera < 3:
                        time.sleep(0.05)
                        panel._evaluar_busqueda()
                        if not panel._estado_busqueda.pendiente:
                            confirmado = True
                            break
                    self.assertTrue(confirmado, "debe confirmar con reloj real")
                    self.assertFalse(panel._estado_busqueda.pendiente)
                    self.assertGreater(panel._estado_busqueda.confirmada, 0)
                    self.assertEqual(anunciar.call_count, 1)
                    self.assertIn("Posición", anunciar.call_args[0][0])
        finally:
            try:
                if player is not None:
                    player.stop()
                    player.release()
            except Exception:
                pass
            try:
                if instancia is not None:
                    instancia.release()
            except Exception:
                pass
            try:
                os.remove(ruta)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
