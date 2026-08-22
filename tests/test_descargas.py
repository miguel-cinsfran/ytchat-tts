from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from unittest import mock

import descargas
from descargas import (
    GestorDescargas,
    INTERVALO_PROGRESO_S,
    analizar_url,
    argumentos_descarga,
    construir_outtmpl,
    debe_emitir_progreso,
    descargar,
    formato_a_ydl,
    tiene_ffmpeg,
)


class TestDebeEmitirProgreso(unittest.TestCase):
    def test_primer_aviso(self): self.assertTrue(debe_emitir_progreso(None, 10, 0))
    def test_aviso_final(self): self.assertTrue(debe_emitir_progreso(10, 10.01, 100))
    def test_aviso_al_intervalo(self): self.assertTrue(debe_emitir_progreso(10, 10.5, 40))
    def test_aviso_dentro_del_intervalo(self): self.assertFalse(debe_emitir_progreso(10, 10.01, 40))


class TestFormatoAYdl(unittest.TestCase):
    def test_mp4(self):
        self.assertIn("bestvideo[ext=mp4]+bestaudio[ext=m4a]", formato_a_ydl("mp4", 192))
    def test_webm(self): self.assertIn("bestvideo[ext=webm]", formato_a_ydl("webm", 256))
    def test_mp3(self): self.assertEqual(formato_a_ydl("mp3", 192), "bestaudio")
    def test_m4a(self): self.assertEqual(formato_a_ydl("m4a", 320), "bestaudio")
    def test_desconocido(self): self.assertEqual(formato_a_ydl("xyz", 192), "best")
    def test_mayusculas(self): self.assertIn("mp4", formato_a_ydl("MP4", 192))


class TestConstruirOuttmpl(unittest.TestCase):
    def test_sin_enumerar(self):
        salida = construir_outtmpl({"carpeta": "/tmp/Descargas"}, False)
        self.assertNotIn("playlist_index", salida)
        self.assertIn("%(title)s", salida)
    def test_incluye_carpeta(self):
        self.assertEqual(Path(construir_outtmpl({"carpeta": "/tmp/Descargas"}, False)).parent,
                         Path("/tmp/Descargas"))
    def test_con_enumerar(self):
        self.assertIn("playlist_index", construir_outtmpl({"carpeta": "/tmp"}, True))
    def test_carpeta_por_defecto(self): self.assertIn("Descargas", construir_outtmpl({}, False))
    def test_carpeta_windows(self): self.assertIn("Descargas", construir_outtmpl({"carpeta": r"C:\Users\foo\Descargas"}, False))


class TestAnalizarUrl(unittest.TestCase):
    def resultado(self, datos, codigo=0, error=""):
        return mock.Mock(stdout=json.dumps(datos), stderr=error, returncode=codigo)

    def test_video(self):
        with mock.patch.object(descargas.ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp"), \
                mock.patch.object(descargas.subprocess, "run", return_value=self.resultado({
                    "_type": "video", "id": "abc", "title": "Mi vídeo"})):
            res = analizar_url("https://example.com/v")
        self.assertEqual((res["tipo"], res["id"], res["cuenta"]), ("video", "abc", 1))

    def test_playlist(self):
        datos = {"_type": "playlist", "id": "PL", "title": "Lista", "entries": [{"id": "1"}]}
        with mock.patch.object(descargas.ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp"), \
                mock.patch.object(descargas.subprocess, "run", return_value=self.resultado(datos)):
            res = analizar_url("https://example.com/lista")
        self.assertEqual((res["tipo"], res["cuenta"]), ("playlist", 1))

    def test_sin_programa(self):
        with mock.patch.object(descargas.ytdlp_bin, "ruta_ytdlp", return_value=None):
            res = analizar_url("https://example.com/v")
        self.assertEqual(res["tipo"], "error")

    def test_fallo_del_programa(self):
        with mock.patch.object(descargas.ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp"), \
                mock.patch.object(descargas.subprocess, "run", return_value=self.resultado({}, 1, "URL inválida")):
            res = analizar_url("https://example.com/v")
        self.assertIn("inválida", res["mensaje"])


class TestArgumentosDescarga(unittest.TestCase):
    def opciones(self, formato): return {"formato": formato, "bitrate": 256, "carpeta": "/tmp"}
    def test_mp3_lleva_conversion(self):
        args = argumentos_descarga("https://example.com/v", self.opciones("mp3"), False)
        self.assertIn("-x", args); self.assertIn("mp3", args); self.assertIn("256K", args)
    def test_mp4_no_lleva_conversion(self):
        args = argumentos_descarga("https://example.com/v", self.opciones("mp4"), False)
        self.assertNotIn("-x", args); self.assertNotIn("--audio-format", args)
        self.assertNotIn("--audio-quality", args)
    def test_no_lleva_quiet(self):
        self.assertNotIn("--quiet", argumentos_descarga("https://example.com/v", self.opciones("mp4"), False))
    def test_url_al_final(self):
        self.assertEqual(argumentos_descarga("-url", self.opciones("mp4"), False)[-2:],
                         ["--", "-url"])
    def test_lleva_plantilla_y_salida(self):
        args = argumentos_descarga("url", self.opciones("mp4"), True)
        self.assertIn("--progress-template", args); self.assertIn("-o", args)
    def test_usa_ruta_de_ffmpeg_recibida(self):
        args = argumentos_descarga("url", self.opciones("mp3"), False,
                                   r"C:\ffmpeg")
        indice = args.index("--ffmpeg-location")
        self.assertEqual(args[indice:indice + 2], ["--ffmpeg-location", r"C:\ffmpeg"])

    def test_sin_empaquetar_no_agrega_ffmpeg(self):
        args = argumentos_descarga("url", self.opciones("mp3"), False)
        self.assertNotIn("--ffmpeg-location", args)

    def test_empaquetado_usa_directorio_de_la_app(self):
        with mock.patch.object(descargas.sys, "frozen", True, create=True), \
                mock.patch.object(descargas, "app_dir", return_value=Path(r"C:\app")):
            args = argumentos_descarga("url", self.opciones("mp3"), False)
        indice = args.index("--ffmpeg-location")
        self.assertEqual(args[indice + 1], r"C:\app")


class TestDescargar(unittest.TestCase):
    def proceso(self, lineas):
        proceso = mock.MagicMock()
        proceso.returncode = 0
        proceso.stdout.readline.side_effect = [*lineas, ""]
        return proceso

    def preparar(self, proceso):
        return mock.patch.object(descargas.ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp"), \
            mock.patch.object(descargas, "tiene_ffmpeg", return_value=True), \
            mock.patch.object(descargas.subprocess, "Popen", return_value=proceso)

    def test_pasa_progreso_al_callback(self):
        proceso = self.proceso(["PROG 5 10 NA 2 3 nombre con espacios.mp4\n"])
        progresos = []; estados = []
        with self.preparar(proceso)[0], self.preparar(proceso)[1], self.preparar(proceso)[2]:
            descargar("url", {"formato": "mp4"}, lambda *a: progresos.append(a),
                      lambda *a: estados.append(a), threading.Event())
        self.assertEqual(progresos, [(50.0, 2.0, 3, "nombre con espacios.mp4")])
        self.assertEqual(estados[-1], ("completado", ""))

    def test_ignora_lineas_no_progreso(self):
        proceso = self.proceso(["[youtube] Extracting URL\n"])
        callback = mock.Mock()
        with self.preparar(proceso)[0], self.preparar(proceso)[1], self.preparar(proceso)[2]:
            descargar("url", {"formato": "mp4"}, callback, lambda *a: None, threading.Event())
        callback.assert_not_called()

    def test_frena_progresos_seguidos(self):
        lineas = ["PROG 5 10 NA 2 3 nombre.mp4\n"] * 20
        proceso = self.proceso(lineas)
        progreso = mock.Mock()
        with self.preparar(proceso)[0], self.preparar(proceso)[1], \
                self.preparar(proceso)[2], \
                mock.patch.object(descargas.time, "monotonic", return_value=10):
            descargar("url", {"formato": "mp4"}, progreso, lambda *a: None,
                      threading.Event())
        self.assertLess(progreso.call_count, len(lineas))

    def test_cancelar_mata_el_proceso(self):
        proceso = self.proceso([]); evento = threading.Event(); evento.set(); estados = []
        with self.preparar(proceso)[0], self.preparar(proceso)[1], self.preparar(proceso)[2]:
            descargar("url", {"formato": "mp4"}, lambda *a: None,
                      lambda *a: estados.append(a), evento)
        self.assertEqual(estados[-1], ("cancelado", "Descarga cancelada"))
        proceso.kill.assert_called_once()

    def test_cancelar_durante_progreso_mata_el_proceso(self):
        proceso = self.proceso([
            "PROG 5 10 NA 2 3 nombre.mp4\n",
            "PROG 6 10 NA 2 3 nombre.mp4\n",
        ])
        evento = threading.Event(); estados = []

        def progreso(*args):
            evento.set()

        with self.preparar(proceso)[0], self.preparar(proceso)[1], self.preparar(proceso)[2]:
            descargar("url", {"formato": "mp4"}, progreso,
                      lambda *a: estados.append(a), evento)
        self.assertEqual(estados[-1], ("cancelado", "Descarga cancelada"))
        proceso.kill.assert_called_once()

    def test_cancelar_despues_de_terminar_marca_estado(self):
        proceso = self.proceso([]); evento = threading.Event(); estados = []
        proceso.wait.side_effect = evento.set
        with self.preparar(proceso)[0], self.preparar(proceso)[1], self.preparar(proceso)[2]:
            descargar("url", {"formato": "mp4"}, lambda *a: None,
                      lambda *a: estados.append(a), evento)
        self.assertEqual(estados[-1], ("cancelado", "Descarga cancelada"))
        proceso.kill.assert_not_called()

    def test_codigo_no_cero_es_error(self):
        proceso = self.proceso([]); proceso.returncode = 2; estados = []
        with self.preparar(proceso)[0], self.preparar(proceso)[1], self.preparar(proceso)[2]:
            descargar("url", {"formato": "mp4"}, lambda *a: None,
                      lambda *a: estados.append(a), threading.Event())
        self.assertEqual(estados[-1][0], "error")

    def test_sin_programa_es_error(self):
        estados = []
        with mock.patch.object(descargas.ytdlp_bin, "ruta_ytdlp", return_value=None):
            descargar("url", {}, lambda *a: None, lambda *a: estados.append(a), threading.Event())
        self.assertEqual(estados[-1][0], "error")


class TestGestorDescargas(unittest.TestCase):
    def opciones(self): return {"formato": "mp4", "bitrate": 192, "carpeta": "/tmp"}
    def test_encolar_almacena_item(self):
        gestor = GestorDescargas(self.opciones())
        with mock.patch.object(descargas.ytdlp_bin, "ruta_ytdlp", return_value=None):
            id_ = gestor.encolar("url", lambda *a: None, lambda *a: None)
        self.assertEqual(gestor.obtener(id_).url, "url")
    def test_cancelar_marca_evento(self):
        gestor = GestorDescargas(self.opciones())
        with mock.patch.object(descargas.ytdlp_bin, "ruta_ytdlp", return_value=None):
            id_ = gestor.encolar("url", lambda *a: None, lambda *a: None)
        gestor.cancelar(id_); self.assertTrue(gestor._eventos[id_].is_set())
    def test_cancelar_inexistente(self): GestorDescargas(self.opciones()).cancelar("no-existe")
    def test_obtener_inexistente(self): self.assertIsNone(GestorDescargas(self.opciones()).obtener("no-existe"))
    def test_set_opciones(self):
        gestor = GestorDescargas(self.opciones()); gestor.set_opciones({"formato": "mp3"})
        self.assertEqual(gestor._opciones["formato"], "mp3")


class TestFfmpeg(unittest.TestCase):
    def test_devuelve_bool(self): self.assertIsInstance(tiene_ffmpeg(), bool)
    def test_faltante_informa_error(self):
        estados = []
        with mock.patch.object(descargas.ytdlp_bin, "ruta_ytdlp", return_value="yt-dlp"), \
                mock.patch.object(descargas, "tiene_ffmpeg", return_value=False):
            descargar("url", {}, lambda *a: None, lambda *a: estados.append(a), threading.Event())
        self.assertIn("ffmpeg", estados[-1][1])


if __name__ == "__main__": unittest.main()
