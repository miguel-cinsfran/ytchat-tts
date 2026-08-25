import unittest

from overlay_datos import (
    COLOR_CUERPO,
    COLOR_DORADO,
    COLOR_TIKTOK,
    COLOR_YOUTUBE,
    FONDO_PEOR,
    PALETA_NOMBRES,
    color_de_nombre,
    evento_de_mensaje,
    inicial_de,
    relacion_de_contraste,
)


class OverlayDatosTests(unittest.TestCase):
    def test_color_de_nombre_es_determinista_y_reparte_la_paleta(self):
        nombres = [f"Nombre {i:03d}" for i in range(300)]
        reparto = tuple(sum(color_de_nombre(n) == color for n in nombres)
                        for color in PALETA_NOMBRES)
        self.assertEqual(reparto, (36, 30, 23, 22, 23, 31, 26, 20, 18, 17, 26, 28))

    def test_inicial_vacia(self):
        self.assertEqual(inicial_de("  "), "?")
        self.assertEqual(inicial_de("álex"), "Á")

    def test_evento_tiene_las_claves_exactas(self):
        evento = evento_de_mensaje("Ana", "Hola", "tiktok", "100")
        self.assertEqual(set(evento), {"autor", "texto", "plataforma", "monto"})
        self.assertEqual(evento["plataforma"], "tiktok")
        with self.assertRaises(ValueError):
            evento_de_mensaje("Ana", "Hola", "otra")

    def test_contraste_de_todos_los_colores_de_texto(self):
        colores = (*PALETA_NOMBRES, COLOR_YOUTUBE, COLOR_TIKTOK,
                   COLOR_DORADO, COLOR_CUERPO)
        for color in colores:
            with self.subTest(color=color):
                self.assertGreaterEqual(relacion_de_contraste(color, FONDO_PEOR), 4.5)

    def test_relacion_es_simetrica_y_esta_en_rango(self):
        relacion = relacion_de_contraste("#000000", "#FFFFFF")
        self.assertAlmostEqual(relacion, 21.0, places=6)
        self.assertEqual(relacion_de_contraste("#123456", "#123456"), 1.0)
