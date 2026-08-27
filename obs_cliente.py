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


class ObsError(RuntimeError):
    """Fallo entendible producido al comunicarse con OBS."""


def mensaje_de_fallo_obs(motivo):
    """Traduce un motivo técnico a un mensaje breve para el usuario."""
    texto = str(motivo or "").lower()
    if any(clave in texto for clave in
           ("refused", "no connection", "10061", "unreachable", "timed out")):
        return ("No se pudo conectar con OBS. Comprueba que OBS esté abierto y "
                "que su servidor websocket esté activado.")
    if any(clave in texto for clave in ("authentication", "4009", "unauthorized")):
        return "OBS rechazó la contraseña. Vuelve a leerla desde OBS."
    if any(clave in texto for clave in ("601", "already exists")):
        return "Ya existe una fuente con ese nombre en OBS."
    if any(clave in texto for clave in ("600", "not found", "no scene")):
        return "OBS no encuentra la escena o la fuente indicada."
    # Se comparte la forma de avisos_red, pero OBS necesita una taxonomía propia.
    return "OBS no pudo completar la operación. Inténtalo de nuevo."
