"""Formato de trazas del transporte del reproductor."""


def _booleano(valor) -> str:
    return "si" if valor else "no"


def _booleano_vlc(valor) -> str:
    if valor is None:
        return "desconocido"
    return _booleano(valor)


def traza_transporte(estado, accion, hay_medio, intencion_reproducir,
                     puede_pausar, es_buscable) -> str:
    """Arma la traza de una decisión de reproducir o pausar."""
    return (
        f"TRANSPORTE estado={estado} accion={accion} medio={_booleano(hay_medio)} "
        f"intencion={_booleano(intencion_reproducir)} "
        f"puede_pausar={_booleano_vlc(puede_pausar)} "
        f"buscable={_booleano_vlc(es_buscable)}"
    )


def traza_salto(origen, pendiente, posicion, delta_ms, destino, duracion) -> str:
    """Arma la traza de un salto sobre la línea de tiempo."""
    pendiente = "ninguno" if pendiente is None else pendiente
    return (f"SALTO origen={origen} pendiente={pendiente} pos={posicion} "
            f"delta={delta_ms} destino={destino} dur={duracion}")


def traza_sin_barra(origen, duracion) -> str:
    """Arma la traza de un salto sin duración disponible."""
    return f"SALTO_SIN_BARRA origen={origen} dur={duracion}"
