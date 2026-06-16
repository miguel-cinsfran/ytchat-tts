"""Parseo del importe de los Super Chats.

El `amountString` que entrega YouTube depende de la locale del espectador
que envía el Super Chat: "€15.50", "$10.00", "5,00 €", "1.234,56 €", "¥500"...
Esta lógica vivía dentro de `gui.YTChatFrame._sumar_superchat`, donde no se
podía probar sin instanciar la ventana wx. Extraída aquí queda como función
pura, cubierta por tests, y el GUI solo la invoca.
"""

from __future__ import annotations

import re

# Captura el primer número del importe, admitiendo separadores de millar y
# decimales en formato europeo o anglosajón.
#   - Rama 1: con separadores de millar reales ("1.234,56", "1,234.56").
#   - Rama 2: dígitos seguidos con decimal opcional ("50000", "15.50", "5,00").
# La rama 1 exige al menos un grupo de millar; si no, se cae a la rama 2,
# que NO trunca enteros largos (antes "50000" se leía como 500, rompiendo
# el total en divisas sin decimales como PYG, JPY o KRW).
_NUM_RE = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)")
# El símbolo/código de divisa es el primer tramo que no sea dígito, espacio,
# coma o punto: "€", "$", "US$", "¥", "PYG"...
_DIVISA_RE = re.compile(r"[^\d\s,.]+")


def parsear_monto(monto: str) -> tuple[str, float] | None:
    """Devuelve (divisa, valor) a partir del amountString, o None si no se puede.

    La divisa es "?" cuando no aparece ningún símbolo reconocible.
    """
    if not monto:
        return None
    m = _NUM_RE.search(monto)
    if not m:
        return None
    num = m.group(1)
    if "," in num and "." in num:
        # Formato europeo (1.234,56) vs anglosajón (1,234.56): manda la
        # posición del último separador, que siempre es el decimal.
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        # Solo coma: la tratamos como separador decimal ("5,00").
        num = num.replace(",", ".")
    try:
        valor = float(num)
    except ValueError:
        return None
    divisa_m = _DIVISA_RE.search(monto)
    divisa = divisa_m.group(0).strip() if divisa_m else "?"
    return (divisa or "?", valor)
