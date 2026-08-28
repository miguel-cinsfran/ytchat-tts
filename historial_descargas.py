"""Historial persistente de las descargas terminadas."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import diagnostico

logger = diagnostico.obtener_logger(__name__)

TOPE_ENTRADAS = 200


def cargar(ruta: Path) -> list[dict]:
    """Lee el historial o devuelve una lista vacía si no se puede usar."""
    try:
        if ruta.exists():
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            return datos if isinstance(datos, list) else []
    except Exception as exc:
        logger.debug("cargar historial de descargas: %s", exc)
    return []


def guardar(ruta: Path, entradas: list[dict]) -> None:
    """Guarda el historial sin impedir las descargas si falla el disco."""
    try:
        ruta.write_text(json.dumps(entradas, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except Exception as exc:
        logger.debug("guardar historial de descargas: %s", exc)


def agregar(entradas: list[dict], entrada: dict,
            tope: int = TOPE_ENTRADAS) -> list[dict]:
    """Devuelve una lista nueva con la entrada reciente al principio."""
    return ([dict(entrada)] + list(entradas))[:tope]


def formatear(entrada: dict) -> tuple[str, str, str]:
    """Devuelve las celdas Nombre, Fecha y Estado de una entrada."""
    return (str(entrada.get("nombre") or ""),
            str(entrada.get("fecha") or ""),
            str(entrada.get("estado") or ""))
