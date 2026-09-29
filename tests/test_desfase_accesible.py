"""Desfase por detrás del directo en el deslizador y en F2."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import wx

from ytchat.capture import estado_sesion
from ytchat.capture.estado_sesion import SnapshotSesion, formatear_estado
from ytchat.player import reproductor


def _panel_relevo(desfase=0, ventana=(5.0, 720), url_flujo="", en_directo=True):
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._url_flujo = url_flujo
    panel._info = {"is_live": en_directo} if en_directo else {}
    panel._relevo_fuentes = ("video-hls", "audio-hls")
    panel._relevo_desfase = desfase
    panel._relevo_ventana = ventana
    panel._relevo_ffmpeg = mock.Mock()
    panel._dur_ms = 0
    panel._pos_ms = 0
    return panel


class TestFrasePosicionDirecto(unittest.TestCase):

    def test_desfase_cero_dice_en_el_directo(self):
        panel = _panel_relevo(desfase=0)
        self.assertEqual(panel.frase_posicion_directo(), "En el directo")

    def test_seis_segmentos_de_cinco_segundos(self):
        panel = _panel_relevo(desfase=6, ventana=(5.0, 720))
        self.assertEqual(panel.frase_posicion_directo(),
                         "30 segundos por detrás del directo")

    def test_sin_relevo_dice_en_directo(self):
        panel = _panel_relevo()
        panel._relevo_fuentes = None
        panel._relevo_ffmpeg = None
        self.assertEqual(panel.frase_posicion_directo(), "En directo")

    def test_con_url_flujo_dice_en_directo(self):
        panel = _panel_relevo(url_flujo="https://tiktok/flv")
        panel._relevo_fuentes = None
        panel._relevo_ffmpeg = None
        self.assertEqual(panel.frase_posicion_directo(), "En directo")


class TestPosAccesibleDesfase(unittest.TestCase):

    def test_directo_por_relevo_anuncia_desfase(self):
        panel = _panel_relevo(desfase=6, ventana=(5.0, 720))
        acc = reproductor._PosAccesible.__new__(reproductor._PosAccesible)
        acc._panel = panel
        self.assertEqual(acc.GetValue(0),
                         (wx.ACC_OK, "30 segundos por detrás del directo"))

    def test_grabado_sigue_diciendo_n_de_m(self):
        panel = _panel_relevo()
        panel._dur_ms = 60000
        panel._pos_ms = 10000
        acc = reproductor._PosAccesible.__new__(reproductor._PosAccesible)
        acc._panel = panel
        codigo, texto = acc.GetValue(0)
        self.assertEqual(codigo, wx.ACC_OK)
        self.assertIn(" de ", texto)

    def test_si_la_frase_falla_dice_en_directo(self):
        panel = _panel_relevo()
        panel.frase_posicion_directo = mock.Mock(side_effect=RuntimeError("x"))
        acc = reproductor._PosAccesible.__new__(reproductor._PosAccesible)
        acc._panel = panel
        self.assertEqual(acc.GetValue(0), (wx.ACC_OK, "En directo"))


class TestDesfaseEnF2(unittest.TestCase):

    def test_corto_y_largo_incluyen_el_desfase(self):
        s = SnapshotSesion(desfase_directo="30 segundos por detrás del directo")
        self.assertEqual(formatear_estado(s, {"desfase_directo"}),
                         "30 segundos por detrás del directo.")
        self.assertEqual(formatear_estado(s, {"desfase_directo"}, "largo"),
                         "Reproductor: 30 segundos por detrás del directo")

    def test_vacio_se_omite(self):
        self.assertEqual(formatear_estado(SnapshotSesion(), {"desfase_directo"}), "")
        self.assertEqual(
            formatear_estado(SnapshotSesion(desfase_directo=""), {"desfase_directo"}), "")

    def test_orden_tras_tiempo_directo(self):
        comps = list(estado_sesion.COMPONENTES)
        self.assertLess(comps.index("tiempo_directo"), comps.index("desfase_directo"))
        self.assertLess(comps.index("desfase_directo"), comps.index("mensajes_leidos"))

    def test_etiqueta(self):
        self.assertEqual(
            estado_sesion.ETIQUETAS["desfase_directo"],
            "Cuánto por detrás del directo va el reproductor")


class TestDesfasePorDefecto(unittest.TestCase):

    def test_activo_por_defecto(self):
        self.assertIn("desfase_directo", estado_sesion.ACTIVOS_DEFECTO)

    def test_config_sin_clave_la_deja_activa(self):
        from tests.rutas_temporales import redirigir_rutas
        from ytchat.core import config
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "config.ini").write_text("[voz]\nvoz = 0\n", encoding="utf-8")
            with redirigir_rutas(tmp):
                cfg = config.cargar_configuracion()
        self.assertIn("desfase_directo", cfg["estado_toggles"])


def _frame_con_panel(frase, desfase_seg):
    from ytchat.ui import gui
    frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
    frame._conectado = True
    frame._es_tiktok = False
    frame._tipo_video = "live"
    frame._titulo_stream = "T"
    frame._metadatos = {}
    frame._sc_totales = {}
    frame._mensajes_programados = []
    frame._config = {"silenciar_lectura": False, "programados_activo": False}
    frame._stats = mock.Mock(leidos=0, superchats=0, descartados=0)
    frame._cola = mock.Mock(qsize=mock.Mock(return_value=0))
    frame._worker = mock.Mock(get_rate=mock.Mock(return_value=0),
                              get_volume=mock.Mock(return_value=0))
    frame._obs_vigilante = None
    panel = mock.Mock()
    panel.frase_posicion_directo = mock.Mock(return_value=frase)
    panel._desfase_relevo_segundos = mock.Mock(return_value=desfase_seg)
    frame._rep_panel = panel
    return frame


class TestSnapshotDesfase(unittest.TestCase):

    def test_panel_por_detras_lleva_la_frase(self):
        from ytchat.ui import gui
        frame = _frame_con_panel("30 segundos por detrás del directo", 30)
        snap = gui.YTChatFrame._snapshot_sesion(frame)
        self.assertEqual(snap.desfase_directo, "30 segundos por detrás del directo")

    def test_desfase_cero_da_cadena_vacia(self):
        from ytchat.ui import gui
        frame = _frame_con_panel("En el directo", 0)
        snap = gui.YTChatFrame._snapshot_sesion(frame)
        self.assertEqual(snap.desfase_directo, "")


if __name__ == "__main__":
    unittest.main()
