"""Frases periódicas para una espera que puede tardar."""

from __future__ import annotations


def aviso_de_espera(segundos_esperando: float,
                    segundos_ultimo_aviso: float | None) -> str:
    """Devuelve el aviso que toca decir, o una cadena vacía."""
    segundos = max(0, int(segundos_esperando))
    if segundos < 2:
        return ""
    if (segundos_ultimo_aviso is not None
            and segundos_esperando - segundos_ultimo_aviso < 3):
        return ""
    if segundos >= 20:
        return (f"Sigue buscando el vídeo, {segundos} segundos. "
                "Está tardando más de lo normal.")
    return f"Buscando el vídeo, {segundos} segundos"
