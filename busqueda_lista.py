"""Búsqueda por prefijo (type-ahead) para listas de texto, sin wx.

Lo usan las listas de contenido dinámico (chat, comentarios): al escribir
letras seguidas mientras la lista tiene el foco, salta al primer ítem cuyo
texto mostrado empiece por lo tecleado. Aislado aquí para poder probarlo sin
GUI, igual que `lista_chat.py`.
"""

from __future__ import annotations

import unicodedata


def normalizar(texto: str) -> str:
    """Quita acentos/diacríticos, pasa a minúsculas «fuertes» (casefold) y
    recorta espacios iniciales, para comparar sin que acentos o mayúsculas
    hagan fallar una coincidencia evidente para quien escucha."""
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFD", texto)
    sin_diacriticos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_diacriticos.casefold().lstrip()


def buscar_prefijo(items: list[str], desde: int, prefijo: str) -> int | None:
    """Primer índice, buscando circularmente desde `desde`, cuyo texto (ya
    normalizado) empiece por `prefijo` (también normalizado).

    Recorre `items` completo como máximo una vez: empieza en `desde` y sigue
    envolviendo (wrap) hasta volver a `desde` inclusive, así una lista con un
    único candidato lo encuentra aunque esté justo en `desde`.
    """
    n = len(items)
    if n == 0 or not prefijo:
        return None
    pref = normalizar(prefijo)
    if not pref:
        return None
    inicio = desde % n if n else 0
    for salto in range(n):
        idx = (inicio + salto) % n
        if normalizar(items[idx]).startswith(pref):
            return idx
    return None
