"""Decide cuándo un aviso sustituye al anterior."""

_ultima_categoria = ""


def debe_interrumpir(categoria: str, anterior: str) -> bool:
    return bool(categoria and categoria == anterior)


def recordar_categoria(categoria: str) -> None:
    global _ultima_categoria
    _ultima_categoria = categoria


def ultima_categoria() -> str:
    return _ultima_categoria
