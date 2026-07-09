"""Formateo del estado de sesión que anuncia F2 (lógica pura, sin wx).

Inspirado en el `status_formatter` de bellbird (otro proyecto del dueño): una
función pura toma un snapshot inmutable de la sesión y un conjunto de
componentes activos (toggles) y arma la frase en español. Aislado aquí para
configurarlo y probarlo sin GUI; qué se anuncia se elige en
Preferencias → Estado (F2).

Antes F2 decía cosas internas del TTS (cola, velocidad, volumen) poco útiles
para quien mira un directo. Ahora, por defecto, prioriza los datos del
contenido: estado, título, canal, espectadores, mensajes leídos y aportes; lo
técnico queda disponible pero desactivado.
"""

from __future__ import annotations

from dataclasses import dataclass


# Códigos de tipo de conexión → etiqueta legible.
_TIPO_TXT = {
    "live_youtube": "Directo de YouTube",
    "live_tiktok":  "Directo de TikTok",
    "vod":          "Vídeo",
    "upcoming":     "Directo programado",
}


@dataclass(frozen=True)
class SnapshotSesion:
    """Foto inmutable de la sesión para formatear. Los campos que no apliquen
    van en su valor «vacío» (None, "", 0) y su componente se omite."""
    conectado: bool = False
    tipo: str = ""              # clave de _TIPO_TXT, o ""
    titulo: str = ""
    canal: str = ""
    espectadores: int | None = None
    mensajes_leidos: int = 0
    aportes: int = 0            # nº de Super Chats (YouTube) o regalos (TikTok)
    total_aportes: str = ""     # ya formateado (p. ej. "US$12.50"), "" si no hay
    en_cola: int = 0
    voz_velocidad: int = 0
    voz_volumen: int = 0
    lectura_silenciada: bool = False


# Orden canónico de los componentes: estado → contenido → actividad → ajustes.
COMPONENTES: tuple[str, ...] = (
    "estado",
    "titulo",
    "canal",
    "espectadores",
    "mensajes_leidos",
    "aportes",
    "en_cola",
    "voz",
    "lectura_silenciada",
)

# Activos por defecto: lo relevante para quien mira un directo. Lo técnico
# (cola, voz) queda disponible pero apagado, porque el dueño lo ve irrelevante.
ACTIVOS_DEFECTO: frozenset[str] = frozenset({
    "estado", "titulo", "canal", "espectadores", "mensajes_leidos", "aportes",
    "lectura_silenciada",
})

# Etiquetas para el editor de Preferencias.
ETIQUETAS = {
    "estado":             "Estado de conexión y tipo",
    "titulo":             "Título del vídeo o directo",
    "canal":              "Canal o autor",
    "espectadores":       "Espectadores ahora",
    "mensajes_leidos":    "Mensajes leídos",
    "aportes":            "Super Chats / regalos",
    "en_cola":            "Mensajes en cola de lectura",
    "voz":                "Velocidad y volumen de la voz",
    "lectura_silenciada": "Aviso de lectura silenciada",
}


def _fmt_num(n) -> str:
    """Miles con punto al estilo español: 30044 → «30.044»."""
    try:    return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError): return str(n)


def _render(nombre: str, s: SnapshotSesion, largo: bool) -> str:
    """Un componente a texto, o "" si no hay dato que mostrar."""
    if nombre == "estado":
        if not s.conectado:
            return "Desconectado"
        return _TIPO_TXT.get(s.tipo, "Conectado")

    if nombre == "titulo":
        t = (s.titulo or "").strip()
        if not t:
            return ""
        return f"Título: {t}" if largo else t

    if nombre == "canal":
        c = (s.canal or "").strip()
        return (f"Canal: {c}" if c else "")

    if nombre == "espectadores":
        if s.espectadores is None:
            return ""
        n = _fmt_num(s.espectadores)
        # En un directo es el nº de espectadores AHORA; en un vídeo, las vistas
        # totales (números distintos, no confundir).
        en_directo = s.tipo in ("live_youtube", "live_tiktok")
        palabra = "espectadores" if en_directo else "vistas"
        return f"{palabra.capitalize()}: {n}" if largo else f"{n} {palabra}"

    if nombre == "mensajes_leidos":
        n = _fmt_num(s.mensajes_leidos)
        return f"Mensajes leídos: {n}" if largo else f"{n} leídos"

    if nombre == "aportes":
        if s.aportes <= 0:
            return ""
        # «Super Chats» en YouTube, «regalos» en TikTok.
        palabra = "regalos" if s.tipo == "live_tiktok" else "Super Chats"
        base = f"{s.aportes} {palabra}"
        if s.total_aportes:
            base += f" ({s.total_aportes})"
        return f"Aportes: {base}" if largo else base

    if nombre == "en_cola":
        n = _fmt_num(s.en_cola)
        return f"En cola: {n}" if largo else f"{n} en cola"

    if nombre == "voz":
        return (f"Voz: velocidad {s.voz_velocidad:+d}, volumen {s.voz_volumen}%")

    if nombre == "lectura_silenciada":
        return "Lectura silenciada" if s.lectura_silenciada else ""

    return ""


def formatear_estado(snap: SnapshotSesion, toggles, modo: str = "corto") -> str:
    """Frase de estado a partir del snapshot y los componentes activos.

    modo="corto": una frase con «; » entre componentes y punto final.
    modo="largo": una línea por componente («Etiqueta: valor»).
    Función pura y determinista; los componentes sin dato se omiten.
    """
    partes = []
    for nombre in COMPONENTES:
        if nombre not in toggles:
            continue
        txt = _render(nombre, snap, largo=(modo == "largo"))
        if txt:
            partes.append(txt)
    if not partes:
        return ""
    if modo == "largo":
        return "\n".join(partes)
    return "; ".join(partes) + "."
