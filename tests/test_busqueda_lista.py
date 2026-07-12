"""Tests de la búsqueda por prefijo (type-ahead) de listas."""

import unittest

from busqueda_lista import buscar_prefijo, normalizar


class TestNormalizar(unittest.TestCase):

    def test_quita_acentos(self):
        self.assertEqual(normalizar("Ángel"), normalizar("angel"))

    def test_casefold(self):
        self.assertEqual(normalizar("MIGUEL"), normalizar("miguel"))

    def test_espacios_iniciales(self):
        self.assertEqual(normalizar("   hola"), normalizar("hola"))

    def test_vacio(self):
        self.assertEqual(normalizar(""), "")
        self.assertEqual(normalizar(None), "")


class TestBuscarPrefijo(unittest.TestCase):

    def setUp(self):
        self.items = [
            "autor1: hola a todos, 12:00:00",
            "Miguel: buenas tardes, 12:00:01",
            "autor3: jaja, 12:00:02",
            "Ángela: qué tal, 12:00:03",
            "migue2: otra vez, 12:00:04",
        ]

    def test_prefijo_simple(self):
        self.assertEqual(buscar_prefijo(self.items, 0, "autor"), 0)

    def test_ignora_mayusculas(self):
        self.assertEqual(buscar_prefijo(self.items, 0, "MIGUEL"), 1)

    def test_ignora_acentos(self):
        # "angela" (sin tilde) debe encontrar "Ángela".
        self.assertEqual(buscar_prefijo(self.items, 0, "angela"), 3)

    def test_multiletra_no_confunde_con_single_letra(self):
        # "mig" debe llegar a "Miguel" (índice 1), no quedarse en autor1.
        self.assertEqual(buscar_prefijo(self.items, 0, "mig"), 1)

    def test_prefijo_creciente_mantiene_coincidencia(self):
        # Buscar "m", luego "mi", luego "mig" desde el mismo punto de partida
        # deben converger en el mismo candidato mientras siga siendo válido.
        idx_m = buscar_prefijo(self.items, 0, "m")
        idx_mi = buscar_prefijo(self.items, 0, "mi")
        idx_mig = buscar_prefijo(self.items, 0, "mig")
        self.assertEqual(idx_m, 1)
        self.assertEqual(idx_mi, 1)
        self.assertEqual(idx_mig, 1)

    def test_prefijo_creciente_deja_de_matchear(self):
        # "migu" también matchea Miguel (índice 1); "miguel2" no matchea nada.
        self.assertEqual(buscar_prefijo(self.items, 0, "migu"), 1)
        self.assertIsNone(buscar_prefijo(self.items, 0, "miguel2"))

    def test_envolvente_wrap(self):
        # Buscando desde después de "migue2" (índice 4), "autor" solo aparece
        # antes: debe envolver y encontrar el índice 0.
        self.assertEqual(buscar_prefijo(self.items, 4, "autor"), 0)

    def test_desde_inclusive(self):
        # Si el propio ítem en `desde` ya matchea, se devuelve ese mismo.
        self.assertEqual(buscar_prefijo(self.items, 2, "autor3"), 2)

    def test_sin_coincidencia(self):
        self.assertIsNone(buscar_prefijo(self.items, 0, "xyz"))

    def test_lista_vacia(self):
        self.assertIsNone(buscar_prefijo([], 0, "a"))

    def test_prefijo_vacio(self):
        self.assertIsNone(buscar_prefijo(self.items, 0, ""))

    def test_desde_fuera_de_rango_no_revienta(self):
        # `desde` puede llegar mayor que la lista (índice tras borrar filas);
        # el módulo de la longitud debe seguir funcionando (7 % 5 == 2, que ya
        # matchea "autor3").
        self.assertEqual(buscar_prefijo(self.items, 7, "autor"), 2)


if __name__ == "__main__":
    unittest.main()
