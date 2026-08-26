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
            "Pulsá la combinación para Conectar. "
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


if __name__ == "__main__":
    unittest.main()
