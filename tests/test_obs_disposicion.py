import unittest

import obs_disposicion as obs


class GeometriaTest(unittest.TestCase):
    def test_mascaras_y_coordenadas(self):
        self.assertEqual(obs.ANCLAJES["inferior-izquierda"], 9)
        self.assertEqual(obs.coordenadas("superior-izquierda", 1600, 900), (32, 18, 5))
        self.assertEqual(obs.coordenadas("centro", 1600, 900), (800, 450, 0))
        self.assertEqual(obs.coordenadas("inferior-derecha", 1600, 900), (1568, 882, 10))
        with self.assertRaises(ValueError):
            obs.coordenadas("medio", 1600, 900)

    def test_rectangulo_para_las_nueve_mascaras(self):
        for nombre, mascara in obs.ANCLAJES.items():
            x, y, _ = obs.coordenadas(nombre, 1600, 900)
            rect = obs.rectangulo(x, y, 460, 620, mascara)
            esperado_x = x if "izquierda" in nombre else x - 460 if "derecha" in nombre else x - 230
            esperado_y = y if "superior" in nombre else y - 620 if "inferior" in nombre else y - 310
            self.assertEqual(rect[:2], (esperado_x, esperado_y))

    def test_areas_solape_y_fuera(self):
        self.assertEqual(obs.solape((0, 0, 100, 100), (50, 50, 100, 100)), 25.0)
        self.assertEqual(obs.solape((0, 0, 10, 10), (20, 20, 0, 10)), 0.0)
        self.assertEqual(obs.fuera_del_lienzo((-10, 0, 100, 100), 100, 100), 10.0)
        self.assertEqual(obs.fuera_del_lienzo((0, 0, 0, 100), 100, 100), 0.0)

    def test_reconoce_anclaje_con_tolerancia(self):
        self.assertEqual(obs.anclaje_de((32, 18, 460, 620), 1600, 900), "superior-izquierda")
        self.assertEqual(obs.anclaje_de((41, 18, 460, 620), 1600, 900), "")


if __name__ == "__main__":
    unittest.main()
