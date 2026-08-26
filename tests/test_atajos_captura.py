"""Pruebas de las decisiones de captura de atajos."""

import unittest
from unittest import mock

import atajos_captura

try:
    import wx  # noqa: F401
    _HAY_WX = True
except Exception:
    _HAY_WX = False


class TestAtajosCaptura(unittest.TestCase):

    def setUp(self):
        self.valores = {
            "rep_play": "ctrl+p",
            "rep_retro": "ctrl+k",
        }

    def test_captura_valida(self):
        resultado = atajos_captura.resolver("rep_play", "ctrl+q", self.valores)
        self.assertEqual(resultado, (
            "capturado", "ctrl+q", "Capturado: Ctrl+Q. Guardado."))

    def test_combinacion_invalida_para_el_area(self):
        resultado = atajos_captura.resolver("rep_play", "alt+k", self.valores)
        self.assertEqual(resultado, (
            "rechazado", None,
            "No vale aquí. Debe ser Ctrl y una tecla (por ejemplo Ctrl+P)."))

    def test_choque_con_otra_accion(self):
        resultado = atajos_captura.resolver("rep_play", "ctrl+k", self.valores)
        self.assertEqual(resultado, (
            "rechazado", None, "Ya lo usa: Retroceder 1 minuto. Elige otra."))

    def test_desactivado(self):
        resultado = atajos_captura.resolver("rep_play", None, self.valores)
        self.assertEqual(resultado, (
            "desactivado", "", "Reproducir o pausa sin atajo. Desactivado."))

    def test_textos_de_etiqueta_y_espera(self):
        self.assertEqual(
            atajos_captura.mostrar_atajo("alt+enter"), "Alt+Enter")
        self.assertEqual(
            atajos_captura.etiqueta_boton("Conectar", "alt+c"),
            "Conectar: Alt+C")
        self.assertEqual(
            atajos_captura.etiqueta_boton("Conectar", ""),
            "Conectar: (sin asignar)")
        self.assertEqual(
            atajos_captura.texto_de_espera(
                "Conectar", "Debe ser Alt y una tecla (por ejemplo Alt+C)."),
            "Pulsa la combinación para Conectar. "
            "Debe ser Alt y una tecla (por ejemplo Alt+C). "
            "Enter la deja sin atajo. Escape cancela.")

    @unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
    def test_la_pagina_entrega_la_combinacion_al_resolvedor(self):
        import wx
        import gui_preferencias as gp
        dialogo = gp.PreferenciasDialog.__new__(gp.PreferenciasDialog)
        boton = mock.Mock()
        dialogo._capturando_atajo = ("rep_play", "Reproducir o pausa")
        dialogo._valores_atajo = {"rep_play": "ctrl+p"}
        dialogo._botones_atajo = {"rep_play": boton}
        evento = mock.Mock()
        evento.GetKeyCode.return_value = ord("Q")
        evento.GetModifiers.return_value = wx.MOD_CONTROL
        with mock.patch.object(gp.atajos_captura, "resolver",
                               return_value=("capturado", "ctrl+q", "Guardado")) as resolver:
            with mock.patch.object(gp, "anunciar"):
                dialogo._on_tecla_captura(evento)
        resolver.assert_called_once_with(
            "rep_play", "ctrl+q", {"rep_play": "ctrl+q"})
        self.assertEqual(dialogo._valores_atajo["rep_play"], "ctrl+q")
        boton.SetLabel.assert_called_once_with(
            "Reproducir o pausa: Ctrl+Q")

    @unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
    def test_escape_cancela_la_captura(self):
        import wx
        import gui_preferencias as gp
        dialogo = gp.PreferenciasDialog.__new__(gp.PreferenciasDialog)
        dialogo._capturando_atajo = ("rep_play", "Reproducir o pausa")
        dialogo._valores_atajo = {"rep_play": "ctrl+q"}
        dialogo._botones_atajo = {"rep_play": mock.Mock()}
        evento = mock.Mock()
        evento.GetKeyCode.return_value = wx.WXK_ESCAPE
        evento.GetModifiers.return_value = wx.MOD_NONE
        with mock.patch.object(gp, "anunciar") as anunciar:
            dialogo._on_tecla_captura(evento)
        self.assertIsNone(dialogo._capturando_atajo)
        self.assertEqual(dialogo._valores_atajo["rep_play"], "ctrl+q")
        anunciar.assert_called_once_with("Sin cambios")

    @unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
    def test_tab_sale_de_la_captura_y_deja_navegar(self):
        import wx
        import gui_preferencias as gp
        dialogo = gp.PreferenciasDialog.__new__(gp.PreferenciasDialog)
        dialogo._capturando_atajo = ("rep_play", "Reproducir o pausa")
        dialogo._valores_atajo = {"rep_play": "ctrl+q"}
        dialogo._botones_atajo = {"rep_play": mock.Mock()}
        evento = mock.Mock()
        evento.GetKeyCode.return_value = wx.WXK_TAB
        evento.GetModifiers.return_value = wx.MOD_NONE
        dialogo._on_tecla_captura(evento)
        self.assertIsNone(dialogo._capturando_atajo)
        self.assertEqual(dialogo._valores_atajo["rep_play"], "ctrl+q")
        evento.Skip.assert_called_once_with()

    @unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
    def test_tecla_de_solo_modificador_no_resuelve_el_atajo(self):
        import wx
        import gui_preferencias as gp
        dialogo = gp.PreferenciasDialog.__new__(gp.PreferenciasDialog)
        captura = ("rep_play", "Reproducir o pausa")
        dialogo._capturando_atajo = captura
        dialogo._valores_atajo = {"rep_play": "ctrl+q"}
        evento = mock.Mock()
        evento.GetKeyCode.return_value = wx.WXK_SHIFT
        evento.GetModifiers.return_value = wx.MOD_NONE
        with mock.patch.object(gp.atajos_captura, "resolver") as resolver:
            dialogo._on_tecla_captura(evento)
        self.assertEqual(dialogo._capturando_atajo, captura)
        self.assertEqual(dialogo._valores_atajo["rep_play"], "ctrl+q")
        resolver.assert_not_called()

    @unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
    def test_enter_solo_desactiva_y_alt_enter_se_captura(self):
        import wx
        import gui_preferencias as gp
        dialogo = gp.PreferenciasDialog.__new__(gp.PreferenciasDialog)
        dialogo._capturando_atajo = ("rep_play", "Reproducir o pausa")
        dialogo._valores_atajo = {"rep_play": "ctrl+p"}
        dialogo._botones_atajo = {"rep_play": mock.Mock()}
        evento = mock.Mock()
        evento.GetKeyCode.return_value = wx.WXK_RETURN
        evento.GetModifiers.return_value = wx.MOD_ALT
        with mock.patch.object(
                gp.atajos_captura, "resolver",
                return_value=("capturado", "alt+enter", "Guardado")) as resolver:
            dialogo._on_tecla_captura(evento)
        resolver.assert_called_once_with(
            "rep_play", "alt+enter", {"rep_play": "alt+enter"})

        dialogo._capturando_atajo = ("rep_play", "Reproducir o pausa")
        evento.GetModifiers.return_value = wx.MOD_NONE
        with mock.patch.object(
                gp.atajos_captura, "resolver",
                return_value=("desactivado", "", "Desactivado")) as resolver:
            dialogo._on_tecla_captura(evento)
        resolver.assert_called_once_with(
            "rep_play", None, {"rep_play": ""})

    @unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
    def test_restablecer_cambia_solo_los_atajos_editables(self):
        import gui_preferencias as gp
        import config as cfg
        dialogo = gp.PreferenciasDialog.__new__(gp.PreferenciasDialog)
        dialogo._valores_atajo = cfg.todos_los_atajos_default()
        dialogo._valores_atajo["rep_play"] = "ctrl+q"
        dialogo._valores_atajo["salir"] = "alt+x"
        dialogo._botones_atajo = {
            accion: mock.Mock() for accion in dialogo._valores_atajo}
        with mock.patch.object(gp, "anunciar") as anunciar:
            dialogo._restablecer_atajos(None)
        self.assertEqual(dialogo._valores_atajo["rep_play"], "ctrl+p")
        self.assertEqual(dialogo._valores_atajo["salir"], "alt+x")
        dialogo._botones_atajo["rep_play"].SetLabel.assert_called_once_with(
            "Reproducir o pausa: Ctrl+P")
        anunciar.assert_called_once_with(
            "Atajos restablecidos a los valores de fábrica")

    @unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
    def test_cancelar_restaurar_la_etiqueta_y_anunciar_sin_cambios(self):
        import gui_preferencias as gp
        dialogo = gp.PreferenciasDialog.__new__(gp.PreferenciasDialog)
        boton = mock.Mock()
        dialogo._capturando_atajo = ("rep_play", "Reproducir o pausa")
        dialogo._valores_atajo = {"rep_play": "ctrl+q"}
        dialogo._botones_atajo = {"rep_play": boton}
        with mock.patch.object(gp, "anunciar") as anunciar:
            dialogo._salir_captura_atajo(True)
        boton.SetLabel.assert_called_once_with(
            "Reproducir o pausa: Ctrl+Q")
        anunciar.assert_called_once_with("Sin cambios")


if __name__ == "__main__":
    unittest.main()
