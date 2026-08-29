"""Pruebas de identificación segura de la ventana del smoke."""

import unittest
from types import SimpleNamespace

from smoke_test import (_recorrer, interactivos_sin_nombre,
                        ventana_es_de_la_aplicacion)


class VentanaEsDeLaAplicacionTest(unittest.TestCase):

    def test_acepta_titulo_y_python(self):
        self.assertTrue(ventana_es_de_la_aplicacion("YTChat TTS", "python.exe"))

    def test_rechaza_explorador_con_titulo_correcto(self):
        self.assertFalse(ventana_es_de_la_aplicacion(
            "YTChat TTS - para probar", "explorer.exe"))

    def test_rechaza_titulo_distinto_con_proceso_correcto(self):
        self.assertFalse(ventana_es_de_la_aplicacion("Otra ventana", "python.exe"))

    def test_compara_el_proceso_sin_mayusculas(self):
        self.assertTrue(ventana_es_de_la_aplicacion("YTChat TTS", "PYTHONW.EXE"))


class InteractivosSinNombreTest(unittest.TestCase):

    def test_devuelve_solo_los_interactivos_sin_nombre(self):
        controles = [
            ("Button", ""),
            ("Edit", "Escribir mensaje"),
            ("Text", ""),
            ("Pane", ""),
            ("List", ""),
        ]

        self.assertEqual(interactivos_sin_nombre(controles), ["Button", "List"])

    def test_ignora_interactivo_con_nombre(self):
        self.assertEqual(interactivos_sin_nombre([("CheckBox", "Activar")]), [])

    def test_ignora_no_interactivo_sin_nombre(self):
        self.assertEqual(interactivos_sin_nombre([("Text", "")]), [])

    def test_acepta_lista_vacia(self):
        self.assertEqual(interactivos_sin_nombre([]), [])


class ElementoFalso:
    def __init__(self, tipo, nombre, descendientes=()):
        self._info = SimpleNamespace(control_type=tipo, name=nombre)
        self._descendientes = list(descendientes)

    @property
    def element_info(self):
        return self._info

    def descendants(self):
        return self._descendientes


class ElementoConInfoFallido(ElementoFalso):

    @property
    def element_info(self):
        raise RuntimeError("información inaccesible")


class ElementoConDescendientesFallidos(ElementoFalso):

    def descendants(self):
        raise RuntimeError("árbol inaccesible")


class RecorrerTest(unittest.TestCase):

    def test_devuelve_raiz_y_descendientes_en_orden(self):
        boton = ElementoFalso("Button", "Conectar")
        texto = ElementoFalso("Text", "Estado")
        raiz = ElementoFalso("Window", "YTChat TTS", [boton, texto])

        self.assertEqual(_recorrer(raiz), [
            ("Window", "YTChat TTS"),
            ("Button", "Conectar"),
            ("Text", "Estado"),
        ])

    def test_salta_descendiente_cuya_informacion_falla(self):
        boton = ElementoFalso("Button", "Conectar")
        raro = ElementoConInfoFallido("Edit", "")
        raiz = ElementoFalso("Window", "YTChat TTS", [raro, boton])

        self.assertEqual(_recorrer(raiz), [
            ("Window", "YTChat TTS"),
            ("Button", "Conectar"),
        ])

    def test_devuelve_lista_vacia_si_no_puede_recorrer_descendientes(self):
        raiz = ElementoConDescendientesFallidos("Window", "YTChat TTS")

        self.assertEqual(_recorrer(raiz), [])

    def test_quita_espacios_del_nombre(self):
        raiz = ElementoFalso("Window", "   ")

        self.assertEqual(_recorrer(raiz), [("Window", "")])
