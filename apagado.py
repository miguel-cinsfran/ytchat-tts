"""Decisiones puras del cierre de la aplicación."""

from __future__ import annotations


NOMBRES_HILOS_CAPTURA = frozenset(("Chat", "TikTok", "LiveChatId"))


def hilos_captura_vivos(nombres: set[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Devuelve los nombres de captura que siguen vivos, ordenados."""
    return tuple(sorted(set(nombres) & NOMBRES_HILOS_CAPTURA))


def hay_que_seguir_esperando(
    nombres: set[str] | tuple[str, ...], transcurrido: float, tope: float
) -> bool:
    """Indica si quedan capturas y todavía no venció el tope."""
    return bool(hilos_captura_vivos(nombres)) and transcurrido < tope


def componer_resultado_cierre(nombres: set[str] | tuple[str, ...], tope: float) -> str:
    """Compone el registro del resultado final de la espera."""
    vivos = hilos_captura_vivos(nombres)
    if not vivos:
        return "CIERRE captura limpia"
    return f"CIERRE por tope={tope:.1f}s hilos vivos={', '.join(vivos)}"
