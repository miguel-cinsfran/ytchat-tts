"""Reglas puras para redactar mensajes y comentarios."""

MAXIMO_CHAT = 200


def motivo_chat(conectado, es_tiktok, hay_live_chat, hay_sesion) -> str:
    if not conectado:
        return "Conéctate a un directo para escribir en el chat"
    if es_tiktok:
        return "El chat de TikTok no permite escribir desde aquí"
    if not hay_live_chat:
        return "Este vídeo no tiene chat en vivo"
    if not hay_sesion:
        return "Inicia sesión en Configuración de API para escribir en el chat"
    return ""


def motivo_comentario(hay_video, hay_sesion) -> str:
    if not hay_video:
        return "Conéctate a un vídeo para poder comentar"
    if not hay_sesion:
        return "Inicia sesión en Configuración de API para comentar"
    return ""


def validar(texto, maximo) -> str:
    texto_limpio = limpiar(texto)
    if not texto_limpio:
        return "Escribe un mensaje antes de enviar"
    if len(texto_limpio) > maximo:
        return f"El mensaje tiene {len(texto_limpio)} caracteres y el máximo es {maximo}"
    return ""


def limpiar(texto) -> str:
    return texto.strip()


def etiqueta_con_motivo(base, motivo) -> str:
    if not motivo:
        return base
    return f"{base} ({motivo[0].lower()}{motivo[1:]})"
