import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

import ytdlp_bin


class PruebasYtdlpBin(unittest.TestCase):
    def test_desde_codigo_fuente_no_usa_ejecutable_de_la_carpeta_del_interprete(self):
        with tempfile.TemporaryDirectory() as carpeta:
            interprete = Path(carpeta) / "Scripts"
            interprete.mkdir()
            (interprete / "yt-dlp.exe").write_bytes(b"lanzador")
            with patch.object(ytdlp_bin, "_ruta_actualizada", return_value=Path(carpeta) / "no.exe"), \
                    patch.object(sys, "executable", str(interprete / "python.exe")), \
                    patch.object(sys, "frozen", False, create=True):
                self.assertIsNone(ytdlp_bin.ruta_ytdlp())

    def test_empaquetado_usa_ejecutable_junto_al_interprete(self):
        with tempfile.TemporaryDirectory() as carpeta:
            carpeta = Path(carpeta)
            ejecutable = carpeta / "YTChatTTS.exe"
            paquete = carpeta / "yt-dlp.exe"
            ejecutable.touch()
            paquete.write_bytes(b"programa")
            with patch.object(sys, "executable", str(ejecutable)), \
                    patch.object(sys, "frozen", True, create=True):
                self.assertEqual(paquete.resolve(), ytdlp_bin._ruta_del_paquete())

    def test_construccion_rechaza_archivo_menor_que_un_mib(self):
        construir = Path(__file__).parents[1] / "construir.bat"
        texto = construir.read_text(encoding="utf-8")
        self.assertIn('set "YTDLP_MIN_BYTES=1048576"', texto)
        self.assertIn('if %%~zf LSS %YTDLP_MIN_BYTES%', texto)
        self.assertIn('del /q "%OUT%\\yt-dlp.exe"', texto)

    def test_firma_sha256_lee_el_archivo_correcto(self):
        texto = (
            "a" * 64 + "  otro.zip\n"
            + "b" * 64 + "   yt-dlp.exe\n"
            + "c" * 64 + "  archivo con espacios.zip\n"
        )
        self.assertEqual("b" * 64, ytdlp_bin.firma_sha256(texto, "yt-dlp.exe"))
        self.assertEqual(
            "c" * 64,
            ytdlp_bin.firma_sha256(texto, "archivo con espacios.zip"),
        )

    def test_firma_sha256_devuelve_vacio_si_no_existe(self):
        self.assertEqual("", ytdlp_bin.firma_sha256("a" * 64 + "  otro.exe", "no.exe"))


    def test_busqueda_prefiere_la_copia_actualizada(self):
        with tempfile.TemporaryDirectory() as carpeta:
            actualizada = Path(carpeta) / "actualizada.exe"
            paquete = Path(carpeta) / "paquete.exe"
            actualizada.touch()
            paquete.touch()
            with patch.object(ytdlp_bin, "_ruta_actualizada", return_value=actualizada), \
                    patch.object(ytdlp_bin, "_ruta_del_paquete", return_value=paquete):
                self.assertEqual(str(actualizada), ytdlp_bin.ruta_ytdlp())

    def test_busqueda_usa_la_unica_copia(self):
        with tempfile.TemporaryDirectory() as carpeta:
            paquete = Path(carpeta) / "paquete.exe"
            paquete.touch()
            with patch.object(ytdlp_bin, "_ruta_actualizada", return_value=Path(carpeta) / "no.exe"), \
                    patch.object(ytdlp_bin, "_ruta_del_paquete", return_value=paquete):
                self.assertEqual(str(paquete), ytdlp_bin.ruta_ytdlp())

    def test_busqueda_sin_copias_devuelve_none(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with patch.object(ytdlp_bin, "_ruta_actualizada", return_value=Path(carpeta) / "no1.exe"), \
                    patch.object(ytdlp_bin, "_ruta_del_paquete", return_value=Path(carpeta) / "no2.exe"):
                self.assertIsNone(ytdlp_bin.ruta_ytdlp())

    def test_ruta_actualizada_usa_localappdata(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with patch.dict(ytdlp_bin.os.environ, {"LOCALAPPDATA": carpeta}):
                self.assertEqual(
                    Path(carpeta) / ytdlp_bin.SUBDIRECTORIO_DATOS / "yt-dlp.exe",
                    ytdlp_bin._ruta_actualizada(),
                )

    def test_ruta_actualizada_usa_carpeta_del_usuario_sin_localappdata(self):
        with tempfile.TemporaryDirectory() as carpeta, \
                patch.dict(ytdlp_bin.os.environ, {}, clear=True), \
                patch.object(Path, "home", return_value=Path(carpeta)):
            self.assertEqual(
                Path.home() / ytdlp_bin.SUBDIRECTORIO_DATOS / "yt-dlp.exe",
                ytdlp_bin._ruta_actualizada(),
            )

    def test_descarga_rechaza_url_que_no_es_https(self):
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "yt-dlp.exe"
            with patch.object(ytdlp_bin, "_descargar_archivo") as descargar:
                resultado = ytdlp_bin.descargar_ytdlp("http://ejemplo", "a" * 64, destino)
            self.assertFalse(resultado.correcta)
            descargar.assert_not_called()
            self.assertFalse(destino.exists())

    def test_descarga_con_firma_incorrecta_conserva_destino_y_borra_temporal(self):
        contenido = b"binario nuevo"
        with tempfile.TemporaryDirectory() as carpeta:
            carpeta = Path(carpeta)
            destino = carpeta / "yt-dlp.exe"
            destino.write_bytes(b"binario anterior")

            def escribir(_url, temporal):
                temporal.write_bytes(contenido)

            with patch.object(ytdlp_bin, "_descargar_archivo", side_effect=escribir):
                resultado = ytdlp_bin.descargar_ytdlp("https://ejemplo", "0" * 64, destino)

            self.assertFalse(resultado.correcta)
            self.assertEqual(b"binario anterior", destino.read_bytes())
            self.assertEqual([], list(carpeta.glob(".yt-dlp-*.tmp")))

    def test_descarga_rechaza_firma_diferente_en_el_ultimo_caracter(self):
        contenido = b"binario nuevo"
        firma = hashlib.sha256(contenido).hexdigest()
        firma_alterada = firma[:-1] + ("0" if firma[-1] != "0" else "1")
        with tempfile.TemporaryDirectory() as carpeta:
            carpeta = Path(carpeta)
            destino = carpeta / "yt-dlp.exe"
            destino.write_bytes(b"binario anterior")

            def escribir(_url, temporal):
                temporal.write_bytes(contenido)

            with patch.object(ytdlp_bin, "_descargar_archivo", side_effect=escribir):
                resultado = ytdlp_bin.descargar_ytdlp(
                    "https://ejemplo", firma_alterada, destino
                )

            self.assertFalse(resultado.correcta)
            self.assertEqual(b"binario anterior", destino.read_bytes())
            self.assertEqual([], list(carpeta.glob(".yt-dlp-*.tmp")))

    def test_descarga_con_firma_correcta_reemplaza_destino(self):
        contenido = b"binario nuevo"
        firma = hashlib.sha256(contenido).hexdigest()
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "yt-dlp.exe"

            def escribir(_url, temporal):
                temporal.write_bytes(contenido)

            with patch.object(ytdlp_bin, "_descargar_archivo", side_effect=escribir):
                resultado = ytdlp_bin.descargar_ytdlp("https://ejemplo", firma, destino)

            self.assertTrue(resultado.correcta)
            self.assertEqual(contenido, destino.read_bytes())



if __name__ == "__main__":
    unittest.main()
