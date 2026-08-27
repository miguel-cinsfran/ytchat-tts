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


class DescripcionTest(unittest.TestCase):
    def test_constantes_y_inmutabilidad(self):
        with self.assertRaises(Exception):
            obs.SnapshotPanel().escena = "Juego"
        self.assertEqual(len(obs.COMPONENTES), 11)
        self.assertIn("posicion", obs.ACTIVOS_DEFECTO)

    def test_componentes_cortos(self):
        s = obs.SnapshotPanel(conectado=False, escena="Juego", ancho=460, alto=620,
                              lienzo_ancho=1600, lienzo_alto=900, visible=False,
                              bloqueada=True, tapada_por="Cámara", solapes=(("Cámara", 12.4),),
                              fuera=12.4, mensajes_visibles=14, tamano_letra=18)
        self.assertEqual(obs.describir(s, ("conexion",)), "Sin conexión con OBS.")
        self.assertEqual(obs.describir(s, ("escena",)), "Juego.")
        self.assertEqual(obs.describir(s, ("tamano",)), "460 por 620, 29% del ancho.")
        self.assertEqual(obs.describir(s, ("capa",)), "Tapada por Cámara.")
        self.assertEqual(obs.describir(s, ("solape",)), "Cámara 12%.")
        self.assertEqual(obs.describir(s, ("visible",)), "Oculto.")
        self.assertEqual(obs.describir(s, ("bloqueada",)), "Fijado.")
        self.assertEqual(obs.describir(s, ("fuera",)), "12% fuera del lienzo.")
        self.assertEqual(obs.describir(s, ("aspecto",)), "14 mensajes, letra 18.")

    def test_largo_y_union(self):
        s = obs.SnapshotPanel(conectado=True, escena="Juego", al_aire=False,
                              ancho=460, alto=620, lienzo_ancho=1600,
                              mensajes_visibles=14, tamano_letra=18)
        esperado = ("OBS: conectado\nEscena: Juego, no al aire\nTamaño: 460 por 620 píxeles, "
                    "29% del ancho de pantalla\nCapa: al frente\nLibre\nVisible: sí\n"
                    "Fijado: no\nAspecto: 14 mensajes visibles, tamaño de letra 18\n"
                    "El fondo del panel es transparente. Solo se ven las tarjetas de los mensajes, "
                    "apiladas contra el borde inferior.")
        self.assertEqual(obs.describir(s, obs.COMPONENTES, "largo"), esperado)
        self.assertEqual(obs.describir(obs.SnapshotPanel(), ("transparencia",), "corto"), "")
        self.assertEqual(obs.describir(obs.SnapshotPanel(), ("transparencia",), "largo"),
                         "El fondo del panel es transparente. Solo se ven las tarjetas de los mensajes, apiladas contra el borde inferior.")


if __name__ == "__main__":
    unittest.main()
