"""Decisiones puras para la caché del audio esclavo."""

from pathlib import Path


TAMANIO_MINIMO = 65536


def ruta_de_cache(carpeta, video_id, extension="webm") -> Path:
    """Devuelve la ruta reservada al audio de un vídeo."""
    return Path(carpeta) / f"{video_id}.{extension}"


def esclavo_a_usar(ruta_local, url_red, minimo=TAMANIO_MINIMO) -> str:
    """Prefiere el audio local solo cuando está completo."""
    if ruta_local is not None:
        ruta = Path(ruta_local)
        try:
            if ruta.is_file() and ruta.stat().st_size >= minimo:
                return str(ruta)
        except OSError:
            pass
    return url_red


def sobrantes_de_cache(entradas, tope) -> tuple:
    """Devuelve las rutas más antiguas que exceden el tope."""
    ordenadas = sorted(entradas, key=lambda entrada: entrada[1])
    return tuple(ruta for ruta, _marca in ordenadas[:-tope or None])


def escalones_de_progreso(anterior, actual, escalones=(25, 50, 75)) -> tuple:
    """Devuelve los avisos de progreso que se cruzaron una sola vez."""
    previo = -1 if anterior is None else anterior
    cruzados = tuple(escalon for escalon in escalones if previo < escalon <= actual)
    return cruzados[-1:]


def sobrantes_por_tamanio(entradas, tope_bytes) -> tuple:
    """Devuelve las rutas más antiguas que exceden el tamaño permitido."""
    if tope_bytes <= 0:
        return tuple(ruta for ruta, _tamanio, _fecha in entradas)
    total = sum(tamanio for _ruta, tamanio, _fecha in entradas)
    sobrantes = []
    for ruta, tamanio, _fecha in sorted(entradas, key=lambda entrada: entrada[2]):
        if total <= tope_bytes:
            break
        sobrantes.append(ruta)
        total -= tamanio
    return tuple(sobrantes)
