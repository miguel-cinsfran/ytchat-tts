"""Pruebas de las referencias y conversiones de la documentación."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generar_docs


class DocumentosTest(unittest.TestCase):

    def test_los_documentos_de_origen_existen(self):
        for origen, _, _ in generar_docs.DOCUMENTOS:
            self.assertTrue(origen.exists(), f"No existe el documento {origen}")

    def test_los_destinos_de_los_enlaces_se_generan(self):
        destinos = {nombre for _, nombre, _ in generar_docs.DOCUMENTOS}
        for reemplazo in generar_docs._REESCRITURA_ENLACES.values():
            destino = reemplazo.removeprefix('href="').removesuffix('"')
            self.assertEqual(Path(destino).suffix, ".html")
            self.assertIn(Path(destino).name, destinos)


class ConvertirTest(unittest.TestCase):

    def test_no_llama_pandoc_si_el_markdown_no_existe(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            with patch.object(generar_docs.subprocess, "run") as ejecutar:
                convertido = generar_docs._convertir(
                    raiz / "ausente.md", raiz / "salida.html", "Título",
                    raiz / "estilo.html")

        self.assertTrue(convertido)
        ejecutar.assert_not_called()

    def test_reescribe_enlaces_del_html_generado(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            markdown = raiz / "origen.md"
            salida = raiz / "salida.html"
            header = raiz / "estilo.html"
            markdown.write_text("# Documento", encoding="utf-8")
            header.write_text("<style></style>", encoding="utf-8")

            def simular_pandoc(*_args, **_kwargs):
                salida.write_text('<a href="README.md">Léeme</a>', encoding="utf-8")

            with patch.object(generar_docs.subprocess, "run",
                              side_effect=simular_pandoc) as ejecutar:
                convertido = generar_docs._convertir(
                    markdown, salida, "Título", header)

            self.assertTrue(convertido)
            ejecutar.assert_called_once()
            self.assertIn('href="README.html"',
                          salida.read_text(encoding="utf-8"))

    def test_devuelve_falso_si_pandoc_falla(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            markdown = raiz / "origen.md"
            markdown.write_text("# Documento", encoding="utf-8")
            error = subprocess.CalledProcessError(
                1, ["pandoc"], stderr="falló pandoc")

            with patch.object(generar_docs.subprocess, "run", side_effect=error):
                convertido = generar_docs._convertir(
                    markdown, raiz / "salida.html", "Título", raiz / "estilo.html")

        self.assertFalse(convertido)
