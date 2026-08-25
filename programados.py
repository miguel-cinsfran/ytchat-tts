"""Lógica de mensajes programados, sin acceso a la interfaz ni a la red."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile


MINUTOS_MINIMOS = 5  # Piso de prudencia contra el antispam.
SEGUNDOS_ENTRE_ENVIOS = 60  # Si dos vencen a la vez, el segundo espera.
MAX_CARACTERES = 200  # Límite del chat en vivo de YouTube.

VALORES_POR_DEFECTO = {
    "texto": "",
    "minutos_min": 10,
    "minutos_max": 10,
    "activo": False,
    "proximo": 0.0,
}

_URL_RE = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)


def validar_mensaje(texto: str, minutos_min: int, minutos_max: int) -> tuple[str, str]:
    """Valida un mensaje y devuelve un error y un aviso, en ese orden."""
    if not texto.strip():
        return "El mensaje no puede estar vacío.", ""
    if len(texto) > MAX_CARACTERES:
        return (f"El mensaje tiene {len(texto)} caracteres y el máximo son "
                f"{MAX_CARACTERES}."), ""
    if minutos_min < MINUTOS_MINIMOS:
        return "El intervalo mínimo son 5 minutos.", ""
    if minutos_max < minutos_min:
        return "El intervalo máximo no puede ser menor que el mínimo.", ""
    aviso = ""
    # Se avisan las formas habituales de URL; YouTube puede bloquearlas.
    if _URL_RE.search(texto):
        aviso = ("YouTube suele bloquear los enlaces en el chat en vivo. "
                 "Conviene poner el nombre de usuario en vez de la dirección completa.")
    return "", aviso


def calcular_proximo(minutos_min: int, minutos_max: int,
                     ahora: float, aleatorio) -> float:
    """Calcula el instante del próximo envío usando un azar inyectado."""
    if minutos_min == minutos_max:
        return ahora + minutos_min * 60
    return ahora + aleatorio(minutos_min * 60, minutos_max * 60)


def elegir_envio(mensajes: list[dict], ahora: float,
                 ultimo_envio: float | None) -> dict | None:
    """Devuelve el mensaje activo vencido más antiguo que puede enviarse."""
    if ultimo_envio is not None and ahora - ultimo_envio < SEGUNDOS_ENTRE_ENVIOS:
        return None
    vencidos = [
        mensaje for mensaje in mensajes
        if mensaje.get("activo", False) and mensaje.get("proximo", float("inf")) <= ahora
    ]
    return min(vencidos, key=lambda mensaje: mensaje["proximo"]) if vencidos else None


def describir_mensaje(mensaje: dict) -> str:
    """Devuelve la línea accesible que representa un mensaje."""
    estado = "Activo" if mensaje.get("activo", False) else "Pausado"
    minimo = mensaje.get("minutos_min", 10)
    maximo = mensaje.get("minutos_max", minimo)
    if minimo == maximo:
        intervalo = f"cada {minimo} {_unidad_minutos(minimo)}"
    else:
        intervalo = f"entre {minimo} y {maximo} minutos"
    texto = str(mensaje.get("texto", ""))
    if len(texto) > 60:
        texto = texto[:57] + "..."
    return f"{estado}, {intervalo}: {texto}"


def _unidad_minutos(valor: int) -> str:
    return "minuto" if valor == 1 else "minutos"


def describir_proximo(mensajes: list[dict], ahora: float) -> str:
    """Describe cuándo vence el siguiente mensaje activo."""
    activos = [
        mensaje for mensaje in mensajes
        if mensaje.get("activo", False) and "proximo" in mensaje
    ]
    if not activos:
        return ""
    restante = min(mensaje["proximo"] for mensaje in activos) - ahora
    if restante < 60:
        return "Próximo mensaje programado en menos de un minuto"
    minutos = math.ceil(restante / 60)
    unidad = "minuto" if minutos == 1 else "minutos"
    return f"Próximo mensaje programado en {minutos} {unidad}"


def _normalizar_mensaje(mensaje: dict) -> dict:
    resultado = dict(VALORES_POR_DEFECTO)
    resultado.update(mensaje)
    return resultado


def cargar(ruta) -> list[dict]:
    """Carga mensajes y devuelve una lista segura aunque el archivo esté roto."""
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        if not isinstance(datos, list):
            return []
        return [_normalizar_mensaje(mensaje) for mensaje in datos
                if isinstance(mensaje, dict)]
    except Exception:
        return []


def guardar(ruta, mensajes: list[dict]) -> None:
    """Guarda mensajes mediante un temporal para conservar el archivo anterior."""
    ruta = os.fspath(ruta)
    directorio = os.path.dirname(os.path.abspath(ruta))
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directorio,
                prefix="mensajes_programados_", suffix=".tmp", delete=False) as archivo:
            temporal = archivo.name
            json.dump(mensajes, archivo, ensure_ascii=False, indent=2)
            archivo.write("\n")
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, ruta)
        temporal = None
    finally:
        if temporal is not None:
            try:
                os.unlink(temporal)
            except OSError:
                pass
