import unittest

import iconos


class PruebasIconos(unittest.TestCase):

    def setUp(self):
        self.app = (iconos.wx.App(False) if not iconos.wx.App.Get()
                    else iconos.wx.App.Get())

    def test_cada_dibujo_devuelve_un_bitmap_valido(self):
        for nombre in iconos._DIBUJOS:
            with self.subTest(nombre=nombre):
                bitmap = iconos.icono(
                    nombre, iconos.wx.Colour("white"), iconos.wx.Colour("black"))
                self.assertTrue(bitmap.IsOk())

    def test_el_bitmap_respeta_el_lado_pedido(self):
        for lado in (18, 32):
            with self.subTest(lado=lado):
                bitmap = iconos.icono(
                    "play", iconos.wx.Colour("white"), iconos.wx.Colour("black"), lado)
                self.assertEqual(lado, bitmap.GetWidth())
                self.assertEqual(lado, bitmap.GetHeight())

    def test_nombre_desconocido_devuelve_un_bitmap_valido(self):
        bitmap = iconos.icono(
            "inexistente", iconos.wx.Colour("white"), iconos.wx.Colour("black"))

        self.assertTrue(bitmap.IsOk())


if __name__ == "__main__":
    unittest.main()
