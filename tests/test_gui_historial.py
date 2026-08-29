import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gui_historial
import historial


def entrada(plataforma, clave, url):
    return {
        "plataforma": plataforma,
        "clave": clave,
        "url": url,
        "titulo": f"Título {clave}",
        "canal": f"Canal {clave}",
        "fecha": "2026-08-28T12:00:00",
        "directo": False,
    }


class PruebasHistorialDialog(unittest.TestCase):

    def setUp(self):
        self.app = (gui_historial.wx.App(False) if not gui_historial.wx.App.Get()
                    else gui_historial.wx.App.Get())
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.ruta = Path(self.temporal.name) / "historial.json"

    def _dialogo(self, entradas):
        self.ruta.write_text(json.dumps(entradas), encoding="utf-8")
        dialogo = gui_historial.HistorialDialog(None, self.ruta, mock.Mock())
        self.addCleanup(dialogo.Destroy)
        return dialogo

    def test_poblar_separa_las_entradas_por_plataforma(self):
        youtube = entrada("youtube", "yt", "https://youtube.com/watch?v=yt")
        tiktok = entrada("tiktok", "tk", "https://tiktok.com/@tk/live")
        dialogo = self._dialogo([youtube, tiktok])

        self.assertEqual([historial.etiqueta(youtube)],
                         list(dialogo._listas["youtube"].GetStrings()))
        self.assertEqual([historial.etiqueta(tiktok)],
                         list(dialogo._listas["tiktok"].GetStrings()))

    def test_historial_vacio_deshabilita_los_botones(self):
        dialogo = self._dialogo([])

        self.assertFalse(dialogo.btn_conectar.IsEnabled())
        self.assertFalse(dialogo.btn_quitar.IsEnabled())

    def test_seleccionada_devuelve_la_entrada_elegida_o_none(self):
        primera = entrada("youtube", "primera", "https://youtube.com/watch?v=primera")
        segunda = entrada("youtube", "segunda", "https://youtube.com/watch?v=segunda")
        dialogo = self._dialogo([primera, segunda])

        dialogo._listas["youtube"].SetSelection(1)
        self.assertEqual(segunda, dialogo._seleccionada())
        dialogo._listas["youtube"].SetSelection(gui_historial.wx.NOT_FOUND)
        self.assertIsNone(dialogo._seleccionada())

    def test_conectar_entrega_la_url_de_la_entrada_elegida(self):
        on_conectar = mock.Mock()
        url = "https://youtube.com/watch?v=elegida"
        datos = entrada("youtube", "elegida", url)
        self.ruta.write_text(json.dumps([datos]), encoding="utf-8")
        dialogo = gui_historial.HistorialDialog(None, self.ruta, on_conectar)
        self.addCleanup(dialogo.Destroy)

        with mock.patch.object(dialogo, "EndModal"):
            dialogo._conectar()

        on_conectar.assert_called_once_with(url)

    def test_conectar_sin_seleccion_anuncia_y_no_llama(self):
        dialogo = self._dialogo([entrada("youtube", "yt", "https://youtube.com/watch?v=yt")])
        dialogo._listas["youtube"].SetSelection(gui_historial.wx.NOT_FOUND)

        with mock.patch.object(gui_historial, "anunciar") as anunciar:
            dialogo._conectar()

        dialogo._on_conectar.assert_not_called()
        anunciar.assert_called_once_with("Sin selección")

    def test_quitar_elimina_guarda_y_anuncia(self):
        youtube = entrada("youtube", "yt", "https://youtube.com/watch?v=yt")
        tiktok = entrada("tiktok", "tk", "https://tiktok.com/@tk/live")
        dialogo = self._dialogo([youtube, tiktok])

        with mock.patch.object(gui_historial, "anunciar") as anunciar:
            dialogo._quitar()

        self.assertEqual(0, dialogo._listas["youtube"].GetCount())
        self.assertEqual([tiktok], historial.cargar(self.ruta))
        anunciar.assert_called_once_with("Entrada quitada del historial")

    def test_controles_tienen_los_nombres_accesibles_esperados(self):
        dialogo = self._dialogo([])
        controles = {
            "lista de YouTube": (dialogo._listas["youtube"], "Historial de YouTube"),
            "lista de TikTok": (dialogo._listas["tiktok"], "Historial de TikTok"),
            "botón Conectar": (dialogo.btn_conectar, "ConectarHistorial"),
            "botón Quitar": (dialogo.btn_quitar, "QuitarHistorial"),
        }

        for descripcion, (control, nombre) in controles.items():
            with self.subTest(control=descripcion):
                self.assertEqual(nombre, control.GetName())


if __name__ == "__main__":
    unittest.main()
