"""Mensajes accesibles para fallos al consultar datos por red."""

from __future__ import annotations


def mensaje_de_fallo(motivo) -> str:
    """Convierte el motivo de un fallo de red en un mensaje para el usuario."""
    texto = str(motivo or "").lower()

    if any(señal in texto for señal in (
            "429", "too many requests", "sign in to confirm", "not a bot")):
        return ("El servicio está recibiendo demasiadas solicitudes. "
                "Vuelve a intentarlo en unos minutos.")
    if any(señal in texto for señal in (
            "timeout", "timed out", "connection", "getaddrinfo", "network")):
        return ("No se pudo consultar el vídeo porque la red no responde. "
                "Comprueba la conexión e inténtalo de nuevo.")
    if any(señal in texto for señal in (
            "not available", "private video", "unavailable", "removed")):
        return ("El vídeo no está disponible. Comprueba la dirección o que no "
                "sea privado.")
    return "No se pudo consultar la información del vídeo. Inténtalo de nuevo más tarde."
