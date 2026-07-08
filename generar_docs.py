#!/usr/bin/env python
"""Genera las versiones HTML de la documentación (README y guía de la API) con pandoc.

Los .md son cómodos para editar y se leen bien en GitHub, pero el amigo que usa
la aplicación no tiene por qué saber abrir un Markdown. Este script convierte
los documentos de cara al usuario a HTML autocontenido (con el estilo dentro del
propio archivo, sin depender de nada externo), fácil de abrir con doble clic y
de leer con lector de pantalla.

El historial de versiones vive en la sección «Novedades» del propio README (no
hay un CHANGELOG aparte).

Uso:
    uv run python generar_docs.py

Requiere pandoc en el PATH (https://pandoc.org). Los HTML se escriben en docs/ y
se versionan; hay que regenerarlos y commitearlos cuando cambie un .md. El
paquete distribuible (construir.bat) copia docs/, así que viajan con la app.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DOCS = AQUI / "docs"

# (origen .md, destino .html en docs/, título de la página). El título es lo que
# lee el lector de pantalla al abrir y lo que sale en la pestaña del navegador.
DOCUMENTOS = [
    (AQUI / "README.md",              "README.html",            "YTChat TTS — Léeme"),
    (DOCS / "CONFIGURACION_API.md",   "CONFIGURACION_API.html", "YTChat TTS — Configurar la API de YouTube"),
]

# Estilo embebido: sobrio, legible y responsivo, con modo claro y oscuro según
# el sistema. Sin fuentes ni recursos externos, para que el HTML se abra en
# cualquier equipo sin conexión.
_ESTILO = """<style>
:root {
  --fondo: #ffffff; --texto: #1c1917; --tenue: #57534e;
  --acento: #b8452f; --borde: #e7e5e4; --codigo-fondo: #f5f5f4;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fondo: #1c1917; --texto: #e7e5e4; --tenue: #a8a29e;
    --acento: #e8745c; --borde: #44403c; --codigo-fondo: #292524;
  }
}
html { -webkit-text-size-adjust: 100%; }
body {
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.65; color: var(--texto); background: var(--fondo);
  max-width: 46rem; margin: 0 auto; padding: 2rem 1.25rem 4rem;
  font-size: 1.05rem;
}
h1, h2, h3 { line-height: 1.25; margin-top: 2.2rem; }
h1 { font-size: 1.9rem; color: var(--acento); border-bottom: 2px solid var(--borde); padding-bottom: .4rem; }
h2 { font-size: 1.4rem; border-bottom: 1px solid var(--borde); padding-bottom: .3rem; }
h3 { font-size: 1.15rem; color: var(--tenue); }
a { color: var(--acento); }
code {
  background: var(--codigo-fondo); padding: .12em .35em;
  border-radius: 4px; font-size: .9em;
}
pre {
  background: var(--codigo-fondo); padding: 1rem; border-radius: 6px;
  overflow-x: auto; border: 1px solid var(--borde);
}
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; overflow-x: auto; display: block; }
th, td { border: 1px solid var(--borde); padding: .5rem .7rem; text-align: left; }
th { background: var(--codigo-fondo); }
blockquote {
  border-left: 3px solid var(--acento); margin: 1rem 0;
  padding: .2rem 1rem; color: var(--tenue);
}
hr { border: none; border-top: 1px solid var(--borde); margin: 2rem 0; }
</style>
"""


# Los .md se enlazan entre sí por su nombre .md (para que funcionen en GitHub).
# En el HTML esos enlaces deben apuntar al HTML equivalente. Los enlaces se
# calculan desde la RAÍZ del paquete, que es donde el usuario abre «Léeme.html»
# (README); la guía de la API queda en la subcarpeta docs/.
_REESCRITURA_ENLACES = {
    'href="README.md"':                'href="README.html"',
    'href="docs/CONFIGURACION_API.md"': 'href="docs/CONFIGURACION_API.html"',
}


def _convertir(md: Path, salida: Path, titulo: str, header: Path) -> bool:
    if not md.exists():
        print(f"  [saltado] no existe {md.name}")
        return True   # no es un fallo: puede que ese .md aún no exista
    # pagetitle (no title): pone el <title> de la pestaña/lector SIN duplicar un
    # <h1> de título en el cuerpo (el .md ya trae su propio encabezado de nivel 1).
    cmd = [
        "pandoc", str(md), "-o", str(salida),
        "--standalone", "--from", "gfm", "--to", "html5",
        "--metadata", f"pagetitle={titulo}", "--metadata", "lang=es",
        "--include-in-header", str(header),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        print(f"  [FALLO] {md.name}: {exc.stderr.strip()}")
        return False
    html = salida.read_text(encoding="utf-8")
    for viejo, nuevo in _REESCRITURA_ENLACES.items():
        html = html.replace(viejo, nuevo)
    salida.write_text(html, encoding="utf-8")
    print(f"  [ok] {md.name}  ->  docs/{salida.name}")
    return True


def main() -> int:
    if shutil.which("pandoc") is None:
        print("ERROR: pandoc no está en el PATH. Instálalo desde https://pandoc.org")
        return 1
    DOCS.mkdir(exist_ok=True)
    print("Generando documentación HTML (pandoc)...")
    # El bloque <style> va a un archivo temporal que pandoc mete en el <head>.
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as f:
        f.write(_ESTILO)
        header = Path(f.name)
    ok = True
    try:
        for md, nombre, titulo in DOCUMENTOS:
            ok = _convertir(md, DOCS / nombre, titulo, header) and ok
    finally:
        try:    header.unlink()
        except OSError: pass
    print("Listo." if ok else "Terminó con errores.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
