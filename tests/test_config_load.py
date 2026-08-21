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

    def test_inyecta_seccion_descargas_con_defaults(self):
        # Sin [descargas] en el INI, cargar_configuracion debe inyectar los
        # defaults (mp4, 192, app_dir()/Descargas, false) y devolverlos en el
        # dict.
        cfg = self._cargar_en(config._CONFIG_FALLBACK.replace(
            "[descargas]\nformato = mp4\nbitrate = 192\ncarpeta = Descargas\nenumerar = false\n",
            ""))
        self.assertIn("descargas", cfg)
        self.assertEqual(cfg["descargas_formato"], "mp4")
        self.assertEqual(cfg["descargas_bitrate"], 192)
        self.assertTrue(cfg["descargas_carpeta"].endswith("Descargas"))
        self.assertFalse(cfg["descargas_enumerar"])

    def test_obtener_opciones_descarga_devuelve_defaults_si_no_existe(self):
        import config
        with mock.patch.object(config, "app_dir", return_value=Path(self._tmp.name)):
            op = config.obtener_opciones_descarga()
        self.assertEqual(op["formato"], "mp4")
        self.assertEqual(op["bitrate"], 192)
        self.assertIn("Descargas", op["carpeta"])
        self.assertFalse(op["enumerar"])

    def test_guardar_opciones_descarga_persiste(self):
        import config
        with mock.patch.object(config, "app_dir", return_value=Path(self._tmp.name)):
            (Path(self._tmp.name) / "config.ini").write_text(
                config._CONFIG_FALLBACK, encoding="utf-8")
            config.guardar_opciones_descarga(
                {"formato": "mp3", "bitrate": 320, "carpeta": "/x/y", "enumerar": True})
            op = config.obtener_opciones_descarga()
        self.assertEqual(op["formato"], "mp3")
        self.assertEqual(op["bitrate"], 320)
        self.assertEqual(op["carpeta"], "/x/y")
        self.assertTrue(op["enumerar"])

    def test_guardar_opciones_descarga_normaliza_invalidos(self):
        import config
        with mock.patch.object(config, "app_dir", return_value=Path(self._tmp.name)):
            (Path(self._tmp.name) / "config.ini").write_text(
                config._CONFIG_FALLBACK, encoding="utf-8")
            # enumerar en el dict es bool, no string. Pasamos un valor truthy
            # pero el código debe normalizarlo (o mantenerlo si es bool True).
            # En este test pasamos un bool True para forzar la rama de
            # normalización a no actuar — y verificamos que un bitrate fuera
            # de rango y un formato inválido caen a los defaults.
            config.guardar_opciones_descarga(
                {"formato": "raro", "bitrate": 999, "enumerar": True})
            op = config.obtener_opciones_descarga()
        self.assertEqual(op["formato"], "mp4")
        self.assertEqual(op["bitrate"], 192)
        self.assertTrue(op["enumerar"])


if __name__ == "__main__":
    unittest.main()
