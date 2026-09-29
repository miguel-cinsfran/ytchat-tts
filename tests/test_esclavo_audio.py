import itertools
from pathlib import Path
import tempfile
import unittest

from ytchat.player import esclavo_audio


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

    def test_escalones_de_progreso(self):
        self.assertEqual((75,), esclavo_audio.escalones_de_progreso(10, 80))
        self.assertEqual((25,), esclavo_audio.escalones_de_progreso(10, 25))

    def test_sobrantes_por_tamanio_cabe(self):
        self.assertEqual((), esclavo_audio.sobrantes_por_tamanio((("a", 2, 1),), 2))

    def test_sobrantes_por_tamanio_borra_el_mas_viejo(self):
        self.assertEqual(("a",), esclavo_audio.sobrantes_por_tamanio(
            (("a", 2, 1), ("b", 2, 2)), 3))

    def test_sobrantes_por_tamanio_borra_varios(self):
        self.assertEqual(("a", "b"), esclavo_audio.sobrantes_por_tamanio(
            (("a", 2, 1), ("b", 2, 2), ("c", 2, 3)), 2))

    def test_sobrantes_por_tamanio_cero_borra_todo(self):
        self.assertEqual(("a", "b"), esclavo_audio.sobrantes_por_tamanio(
            (("a", 2, 1), ("b", 2, 2)), 0))

    def test_sobrantes_por_tamanio_vacio(self):
        self.assertEqual((), esclavo_audio.sobrantes_por_tamanio((), 2))

    def test_huerfanos_viejo_con_prefijo_sale(self):
        ahora = 1000000.0
        entradas = (("carpeta/.ytcache-viejo.mp4.part", 10, ahora - 10800),)
        self.assertEqual(("carpeta/.ytcache-viejo.mp4.part",),
                         esclavo_audio.temporales_huerfanos(entradas, ahora))

    def test_huerfanos_reciente_con_prefijo_no_sale(self):
        ahora = 1000000.0
        entradas = (("carpeta/.ytcache-nuevo.mp4.part", 10, ahora - 600),)
        self.assertEqual((), esclavo_audio.temporales_huerfanos(entradas, ahora))

    def test_huerfanos_viejo_sin_prefijo_no_sale(self):
        ahora = 1000000.0
        entradas = (("carpeta/abc.mp4", 10, ahora - 10800),)
        self.assertEqual((), esclavo_audio.temporales_huerfanos(entradas, ahora))

    def test_huerfanos_justo_en_el_limite_no_sale(self):
        ahora = 1000000.0
        entradas = ((".ytcache-limite.mp4.part", 10, ahora - 7200),)
        self.assertEqual((), esclavo_audio.temporales_huerfanos(entradas, ahora))

    def test_huerfanos_vacio_da_vacio(self):
        self.assertEqual((), esclavo_audio.temporales_huerfanos((), 1000000.0))

    def test_huerfanos_acepta_path_con_carpeta_y_respeta_orden(self):
        ahora = 1000000.0
        viejo_uno = Path("carpeta") / ".ytcache-uno.part"
        reciente = Path("carpeta") / ".ytcache-dos.part"
        bueno = Path("carpeta") / "video.mp4"
        viejo_dos = Path("carpeta") / ".ytcache-tres.part"
        entradas = ((bueno, 5, ahora - 20000),
                    (viejo_uno, 5, ahora - 10000),
                    (reciente, 5, ahora - 100),
                    (viejo_dos, 5, ahora - 20000))
        self.assertEqual((viejo_uno, viejo_dos),
                         esclavo_audio.temporales_huerfanos(entradas, ahora))


if __name__ == "__main__":
    unittest.main()
