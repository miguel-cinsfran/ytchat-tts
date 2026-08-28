"""Frases del estado y las acciones de transmisión de OBS."""

from estado_sesion import _duracion


def frase_transmision(activa, segundos, perdidos, totales) -> str:
    """Describe el estado de la transmisión sin ruido innecesario."""
    if not activa:
        return "No estás transmitiendo"
    frase = f"Transmitiendo desde hace {_duracion(int(segundos))}"
    if perdidos:
        frase += f", {int(perdidos)} fotogramas perdidos"
    return frase


def frase_grabacion(activa, en_pausa, codigo_tiempo) -> str:
    """Describe el estado de la grabación con el tiempo útil de OBS."""
    if not activa:
        return "No estás grabando"
    tiempo = str(codigo_tiempo).split(".", 1)[0]
    return (f"Grabación en pausa, {tiempo}" if en_pausa
            else f"Grabando, {tiempo}")


def frase_resultado(accion) -> str:
    """Traduce una acción de OBS a su confirmación audible."""
    return {
        "transmision_iniciada": "Transmisión iniciada",
        "transmision_detenida": "Transmisión detenida",
        "grabacion_iniciada": "Grabación iniciada",
        "grabacion_detenida": "Grabación detenida",
        "grabacion_en_pausa": "Grabación en pausa",
        "grabacion_reanudada": "Grabación reanudada",
    }[accion]
