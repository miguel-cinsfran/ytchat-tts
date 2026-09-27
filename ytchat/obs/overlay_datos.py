"""Datos y transformaciones puras del panel de chat."""

PALETA_NOMBRES = (
    "#ED8068", "#5FBFA8", "#E0AE4E", "#8FB8E8", "#C79BE0", "#9CC97E",
    "#F0908A", "#6FD0C4", "#D8C06A", "#B0A8F0", "#E3A277", "#7FC8E8",
)
COLOR_YOUTUBE = "#ED8068"
COLOR_TIKTOK = "#3FB8A8"
COLOR_DORADO = "#E0AE4E"
COLOR_CUERPO = "#EDEAE7"
FONDO_PEOR = "#302E2C"


def color_de_nombre(nombre: str) -> str:
    h = 2166136261
    for caracter in nombre:
        h = ((h ^ ord(caracter)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    return PALETA_NOMBRES[h % len(PALETA_NOMBRES)]


def inicial_de(nombre: str) -> str:
    limpio = (nombre or "").strip()
    return limpio[0].upper() if limpio else "?"


def evento_de_mensaje(autor: str, texto: str, plataforma: str,
                      monto=None) -> dict:
    if plataforma not in ("youtube", "tiktok"):
        raise ValueError("la plataforma debe ser youtube o tiktok")
    return {
        "autor": autor,
        "texto": texto,
        "plataforma": plataforma,
        "monto": monto,
    }


def relacion_de_contraste(color_a: str, color_b: str) -> float:
    def luminancia(color):
        valores = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        lineales = [
            valor / 12.92 if valor <= 0.03928
            else ((valor + 0.055) / 1.055) ** 2.4
            for valor in valores
        ]
        return 0.2126 * lineales[0] + 0.7152 * lineales[1] + 0.0722 * lineales[2]

    una, otra = luminancia(color_a), luminancia(color_b)
    claro, oscuro = max(una, otra), min(una, otra)
    return (claro + 0.05) / (oscuro + 0.05)
