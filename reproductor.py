"""Reproductor de audio del vídeo/directo, siempre visible y accesible.

Backend: yt-dlp extrae la URL del flujo de audio y libVLC (python-vlc) lo
reproduce. Se eligió VLC porque el backend nativo de Windows (wx.media /
DirectShow) no reproduce de forma fiable los flujos `googlevideo` de YouTube;
VLC sí, y además aguanta directos (HLS/DASH).

Todo degrada tras guardas: si falta python-vlc, libVLC o yt-dlp, el panel
muestra un aviso y el resto de la app funciona igual. El audio del reproductor
se solapa con el TTS; hay botón de silencio para gestionarlo.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

import wx

from gui import anunciar, _T, _tc

logger = logging.getLogger(__name__)


# ── Localización de libVLC (incl. app empaquetada) ───────────────────────────

def _preparar_vlc() -> None:
    """Si la app está empaquetada, apunta python-vlc a la copia de VLC junto al
    .exe (carpeta «vlc»). En desarrollo usa el VLC instalado en el sistema."""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "vlc")
        lib = os.path.join(base, "libvlc.dll")
        if os.path.exists(lib):
            os.environ.setdefault("PYTHON_VLC_LIB_PATH", lib)
            os.environ.setdefault("PYTHON_VLC_MODULE_PATH", os.path.join(base, "plugins"))
            try:
                os.add_dll_directory(base)
            except Exception:
                pass


_preparar_vlc()

try:
    import vlc as _vlc
    _VLC_OK = True
except Exception:
    _vlc = None
    _VLC_OK = False


def ytdlp_disponible() -> bool:
    try:
        import yt_dlp  # noqa: F401
        return True
    except Exception:
        return False


def disponible() -> bool:
    """¿Se puede reproducir? Hacen falta python-vlc (con libVLC) y yt-dlp."""
    return _VLC_OK and ytdlp_disponible()


def _extraer_url_audio(video_id: str) -> str:
    """URL directa del mejor flujo de audio (bloquea; usar en hilo)."""
    import yt_dlp
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    directa = info.get("url")
    if directa:
        return directa
    for f in reversed(info.get("formats", []) or []):
        if f.get("acodec") not in (None, "none") and f.get("url"):
            return f["url"]
    raise RuntimeError("yt-dlp no devolvió ninguna URL de audio")


class ReproductorPanel(wx.Panel):
    """Barra de reproducción siempre visible (no es una pestaña)."""

    def __init__(self, parent, config):
        super().__init__(parent, name="PanelReproductor")
        self._config = config
        self._video_id = ""
        self._cargando = False
        self._listo = disponible()
        self._duracion_ms = 0
        self._vol = 80

        self.SetBackgroundColour(_T.bg)
        self.SetForegroundColour(_T.text)
        if self._listo:
            self._inst = _vlc.Instance("--no-video", "--quiet")
            self._player = self._inst.media_player_new()
            self._build_ui()
        else:
            self._inst = None
            self._player = None
            self._build_aviso()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_aviso(self):
        box = wx.StaticBoxSizer(wx.HORIZONTAL, self, "Reproductor")
        if not _VLC_OK:
            txt = ("Reproductor no disponible: falta VLC. Instala VLC "
                   "(videolan.org) y la librería python-vlc.")
        else:
            txt = "Reproductor no disponible: falta yt-dlp (pip install yt-dlp)."
        lbl = wx.StaticText(self, label=txt, name="AvisoReproductor")
        lbl.SetForegroundColour(_T.dim)
        box.Add(lbl, 1, wx.ALL, 8)
        self.SetSizer(box)

    def _build_ui(self):
        box = wx.StaticBoxSizer(wx.VERTICAL, self, "Reproductor")

        # Fila 1: botones de transporte.
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_play  = wx.Button(self, label="&Reproducir", name="ReproducirPausa")
        self.btn_retro = wx.Button(self, label="&Retroceder 10 s", name="Retroceder")
        self.btn_avanz = wx.Button(self, label="&Avanzar 10 s", name="Avanzar")
        self.btn_stop  = wx.Button(self, label="&Detener", name="DetenerReproduccion")
        self.btn_mute  = wx.Button(self, label="&Silenciar audio", name="SilenciarAudio")
        for b in (self.btn_play, self.btn_retro, self.btn_avanz, self.btn_stop, self.btn_mute):
            b.SetBackgroundColour(_T.btn)
            b.SetForegroundColour(_T.btn_t)
            row.Add(b, 0, wx.RIGHT, 6)
        box.Add(row, 0, wx.ALL, 6)

        # Fila 2: posición + tiempo.
        row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self, label="Posición:", name="EtiquetaPosicion")
        lbl.SetForegroundColour(_T.dim)
        row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.sld_pos = wx.Slider(self, value=0, minValue=0, maxValue=1000,
                                 name="Posición de reproducción")
        _tc(self.sld_pos, bg=_T.surface)
        self.sld_pos.SetToolTip("Flecha derecha avanza, flecha izquierda retrocede.")
        row.Add(self.sld_pos, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.lbl_tiempo = wx.StaticText(self, label="0:00 / 0:00", name="Tiempo")
        self.lbl_tiempo.SetForegroundColour(_T.text)
        row.Add(self.lbl_tiempo, 0, wx.ALIGN_CENTER_VERTICAL)
        box.Add(row, 0, wx.EXPAND | wx.ALL, 6)

        # Fila 3: volumen + estado.
        row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self, label="Volumen:", name="EtiquetaVolumenReproductor")
        lbl.SetForegroundColour(_T.dim)
        row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.sld_vol = wx.Slider(self, value=self._vol, minValue=0, maxValue=100,
                                 name="Volumen del reproductor")
        _tc(self.sld_vol, bg=_T.surface)
        self.sld_vol.SetToolTip("Flecha arriba sube, flecha abajo baja el volumen.")
        self.sld_vol.SetMinSize((160, -1))
        row.Add(self.sld_vol, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        self.lbl_estado = wx.StaticText(self, label="Sin reproducir.", name="EstadoReproductor")
        self.lbl_estado.SetForegroundColour(_T.accent)
        row.Add(self.lbl_estado, 1, wx.ALIGN_CENTER_VERTICAL)
        box.Add(row, 0, wx.EXPAND | wx.ALL, 6)

        self.SetSizer(box)
        # Todos los controles quedan habilitados desde el inicio: NVDA salta los
        # botones deshabilitados, así que mantenerlos activos los hace siempre
        # alcanzables. Cada acción valida por dentro si hay algo que reproducir.

        self.btn_play.Bind(wx.EVT_BUTTON, lambda e: self._toggle_play())
        self.btn_retro.Bind(wx.EVT_BUTTON, lambda e: self._buscar_rel(-10_000))
        self.btn_avanz.Bind(wx.EVT_BUTTON, lambda e: self._buscar_rel(+10_000))
        self.btn_stop.Bind(wx.EVT_BUTTON, lambda e: self._detener())
        self.btn_mute.Bind(wx.EVT_BUTTON, lambda e: self._toggle_mute())
        self.sld_pos.Bind(wx.EVT_SLIDER, self._on_sld_pos)
        self.sld_pos.Bind(wx.EVT_KEY_DOWN, self._on_pos_key)
        self.sld_vol.Bind(wx.EVT_SLIDER, self._on_sld_vol)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)

    # ── API pública (la ventana la llama al conectar) ─────────────────────────

    def anclar_foco(self) -> None:
        """Lleva el foco al primer control del reproductor (para F6)."""
        try:
            if self._listo:
                self.btn_play.SetFocus()
        except Exception:
            pass

    def set_video(self, video_id: str, autoplay: bool = True) -> None:
        self._video_id = video_id or ""
        if not self._listo:
            return
        self._detener(silencioso=True)
        if self._video_id and autoplay:
            self.cargar(reproducir=True)
        else:
            self.lbl_estado.SetLabel("Listo. Pulsa Reproducir.")

    def detener_todo(self) -> None:
        if self._listo:
            self._detener(silencioso=True)

    # ── Carga / reproducción ──────────────────────────────────────────────────

    def cargar(self, reproducir: bool = True):
        if not self._listo:
            anunciar("El reproductor no está disponible.")
            return
        if not self._video_id or self._cargando:
            return
        self._cargando = True
        self.lbl_estado.SetLabel("Cargando audio…")
        anunciar("Cargando audio")
        vid = self._video_id

        def _run():
            try:
                url = _extraer_url_audio(vid)
                wx.CallAfter(self._reproducir_url, url, reproducir, vid)
            except Exception as exc:
                logger.warning("extraer audio: %s", exc)
                wx.CallAfter(self._error_carga)

        threading.Thread(target=_run, daemon=True, name="ReproductorURL").start()

    def _reproducir_url(self, url, reproducir, vid):
        if vid != self._video_id:      # se cambió de vídeo mientras cargaba
            self._cargando = False
            return
        try:
            self._player.set_media(self._inst.media_new(url))
            self._player.audio_set_volume(self._vol)
            if reproducir:
                self._player.play()
                self.btn_play.SetLabel("&Pausa")
                self._timer.Start(500)
        except Exception as exc:
            logger.warning("reproducir: %s", exc)
            self._error_carga()
            return
        self._cargando = False
        self._duracion_ms = 0
        self.lbl_estado.SetLabel("Reproduciendo." if reproducir else "Listo.")
        if reproducir:
            anunciar("Reproduciendo")

    def _error_carga(self):
        self._cargando = False
        import sound_player as _snd
        _snd.reproducir("error")
        self.lbl_estado.SetLabel("No se pudo cargar el audio.")
        anunciar("No se pudo cargar el audio")

    # ── Transporte ──────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if not self._listo or self._player is None:
            return
        st = self._player.get_state()
        if st == _vlc.State.Playing:
            self._player.pause()
            self.btn_play.SetLabel("&Reproducir")
            self._timer.Stop()
            anunciar("Pausa")
        else:
            # Si no hay medio cargado todavía, cargar y reproducir.
            if st in (_vlc.State.NothingSpecial, _vlc.State.Ended, _vlc.State.Stopped, _vlc.State.Error):
                if self._video_id:
                    self.cargar(reproducir=True)
                return
            self._player.play()
            self.btn_play.SetLabel("&Pausa")
            self._timer.Start(500)
            anunciar("Reproduciendo")

    def _detener(self, silencioso: bool = False):
        if self._player is not None:
            try:    self._player.stop()
            except Exception: pass
        if hasattr(self, "_timer"):
            self._timer.Stop()
        if hasattr(self, "btn_play"):
            self.btn_play.SetLabel("&Reproducir")
            self.sld_pos.SetValue(0)
            self.lbl_tiempo.SetLabel("0:00 / 0:00")
        if not silencioso:
            anunciar("Detenido")

    def _buscar_rel(self, delta_ms: int):
        if self._player is None:
            return
        dur = self._player.get_length()
        if dur <= 0:
            anunciar("No se puede buscar en este flujo")
            return
        nueva = min(max(0, self._player.get_time() + delta_ms), dur)
        self._player.set_time(int(nueva))
        anunciar(_fmt_t(nueva))

    def _toggle_mute(self):
        if self._player is None:
            return
        self._player.audio_toggle_mute()
        mute = self._player.audio_get_mute()
        self.btn_mute.SetLabel("Activar audio" if mute else "Silenciar audio")
        anunciar("Audio silenciado" if mute else "Audio activado")

    def ajustar_volumen(self, delta: int):
        self._vol = max(0, min(100, self._vol + delta))
        self.sld_vol.SetValue(self._vol)
        if self._player is not None:
            self._player.audio_set_volume(self._vol)
        anunciar(f"Volumen reproductor {self._vol} por ciento")

    # ── Eventos de los sliders ───────────────────────────────────────────────

    def _on_sld_pos(self, event):
        if self._player is None:
            return
        dur = self._player.get_length()
        if dur <= 0:
            return
        destino = int(self.sld_pos.GetValue() / 1000.0 * dur)
        self._player.set_time(destino)

    def _on_pos_key(self, event):
        k = event.GetKeyCode()
        if k == wx.WXK_RIGHT:
            self._buscar_rel(+5_000)
        elif k == wx.WXK_LEFT:
            self._buscar_rel(-5_000)
        else:
            event.Skip()

    def _on_sld_vol(self, event):
        self._vol = self.sld_vol.GetValue()
        if self._player is not None:
            self._player.audio_set_volume(self._vol)

    def _on_timer(self, event):
        if self._player is None:
            return
        dur = self._player.get_length()
        if dur > 0:
            self._duracion_ms = dur
            pos = self._player.get_time()
            self.sld_pos.SetValue(int(pos / dur * 1000))
            self.lbl_tiempo.SetLabel(f"{_fmt_t(pos)} / {_fmt_t(dur)}")
        st = self._player.get_state()
        if st == _vlc.State.Ended:
            self._detener(silencioso=True)
            anunciar("Fin del audio")


def _fmt_t(ms: int) -> str:
    s = max(0, int(ms) // 1000)
    return f"{s // 60}:{s % 60:02d}"
