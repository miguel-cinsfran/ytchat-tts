"""Tests del formateo del panel de información del vídeo (metadatos.py)."""

import unittest

import metadatos
from metadatos import _fmt_num, _fmt_fecha, _fmt_duracion, formatear


class TestFormateadores(unittest.TestCase):

    def test_num_miles_espanol(self):
        self.assertEqual(_fmt_num(30044), "30.044")
        self.assertEqual(_fmt_num(7), "7")
        self.assertEqual(_fmt_num(1234567), "1.234.567")

    def test_num_invalido_o_ausente(self):
        self.assertEqual(_fmt_num(None), "")
        self.assertEqual(_fmt_num("muchas"), "")

    def test_fecha(self):
        self.assertEqual(_fmt_fecha("20240131"), "31/01/2024")
        self.assertEqual(_fmt_fecha(""), "")
        self.assertEqual(_fmt_fecha("2024"), "")
        self.assertEqual(_fmt_fecha(None), "")

    def test_duracion(self):
        self.assertEqual(_fmt_duracion(1372), "22:52")
        self.assertEqual(_fmt_duracion(3661), "1:01:01")
        self.assertEqual(_fmt_duracion(0), "")
        self.assertEqual(_fmt_duracion(None), "")


class TestFormatear(unittest.TestCase):

    def test_vacio(self):
        self.assertEqual(formatear({}), "Sin información del vídeo.")
        self.assertEqual(formatear(None), "Sin información del vídeo.")

    def test_orden_y_etiquetas_vod(self):
        meta = {
            "titulo": "Un título", "canal": "El Canal", "vistas": 30044,
            "me_gusta": 1500, "comentarios": 87, "fecha": "20240131",
            "duracion": 1372, "en_vivo": False, "descripcion": "Hola\nmundo",
        }
        texto = formatear(meta)
        esperado = (
            "Un título\n"
            "Canal: El Canal\n"
            "Vistas: 30.044\n"
            "Me gusta: 1.500\n"
            "Comentarios: 87\n"
            "Publicado: 31/01/2024\n"
            "Duración: 22:52\n\n"
            "Descripción:\n"
            "Hola\nmundo"
        )
        self.assertEqual(texto, esperado)

    def test_directo_usa_espectadores_y_omite_duracion(self):
        meta = {"titulo": "Directo", "vistas": 120, "en_vivo": True,
                "duracion": 9999}
        texto = formatear(meta)
        self.assertIn("Espectadores: 120", texto)
        self.assertNotIn("Vistas", texto)
        self.assertNotIn("Duración", texto)

    def test_omite_campos_ausentes(self):
        # Solo título y descripción: nada de canal/vistas/etc.
        meta = {"titulo": "Solo título", "descripcion": "Texto"}
        texto = formatear(meta)
        self.assertEqual(texto, "Solo título\n\nDescripción:\nTexto")

    def test_solo_descripcion_sin_cabecera(self):
        self.assertEqual(formatear({"descripcion": "Algo"}),
                         "Sin información del vídeo.\n\nDescripción:\nAlgo")


if __name__ == "__main__":
    unittest.main()
