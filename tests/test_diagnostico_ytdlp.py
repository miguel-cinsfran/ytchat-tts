from __future__ import annotations

import unittest
from unittest import mock

import diagnostico


class TestVersionYtdlpDiagnostico(unittest.TestCase):
    def test_usa_la_version_del_ejecutable(self):
        with mock.patch.object(diagnostico.ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp"), \
                mock.patch.object(diagnostico.ytdlp_bin, "version_ytdlp", return_value="2026.08.19") as version, \
                mock.patch.object(diagnostico, "_version_paquete", return_value=("vieja", None)), \
                mock.patch.object(diagnostico, "_placa_video", return_value=(None, None)), \
                mock.patch.object(diagnostico, "_lector_activo", return_value=(None, None)), \
                mock.patch.object(diagnostico, "componer_volcado_entorno", return_value="texto"):
            diagnostico.registrar_entorno("2.0.0")
        version.assert_called_once_with("yt-dlp")

    def test_sin_ejecutable_no_intenta_leer_version(self):
        with mock.patch.object(diagnostico.ytdlp_bin, "ruta_ytdlp", return_value=None), \
                mock.patch.object(diagnostico.ytdlp_bin, "version_ytdlp") as version, \
                mock.patch.object(diagnostico, "_placa_video", return_value=(None, None)), \
                mock.patch.object(diagnostico, "_lector_activo", return_value=(None, None)), \
                mock.patch.object(diagnostico, "componer_volcado_entorno", return_value="texto"):
            diagnostico.registrar_entorno("2.0.0")
        version.assert_not_called()


if __name__ == "__main__":
    unittest.main()
