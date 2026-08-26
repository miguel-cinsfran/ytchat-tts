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
