"""Pruebas de la salida accesible de los registros."""

import logging
import unittest
from unittest import mock

import gui
import apagado
import ytdlp_bin


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


class TestActualizarYtdlp(unittest.TestCase):

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

    def test_anuncia_antes_de_descargar_y_al_terminar(self):
        anuncios = []
        hilo = mock.Mock()
        hilo.start.side_effect = lambda: hilo.target()

        def crear(target, nombre):
            hilo.target = target
            return hilo

        def actualizar(aviso):
            aviso()
            return "actualizado", "2026.08.20", "2026.08.21"

        with mock.patch.object(gui, "anunciar", side_effect=anuncios.append), \
                mock.patch.object(gui.diagnostico, "crear_hilo", side_effect=crear), \
                mock.patch.object(gui.wx, "CallAfter", side_effect=lambda fn, *args: fn(*args)), \
                mock.patch.object(gui.wx, "MessageBox") as mensaje, \
                mock.patch.object(ytdlp_bin, "actualizar_ytdlp", side_effect=actualizar):
            gui.YTChatFrame._on_actualizar_ytdlp(gui.YTChatFrame.__new__(gui.YTChatFrame), None)
        self.assertIn("Buscando", anuncios[0])
        self.assertIn("Descargando", anuncios[1])
        self.assertEqual(1, mensaje.call_count)
        self.assertIn("actualizó", mensaje.call_args.args[0])


class TestCierreVentana(unittest.TestCase):

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
