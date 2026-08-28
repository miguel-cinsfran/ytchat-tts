"""Decisiones puras para la posición y el transporte del reproductor."""

TOLERANCIA_DESTINO_MS = 1500


def destino_acumulado(destino_pendiente, posicion_actual, delta_ms,
                      duracion_ms) -> int:
    """Calcula el siguiente salto sin perder pulsaciones en vuelo."""
    base = posicion_actual if destino_pendiente is None else destino_pendiente
    return min(max(0, base + delta_ms), duracion_ms)


def destino_alcanzado(destino_pendiente, posicion_actual,
                      tolerancia_ms) -> bool:
    """Indica cuándo la posición real ya puede sustituir al destino pedido."""
    return (destino_pendiente is None
            or abs(posicion_actual - destino_pendiente) <= tolerancia_ms)


def posicion_a_mostrar(destino_pendiente, posicion_actual) -> int:
    """Conserva visible el destino hasta que el reproductor lo alcance."""
    return posicion_actual if destino_pendiente is None else destino_pendiente


def accion_play_pausa(estado, hay_medio, intencion_reproducir) -> str:
    """Decide el transporte sin depender de enums ni estados transitorios."""
    if not hay_medio:
        return "cargar"
    if estado == "playing":
        return "pausar"
    if estado == "paused":
        return "reanudar"
    if estado in {"ended", "stopped", "error", "nothingspecial"}:
        return "cargar"
    # Opening y buffering aún no reflejan la orden previa: nunca recargan.
    return "pausar" if intencion_reproducir else "reanudar"
