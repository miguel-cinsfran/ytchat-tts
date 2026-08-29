from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import ytdlp_bin


class PruebasDescargarAudio(unittest.TestCase):

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1])
        self.destino = Path(self.temporal.name) / "audio.webm"

    def tearDown(self):
        self.temporal.cleanup()

    def _respuesta(self, codigo=0):
        return mock.Mock(returncode=codigo)

    def test_sin_ejecutable_no_inicia_subproceso(self):
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value=None), \
                mock.patch.object(ytdlp_bin.subprocess, "run") as ejecutar:
            self.assertFalse(ytdlp_bin.descargar_audio("A" * 11, self.destino))
        ejecutar.assert_not_called()

    def test_archivo_utilizable_devuelve_verdadero(self):
        def ejecutar(*_args, **_kwargs):
            self.destino.write_bytes(b"x" * ytdlp_bin.TAMANIO_MINIMO)
            return self._respuesta()
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "run", side_effect=ejecutar):
            self.assertTrue(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_archivo_ausente_devuelve_falso(self):
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "run", return_value=self._respuesta()):
            self.assertFalse(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_archivo_corto_devuelve_falso(self):
        self.destino.write_bytes(b"x" * (ytdlp_bin.TAMANIO_MINIMO - 1))
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "run", return_value=self._respuesta()):
            self.assertFalse(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_error_del_proceso_devuelve_falso(self):
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "run", return_value=self._respuesta(1)):
            self.assertFalse(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_timeout_no_se_propaga(self):
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "run",
                                  side_effect=subprocess.TimeoutExpired("yt-dlp", 90)):
            self.assertFalse(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_invocacion_oculta_la_consola(self):
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "run", return_value=self._respuesta()) as ejecutar:
            ytdlp_bin.descargar_audio("A" * 11, self.destino)
        self.assertEqual(getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         ejecutar.call_args.kwargs["creationflags"])


if __name__ == "__main__":
    unittest.main()
