"""Pruebas de la migración de datos de la raíz a la subcarpeta de datos."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ytchat.core import migracion_datos
from ytchat.core import paths


def _instalacion_vieja(inst):
    """Crea una instalación vieja falsa y devuelve pares nombre y contenido."""
    piezas = {
        "config.ini": "[voz]\nvelocidad = 200\n",
        "credenciales.json": '{"falso": true}',
        "ytchat-debug.log": "traza vieja\n",
        "ytchat-debug.log.2": "traza rotada\n",
    }
    for nombre, contenido in piezas.items():
        (inst / nombre).write_text(contenido, encoding="utf-8")
    cache = inst / "cache-audio"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "clip.mp3").write_bytes(b"audio falso")
    return piezas


class TestMigrar(unittest.TestCase):

    def test_instalacion_vieja_completa_termina_en_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp) / "app"
            inst.mkdir()
            datos = inst / "data"
            piezas = _instalacion_vieja(inst)
            with mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=inst), \
                 mock.patch.object(paths, "carpeta_datos",
                                   return_value=datos):
                resultado = migracion_datos.migrar(
                    paths.carpeta_instalacion(), paths.carpeta_datos(),
                    paths.datos_a_migrar(), paths.sounds_ini())
            for nombre, contenido in piezas.items():
                with self.subTest(archivo=nombre):
                    self.assertEqual((datos / nombre).read_text(encoding="utf-8"),
                                     contenido)
                    self.assertFalse((inst / nombre).exists())
            self.assertEqual((datos / "cache-audio" / "clip.mp3").read_bytes(),
                             b"audio falso")
            self.assertFalse((inst / "cache-audio").exists())
            self.assertIn("config.ini", resultado.movidos)

    def test_sounds_ini_se_copia_y_la_raiz_sigue(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp) / "app"
            inst.mkdir()
            datos = inst / "data"
            (inst / "sounds.ini").write_text("[sonidos]\n", encoding="utf-8")
            with mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=inst), \
                 mock.patch.object(paths, "carpeta_datos",
                                   return_value=datos):
                resultado = migracion_datos.migrar(
                    paths.carpeta_instalacion(), paths.carpeta_datos(),
                    paths.datos_a_migrar(), paths.sounds_ini())
            self.assertTrue((inst / "sounds.ini").is_file())
            self.assertEqual(
                (datos / "sounds.ini").read_text(encoding="utf-8"),
                (inst / "sounds.ini").read_text(encoding="utf-8"))
            self.assertIn("sounds.ini", resultado.copiados)
            self.assertNotIn("sounds.ini", resultado.movidos)

    def test_destino_existente_no_se_pisa_y_figura_en_conflictos(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp) / "app"
            inst.mkdir()
            datos = inst / "data"
            datos.mkdir()
            (inst / "config.ini").write_text("viejo\n", encoding="utf-8")
            (datos / "config.ini").write_text("nuevo\n", encoding="utf-8")
            with mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=inst), \
                 mock.patch.object(paths, "carpeta_datos",
                                   return_value=datos):
                resultado = migracion_datos.migrar(
                    paths.carpeta_instalacion(), paths.carpeta_datos(),
                    paths.datos_a_migrar(), paths.sounds_ini())
            self.assertEqual((datos / "config.ini").read_text(encoding="utf-8"),
                             "nuevo\n")
            self.assertEqual((inst / "config.ini").read_text(encoding="utf-8"),
                             "viejo\n")
            self.assertIn("config.ini", resultado.conflictos)

    def test_segunda_llamada_no_hace_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp) / "app"
            inst.mkdir()
            datos = inst / "data"
            _instalacion_vieja(inst)
            with mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=inst), \
                 mock.patch.object(paths, "carpeta_datos",
                                   return_value=datos):
                rutas = paths.datos_a_migrar()
                sonidos = paths.sounds_ini()
                migracion_datos.migrar(inst, datos, rutas, sonidos)
                segunda = migracion_datos.migrar(inst, datos, rutas, sonidos)
            self.assertEqual(segunda.movidos, [])
            self.assertEqual(segunda.copiados, [])
            self.assertEqual(segunda.conflictos, [])
            self.assertEqual(segunda.errores, [])

    def test_sin_nada_viejo_no_crea_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp) / "app"
            inst.mkdir()
            datos = inst / "data"
            with mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=inst), \
                 mock.patch.object(paths, "carpeta_datos",
                                   return_value=datos):
                resultado = migracion_datos.migrar(
                    paths.carpeta_instalacion(), paths.carpeta_datos(),
                    paths.datos_a_migrar(), paths.sounds_ini())
            self.assertFalse(datos.exists())
            self.assertEqual(resultado.movidos, [])
            self.assertEqual(resultado.copiados, [])
            self.assertEqual(resultado.conflictos, [])
            self.assertEqual(resultado.errores, [])

    def test_si_mover_falla_cae_a_la_copia(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp) / "app"
            inst.mkdir()
            datos = inst / "data"
            (inst / "config.ini").write_text("viejo\n", encoding="utf-8")
            with mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=inst), \
                 mock.patch.object(paths, "carpeta_datos",
                                   return_value=datos):
                rutas = paths.datos_a_migrar()
                sonidos = paths.sounds_ini()
                with mock.patch(
                        "ytchat.core.migracion_datos.os.replace",
                        side_effect=OSError("bloqueado")):
                    resultado = migracion_datos.migrar(
                        inst, datos, rutas, sonidos)
            self.assertIn("config.ini", resultado.copiados)
            self.assertEqual((datos / "config.ini").read_text(encoding="utf-8"),
                             "viejo\n")
            self.assertTrue((inst / "config.ini").is_file())

    def test_si_copiar_tambien_falla_va_a_errores_sin_lanzar(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp) / "app"
            inst.mkdir()
            datos = inst / "data"
            (inst / "config.ini").write_text("viejo\n", encoding="utf-8")
            with mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=inst), \
                 mock.patch.object(paths, "carpeta_datos",
                                   return_value=datos):
                rutas = paths.datos_a_migrar()
                sonidos = paths.sounds_ini()
                with mock.patch(
                        "ytchat.core.migracion_datos.os.replace",
                        side_effect=OSError("bloqueado")), \
                     mock.patch(
                        "ytchat.core.migracion_datos.shutil.copy2",
                        side_effect=OSError("disco lleno")):
                    resultado = migracion_datos.migrar(
                        inst, datos, rutas, sonidos)
            self.assertTrue(
                any("config.ini" in error for error in resultado.errores))
            self.assertTrue((inst / "config.ini").is_file())


class TestCableadoMain(unittest.TestCase):

    def test_migrar_se_llama_antes_que_configurar_logging(self):
        import main as app_main
        orden = []

        def falso_migrar(*args, **kwargs):
            orden.append("migrar")
            return migracion_datos.ResultadoMigracion()

        def falso_logging(*args, **kwargs):
            orden.append("logging")
            raise RuntimeError("corte de prueba")

        with mock.patch.object(app_main.migracion_datos, "migrar",
                               side_effect=falso_migrar), \
             mock.patch.object(app_main, "configurar_logging",
                               side_effect=falso_logging):
            with self.assertRaises(RuntimeError):
                app_main.main()
        self.assertEqual(orden, ["migrar", "logging"])


if __name__ == "__main__":
    unittest.main()
