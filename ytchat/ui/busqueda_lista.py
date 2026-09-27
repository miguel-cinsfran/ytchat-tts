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


def _sin_simbolos_iniciales(texto: str) -> str:
    """Salta los caracteres iniciales que no son letra ni dígito. Las filas del
    chat pueden empezar por «@» (el handle del autor), «💲 [monto]», «⭐», «👋»…
    y quien busca teclea letras: sin esto, «j» jamás encontraría a
    «@judith…»."""
    i = 0
    while i < len(texto) and not texto[i].isalnum():
        i += 1
    return texto[i:]


def coincide(texto: str, prefijo: str) -> bool:
    """¿`texto` empieza por `prefijo`? Compara normalizado y también saltando
    los símbolos iniciales del texto (arroba, marcadores de evento…)."""
    pref = normalizar(prefijo)
    if not pref:
        return False
    t = normalizar(texto)
    return t.startswith(pref) or _sin_simbolos_iniciales(t).startswith(pref)


def buscar_prefijo(items: list[str], desde: int, prefijo: str) -> int | None:
    """Primer índice, buscando circularmente desde `desde`, cuyo texto empiece
    por `prefijo` (ver `coincide`: normalizado y tolerando símbolos iniciales).

    Recorre `items` completo como máximo una vez: empieza en `desde` y sigue
    envolviendo (wrap) hasta volver a `desde` inclusive, así una lista con un
    único candidato lo encuentra aunque esté justo en `desde`.
    """
    n = len(items)
    if n == 0 or not prefijo:
        return None
    if not normalizar(prefijo):
        return None
    inicio = desde % n
    for salto in range(n):
        idx = (inicio + salto) % n
        if coincide(items[idx], prefijo):
            return idx
    return None
