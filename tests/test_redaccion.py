import unittest

import redaccion


class TestRedaccion(unittest.TestCase):
    def test_motivo_chat_prioriza_desconexion(self):
        self.assertEqual(redaccion.motivo_chat(False, False, False, False),
                         "Conéctate a un directo para escribir en el chat")

    def test_motivo_chat_prioriza_tiktok(self):
        self.assertEqual(redaccion.motivo_chat(True, True, True, True),
                         "El chat de TikTok no permite escribir desde aquí")

    def test_motivo_chat_sin_chat(self):
        self.assertEqual(redaccion.motivo_chat(True, False, False, True),
                         "Este vídeo no tiene chat en vivo")

    def test_motivo_chat_sin_sesion(self):
        self.assertIn("Inicia sesión", redaccion.motivo_chat(True, False, True, False))

    def test_motivo_chat_vacio_si_se_puede(self):
        self.assertEqual(redaccion.motivo_chat(True, False, True, True), "")

    def test_motivo_comentario(self):
        self.assertIn("Conéctate", redaccion.motivo_comentario(False, True))
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
