"""Pruebas de la consulta de información de vídeos."""

import sys
import types
import unittest
from unittest import mock

import main


class _YoutubeDL:
    def __init__(self, opciones):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, *args, **kwargs):
        return {"title": "Vídeo de prueba", "live_status": "not_live"}


class TestObtenerInfoVideo(unittest.TestCase):

    def test_metadatos_directo_prefiere_espectadores_actuales(self):
        meta = main._metadatos_desde_ytdlp({
            "live_status": "is_live", "view_count": 3000,
            "concurrent_view_count": 30,
        })
        self.assertEqual(meta["vistas"], 30)

    def test_metadatos_video_normal_usa_vistas_acumuladas(self):
        meta = main._metadatos_desde_ytdlp({
            "live_status": "not_live", "view_count": 3000,
            "concurrent_view_count": 30,
        })
        self.assertEqual(meta["vistas"], 3000)

    def test_metadatos_directo_sin_contador_actual_recurre_a_vistas(self):
        meta = main._metadatos_desde_ytdlp({
            "live_status": "is_live", "view_count": 3000,
        })
        self.assertEqual(meta["vistas"], 3000)

    def test_obtener_info_video_con_programa_usa_titulo_y_tipo(self):
        info = {"title": "Vídeo del programa", "live_status": "is_live"}
        with mock.patch.object(main.ytdlp_bin, "info_video", return_value=info), \
                mock.patch.dict(sys.modules, {"yt_dlp": None}), \
                mock.patch.object(main, "_descargar_watch") as respaldo:
            titulo, tipo, _ = main.obtener_info_video("A" * 11)

        self.assertEqual((titulo, tipo),
                         ("Vídeo del programa", main.deteccion.LIVE))
        respaldo.assert_not_called()

    def test_obtener_info_video_sin_programa_usa_el_modulo(self):
        modulo = types.SimpleNamespace(YoutubeDL=_YoutubeDL)
        with mock.patch.object(main.ytdlp_bin, "info_video", return_value=None), \
                mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main, "_descargar_watch") as respaldo:
            titulo, tipo, _ = main.obtener_info_video("A" * 11)

        self.assertEqual((titulo, tipo), ("Vídeo de prueba", main.deteccion.VOD))
        respaldo.assert_not_called()

    def test_modulo_utilizable_no_llama_al_ejecutable(self):
        modulo = types.SimpleNamespace(YoutubeDL=_YoutubeDL)
        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main.ytdlp_bin, "info_video") as ejecutable, \
                mock.patch.object(main, "_descargar_watch") as respaldo:
            titulo, tipo, _ = main.obtener_info_video("A" * 11)

        self.assertEqual((titulo, tipo), ("Vídeo de prueba", main.deteccion.VOD))
        ejecutable.assert_not_called()
        respaldo.assert_not_called()

    def test_modulo_con_excepcion_usa_el_ejecutable(self):
        info = {"title": "Vídeo del ejecutable", "live_status": "is_live"}
        modulo = types.SimpleNamespace(YoutubeDL=mock.Mock(
            side_effect=RuntimeError("fallo del módulo")))
        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main.ytdlp_bin, "info_video", return_value=info), \
                mock.patch.object(main, "_descargar_watch") as respaldo:
            titulo, tipo, _ = main.obtener_info_video("A" * 11)

        self.assertEqual((titulo, tipo),
                         ("Vídeo del ejecutable", main.deteccion.LIVE))
        respaldo.assert_not_called()

    def test_modulo_y_ejecutable_fallan_y_usa_scraping_y_api(self):
        modulo = types.SimpleNamespace(YoutubeDL=mock.Mock(
            side_effect=RuntimeError("fallo del módulo")))
        html = '<title>Vídeo de respaldo - YouTube</title>'
        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main.ytdlp_bin, "info_video", return_value=None), \
                mock.patch.object(main, "_descargar_watch", return_value=html), \
                mock.patch.object(main, "_clasificar_por_api",
                                  return_value=main.deteccion.VOD) as api:
            titulo, tipo, _ = main.obtener_info_video("A" * 11)

        self.assertEqual((titulo, tipo), ("Vídeo de respaldo", main.deteccion.VOD))
        api.assert_called_once_with("A" * 11)

    def test_fallo_de_yt_dlp_llega_al_mensaje(self):
        motivo = "Sign in to confirm you're not a bot"
        modulo = types.SimpleNamespace(YoutubeDL=mock.Mock(
            side_effect=RuntimeError(motivo)))

        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main.ytdlp_bin, "info_video", return_value=None), \
                mock.patch.object(main, "_descargar_watch", return_value=""):
            _, _, metadatos = main.obtener_info_video("A" * 11)

        self.assertEqual(
            metadatos["fallo"],
            "El servicio está recibiendo demasiadas solicitudes. "
            "Vuelve a intentarlo en unos minutos.")

    def test_fallo_de_descarga_html_llega_al_mensaje(self):
        modulo = types.SimpleNamespace(YoutubeDL=mock.Mock(side_effect=RuntimeError(
            "Sign in to confirm you're not a bot")))

        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main.ytdlp_bin, "info_video", return_value=None), \
                mock.patch.object(
                    main.urllib.request, "urlopen",
                    side_effect=RuntimeError("HTTP Error 429: Too Many Requests")), \
                mock.patch.object(
                    main.avisos_red, "mensaje_de_fallo",
                    side_effect=lambda motivo: (
                        "Mensaje que corresponde a los dos fallos"
                        if "Sign in to confirm you're not a bot" in motivo
                        and "HTTP Error 429: Too Many Requests" in motivo
                        else "Mensaje incompleto")):
            _, _, metadatos = main.obtener_info_video("A" * 11)

        self.assertEqual(
            metadatos["fallo"],
            "Mensaje que corresponde a los dos fallos")

    def test_respaldo_con_titulo_no_anuncia_fallo(self):
        modulo = types.SimpleNamespace(YoutubeDL=mock.Mock(side_effect=RuntimeError(
            "Sign in to confirm you're not a bot")))
        html = '<title>Vídeo de respaldo - YouTube</title>'

        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main.ytdlp_bin, "info_video", return_value=None), \
                mock.patch.object(main, "_descargar_watch", return_value=html):
            titulo, _, metadatos = main.obtener_info_video("A" * 11)

        self.assertEqual(titulo, "Vídeo de respaldo")
        self.assertNotIn("fallo", metadatos)

    def test_fallo_de_los_dos_caminos_va_a_los_metadatos(self):
        modulo = types.SimpleNamespace(YoutubeDL=mock.Mock(side_effect=RuntimeError(
            "Sign in to confirm you're not a bot")))

        def falla_watch(video_id, timeout=8.0, al_fallar=None):
            al_fallar(RuntimeError("HTTP Error 429: Too Many Requests"))
            return ""

        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main.ytdlp_bin, "info_video", return_value=None), \
                mock.patch.object(main, "_descargar_watch", side_effect=falla_watch):
            titulo, tipo, metadatos = main.obtener_info_video("A" * 11)

        self.assertEqual((titulo, tipo), ("", main.deteccion.DESCONOCIDO))
        self.assertEqual(
            metadatos["fallo"],
            "El servicio está recibiendo demasiadas solicitudes. "
            "Vuelve a intentarlo en unos minutos.")

    def test_consulta_exitosa_no_agrega_fallo(self):
        modulo = types.SimpleNamespace(YoutubeDL=_YoutubeDL)
        with mock.patch.dict(sys.modules, {"yt_dlp": modulo}), \
                mock.patch.object(main, "_descargar_watch") as respaldo:
            titulo, tipo, metadatos = main.obtener_info_video("A" * 11)

        self.assertEqual(titulo, "Vídeo de prueba")
        self.assertEqual(tipo, main.deteccion.VOD)
        self.assertNotIn("fallo", metadatos)
        respaldo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
