"""Decisiones y textos del ajuste fino del panel de OBS."""


PASO_NORMAL = 10
PASO_GRANDE = 50
PASO_FINO = 1


def resolver(codigo, ctrl, shift) -> tuple:
    """Decide la acción y el desplazamiento para una tecla."""
    if codigo in (13, 370):
        return "confirmar", 0, 0
    if codigo == 27:
        return "cancelar", 0, 0
    if codigo == 9:
        return "salir", 0, 0

    paso = PASO_GRANDE if ctrl else PASO_FINO if shift else PASO_NORMAL
    movimientos = {
        314: (-paso, 0), 316: (paso, 0),
        315: (0, -paso), 317: (0, paso),
    }
    dx, dy = movimientos.get(codigo, (0, 0))
    return ("mover", dx, dy) if codigo in movimientos else ("ignorar", 0, 0)


def etiqueta_boton(activo, etiqueta_base) -> str:
    """Devuelve la etiqueta que corresponde al estado del modo."""
    return "Ajustando, flechas para mover" if activo else etiqueta_base


def texto_de_entrada() -> str:
    """Devuelve el anuncio al entrar en el modo."""
    return ("Ajuste fino. Flechas para mover, Control para pasos grandes, "
            "Mayúsculas para pasos de un píxel. Intro confirma, Escape deshace, "
            "Tab sale.")
