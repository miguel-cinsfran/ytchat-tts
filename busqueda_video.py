"""Decisiones puras para la posición y el transporte del reproductor."""

TOLERANCIA_DESTINO_MS = 1500
TOLERANCIA_ATRAS_MS = 2000
CADUCIDAD_DESTINO_MS = 5000
# Pasada esta ventana, el estado real recupera el mando ante un desajuste.
VENTANA_ORDEN_MS = 3000


def destino_acumulado(destino_pendiente, posicion_actual, delta_ms,
                      duracion_ms) -> int:
    """Calcula el siguiente salto sin perder pulsaciones en vuelo."""
    base = posicion_actual if destino_pendiente is None else destino_pendiente
    destino = min(max(0, base + delta_ms), duracion_ms)
    if delta_ms > 0 and destino < base:
        return base
    return destino


def destino_alcanzado(destino_pendiente, posicion_actual,
                      tolerancia_ms) -> bool:
    """Indica cuándo la posición real ya puede sustituir al destino pedido."""
    return (destino_pendiente is None
            or abs(posicion_actual - destino_pendiente) <= tolerancia_ms)


def posicion_a_mostrar(destino_pendiente, posicion_actual) -> int:
    """Conserva visible el destino hasta que el reproductor lo alcance."""
    return posicion_actual if destino_pendiente is None else destino_pendiente


def posicion_confiable(ultima_confiable, lectura, tolerancia_ms) -> int:
    """Descarta una lectura que retrocede sin una orden de salto."""
    if ultima_confiable is not None and lectura < ultima_confiable - tolerancia_ms:
        return ultima_confiable
    return lectura


def destino_vigente(destino_pendiente, edad_ms, tope_ms):
    """Conserva un destino pendiente solo durante un tiempo acotado."""
    if destino_pendiente is None or edad_ms > tope_ms:
        return None
    return destino_pendiente


def accion_play_pausa(estado, hay_medio, intencion_reproducir,
                      orden_reciente=False) -> str:
    """Decide el transporte sin depender de enums ni estados transitorios."""
    if not hay_medio:
        return "cargar"
    if estado in {"ended", "stopped", "error", "nothingspecial"}:
        return "cargar"
    if orden_reciente and ((estado == "playing" and not intencion_reproducir)
                           or (estado == "paused" and intencion_reproducir)):
        return "en_curso"
    if estado == "playing":
        return "pausar"
    if estado == "paused":
        return "reanudar"
    # Opening y buffering aún no reflejan la orden previa: nunca recargan.
    return "pausar" if intencion_reproducir else "reanudar"
