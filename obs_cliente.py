"""Cliente sincrónico para el servidor websocket de OBS Studio."""

import base64
import hashlib
import json
import os
from dataclasses import dataclass


RUTA_CONFIG_OBS = os.path.join(
    os.environ.get("APPDATA", ""),
    "obs-studio",
    "plugin_config",
    "obs-websocket",
    "config.json",
)


@dataclass(frozen=True)
class AjustesObs:
    activo: bool = False
    puerto: int = 4455
    password: str = ""


def leer_ajustes(ruta=None):
    """Lee la configuración de OBS sin modificarla."""
    try:
        with open(ruta or RUTA_CONFIG_OBS, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return AjustesObs(
            activo=bool(datos.get("server_enabled", False)),
            puerto=int(datos.get("server_port", 4455)),
            password=str(datos.get("server_password", "")),
        )
    except (OSError, ValueError, TypeError, KeyError):
        return AjustesObs()


def respuesta_auth(password, salt, challenge):
    """Calcula la respuesta de autenticación exigida por OBS."""
    secreto = base64.b64encode(
        hashlib.sha256((password + salt).encode("utf-8")).digest()
    ).decode("ascii")
    return base64.b64encode(
        hashlib.sha256((secreto + challenge).encode("utf-8")).digest()
    ).decode("ascii")
