"""Redirige las raíces de `paths` a una carpeta temporal, en un solo punto.

Toda prueba que necesite aislar archivos de datos o de instalación usa este
administrador de contexto en vez de reemplazar `app_dir` por su cuenta. Así,
cuando las dos raíces se separen, se ajusta solo este ayudante.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import paths


@contextmanager
def redirigir_rutas(carpeta):
    """Hace que `carpeta_instalacion` y `carpeta_datos` devuelvan `carpeta`."""
    destino = Path(carpeta)
    with mock.patch.object(paths, "carpeta_instalacion", return_value=destino), \
         mock.patch.object(paths, "carpeta_datos", return_value=destino):
        yield destino
