"""Alias persistentes para mostrar y leer nombres de usuario."""

from __future__ import annotations

import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)
_vigente: dict = {}


def clave(autor) -> str:
    """Normaliza un autor para buscar su alias."""
    return (autor or "").strip().lower()


def cargar(ruta: Path) -> dict:
    """Lee los alias o devuelve un mapa vacío si el archivo no sirve."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except Exception as exc:
        logger.debug("cargar alias: %s", exc)
        return {}


def guardar(ruta: Path, mapa: dict) -> None:
    """Escribe los alias sin interrumpir la aplicación si falla."""
    try:
        ruta.write_text(json.dumps(mapa, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except Exception as exc:
        logger.debug("guardar alias: %s", exc)


def _limpiar_alias(alias) -> str:
    return (alias or "").replace("\r", "").replace("\n", "").strip()[:50]


def poner(mapa: dict, autor, alias) -> dict:
    """Devuelve un mapa nuevo con el alias puesto o quitado."""
    resultado = dict(mapa)
    autor_clave = clave(autor)
    if not autor_clave:
        return resultado
    alias_limpio = _limpiar_alias(alias)
    if alias_limpio:
        resultado[autor_clave] = alias_limpio
    else:
        resultado.pop(autor_clave, None)
    return resultado


def quitar(mapa: dict, autor) -> dict:
    """Devuelve un mapa nuevo sin el alias del autor."""
    resultado = dict(mapa)
    resultado.pop(clave(autor), None)
    return resultado


def aplicar(autor, mapa: dict) -> str:
    """Devuelve el alias del autor, o el autor original si no lo tiene."""
    if not autor or not mapa:
        return autor
    return mapa.get(clave(autor), autor)


def usar(mapa: dict) -> None:
    """Establece el mapa de alias de la sesión."""
    global _vigente
    _vigente = mapa


def vigente() -> dict:
    """Devuelve el mapa de alias de la sesión."""
    return _vigente


def visible(autor) -> str:
    """Devuelve el nombre que debe presentarse al usuario."""
    return aplicar(autor, vigente())
