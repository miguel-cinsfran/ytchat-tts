"""Tests de la captura de atajos (conversión tecla→texto y visualización).

Necesita wxPython (usa constantes wx.WXK_*/wx.MOD_*), así que se salta donde no
esté instalado, como el resto de lo que toca GUI.
"""

import unittest

try:
    import wx  # noqa: F401
    _HAY_WX = True
except Exception:
    _HAY_WX = False


@unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
class TestCapturaAtajos(unittest.TestCase):

    def setUp(self):
        # wx.App necesaria para instanciar/usar helpers que tocan wx.
        import wx
        self.app = wx.App() if not wx.App.Get() else wx.App.Get()
        import gui_preferencias as gp
        self.gp = gp

    def test_combo_ctrl_letra(self):
        import wx
        self.assertEqual(self.gp._combo_a_texto(wx.MOD_CONTROL, ord("P")), "ctrl+p")

    def test_combo_alt_enter(self):
        import wx
        self.assertEqual(self.gp._combo_a_texto(wx.MOD_ALT, wx.WXK_RETURN), "alt+enter")

    def test_combo_fkey_sin_modificador(self):
        import wx
        self.assertEqual(self.gp._combo_a_texto(wx.MOD_NONE, wx.WXK_F5), "f5")

    def test_combo_ctrl_flecha(self):
        import wx
        self.assertEqual(self.gp._combo_a_texto(wx.MOD_CONTROL, wx.WXK_LEFT), "ctrl+left")

    def test_combo_shift_incluido_para_que_se_rechace(self):
        import wx
        # Ctrl+Shift+P se captura tal cual; la validación de config lo rechaza.
        import config as cfg
        combo = self.gp._combo_a_texto(wx.MOD_CONTROL | wx.MOD_SHIFT, ord("P"))
        self.assertEqual(combo, "ctrl+shift+p")
        self.assertIsNone(cfg._normalizar_atajo(combo))

    def test_tecla_no_admitida(self):
        import wx
        self.assertIsNone(self.gp._combo_a_texto(wx.MOD_NONE, wx.WXK_CAPITAL))

    def test_mostrar_atajo(self):
        self.assertEqual(self.gp._mostrar_atajo("ctrl+p"), "Ctrl+P")
        self.assertEqual(self.gp._mostrar_atajo("alt+enter"), "Alt+Enter")
        self.assertEqual(self.gp._mostrar_atajo("ctrl+left"), "Ctrl+Left")
        self.assertEqual(self.gp._mostrar_atajo("f5"), "F5")
        self.assertEqual(self.gp._mostrar_atajo(""), "(sin asignar)")

    def test_caja_de_grupo_devuelve_la_caja_como_padre(self):
        import wx
        frame = wx.Frame(None)
        try:
            panel = wx.Panel(frame)
            sizer, caja = self.gp.caja_de_grupo(panel, "Grupo de prueba")
            boton = wx.Button(caja, label="Botón")

            self.assertIs(boton.GetParent(), caja)
            self.assertEqual(caja.GetLabel(), "Grupo de prueba")
            self.assertIs(sizer.GetStaticBox(), caja)
        finally:
            frame.Destroy()

    def test_los_atajos_cuelgan_de_su_caja_de_grupo(self):
        import wx
        import config as cfg
        dialogo = self.gp.PreferenciasDialog(None, {})
        try:
            controles = []
            pendientes = list(dialogo.GetChildren())
            while pendientes:
                control = pendientes.pop()
                pendientes.extend(control.GetChildren())
                if (isinstance(control, wx.Button) and
                        control.GetName().startswith("Atajo_")):
                    controles.append(control)

            self.assertEqual(len(controles), 20)
            titulos = {titulo for titulo, _acciones in cfg.ATAJOS_GRUPOS}
            for boton in controles:
                caja = boton.GetParent()
                self.assertIsInstance(caja, wx.StaticBox)
                self.assertIn(caja.GetLabel(), titulos)
        finally:
            dialogo.Destroy()


if __name__ == "__main__":
    unittest.main()
