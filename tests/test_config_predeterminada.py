"""Pruebas de la configuración predeterminada canónica."""

import tempfile
import unittest
import configparser
from pathlib import Path
from unittest import mock

import config
import config_predeterminada as pred
import estado_sesion


class TestArchivoIdentico(unittest.TestCase):
    def test_config_predeterminado_ini_identico_a_generador(self):
        base = Path(__file__).parent.parent
        archivo = base / "config.predeterminado.ini"
        self.assertTrue(archivo.exists(), "config.predeterminado.ini debe existir")
        esperado = pred.generar_texto()
        real = archivo.read_text(encoding="utf-8")
        self.assertEqual(real, esperado, "config.predeterminado.ini debe ser byte por byte igual al generador")

    def test_generar_y_escribir_coinciden(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "salida.ini"
            pred.escribir(ruta)
            self.assertEqual(ruta.read_text(encoding="utf-8"), pred.generar_texto())
            # vía CLI con argumento
            import subprocess, sys
            ruta2 = Path(tmp) / "cli.ini"
            subprocess.check_call([sys.executable, str(Path(pred.__file__)), str(ruta2)])
            self.assertEqual(ruta2.read_text(encoding="utf-8"), pred.generar_texto())


class TestPrimeraEjecucion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_primera_ejecucion_crea_exactamente_canonica(self):
        tmp = Path(self._tmp.name)
        self.assertFalse((tmp / "config.ini").exists())
        with mock.patch.object(config, "app_dir", return_value=tmp):
            cfg = config.cargar_configuracion()
        self.assertTrue((tmp / "config.ini").exists())
        texto = (tmp / "config.ini").read_text(encoding="utf-8")
        self.assertEqual(texto, pred.generar_texto())
        # valores clave del dict deben coincidir con la fuente
        self.assertEqual(cfg["voz"], "0")
        self.assertEqual(cfg["velocidad"], 175)
        self.assertEqual(cfg["volumen"], 1.0)
        self.assertEqual(cfg["estrategia"], "limite")
        self.assertEqual(cfg["formato_prefijo"], "nombre_mensaje")
        self.assertEqual(cfg["mostrar_metadatos"], True)
        self.assertEqual(cfg["descargas_formato"], "mp4")


class TestMigracion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_migracion_agrega_claves_conserva_valores_y_desconocidas(self):
        tmp = Path(self._tmp.name)
        # INI mínimo con valor distinto, vacío intencional y clave desconocida
        contenido = (
            "[voz]\n"
            "voz = 5\n"  # distinto del default 0, debe conservarse
            "[obs]\n"
            "microfono = \n"  # vacío intencional (default también vacío)
            "[filtros]\n"
            "palabras_silenciadas = \n"  # vacío intencional
            "[lectura]\n"
            "formato_prefijo = \n"  # vacío aunque el default no lo sea
            "[mi_seccion]\n"
            "clave_desconocida = valor_raro\n"
        )
        (tmp / "config.ini").write_text(contenido, encoding="utf-8")
        with mock.patch.object(config, "app_dir", return_value=tmp):
            cfg = config.cargar_configuracion()
        texto = (tmp / "config.ini").read_text(encoding="utf-8")
        # conserva valor distinto
        self.assertEqual(cfg["voz"], "5")
        self.assertIn("voz = 5", texto)
        # conserva vacío intencional: la clave sigue existiendo y el valor no se reemplaza por default
        p = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
        p.read(tmp / "config.ini", encoding="utf-8")
        self.assertTrue(p.has_option("obs", "microfono"))
        self.assertEqual(p.get("obs", "microfono").strip(), "")
        self.assertTrue(p.has_option("filtros", "palabras_silenciadas"))
        self.assertEqual(p.get("lectura", "formato_prefijo").strip(), "")
        # conserva clave desconocida
        self.assertTrue(p.has_section("mi_seccion"))
        self.assertEqual(p.get("mi_seccion", "clave_desconocida"), "valor_raro")
        self.assertIn("clave_desconocida = valor_raro", texto)
        # agrega todas las secciones y claves canónicas, incluida la carpeta
        for seccion, claves in pred.datos().items():
            self.assertTrue(p.has_section(seccion), f"falta sección [{seccion}]")
            for clave in claves:
                self.assertTrue(
                    p.has_option(seccion, clave),
                    f"falta {seccion}.{clave} tras migración",
                )


class TestFallbacksSeccion(unittest.TestCase):
    def test_fallbacks_distinguen_seccion_y_clave(self):
        # clave "voz" solo existe en [voz]; pedirla en [ui] debe dar fallback vacío
        self.assertEqual(pred.obtener("voz", "voz"), "0")
        self.assertEqual(pred.obtener("ui", "voz"), "")
        # "activo" existe en varias secciones con mismo valor pero debe distinguirse por sección
        # si preguntamos una sección inexistente, debe dar fallback vacío
        self.assertEqual(pred.obtener("seccion_inexistente", "activo"), "")
        # a nivel de config._gs con parser vacío
        p = config._mk_parser()
        self.assertEqual(config._gs(p, "voz", "voz"), "0")
        self.assertEqual(config._gs(p, "ui", "voz"), "")
        self.assertEqual(config._gs(p, "overlay", "activo"), "false")
        self.assertEqual(config._gs(p, "programados", "activo"), "false")
        self.assertEqual(config._gs(p, "inexistente", "activo"), "")


class TestAtajosDefaults(unittest.TestCase):
    def test_atajos_defaults_coincide_con_atajos_canonicos(self):
        self.assertEqual(config.ATAJOS_DEFAULTS, pred.seccion("atajos"))
        self.assertEqual(config._CONFIG_FALLBACK, pred.generar_texto())

    def test_boton_fabrica_usa_fuente_canonica_y_no_altera_fijos(self):
        try:
            import wx
            import gui_preferencias as gp
        except Exception:
            self.skipTest("wx no disponible")
        # Preparar dialogo sin construir UI completa
        dialogo = gp.PreferenciasDialog.__new__(gp.PreferenciasDialog)
        dialogo._valores_atajo = {"rep_play": "ctrl+q", "salir": "alt+x"}
        # necesitamos botones mock para _restaurar_etiqueta_atajo
        import unittest.mock as mock
        # crear botones para cada accion de la fuente canónica + fijos
        todas = {**config.ATAJOS_DEFAULTS, **config.ATAJOS_FIJOS_DEFAULTS}
        dialogo._botones_atajo = {a: mock.Mock() for a in todas}
        dialogo._valores_atajo["region_siguiente"] = "f6"
        # patch de la fuente canónica expuesta a la GUI
        nuevo = dict(pred.seccion("atajos"))
        nuevo["rep_play"] = "ctrl+z"
        # mantener el resto igual para no romper
        with mock.patch.object(pred, "seccion", return_value=nuevo):
            with mock.patch.object(gp, "anunciar"):
                dialogo._restablecer_atajos(None)
        self.assertEqual(dialogo._valores_atajo["rep_play"], "ctrl+z")
        # los fijos no se tocan
        self.assertEqual(dialogo._valores_atajo["salir"], "alt+x")


class TestEstadoDefecto(unittest.TestCase):
    def test_activos_defecto_coincide_con_true_de_estado(self):
        sec = pred.seccion("estado")
        esperados = {k for k, v in sec.items() if v.strip().lower() in ("true", "yes", "1", "on")}
        self.assertEqual(estado_sesion.ACTIVOS_DEFECTO, frozenset(esperados))

    def test_estado_cubre_exactamente_componentes(self):
        sec_keys = set(pred.seccion("estado").keys())
        comp = set(estado_sesion.COMPONENTES)
        self.assertEqual(sec_keys, comp, f"estado debe cubrir exactamente COMPONENTES. Faltan {comp - sec_keys}, sobran {sec_keys - comp}")


class TestConstruirBat(unittest.TestCase):
    def test_construir_invoca_generador_y_no_usa_git_para_config(self):
        base = Path(__file__).parent.parent
        texto = (base / "construir.bat").read_text(encoding="utf-8")
        self.assertNotIn("HEAD:config.ini", texto)
        # no debe copiar config.ini local
        self.assertNotIn('copy /y "config.ini"', texto)
        self.assertIn("config_predeterminada.py", texto)
        self.assertIn("%OUT%\\config.ini", texto)
        # debe tener manejo de error tras generar
        self.assertIn("if errorlevel 1", texto)
        # el siguiente if errorlevel debe estar tras la invocación del generador
        idx = texto.lower().find("config_predeterminada.py")
        self.assertGreater(idx, -1)
        resto = texto[idx: idx + 500].lower()
        self.assertIn("error", resto)
        self.assertIn("exit /b 1", resto)


class TestGitignore(unittest.TestCase):
    def test_gitignore_ignora_config_y_no_ignora_predeterminado(self):
        base = Path(__file__).parent.parent
        txt = (base / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/config.ini", txt)
        # config.predeterminado.ini no debe estar ignorado: no aparece como patrón
        # que lo ignore y git check-ignore debe no ignorarlo
        import subprocess
        # git check-ignore devuelve 0 si está ignorado, 1 si no. Usar --no-index
        # porque config.ini aún está trackeado y sin --no-index no se ve ignorado.
        try:
            res = subprocess.run(["git", "check-ignore", "--no-index", "config.predeterminado.ini"],
                                 cwd=str(base), capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0, "config.predeterminado.ini no debe estar ignorado")
            res2 = subprocess.run(["git", "check-ignore", "--no-index", "config.ini"],
                                  cwd=str(base), capture_output=True, text=True)
            self.assertEqual(res2.returncode, 0, "config.ini debe estar ignorado")
        except FileNotFoundError:
            # si git no está, al menos verificar que no hay patrón que lo ignore
            self.assertNotIn("config.predeterminado.ini", txt)
