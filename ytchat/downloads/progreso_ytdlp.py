"""Analiza el progreso textual emitido por el programa yt-dlp."""

from __future__ import annotations


PREFIJO = "PROG"
PLANTILLA = (
    "download:PROG %(progress.downloaded_bytes)s "
    "%(progress.total_bytes)s %(progress.total_bytes_estimate)s "
    "%(progress.speed)s %(progress.eta)s %(progress.filename)s"
)


def _numero(texto: str, convertir):
    if texto == "NA":
        return None
    try:
        return convertir(texto)
    except (TypeError, ValueError):
        return None


def analizar_linea_progreso(linea: str) -> dict | None:
    """Convierte una línea de progreso a datos, o devuelve ``None``."""
    partes = linea.rstrip("\r\n").split(" ", 6)
    if len(partes) not in (6, 7) or partes[0] != PREFIJO:
        return None

    descargado = _numero(partes[1], int)
    if descargado is None:
        return None
    total_bytes = _numero(partes[2], int)
    total_estimado = _numero(partes[3], float)
    total = total_bytes
    total_para_pct = total_bytes if total_bytes is not None else total_estimado
    velocidad = _numero(partes[4], float)
    if len(partes) == 7:
        eta = _numero(partes[5], int)
        nombre = partes[6]
    else:
        eta = None
        nombre = partes[5]
    if not nombre:
        return None

    pct = (descargado * 100.0 / total_para_pct) if total_para_pct else 0.0
    return {
        "descargado": descargado,
        "total": total,
        "pct": pct,
        "velocidad": velocidad,
        "eta": eta,
        "nombre": nombre,
    }
