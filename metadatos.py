"""Formateo del panel de información del vídeo (lógica pura, sin wx).

Toma el dict de metadatos que arma `main._metadatos_desde_ytdlp` (lo que trae
yt-dlp en la extracción `process=False`) y lo convierte en el texto, en orden,
que muestra el cuadro de solo lectura. Aislado aquí para poder probarlo sin GUI.
"""

from __future__ import annotations


def _fmt_num(n) -> str:
    """Miles con punto, al estilo español: 30044 → «30.044». Vacío si no es número."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return ""


def _fmt_fecha(yyyymmdd) -> str:
    """«20240131» → «31/01/2024». Vacío si no encaja el formato de yt-dlp."""
    s = str(yyyymmdd or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[6:8]}/{s[4:6]}/{s[0:4]}"
    return ""


def _fmt_duracion(seg) -> str:
    """Segundos → «H:MM:SS» (o «M:SS» si dura menos de una hora). Vacío si <=0."""
    try:
        s = int(seg)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def formatear(meta: dict) -> str:
    """Texto del panel de información, en orden: título, canal, vistas (o
    espectadores si es directo), me gusta, comentarios, fecha, duración y
    descripción. Omite lo que no venga. Devuelve un aviso si no hay nada."""
    if not meta:
        return "Sin información del vídeo."

    lineas = []
    titulo = (meta.get("titulo") or "").strip()
    if titulo:
        lineas.append(titulo)
    canal = (meta.get("canal") or "").strip()
    if canal:
        lineas.append(f"Canal: {canal}")

    en_vivo = bool(meta.get("en_vivo"))
    vistas = _fmt_num(meta.get("vistas"))
    if vistas:
        lineas.append(f"{'Espectadores' if en_vivo else 'Vistas'}: {vistas}")
    me_gusta = _fmt_num(meta.get("me_gusta"))
    if me_gusta:
        lineas.append(f"Me gusta: {me_gusta}")
    comentarios = _fmt_num(meta.get("comentarios"))
    if comentarios:
        lineas.append(f"Comentarios: {comentarios}")

    fecha = _fmt_fecha(meta.get("fecha"))
    if fecha:
        lineas.append(f"Publicado: {fecha}")
    # En un directo la «duración» no tiene sentido (crece en vivo): se omite.
    if not en_vivo:
        dur = _fmt_duracion(meta.get("duracion"))
        if dur:
            lineas.append(f"Duración: {dur}")

    cabecera = "\n".join(lineas) if lineas else "Sin información del vídeo."
    desc = (meta.get("descripcion") or "").strip()
    if desc:
        return f"{cabecera}\n\nDescripción:\n{desc}"
    return cabecera
