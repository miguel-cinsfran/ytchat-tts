import itertools
from pathlib import Path
import tempfile
import unittest

import esclavo_audio


class PruebasEsclavoAudio(unittest.TestCase):

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.temporal.name)
        self.url = "https://audio.ejemplo/flujo"

    def tearDown(self):
        self.temporal.cleanup()

    def _archivo(self, nombre, tamanio):
        ruta = self.carpeta / nombre
        ruta.write_bytes(b"x" * tamanio)
        return ruta

    def test_ruta_de_cache_conserva_id_y_extension(self):
        self.assertEqual(self.carpeta / "abc.webm",
                         esclavo_audio.ruta_de_cache(self.carpeta, "abc"))

    def test_esclavo_local_utilizable(self):
        ruta = self._archivo("audio.webm", 70000)
        self.assertEqual(str(ruta), esclavo_audio.esclavo_a_usar(ruta, self.url))

    def test_esclavo_sin_ruta_vuelve_a_red(self):
        self.assertEqual(self.url, esclavo_audio.esclavo_a_usar(None, self.url))

    def test_esclavo_inexistente_vuelve_a_red(self):
        self.assertEqual(self.url, esclavo_audio.esclavo_a_usar(
            self.carpeta / "no-existe.webm", self.url))

    def test_esclavo_vacio_vuelve_a_red(self):
        ruta = self._archivo("vacio.webm", 0)
        self.assertEqual(self.url, esclavo_audio.esclavo_a_usar(ruta, self.url))

    def test_esclavo_en_el_umbral_es_local(self):
        ruta = self._archivo("umbral.webm", esclavo_audio.TAMANIO_MINIMO)
        self.assertEqual(str(ruta), esclavo_audio.esclavo_a_usar(ruta, self.url))

    def test_esclavo_debajo_del_umbral_vuelve_a_red(self):
        ruta = self._archivo("corto.webm", esclavo_audio.TAMANIO_MINIMO - 1)
        self.assertEqual(self.url, esclavo_audio.esclavo_a_usar(ruta, self.url))

    def test_sobrantes_no_hay_si_entran_en_tope(self):
        self.assertEqual((), esclavo_audio.sobrantes_de_cache((("a", 1),), 2))

    def test_sobrantes_son_los_mas_viejos_en_orden(self):
        entradas = (("c", 3), ("a", 1), ("b", 2), ("d", 4))
        self.assertEqual(("a", "b"), esclavo_audio.sobrantes_de_cache(entradas, 2))

    def test_sobrantes_con_tope_cero_devuelve_todas(self):
        self.assertEqual(("a", "b"), esclavo_audio.sobrantes_de_cache(
            (("b", 2), ("a", 1)), 0))

    def test_sobrantes_con_marcas_iguales_no_falla(self):
        resultado = esclavo_audio.sobrantes_de_cache((("a", 1), ("b", 1)), 1)
        self.assertEqual(1, len(resultado))

    def test_propiedad_de_sobrantes(self):
        for cantidad, tope, marcas in itertools.product(range(7), range(8),
                                                         itertools.product(range(3), repeat=6)):
            entradas = tuple((f"r{i}", marcas[i]) for i in range(cantidad))
            sobrantes = esclavo_audio.sobrantes_de_cache(entradas, tope)
            ordenadas = sorted(entradas, key=lambda e: e[1])
            nuevas = {ruta for ruta, _ in (ordenadas[-tope:] if tope else ())}
            self.assertLessEqual(len(sobrantes) + min(tope, cantidad), cantidad)
            self.assertTrue(set(sobrantes).isdisjoint(nuevas))


if __name__ == "__main__":
    unittest.main()
