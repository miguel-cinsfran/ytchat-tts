"""Genera los WAV de retroalimentación con stdlib (wave + struct + math).

Uso:  python sound_gen.py  [--forzar]  [--destino CARPETA]
"""

import math
import struct
import wave
from pathlib import Path


SR       = 44100
BITS     = 16
CANALES  = 2         # Contenedor estéreo aunque el contenido sea dual-mono:
                     # permite sustituir por WAV estéreo sin cambiar código.
AMP      = 0.55      # Margen sobre 1.0 para evitar clipping al sumar ondas.
CARPETA  = Path(__file__).parent / "sounds"

C4, D4, E4, F4, G4, A4, B4 = 261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88
C5, D5, E5, F5, G5, A5, B5 = 523.25, 587.33, 659.25, 698.46, 783.99, 880.00, 987.77
C6 = 1046.50


# ── Primitivas ────────────────────────────────────────────────────────────────

def _seno(freq, dur, amp=AMP, fase=0.0):
    n = int(SR * dur)
    return [amp * math.sin(2 * math.pi * freq * i / SR + fase) for i in range(n)]


def _triangular(freq, dur, amp=AMP):
    # Más cálida que la senoidal y menos agresiva que la cuadrada: apta
    # para tonos de UI que van a sonar muchas veces seguidas.
    n = int(SR * dur)
    p = SR / freq
    out = []
    for i in range(n):
        x = (i % p) / p
        y = 4 * x - 1 if x < 0.5 else 3 - 4 * x
        out.append(amp * y)
    return out


def _silencio(dur):
    return [0.0] * int(SR * dur)


def _suma(*ondas):
    if not ondas:
        return []
    n = min(len(o) for o in ondas)
    return [sum(o[i] for o in ondas) for i in range(n)]


def _concat(*ondas):
    r = []
    for o in ondas:
        r.extend(o)
    return r


def _envolvente(muestras, ataque=0.01, caida=0.05):
    # Fade de entrada y salida: sin esto, el corte brusco al principio y
    # al final produce un click audible en cada reproducción.
    n = len(muestras)
    if n == 0:
        return muestras
    na = min(max(1, int(SR * ataque)), n // 2)
    nc = min(max(1, int(SR * caida)),  n // 2)
    out = list(muestras)
    for i in range(na):
        out[i] *= i / na
    for i in range(nc):
        out[n - 1 - i] *= i / nc
    return out


def _normalizar(muestras, objetivo=0.85):
    if not muestras:
        return muestras
    pico = max(abs(x) for x in muestras)
    if pico < 1e-9:
        return muestras
    k = objetivo / pico
    return [x * k for x in muestras]


def _escribir_wav(path: Path, muestras):
    path.parent.mkdir(parents=True, exist_ok=True)
    maxv = (1 << (BITS - 1)) - 1
    frames = bytearray()
    if CANALES == 1:
        for x in muestras:
            x = max(-1.0, min(1.0, x))
            frames += struct.pack("<h", int(x * maxv))
    else:
        for x in muestras:
            x = max(-1.0, min(1.0, x))
            v = int(x * maxv)
            frames += struct.pack("<hh", v, v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CANALES)
        w.setsampwidth(BITS // 8)
        w.setframerate(SR)
        w.writeframes(bytes(frames))


# ── Diseño de cada sonido ─────────────────────────────────────────────────────
# Cada función devuelve las muestras listas para escribir. Las decisiones
# tonales buscan sobriedad: nada infantil, nada estridente.

def gen_app_inicio():
    # Acorde mayor C-E-G con entrada escalonada: arpegio rápido, cálido.
    d = 0.12
    partes = [
        _envolvente(_triangular(C4, d,        0.40), 0.005, 0.02),
        _envolvente(_triangular(E4, d,        0.40), 0.005, 0.02),
        _envolvente(_triangular(G4, d + 0.10, 0.45), 0.005, 0.12),
    ]
    retardo = int(SR * 0.08)
    n_total = max(retardo * (i + 1) + len(p) for i, p in enumerate(partes))
    mix = [0.0] * n_total
    for i, p in enumerate(partes):
        off = retardo * i
        for j, v in enumerate(p):
            mix[off + j] += v
    return _normalizar(_envolvente(mix, 0.005, 0.08), 0.75)


def gen_conectando():
    # Dos pulsos con hueco: leído como "esperando", no como "listo".
    pulso = _envolvente(_triangular(A4, 0.08, 0.40), 0.008, 0.04)
    return _concat(pulso, _silencio(0.06), pulso, _silencio(0.02))


def gen_conectado():
    a = _triangular(C5, 0.18, 0.35)
    b = _triangular(E5, 0.18, 0.25)
    return _normalizar(_envolvente(_suma(a, b), 0.005, 0.14), 0.8)


def gen_desconectado():
    t1 = _envolvente(_triangular(G4, 0.11, 0.35), 0.005, 0.02)
    t2 = _envolvente(_triangular(E4, 0.12, 0.30), 0.005, 0.08)
    return _concat(t1, t2)


def gen_mensaje():
    # Amplitud baja y duración corta porque suena potencialmente cientos
    # de veces por sesión: cualquier cosa más notable cansa rapidísimo.
    return _normalizar(_envolvente(_seno(G5, 0.06, 0.22), 0.012, 0.048), 0.45)


def gen_superchat():
    # Parcial inarmónico (f * 4.2) imita el espectro de una campana real;
    # sin él suena a órgano y pierde la asociación con "importante".
    f = A5
    partes = [
        _seno(f,       0.28, 0.32),
        _seno(f * 2,   0.28, 0.14),
        _seno(f * 3,   0.20, 0.08),
        _seno(f * 4.2, 0.15, 0.05),
    ]
    return _normalizar(_envolvente(_suma(*partes), 0.003, 0.25), 0.8)


def gen_miembro():
    d = 0.09
    n1 = _envolvente(_triangular(C5, d,        0.35), 0.005, 0.03)
    n2 = _envolvente(_triangular(E5, d,        0.38), 0.005, 0.03)
    n3 = _envolvente(_triangular(G5, d + 0.08, 0.42), 0.005, 0.12)
    return _normalizar(_concat(n1, n2, n3), 0.80)


def gen_error():
    # Dos senos muy cercanos producen un batido (beat) que el oído asocia
    # a aviso; más limpio que un zumbido grave solo.
    a = _seno(175, 0.18, 0.35)
    b = _seno(185, 0.18, 0.35)
    return _normalizar(_envolvente(_suma(a, b), 0.003, 0.08), 0.75)


def gen_pausa():
    n1 = _envolvente(_triangular(G4, 0.06, 0.32), 0.004, 0.02)
    n2 = _envolvente(_triangular(D4, 0.08, 0.32), 0.004, 0.06)
    return _concat(n1, n2)


def gen_reanudar():
    n1 = _envolvente(_triangular(D4, 0.06, 0.32), 0.004, 0.02)
    n2 = _envolvente(_triangular(G4, 0.08, 0.32), 0.004, 0.06)
    return _concat(n1, n2)


def gen_copiar():
    return _normalizar(_envolvente(_triangular(C6, 0.035, 0.30), 0.002, 0.025), 0.55)


def gen_voz_cambiada():
    return _normalizar(_envolvente(_triangular(E5, 0.08, 0.30), 0.006, 0.06), 0.65)


SONIDOS = {
    "app_inicio.wav":   gen_app_inicio,
    "conectando.wav":   gen_conectando,
    "conectado.wav":    gen_conectado,
    "desconectado.wav": gen_desconectado,
    "mensaje.wav":      gen_mensaje,
    "superchat.wav":    gen_superchat,
    "miembro.wav":      gen_miembro,
    "error.wav":        gen_error,
    "pausa.wav":        gen_pausa,
    "reanudar.wav":     gen_reanudar,
    "copiar.wav":       gen_copiar,
    "voz_cambiada.wav": gen_voz_cambiada,
}


# ── Entrada ───────────────────────────────────────────────────────────────────

def generar_todos(destino: Path = CARPETA, sobreescribir: bool = False) -> int:
    destino.mkdir(parents=True, exist_ok=True)
    n = 0
    for nombre, fn in SONIDOS.items():
        ruta = destino / nombre
        if ruta.exists() and not sobreescribir:
            print(f"  [saltar]  {nombre}  (ya existe)")
            continue
        muestras = fn()
        _escribir_wav(ruta, muestras)
        print(f"  [crear ]  {nombre:20s}  {len(muestras):6d} muestras  {ruta.stat().st_size:6d} bytes")
        n += 1
    return n


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Genera los WAV de retroalimentación.")
    ap.add_argument("-f", "--forzar",  action="store_true", help="Sobreescribir existentes")
    ap.add_argument("-d", "--destino", default=str(CARPETA))
    args = ap.parse_args()

    print(f"\n  Generando sonidos en: {args.destino}")
    print("─" * 60)
    n = generar_todos(Path(args.destino), sobreescribir=args.forzar)
    print("─" * 60)
    print(f"  {n} creado(s). {len(SONIDOS) - n} saltado(s).\n")
    if not args.forzar and n < len(SONIDOS):
        print("  Usa --forzar para regenerar los existentes.\n")


if __name__ == "__main__":
    main()
