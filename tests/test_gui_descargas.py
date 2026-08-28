"""Pruebas de accesibilidad del selector de carpeta."""

import unittest
import threading
from unittest import mock

import descargas
import gui_descargas

try:
    import wx
    _HAY_WX = True
except Exception:
    _HAY_WX = False


class _DobleControl:

    def __init__(self):
        self.etiquetas = []

    def SetLabel(self, texto):
        self.etiquetas.append(texto)


class _DobleSelector:

    def __init__(self):
        self.texto = _DobleControl()
        self.boton = _DobleControl()

    def GetTextCtrl(self):
        return self.texto

    def GetPickerCtrl(self):
        return self.boton


class TestNombrarSelectorCarpeta(unittest.TestCase):

    def test_nombra_campo_y_boton(self):
        selector = _DobleSelector()
        llamadas = []

        def nombrar(control, nombre):
            llamadas.append((control, nombre))

        with mock.patch.object(gui_descargas, "nombre_accesible", nombrar):
            gui_descargas.nombrar_selector_carpeta(selector)

        self.assertEqual(
            llamadas[0], (selector.texto, "Carpeta de destino de las descargas"))
        self.assertEqual(selector.boton.etiquetas, ["Examinar…"])
        self.assertEqual(llamadas[1], (selector.boton, "Examinar…"))
        self.assertTrue(llamadas[1][1].startswith("Examinar"))
        self.assertNotEqual(llamadas[1][1], "Browse")

    def test_acepta_selector_sin_controles_internos(self):
        with mock.patch.object(gui_descargas, "nombre_accesible") as nombrar:
            gui_descargas.nombrar_selector_carpeta(object())

        nombrar.assert_not_called()


@unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
class TestGruposGestorDescargas(unittest.TestCase):

    def setUp(self):
        self.app = wx.App() if not wx.App.Get() else wx.App.Get()

    def tearDown(self):
        descargas.reiniciar_gestor()

    def test_controles_anunciables_cuelgan_de_su_grupo(self):
        dialogo = gui_descargas.GestorDescargasDialog(None)
        try:
            esperados = {
                "EnumerarPlaylist": "Opciones de descarga",
                "EtiquetaURL": "Añadir URL",
                "URL del vídeo o playlist": "Añadir URL",
                "Cola de descargas": "Cola de descargas",
            }
            encontrados = {}
            pendientes = list(dialogo.GetChildren())
            while pendientes:
                control = pendientes.pop()
                pendientes.extend(control.GetChildren())
                if control.GetName() in esperados:
                    encontrados[control.GetName()] = control
            self.assertEqual(set(esperados), set(encontrados))
            for nombre, control in encontrados.items():
                padre = control.GetParent()
                self.assertIsInstance(padre, wx.StaticBox,
                                      msg=nombre)
                self.assertEqual(esperados[nombre], padre.GetLabel())
        finally:
            dialogo.Destroy()

    def test_progreso_rezagado_despues_de_cerrar_no_lanza(self):
        dialogo = gui_descargas.GestorDescargasDialog(None)
        dialogo.lista.InsertItem(0, "archivo.mp4")
        dialogo._items_fila["item"] = 0
        dialogo._on_cerrar(None)
        wx.Yield()
        dialogo._actualizar_progreso("item", 50, "archivo.mp4")
        dialogo._actualizar_estado("item", "completado", "")

    def test_callbacks_rezagados_despues_de_destruir_no_lanzan(self):
        dialogo = gui_descargas.GestorDescargasDialog(None)
        dialogo.lista.InsertItem(0, "archivo.mp4")
        dialogo._items_fila["item"] = 0
        dialogo.Destroy()
        wx.Yield()
        dialogo._actualizar_progreso("item", 50, "archivo.mp4")
        dialogo._actualizar_estado("item", "completado", "")

    def test_fin_avisado_despues_de_cerrar_el_dialogo(self):
        inicio = threading.Event()
        terminar = threading.Event()
        completada = threading.Event()

        def descarga_simulada(_url, _opciones, _progreso, estado, _cancelar):
            inicio.set()
            terminar.wait(1)
            estado("completado", "")
            completada.set()

        with mock.patch.object(descargas, "analizar_url", return_value={}), \
                mock.patch.object(descargas, "descargar", descarga_simulada), \
                mock.patch.object(gui_descargas, "anunciar") as anunciar, \
                mock.patch.object(gui_descargas._snd, "reproducir") as sonido:
            dialogo = gui_descargas.GestorDescargasDialog(None)
            dialogo._gestor.encolar("https://youtu.be/video", lambda *_: None,
                                    lambda *_: None)
            self.assertTrue(inicio.wait(1))
            dialogo.Destroy()
            terminar.set()
            self.assertTrue(completada.wait(1))
            wx.Yield()

        anunciar.assert_called_once_with("Descarga completada")
        sonido.assert_called_once_with("copiar")


if __name__ == "__main__":
    unittest.main()
