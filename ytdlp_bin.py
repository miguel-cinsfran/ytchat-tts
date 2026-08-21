"""Localiza y actualiza el ejecutable independiente de yt-dlp."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import NamedTuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL_API_RELEASES = (
    "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
)
USER_AGENT = "ytchat-tts/2.0"
NOMBRE_BINARIO = "yt-dlp.exe"
NOMBRE_FIRMAS = "SHA2-256SUMS"
SUBDIRECTORIO_DATOS = "YTChat TTS"
TIEMPO_ESPERA = 30


class ResultadoDescarga(NamedTuple):
    """Resultado que se puede mostrar sin propagar errores de red."""

    correcta: bool
    motivo: str


def _ruta_actualizada() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / SUBDIRECTORIO_DATOS / NOMBRE_BINARIO
    return Path.home() / SUBDIRECTORIO_DATOS / NOMBRE_BINARIO


def _ruta_del_paquete() -> Path:
    return Path(sys.executable).resolve().parent / NOMBRE_BINARIO


def ruta_ytdlp() -> str | None:
    """Devuelve la copia actualizada o la que viaja junto al ejecutable."""
    for ruta in (_ruta_actualizada(), _ruta_del_paquete()):
        if ruta.is_file():
            return str(ruta)
    return None


def version_ytdlp(ruta: str | os.PathLike) -> str:
    """Lee la versión de un ejecutable sin abrir una ventana de consola."""
    try:
        resultado = subprocess.run(
            [str(ruta), "--version"],
            capture_output=True,
            text=True,
            timeout=TIEMPO_ESPERA,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if resultado.returncode:
        return ""
    return resultado.stdout.strip()


def ultima_version_ytdlp() -> tuple[str, str, str] | None:
    """Devuelve versión, descarga del ejecutable y descarga de sus firmas."""
    try:
        solicitud = Request(URL_API_RELEASES, headers={"User-Agent": USER_AGENT})
        with urlopen(solicitud, timeout=TIEMPO_ESPERA) as respuesta:
            datos = json.load(respuesta)
        activos = {activo["name"]: activo for activo in datos["assets"]}
        ejecutable = activos[NOMBRE_BINARIO]["browser_download_url"]
        firmas = activos[NOMBRE_FIRMAS]["browser_download_url"]
        return datos["tag_name"], ejecutable, firmas
    except (HTTPError, URLError, OSError, KeyError, TypeError, ValueError,
            json.JSONDecodeError):
        return None


def firma_sha256(texto: str, nombre: str) -> str:
    """Extrae la firma de un archivo SHA2-256SUMS para un nombre concreto."""
    nombre = str(nombre).strip()
    for linea in texto.splitlines():
        partes = linea.strip().split(None, 1)
        if len(partes) != 2:
            continue
        firma, archivo = partes
        if archivo.lstrip("*").strip() == nombre:
            return firma.lower()
    return ""


def _descargar_archivo(url: str, destino: Path) -> None:
    solicitud = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(solicitud, timeout=TIEMPO_ESPERA) as respuesta:
        with destino.open("wb") as archivo:
            while True:
                bloque = respuesta.read(1024 * 1024)
                if not bloque:
                    break
                archivo.write(bloque)


def descargar_ytdlp(url: str, firma: str, destino: str | os.PathLike) -> ResultadoDescarga:
    """Descarga, verifica y reemplaza un ejecutable sin ejecutar el temporal."""
    if not url.lower().startswith("https://"):
        return ResultadoDescarga(False, "la descarga exige una URL https")
    destino = Path(destino)
    temporal = None
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
                prefix=".yt-dlp-", suffix=".tmp", dir=destino.parent,
                delete=False) as archivo:
            temporal = Path(archivo.name)
        _descargar_archivo(url, temporal)
        resumen = hashlib.sha256()
        with temporal.open("rb") as archivo:
            for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
                resumen.update(bloque)
        if resumen.hexdigest().lower() != firma.strip().lower():
            return ResultadoDescarga(False, "la firma SHA-256 no coincide")
        os.replace(temporal, destino)
        temporal = None
        return ResultadoDescarga(True, "yt-dlp actualizado")
    except (OSError, HTTPError, URLError, ValueError) as error:
        return ResultadoDescarga(False, f"no se pudo descargar yt-dlp: {error}")
    finally:
        if temporal is not None:
            try:
                temporal.unlink()
            except OSError:
                pass


def asegurar_ytdlp(destino: str | os.PathLike | None = None) -> ResultadoDescarga:
    """Asegura una copia local y no descarga si ya existe un binario."""
    if destino is None:
        destino = _ruta_actualizada()
    destino = Path(destino)
    if ruta_ytdlp() is not None:
        return ResultadoDescarga(True, "yt-dlp ya está disponible")
    ultima = ultima_version_ytdlp()
    if ultima is None:
        return ResultadoDescarga(False, "no se pudo consultar la última versión")
    _, url_ejecutable, url_firmas = ultima
    try:
        solicitud = Request(url_firmas, headers={"User-Agent": USER_AGENT})
        with urlopen(solicitud, timeout=TIEMPO_ESPERA) as respuesta:
            texto_firmas = respuesta.read().decode("utf-8")
    except (HTTPError, URLError, OSError, UnicodeError):
        return ResultadoDescarga(False, "no se pudieron descargar las firmas")
    firma = firma_sha256(texto_firmas, NOMBRE_BINARIO)
    if not firma:
        return ResultadoDescarga(False, "no se encontró la firma de yt-dlp.exe")
    return descargar_ytdlp(url_ejecutable, firma, destino)
