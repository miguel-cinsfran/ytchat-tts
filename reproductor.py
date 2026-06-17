"""Reproductor de vídeo/audio del directo o vídeo, accesible y con imagen.

Backend: yt-dlp obtiene las URLs de los flujos y libVLC (python-vlc) reproduce,
mostrando la imagen embebida (set_hwnd) con audio. Permite elegir calidad y
pantalla completa. Para audio+vídeo en calidades altas (DASH) se reproduce el
flujo de vídeo con el de audio como «input-slave».

Se eligió VLC porque el backend nativo de Windows no reproduce los flujos
`googlevideo`. Todo degrada tras guardas: si falta python-vlc, libVLC o yt-dlp,
el panel muestra un aviso y el resto de la app funciona igual. VLC se importa y
se instancia de forma perezosa (al primer uso) para no frenar el arranque.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading

import wx

import iconos
from gui import anunciar, _T, _tc

logger = logging.getLogger(__name__)

_vlc = None          # binding python-vlc; se importa perezosamente
_VLC_PREPARADO = False


def _carpeta_vlc_empaquetada() -> str | None:
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "vlc")
        if os.path.exists(os.path.join(base, "libvlc.dll")):
            return base
    return None


def _preparar_vlc() -> None:
    """Deja listo el entorno para cargar libVLC. En la app empaquetada apunta a
    la copia de VLC junto al .exe y PRECARGA libvlccore para que el cargador de
    PyInstaller no falle al resolver la dependencia."""
    global _VLC_PREPARADO
    if _VLC_PREPARADO:
        return
    _VLC_PREPARADO = True
    base = _carpeta_vlc_empaquetada()
    if not base:
        return
    lib = os.path.join(base, "libvlc.dll")
    plugins = os.path.join(base, "plugins")
    os.environ["PYTHON_VLC_LIB_PATH"] = lib
    os.environ["PYTHON_VLC_MODULE_PATH"] = plugins
    # VLC_PLUGIN_PATH es lo que lee libVLC para localizar sus plugins; sin esto
    # la instancia sale None en la app empaquetada.
    os.environ["VLC_PLUGIN_PATH"] = plugins
    os.environ["PATH"] = base + os.pathsep + os.environ.get("PATH", "")
    try:
        os.add_dll_directory(base)
    except Exception:
        pass
    # Precargar el core: así libvlc.dll encuentra su dependencia bajo PyInstaller.
    try:
        import ctypes
        ctypes.CDLL(os.path.join(base, "libvlccore.dll"))
    except Exception as exc:
        logger.debug("preload libvlccore: %s", exc)


def _cargar_vlc() -> bool:
    """Importa python-vlc de forma perezosa. True si quedó disponible."""
    global _vlc
    if _vlc is not None:
        return True
    _preparar_vlc()
    try:
        import vlc
        _vlc = vlc
        return True
    except Exception as exc:
        logger.warning("No se pudo cargar libVLC: %s", exc)
        return False


def vlc_disponible() -> bool:
    """¿Hay VLC? Sin importarlo (cargar la DLL es lento) para no frenar arranque."""
    if getattr(sys, "frozen", False):
        return _carpeta_vlc_empaquetada() is not None
    try:
        return importlib.util.find_spec("vlc") is not None
    except Exception:
        return False


def ytdlp_disponible() -> bool:
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "_internal", "yt_dlp")
        return os.path.isdir(base)
    try:
        return importlib.util.find_spec("yt_dlp") is not None
    except Exception:
        return False


def disponible() -> bool:
    return vlc_disponible() and ytdlp_disponible()


# Argumentos de la instancia: solo los imprescindibles. Cualquier opción que
# libVLC no reconozca hace que libvlc_new devuelva NULL (instancia None), así
# que el ajuste de buffer va como opción POR MEDIO (más tolerante), no aquí.
_VLC_ARGS = ("--quiet",)
# Opciones por medio: poco buffer para que play/pausa/búsqueda respondan rápido.
_MEDIA_OPTS = (":network-caching=300", ":live-caching=300")

# Alturas de vídeo que ofrecemos como «calidad», de mayor a menor.
_CALIDADES = [2160, 1440, 1080, 720, 480, 360, 240, 144]


def _info_video(video_id: str) -> dict:
    """Datos de yt-dlp del vídeo (bloquea; usar en hilo)."""
    import yt_dlp
    # socket_timeout: sin él, una red lenta deja la app colgada en «Cargando
    # vídeo…» sin feedback. 20 s es de sobra para la extracción normal (~3-5 s).
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": True, "socket_timeout": 20}
    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _alturas_disponibles(info: dict) -> list[int]:
    alturas = set()
    for f in info.get("formats", []) or []:
        if f.get("vcodec") not in (None, "none") and f.get("height"):
            alturas.add(int(f["height"]))
    return sorted(alturas, reverse=True)


def _mejor_audio(info: dict) -> str:
    for f in sorted(info.get("formats", []) or [],
                    key=lambda x: x.get("abr") or 0, reverse=True):
        if (f.get("acodec") not in (None, "none")
                and f.get("vcodec") in (None, "none") and f.get("url")):
            return f["url"]
    return ""


def _video_para_altura(info: dict, altura: int) -> tuple[str, bool]:
    """(url, progresivo). Busca el mejor flujo para esa altura; progresivo=True
    si ya trae audio (no hace falta slave)."""
    fmts = info.get("formats", []) or []
    # 1) Progresivo (audio+vídeo) exacto o cercano por debajo.
    prog = [f for f in fmts if f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none") and f.get("url") and f.get("height")]
    cand = [f for f in prog if int(f["height"]) <= altura]
    if cand:
        f = max(cand, key=lambda x: int(x["height"]))
        if int(f["height"]) == altura:
            return f["url"], True
    # 2) Vídeo solo a esa altura (se acompañará con audio como slave).
    solo = [f for f in fmts if f.get("vcodec") not in (None, "none")
            and f.get("acodec") in (None, "none") and f.get("url")
            and f.get("height") and int(f["height"]) == altura]
    if solo:
        return max(solo, key=lambda x: x.get("tbr") or 0)["url"], False
    # 3) Lo mejor progresivo que haya.
    if prog:
        return max(prog, key=lambda x: int(x["height"]))["url"], True
    return "", False


def _fmt_t(ms) -> str:
    """Compacto para la etiqueta visual: H:MM:SS, o M:SS si dura menos de 1 h."""
    s = max(0, int(ms or 0) // 1000)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _fmt_hablado(ms) -> str:
    """Verboso para el lector, estilo YouTube: «2 horas 16 minutos 35 segundos»."""
    s = max(0, int(ms or 0) // 1000)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    partes = []
    if h:
        partes.append(f"{h} hora" + ("s" if h != 1 else ""))
    if h or m:
        partes.append(f"{m} minuto" + ("s" if m != 1 else ""))
    partes.append(f"{sec} segundo" + ("s" if sec != 1 else ""))
    return " ".join(partes)


class _PosAccesible(wx.Accessible):
    """Hace que NVDA lea la posición como tiempo hablado, no el número crudo."""

    def __init__(self, panel):
        super().__init__()
        self._panel = panel

    def GetName(self, childId):
        return (wx.ACC_OK, "Posición de reproducción")

    def GetValue(self, childId):
        p = self._panel
        return (wx.ACC_OK, f"{_fmt_hablado(p._pos_ms)} de {_fmt_hablado(p._dur_ms)}")


class _PantallaCompleta(wx.Frame):
    """Ventana sin bordes a pantalla completa para el vídeo. Escape o F11 sale."""

    def __init__(self, panel):
        super().__init__(None, title="Reproductor", name="PantallaCompleta")
        self._panel = panel
        self.SetBackgroundColour(wx.BLACK)
        self.video = wx.Window(self, name="VideoPantallaCompleta")
        self.video.SetBackgroundColour(wx.BLACK)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.ShowFullScreen(True)

    def _on_key(self, event):
        if event.GetKeyCode() in (wx.WXK_ESCAPE, wx.WXK_F11):
            self._panel.alternar_pantalla_completa()
        else:
            event.Skip()


class ReproductorPanel(wx.Panel):
    """Reproductor siempre visible (no es una pestaña): imagen + controles."""

    def __init__(self, parent, config):
        super().__init__(parent, name="PanelReproductor")
        self._config = config
        self._video_id = ""
        self._cargando = False
        # «Generación» de carga: cada stop/desconexión la incrementa, así una
        # carga de yt-dlp que quedó en vuelo se descarta al volver (si no, al
        # desconectar mientras cargaba, rearrancaba la reproducción sola).
        self._gen = 0
        self._listo = disponible()
        self._pos_ms = 0
        self._dur_ms = 0
        self._vol = 80
        self._muted = False
        # Botones de control ocultables (opción minimalista). El estado se guarda
        # en config; la ventana sincroniza el menú y persiste vía on_botones_toggle.
        self._botones_visibles = bool(config.get("mostrar_botones_reproductor", False))
        self.on_botones_toggle = None
        self._calidad_sel = None
        self._alturas = []
        self._inst = None
        self._inst_lock = threading.Lock()  # crear la instancia VLC sin carreras
        self._player = None
        self._info = None
        self._fs = None        # ventana de pantalla completa, si está activa

        self.SetBackgroundColour(_T.bg)
        self.SetForegroundColour(_T.text)
        if self._listo:
            self._build_ui()
            self._precalentar()
        else:
            self._build_aviso()

    # ── Instancia perezosa de VLC ─────────────────────────────────────────────

    def _asegurar_instancia(self) -> bool:
        """Crea (o reutiliza) la instancia de libVLC. Es la parte LENTA: importar
        libvlc.dll y escanear todos los plugins (1-2 s la 1ª vez). Va con lock
        para poder precalentarla en segundo plano sin chocar con el hilo de la
        GUI si el usuario conecta justo en ese momento."""
        if self._inst is not None:
            return True
        if not self._listo or not _cargar_vlc():
            return False
        with self._inst_lock:
            if self._inst is None:
                try:
                    self._inst = _vlc.Instance(*_VLC_ARGS)
                except Exception as exc:
                    logger.warning("No se pudo crear la instancia de VLC: %s", exc)
                    return False
        return self._inst is not None

    def _precalentar(self) -> None:
        """Crea la instancia de libVLC en segundo plano apenas se construye el
        panel, para que el primer «Conectar» no congele la ventana. Nadie espera
        este hilo: si el usuario conecta antes de que termine, `_asegurar_player`
        comparte la misma instancia vía lock."""
        def _run():
            try:
                self._asegurar_instancia()
            except Exception as exc:
                logger.debug("precalentar VLC: %s", exc)
        threading.Thread(target=_run, daemon=True, name="ReproductorWarmup").start()

    def _asegurar_player(self) -> bool:
        # La instancia (lenta) puede venir ya precalentada; el reproductor y el
        # set_hwnd son rápidos y deben crearse aquí, en el hilo de la GUI.
        if self._player is not None:
            return True
        if not self._asegurar_instancia():
            return False
        try:
            self._player = self._inst.media_player_new()
            self._fijar_salida(self._video.GetHandle())
        except Exception as exc:
            logger.warning("No se pudo crear el reproductor de VLC: %s", exc)
            return False
        return True

    def _fijar_salida(self, hwnd):
        try:
            self._player.set_hwnd(int(hwnd))
        except Exception as exc:
            logger.debug("set_hwnd: %s", exc)

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_aviso(self):
        box = wx.StaticBoxSizer(wx.HORIZONTAL, self, "Reproductor")
        if not vlc_disponible():
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

        # Superficie de vídeo (VLC dibuja aquí vía set_hwnd).
        self._video = wx.Window(self, size=(-1, 160), name="Vídeo")
        self._video.SetBackgroundColour(wx.BLACK)
        box.Add(self._video, 1, wx.EXPAND | wx.ALL, 6)

        # Fila 1: transporte con iconos (nombre accesible + tooltip).
        self._ic_play  = iconos.icono("play", _T.text, _T.btn)
        self._ic_pause = iconos.icono("pause", _T.text, _T.btn)
        self._ic_mute  = iconos.icono("mute", _T.text, _T.btn)
        self._ic_sound = iconos.icono("sound", _T.text, _T.btn)
        # Sin mnemónicos «&» en estos botones: chocaban entre sí (dos con la misma
        # letra) y el lector los leía como «alt+letra». El control va por los
        # atajos Ctrl+… y por Tab+Espacio.
        self._fila_botones = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_play  = self._btn_icono(self._ic_play, "Reproducir", "Reproducir o pausa")
        self.btn_retro = self._btn_icono(iconos.icono("retro", _T.text, _T.btn),
                                         "Retroceder 1 min", "Retroceder 1 minuto")
        self.btn_avanz = self._btn_icono(iconos.icono("avanz", _T.text, _T.btn),
                                         "Avanzar 1 min", "Avanzar 1 minuto")
        self.btn_stop  = self._btn_icono(iconos.icono("stop", _T.text, _T.btn),
                                         "Detener", "Detener")
        self.btn_mute  = self._btn_icono(self._ic_sound, "Silenciar audio",
                                         "Silenciar o activar audio")
        self.btn_fs    = self._btn_icono(iconos.icono("fullscreen", _T.text, _T.btn),
                                         "Pantalla completa", "Pantalla completa")
        for b in (self.btn_play, self.btn_retro, self.btn_avanz, self.btn_stop,
                  self.btn_mute, self.btn_fs):
            self._fila_botones.Add(b, 0, wx.RIGHT, 6)
        box.Add(self._fila_botones, 0, wx.ALL, 6)

        # Fila 2: posición + tiempo. La calidad va en el menú Reproductor.
        row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self, label="Posición:", name="EtiquetaPosicion")
        lbl.SetForegroundColour(_T.dim)
        row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.sld_pos = wx.Slider(self, value=0, minValue=0, maxValue=1000,
                                 name="Posición de reproducción")
        _tc(self.sld_pos, bg=_T.surface)
        self.sld_pos.SetToolTip("Flecha derecha avanza 10 s, flecha izquierda retrocede 10 s.")
        self.sld_pos.SetAccessible(_PosAccesible(self))
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
        self.sld_vol.SetLineSize(1)
        self.sld_vol.SetToolTip("Flecha arriba sube, flecha abajo baja el volumen de 1 en 1.")
        self.sld_vol.SetMinSize((160, -1))
        row.Add(self.sld_vol, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        self.lbl_estado = wx.StaticText(self, label="Sin reproducir.", name="EstadoReproductor")
        self.lbl_estado.SetForegroundColour(_T.accent)
        row.Add(self.lbl_estado, 1, wx.ALIGN_CENTER_VERTICAL)
        box.Add(row, 0, wx.EXPAND | wx.ALL, 6)

        # Fila 4: interruptor para mostrar/ocultar los botones de control. Va el
        # último para no estorbar el recorrido de Tab de los controles de uso;
        # queda siempre visible aunque la fila de botones esté oculta.
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_toggle_botones = wx.Button(self, name="AlternarBotonesReproductor",
                                            label=self._etiqueta_toggle())
        self.btn_toggle_botones.SetBackgroundColour(_T.btn)
        self.btn_toggle_botones.SetForegroundColour(_T.btn_t)
        self.btn_toggle_botones.SetToolTip(
            "Muestra u oculta los botones de control del reproductor. También en "
            "el menú Reproductor. Los atajos funcionan estén o no visibles.")
        row.Add(self.btn_toggle_botones, 0)
        box.Add(row, 0, wx.ALL, 6)

        self.SetSizer(box)

        self.btn_play.Bind(wx.EVT_BUTTON, lambda e: self._toggle_play())
        self.btn_retro.Bind(wx.EVT_BUTTON, lambda e: self._buscar_rel(-60_000))
        self.btn_avanz.Bind(wx.EVT_BUTTON, lambda e: self._buscar_rel(+60_000))
        self.btn_stop.Bind(wx.EVT_BUTTON, lambda e: self._detener())
        self.btn_mute.Bind(wx.EVT_BUTTON, lambda e: self._toggle_mute())
        self.btn_fs.Bind(wx.EVT_BUTTON, lambda e: self.alternar_pantalla_completa())
        self.sld_pos.Bind(wx.EVT_SLIDER, self._on_sld_pos)
        self.sld_pos.Bind(wx.EVT_KEY_DOWN, self._on_pos_key)
        self.sld_vol.Bind(wx.EVT_SLIDER, self._on_sld_vol)
        self.sld_vol.Bind(wx.EVT_KEY_DOWN, self._on_vol_key)
        self._video.Bind(wx.EVT_LEFT_DCLICK, lambda e: self.alternar_pantalla_completa())
        self.btn_toggle_botones.Bind(wx.EVT_BUTTON, lambda e: self.alternar_botones())

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)

        # Aplicar el estado guardado (por defecto, botones ocultos = minimalista).
        self._aplicar_visibilidad_botones()

    def _btn_icono(self, bmp, etiqueta, tooltip):
        # Icono + TEXTO: el texto es el nombre accesible que lee el lector (un
        # botón solo-icono lo leería como «botón»). El icono da el aire moderno.
        b = wx.Button(self, label=etiqueta, name=etiqueta.replace("&", ""))
        b.SetBackgroundColour(_T.btn)
        b.SetForegroundColour(_T.btn_t)
        b.SetBitmap(bmp)
        b.SetBitmapMargins((4, 0))
        b.SetToolTip(tooltip)
        return b

    # ── API pública (la ventana la llama al conectar) ─────────────────────────

    def anclar_foco(self) -> None:
        # Llevar el foco a algo útil: si los botones están visibles, a Reproducir;
        # si no, al deslizador de Posición (primer control navegable del panel).
        try:
            if self._listo:
                destino = self.btn_play if self._botones_visibles else self.sld_pos
                destino.SetFocus()
        except Exception:
            pass

    # ── Botones ocultables (interruptor / menú) ───────────────────────────────

    def _etiqueta_toggle(self) -> str:
        return ("Ocultar botones del reproductor" if self._botones_visibles
                else "Mostrar botones del reproductor")

    def botones_visibles(self) -> bool:
        return self._botones_visibles

    def _aplicar_visibilidad_botones(self) -> None:
        """Muestra u oculta la fila de botones y reajusta el layout. Ocultos,
        salen además del recorrido de Tab (wx omite las ventanas no visibles)."""
        sizer = self.GetSizer()
        if sizer is None or not hasattr(self, "_fila_botones"):
            return
        sizer.Show(self._fila_botones, self._botones_visibles, recursive=True)
        self.btn_toggle_botones.SetLabel(self._etiqueta_toggle())
        self.Layout()

    def set_botones_visibles(self, visibles: bool) -> None:
        """Fija la visibilidad y avisa a la ventana (para el menú y persistir)."""
        self._botones_visibles = bool(visibles)
        self._aplicar_visibilidad_botones()
        if self.on_botones_toggle:
            try:    self.on_botones_toggle(self._botones_visibles)
            except Exception: pass

    def alternar_botones(self) -> None:
        self.set_botones_visibles(not self._botones_visibles)
        anunciar("Botones del reproductor visibles" if self._botones_visibles
                 else "Botones del reproductor ocultos")

    def set_video(self, video_id: str, autoplay: bool = True) -> None:
        self._video_id = video_id or ""
        if not self._listo:
            return
        self._detener(silencioso=True)
        self._info = None
        self._calidad_sel = None
        self._alturas = []
        if self._video_id and autoplay:
            self.cargar(reproducir=True)
        else:
            self.lbl_estado.SetLabel("Listo. Pulsa Reproducir.")

    def detener_todo(self) -> None:
        # Olvidar el vídeo actual: al desconectar el reproductor queda en blanco,
        # como recién abierta la app (sin un id viejo que pudiera relanzarse).
        self._video_id = ""
        if self._listo:
            if self._fs:
                self.alternar_pantalla_completa()
            self._detener(silencioso=True)

    # ── Carga / reproducción ──────────────────────────────────────────────────

    def cargar(self, reproducir: bool = True):
        if not self._listo or not self._asegurar_player():
            anunciar("El reproductor no está disponible.")
            return
        if not self._video_id or self._cargando:
            return
        self._cargando = True
        self.lbl_estado.SetLabel("Cargando vídeo…")
        anunciar("Cargando vídeo")
        vid = self._video_id
        gen = self._gen   # si cambia al volver, esta carga ya no vale

        def _run():
            try:
                info = _info_video(vid)
            except Exception as exc:
                logger.warning("info vídeo: %s", exc)
                wx.CallAfter(self._error_carga, gen)
                return
            wx.CallAfter(self._info_listo, info, reproducir, vid, gen)

        threading.Thread(target=_run, daemon=True, name="ReproductorInfo").start()

    def _info_listo(self, info, reproducir, vid, gen):
        if gen != self._gen or vid != self._video_id:
            return  # se detuvo/desconectó o cambió de vídeo mientras cargaba
        self._info = info
        self._alturas = [a for a in _CALIDADES if a in _alturas_disponibles(info)]
        self._cargando = False
        self._reproducir_calidad(self._calidad_sel, reproducir)

    def _reproducir_calidad(self, altura, reproducir):
        if self._info is None or not self._asegurar_player():
            return
        es_directo = self._info.get("is_live")
        if altura is None or es_directo:
            # Auto / directo: el formato combinado que elija yt-dlp.
            url, slave = self._info.get("url") or "", None
            if not url:
                url, prog = _video_para_altura(self._info, 10_000)
                slave = None if prog else _mejor_audio(self._info)
        else:
            url, prog = _video_para_altura(self._info, altura)
            slave = None if prog else _mejor_audio(self._info)
        if not url:
            self._error_carga()
            return
        try:
            media = self._inst.media_new(url)
            for opt in _MEDIA_OPTS:
                media.add_option(opt)
            if slave:
                media.add_option(f":input-slave={slave}")
            self._player.set_media(media)
            self._player.audio_set_volume(self._vol)
            self._player.audio_set_mute(self._muted)
            if reproducir:
                self._player.play()
                self._mostrar_pausa(True)
                self._timer.Start(500)
        except Exception as exc:
            logger.warning("reproducir: %s", exc)
            self._error_carga()
            return
        self._pos_ms = self._dur_ms = 0
        self.lbl_estado.SetLabel("Reproduciendo." if reproducir else "Listo.")
        if reproducir:
            anunciar("Reproduciendo")

    def set_calidad(self, altura):
        """altura=None → automática; si no hay info aún, se aplica al cargar."""
        self._calidad_sel = altura
        anunciar("Calidad automática" if altura is None else f"Calidad {altura}p")
        if self._info is not None:
            self._reproducir_calidad(altura, reproducir=True)

    def alturas_disponibles(self) -> list[int]:
        return list(self._alturas)

    def _error_carga(self, gen=None):
        if gen is not None and gen != self._gen:
            return  # error de una carga ya descartada (stop/desconexión)
        self._cargando = False
        import sound_player as _snd
        _snd.reproducir("error")
        self.lbl_estado.SetLabel("No se pudo cargar el vídeo.")
        anunciar("No se pudo cargar el vídeo")

    # ── Transporte ──────────────────────────────────────────────────────────────

    def _mostrar_pausa(self, reproduciendo: bool):
        """Pone icono + texto del botón play/pausa según el estado."""
        self.btn_play.SetBitmap(self._ic_pause if reproduciendo else self._ic_play)
        self.btn_play.SetLabel("Pausa" if reproduciendo else "Reproducir")

    def _toggle_play(self):
        if not self._asegurar_player():
            return
        st = self._player.get_state()
        if st == _vlc.State.Playing:
            self._player.set_pause(1)
            self._mostrar_pausa(False)
            self._timer.Stop()
            anunciar("Pausa")
        elif st == _vlc.State.Paused:
            self._player.set_pause(0)
            self._mostrar_pausa(True)
            self._timer.Start(500)
            anunciar("Reproduciendo")
        else:
            if self._video_id:
                self.cargar(reproducir=True)

    def _detener(self, silencioso: bool = False):
        # Invalida cualquier carga en vuelo (yt-dlp) y desbloquea futuras cargas:
        # sin esto, una carga que termina tras detener/desconectar rearrancaba la
        # reproducción al volver por wx.CallAfter.
        self._gen += 1
        self._cargando = False
        if self._player is not None:
            try:    self._player.stop()
            except Exception: pass
        if hasattr(self, "_timer"):
            self._timer.Stop()
        if hasattr(self, "btn_play"):
            self._mostrar_pausa(False)
            self._fijar_tiempo(0, 0, mover_slider=True, anunciar_t=False)
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
        self._fijar_tiempo(nueva, dur, mover_slider=True, anunciar_t=True)

    def _toggle_mute(self):
        if self._player is None:
            return
        self._muted = not self._muted
        self._player.audio_set_mute(self._muted)
        self.btn_mute.SetBitmap(self._ic_mute if self._muted else self._ic_sound)
        self.btn_mute.SetLabel("Activar audio" if self._muted else "Silenciar audio")
        anunciar("Audio silenciado" if self._muted else "Audio activado")

    def ajustar_volumen(self, delta: int):
        self._vol = max(0, min(100, self._vol + delta))
        self.sld_vol.SetValue(self._vol)
        if self._player is not None:
            self._player.audio_set_volume(self._vol)
        anunciar(f"Volumen reproductor {self._vol} por ciento")

    # ── Pantalla completa ──────────────────────────────────────────────────────

    def alternar_pantalla_completa(self):
        if not self._asegurar_player():
            return
        if self._fs is None:
            self._fs = _PantallaCompleta(self)
            self._fijar_salida(self._fs.video.GetHandle())
            anunciar("Pantalla completa. Escape para salir.")
        else:
            self._fijar_salida(self._video.GetHandle())
            self._fs.Destroy()
            self._fs = None
            anunciar("Pantalla completa desactivada")

    # ── Tiempo / sliders ──────────────────────────────────────────────────────

    def _fijar_tiempo(self, pos_ms, dur_ms, mover_slider, anunciar_t):
        self._pos_ms = int(pos_ms or 0)
        self._dur_ms = int(dur_ms or 0)
        self.lbl_tiempo.SetLabel(f"{_fmt_t(self._pos_ms)} / {_fmt_t(self._dur_ms)}")
        if mover_slider and self._dur_ms > 0:
            self.sld_pos.SetValue(int(self._pos_ms / self._dur_ms * 1000))
        if anunciar_t:
            anunciar(_fmt_hablado(self._pos_ms))

    def _on_sld_pos(self, event):
        if self._player is None:
            return
        dur = self._player.get_length()
        if dur <= 0:
            return
        destino = int(self.sld_pos.GetValue() / 1000.0 * dur)
        self._player.set_time(destino)
        self._fijar_tiempo(destino, dur, mover_slider=False, anunciar_t=False)

    def _on_pos_key(self, event):
        # Consumimos las flechas (no Skip) para que el deslizador no cambie su
        # valor crudo por su cuenta. Las teclas 0-9 saltan al porcentaje, como
        # en YouTube (5 = 50 %).
        k = event.GetKeyCode()
        if k in (wx.WXK_RIGHT, wx.WXK_UP):
            self._buscar_rel(+10_000)
        elif k in (wx.WXK_LEFT, wx.WXK_DOWN):
            self._buscar_rel(-10_000)
        elif ord("0") <= k <= ord("9"):
            self._buscar_porcentaje((k - ord("0")) * 10)
        elif wx.WXK_NUMPAD0 <= k <= wx.WXK_NUMPAD9:
            self._buscar_porcentaje((k - wx.WXK_NUMPAD0) * 10)
        else:
            event.Skip()

    def _buscar_porcentaje(self, pct):
        if self._player is None:
            return
        dur = self._player.get_length()
        if dur <= 0:
            anunciar("No se puede buscar en este flujo")
            return
        destino = int(dur * pct / 100)
        self._player.set_time(destino)
        self._fijar_tiempo(destino, dur, mover_slider=True, anunciar_t=True)

    def _on_vol_key(self, event):
        # En un trackbar horizontal, Arriba baja y Abajo sube (nativo). Lo
        # invertimos para que sea intuitivo: Arriba/Derecha sube, Abajo/Izq baja.
        k = event.GetKeyCode()
        if k in (wx.WXK_UP, wx.WXK_RIGHT):
            self._vol_flecha(+1)
        elif k in (wx.WXK_DOWN, wx.WXK_LEFT):
            self._vol_flecha(-1)
        else:
            event.Skip()

    def _vol_flecha(self, delta):
        self._vol = max(0, min(100, self._vol + delta))
        self.sld_vol.SetValue(self._vol)
        if self._player is not None:
            self._player.audio_set_volume(self._vol)
        anunciar(f"Volumen {self._vol}")

    def _on_sld_vol(self, event):
        self._vol = self.sld_vol.GetValue()
        if self._player is not None:
            self._player.audio_set_volume(self._vol)

    def _on_timer(self, event):
        if self._player is None:
            return
        # VLC arranca cada media nueva con SU volumen por defecto e ignora el
        # audio_set_volume previo cuando la salida de audio aún no existía: por
        # eso al cambiar de URL el slider quedaba en un valor y el audio sonaba a
        # otro (incluso slider a 0 % sonando). Reconciliamos aquí, ya en marcha:
        # el slider (self._vol) manda. Mientras esté en mute no tocamos nada.
        if not self._muted and self._player.get_state() == _vlc.State.Playing:
            actual = self._player.audio_get_volume()
            if actual >= 0 and actual != self._vol:
                self._player.audio_set_volume(self._vol)
        dur = self._player.get_length()
        pos = self._player.get_time()
        mover = wx.Window.FindFocus() is not self.sld_pos
        self._fijar_tiempo(pos, dur, mover_slider=mover, anunciar_t=False)
        if self._player.get_state() == _vlc.State.Ended:
            self._detener(silencioso=True)
            anunciar("Fin del vídeo")
