"""Hilo TTS (SAPI5) y sanitización de texto.

Speak se lanza en modo asíncrono con WaitUntilDone en tramos de 100 ms,
lo que permite interrumpir un mensaje en curso (Alt+D) insertando un
purge entre tramos.
"""

from __future__ import annotations

import threading
import queue
import logging
import re
import time

logger = logging.getLogger(__name__)

_STOP = object()

SVSF_ASYNC        = 1
SVSF_PURGE_BEFORE = 2
SVSF_IS_NOT_XML   = 16   # evita que '<' al inicio se interprete como XML SAPI
_SPEAK_FLAGS      = SVSF_ASYNC | SVSF_IS_NOT_XML


# ── Sanitización de texto ────────────────────────────────────────────────────

_EMOJI = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF"
    "\U00002702-\U000027B0\U0001F1E0-\U0001F1FF"
    "\u2600-\u2B55\u200d\ufe0f\u3030]+",
    flags=re.UNICODE,
)
_URL   = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)
_CTRL  = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_SPACE = re.compile(r"\s+")


def sanitizar(texto: str, emojis: bool, urls: bool, maxlen: int) -> str:
    if not texto:
        return ""
    if urls:   texto = _URL.sub("", texto)
    if emojis: texto = _EMOJI.sub("", texto)
    texto = _CTRL.sub("", texto)
    texto = _SPACE.sub(" ", texto).strip()
    if maxlen > 0 and len(texto) > maxlen:
        t  = texto[:maxlen]
        sp = t.rfind(" ")
        texto = (t[:sp] if sp > maxlen // 2 else t) + "..."
    return texto


def construir_tts(autor: str, mensaje: str, config: dict) -> str:
    autor_limpio = sanitizar(autor, config["limpiar_emojis"], False, 50) or "Usuario"
    fmt = config.get("formato_prefijo", "nombre_mensaje")
    if fmt == "solo_mensaje": return mensaje
    if fmt == "solo_nombre":  return autor_limpio
    return f"{autor_limpio}: {mensaje}"


# ── Conversión WPM → Rate SAPI5 ─────────────────────────────────────────────

def _wpm_a_rate(wpm: int) -> int:
    return max(-10, min(10, round((int(wpm) - 180) / 20)))


# ── Hilo TTS ─────────────────────────────────────────────────────────────────

class TTSWorker(threading.Thread):

    def __init__(self, cola: queue.Queue, config: dict):
        super().__init__(daemon=True, name="TTSWorker")
        self.cola   = cola
        self.config = config
        self._ready  = threading.Event()
        self._error  = None
        self._active = threading.Event()
        self._active.set()
        self._paused = False
        self._cmds   = queue.Queue()
        self._rate   = _wpm_a_rate(config.get("velocidad", 175))
        self._volume = max(0, min(100, int(config.get("volumen", 1.0) * 100)))
        self._purge_pending = threading.Event()

    def run(self):
        self._init_com()
        try:
            self._voz = self._create_voice()
        except Exception as exc:
            self._error = exc
            self._ready.set()
            logger.error("TTSWorker: %s", exc)
            return
        self._ready.set()
        logger.info("TTSWorker listo.")
        _err = 0

        while True:
            self._active.wait()
            self._procesar_comandos()
            try:
                item = self.cola.get(timeout=0.3)
            except queue.Empty:
                self._pump(); continue
            if item is _STOP:
                break
            texto = (item.get("texto_tts") or "").strip()
            if not texto:
                continue
            self._active.wait()
            try:
                self._hablar(texto); _err = 0
            except Exception as exc:
                _err += 1
                if _err <= 5:
                    logger.warning("TTS error: %s", exc)
                elif _err == 6:
                    logger.error("TTS: demasiados errores seguidos.")
        logger.info("TTSWorker terminado.")

    def _hablar(self, texto: str) -> None:
        self._voz.Speak(texto, _SPEAK_FLAGS)
        while True:
            try:
                terminado = bool(self._voz.WaitUntilDone(100))
            except Exception:
                time.sleep(0.1)
                try:    terminado = (self._voz.Status.RunningState == 1)
                except Exception: terminado = True
            if terminado:
                break
            self._procesar_comandos()
            if self._purge_pending.is_set():
                self._purge_pending.clear()
                try:
                    self._voz.Speak("", SVSF_ASYNC | SVSF_PURGE_BEFORE)
                    self._voz.WaitUntilDone(200)
                except Exception: pass
                break
            if not self._active.is_set():
                self._active.wait()

    def _procesar_comandos(self):
        while not self._cmds.empty():
            try:    cmd, val = self._cmds.get_nowait()
            except queue.Empty: break
            try:
                if cmd == "voice":
                    voces = self._voz.GetVoices()
                    if 0 <= val < voces.Count:
                        self._voz.Voice = voces.Item(val)
                        logger.info("Voz cambiada: %s", voces.Item(val).GetDescription())
                elif cmd == "rate":
                    self._rate = max(-10, min(10, int(val)))
                    self._voz.Rate = self._rate
                elif cmd == "rate_delta":
                    self._rate = max(-10, min(10, self._rate + int(val)))
                    self._voz.Rate = self._rate
                elif cmd == "volume":
                    self._volume = max(0, min(100, int(val)))
                    self._voz.Volume = self._volume
                elif cmd == "volume_delta":
                    self._volume = max(0, min(100, self._volume + int(val)))
                    self._voz.Volume = self._volume
                elif cmd == "purge":
                    self._purge_pending.set()
            except Exception as exc:
                logger.warning("Comando %s: %s", cmd, exc)

    def _init_com(self):
        try:
            import pythoncom; pythoncom.CoInitialize()
        except ImportError:
            raise RuntimeError("pywin32 no instalado: pip install pywin32")
        except Exception as exc:
            logger.debug("CoInitialize: %s", exc)

    def _create_voice(self):
        try:    import win32com.client
        except ImportError:
            raise RuntimeError("win32com no disponible: pip install pywin32")
        try:    tts = win32com.client.Dispatch("SAPI.SpVoice")
        except Exception as exc:
            raise RuntimeError(f"No se pudo crear SAPI.SpVoice: {exc}") from exc

        voces = tts.GetVoices()
        if voces.Count == 0:
            raise RuntimeError("No hay voces SAPI5.")
        idx = self._resolve_voice(self.config["voz"], voces)
        if idx is None:
            nombres = "\n".join(f"  [{i}] {voces.Item(i).GetDescription()}" for i in range(voces.Count))
            raise ValueError(f"Voz '{self.config['voz']}' no encontrada.\n{nombres}")

        tts.Voice  = voces.Item(idx)
        tts.Volume = self._volume
        tts.Rate   = self._rate
        logger.info("Voz: %s | Rate: %+d | Vol: %d%%",
                    voces.Item(idx).GetDescription(), tts.Rate, tts.Volume)
        return tts

    def _resolve_voice(self, cfg, voces):
        try:
            idx = int(cfg)
            if 0 <= idx < voces.Count: return idx
            return 0
        except ValueError: pass
        term = str(cfg).lower()
        for i in range(voces.Count):
            if term in voces.Item(i).GetDescription().lower(): return i
        return None

    def _pump(self):
        try:
            import pythoncom; pythoncom.PumpWaitingMessages()
        except Exception: pass

    # ── API pública ──────────────────────────────────────────────────────────

    def esperar_inicio(self, timeout=10.0):
        if not self._ready.wait(timeout=timeout): return False
        if self._error:
            logger.error(str(self._error)); return False
        return True

    def pausar(self):
        if not self._paused:
            self._paused = True; self._active.clear()

    def reanudar(self):
        if self._paused:
            self._paused = False; self._active.set()

    def toggle_pausa(self):
        self.reanudar() if self._paused else self.pausar()

    def esta_pausado(self):
        return self._paused

    def vaciar_cola(self):
        n = 0
        while not self.cola.empty():
            try:    self.cola.get_nowait(); n += 1
            except queue.Empty: break
        if n: logger.info("Cola vaciada: %d mensaje(s).", n)

    def detener(self):
        if self._paused: self._active.set()
        try:    self.cola.put(_STOP)
        except Exception: pass
        self.join(timeout=5.0)

    def detener_actual(self):
        """Interrumpe el mensaje en curso y vacía la cola (Alt+D)."""
        self.vaciar_cola()
        self._cmds.put(("purge", None))

    def cambiar_voz(self, idx: int):
        self._cmds.put(("voice", idx))

    def cambiar_rate(self, delta: int):
        self._cmds.put(("rate_delta", delta))

    def cambiar_volumen(self, delta: int) -> None:
        self._cmds.put(("volume_delta", delta))

    def get_rate(self) -> int:
        return self._rate

    def get_volume(self) -> int:
        return self._volume
