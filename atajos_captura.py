"""Decisiones y textos de la captura de atajos."""

import config as cfg


_NOMBRE_TECLA_MOSTRAR = {
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "enter": "Enter",
    "left": "Left", "right": "Right", "up": "Up", "down": "Down",
    "space": "Space",
}
_AREA_AYUDA = {
    "ctrl": "Debe ser Ctrl y una tecla (por ejemplo Ctrl+P).",
    "alt": "Debe ser Alt y una tecla (por ejemplo Alt+C).",
    "f": "Debe ser una tecla de función, de F1 a F12.",
}
_ETIQUETAS = {
    "rep_play": "Reproducir o pausa", "rep_retro": "Retroceder 1 minuto",
    "rep_avanz": "Avanzar 1 minuto", "rep_detener": "Detener vídeo",
    "rep_mute": "Silenciar o activar audio",
    "rep_vol_menos": "Bajar volumen del reproductor",
    "rep_vol_mas": "Subir volumen del reproductor",
    "descargas_abrir": "Abrir el gestor de descargas",
    "pantalla_completa": "Pantalla completa", "conectar": "Conectar",
    "desconectar": "Desconectar", "enviar_chat": "Enviar mensaje al chat",
    "ir_lista": "Ir a la lista del panel actual", "salir": "Salir de la aplicación",
    "pausa": "Pausar o reanudar lectura", "detener_tts": "Detener voz actual",
    "velocidad_menos": "Bajar velocidad (fija)",
    "velocidad_mas": "Subir velocidad (fija)",
    "volumen_menos": "Bajar volumen del TTS (fijo)",
    "volumen_mas": "Subir volumen del TTS (fijo)",
    "silenciar_lectura": "Silenciar lectura TTS",
    "silenciar_sonidos": "Silenciar sonidos", "anunciar_estado": "Anunciar estado",
    "region_siguiente": "Región siguiente", "region_anterior": "Región anterior",
}


def mostrar_atajo(valor: str) -> str:
    """Devuelve el texto legible de un atajo."""
    if not valor:
        return "(sin asignar)"
    partes = [_NOMBRE_TECLA_MOSTRAR.get(parte, parte.upper())
              for parte in valor.split("+")]
    return "+".join(partes)


def etiqueta_boton(etiqueta: str, valor: str) -> str:
    """Devuelve la etiqueta completa de un botón de atajo."""
    return f"{etiqueta}: {mostrar_atajo(valor)}"


def texto_de_espera(etiqueta: str, ayuda_area: str) -> str:
    """Devuelve el anuncio para entrar en modo captura."""
    return (f"Pulsá la combinación para {etiqueta}. {ayuda_area} "
            "Enter la deja sin atajo. Escape cancela.")


def resolver(accion: str, combo: str | None,
             valores: dict[str, str]) -> tuple[str, str | None, str]:
    """Decide qué hacer con una combinación y construye su anuncio."""
    etiqueta = _ETIQUETAS.get(accion, accion.replace("_", " ").capitalize())
    if combo is None:
        return "desactivado", "", f"{etiqueta} sin atajo. Desactivado."

    normalizado = cfg._normalizar_atajo(combo)
    if normalizado is None:
        return "rechazado", None, "Esa combinación no es válida."
    if not cfg.atajo_valido_para_area(accion, normalizado):
        ayuda = _AREA_AYUDA.get(cfg.ATAJOS_AREA.get(accion), "")
        return "rechazado", None, f"No vale aquí. {ayuda}"

    for otra, valor in valores.items():
        if otra != accion and valor and valor == normalizado:
            otra_etiqueta = _ETIQUETAS.get(
                otra, otra.replace("_", " ").capitalize())
            return "rechazado", None, f"Ya lo usa: {otra_etiqueta}. Elige otra."
    return "capturado", normalizado, (
        f"Capturado: {mostrar_atajo(normalizado)}. Guardado.")
