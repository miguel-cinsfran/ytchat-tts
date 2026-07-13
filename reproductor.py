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
import re
import sys
import threading

import wx

import config as _cfg
import iconos
from gui import anunciar, nombre_accesible, _T, _tc

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
    # Preferimos la pista ORIGINAL antes que la de mayor bitrate: cada vez más
    # vídeos traen doblajes y yt-dlp marca la original/«default» con
    # language_preference alto (10). Sin esto, entre dos bitrates parecidos
    # podríamos reproducir el doblaje en vez del audio original. A igualdad de
    # idioma, gana el bitrate (como antes), así que un vídeo de una sola pista
    # se comporta igual que siempre.
    auds = [f for f in info.get("formats", []) or []
            if f.get("acodec") not in (None, "none")
            and f.get("vcodec") in (None, "none") and f.get("url")]
    if not auds:
        return ""
    mejor = max(auds, key=lambda x: ((x.get("language_preference") or 0),
                                     (x.get("abr") or 0)))
    return mejor["url"]


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


# ── Atajos en pantalla completa ───────────────────────────────────────────────
# Traducción de los atajos de config («ctrl+p», «ctrl+left», «f5»…) a lo que
# entrega wx.EVT_CHAR_HOOK: (modificadores, keycode).

_TECLAS_WX = {
    "left": wx.WXK_LEFT, "right": wx.WXK_RIGHT, "up": wx.WXK_UP,
    "down": wx.WXK_DOWN, "enter": wx.WXK_RETURN, "space": wx.WXK_SPACE,
}
_RE_FKEY_WX = re.compile(r"^f(1[0-2]|[1-9])$")


def _combo_wx(texto: str) -> tuple[int, int] | None:
    """«ctrl+p» → (wx.MOD_CONTROL, ord('P')). None si no se puede traducir."""
    partes = (texto or "").lower().split("+")
    if not partes or not partes[-1]:
        return None
    mods = 0
    for p in partes[:-1]:
        m = {"ctrl": wx.MOD_CONTROL, "alt": wx.MOD_ALT, "shift": wx.MOD_SHIFT}.get(p)
        if m is None:
            return None
        mods |= m
    tecla = partes[-1]
    if tecla in _TECLAS_WX:
        return (mods, _TECLAS_WX[tecla])
    if _RE_FKEY_WX.match(tecla):
        return (mods, wx.WXK_F1 + int(tecla[1:]) - 1)
    if len(tecla) == 1:
        return (mods, ord(tecla.upper()))
    return None


class _PosAccesible(wx.Accessible):
    """Hace que NVDA lea la posición como tiempo hablado, no el número crudo."""

    def __init__(self, panel):
        super().__init__()
        self._panel = panel

    def GetName(self, childId):
        return (wx.ACC_OK, "Posición de reproducción")

    def GetValue(self, childId):
        p = self._panel
        if p._dur_ms > 0:
            return (wx.ACC_OK, f"{_fmt_hablado(p._pos_ms)} de {_fmt_hablado(p._dur_ms)}")
        return (wx.ACC_OK, "En directo")   # un live no tiene duración que anunciar


class _PantallaCompleta(wx.Frame):
    """Ventana sin bordes a pantalla completa para el vídeo.

    Antes solo atendía Escape/F11 y era una trampa de teclado: los atajos
    Ctrl+… son aceleradores del menú de la ventana PRINCIPAL y aquí no llegan,
    así que no había ni pausa ni volumen. Ahora la ventana atiende:
      - los atajos del reproductor configurados en Preferencias (Ctrl+…), y
      - las teclas convencionales de los reproductores de vídeo (VLC/YouTube):
        espacio pausa, flechas buscan y ajustan volumen, M silencia,
        F alterna pantalla completa y 0-9 salta al porcentaje.
    """

    def __init__(self, panel):
        # Título = el de la ventana principal (el del vídeo, p. ej. «… — YTChat
        # TTS»), no un genérico «Reproductor»: es lo que anuncia el lector y lo
        # que sale en Alt+Tab al entrar a pantalla completa.
        try:
            principal = wx.GetApp().GetTopWindow()
            titulo = (principal.GetTitle() if principal else "") or _cfg.APP_NAME
        except Exception:
            titulo = _cfg.APP_NAME
        super().__init__(None, title=titulo, name="PantallaCompleta")
        self._panel = panel
        self._atajos = panel._mapa_atajos_fs()
        self.SetBackgroundColour(wx.BLACK)
        self.video = wx.Window(self, name="VideoPantallaCompleta")
        self.video.SetBackgroundColour(wx.BLACK)
        nombre_accesible(
            self.video,
            "Vídeo a pantalla completa. Espacio pausa, flechas buscan y ajustan "
            "volumen, Escape sale.")
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.video.Bind(wx.EVT_LEFT_DCLICK,
                        lambda e: self._panel.alternar_pantalla_completa())
        self.ShowFullScreen(True)
        # Foco a la superficie de vídeo: así EVT_CHAR_HOOK recibe el teclado y
        # el lector de pantalla queda sobre un control con nombre accesible.
        self.video.SetFocus()

    def _on_key(self, event):
        p = self._panel
        k = event.GetKeyCode()
        mods = event.GetModifiers()
        if k in (wx.WXK_ESCAPE, wx.WXK_F11):
            p.alternar_pantalla_completa()
            return
        accion = self._atajos.get((mods, k))
        if accion is not None:
            accion()
            return
        if mods == wx.MOD_NONE:
            if k in (wx.WXK_SPACE, wx.WXK_MEDIA_PLAY_PAUSE):
                p._toggle_play(); return
            if k == wx.WXK_LEFT:
                p._buscar_rel(-10_000); return
            if k == wx.WXK_RIGHT:
                p._buscar_rel(+10_000); return
            if k == wx.WXK_UP:
                p._vol_flecha(+5); return
            if k == wx.WXK_DOWN:
                p._vol_flecha(-5); return
            if k == ord("M"):
                p._toggle_mute(); return
            if k == ord("F"):
                p.alternar_pantalla_completa(); return
            if ord("0") <= k <= ord("9"):
                p._buscar_porcentaje((k - ord("0")) * 10); return
            if wx.WXK_NUMPAD0 <= k <= wx.WXK_NUMPAD9:
                p._buscar_porcentaje((k - wx.WXK_NUMPAD0) * 10); return
        event.Skip()

    def _on_close(self, event):
        # Alt+F4: salir por el mismo camino que Escape/F11. Si se destruyera sin
        # avisar, el panel seguiría apuntando aquí y el vídeo quedaría dibujando
        # en una ventana muerta (y el siguiente toggle petaría).
        self._panel.alternar_pantalla_completa()


class ReproductorPanel(wx.Panel):
    """Reproductor siempre visible (no es una pestaña): imagen + controles."""

    def __init__(self, parent, config):
        super().__init__(parent, name="PanelReproductor")
        self._config = config
        self._video_id = ""
        # URL de flujo directa (HLS de TikTok): reproduce sin pasar por yt-dlp.
        # Excluyente con _video_id: solo una de las dos fuentes está activa.
        self._url_flujo = ""
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

        # Superficie de vídeo (VLC dibuja aquí vía set_hwnd). Es una ventana
        # genérica: sin nombre accesible reforzado, el lector no dice nada útil
        # al llegar aquí (p. ej. con doble clic para pantalla completa).
        self._video = wx.Window(self, size=(-1, 160), name="Vídeo")
        self._video.SetBackgroundColour(wx.BLACK)
        nombre_accesible(self._video, "Vídeo. Doble clic para pantalla completa.")
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
        # Los deslizadores son justo el caso donde SetName no basta en Windows.
        nombre_accesible(self.sld_vol, "Volumen del reproductor")
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

    # ── Atajos para la ventana de pantalla completa ───────────────────────────

    def _mapa_atajos_fs(self) -> dict:
        """(modificadores, keycode) → acción, para los atajos del reproductor
        configurados por el usuario. La ventana de pantalla completa lo usa
        para que Ctrl+P, Ctrl+flechas, etc. sigan funcionando allí (donde los
        aceleradores del menú de la ventana principal no llegan)."""
        acciones = {
            "rep_play":      self._toggle_play,
            "rep_retro":     lambda: self._buscar_rel(-60_000),
            "rep_avanz":     lambda: self._buscar_rel(+60_000),
            "rep_detener":   self._detener,
            "rep_mute":      self._toggle_mute,
            "rep_vol_menos": lambda: self.ajustar_volumen(-20),
            "rep_vol_mas":   lambda: self.ajustar_volumen(+20),
        }
        atajos = _cfg.parsear_atajos(self._config.get("atajos_raw", {}))
        mapa = {}
        for accion, fn in acciones.items():
            at = atajos.get(accion)
            if at:
                combo = _combo_wx(at.texto)
                if combo:
                    mapa[combo] = fn
        return mapa

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
        self._url_flujo = ""
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

    def set_flujo(self, url: str, autoplay: bool = True) -> None:
        """Reproduce una URL de flujo directa (el HLS de un directo de TikTok).
        Sin yt-dlp ni calidades: la URL ya viene resuelta por quien conecta."""
        self._video_id = ""
        self._url_flujo = (url or "").strip()
        if not self._listo:
            return
        self._detener(silencioso=True)
        self._info = None
        self._calidad_sel = None
        self._alturas = []
        if self._url_flujo and autoplay:
            self._reproducir_flujo()
        elif self._url_flujo:
            self.lbl_estado.SetLabel("Listo. Pulsa Reproducir.")
        else:
            self.lbl_estado.SetLabel("Este directo no trae vídeo reproducible.")

    def detener_todo(self) -> None:
        # Olvidar el vídeo actual: al desconectar el reproductor queda en blanco,
        # como recién abierta la app (sin un id viejo que pudiera relanzarse).
        self._video_id = ""
        self._url_flujo = ""
        if self._listo:
            if self._fs:
                self.alternar_pantalla_completa()
            # Parada en segundo plano: stop() de un flujo en vivo puede tardar
            # varios segundos y, al llamarse desde el hilo de la GUI (desconexión),
            # congelaba la ventana hasta que terminaba.
            self._detener(silencioso=True, en_segundo_plano=True)

    # ── Getters para el gestor de descargas (gui_descargas) ──────────────────
    # NO acoplan con `descargas.py`: este módulo sigue con sus llamadas yt-dlp
    # propias, y el gestor usa estos getters solo para decidir QUÉ descargar
    # (URL actual + si es YouTube no-live). El _info_listo es asíncrono, así
    # que `get_es_live` se evalúa contra el último `_info` cacheado o devuelve
    # False si aún no se cargó.

    def get_url_para_descarga(self) -> str | None:
        """URL o id de YouTube del vídeo actual. None si no hay o es flujo de
        TikTok (que se gatingea en gui.py)."""
        if self._video_id:
            return "https://www.youtube.com/watch?v=" + self._video_id
        return None

    def get_plataforma(self) -> str:
        """Plataforma del vídeo en reproducción: 'youtube' (el panel es siempre
        YouTube; TikTok usa set_flujo y se gatingea en gui.py)."""
        return "youtube"

    def get_es_live(self) -> bool:
        """¿El vídeo actual es un directo en curso? True si yt-dlp ya lo
        clasificó como live. False si aún no se cargó, si es VOD/programado,
        o si la reproducción viene de un flujo HLS de TikTok."""
        if self._info is None:
            return False
        try:    return bool(self._info.get("is_live"))
        except Exception: return False

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

    def _reproducir_flujo(self, reproducir: bool = True):
        """Arranca la URL de flujo directa en VLC (mismo camino final que
        _reproducir_calidad, pero sin pasar por la info de yt-dlp)."""
        if not self._url_flujo or not self._asegurar_player():
            anunciar("El reproductor no está disponible.")
            return
        try:
            media = self._inst.media_new(self._url_flujo)
            for opt in _MEDIA_OPTS:
                media.add_option(opt)
            self._player.set_media(media)
            self._player.audio_set_volume(self._vol)
            self._player.audio_set_mute(self._muted)
            if reproducir:
                self._player.play()
                self._mostrar_pausa(True)
                self._timer.Start(500)
        except Exception as exc:
            logger.warning("reproducir flujo: %s", exc)
            self._error_carga()
            return
        self._pos_ms = self._dur_ms = 0
        # Un directo de TikTok no tiene barra de tiempo: se puede pausar (al
        # reanudar vuelve al momento actual) pero no adelantar ni retroceder.
        self.lbl_estado.SetLabel("En directo (sin barra de tiempo)."
                                 if reproducir else "Listo.")
        if reproducir:
            anunciar("En directo")

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
            # En un directo de TikTok (flujo en vivo, sin línea de tiempo)
            # «reanudar» dejaría el vídeo retrasado; recargamos para volver al
            # momento actual del directo.
            if self._url_flujo:
                self._reproducir_flujo()
            else:
                self._player.set_pause(0)
                self._mostrar_pausa(True)
                self._timer.Start(500)
                anunciar("Reproduciendo")
        else:
            if self._video_id:
                self.cargar(reproducir=True)
            elif self._url_flujo:
                self._reproducir_flujo()

    def _detener(self, silencioso: bool = False, en_segundo_plano: bool = False):
        # Invalida cualquier carga en vuelo (yt-dlp) y desbloquea futuras cargas:
        # sin esto, una carga que termina tras detener/desconectar rearrancaba la
        # reproducción al volver por wx.CallAfter.
        self._gen += 1
        self._cargando = False
        if self._player is not None:
            if en_segundo_plano:
                # Soltar el player en un hilo: stop()+release() de un flujo en
                # vivo puede bloquear segundos. Lo dejamos en None para que el
                # siguiente uso cree uno nuevo (sin carreras con el que se cierra).
                player = self._player
                self._player = None
                def _cerrar():
                    try:    player.stop()
                    except Exception: pass
                    try:    player.release()
                    except Exception: pass
                threading.Thread(target=_cerrar, daemon=True, name="ReproductorStop").start()
            else:
                try:    self._player.stop()
                except Exception: pass
        if hasattr(self, "_timer"):
            self._timer.Stop()
        if hasattr(self, "btn_play"):
            self._mostrar_pausa(False)
            self._fijar_tiempo(0, 0, mover_slider=True, anunciar_t=False)
        if not silencioso:
            anunciar("Detenido")

    def _aviso_sin_barra(self) -> None:
        # En un directo de TikTok no hay línea de tiempo; en un directo de
        # YouTube sí (se puede retroceder dentro del margen que da YouTube).
        if self._url_flujo:
            anunciar("En un directo de TikTok no se puede adelantar ni retroceder")
        else:
            anunciar("No se puede buscar en este momento")

    def _buscar_rel(self, delta_ms: int):
        if self._player is None:
            return
        dur = self._player.get_length()
        if dur <= 0:
            self._aviso_sin_barra()
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

    def _aplicar_volumen(self, delta: int) -> int:
        """Ajusta el volumen (slider + VLC) y devuelve el valor nuevo. Común al
        atajo Ctrl+Arriba/Abajo y a las flechas sobre el deslizador."""
        self._vol = max(0, min(100, self._vol + delta))
        self.sld_vol.SetValue(self._vol)
        if self._player is not None:
            self._player.audio_set_volume(self._vol)
        return self._vol

    def ajustar_volumen(self, delta: int):
        anunciar(f"Volumen reproductor {self._aplicar_volumen(delta)} por ciento")

    # ── Pantalla completa ──────────────────────────────────────────────────────

    def alternar_pantalla_completa(self):
        if not self._asegurar_player():
            return
        if self._fs is None:
            self._fs = _PantallaCompleta(self)
            self._fijar_salida(self._fs.video.GetHandle())
            anunciar("Pantalla completa. Espacio pausa, flechas buscan y ajustan "
                     "volumen, Escape sale.")
        else:
            self._fijar_salida(self._video.GetHandle())
            self._fs.Destroy()
            self._fs = None
            # Devolver el foco al panel: al cerrarse la ventana de pantalla
            # completa, el foco quedaba en el aire (el lector se perdía). Va a un
            # control con nombre accesible del reproductor.
            try:    self.anclar_foco()
            except Exception: pass
            anunciar("Pantalla completa desactivada")

    # ── Tiempo / sliders ──────────────────────────────────────────────────────

    def _fijar_tiempo(self, pos_ms, dur_ms, mover_slider, anunciar_t):
        self._pos_ms = int(pos_ms or 0)
        self._dur_ms = int(dur_ms or 0)
        # Un directo (TikTok/YouTube live) no tiene duración: mostrar «En
        # directo» en vez de un engañoso «5:23 / 0:00».
        if self._dur_ms > 0:
            self.lbl_tiempo.SetLabel(f"{_fmt_t(self._pos_ms)} / {_fmt_t(self._dur_ms)}")
        else:
            self.lbl_tiempo.SetLabel("En directo")
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
            self._aviso_sin_barra()
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
        anunciar(f"Volumen {self._aplicar_volumen(delta)}")

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
