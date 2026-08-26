import unittest
from unittest import mock

import wx

import gui_redactar


class EventoTeclado:
    def __init__(self, codigo, mayus=False):
        self.codigo = codigo
        self.mayus = mayus
        self.omitido = False

    def GetKeyCode(self):
        return self.codigo

    def ShiftDown(self):
        return self.mayus

    def Skip(self):
        self.omitido = True


class TestPanelRedactar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App() if not wx.App.Get() else wx.App.Get()
        cls.frame = wx.Frame(None)

    @classmethod
    def tearDownClass(cls):
        cls.frame.Destroy()

    def panel(self, texto="mensaje", motivo=""):
        enviado = []
        panel = gui_redactar.PanelRedactar(
            self.frame, "&Mensaje:", 200, enviado.append)
        panel.texto.SetValue(texto)
        panel.establecer_motivo(motivo)
        panel._enviado = enviado
        return panel

    def test_enter_envia_y_no_deja_pasarlo(self):
        panel = self.panel()
        evento = EventoTeclado(wx.WXK_RETURN)
        with mock.patch.object(panel, "_on_enviar", wraps=panel._on_enviar) as enviar:
            panel._on_char_hook(evento)
        self.assertEqual(panel._enviado, ["mensaje"])
        enviar.assert_called_once_with(evento)
        self.assertFalse(evento.omitido)
        panel.Destroy()

    def test_texto_enlaza_char_hook(self):
        with mock.patch.object(wx.TextCtrl, "Bind") as enlazar:
            panel = gui_redactar.PanelRedactar(
                self.frame, "&Mensaje:", 200, lambda texto: None)
        eventos = [llamada.args[0] for llamada in enlazar.call_args_list]
        self.assertIn(wx.EVT_CHAR_HOOK, eventos)
        panel.Destroy()

    def test_mayusculas_enter_inserta_salto_y_no_envia(self):
        panel = self.panel()
        evento = EventoTeclado(wx.WXK_RETURN, mayus=True)
        panel._on_char_hook(evento)
        self.assertEqual(panel._enviado, [])
        self.assertTrue(evento.omitido)
        panel.Destroy()

    def test_otra_tecla_se_deja_pasar(self):
        panel = self.panel()
        evento = EventoTeclado(ord("a"))
        panel._on_char_hook(evento)
        self.assertEqual(panel._enviado, [])
        self.assertTrue(evento.omitido)
        panel.Destroy()

    def test_motivo_no_envia_y_anuncia(self):
        panel = self.panel(motivo="Inicia sesión")
        with mock.patch.object(gui_redactar, "_anunciar") as anunciar:
            panel._on_enviar(None)
        self.assertEqual(panel._enviado, [])
        anunciar.assert_called_once_with("Inicia sesión")
        panel.Destroy()

    def test_texto_vacio_no_envia_y_anuncia_validacion(self):
        panel = self.panel(texto="   ")
        with mock.patch.object(gui_redactar, "_anunciar") as anunciar:
            panel._on_enviar(None)
        self.assertEqual(panel._enviado, [])
        anunciar.assert_called_once_with("Escribe un mensaje antes de enviar")
        panel.Destroy()

    def test_envio_correcto_vacia_el_cuadro(self):
        panel = self.panel("  mensaje  ")
        panel._on_enviar(None)
        self.assertEqual(panel._enviado, ["mensaje"])
        self.assertEqual(panel.texto.GetValue(), "")
        panel.Destroy()


if __name__ == "__main__":
    unittest.main()
