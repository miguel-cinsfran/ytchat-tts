import unittest
from unittest import mock

import deteccion
import gui
import gui_redactar
import redaccion


class TestRedaccion(unittest.TestCase):
    def test_motivo_chat_prioriza_desconexion(self):
        self.assertEqual(redaccion.motivo_chat(False, False, False, False, False, False),
                         "Conéctate a un directo para escribir en el chat")

    def test_motivo_chat_prioriza_tiktok(self):
        self.assertEqual(redaccion.motivo_chat(True, True, True, True, True, True),
                         "El chat de TikTok no permite escribir desde aquí")

    def test_motivo_chat_video_sin_directo(self):
        self.assertEqual(redaccion.motivo_chat(True, False, False, True, True, True),
                         "Este vídeo no tiene chat en vivo")

    def test_motivo_chat_sin_librerias(self):
        self.assertEqual(redaccion.motivo_chat(True, False, True, False, True, True),
                         "Faltan las librerías de la API para escribir en el chat")

    def test_motivo_chat_sin_sesion(self):
        self.assertIn("Inicia sesión", redaccion.motivo_chat(True, False, True, True, False, True))

    def test_motivo_chat_sin_acceso_al_chat(self):
        self.assertEqual(redaccion.motivo_chat(True, False, True, True, True, False),
                         "No se pudo acceder al chat de este directo")

    def test_motivo_chat_vacio_si_se_puede(self):
        self.assertEqual(redaccion.motivo_chat(True, False, True, True, True, True), "")

    def test_causa_sin_chat(self):
        casos = [
            ((False, False, False, False, ""), "sin_credenciales"),
            ((True, True, False, False, ""), "fallo_consulta"),
            ((True, False, False, False, ""), "sin_video"),
            ((True, False, True, False, ""), "no_es_directo"),
            ((True, False, True, True, ""), "chat_desactivado"),
            ((True, False, True, True, "chat"), ""),
        ]
        for argumentos, esperada in casos:
            with self.subTest(argumentos=argumentos):
                self.assertEqual(redaccion.causa_sin_chat(*argumentos), esperada)

    def test_motivo_chat_detalla_la_causa(self):
        casos = {
            "sin_credenciales": ("Falta la API key para saber si este directo permite "
                                  "escribir. Ponla en Preferencias, pestaña API"),
            "sin_video": "No se encontró este video",
            "no_es_directo": "Este video no es un directo",
            "chat_desactivado": "Este directo tiene el chat desactivado",
            "desconocida": "No se pudo acceder al chat de este directo",
        }
        for causa, esperada in casos.items():
            with self.subTest(causa=causa):
                self.assertEqual(redaccion.motivo_chat(
                    True, False, True, True, True, False, causa), esperada)

    def test_motivo_chat_directo_sin_credenciales_no_inventa_chat_ausente(self):
        for hay_librerias, hay_sesion in ((False, False), (True, False)):
            with self.subTest(hay_librerias=hay_librerias):
                motivo = redaccion.motivo_chat(True, False, True, hay_librerias,
                                                hay_sesion, False)
                self.assertNotEqual(motivo, "Este vídeo no tiene chat en vivo")

    def test_motivo_chat_llega_al_panel_en_directo_sin_sesion(self):
        app = gui.wx.App(False)
        ventana = gui.wx.Frame(None)
        self.addCleanup(ventana.Destroy)
        self.addCleanup(app.Destroy)
        panel = gui_redactar.PanelRedactar(ventana, "Mensaje", 200, lambda texto: None)
        frame = gui.YTChatFrame.__new__(gui.YTChatFrame)
        frame._conectado, frame._es_tiktok = True, False
        frame._tipo_video, frame._live_chat_id = deteccion.LIVE, ""
        frame._causa_sin_chat = ""
        frame._panel_redactar = panel
        with mock.patch.object(gui.youtube_api, "google_disponible", return_value=True), \
                mock.patch.object(gui.credenciales, "hay_sesion", return_value=False):
            frame._actualizar_motivo_redaccion()
        self.assertIn("inicia sesión", panel.boton.GetLabel())
        self.assertNotIn("no tiene chat", panel.boton.GetLabel())

    def test_motivo_comentario(self):
        self.assertIn("Conéctate", redaccion.motivo_comentario(False, True))
        self.assertIn("desactivados", redaccion.motivo_comentario(True, False, True))
        self.assertIn("Inicia sesión", redaccion.motivo_comentario(True, False))
        self.assertEqual(redaccion.motivo_comentario(True, True), "")

    def test_motivo_lectura_comentarios_sin_librerias(self):
        self.assertEqual(
            redaccion.motivo_lectura_comentarios(False, True, True),
            "Faltan las librerías de la API. Instálalas con: pip install "
            "google-api-python-client google-auth-oauthlib")

    def test_motivo_lectura_comentarios_sin_api_key(self):
        self.assertEqual(
            redaccion.motivo_lectura_comentarios(True, False, True),
            "Falta la API key. Ponla en Preferencias, pestaña API, para leer comentarios.")

    def test_motivo_lectura_comentarios_sin_video(self):
        self.assertEqual(redaccion.motivo_lectura_comentarios(True, True, False),
                         "Conéctate a un vídeo para poder leer los comentarios")

    def test_motivo_lectura_comentarios_vacio_si_se_puede(self):
        self.assertEqual(redaccion.motivo_lectura_comentarios(True, True, True), "")

    def test_motivo_lectura_comentarios_prioriza_librerias(self):
        self.assertIn("librerías", redaccion.motivo_lectura_comentarios(False, False, False))

    def test_validar(self):
        self.assertIn("Escribe", redaccion.validar("  \n ", 3))
        self.assertIn("4 caracteres", redaccion.validar("  abcd  ", 3))
        self.assertEqual(redaccion.validar("  abc  ", 3), "")

    def test_limpiar_conserva_saltos_internos(self):
        self.assertEqual(redaccion.limpiar("  uno\ndos  "), "uno\ndos")

    def test_etiqueta_con_motivo(self):
        self.assertEqual(redaccion.etiqueta_con_motivo("Comentar", "Inicia sesión"),
                         "Comentar (inicia sesión)")
        self.assertEqual(redaccion.etiqueta_con_motivo("Comentar", ""), "Comentar")
