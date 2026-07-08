"""Tests de la traducción de atajos a combos wx para la pantalla completa.

Necesita wxPython (por las constantes wx.WXK_*/wx.MOD_*), así que se salta
donde no esté instalado (p. ej. CI en Linux), como el resto de lo que toca GUI.
"""

import unittest

try:
    import wx  # noqa: F401
    _HAY_WX = True
except Exception:
    _HAY_WX = False


@unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
class TestComboWx(unittest.TestCase):

    def setUp(self):
        import reproductor
        self.combo = reproductor._combo_wx

    def test_ctrl_letra(self):
        import wx
        self.assertEqual(self.combo("ctrl+p"), (wx.MOD_CONTROL, ord("P")))

    def test_ctrl_flecha(self):
        import wx
        self.assertEqual(self.combo("ctrl+left"), (wx.MOD_CONTROL, wx.WXK_LEFT))
        self.assertEqual(self.combo("ctrl+up"), (wx.MOD_CONTROL, wx.WXK_UP))

    def test_tecla_f_sin_modificador(self):
        import wx
        self.assertEqual(self.combo("f5"), (wx.MOD_NONE, wx.WXK_F5))
        self.assertEqual(self.combo("f12"), (wx.MOD_NONE, wx.WXK_F12))

    def test_alt_enter(self):
        import wx
        self.assertEqual(self.combo("alt+enter"), (wx.MOD_ALT, wx.WXK_RETURN))

    def test_invalidos(self):
        self.assertIsNone(self.combo(""))
        self.assertIsNone(self.combo("xyz+q"))
        self.assertIsNone(self.combo("ctrl+"))
        self.assertIsNone(self.combo(None))


if __name__ == "__main__":
    unittest.main()
