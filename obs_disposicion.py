"""Geometría de la disposición del panel en OBS."""

from __future__ import annotations


ANCLAJES: dict[str, int] = {
    "superior-izquierda": 5, "superior-centro": 4, "superior-derecha": 6,
    "centro-izquierda": 1, "centro": 0, "centro-derecha": 2,
    "inferior-izquierda": 9, "inferior-centro": 8, "inferior-derecha": 10,
}


def coordenadas(anclaje, lienzo_ancho, lienzo_alto, margen_pct=2.0):
    if anclaje not in ANCLAJES:
        raise ValueError(f"Anclaje desconocido: {anclaje}")
    margen_x = lienzo_ancho * margen_pct / 100
    margen_y = lienzo_alto * margen_pct / 100
    mascara = ANCLAJES[anclaje]
    x = (margen_x if mascara & 1 else
         lienzo_ancho - margen_x if mascara & 2 else lienzo_ancho / 2)
    y = (margen_y if mascara & 4 else
         lienzo_alto - margen_y if mascara & 8 else lienzo_alto / 2)
    return x, y, mascara


def rectangulo(x, y, ancho, alto, alineacion):
    izquierda = (x if alineacion & 1 else
                 x - ancho if alineacion & 2 else x - ancho / 2)
    arriba = (y if alineacion & 4 else
              y - alto if alineacion & 8 else y - alto / 2)
    return izquierda, arriba, ancho, alto


def _interseccion(a, b):
    izquierda = max(a[0], b[0])
    arriba = max(a[1], b[1])
    derecha = min(a[0] + a[2], b[0] + b[2])
    abajo = min(a[1] + a[3], b[1] + b[3])
    return max(0.0, derecha - izquierda) * max(0.0, abajo - arriba)


def _area(rect):
    return max(0.0, rect[2]) * max(0.0, rect[3])


def solape(rect_a, rect_b) -> float:
    area_b = _area(rect_b)
    return 0.0 if not area_b else _interseccion(rect_a, rect_b) / area_b * 100


def fuera_del_lienzo(rect, lienzo_ancho, lienzo_alto) -> float:
    area = _area(rect)
    if not area:
        return 0.0
    return (area - _interseccion(rect, (0, 0, lienzo_ancho, lienzo_alto))) / area * 100


def anclaje_de(rect, lienzo_ancho, lienzo_alto, margen_pct=2.0,
               tolerancia_pct=0.5) -> str:
    tolerancia_x = lienzo_ancho * tolerancia_pct / 100
    tolerancia_y = lienzo_alto * tolerancia_pct / 100
    for nombre in ANCLAJES:
        x, y, alineacion = coordenadas(nombre, lienzo_ancho, lienzo_alto, margen_pct)
        esperado = rectangulo(x, y, rect[2], rect[3], alineacion)
        if (abs(rect[0] - esperado[0]) <= tolerancia_x and
                abs(rect[1] - esperado[1]) <= tolerancia_y):
            return nombre
    return ""
