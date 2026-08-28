"""Pruebas de la sustitución de avisos del lector."""

import unittest

import avisos


class TestInterrupcion(unittest.TestCase):

    def test_misma_categoria_interrumpe(self):
        self.assertTrue(avisos.debe_interrumpir("volumen", "volumen"))

    def test_categorias_distintas_no_interrumpen(self):
        self.assertFalse(avisos.debe_interrumpir("volumen", "velocidad"))

    def test_sin_categoria_despues_de_categoria_no_interrumpe(self):
        self.assertFalse(avisos.debe_interrumpir("", "volumen"))

    def test_categoria_despues_de_sin_categoria_no_interrumpe(self):
        self.assertFalse(avisos.debe_interrumpir("volumen", ""))

    def test_dos_sin_categoria_no_interrumpen(self):
        self.assertFalse(avisos.debe_interrumpir("", ""))

    def test_primer_anuncio_no_interrumpe(self):
        self.assertFalse(avisos.debe_interrumpir("volumen", avisos.ultima_categoria()))


class TestMemoriaCategoria(unittest.TestCase):

    def setUp(self):
        avisos.recordar_categoria("")

    def test_recuerda_la_ultima_categoria(self):
        avisos.recordar_categoria("ajuste")
        self.assertEqual(avisos.ultima_categoria(), "ajuste")


if __name__ == "__main__":
    unittest.main()
