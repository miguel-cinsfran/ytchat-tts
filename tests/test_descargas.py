"""Tests del módulo puro `descargas` (gestor de descargas con yt-dlp).

Estos tests son PURE-PYTHON: parchean `descargas.yt_dlp` con mocks para no
necesitar la librería real ni conexión a internet. El módulo `descargas` se
importa sin `wx`, así que corren tanto en Windows como en Linux/WSL.
"""
from __future__ import annotations

import threading
import unittest
from unittest import mock

import descargas
from descargas import (
    DownloadCancelled,
    GestorDescargas,
    ItemDescarga,
    analizar_url,
    construir_outtmpl,
    descargar,
    formato_a_ydl,
    tiene_ffmpeg,
)


# ── formato_a_ydl: selector que se pasa a YoutubeDL ──────────────────────────

class TestFormatoAYdl(unittest.TestCase):
    """El selector que pasamos a YoutubeDL define cómo se combinan los streams.

    mp4 y webm piden el mejor vídeo de esa extensión combinado con el mejor
    audio compatible (con fallback). mp3 y m4a piden solo el mejor audio y
    dejan que el postprocesador FFmpegExtractAudio haga la conversión."""

    def test_mp4_prefiere_mp4_y_combina_video_audio(self):
        s = formato_a_ydl("mp4", 192)
        self.assertIn("mp4", s)
        # Combina vídeo + audio (no entrega solo audio):
        self.assertIn("bestvideo", s)
        self.assertIn("bestaudio", s)
        # El primer intento es mp4 + m4a (compatible contenedor):
        self.assertIn("bestvideo[ext=mp4]+bestaudio[ext=m4a]", s)

    def test_webm_prefiere_webm_y_combina_video_audio(self):
        s = formato_a_ydl("webm", 256)
        self.assertIn("webm", s)
        self.assertIn("bestvideo[ext=webm]+bestaudio[ext=webm]", s)

    def test_mp3_solo_audio(self):
        # mp3 -> se extrae el audio y FFmpegExtractAudio lo convierte a mp3.
        self.assertEqual(formato_a_ydl("mp3", 192), "bestaudio")

    def test_m4a_solo_audio(self):
        # m4a -> solo audio, lo convierte el postprocesador.
        self.assertEqual(formato_a_ydl("m4a", 320), "bestaudio")

    def test_formato_desconocido_cae_a_best(self):
        # Si el usuario escribió otra cosa, devolvemos el mejor disponible.
        self.assertEqual(formato_a_ydl("xyz", 192), "best")

    def test_formato_normaliza_mayusculas(self):
        # "MP4" en config debe funcionar igual que "mp4".
        self.assertIn("mp4", formato_a_ydl("MP4", 192))


# ── construir_outtmpl: plantilla de nombre de archivo ───────────────────────

class TestConstruirOuttmpl(unittest.TestCase):
    """Une la carpeta con la plantilla. Con enumerar=True yt-dlp prefijará
    01_, 02_... si es playlist."""

    def test_sin_enumerar_no_lleva_playlist_index(self):
        out = construir_outtmpl({"carpeta": "/tmp/Descargas"}, enumerar=False)
        self.assertNotIn("playlist_index", out)
        # La plantilla siempre lleva título, id y extensión.
        self.assertIn("%(title)s", out)
        self.assertIn("%(id)s", out)
        self.assertIn("%(ext)s", out)

    def test_sin_enumerar_incluye_carpeta(self):
        out = construir_outtmpl({"carpeta": "/tmp/Descargas"}, enumerar=False)
        self.assertIn("Descargas", out)
        self.assertIn("/tmp", out)

    def test_con_enumerar_lleva_playlist_index(self):
        out = construir_outtmpl({"carpeta": "/tmp/Descargas"}, enumerar=True)
        self.assertIn("playlist_index", out)
        self.assertIn("%(title)s", out)

    def test_sin_carpeta_usa_appdir_descargas(self):
        out = construir_outtmpl({}, enumerar=False)
        # La ruta por defecto (app_dir()/"Descargas") debe aparecer.
        self.assertIn("Descargas", out)

    def test_carpeta_windows_se_conserva(self):
        out = construir_outtmpl({"carpeta": r"C:\Users\foo\Descargas"}, enumerar=False)
        self.assertIn("Descargas", out)


# ── analizar_url: detecta vídeo vs playlist con su propio YoutubeDL ──────────

class TestAnalizarUrl(unittest.TestCase):
    """analizar_url crea su PROPIA instancia de YoutubeDL (no acopla con
    main.obtener_info_video ni reproductor._info_video). Si yt_dlp no está
    instalado, devuelve error."""

    def test_video(self):
        fake_ydl = mock.MagicMock()
        fake_ydl.extract_info.return_value = {
            "_type": "video", "id": "abc12345678", "title": "Mi vídeo",
        }
        with mock.patch.object(descargas, "yt_dlp") as ytdlp:
            ytdlp.YoutubeDL.return_value.__enter__.return_value = fake_ydl
            res = analizar_url("https://www.youtube.com/watch?v=abc12345678")
        self.assertEqual(res["tipo"], "video")
        self.assertEqual(res["id"], "abc12345678")
        self.assertEqual(res["titulo"], "Mi vídeo")
        self.assertEqual(res["cuenta"], 1)

    def test_playlist_con_varias_entradas(self):
        fake_ydl = mock.MagicMock()
        fake_ydl.extract_info.return_value = {
            "_type": "playlist", "id": "PL123", "title": "Mi playlist",
            "entries": [{"id": f"v{i}"} for i in range(5)],
        }
        with mock.patch.object(descargas, "yt_dlp") as ytdlp:
            ytdlp.YoutubeDL.return_value.__enter__.return_value = fake_ydl
            res = analizar_url("https://www.youtube.com/playlist?list=PL123")
        self.assertEqual(res["tipo"], "playlist")
        self.assertEqual(res["id"], "PL123")
        self.assertEqual(res["titulo"], "Mi playlist")
        self.assertEqual(res["cuenta"], 5)

    def test_sin_ytdlp_devuelve_error(self):
        with mock.patch.object(descargas, "yt_dlp", None):
            res = analizar_url("https://www.youtube.com/watch?v=abc")
        self.assertEqual(res["tipo"], "error")
        self.assertIn(res["id"], ("",))   # sin id
        self.assertEqual(res["cuenta"], 0)

    def test_extract_info_falla_devuelve_error(self):
        fake_ydl = mock.MagicMock()
        fake_ydl.extract_info.side_effect = RuntimeError("URL inválida")
        with mock.patch.object(descargas, "yt_dlp") as ytdlp:
            ytdlp.YoutubeDL.return_value.__enter__.return_value = fake_ydl
            res = analizar_url("https://www.youtube.com/watch?v=abc")
        self.assertEqual(res["tipo"], "error")
        self.assertIn("inválida", res["mensaje"])


# ── cancelar descarga ───────────────────────────────────────────────────────

class TestCancelarDescarga(unittest.TestCase):
    """Si el cancel_event está activo cuando se invoca el progress hook, la
    descarga termina con estado 'cancelado' (no se mata el hilo)."""

    def test_cancel_event_antes_de_empezar_termina_en_cancelado(self):
        cancel_event = threading.Event()
        cancel_event.set()   # ya está marcado al arrancar
        estados: list = []

        with mock.patch.object(descargas, "yt_dlp") as ytdlp, \
                mock.patch.object(descargas, "tiene_ffmpeg", return_value=True):
            fake_ydl = mock.MagicMock()

            def _fake_download(urls):
                # Sacamos la progress_hook real de los opts con los que se
                # construyó YoutubeDL y la invocamos para simular el callback.
                args, kwargs = ytdlp.YoutubeDL.call_args
                opts = args[0] if args else kwargs.get("params", {})
                for hook in opts.get("progress_hooks", []):
                    hook({"status": "downloading", "downloaded_bytes": 0,
                          "total_bytes": 100, "filename": "x"})
                return []

            fake_ydl.download.side_effect = _fake_download
            ytdlp.YoutubeDL.return_value.__enter__.return_value = fake_ydl

            descargar(
                "https://example.com/v",
                {"formato": "mp4", "bitrate": 192, "carpeta": "/tmp",
                 "enumerar": False},
                lambda *_a, **_k: None,
                lambda est, msg="": estados.append((est, msg)),
                cancel_event,
            )

        # El último estado reportado debe ser "cancelado".
        self.assertTrue(estados, "no se llamó estado_cb")
        self.assertEqual(estados[-1][0], "cancelado")

    def test_sin_ytdlp_devuelve_error_y_no_relevanta_excepcion(self):
        # Si yt_dlp falta, estado_cb("error", ...) y return limpio: el hilo
        # de la GUI NO se mata.
        estados: list = []
        with mock.patch.object(descargas, "yt_dlp", None):
            descargar("https://example.com/v", {"formato": "mp4"},
                      lambda *_a, **_k: None,
                      lambda est, msg="": estados.append((est, msg)),
                      threading.Event())
        self.assertEqual(estados[-1][0], "error")


# ── GestorDescargas: cola de ítems ───────────────────────────────────────────

class TestGestorDescargas(unittest.TestCase):
    """La cola: cada ítem corre en su propio hilo (daemon). cancelar() marca
    el event; el hook lo ve y lanza DownloadCancelled."""

    def _opciones(self) -> dict:
        return {"formato": "mp4", "bitrate": 192, "carpeta": "/tmp"}

    def test_encolar_devuelve_id_y_almacena_item(self):
        g = GestorDescargas(self._opciones())
        with mock.patch.object(descargas, "yt_dlp", None):
            id_ = g.encolar("https://example.com/v",
                            lambda *_a, **_k: None,
                            lambda *_a, **_k: None)
        it = g.obtener(id_)
        self.assertIsNotNone(it)
        self.assertEqual(it.url, "https://example.com/v")
        # El ítem aparece en la lista.
        self.assertIn(id_, [i.id for i in g.lista()])

    def test_cancelar_marca_el_evento_del_item(self):
        g = GestorDescargas(self._opciones())
        with mock.patch.object(descargas, "yt_dlp", None):
            id_ = g.encolar("https://example.com/v",
                            lambda *_a, **_k: None,
                            lambda *_a, **_k: None)
        ev = g._eventos[id_]
        self.assertFalse(ev.is_set())
        g.cancelar(id_)
        self.assertTrue(ev.is_set())

    def test_cancelar_id_inexistente_no_falla(self):
        g = GestorDescargas(self._opciones())
        # No debe lanzar.
        g.cancelar("no-existe")

    def test_obtener_id_inexistente_devuelve_none(self):
        g = GestorDescargas(self._opciones())
        self.assertIsNone(g.obtener("no-existe"))

    def test_set_opciones_reemplaza_la_configuracion(self):
        g = GestorDescargas(self._opciones())
        g.set_opciones({"formato": "mp3", "bitrate": 256, "carpeta": "/x"})
        self.assertEqual(g._opciones["formato"], "mp3")
        self.assertEqual(g._opciones["carpeta"], "/x")


# ── tiene_ffmpeg: lookup en app_dir (frozen) o PATH ─────────────────────────

class TestTieneFfmpeg(unittest.TestCase):
    def test_devuelve_bool(self):
        self.assertIsInstance(tiene_ffmpeg(), bool)


class TestFfmpegFaltante(unittest.TestCase):
    """Si falta ffmpeg, descargar() debe informar un error CLARO (no uno
    genérico de yt-dlp), para que el usuario ciego sepa qué falta."""

    def test_sin_ffmpeg_devuelve_error_claro(self):
        estados: list = []
        with mock.patch.object(descargas, "yt_dlp") as ytdlp, \
                mock.patch.object(descargas, "tiene_ffmpeg", return_value=False):
            ytdlp.YoutubeDL.return_value.__enter__.return_value = mock.MagicMock()
            descargar("https://example.com/v", {"formato": "mp4"},
                      lambda *_a, **_k: None,
                      lambda est, msg="": estados.append((est, msg)),
                      threading.Event())
        self.assertTrue(estados)
        self.assertEqual(estados[-1][0], "error")
        self.assertIn("ffmpeg", estados[-1][1].lower())


if __name__ == "__main__":
    unittest.main()
