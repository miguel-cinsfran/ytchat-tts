"""Decisiones y textos accesibles sobre mensajes descartados."""


UMBRAL_AVISO = 3


def hay_que_avisar(descartados: int, ya_avisado: bool,
                    umbral: int = UMBRAL_AVISO) -> bool:
    """Indica si esta sesión debe anunciar los descartes."""
    return descartados >= umbral and not ya_avisado


def frase_aviso(umbral_solo_nombre: int) -> str:
    """Devuelve el aviso que se interrumpe para no ocultar los descartes."""
    base = ("La lectura va con retraso y se están descartando mensajes. "
            "Puedes buscarlos en la lista del chat.")
    if umbral_solo_nombre > 0:
        return base
    return (base + " Activa en Preferencias la lectura solo del nombre cuando "
            "haya muchos mensajes.")


def frase_estado(descartados: int) -> str:
    """Devuelve el componente de estado, vacío si no hubo descartes."""
    if descartados <= 0:
        return ""
    return f"Mensajes descartados: {descartados}"
