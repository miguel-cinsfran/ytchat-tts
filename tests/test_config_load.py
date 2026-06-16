"""Tests de carga de config.ini (config.cargar_configuracion).

Se redirige app_dir() a un directorio temporal para no tocar el config.ini
real del proyecto.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config


class TestCargarConfiguracion(unittest.TestCase):

    def _cargar_en(self, contenido: str) -> dict:
        tmp = Path(self._tmp.name)
        (tmp / "config.ini").write_text(contenido, encoding="utf-8")
        with mock.patch.object(config, "app_dir", return_value=tmp):
            return config.cargar_configuracion()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_regenera_si_falta(self):
        tmp = Path(self._tmp.name)
        with mock.patch.object(config, "app_dir", return_value=tmp):
            cfg = config.cargar_configuracion()
        self.assertTrue((tmp / "config.ini").exists())
        self.assertEqual(cfg["formato_prefijo"], "nombre_mensaje")

    def test_valores_basicos(self):
        cfg = self._cargar_en(config._CONFIG_FALLBACK)
        self.assertEqual(cfg["velocidad"], 175)
        self.assertEqual(cfg["volumen"], 1.0)
        self.assertEqual(cfg["estrategia"], "limite")
        self.assertTrue(cfg["reconectar"])

    def test_clamp_velocidad(self):
        cfg = self._cargar_en("[voz]\nvelocidad = 9000\n")
        self.assertEqual(cfg["velocidad"], 500)

    def test_clamp_volumen(self):
        cfg = self._cargar_en("[voz]\nvolumen = 5.0\n")
        self.assertEqual(cfg["volumen"], 1.0)

    def test_estrategia_invalida_cae_a_limite(self):
        cfg = self._cargar_en("[cola]\nestrategia = loquesea\n")
        self.assertEqual(cfg["estrategia"], "limite")

    def test_listas_de_filtros(self):
        cfg = self._cargar_en(
            "[filtros]\npalabras_silenciadas = Spam, Publicidad\n"
            "usuarios_silenciados = Bot1, BOT2\n")
        self.assertEqual(cfg["palabras_silenciadas"], ["spam", "publicidad"])
        self.assertEqual(cfg["usuarios_silenciados"], ["bot1", "bot2"])

    def test_formato_invalido_cae_a_default(self):
        cfg = self._cargar_en("[lectura]\nformato_prefijo = raro\n")
        self.assertEqual(cfg["formato_prefijo"], "nombre_mensaje")


if __name__ == "__main__":
    unittest.main()
