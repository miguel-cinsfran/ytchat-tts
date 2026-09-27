"""Elección y anuncios de las fuentes de audio de OBS."""

import unicodedata


def _contiene_microfono(nombre: str) -> bool:
    normalizado = unicodedata.normalize("NFD", nombre.casefold())
    sin_tildes = "".join(
        caracter for caracter in normalizado
        if unicodedata.category(caracter) != "Mn")
    return "mic" in sin_tildes


def elegir_microfono(fuentes, preferido: str) -> str:
    """Devuelve la fuente de audio que se usará como micrófono."""
    fuentes = tuple(fuentes)
    if preferido in fuentes:
        return preferido
    return next((fuente for fuente in fuentes if _contiene_microfono(fuente)),
                fuentes[0] if fuentes else "")


def frase_microfono(fuente: str, silenciado: bool) -> str:
    """Compone el anuncio posterior a cambiar el silencio."""
    if not fuente:
        return "OBS no tiene ninguna fuente de audio"
    estado = "silenciado" if silenciado else "activado"
    if _contiene_microfono(fuente):
        return f"Micrófono {estado}"
    return f"{fuente} {estado}"
