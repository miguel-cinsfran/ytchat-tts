"""Tests del parseo de atajos de teclado (config.parsear_atajos)."""

import unittest
from unittest import mock

from config import (
    _normalizar_atajo, parsear_atajos, ATAJOS_DEFAULTS, ATAJOS_AREA,
    ATAJOS_FIJOS, ATAJOS_FIJOS_DEFAULTS, ATAJOS_GRUPOS, todos_los_atajos_default,
)
import gui_preferencias
from gui_preferencias import _ETIQUETAS_ATAJO, etiqueta_de_accion


class TestNormalizarAtajo(unittest.TestCase):

    def test_none(self):
        self.assertIsNone(_normalizar_atajo(None))

    def test_vacio(self):
        self.assertIsNone(_normalizar_atajo("  "))

    def test_alt_letra(self):
        self.assertEqual(_normalizar_atajo("alt+u"), "alt+u")

    def test_alt_letra_mayuscula_y_espacios(self):
        self.assertEqual(_normalizar_atajo(" ALT + U "), "alt+u")

    def test_fkey(self):
        self.assertEqual(_normalizar_atajo("f5"), "f5")
        self.assertEqual(_normalizar_atajo("F12"), "f12")

    def test_fkey_fuera_de_rango(self):
        self.assertIsNone(_normalizar_atajo("f13"))

    def test_simbolo_permitido(self):
        self.assertEqual(_normalizar_atajo("alt+."), "alt+.")

    def test_ctrl_letra(self):
        self.assertEqual(_normalizar_atajo("ctrl+d"), "ctrl+d")

    def test_teclas_con_nombre(self):
        self.assertEqual(_normalizar_atajo("ctrl+left"), "ctrl+left")
        self.assertEqual(_normalizar_atajo("alt+enter"), "alt+enter")
        self.assertEqual(_normalizar_atajo("ctrl+up"), "ctrl+up")

    def test_modificador_no_soportado(self):
        # Shift y combinaciones multi-modificador no se admiten en el editor.
        self.assertIsNone(_normalizar_atajo("shift+u"))
        self.assertIsNone(_normalizar_atajo("ctrl+shift+x"))

    def test_tecla_nombre_desconocida(self):
        self.assertIsNone(_normalizar_atajo("ctrl+home"))


class TestParsearAtajos(unittest.TestCase):

    def test_pagina_de_atajos_usa_etiqueta_de_accion(self):
        dialogo = gui_preferencias.PreferenciasDialog.__new__(
            gui_preferencias.PreferenciasDialog)
        dialogo._config = {"atajos_raw": {}}
        panel = mock.Mock()
        boton = mock.Mock()
        sizer = mock.Mock()
        crear_boton = mock.Mock(return_value=boton)
        with mock.patch.object(dialogo, "_make_panel", return_value=panel), \
                mock.patch.object(gui_preferencias.wx, "BoxSizer", return_value=sizer), \
                mock.patch.object(gui_preferencias, "caja_de_grupo",
                                  return_value=(sizer, panel)), \
                mock.patch.object(gui_preferencias.wx, "StaticText", return_value=mock.Mock()), \
                mock.patch.object(gui_preferencias.wx, "Button", crear_boton), \
                mock.patch.object(gui_preferencias, "etiqueta_de_accion",
                                  return_value="Acción desconocida") as etiqueta:
            with mock.patch.object(gui_preferencias.cfg, "ATAJOS_DEFAULTS",
                                   {"accion_nueva": "ctrl+a"}), \
                    mock.patch.object(gui_preferencias.cfg, "ATAJOS_GRUPOS",
                                      [("Grupo", ["accion_nueva"])]), \
                    mock.patch.object(gui_preferencias.cfg, "ATAJOS_FIJOS", set()):
                dialogo._pag_atajos(object())
        etiqueta.assert_called_once_with("accion_nueva")
        self.assertEqual(crear_boton.call_args.kwargs["label"],
                         "Acción desconocida: Ctrl+A")

    def test_todas_las_acciones_tienen_etiqueta(self):
        self.assertTrue(set(todos_los_atajos_default()) <= set(_ETIQUETAS_ATAJO))

    def test_etiquetas_de_defaults_no_exponen_guiones_bajos(self):
        for accion in todos_los_atajos_default():
            self.assertNotIn("_", etiqueta_de_accion(accion))

    def test_todos_los_atajos_tienen_metadatos_y_no_colisionan(self):
        todos = todos_los_atajos_default()
        grupos = {accion for _, acciones in ATAJOS_GRUPOS for accion in acciones}
        self.assertEqual(set(todos), set(ATAJOS_AREA))
        self.assertEqual(set(todos), grupos)
        self.assertEqual(set(todos), set(_ETIQUETAS_ATAJO))
        self.assertEqual(len(todos), len(set(todos.values())))
        for accion, valor in todos.items():
            self.assertTrue(etiqueta_de_accion(accion))
            if accion in ATAJOS_FIJOS_DEFAULTS:
                normalizado = valor
            else:
                normalizado = _normalizar_atajo(valor)
            area = ATAJOS_AREA[accion]
            if accion == "region_anterior":
                self.assertEqual(normalizado, "shift+f6")
                continue
            if area == "f":
                self.assertRegex(normalizado, r"^f(1[0-2]|[1-9])$")
            else:
                self.assertTrue(normalizado.startswith(area + "+"))
        self.assertEqual(set(ATAJOS_FIJOS_DEFAULTS) | {
            "velocidad_menos", "velocidad_mas", "volumen_menos", "volumen_mas"
        }, ATAJOS_FIJOS)

    def test_etiqueta_desconocida_es_frase(self):
        self.assertEqual(
            etiqueta_de_accion("algo_que_no_existe"), "Algo que no existe")

    def test_defaults_completos(self):
        atajos = parsear_atajos({})
        # Todas las acciones por defecto quedan resueltas.
        self.assertEqual(set(atajos.keys()), set(todos_los_atajos_default().keys()))

    def test_fija_reserva_su_combinacion(self):
        atajos = parsear_atajos({"pausa": "f6"})
        self.assertEqual(atajos["region_siguiente"].texto, "f6")
        self.assertNotIn("pausa", atajos)

    def test_desactivar_con_valor_vacio(self):
        atajos = parsear_atajos({"pausa": ""})
        self.assertNotIn("pausa", atajos)

    def test_valor_invalido_cae_al_default(self):
        atajos = parsear_atajos({"pausa": "ctrl+shift+x"})
        # Inválido -> usa el default de pausa (f5).
        self.assertIn("pausa", atajos)
        self.assertEqual(atajos["pausa"].texto, ATAJOS_DEFAULTS["pausa"])

    def test_conflicto_descarta_el_segundo(self):
        # Dos acciones reclamando la misma tecla: la segunda se descarta.
        atajos = parsear_atajos({"pausa": "f3", "detener_tts": "f3"})
        teclas = [a.tecla for a in atajos.values()]
        # 'f3' aparece una sola vez.
        self.assertEqual(teclas.count("f3"), 1)

    def test_override_valido(self):
        atajos = parsear_atajos({"pausa": "alt+j"})
        self.assertEqual(atajos["pausa"].texto, "alt+j")

    def test_ctrl_y_alt_misma_letra_no_chocan(self):
        # 'ctrl+d' (rep_detener) y 'alt+d' (desconectar) conviven.
        atajos = parsear_atajos({})
        self.assertEqual(atajos["rep_detener"].texto, "ctrl+d")
        self.assertEqual(atajos["desconectar"].texto, "alt+d")


if __name__ == "__main__":
    unittest.main()
