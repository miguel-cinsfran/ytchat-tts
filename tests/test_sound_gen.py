"""Contratos entre la configuración y el generador de sonidos."""

import contextlib
import io
import tempfile
import unittest
import wave
from pathlib import Path

import config
import sound_gen


class PruebasSoundGen(unittest.TestCase):
    def test_eventos_del_tema_default_coinciden_con_configuracion(self):
        generados = {Path(nombre).stem for nombre in sound_gen.TEMAS["default"]}
        configurados = set(config._EVENTOS_SONIDO)
        sobrantes = sorted(generados - configurados)
        faltantes = sorted(configurados - generados)

        self.assertEqual(
            generados,
            configurados,
            f"Sobran: {sobrantes}; faltan: {faltantes}",
        )

    def test_los_dos_temas_tienen_las_mismas_claves(self):
        self.assertEqual(set(sound_gen.TEMAS["suave"]), set(sound_gen.TEMAS["default"]))

    def test_los_generadores_suaves_son_distintos_a_los_del_tema_default(self):
        for nombre, generador_default in sound_gen.TEMAS["default"].items():
            generador_suave = sound_gen.TEMAS["suave"][nombre]
            self.assertTrue(callable(generador_default), nombre)
            self.assertTrue(callable(generador_suave), nombre)
            self.assertIsNot(generador_suave, generador_default, nombre)

    def test_el_paneo_solo_refiere_eventos_validos_y_esta_en_rango(self):
        eventos = set(sound_gen.TEMAS["default"])
        self.assertTrue(set(sound_gen.PANEO).issubset(eventos))
        for nombre, valor in sound_gen.PANEO.items():
            self.assertGreaterEqual(valor, -1, nombre)
            self.assertLessEqual(valor, 1, nombre)

    def test_generar_los_dos_temas_crea_wav_estereo(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directorio:
            raiz = Path(directorio)
            with contextlib.redirect_stdout(io.StringIO()):
                for tema, sonidos in sound_gen.TEMAS.items():
                    destino = raiz / tema
                    self.assertEqual(sound_gen.generar_tema(tema, destino), 16)
                    for nombre in sonidos:
                        ruta = destino / nombre
                        self.assertGreater(ruta.stat().st_size, 0, nombre)
                        with wave.open(str(ruta), "rb") as wav:
                            self.assertEqual(wav.getnchannels(), 2, nombre)

    def test_generar_tema_omite_archivos_ya_existentes(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directorio:
            destino = Path(directorio)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sound_gen.generar_tema("default", destino), 16)
                self.assertEqual(sound_gen.generar_tema("default", destino), 0)


if __name__ == "__main__":
    unittest.main()
