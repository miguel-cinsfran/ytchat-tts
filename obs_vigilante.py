"""Vigilancia en segundo plano del estado de OBS."""


PLAZO_FRESCURA = 12.0


def dato_fresco(ultimo_sondeo: float | None, ahora: float) -> bool:
    """Indica si un sondeo de OBS todavía puede anunciarse."""
    return ultimo_sondeo is not None and ahora - ultimo_sondeo <= PLAZO_FRESCURA
