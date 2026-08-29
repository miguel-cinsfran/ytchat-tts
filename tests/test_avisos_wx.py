"""Evita que vuelvan avisos de wx por hijos de un ``wx.StaticBox``.

Los doce avisos de ``statusbar.cpp`` salen de ``CreateStatusBar`` dentro de
wx y traen el código ``0x00000000``; no son avisos de esta aplicación.
"""

import queue
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import gui
import reproductor


class _CazadorWx(gui.wx.Log):
    def __init__(self):
        super().__init__()
        self.mensajes = []

    def DoLogRecord(self, level, msg, info):
        self.mensajes.append(msg)


class TestAvisosStaticBox(unittest.TestCase):

    def setUp(self):
        self.app = gui.wx.App(False) if not gui.wx.App.Get() else gui.wx.App.Get()
        self.cazador = _CazadorWx()
        anterior = gui.wx.Log.SetActiveTarget(self.cazador)
        self.addCleanup(gui.wx.Log.SetActiveTarget, anterior)

    def _comprobar_sin_aviso_staticbox(self):
        aviso = "should be created as child"
        self.assertFalse(
            any(aviso in mensaje for mensaje in self.cazador.mensajes),
            f"wx avisó de un hijo incorrecto de StaticBox: {self.cazador.mensajes!r}",
        )

    def test_ventana_principal_no_avisa_por_staticbox(self):
        configuracion = {
            "atajos_raw": {},
            "filtro_activo": "todos",
            "mostrar_botones_reproductor": False,
            "mostrar_metadatos": True,
            "mostrar_total_superchats": True,
            "overlay_activo": False,
            "programados_activo": False,
        }
        stats = SimpleNamespace(leidos=0, superchats=0, descartados=0)
        worker = SimpleNamespace(get_rate=lambda: 0, get_volume=lambda: 100)

        with mock.patch.object(gui.diagnostico, "crear_hilo"):
            frame = gui.YTChatFrame(
                None, configuracion, queue.Queue(), stats, worker, threading.Event())
        self.addCleanup(frame.Destroy)

        self._comprobar_sin_aviso_staticbox()

    def test_aviso_sin_vlc_no_avisa_por_staticbox(self):
        frame = gui.wx.Frame(None)
        self.addCleanup(frame.Destroy)

        with mock.patch.object(reproductor, "vlc_disponible", return_value=False):
            panel = reproductor.ReproductorPanel(frame, {})
        self.addCleanup(panel.Destroy)

        self._comprobar_sin_aviso_staticbox()

    def test_video_es_hijo_del_staticbox_y_tiene_nombre_accesible(self):
        frame = gui.wx.Frame(None)
        self.addCleanup(frame.Destroy)

        with mock.patch.object(reproductor, "disponible", return_value=True):
            panel = reproductor.ReproductorPanel(frame, {})
        self.addCleanup(panel.Destroy)

        self._comprobar_sin_aviso_staticbox()
        self.assertIsInstance(panel._video.GetParent(), gui.wx.StaticBox)
        self.assertEqual(
            panel._video.GetName(), "Vídeo. Doble clic para pantalla completa.")


if __name__ == "__main__":
    unittest.main()
