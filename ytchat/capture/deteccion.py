"""Clasificación del tipo de vídeo de YouTube (directo, próximo, VOD).

Funciones PURAS, sin red: reciben el HTML del watch o la respuesta de la API y
deciden qué es. La descarga del HTML vive en `main.py` (con red); aquí solo se
parsea, para poder testearlo sin Windows ni conexión, al estilo de `montos.py`.

Tipos devueltos:
  - "live"        directo emitiéndose ahora mismo (hay chat en vivo por pytchat).
  - "upcoming"    directo programado que aún no empezó (no hay chat todavía).
  - "vod"         vídeo subido o directo ya terminado (solo comentarios).
  - "desconocido" no se pudo determinar (el llamador decide el fallback).
"""

from __future__ import annotations

import re

LIVE = "live"
UPCOMING = "upcoming"
VOD = "vod"
DESCONOCIDO = "desconocido"

# Banderas dentro de videoDetails de ytInitialPlayerResponse. Se buscan con
# regex tolerante (espacios opcionales, true/false) sin parsear todo el JSON:
# el HTML del watch es enorme y solo nos interesan estas tres claves.
_RE_IS_LIVE      = re.compile(r'"isLive"\s*:\s*(true|false)')
_RE_IS_UPCOMING  = re.compile(r'"isUpcoming"\s*:\s*(true|false)')
_RE_IS_LIVE_CONT = re.compile(r'"isLiveContent"\s*:\s*(true|false)')
# Señal redundante presente en algunas respuestas; refuerza la decisión.
_RE_BROADCAST    = re.compile(r'"liveBroadcastContent"\s*:\s*"(live|upcoming|none)"')


def _bandera(rx: re.Pattern, html: str) -> bool | None:
    m = rx.search(html)
    if not m:
        return None
    return m.group(1) == "true"


def clasificar_desde_html(html: str) -> str:
    """Determina el tipo a partir del HTML del watch de YouTube.

    Prioridad: directo en curso > programado > VOD. Si no hay ninguna señal
    fiable, devuelve "desconocido" para que el llamador use otro método.
    """
    if not html:
        return DESCONOCIDO

    is_live     = _bandera(_RE_IS_LIVE, html)
    is_upcoming = _bandera(_RE_IS_UPCOMING, html)

    mb = _RE_BROADCAST.search(html)
    broadcast = mb.group(1) if mb else None

    if is_live is True or broadcast == "live":
        return LIVE
    if is_upcoming is True or broadcast == "upcoming":
        return UPCOMING

    # Si vimos cualquier bandera de videoDetails (aunque sea false) o el
    # broadcast es "none", es un vídeo normal o un directo terminado: VOD.
    if (is_live is not None or is_upcoming is not None
            or _bandera(_RE_IS_LIVE_CONT, html) is not None
            or broadcast == "none"):
        return VOD

    return DESCONOCIDO


def clasificar_desde_api(live_broadcast_content: str | None) -> str:
    """Traduce el campo `snippet.liveBroadcastContent` de la Data API.

    Valores oficiales: "live", "upcoming" y "none". Cualquier otra cosa
    (incluido None o cadena vacía) se considera no determinable.
    """
    v = (live_broadcast_content or "").strip().lower()
    if v == "live":
        return LIVE
    if v == "upcoming":
        return UPCOMING
    if v == "none":
        return VOD
    return DESCONOCIDO


def tiene_chat_en_vivo(tipo: str) -> bool:
    """¿Conviene arrancar la captura del chat (pytchat) para este tipo?"""
    return tipo in (LIVE, DESCONOCIDO)
