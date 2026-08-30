from pathlib import Path
import subprocess
import tempfile
import time
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

    def _proceso(self, codigo=0, lineas=()):
        proceso = mock.Mock()
        proceso.stdout = lineas
        proceso.wait.return_value = codigo
        proceso.poll.return_value = codigo
        proceso.returncode = codigo
        proceso.kill = mock.Mock()
        return proceso

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
                mock.patch.object(ytdlp_bin.subprocess, "Popen",
                                  side_effect=lambda *_a, **_k: (ejecutar(), self._proceso())[1]):
            self.assertTrue(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_archivo_ausente_devuelve_falso(self):
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "Popen", return_value=self._proceso()):
            self.assertFalse(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_archivo_corto_devuelve_falso(self):
        self.destino.write_bytes(b"x" * (ytdlp_bin.TAMANIO_MINIMO - 1))
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "Popen", return_value=self._proceso()):
            self.assertFalse(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_error_del_proceso_devuelve_falso(self):
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "Popen", return_value=self._proceso(1)):
            self.assertFalse(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_timeout_no_se_propaga(self):
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "Popen",
                                  side_effect=subprocess.TimeoutExpired("yt-dlp", 90)):
            self.assertFalse(ytdlp_bin.descargar_audio("A" * 11, self.destino))

    def test_invocacion_oculta_la_consola(self):
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "Popen", return_value=self._proceso()) as ejecutar:
            ytdlp_bin.descargar_audio("A" * 11, self.destino)
        self.assertEqual(getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         ejecutar.call_args.kwargs["creationflags"])

    def test_progreso_entrega_porcentajes_enteros(self):
        lineas = (
            "PROG 10 100 NA 1 1 audio.webm\n",
            "PROG 80 100 NA 1 1 audio.webm\n",
        )
        avisos = []
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "Popen",
                                  return_value=self._proceso(1, lineas)):
            ytdlp_bin.descargar_audio("A" * 11, self.destino, avisos.append)
        self.assertEqual([10, 80], avisos)

    def test_argumentos_sin_quiet_con_progreso(self):
        # Verifica que no se use --quiet y sí --newline y --progress-template.
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "Popen",
                                  return_value=self._proceso()) as crear:
            ytdlp_bin.descargar_audio("A" * 11, self.destino)
        argumentos = crear.call_args[0][0]
        self.assertNotIn("--quiet", argumentos)
        self.assertIn("--newline", argumentos)
        self.assertIn("--progress-template", argumentos)
        self.assertIn("--no-warnings", argumentos)

    def test_tope_corta_descarga_colgada_sin_salida(self):
        # Proceso que no imprime nada y no termina: debe cortarse por tope.
        class _SalidaBloqueada:
            def __iter__(self):
                return self

            def __next__(self):
                time.sleep(10)
                return "nunca termina"

        proceso = mock.Mock()
        proceso.stdout = _SalidaBloqueada()
        proceso.poll.return_value = None
        proceso.returncode = None
        proceso.kill = mock.Mock()
        # wait debe no bloquear indefinidamente; simulamos que tras kill termina
        def _espera(*_a, **_kw):
            return 0
        proceso.wait.side_effect = _espera
        with mock.patch.object(ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp.exe"), \
                mock.patch.object(ytdlp_bin.subprocess, "Popen", return_value=proceso):
            inicio = time.monotonic()
            resultado = ytdlp_bin.descargar_audio("A" * 11, self.destino, tope_segundos=1)
            duracion = time.monotonic() - inicio
        self.assertFalse(resultado)
        self.assertLess(duracion, 3)
        proceso.kill.assert_called()


if __name__ == "__main__":
    unittest.main()
