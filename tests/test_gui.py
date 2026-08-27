"""Pruebas de la salida accesible de los registros."""

import logging
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gui
import gui_comentarios
import gui_preferencias
import apagado
import alias
import programados
import ytdlp_bin


class EventoTecladoFalso:
    def __init__(self, codigo):
        self.codigo = codigo
        self.omitido = False

    def GetKeyCode(self):
        return self.codigo

    def Skip(self):
        self.omitido = True


class TestEnterEnListas(unittest.TestCase):

    def test_chat_enlaza_el_gancho_de_caracteres(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame.lb_chat = mock.Mock()
        frame._enlazar_eventos_chat()
        enlaces = [llamada.args[0] for llamada in frame.lb_chat.Bind.call_args_list]
        self.assertIn(gui.wx.EVT_CHAR_HOOK, enlaces)

    def test_chat_enter_copia_sin_omitirlo(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._copiar_mensaje = mock.Mock()
        evento = EventoTecladoFalso(gui.wx.WXK_RETURN)
        frame._on_chat_char_hook(evento)
        frame._copiar_mensaje.assert_called_once_with()
        self.assertFalse(evento.omitido)

    def test_chat_otra_tecla_se_deja_pasar(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._copiar_mensaje = mock.Mock()
        evento = EventoTecladoFalso(ord("a"))
        frame._on_chat_char_hook(evento)
        frame._copiar_mensaje.assert_not_called()
        self.assertTrue(evento.omitido)

    def test_comentarios_enlaza_el_gancho_de_caracteres(self):
        panel = gui_comentarios.ComentariosPanel.__new__(
            gui_comentarios.ComentariosPanel)
        panel.lb = mock.Mock()
        panel._enlazar_eventos_lista()
        enlaces = [llamada.args[0] for llamada in panel.lb.Bind.call_args_list]
        self.assertIn(gui_comentarios.wx.EVT_CHAR_HOOK, enlaces)

    def test_comentarios_enter_lee_sin_omitirlo(self):
        panel = gui_comentarios.ComentariosPanel.__new__(
            gui_comentarios.ComentariosPanel)
        panel._leer = mock.Mock()
        evento = EventoTecladoFalso(gui_comentarios.wx.WXK_RETURN)
        panel._on_char_hook(evento)
        panel._leer.assert_called_once_with()
        self.assertFalse(evento.omitido)

    def test_comentarios_otra_tecla_se_deja_pasar(self):
        panel = gui_comentarios.ComentariosPanel.__new__(
            gui_comentarios.ComentariosPanel)
        panel._leer = mock.Mock()
        evento = EventoTecladoFalso(ord("a"))
        panel._on_char_hook(evento)
        panel._leer.assert_not_called()
        self.assertTrue(evento.omitido)


class GrabadorDeVoz:
    """Ocupa el lugar del lector de pantalla y anota lo que se le diría."""

    def __init__(self):
        self.hablado = []
        self.brailleado = []

    def speak(self, texto, interrupt=None):
        self.hablado.append(texto)

    def braille(self, texto):
        self.brailleado.append(texto)


class TestRegistroEsAnunciable(unittest.TestCase):

    def test_descarta_diagnostico_y_sus_hijos(self):
        self.assertFalse(gui.registro_es_anunciable("diagnostico"))
        self.assertFalse(gui.registro_es_anunciable("diagnostico.hilos"))

    def test_no_descarta_nombres_parecidos(self):
        self.assertTrue(gui.registro_es_anunciable("diagnosticador"))

    def test_anuncia_el_resto_y_nombres_vacios(self):
        self.assertTrue(gui.registro_es_anunciable("aplicacion"))
        self.assertTrue(gui.registro_es_anunciable(""))
        self.assertTrue(gui.registro_es_anunciable(None))

    def test_manejador_consulta_el_nombre_del_registro(self):
        manejador = gui.WxAnnouncingHandler()
        registro = logging.LogRecord(
            "diagnostico.hilos", logging.INFO, __file__, 1, "oculto", (), None)
        with mock.patch.object(gui, "registro_es_anunciable", return_value=False) as decidir:
            with mock.patch.object(gui, "anunciar") as anunciar:
                manejador.emit(registro)
        decidir.assert_called_once_with("diagnostico.hilos")
        anunciar.assert_not_called()

    def test_anunciar_envia_el_texto_completo(self):
        grabador = GrabadorDeVoz()
        with mock.patch.object(gui, "_ao2", grabador):
            gui.anunciar("hola")

        self.assertEqual(grabador.hablado, ["hola"])
        self.assertEqual(grabador.brailleado, ["hola"])

    def test_manejador_omite_diagnostico_sin_parchear_anunciar(self):
        grabador = GrabadorDeVoz()
        registro = logging.LogRecord(
            "diagnostico.hilos", logging.INFO, __file__, 1, "oculto", (), None)
        with mock.patch.object(gui, "_ao2", grabador):
            gui.WxAnnouncingHandler().emit(registro)

        self.assertEqual(grabador.hablado, [])
        self.assertEqual(grabador.brailleado, [])

    def test_manejador_anuncia_mensaje_de_aplicacion(self):
        grabador = GrabadorDeVoz()
        registro = logging.LogRecord(
            "aplicacion", logging.INFO, __file__, 1, "conectado", (), None)
        with mock.patch.object(gui, "_ao2", grabador):
            gui.WxAnnouncingHandler().emit(registro)

        self.assertEqual(grabador.hablado, ["conectado"])


class _BarraDeMenu:

    def __init__(self):
        self.llamadas = []

    def EnableTop(self, *args):
        self.llamadas.append(args)


class _ControlMenu:

    def Enable(self, habilitado):
        pass


class TestMenusPorConexion(unittest.TestCase):

    def test_no_apaga_menu_reproductor_sin_conexion(self):
        frame = mock.Mock()
        frame._conectado = False
        frame._mi_ver_conexion = []
        frame._mi_voz_conexion = []
        frame._mi_filtro_sub = _ControlMenu()
        frame._es_tiktok = False
        frame._rep_panel = None
        frame.mi_descargar_este = _ControlMenu()
        barra = _BarraDeMenu()
        frame.GetMenuBar.return_value = barra

        gui.YTChatFrame._actualizar_menus_por_conexion(frame)

        self.assertEqual(barra.llamadas, [])


class TestAliasEnLaLista(unittest.TestCase):

    def test_lista_muestra_el_alias_del_autor(self):
        autor = "xX_gamer_29384756_Xx"
        alias.usar({autor.lower(): "Carlos"})
        self.addCleanup(alias.usar, {})
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._config = {"limpiar_emojis": True}

        texto = frame._format_display(autor, "hola", "12:00", 0, "")

        self.assertEqual(texto, "Carlos: hola, 12:00")


class DialogoAliasFalso:

    def __init__(self, aceptar, valor):
        self.aceptar = aceptar
        self.valor = valor
        self.destruido = False

    def ShowModal(self):
        return gui.wx.ID_OK if self.aceptar else gui.wx.ID_CANCEL

    def GetValue(self):
        return self.valor

    def Destroy(self):
        self.destruido = True


class MenuChatFalso:

    def __init__(self):
        self.etiquetas = {}
        self.handlers = {}

    def Append(self, identificador, etiqueta):
        self.etiquetas[identificador] = etiqueta

    def AppendSeparator(self):
        pass

    def Bind(self, _evento, handler, id):
        self.handlers[id] = handler

    def Destroy(self):
        pass


class TestAliasDesdeElChat(unittest.TestCase):

    autor = "xX_gamer_29384756_Xx"

    def _frame(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame.lb_chat = mock.Mock()
        frame._rebuild_listbox = mock.Mock()
        return frame

    def test_aceptar_guarda_persiste_y_redibuja(self):
        frame = self._frame()
        dialogo = DialogoAliasFalso(True, "Carlos")
        alias.usar({})
        with mock.patch.object(gui.wx, "TextEntryDialog", return_value=dialogo), \
                mock.patch.object(gui.alias, "guardar") as guardar, \
                mock.patch.object(gui, "anunciar") as anunciar:
            frame._editar_alias_autor(self.autor)

        self.assertEqual(alias.visible(self.autor), "Carlos")
        guardar.assert_called_once_with(
            gui.app_dir() / "alias.json", {self.autor.lower(): "Carlos"})
        frame._rebuild_listbox.assert_called_once_with()
        frame.lb_chat.SetFocus.assert_called_once_with()
        self.assertTrue(dialogo.destruido)
        anunciar.assert_called_once_with("Alias guardado, Carlos")
        alias.usar({})

    def test_aceptar_vacio_quita_el_alias(self):
        frame = self._frame()
        dialogo = DialogoAliasFalso(True, "")
        alias.usar({self.autor.lower(): "Carlos"})
        with mock.patch.object(gui.wx, "TextEntryDialog", return_value=dialogo), \
                mock.patch.object(gui.alias, "guardar") as guardar, \
                mock.patch.object(gui, "anunciar") as anunciar:
            frame._editar_alias_autor(self.autor)

        self.assertEqual(alias.visible(self.autor), self.autor)
        guardar.assert_called_once_with(gui.app_dir() / "alias.json", {})
        frame._rebuild_listbox.assert_called_once_with()
        anunciar.assert_called_once_with("Alias quitado")
        alias.usar({})

    def test_cancelar_no_guarda_ni_redibuja(self):
        frame = self._frame()
        dialogo = DialogoAliasFalso(False, "Carlos")
        alias.usar({})
        with mock.patch.object(gui.wx, "TextEntryDialog", return_value=dialogo), \
                mock.patch.object(gui.alias, "guardar") as guardar, \
                mock.patch.object(gui, "anunciar") as anunciar:
            frame._editar_alias_autor(self.autor)

        guardar.assert_not_called()
        frame._rebuild_listbox.assert_not_called()
        anunciar.assert_not_called()
        frame.lb_chat.SetFocus.assert_called_once_with()

    def test_menu_muestra_alias_y_moderacion_recibe_autor_real(self):
        frame = self._frame()
        frame.lb_chat.GetSelection.return_value = 0
        frame._autor_seleccionado = mock.Mock(return_value=self.autor)
        frame._autor_esta_silenciado = mock.Mock(return_value=False)
        frame._canal_por_autor = {self.autor.lower(): "canal-real"}
        frame._live_chat_id = "chat"
        frame._moderar = mock.Mock()
        frame._silenciar_autor = mock.Mock()
        menu = MenuChatFalso()
        alias.usar({self.autor.lower(): "Carlos"})
        with mock.patch.object(gui.wx, "Menu", return_value=menu), \
                mock.patch.object(gui.wx, "NewIdRef", side_effect=range(1, 11)), \
                mock.patch.object(gui.youtube_api, "google_disponible", return_value=True), \
                mock.patch.object(gui.credenciales, "hay_sesion", return_value=True):
            frame._mostrar_menu_chat()

        self.assertIn("Silenciar a Carlos (solo TTS)", menu.etiquetas.values())
        self.assertIn("Expulsar 5 min a Carlos (timeout)", menu.etiquetas.values())
        self.assertIn("Banear a Carlos del directo (permanente)", menu.etiquetas.values())
        self.assertIn("Cambiar el &alias de Carlos…", menu.etiquetas.values())
        identificador_ban = next(i for i, texto in menu.etiquetas.items()
                                 if texto.startswith("Banear"))
        identificador_silenciar = next(i for i, texto in menu.etiquetas.items()
                                       if texto.startswith("Silenciar"))
        menu.handlers[identificador_ban](None)
        menu.handlers[identificador_silenciar](None)
        frame._moderar.assert_called_once_with(self.autor, "canal-real", None)
        frame._silenciar_autor.assert_called_once_with(self.autor, ocultar=False)
        alias.usar({})


class TestProgramadosEnPreferencias(unittest.TestCase):

    def _dialogo(self, mensajes, seleccion):
        dialogo = gui_preferencias.PreferenciasDialog.__new__(
            gui_preferencias.PreferenciasDialog)
        dialogo._mensajes_programados = mensajes
        dialogo._ruta_programados = Path(tempfile.mktemp(suffix=".json"))
        dialogo.lista_programados = mock.Mock()
        dialogo.lista_programados.GetSelection.return_value = seleccion
        dialogo._refrescar_programados = mock.Mock()
        self.addCleanup(lambda: dialogo._ruta_programados.unlink(missing_ok=True))
        return dialogo

    def test_quitar_persiste_que_el_mensaje_desaparecio(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "mensajes_programados.json"
            mensajes = [
                {"texto": "Quitar", "minutos_min": 10, "minutos_max": 10,
                 "activo": True, "proximo": 100.0},
                {"texto": "Conservar", "minutos_min": 10, "minutos_max": 10,
                 "activo": True, "proximo": 200.0},
            ]
            dialogo = self._dialogo(mensajes, 0)
            dialogo._ruta_programados = ruta
            def guardar_doble(ruta_a_guardar, mensajes_a_guardar):
                Path(ruta_a_guardar).write_text(
                    json.dumps(mensajes_a_guardar, ensure_ascii=False), encoding="utf-8")

            with mock.patch.object(
                    gui_preferencias.programados, "guardar",
                    side_effect=guardar_doble), \
                    mock.patch.object(gui_preferencias, "anunciar"):
                dialogo._quitar_programado(None)

            guardados = json.loads(ruta.read_text(encoding="utf-8"))
            self.assertEqual(guardados, [mensajes[0]])
            self.assertNotIn("Quitar", ruta.read_text(encoding="utf-8"))


    def test_guardar_edita_la_fila_elegida(self):
        mensajes = [
            {"texto": "Primero", "proximo": 100.0},
            {"texto": "Segundo", "proximo": 200.0},
            {"texto": "Tercero", "proximo": 300.0},
        ]
        dialogo = self._dialogo(mensajes, 2)
        dialogo._datos_programado = mock.Mock(return_value={"texto": "Editado"})
        dialogo._validar_programado = mock.Mock(return_value=True)
        with mock.patch.object(gui_preferencias.programados, "guardar"), \
                mock.patch.object(gui_preferencias, "anunciar"):
            dialogo._guardar_programado(None)

        self.assertEqual(mensajes[0]["texto"], "Primero")
        self.assertEqual(mensajes[2]["texto"], "Editado")

    def test_guardar_conserva_el_proximo_envio(self):
        mensajes = [
            {"texto": "Primero", "proximo": 100.0},
            {"texto": "Segundo", "proximo": 200.0},
        ]
        dialogo = self._dialogo(mensajes, 1)
        dialogo._datos_programado = mock.Mock(return_value={"texto": "Corregido"})
        dialogo._validar_programado = mock.Mock(return_value=True)
        with mock.patch.object(gui_preferencias.programados, "guardar"), \
                mock.patch.object(gui_preferencias, "anunciar"):
            dialogo._guardar_programado(None)

        self.assertEqual(mensajes[1]["proximo"], 200.0)

    def test_quitar_sin_seleccion_anuncia_y_no_revienta(self):
        dialogo = self._dialogo([], -1)
        with mock.patch.object(gui_preferencias, "anunciar") as anunciar:
            dialogo._quitar_programado(None)

        anunciar.assert_called_once_with("Elige primero un mensaje de la lista")


class TestProgramadorGui(unittest.TestCase):
    def _frame(self, **config):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._config = {"programados_activo": True, **config}
        frame._mensajes_programados = [{"texto": "Hola", "activo": True,
                                        "minutos_min": 5, "minutos_max": 5,
                                        "proximo": 0.0}]
        frame._programados_reloj_iniciado = True
        frame._programados_ultimo_envio = None
        frame._programado_en_curso = False
        frame._conectado = True
        frame._es_tiktok = False
        frame._live_chat_id = "chat"
        return frame

    def test_envio_exitoso_avanza_el_reloj(self):
        frame = self._frame()
        with mock.patch.object(gui.programados, "calcular_proximo",
                               return_value=900.0) as calcular:
            frame._programado_enviado(frame._mensajes_programados[0])
        self.assertEqual(frame._mensajes_programados[0]["proximo"], 900.0)
        self.assertIsNotNone(frame._programados_ultimo_envio)
        calcular.assert_called_once()

    def test_envia_con_el_doble_de_la_api_sin_anunciar_exito(self):
        frame = self._frame()
        cliente = mock.Mock()
        cliente.token_actualizado.return_value = None

        class Hilo:
            def __init__(self, objetivo):
                self.objetivo = objetivo

            def start(self):
                self.objetivo()

        with mock.patch.object(gui.youtube_api, "ClienteYouTube",
                               return_value=cliente), \
                mock.patch.object(gui.credenciales, "cargar", return_value={}), \
                mock.patch.object(gui.diagnostico, "crear_hilo",
                                  side_effect=lambda objetivo, nombre: Hilo(objetivo)), \
                mock.patch.object(gui.wx, "CallAfter",
                                  side_effect=lambda fn, *args: fn(*args)), \
                mock.patch.object(gui, "anunciar") as anunciar:
            frame._enviar_programado(frame._mensajes_programados[0], 1000.0)
        cliente.enviar_mensaje_live.assert_called_once_with("chat", "Hola")
        anunciar.assert_not_called()

    def test_no_duplica_un_envio_en_curso(self):
        frame = self._frame()
        frame._programado_en_curso = True
        with mock.patch.object(frame, "_sesion_api_disponible", return_value=True), \
                mock.patch.object(frame, "_enviar_programado") as enviar:
            frame._procesar_programado()
        enviar.assert_not_called()

    def test_procesar_arma_la_bandera_antes_de_enviar(self):
        frame = self._frame()
        frame._mensajes_programados[0]["proximo"] = 0.0

        class Hilo:
            def start(self):
                pass

        with mock.patch.object(gui.time, "time", return_value=1000.0), \
                mock.patch.object(frame, "_sesion_api_disponible", return_value=True), \
                mock.patch.object(gui.diagnostico, "crear_hilo",
                                  return_value=Hilo()):
            frame._procesar_programado()
        self.assertTrue(frame._programado_en_curso)

    def test_al_encender_da_cuerda_al_reloj(self):
        frame = self._frame()
        frame._programados_reloj_iniciado = False
        with mock.patch.object(gui.programados, "iniciar_reloj") as iniciar:
            frame._iniciar_programados_si_corresponde(1000.0)
        iniciar.assert_called_once()
        self.assertTrue(frame._programados_reloj_iniciado)

    def test_procesar_no_vuelve_a_dar_cuerda_al_reloj(self):
        frame = self._frame()
        frame._programados_reloj_iniciado = False
        frame._conectado = False
        mensaje = frame._mensajes_programados[0]
        with mock.patch.object(gui.time, "time", side_effect=(1000.0, 2000.0)):
            frame._procesar_programado()
            proximo = mensaje["proximo"]
            frame._procesar_programado()
        self.assertEqual(mensaje["proximo"], proximo)

    def test_no_envia_si_no_hay_conexion(self):
        frame = self._frame()
        frame._conectado = False
        with mock.patch.object(frame, "_sesion_api_disponible", return_value=True), \
                mock.patch.object(frame, "_enviar_programado") as enviar:
            frame._procesar_programado()
        enviar.assert_not_called()

    def test_no_envia_sin_sesion_api(self):
        frame = self._frame()
        with mock.patch.object(frame, "_sesion_api_disponible", return_value=False), \
                mock.patch.object(frame, "_enviar_programado") as enviar:
            frame._procesar_programado()
        enviar.assert_not_called()

    def test_no_envia_si_falta_live_chat_id(self):
        frame = self._frame()
        frame._live_chat_id = ""
        with mock.patch.object(frame, "_sesion_api_disponible", return_value=True), \
                mock.patch.object(frame, "_enviar_programado") as enviar:
            frame._procesar_programado()
        enviar.assert_not_called()

    def test_no_envia_si_interruptor_apagado(self):
        frame = self._frame(programados_activo=False)
        with mock.patch.object(frame, "_sesion_api_disponible", return_value=True), \
                mock.patch.object(frame, "_enviar_programado") as enviar:
            frame._procesar_programado()
        enviar.assert_not_called()

    def test_no_envia_en_tiktok(self):
        frame = self._frame()
        frame._es_tiktok = True
        with mock.patch.object(frame, "_sesion_api_disponible", return_value=True), \
                mock.patch.object(frame, "_enviar_programado") as enviar:
            frame._procesar_programado()
        enviar.assert_not_called()

    def test_no_envia_si_elegir_devuelve_none(self):
        frame = self._frame()
        with mock.patch.object(frame, "_sesion_api_disponible", return_value=True), \
                mock.patch.object(gui.programados, "elegir_envio", return_value=None), \
                mock.patch.object(frame, "_enviar_programado") as enviar:
            frame._procesar_programado()
        enviar.assert_not_called()

    def test_error_apaga_programador_y_anuncia_una_vez(self):
        frame = self._frame()
        with mock.patch.object(gui, "anunciar") as anunciar:
            frame._programado_fallo(RuntimeError("rateLimitExceeded"))
        self.assertFalse(frame._config["programados_activo"])
        anunciar.assert_called_once_with(
            "Los mensajes automáticos se detuvieron por un error del servicio.")

    def test_error_baja_la_bandera_de_envio(self):
        frame = self._frame()
        frame._programado_en_curso = True
        with mock.patch.object(gui, "anunciar"):
            frame._programado_fallo(RuntimeError("rateLimitExceeded"))
        self.assertFalse(frame._programado_en_curso)

    def test_snapshot_omite_proximo_si_el_interruptor_esta_apagado(self):
        frame = self._frame(programados_activo=False)
        frame._tipo_video = "live_youtube"
        frame._titulo_stream = "Directo"
        frame._metadatos = {}
        frame._sc_totales = {}
        snapshot = frame._snapshot_sesion()
        self.assertEqual(snapshot.programados_proximo, "")


class TestActualizarYtdlp(unittest.TestCase):

    class Dialogo:
        def __init__(self, cancelado=False):
            self.cancelado = cancelado
            self.actualizaciones = []
            self.destruido = False

        def WasCancelled(self):
            return self.cancelado

        def Update(self, *argumentos):
            self.actualizaciones.append(argumentos)

        def Destroy(self):
            self.destruido = True

    def _ejecutar(self, resultado):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        anuncios = []
        dialogos = []
        hilo = mock.Mock()
        hilo.start.side_effect = lambda: hilo.target()

        def crear(target, nombre):
            hilo.target = target
            return hilo

        with mock.patch.object(gui, "anunciar", side_effect=anuncios.append), \
                mock.patch.object(gui.diagnostico, "crear_hilo", side_effect=crear), \
                mock.patch.object(gui.wx, "CallAfter", side_effect=lambda fn, *args: fn(*args)), \
                mock.patch.object(gui.wx, "MessageBox", side_effect=lambda *args: dialogos.append(args)), \
                mock.patch.object(ytdlp_bin, "actualizar_ytdlp", return_value=resultado):
            gui.YTChatFrame._on_actualizar_ytdlp(frame, None)
        return anuncios, dialogos, hilo

    def test_activar_anuncia_antes_de_empezar(self):
        anuncios, dialogos, hilo = self._ejecutar(("ya_al_dia", "2026.08.20", "2026.08.20"))
        self.assertIn("Buscando", anuncios[0])
        hilo.start.assert_called_once()

    def test_cada_desenlace_anuncia_su_texto(self):
        casos = (
            (("actualizado", "2026.08.20", "2026.08.21"), "actualizó"),
            (("ya_al_dia", "2026.08.20", "2026.08.20"), "al día"),
            (("sin_conexion", "2026.08.20", ""), "conexión"),
            (("firma_incorrecta", "2026.08.20", "2026.08.21"), "No se instaló nada"),
            (("otro_fallo", "2026.08.20", "2026.08.21"), "No se pudo actualizar"),
        )
        for resultado, esperado in casos:
            with self.subTest(esperado=esperado):
                anuncios, dialogos, _ = self._ejecutar(resultado)
                self.assertIn("Buscando", anuncios[0])
                self.assertTrue(any(esperado in texto[0] for texto in dialogos))

    def test_fallo_de_red_no_propaga_excepcion_y_anuncia(self):
        anuncios, dialogos, hilo = self._ejecutar(("sin_conexion", "", ""))
        self.assertIn("conexión", dialogos[-1][0])
        hilo.start.assert_called_once()

    def test_pasa_el_estado_sin_mirar_el_motivo(self):
        with mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.diagnostico, "crear_hilo") as crear, \
                mock.patch.object(gui.wx, "CallAfter", side_effect=lambda fn, *args: fn(*args)), \
                mock.patch.object(gui.wx, "MessageBox"), \
                mock.patch.object(ytdlp_bin, "mensaje_de_actualizacion") as mensaje, \
                mock.patch.object(ytdlp_bin, "actualizar_ytdlp", return_value=("firma_incorrecta", "", "2026.08.21")):
            hilo = mock.Mock()
            hilo.start.side_effect = lambda: hilo.target()
            crear.side_effect = lambda target, nombre: setattr(hilo, "target", target) or hilo
            gui.YTChatFrame._on_actualizar_ytdlp(gui.YTChatFrame.__new__(gui.YTChatFrame), None)
        mensaje.assert_called_once_with("firma_incorrecta", "", "2026.08.21")

    def test_cancelar_usa_was_cancelled_y_muestra_mensaje_propio(self):
        dialogo = self.Dialogo(cancelado=True)
        hilo = mock.Mock()
        hilo.start.side_effect = lambda: hilo.target()

        def crear(target, nombre):
            hilo.target = target
            return hilo

        def actualizar(antes, progreso, cancelar):
            antes()
            self.assertTrue(cancelar())
            return "cancelado", "2026.08.20", "2026.08.21"

        with mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.diagnostico, "crear_hilo", side_effect=crear), \
                mock.patch.object(gui.wx, "CallAfter", side_effect=lambda fn, *args: fn(*args)), \
                mock.patch.object(gui.wx, "CallLater"), \
                mock.patch.object(gui.wx, "ProgressDialog", return_value=dialogo), \
                mock.patch.object(gui.wx, "MessageBox") as mensaje, \
                mock.patch.object(ytdlp_bin, "actualizar_ytdlp", side_effect=actualizar):
            gui.YTChatFrame._on_actualizar_ytdlp(gui.YTChatFrame.__new__(gui.YTChatFrame), None)
        self.assertIn("Se canceló la descarga de yt-dlp.", mensaje.call_args.args[0])
        self.assertTrue(dialogo.destruido)

    def test_icono_de_resultado_distingue_fallo_y_acierto(self):
        for estado, icono in (
                ("actualizado", gui.wx.ICON_INFORMATION),
                ("otro_fallo", gui.wx.ICON_ERROR)):
            with self.subTest(estado=estado):
                _, dialogos, _ = self._ejecutar((estado, "", "2026.08.21"))
                self.assertEqual(icono, dialogos[-1][2] & (gui.wx.ICON_ERROR | gui.wx.ICON_INFORMATION))

    def test_anuncia_antes_de_descargar_y_al_terminar(self):
        anuncios = []
        hilo = mock.Mock()
        hilo.start.side_effect = lambda: hilo.target()

        def crear(target, nombre):
            hilo.target = target
            return hilo

        def actualizar(aviso, _progreso, _cancelar):
            aviso()
            return "actualizado", "2026.08.20", "2026.08.21"

        with mock.patch.object(gui, "anunciar", side_effect=anuncios.append), \
                mock.patch.object(gui.diagnostico, "crear_hilo", side_effect=crear), \
                mock.patch.object(gui.wx, "CallAfter", side_effect=lambda fn, *args: fn(*args)), \
                mock.patch.object(gui.wx, "MessageBox") as mensaje, \
                mock.patch.object(gui.wx, "ProgressDialog") as progreso, \
                mock.patch.object(gui.wx, "CallLater"), \
                mock.patch.object(ytdlp_bin, "actualizar_ytdlp", side_effect=actualizar):
            progreso.return_value.IsCancelled.return_value = False
            gui.YTChatFrame._on_actualizar_ytdlp(gui.YTChatFrame.__new__(gui.YTChatFrame), None)
        self.assertIn("Buscando", anuncios[0])
        progreso.assert_called_once()
        self.assertEqual(1, mensaje.call_count)
        self.assertIn("actualizó", mensaje.call_args.args[0])


    def test_sondeo_de_cancelacion_se_reprograma(self):
        dialogo = self.Dialogo()
        hilo = mock.Mock()
        hilo.start.side_effect = lambda: hilo.target()

        def crear(target, nombre):
            hilo.target = target
            return hilo

        def actualizar(antes, _progreso, _cancelar):
            antes()
            return "cancelado", "2026.08.20", "2026.08.21"

        with mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.diagnostico, "crear_hilo", side_effect=crear), \
                mock.patch.object(gui.wx, "CallAfter", side_effect=lambda fn, *args: fn(*args)), \
                mock.patch.object(gui.wx, "CallLater") as call_later, \
                mock.patch.object(gui.wx, "ProgressDialog", return_value=dialogo), \
                mock.patch.object(gui.wx, "MessageBox"), \
                mock.patch.object(ytdlp_bin, "actualizar_ytdlp", side_effect=actualizar):
            gui.YTChatFrame._on_actualizar_ytdlp(
                gui.YTChatFrame.__new__(gui.YTChatFrame), None)

        call_later.assert_called_once()
        self.assertEqual(call_later.call_args.args[0], 100)
        self.assertTrue(callable(call_later.call_args.args[1]))


class TestCierreVentana(unittest.TestCase):

    def test_el_overlay_activo_se_enciende_al_construir_la_ventana(self):
        configuracion = {"overlay_activo": True, "overlay_puerto": 8730}

        def construir_menu(frame):
            frame.mi_overlay = mock.Mock()

        with mock.patch.object(gui.wx.Frame, "__init__", return_value=None), \
                mock.patch.object(gui.YTChatFrame, "_build_menubar", construir_menu), \
                mock.patch.object(gui.YTChatFrame, "_build_ui"), \
                mock.patch.object(gui.YTChatFrame, "_bind_events"), \
                mock.patch.object(gui.YTChatFrame, "_init_timer"), \
                mock.patch.object(gui.YTChatFrame, "SetBackgroundColour"), \
                mock.patch.object(gui.YTChatFrame, "Centre"), \
                mock.patch.object(gui, "anunciar_conflictos_atajos"), \
                mock.patch.object(gui.diagnostico, "crear_hilo") as crear, \
                mock.patch.object(gui.overlay_servidor, "encender") as encender, \
                mock.patch.object(gui, "guardar_opcion"), \
                mock.patch.object(gui, "anunciar"):
            gui.YTChatFrame(None, configuracion, None, None, None, None)

        encender.assert_called_once_with(8730)

    def test_el_overlay_no_miente_si_el_puerto_esta_ocupado_al_arrancar(self):
        configuracion = {"overlay_activo": True, "overlay_puerto": 8730}

        def construir_menu(frame):
            frame.mi_overlay = mock.Mock()

        with mock.patch.object(gui.wx.Frame, "__init__", return_value=None), \
                mock.patch.object(gui.YTChatFrame, "_build_menubar", construir_menu), \
                mock.patch.object(gui.YTChatFrame, "_build_ui"), \
                mock.patch.object(gui.YTChatFrame, "_bind_events"), \
                mock.patch.object(gui.YTChatFrame, "_init_timer"), \
                mock.patch.object(gui.YTChatFrame, "SetBackgroundColour"), \
                mock.patch.object(gui.YTChatFrame, "Centre"), \
                mock.patch.object(gui, "anunciar_conflictos_atajos"), \
                mock.patch.object(gui.diagnostico, "crear_hilo"), \
                mock.patch.object(gui.overlay_servidor, "encender", side_effect=gui.overlay_servidor.OverlayPuertoOcupadoError), \
                mock.patch.object(gui, "guardar_opcion"), \
                mock.patch.object(gui, "anunciar") as anunciar:
            frame = gui.YTChatFrame(None, configuracion, None, None, None, None)

        frame.mi_overlay.Check.assert_called_once_with(False)
        anunciar.assert_called_once_with(
            "No se pudo activar el panel, el puerto 8730 está ocupado")

    def test_el_precalentamiento_se_arranca_solo_con_la_ventana_viva(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._alive = True
        frame._rep_panel = mock.Mock()
        frame._arrancar_precalentamiento()
        frame._rep_panel._precalentar.assert_called_once_with()

        frame._alive = False
        frame._rep_panel._precalentar.reset_mock()
        frame._arrancar_precalentamiento()
        frame._rep_panel._precalentar.assert_not_called()

    def _frame(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._apagando = False
        frame._alive = True
        frame._timer = mock.Mock()
        frame._pendientes_timer = None
        frame.on_desconectar_cb = None
        frame._parada = mock.Mock()
        frame._rep_panel = mock.Mock()
        frame._worker = mock.Mock()
        frame._diagnostico_parada = mock.Mock()
        frame.Hide = mock.Mock()
        frame.Destroy = mock.Mock()
        return frame

    def test_con_captura_viva_programa_espera_y_anuncia_cerrando(self):
        frame = self._frame()
        hilo = mock.Mock()
        hilo.name = "Chat"
        hilo.is_alive.return_value = True
        with mock.patch.object(gui.threading, "enumerate", return_value=[hilo]), \
                mock.patch.object(gui, "anunciar") as anunciar, \
                mock.patch.object(gui.wx, "CallLater") as call_later:
            frame._on_close(None)

        anunciar.assert_called_once_with("Cerrando")
        call_later.assert_called_once_with(200, frame._comprobar_cierre)
        frame.Destroy.assert_not_called()

    def test_sin_captura_no_anuncia_y_destruye(self):
        frame = self._frame()
        with mock.patch.object(gui.threading, "enumerate", return_value=[]), \
                mock.patch.object(gui, "anunciar") as anunciar, \
                mock.patch.object(gui.wx, "CallLater") as call_later:
            frame._on_close(None)

        anunciar.assert_not_called()
        call_later.assert_not_called()
        frame.Destroy.assert_called_once_with()

    def test_al_cerrar_detiene_el_vigilante_de_interfaz(self):
        frame = self._frame()
        with mock.patch.object(gui.threading, "enumerate", return_value=[]), \
                mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.diagnostico.logger, "info"):
            frame._on_close(None)

        frame._diagnostico_parada.set.assert_called_once_with()

    def test_menu_overlay_falla_y_queda_desmarcado(self):
        frame = self._frame()
        frame._config = {"overlay_puerto": 8730, "overlay_activo": False}
        frame.mi_overlay = mock.Mock()
        evento = mock.Mock()
        evento.IsChecked.return_value = True
        with mock.patch.object(gui.overlay_servidor, "encender",
                               side_effect=gui.overlay_servidor.OverlayPuertoOcupadoError()), \
                mock.patch.object(gui, "anunciar") as anunciar, \
                mock.patch.object(gui, "RUTA_CONFIG", None):
            frame._on_overlay(evento)
        frame.mi_overlay.Check.assert_called_once_with(False)
        self.assertFalse(frame._config["overlay_activo"])
        anunciar.assert_called_once_with(
            "No se pudo activar el panel, el puerto 8730 está ocupado")

    def test_cerrar_apaga_el_overlay(self):
        frame = self._frame()
        with mock.patch.object(gui.threading, "enumerate", return_value=[]), \
                mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.overlay_servidor, "apagar") as apagar:
            frame._on_close(None)
        apagar.assert_called_once_with()

    def test_el_timer_actualiza_la_marca_del_vigilante(self):
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._alive = True
        frame._diagnostico_marca = 10.0
        frame._diagnostico_censo = 10.0
        with mock.patch.object(gui.time, "monotonic", return_value=12.5), \
                mock.patch.object(gui.diagnostico, "debe_censar_hilos", return_value=None):
            frame._on_diagnostico_timer(None)

        self.assertEqual(frame._diagnostico_marca, 12.5)

    def test_el_vigilante_se_arranca_con_nombre_propio(self):
        hilos = []
        hilo = mock.Mock()

        def crear(target, nombre):
            hilos.append((target, nombre))
            return hilo

        configuracion = mock.Mock()
        configuracion.get.return_value = {}
        with mock.patch.object(gui.wx.Frame, "__init__", return_value=None), \
                mock.patch.object(gui.YTChatFrame, "_build_menubar"), \
                mock.patch.object(gui.YTChatFrame, "_build_ui"), \
                mock.patch.object(gui.YTChatFrame, "_bind_events"), \
                mock.patch.object(gui.YTChatFrame, "_init_timer"), \
                mock.patch.object(gui.YTChatFrame, "SetBackgroundColour"), \
                mock.patch.object(gui.YTChatFrame, "Centre"), \
                mock.patch.object(gui, "anunciar_conflictos_atajos"), \
                mock.patch.object(gui.diagnostico, "crear_hilo", side_effect=crear):
            gui.YTChatFrame(None, configuracion, None, None, None, None)

        self.assertEqual(len(hilos), 1)
        self.assertEqual(hilos[0][1], "VigilanteInterfaz")
        hilo.start.assert_called_once_with()

    def test_el_nombre_del_vigilante_no_es_de_captura(self):
        self.assertNotIn("VigilanteInterfaz", apagado.NOMBRES_HILOS_CAPTURA)

    def test_el_tope_del_cierre_sale_de_apagado(self):
        self.assertEqual(apagado.TOPE_ESPERA_CIERRE, 3.0)
        frame = self._frame()
        hilo = mock.Mock()
        hilo.name = "TikTok"
        hilo.is_alive.return_value = True
        with mock.patch.object(gui.threading, "enumerate", return_value=[hilo]), \
                mock.patch.object(gui, "anunciar"), \
                mock.patch.object(gui.wx, "CallLater"):
            frame._on_close(None)

        self.assertEqual(frame._cierre_tope, apagado.TOPE_ESPERA_CIERRE)

    def test_comprobar_cierre_con_hilos_vivos_reprograma_y_no_destruye(self):
        frame = self._frame()
        frame._cierre_inicio = 100.0
        frame._cierre_tope = 3.0
        hilo = mock.Mock(name="Chat")
        hilo.name = "Chat"
        hilo.is_alive.return_value = True
        with mock.patch.object(gui.threading, "enumerate", return_value=[hilo]), \
                mock.patch.object(gui.time, "monotonic", return_value=101.0), \
                mock.patch.object(gui.wx, "CallLater") as call_later:
            frame._comprobar_cierre()

        call_later.assert_called_once_with(200, frame._comprobar_cierre)
        frame.Destroy.assert_not_called()

    def test_comprobar_cierre_sin_hilos_destruye_y_registra_cierre_limpio(self):
        frame = self._frame()
        frame._cierre_inicio = 100.0
        frame._cierre_tope = 3.0
        with mock.patch.object(gui.threading, "enumerate", return_value=[]), \
                mock.patch.object(gui.time, "monotonic", return_value=101.0), \
                mock.patch.object(gui.wx, "CallLater") as call_later, \
                mock.patch.object(gui.diagnostico.logger, "info") as registrar:
            frame._comprobar_cierre()

        call_later.assert_not_called()
        frame.Destroy.assert_called_once_with()
        registrar.assert_called_once_with("%s", "CIERRE captura limpia")

    def test_comprobar_cierre_con_tope_vencido_destruye_y_registra_hilos(self):
        frame = self._frame()
        frame._cierre_inicio = 100.0
        frame._cierre_tope = 3.0
        hilo = mock.Mock(name="TikTok")
        hilo.name = "TikTok"
        hilo.is_alive.return_value = True
        with mock.patch.object(gui.threading, "enumerate", return_value=[hilo]), \
                mock.patch.object(gui.time, "monotonic", return_value=104.0), \
                mock.patch.object(gui.wx, "CallLater") as call_later, \
                mock.patch.object(gui.diagnostico.logger, "info") as registrar:
            frame._comprobar_cierre()

        call_later.assert_not_called()
        frame.Destroy.assert_called_once_with()
        registrar.assert_called_once_with(
            "%s", "CIERRE por tope=3.0s hilos vivos=TikTok")


if __name__ == "__main__":
    unittest.main()
