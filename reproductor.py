"""Panel reproductor de audio del vídeo, accesible y aislado tras guardas.

Estrategia ligera (junio 2026): `yt-dlp` extrae la URL directa del flujo de
audio (dependencia pip, sin binarios pesados) y `wx.media.MediaCtrl` —que ya
viene en wxPython— lo reproduce, sin DLL externa. Si más adelante el backend
nativo de Windows no traga algún flujo, se puede añadir `python-vlc` como
respaldo sin tocar el resto del panel.

Todo degrada solo: si falta `wx.media` o `yt-dlp`, el panel muestra un aviso y
no rompe nada. El audio del reproductor se solapa con el TTS, así que tiene más
sentido en vídeos subidos que durante tu propio directo.
"""

from __future__ import annotations

import logging
import threading

import wx

from gui import anunciar, _T, _tc

logger = logging.getLogger(__name__)

# wx.media no siempre está disponible (depende del build de wxWidgets). Se
# importa con guarda para que `import reproductor` nunca falle.
try:
    import wx.media as _wxmedia
    _MEDIA_OK = True
except Exception:
    _wxmedia = None
    _MEDIA_OK = False


def ytdlp_disponible() -> bool:
    try:
        import yt_dlp  # noqa: F401
        return True
    except Exception:
        return False


def disponible() -> bool:
    """¿Se puede reproducir? Hace falta wx.media y yt-dlp."""
    return _MEDIA_OK and ytdlp_disponible()


def _extraer_url_audio(video_id: str) -> str:
    """Devuelve la URL directa del mejor flujo de audio (bloquea; usar en hilo)."""
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
    # Algunos formatos traen la url directa en 'url'; si no, buscar en formats.
    directa = info.get("url")
    if directa:
        return directa
    for f in reversed(info.get("formats", []) or []):
        if f.get("acodec") not in (None, "none") and f.get("url"):
            return f["url"]
    raise RuntimeError("yt-dlp no devolvió ninguna URL de audio")


class ReproductorPanel(wx.Panel):
    """Pestaña de reproducción de audio del vídeo conectado."""

    def __init__(self, parent, config):
        super().__init__(parent, name="PanelReproductor")
        self._config = config
        self._video_id = ""
        self._cargando = False
        self._duracion_ms = 0
        self._arrastrando = False
        self._listo = disponible()

        self.SetBackgroundColour(_T.bg)
        self.SetForegroundColour(_T.text)
        if self._listo:
            self._build_ui()
        else:
            self._build_aviso()

    # ── UI cuando no se puede reproducir ──────────────────────────────────────

    def _build_aviso(self):
        vs = wx.BoxSizer(wx.VERTICAL)
        if not _MEDIA_OK:
            txt = ("El reproductor no está disponible: este build de wxPython no "
                   "incluye wx.media.")
        else:
            txt = ("Para reproducir el audio del vídeo hace falta yt-dlp. "
                   "Instálalo con:  pip install yt-dlp")
        lbl = wx.StaticText(self, label=txt, name="AvisoReproductor")
        lbl.SetForegroundColour(_T.dim)
        vs.Add(lbl, 0, wx.ALL, 16)
        self.SetSizer(vs)

    # ── UI normal ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        vs = wx.BoxSizer(wx.VERTICAL)

        self._mc = _wxmedia.MediaCtrl(self, name="ControlMultimedia")
        self._mc.Hide()  # solo audio: no necesitamos área de vídeo.

        self.lbl_estado = wx.StaticText(self, label="Sin audio cargado.",
                                        name="EstadoReproductor")
        self.lbl_estado.SetForegroundColour(_T.accent)
        vs.Add(self.lbl_estado, 0, wx.ALL, 8)

        # Transporte
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_cargar = wx.Button(self, label="&Cargar audio", name="CargarAudio")
        self.btn_play   = wx.Button(self, label="&Reproducir", name="ReproducirPausa")
        self.btn_retro  = wx.Button(self, label="Retroceder 10 s", name="Retroceder")
        self.btn_avanz  = wx.Button(self, label="Avanzar 10 s", name="Avanzar")
        self.btn_stop   = wx.Button(self, label="De&tener", name="DetenerReproduccion")
        for b in (self.btn_cargar, self.btn_play, self.btn_retro,
                  self.btn_avanz, self.btn_stop):
            b.SetBackgroundColour(_T.btn)
            b.SetForegroundColour(_T.btn_t)
            row.Add(b, 0, wx.RIGHT, 6)
        vs.Add(row, 0, wx.ALL, 8)

        # Barra de progreso (flechas izquierda/derecha buscan ±5 s)
        lbl = wx.StaticText(self, label="&Posición:", name="EtiquetaPosicion")
        lbl.SetForegroundColour(_T.dim)
        vs.Add(lbl, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.sld_pos = wx.Slider(self, value=0, minValue=0, maxValue=1000,
                                 name="Posición de reproducción")
        _tc(self.sld_pos, bg=_T.surface)
        vs.Add(self.sld_pos, 0, wx.EXPAND | wx.ALL, 8)

        # Volumen del reproductor (independiente del TTS)
        lbl = wx.StaticText(self, label="&Volumen del reproductor:",
                            name="EtiquetaVolumenReproductor")
        lbl.SetForegroundColour(_T.dim)
        vs.Add(lbl, 0, wx.LEFT | wx.RIGHT, 8)
        self.sld_vol = wx.Slider(self, value=80, minValue=0, maxValue=100,
                                 name="Volumen del reproductor")
        _tc(self.sld_vol, bg=_T.surface)
        vs.Add(self.sld_vol, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizer(vs)
        self._set_transporte(False)

        self.btn_cargar.Bind(wx.EVT_BUTTON, lambda e: self.cargar())
        self.btn_play.Bind(wx.EVT_BUTTON, lambda e: self._toggle_play())
        self.btn_retro.Bind(wx.EVT_BUTTON, lambda e: self._buscar_rel(-10_000))
        self.btn_avanz.Bind(wx.EVT_BUTTON, lambda e: self._buscar_rel(+10_000))
        self.btn_stop.Bind(wx.EVT_BUTTON, lambda e: self._detener())
        self.sld_pos.Bind(wx.EVT_SLIDER, self._on_sld_pos)
        self.sld_vol.Bind(wx.EVT_SLIDER, self._on_sld_vol)
        self._mc.Bind(_wxmedia.EVT_MEDIA_LOADED, self._on_cargado)
        self._mc.Bind(_wxmedia.EVT_MEDIA_FINISHED, self._on_fin)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)

    # ── API pública (la ventana la llama al conectar) ─────────────────────────

    def set_video(self, video_id: str) -> None:
        self._video_id = video_id or ""
        if self._listo:
            self._detener(silencioso=True)
            self.lbl_estado.SetLabel("Pulsa «Cargar audio» para reproducir este vídeo.")

    def detener_todo(self) -> None:
        if self._listo:
            self._detener(silencioso=True)

    # ── Carga ─────────────────────────────────────────────────────────────────

    def cargar(self):
        if not self._listo:
            anunciar("El reproductor no está disponible. Instala yt-dlp.")
            return
        if not self._video_id:
            anunciar("Conecta primero un vídeo")
            return
        if self._cargando:
            return
        self._cargando = True
        self.btn_cargar.Disable()
        self.lbl_estado.SetLabel("Obteniendo audio…")
        anunciar("Obteniendo audio del vídeo")
        vid = self._video_id

        def _run():
            try:
                url = _extraer_url_audio(vid)
                wx.CallAfter(self._cargar_url, url)
            except Exception as exc:
                logger.warning("extraer audio: %s", exc)
                wx.CallAfter(self._error_carga, exc)

        threading.Thread(target=_run, daemon=True, name="ReproductorURL").start()

    def _cargar_url(self, url):
        try:
            ok = self._mc.LoadURI(url) if hasattr(self._mc, "LoadURI") else self._mc.Load(url)
        except Exception as exc:
            self._error_carga(exc)
            return
        if ok is False:
            self._error_carga(RuntimeError("el backend no pudo cargar el flujo"))

    def _error_carga(self, exc):
        self._cargando = False
        self.btn_cargar.Enable()
        import sound_player as _snd
        _snd.reproducir("error")
        self.lbl_estado.SetLabel("No se pudo cargar el audio.")
        anunciar("No se pudo cargar el audio del vídeo")
        logger.debug("error carga reproductor: %s", exc)

    def _on_cargado(self, event):
        self._cargando = False
        self.btn_cargar.Enable()
        self._duracion_ms = max(0, int(self._mc.Length()))
        self._mc.SetVolume(self.sld_vol.GetValue() / 100.0)
        self._set_transporte(True)
        self.lbl_estado.SetLabel(f"Audio listo. Duración: {_fmt_t(self._duracion_ms)}.")
        anunciar(f"Audio listo, duración {_fmt_t(self._duracion_ms)}")

    # ── Transporte ─────────────────────────────────────────────────────────────

    def _set_transporte(self, on: bool):
        for b in (self.btn_play, self.btn_retro, self.btn_avanz, self.btn_stop):
            b.Enable(on)
        self.sld_pos.Enable(on)

    def _toggle_play(self):
        estado = self._mc.GetState()
        if estado == _wxmedia.MEDIASTATE_PLAYING:
            self._mc.Pause()
            self.btn_play.SetLabel("&Reproducir")
            self._timer.Stop()
            anunciar("Pausa")
        else:
            if self._mc.Play():
                self.btn_play.SetLabel("&Pausa")
                self._timer.Start(500)
                anunciar("Reproduciendo")

    def _detener(self, silencioso: bool = False):
        try:
            self._mc.Stop()
        except Exception:
            pass
        self._timer.Stop()
        self.btn_play.SetLabel("&Reproducir")
        self.sld_pos.SetValue(0)
        if not silencioso:
            anunciar("Detenido")

    def _buscar_rel(self, delta_ms: int):
        if self._duracion_ms <= 0:
            return
        nueva = min(max(0, self._mc.Tell() + delta_ms), self._duracion_ms)
        self._mc.Seek(nueva)
        anunciar(_fmt_t(nueva))

    def _on_sld_pos(self, event):
        if self._duracion_ms <= 0:
            return
        frac = self.sld_pos.GetValue() / 1000.0
        destino = int(frac * self._duracion_ms)
        self._mc.Seek(destino)
        anunciar(_fmt_t(destino))

    def _on_sld_vol(self, event):
        self._mc.SetVolume(self.sld_vol.GetValue() / 100.0)

    def _on_fin(self, event):
        self._timer.Stop()
        self.btn_play.SetLabel("&Reproducir")
        self.sld_pos.SetValue(0)
        anunciar("Fin del audio")

    def _on_timer(self, event):
        if self._duracion_ms <= 0:
            return
        pos = self._mc.Tell()
        self.sld_pos.SetValue(int(pos / self._duracion_ms * 1000))


def _fmt_t(ms: int) -> str:
    s = max(0, ms // 1000)
    return f"{s // 60}:{s % 60:02d}"
