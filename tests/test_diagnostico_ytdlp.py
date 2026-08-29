from __future__ import annotations

import unittest
from unittest import mock

import diagnostico


class TestVersionYtdlpDiagnostico(unittest.TestCase):
    def test_registrar_entorno_escribe_tambien_en_archivo_de_fallos(self):
        archivo = mock.Mock()
        anterior = diagnostico._ARCHIVO_FALLOS
        diagnostico._ARCHIVO_FALLOS = archivo
        try:
            with mock.patch.object(diagnostico.ytdlp_bin, "ruta_ytdlp", return_value=None), \
                    mock.patch.object(diagnostico, "_version_paquete", return_value=(None, "falta")), \
                    mock.patch.object(diagnostico, "_placa_video", return_value=(None, "falta")), \
                    mock.patch.object(diagnostico, "_lector_activo", return_value=(None, "falta")), \
                    mock.patch.object(diagnostico, "componer_volcado_entorno", return_value="texto"), \
                    mock.patch.object(diagnostico, "obtener_logger") as obtener:
                diagnostico.registrar_entorno("2.0.0")
            obtener.return_value.info.assert_called_once_with("%s", "texto")
            archivo.write.assert_called_once_with("texto\n")
            archivo.flush.assert_called_once_with()
        finally:
            diagnostico._ARCHIVO_FALLOS = anterior

    def test_registrar_entorno_en_hilo_crea_y_arranca_hilo(self):
        hilo = mock.Mock()
        with mock.patch.object(diagnostico, "crear_hilo", return_value=hilo) as crear:
            diagnostico.registrar_entorno_en_hilo("2.0.0")
        crear.assert_called_once_with(
            diagnostico.registrar_entorno, "Entorno", args=("2.0.0",))
        hilo.start.assert_called_once_with()

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
