"""Tests del parseo de atajos de teclado (config.parsear_atajos)."""

import unittest
import inspect
from unittest import mock

from config import (
    _normalizar_atajo, parsear_atajos, detectar_conflictos_atajos,
    ATAJOS_DEFAULTS, ATAJOS_AREA, atajo_valido_para_area,
    ATAJOS_FIJOS, ATAJOS_FIJOS_DEFAULTS, ATAJOS_GRUPOS, todos_los_atajos_default,
)
import gui_preferencias
import gui
import atajos_captura
import config
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
        # Shift solo y combinaciones distintas de Ctrl+Shift no se admiten.
        self.assertIsNone(_normalizar_atajo("shift+u"))
        self.assertIsNone(_normalizar_atajo("alt+shift+x"))
        self.assertIsNone(_normalizar_atajo("ctrl+alt+x"))
        self.assertEqual(_normalizar_atajo("ctrl+shift+x"), "ctrl+shift+x")

    def test_tecla_nombre_desconocida(self):
        self.assertIsNone(_normalizar_atajo("ctrl+home"))

    def test_ctrl_shift_tecla_con_nombre(self):
        self.assertEqual(_normalizar_atajo("ctrl+shift+left"), "ctrl+shift+left")


class TestAreasAtajo(unittest.TestCase):

    def test_ctrl_shift_no_pertenece_al_area_ctrl(self):
        with mock.patch.dict(config.ATAJOS_AREA, {"accion": "ctrl"}):
            self.assertFalse(atajo_valido_para_area("accion", "ctrl+shift+p"))

    def test_ctrl_shift_pertenece_a_su_area(self):
        with mock.patch.dict(config.ATAJOS_AREA, {"accion": "ctrl+shift"}):
            self.assertTrue(atajo_valido_para_area("accion", "ctrl+shift+p"))


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
        llamada = next(llamada for llamada in crear_boton.call_args_list
                       if llamada.kwargs["name"] == "Atajo_accion_nueva")
        self.assertEqual(llamada.kwargs["label"],
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
            area = ATAJOS_AREA.get(accion)
            if area is None:
                self.assertIn(accion, ATAJOS_FIJOS_DEFAULTS)
                continue
            if area == "f":
                self.assertRegex(normalizado, r"^f(1[0-2]|[1-9])$")
            else:
                self.assertTrue(normalizado.startswith(area + "+"))
        self.assertEqual(set(ATAJOS_FIJOS_DEFAULTS) | {
            "velocidad_menos", "velocidad_mas", "volumen_menos", "volumen_mas"
        }, ATAJOS_FIJOS)

    def test_atajos_fijos_tienen_grupo_sin_area(self):
        grupos_fijos = [acciones for titulo, acciones in ATAJOS_GRUPOS
                        if "Ventana y navegación" in titulo]
        self.assertEqual(grupos_fijos, [["salir", "region_siguiente", "region_anterior"]])
        for accion in ATAJOS_FIJOS_DEFAULTS:
            self.assertIsNone(ATAJOS_AREA[accion])

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

    def test_las_fijas_sobreviven_a_un_valor_vacio(self):
        atajos = parsear_atajos({accion: "" for accion in ATAJOS_FIJOS})
        for accion, esperado in ATAJOS_FIJOS_DEFAULTS.items():
            self.assertEqual(atajos[accion].texto, esperado)
        for accion in ("velocidad_menos", "velocidad_mas",
                       "volumen_menos", "volumen_mas"):
            self.assertEqual(atajos[accion].texto, ATAJOS_DEFAULTS[accion])

    def test_valor_invalido_cae_al_default(self):
        atajos = parsear_atajos({"pausa": "ctrl+home"})
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

    def test_nuevos_atajos_editables_tienen_area_y_grupo(self):
        for accion, valor, area in (
                ("pantalla_completa", "ctrl+f", "ctrl"),
                ("ir_lista", "alt+l", "alt"),
                ("abrir_preferencias", "ctrl+shift+p", "ctrl+shift"),
                ("abrir_historial", "ctrl+shift+h", "ctrl+shift"),
                ("marcar_incidencia", "ctrl+shift+i", "ctrl+shift"),
                ("obs_micro", "ctrl+shift+m", "ctrl+shift")):
            self.assertEqual(ATAJOS_DEFAULTS[accion], valor)
            self.assertTrue(atajo_valido_para_area(accion, valor),
                            f"{accion} no tiene un atajo válido para su área")
            self.assertEqual(ATAJOS_AREA[accion], area)
            self.assertNotIn(accion, ATAJOS_FIJOS)
            self.assertIn(accion, {
                accion_grupo for _, acciones in ATAJOS_GRUPOS for accion_grupo in acciones
            })

    def test_menus_usan_el_sistema_para_los_nuevos_atajos(self):
        fuente = inspect.getsource(gui.YTChatFrame._build_menubar)
        self.assertIn('self._accel("ir_lista")', fuente)
        self.assertIn('self._accel("pantalla_completa")', fuente)
        self.assertIn('self._accel("abrir_historial")', fuente)
        self.assertIn('self._accel("abrir_preferencias")', fuente)
        self.assertIn('self._accel("marcar_incidencia")', fuente)
        self.assertIn('self._accel("obs_micro")', fuente)
        self.assertNotIn("\\tAlt+L", fuente)
        self.assertNotIn("\\tCtrl+F", fuente)

    def test_conflicto_incluye_las_fijas(self):
        self.assertEqual(
            detectar_conflictos_atajos({"pausa": "f6"}),
            [("pausa", "region_siguiente", "f6")])

    def test_captura_rechaza_fija_incluso_si_la_gramatica_no_la_admite(self):
        resultado = atajos_captura.resolver(
            "ir_lista", "alt+f4", {"ir_lista": "alt+l", "salir": "alt+f4"})
        self.assertEqual(resultado, (
            "rechazado", None,
            "Ya lo usa: Salir de la aplicación. Elige otra."))

    def test_rechazo_muestra_aviso_y_vuelve_a_capturar(self):
        import wx
        dialogo = gui_preferencias.PreferenciasDialog.__new__(
            gui_preferencias.PreferenciasDialog)
        boton = mock.Mock()
        dialogo._capturando_atajo = ("ir_lista", "Ir a la lista del panel actual")
        dialogo._valores_atajo = {"ir_lista": "alt+l", "salir": "alt+f4"}
        dialogo._botones_atajo = {"ir_lista": boton}
        evento = mock.Mock()
        evento.GetKeyCode.return_value = wx.WXK_F4
        evento.GetModifiers.return_value = wx.MOD_ALT
        texto = "Ya lo usa: Salir de la aplicación. Elige otra."
        anuncios = []
        with mock.patch.object(gui_preferencias, "anunciar",
                               side_effect=anuncios.append), \
                mock.patch.object(gui_preferencias.wx, "MessageBox") as aviso:
            dialogo._on_tecla_captura(evento)
        aviso.assert_called_once_with(
            texto, gui_preferencias.APP_NAME, wx.OK | wx.ICON_ERROR, dialogo)
        boton.SetFocus.assert_called_once_with()
        self.assertEqual(dialogo._capturando_atajo,
                         ("ir_lista", "Ir a la lista del panel actual"))
        self.assertEqual(anuncios, [texto,
                                    atajos_captura.texto_de_espera(
                                        "Ir a la lista del panel actual",
                                        "Debe ser Alt y una tecla (por ejemplo Alt+C).")])

    def test_arranque_anuncia_la_accion_que_pierde(self):
        anuncios = []
        with mock.patch.object(gui, "anunciar", side_effect=anuncios.append):
            gui.anunciar_conflictos_atajos({"pausa": "f6"})
        self.assertEqual(anuncios, [
            "Conflicto de atajos: pausa se quedó sin atajo porque "
            "region_siguiente usa f6."
        ])


    def test_construccion_del_frame_anuncia_los_conflictos(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        configuracion = {"atajos_raw": {"pausa": "f6"}}
        with mock.patch.object(gui.wx.Frame, "__init__", return_value=None), \
                mock.patch.object(gui.YTChatFrame, "SetBackgroundColour"), \
                mock.patch.object(gui.YTChatFrame, "_build_menubar"), \
                mock.patch.object(gui.YTChatFrame, "_build_ui"), \
                mock.patch.object(gui.YTChatFrame, "_bind_events"), \
                mock.patch.object(gui.YTChatFrame, "_init_timer"), \
                mock.patch.object(gui.YTChatFrame, "Centre"), \
                mock.patch.object(gui, "anunciar_conflictos_atajos") as anunciar:
            gui.YTChatFrame.__init__(frame, None, configuracion, None, None, None, None)

        anunciar.assert_called_once_with(configuracion["atajos_raw"])


if __name__ == "__main__":
    unittest.main()
