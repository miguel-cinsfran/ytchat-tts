"""Tests de los parsers puros de youtube_api (sin red ni libs de Google)."""

import unittest

from youtube_api import (
    normalizar_comentario, parsear_pagina_comentarios, mensaje_error_api,
)


class TestNormalizarComentario(unittest.TestCase):

    def test_basico(self):
        c = normalizar_comentario({
            "authorDisplayName": "Ana",
            "textOriginal": "hola",
            "likeCount": 5,
            "publishedAt": "2026-01-01T00:00:00Z",
            "authorChannelId": {"value": "UCabc"},
        }, comment_id="x1")
        self.assertEqual(c.autor, "Ana")
        self.assertEqual(c.texto, "hola")
        self.assertEqual(c.likes, 5)
        self.assertEqual(c.autor_canal_id, "UCabc")
        self.assertEqual(c.comment_id, "x1")
        self.assertFalse(c.es_respuesta)

    def test_campos_faltantes(self):
        c = normalizar_comentario({})
        self.assertEqual(c.autor, "Usuario")
        self.assertEqual(c.texto, "")
        self.assertEqual(c.likes, 0)
        self.assertEqual(c.autor_canal_id, "")

    def test_likecount_invalido(self):
        c = normalizar_comentario({"likeCount": "no-numero"})
        self.assertEqual(c.likes, 0)

    def test_textdisplay_como_respaldo(self):
        c = normalizar_comentario({"textDisplay": "<b>hola</b>"})
        self.assertEqual(c.texto, "<b>hola</b>")

    def test_canal_como_string(self):
        c = normalizar_comentario({"authorChannelId": "UCxyz"})
        self.assertEqual(c.autor_canal_id, "UCxyz")


class TestParsearPagina(unittest.TestCase):

    def _resp(self):
        return {
            "items": [{
                "snippet": {
                    "totalReplyCount": 1,
                    "topLevelComment": {
                        "id": "top1",
                        "snippet": {"authorDisplayName": "Ana", "textOriginal": "hola",
                                    "likeCount": 3},
                    },
                },
                "replies": {"comments": [{
                    "id": "rep1",
                    "snippet": {"authorDisplayName": "Beto", "textOriginal": "que tal"},
                }]},
            }],
            "nextPageToken": "NEXT",
        }

    def test_intercala_respuestas(self):
        coms, nxt = parsear_pagina_comentarios(self._resp())
        self.assertEqual(nxt, "NEXT")
        self.assertEqual(len(coms), 2)
        self.assertEqual(coms[0].autor, "Ana")
        self.assertEqual(coms[0].respuestas, 1)
        self.assertFalse(coms[0].es_respuesta)
        self.assertEqual(coms[1].autor, "Beto")
        self.assertTrue(coms[1].es_respuesta)

    def test_excluir_respuestas(self):
        coms, _ = parsear_pagina_comentarios(self._resp(), incluir_respuestas=False)
        self.assertEqual(len(coms), 1)
        self.assertEqual(coms[0].autor, "Ana")

    def test_respuesta_conserva_id_para_responder(self):
        coms, _ = parsear_pagina_comentarios(self._resp())
        self.assertEqual(coms[0].comment_id, "top1")
        self.assertEqual(coms[1].comment_id, "rep1")

    def test_pagina_vacia(self):
        coms, nxt = parsear_pagina_comentarios({})
        self.assertEqual(coms, [])
        self.assertEqual(nxt, "")


class TestMensajeError(unittest.TestCase):

    def test_quota(self):
        self.assertIn("cuota", mensaje_error_api("The request cannot be completed: quotaExceeded"))

    def test_comentarios_desactivados(self):
        self.assertIn("desactivados", mensaje_error_api("commentsDisabled"))

    def test_video_no_encontrado(self):
        self.assertIn("vídeo", mensaje_error_api("videoNotFound"))

    def test_sin_permiso(self):
        self.assertIn("permiso", mensaje_error_api("insufficientPermissions"))

    def test_generico(self):
        self.assertIn("Error de la API", mensaje_error_api("algo raro"))


if __name__ == "__main__":
    unittest.main()
