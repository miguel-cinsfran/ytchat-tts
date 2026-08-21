from __future__ import annotations

import unittest

from progreso_ytdlp import analizar_linea_progreso


class TestAnalizarLineaProgreso(unittest.TestCase):
    def test_linea_http_conserva_el_nombre(self):
        datos = analizar_linea_progreso(
            "PROG 7168 117495 NA 3617032.130895091 0 "
            "nombre con espacios.m4a"
        )
        self.assertEqual(datos["descargado"], 7168)
        self.assertEqual(datos["total"], 117495)
        self.assertAlmostEqual(datos["pct"], 7168 * 100 / 117495)
        self.assertEqual(datos["velocidad"], 3617032.130895091)
        self.assertEqual(datos["eta"], 0)
        self.assertEqual(datos["nombre"], "nombre con espacios.m4a")

    def test_linea_hls_usa_total_estimado(self):
        datos = analizar_linea_progreso(
            "PROG 1024 NA 4876.190478857593 NA prueba.mp4"
        )
        self.assertIsNone(datos["total"])
        self.assertGreater(datos["pct"], 0)

    def test_linea_sin_prefijo_no_es_progreso(self):
        self.assertIsNone(analizar_linea_progreso("[youtube] Extracting URL"))

    def test_na_se_convierte_en_none(self):
        datos = analizar_linea_progreso("PROG 1 NA NA NA NA archivo.mp4")
        self.assertIsNone(datos["total"])
        self.assertIsNone(datos["velocidad"])
        self.assertIsNone(datos["eta"])
        self.assertEqual(datos["pct"], 0.0)

    def test_nombre_vacio_es_linea_rota(self):
        self.assertIsNone(analizar_linea_progreso("PROG 1 2 NA 3 4 "))

    def test_linea_incompleta_no_revienta(self):
        self.assertIsNone(analizar_linea_progreso("PROG 1 2"))

    def test_numero_roto_no_revienta(self):
        self.assertIsNone(analizar_linea_progreso("PROG roto 2 NA 3 4 archivo"))

    def test_salto_de_linea_no_contamina_el_nombre(self):
        datos = analizar_linea_progreso("PROG 1 2 NA 3 4 archivo.mp4\r\n")
        self.assertEqual(datos["nombre"], "archivo.mp4")


if __name__ == "__main__":
    unittest.main()
