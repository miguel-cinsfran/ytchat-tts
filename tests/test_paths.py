"""Pruebas del módulo paths, único origen de las rutas de la aplicación."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
import paths
from tests.rutas_temporales import redirigir_rutas


# (función de paths, nombre esperado en disco)
RUTAS_DE_DATOS = [
    ("config_ini", "config.ini"),
    ("credenciales", "credenciales.json"),
    ("historial_lives", "historial_lives.json"),
    ("historial_descargas", "historial_descargas.json"),
    ("alias", "alias.json"),
    ("mensajes_programados", "mensajes_programados.json"),
    ("sounds_ini", "sounds.ini"),
    ("log_principal", "ytchat.log"),
    ("log_detallado", "ytchat-debug.log"),
    ("log_fallos", "ytchat-fallos.log"),
    ("cache_audio", "cache-audio"),
    ("cache_video", "cache-video"),
    ("descargas_por_defecto", "Descargas"),
]

RUTAS_DE_INSTALACION = [
    ("carpeta_sonidos", "sounds"),
    ("config_predeterminada_ini", "config.predeterminado.ini"),
    ("ffmpeg_empaquetado", paths.NOMBRE_FFMPEG),
    ("ytdlp_empaquetado", paths.NOMBRE_YTDLP),
    ("carpeta_vlc_empaquetada", "vlc"),
    ("carpeta_interna", "_internal"),
]

TODAS_LAS_FUNCIONES = (
    [nombre for nombre, _ in RUTAS_DE_DATOS]
    + [nombre for nombre, _ in RUTAS_DE_INSTALACION]
    + ["pagina_overlay"]
)


class TestRaices(unittest.TestCase):

    def test_empaquetada_es_la_carpeta_del_ejecutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = str(Path(tmp) / "YTChatTTS.exe")
            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "executable", exe):
                self.assertEqual(paths.carpeta_instalacion(), Path(tmp))
                self.assertEqual(paths.config_ini(), Path(tmp) / "config.ini")
                self.assertEqual(paths.ytdlp_empaquetado(),
                                 Path(tmp) / paths.NOMBRE_YTDLP)

    def test_en_desarrollo_es_la_raiz_del_repositorio(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            raiz = paths.carpeta_instalacion()
        self.assertEqual(raiz, Path(paths.__file__).resolve().parent)
        self.assertTrue((raiz / "config.py").is_file())

    def test_datos_coincide_con_instalacion_en_este_encargo(self):
        self.assertEqual(paths.carpeta_datos(), paths.carpeta_instalacion())


class TestFunciones(unittest.TestCase):

    def test_cada_dato_cuelga_de_carpeta_datos(self):
        with tempfile.TemporaryDirectory() as tmp:
            datos, instalacion = Path(tmp) / "datos", Path(tmp) / "app"
            with mock.patch.object(paths, "carpeta_datos",
                                   return_value=datos), \
                 mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=instalacion):
                for nombre, esperado in RUTAS_DE_DATOS:
                    with self.subTest(funcion=nombre):
                        self.assertEqual(getattr(paths, nombre)(),
                                         datos / esperado)

    def test_cada_instalacion_cuelga_de_carpeta_instalacion(self):
        with tempfile.TemporaryDirectory() as tmp:
            datos, instalacion = Path(tmp) / "datos", Path(tmp) / "app"
            with mock.patch.object(paths, "carpeta_datos",
                                   return_value=datos), \
                 mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=instalacion):
                for nombre, esperado in RUTAS_DE_INSTALACION:
                    with self.subTest(funcion=nombre):
                        self.assertEqual(getattr(paths, nombre)(),
                                         instalacion / esperado)
                self.assertEqual(paths.pagina_overlay(),
                                 instalacion / "web" / "chat.html")

    def test_ninguna_funcion_crea_nada_en_disco(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "inexistente"
            with mock.patch.object(paths, "carpeta_datos",
                                   return_value=destino), \
                 mock.patch.object(paths, "carpeta_instalacion",
                                   return_value=destino):
                for nombre in TODAS_LAS_FUNCIONES:
                    with self.subTest(funcion=nombre):
                        getattr(paths, nombre)()
            self.assertFalse(destino.exists())


class TestAyudante(unittest.TestCase):

    def test_redirigir_rutas_mueve_las_dos_raices_y_app_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            with redirigir_rutas(destino) as devuelta:
                self.assertEqual(devuelta, destino)
                self.assertEqual(paths.carpeta_datos(), destino)
                self.assertEqual(paths.carpeta_instalacion(), destino)
                self.assertEqual(paths.config_ini(), destino / "config.ini")
                # app_dir delega en paths: lo redirigido también la mueve.
                self.assertEqual(config.app_dir(), destino)
            self.assertNotEqual(paths.carpeta_instalacion(), destino)


class TestFronteraReal(unittest.TestCase):

    def test_cargar_configuracion_lee_el_ini_redirigido(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirigir_rutas(tmp):
                # El nombre se escribe a propósito en literal: es el contrato
                # de ubicación física, y así la prueba lo exige sin pasar por
                # la función bajo prueba.
                esperada = Path(tmp) / "config.ini"
                esperada.write_text("[voz]\nvelocidad = 200\n", encoding="utf-8")
                cfg = config.cargar_configuracion()
            self.assertEqual(cfg["ruta_config"], esperada)
            # 200 no es el valor por defecto (175): solo puede venir de ESE
            # archivo, no de otro config.ini del disco.
            self.assertEqual(cfg["velocidad"], 200)


def _sin_comentarios(texto: str) -> str:
    """Devuelve el texto sin comentarios `#`, respetando los strings."""
    salida = []
    i, n = 0, len(texto)
    comilla = None  # ', " o su variante triple
    while i < n:
        if comilla is None:
            if texto.startswith("#", i):
                while i < n and texto[i] != "\n":
                    i += 1
                continue
            for candidato in ('"""', "'''", '"', "'"):
                if texto.startswith(candidato, i):
                    comilla = candidato
                    salida.append(candidato)
                    i += len(candidato)
                    break
            else:
                salida.append(texto[i])
                i += 1
        else:
            if texto[i] == "\\":
                salida.append(texto[i:i + 2])
                i += 2
                continue
            if texto.startswith(comilla, i):
                salida.append(comilla)
                i += len(comilla)
                comilla = None
            else:
                salida.append(texto[i])
                i += 1
    return "".join(salida)


class TestGuardaRutas(unittest.TestCase):
    """Ningún módulo arma rutas por su cuenta: todo sale de paths."""

    EXCLUIDOS = {"paths.py", "smoke_test.py", "generar_docs.py", "sound_gen.py"}

    NOMBRES_DATOS = (
        "config.ini", "credenciales.json", "historial_lives.json",
        "historial_descargas.json", "alias.json", "mensajes_programados.json",
        "sounds.ini", "ytchat.log", "ytchat-debug.log", "ytchat-fallos.log",
    )

    # (archivo, fragmento permitido, motivo). Sin comodines.
    EXCEPCIONES = (
        ("config.py", "def app_dir",
         "app_dir se conserva delegando en paths, para herramientas fuera del alcance"),
    )

    def _exceptuado(self, archivo: str, codigo: str) -> bool:
        return any(archivo == exc_archivo and fragmento in codigo
                   for exc_archivo, fragmento, _motivo in self.EXCEPCIONES)

    def test_ningun_modulo_arma_rutas_por_su_cuenta(self):
        raiz = Path(__file__).resolve().parent.parent
        violaciones = []
        for modulo in sorted(raiz.glob("*.py")):
            if modulo.name in self.EXCLUIDOS:
                continue
            codigo = _sin_comentarios(modulo.read_text(encoding="utf-8"))
            for nro, linea in enumerate(codigo.splitlines(), 1):
                if self._exceptuado(modulo.name, linea):
                    continue
                if "app_dir(" in linea:
                    violaciones.append(f"{modulo.name}:{nro}: usa app_dir(")
                if "sys.executable" in linea:
                    violaciones.append(f"{modulo.name}:{nro}: usa sys.executable")
                for nombre in self.NOMBRES_DATOS:
                    if f'"{nombre}"' in linea or f"'{nombre}'" in linea:
                        violaciones.append(
                            f"{modulo.name}:{nro}: nombra {nombre} entre comillas")
        self.assertEqual([], violaciones,
                         "rutas armadas fuera de paths:\n" + "\n".join(violaciones))


if __name__ == "__main__":
    unittest.main()
