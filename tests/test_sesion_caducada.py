"""Sesión de YouTube caducada: aviso con voz y cierre del token muerto.

Sin ventanas: no se crea wx.App ni diálogos reales. Los marcos se arman con
`__new__` (o un espacio de nombres para `_api_err`, cuyo guarda `if not self`
trata a un marco sin construir como ventana destruida) y los diálogos con
dobles.
"""

import importlib.util
import types
import unittest
from unittest import mock

import wx

from ytchat.youtube import youtube_api
from ytchat.ui import gui
from ytchat.ui import gui_comentarios
from ytchat.ui import gui_preferencias


FRASE_SESION = ("Tu sesión de YouTube caducó. Vuelve a iniciar sesión en "
                "Preferencias, pestaña API y sesión.")
FRASE_PROGRAMADO = ("Los mensajes automáticos se detuvieron porque la sesión "
                    "de YouTube caducó.")


class RefreshError(Exception):
    """Doble con el mismo nombre de clase que google.auth RefreshError."""


class HiloDirecto:
    """El hilo de trabajo corre en el acto, como en las pruebas de gui."""

    def __init__(self, objetivo):
        self.objetivo = objetivo

    def start(self):
        self.objetivo()


class TestSesionCaducada(unittest.TestCase):

    def test_nombre_refresh_error(self):
        self.assertTrue(youtube_api.sesion_caducada(RefreshError("boom")))

    def test_texto_invalid_grant(self):
        self.assertTrue(youtube_api.sesion_caducada(
            Exception("('invalid_grant: Bad Request', ...)")))
        self.assertTrue(youtube_api.sesion_caducada(
            Exception("INVALID_GRANT en mayúsculas también vale")))

    def test_error_comun_no_es_sesion(self):
        self.assertFalse(youtube_api.sesion_caducada(Exception("quotaExceeded")))
        self.assertFalse(youtube_api.sesion_caducada(Exception("algo raro")))


class TestMensajeSesion(unittest.TestCase):

    def test_frase_exacta_con_refresh_error(self):
        self.assertEqual(youtube_api.mensaje_error_api(RefreshError("x")),
                         FRASE_SESION)

    def test_frase_exacta_con_invalid_grant(self):
        self.assertEqual(
            youtube_api.mensaje_error_api(Exception("invalid_grant: Bad Request")),
            FRASE_SESION)

    def test_otros_casos_quedan_igual(self):
        self.assertIn("cuota", youtube_api.mensaje_error_api("quotaExceeded"))
        self.assertIn("Error de la API",
                      youtube_api.mensaje_error_api("algo raro"))

    @unittest.skipUnless(importlib.util.find_spec("google.auth.exceptions"),
                         "sin google-auth instalado")
    def test_clase_real_de_google(self):
        from google.auth.exceptions import RefreshError as Real
        exc = Real("invalid_grant: Bad Request")
        self.assertTrue(youtube_api.sesion_caducada(exc))
        self.assertEqual(youtube_api.mensaje_error_api(exc), FRASE_SESION)


class TestCierreAntesDelAviso(unittest.TestCase):
    """El token muerto se borra en el hilo, antes de avisar a la interfaz."""

    def _orden_accion_api(self, exc):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        orden = []

        def _falla(_cli):
            raise exc

        with mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.diagnostico, "crear_hilo",
                                  side_effect=lambda ob, n: HiloDirecto(ob)), \
                mock.patch.object(gui.wx, "CallAfter",
                                  side_effect=lambda fn, *a: orden.append("aviso")), \
                mock.patch.object(gui.credenciales, "cargar", return_value={}), \
                mock.patch.object(gui.youtube_api, "ClienteYouTube",
                                  return_value=mock.Mock(
                                      token_actualizado=mock.Mock(return_value=None))), \
                mock.patch.object(gui.credenciales, "cerrar_sesion",
                                  side_effect=lambda: orden.append("cierre")):
            frame._accion_api(_falla, "ok")
        return orden

    def test_accion_api_cierra_antes_de_agendar_el_error(self):
        self.assertEqual(
            self._orden_accion_api(RefreshError("invalid_grant: Bad Request")),
            ["cierre", "aviso"])

    def test_accion_api_con_error_comun_no_cierra(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        with mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.diagnostico, "crear_hilo",
                                  side_effect=lambda ob, n: HiloDirecto(ob)), \
                mock.patch.object(gui.wx, "CallAfter"), \
                mock.patch.object(gui.credenciales, "cargar", return_value={}), \
                mock.patch.object(gui.youtube_api, "ClienteYouTube",
                                  return_value=mock.Mock(
                                      token_actualizado=mock.Mock(return_value=None))), \
                mock.patch.object(gui.credenciales, "cerrar_sesion") as cierre:
            frame._accion_api(mock.Mock(side_effect=RuntimeError("quotaExceeded")),
                              "ok")
        cierre.assert_not_called()

    def test_programado_cierra_antes_de_agendar_el_fallo(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._live_chat_id = "chat"
        frame._programado_en_curso = False
        orden = []
        cliente = mock.Mock()
        cliente.enviar_mensaje_live.side_effect = RefreshError("invalid_grant")
        cliente.token_actualizado.return_value = None
        with mock.patch.object(gui.youtube_api, "ClienteYouTube",
                               return_value=cliente), \
                mock.patch.object(gui.credenciales, "cargar", return_value={}), \
                mock.patch.object(gui.diagnostico, "crear_hilo",
                                  side_effect=lambda ob, n: HiloDirecto(ob)), \
                mock.patch.object(gui.wx, "CallAfter",
                                  side_effect=lambda fn, *a: orden.append("aviso")), \
                mock.patch.object(gui.credenciales, "cerrar_sesion",
                                  side_effect=lambda: orden.append("cierre")):
            frame._enviar_programado({"texto": "Hola"}, 1000.0)
        self.assertEqual(orden, ["cierre", "aviso"])

    def test_escritura_cierra_antes_de_agendar_el_error(self):
        panel = gui_comentarios.ComentariosPanel.__new__(
            gui_comentarios.ComentariosPanel)
        orden = []
        with mock.patch.object(gui_comentarios, "anunciar"), \
                mock.patch.object(gui_comentarios.diagnostico, "crear_hilo",
                                  side_effect=lambda ob, n: HiloDirecto(ob)), \
                mock.patch.object(gui_comentarios.wx, "CallAfter",
                                  side_effect=lambda fn, *a: orden.append("aviso")), \
                mock.patch.object(gui_comentarios.credenciales, "cerrar_sesion",
                                  side_effect=lambda: orden.append("cierre")), \
                mock.patch.object(panel, "_cliente",
                                  return_value=mock.Mock(
                                      token_actualizado=mock.Mock(return_value=None))):
            panel._enviar_escritura(
                mock.Mock(side_effect=RefreshError("invalid_grant")), "ok")
        self.assertEqual(orden, ["cierre", "aviso"])


class DialogoFalso:
    instancias = []

    def __init__(self, parent, config):
        self.nb = mock.Mock()
        self.nb.GetPageCount.return_value = 3
        self.nb.GetPageText.side_effect = ["Voz", "API y sesión", "Atajos"]
        self.__class__.instancias.append(self)

    def ShowModal(self):
        return wx.ID_OK

    def hubo_cambios(self):
        return True

    def Destroy(self):
        pass


class TestAbrirEnPagina(unittest.TestCase):

    def setUp(self):
        DialogoFalso.instancias = []

    def test_pagina_coincidente_queda_seleccionada(self):
        with mock.patch.object(gui_preferencias, "PreferenciasDialog",
                               DialogoFalso):
            self.assertTrue(gui_preferencias.abrir_preferencias(
                "padre", {}, pagina="API y sesión"))
        dialogo = DialogoFalso.instancias[0]
        dialogo.nb.SetSelection.assert_called_once_with(1)

    def test_sin_pagina_igual_que_hoy(self):
        with mock.patch.object(gui_preferencias, "PreferenciasDialog",
                               DialogoFalso):
            self.assertTrue(gui_preferencias.abrir_preferencias("padre", {}))
        dialogo = DialogoFalso.instancias[0]
        dialogo.nb.SetSelection.assert_not_called()

    def test_pagina_inexistente_no_rompe(self):
        with mock.patch.object(gui_preferencias, "PreferenciasDialog",
                               DialogoFalso):
            self.assertTrue(gui_preferencias.abrir_preferencias(
                "padre", {}, pagina="No existe"))
        dialogo = DialogoFalso.instancias[0]
        dialogo.nb.SetSelection.assert_not_called()


class TestOfrecerIniciarSesion(unittest.TestCase):

    def test_si_abre_preferencias_en_api_y_sesion(self):
        with mock.patch.object(gui_preferencias.wx, "MessageBox",
                               return_value=wx.YES) as caja, \
                mock.patch.object(gui_preferencias, "abrir_preferencias",
                                  return_value=True) as abrir:
            self.assertTrue(gui_preferencias.ofrecer_iniciar_sesion(
                "padre", {"clave": 1}))
        texto = caja.call_args.args[0]
        self.assertIn("¿Abrir Preferencias para volver a iniciar sesión?",
                      texto)
        self.assertEqual(caja.call_args.args[1], "Sesión caducada")
        self.assertTrue(caja.call_args.args[2] & wx.YES_NO)
        abrir.assert_called_once_with("padre", {"clave": 1},
                                      pagina="API y sesión")

    def test_no_no_abre_preferencias(self):
        with mock.patch.object(gui_preferencias.wx, "MessageBox",
                               return_value=wx.NO), \
                mock.patch.object(gui_preferencias, "abrir_preferencias") as abrir:
            self.assertFalse(gui_preferencias.ofrecer_iniciar_sesion(
                "padre", {}))
        abrir.assert_not_called()


class TestApiErr(unittest.TestCase):
    """gui._api_err con sesión caducada ofrece volver a entrar, sin MessageBox."""

    def _receptor(self):
        config = {}
        return types.SimpleNamespace(
            _config=config,
            _actualizar_estado_online=mock.Mock(),
            _aplicar_preferencias_en_caliente=mock.Mock()), config

    def test_sesion_llama_a_ofrecer_y_no_al_aviso_de_error(self):
        receptor, config = self._receptor()
        with mock.patch.object(gui._snd, "reproducir") as sonar, \
                mock.patch.object(gui, "anunciar") as anunciar, \
                mock.patch.object(gui.wx, "MessageBox") as caja, \
                mock.patch.object(gui_preferencias, "ofrecer_iniciar_sesion",
                                  return_value=True) as ofrecer:
            gui.YTChatFrame._api_err(receptor, RefreshError("invalid_grant"))
        ofrecer.assert_called_once_with(receptor, config)
        caja.assert_not_called()
        sonar.assert_called_once_with("error")
        anunciar.assert_called_once_with(FRASE_SESION)
        receptor._actualizar_estado_online.assert_called_once_with()
        receptor._aplicar_preferencias_en_caliente.assert_called_once_with()

    def test_si_no_quiere_entrar_no_aplica_preferencias(self):
        receptor, _ = self._receptor()
        with mock.patch.object(gui._snd, "reproducir"), \
                mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.wx, "MessageBox") as caja, \
                mock.patch.object(gui_preferencias, "ofrecer_iniciar_sesion",
                                  return_value=False):
            gui.YTChatFrame._api_err(receptor, RefreshError("invalid_grant"))
        caja.assert_not_called()
        receptor._aplicar_preferencias_en_caliente.assert_not_called()

    def test_error_comun_igual_que_hoy(self):
        receptor, _ = self._receptor()
        with mock.patch.object(gui._snd, "reproducir"), \
                mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.wx, "MessageBox") as caja, \
                mock.patch.object(gui_preferencias, "ofrecer_iniciar_sesion") as ofrecer:
            gui.YTChatFrame._api_err(receptor, RuntimeError("quotaExceeded"))
        ofrecer.assert_not_called()
        caja.assert_called_once()


class TestEscrituraErr(unittest.TestCase):

    def _panel(self):
        panel = gui_comentarios.ComentariosPanel.__new__(
            gui_comentarios.ComentariosPanel)
        panel._config = {}
        return panel

    def test_sesion_ofrece_sin_aviso_de_error(self):
        panel = self._panel()
        with mock.patch.object(gui_comentarios._snd, "reproducir") as sonar, \
                mock.patch.object(gui_comentarios, "anunciar") as anunciar, \
                mock.patch.object(gui_comentarios.wx, "MessageBox") as caja, \
                mock.patch.object(gui_preferencias, "ofrecer_iniciar_sesion",
                                  return_value=False) as ofrecer:
            panel._escritura_err(RefreshError("invalid_grant"))
        ofrecer.assert_called_once_with(panel, panel._config)
        caja.assert_not_called()
        sonar.assert_called_once_with("error")
        anunciar.assert_called_once_with(FRASE_SESION)

    def test_error_comun_igual_que_hoy(self):
        panel = self._panel()
        with mock.patch.object(gui_comentarios._snd, "reproducir"), \
                mock.patch.object(gui_comentarios, "anunciar"), \
                mock.patch.object(gui_comentarios.wx, "MessageBox") as caja, \
                mock.patch.object(gui_preferencias, "ofrecer_iniciar_sesion") as ofrecer:
            panel._escritura_err(RuntimeError("quotaExceeded"))
        ofrecer.assert_not_called()
        caja.assert_called_once()


class TestProgramadoFallo(unittest.TestCase):

    def _frame(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._config = {"programados_activo": True}
        frame._programado_en_curso = True
        return frame

    def test_frase_exacta_sin_dialogo(self):
        frame = self._frame()
        with mock.patch.object(gui, "anunciar") as anunciar, \
                mock.patch.object(gui.wx, "MessageBox") as caja:
            frame._programado_fallo(RefreshError("invalid_grant"))
        anunciar.assert_called_once_with(FRASE_PROGRAMADO)
        caja.assert_not_called()
        self.assertFalse(frame._config["programados_activo"])
        self.assertFalse(frame._programado_en_curso)

    def test_error_comun_conserva_la_frase_generica(self):
        frame = self._frame()
        with mock.patch.object(gui, "anunciar") as anunciar:
            frame._programado_fallo(RuntimeError("rateLimitExceeded"))
        anunciar.assert_called_once_with(
            "Los mensajes automáticos se detuvieron por un error del servicio.")


if __name__ == "__main__":
    unittest.main()
