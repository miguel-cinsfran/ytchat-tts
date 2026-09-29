"""Pruebas de «Ir al directo» (Ctrl+Fin, acción rep_directo)."""

import inspect
import unittest
from unittest import mock

from ytchat.core import config as cfg

try:
    import wx  # noqa: F401
    _HAY_WX = True
except Exception:
    _HAY_WX = False


def _panel(desfase=0, ventana=(5.0, 720), url_flujo="", en_directo=True):
    from ytchat.player import reproductor
    panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
    panel._url_flujo = url_flujo
    panel._info = {"is_live": en_directo} if en_directo else {}
    panel._relevo_fuentes = ("video-hls", "audio-hls")
    panel._relevo_desfase = desfase
    panel._relevo_ventana = ventana
    return panel


class TestRepDirectoConfig(unittest.TestCase):

    def test_normaliza_ctrl_end_y_vale_para_el_grupo_ctrl(self):
        self.assertEqual(cfg._normalizar_atajo("ctrl+end"), "ctrl+end")
        self.assertEqual(cfg._normalizar_atajo(" CTRL + END "), "ctrl+end")
        self.assertTrue(cfg.atajo_valido_para_area("rep_directo", "ctrl+end"))

    def test_default_fabrica_y_sin_conflictos(self):
        self.assertEqual(cfg.ATAJOS_DEFAULTS.get("rep_directo"), "ctrl+end")
        grupos = dict(cfg.ATAJOS_GRUPOS)
        self.assertIn("rep_directo", grupos["Reproductor (Ctrl)"])
        self.assertEqual(
            grupos["Reproductor (Ctrl)"].index("rep_directo"),
            grupos["Reproductor (Ctrl)"].index("rep_avanz") + 1)
        self.assertEqual(cfg.detectar_conflictos_atajos(None), [])
        self.assertEqual(
            cfg.detectar_conflictos_atajos(dict(cfg.todos_los_atajos_default())), [])

    def test_textos_y_acelerador_muestran_end(self):
        from ytchat.ui import atajos_captura
        from ytchat.ui.gui import _fmt_accel
        self.assertEqual(atajos_captura.mostrar_atajo("ctrl+end"), "Ctrl+End")
        self.assertEqual(_fmt_accel("ctrl+end"), "Ctrl+End")
        self.assertEqual(
            atajos_captura.etiqueta_boton("Ir al directo", "ctrl+end"),
            "Ir al directo: Ctrl+End")


class TestIrAlDirecto(unittest.TestCase):

    def test_relevo_a_seis_segmentos_llama_con_treinta_mil(self):
        from ytchat.player import reproductor
        panel = _panel(desfase=6, ventana=(5.0, 720))
        with mock.patch.object(panel, "_saltar_en_relevo") as saltar, \
                mock.patch.object(reproductor, "anunciar") as anunciar:
            panel.ir_al_directo()
        saltar.assert_called_once_with(30000)
        anunciar.assert_not_called()

    def test_relevo_en_desfase_cero_anuncia_sin_saltar(self):
        from ytchat.player import reproductor
        panel = _panel(desfase=0)
        with mock.patch.object(panel, "_saltar_en_relevo") as saltar, \
                mock.patch.object(reproductor, "anunciar") as anunciar:
            panel.ir_al_directo()
        saltar.assert_not_called()
        anunciar.assert_called_once_with("Ya estás en el directo")

    def test_tiktok_anuncia_en_el_borde(self):
        from ytchat.player import reproductor
        panel = _panel(url_flujo="https://tiktok/flv")
        panel._relevo_fuentes = None
        panel._relevo_ffmpeg = None
        with mock.patch.object(panel, "_saltar_en_relevo") as saltar, \
                mock.patch.object(reproductor, "anunciar") as anunciar:
            panel.ir_al_directo()
        saltar.assert_not_called()
        anunciar.assert_called_once_with("Ya estás en el directo")

    def test_directo_sin_relevo_anuncia_en_el_borde(self):
        from ytchat.player import reproductor
        panel = _panel()
        panel._relevo_fuentes = None
        with mock.patch.object(panel, "_saltar_en_relevo") as saltar, \
                mock.patch.object(reproductor, "anunciar") as anunciar:
            panel.ir_al_directo()
        saltar.assert_not_called()
        anunciar.assert_called_once_with("Ya estás en el directo")

    def test_grabado_y_sin_medio_avisan_que_no_es_directo(self):
        from ytchat.player import reproductor
        for panel in (_panel(en_directo=False),
                      _panel(url_flujo="", en_directo=False)):
            panel._relevo_fuentes = None
            with mock.patch.object(panel, "_saltar_en_relevo") as saltar, \
                    mock.patch.object(reproductor, "anunciar") as anunciar:
                panel.ir_al_directo()
            saltar.assert_not_called()
            anunciar.assert_called_once_with("Este vídeo no es un directo")
        panel = _panel()
        panel._url_flujo = ""
        panel._info = None
        panel._relevo_fuentes = None
        with mock.patch.object(panel, "_saltar_en_relevo") as saltar, \
                mock.patch.object(reproductor, "anunciar") as anunciar:
            panel.ir_al_directo()
        saltar.assert_not_called()
        anunciar.assert_called_once_with("Este vídeo no es un directo")


@unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
class TestRepDirectoWx(unittest.TestCase):

    def test_mapa_de_pantalla_completa_apunta_a_ir_al_directo(self):
        import wx
        from ytchat.player import reproductor
        panel = reproductor.ReproductorPanel.__new__(reproductor.ReproductorPanel)
        panel._config = {"atajos_raw": {}}
        mapa = panel._mapa_atajos_fs()
        self.assertIs(
            mapa.get((wx.MOD_CONTROL, wx.WXK_END)).__self__, panel)
        self.assertEqual(
            mapa[(wx.MOD_CONTROL, wx.WXK_END)].__func__,
            reproductor.ReproductorPanel.ir_al_directo)

    def test_combo_wx_traduce_ctrl_end(self):
        import wx
        from ytchat.player import reproductor
        self.assertEqual(reproductor._combo_wx("ctrl+end"),
                         (wx.MOD_CONTROL, wx.WXK_END))

    def test_captura_convierte_fin_con_ctrl_en_ctrl_end(self):
        import wx
        from ytchat.ui import gui_preferencias as gp
        self.assertEqual(
            gp._combo_a_texto(wx.MOD_CONTROL, wx.WXK_END), "ctrl+end")
        self.assertEqual(gp._tecla_texto(wx.WXK_END), "end")

    def test_menu_usa_acelerador_y_enlace(self):
        from ytchat.ui import gui
        fuente = inspect.getsource(gui.YTChatFrame._build_menubar)
        self.assertIn('"&Ir al directo"', fuente)
        self.assertIn('self._accel("rep_directo")', fuente)
        self.assertIn('"ir_al_directo"', fuente)


if __name__ == "__main__":
    unittest.main()
