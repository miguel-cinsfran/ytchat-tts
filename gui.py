"""Interfaz wxPython accesible: barra de menú nativa + paneles en notebook.

Rediseño: una sola ventana con barra de menú (que NVDA lee de forma nativa y
que muestra los atajos), barra superior con URL+Conectar, y un notebook con los
paneles Chat en vivo, Comentarios y Reproductor. Al conectar se detecta si la
URL es un directo o un vídeo subido y se ajustan los paneles.
"""

from __future__ import annotations

import logging
import re
import webbrowser

import wx

from config import (
    APP_NAME, APP_VERSION,
    TIPO_TEXTO, TIPO_SUPERCHAT, TIPO_STICKER, TIPO_MIEMBRO,
    FILTROS,
)
from config import parsear_atajos, ATAJOS_DEFAULTS, app_dir, guardar_opcion
import deteccion
import sound_player as _snd
import credenciales
import youtube_api

# Mapeo entre índice de FILTROS y clave persistida en config.ini.
_NOMBRES_FILTRO = ("todos", "texto", "superchat", "miembro")
_IDX_FILTRO     = {"todos": 0, "texto": 1, "superchat": 2, "miembro": 3}


MAX_ITEMS_CHAT  = 500
TIMER_STATUS_MS = 1000
ANCHO_DEFECTO   = 860
ALTO_DEFECTO    = 700
RUTA_CONFIG = None  # se asigna en iniciar_gui() con app_dir()
_URL_RE         = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)

# Índices de las páginas del notebook (solo chat y comentarios; el reproductor
# es una región fija, no una pestaña).
PAG_CHAT = 0
PAG_COMENTARIOS = 1

# Regiones que recorre F6 / Shift+F6.
REG_CONEXION = 0
REG_CONTENIDO = 1
REG_REPRODUCTOR = 2
_NOMBRE_REGION = ("Conexión", "Contenido", "Reproductor")

logger = logging.getLogger(__name__)


# ── accessible_output2 (opcional) ───────────────────────────────────────────
# Si no está instalado o no hay un lector de pantalla activo, los
# `anunciar()` son no-ops silenciosos; la app funciona igual.

_ao2 = None


def _ao2_init():
    global _ao2
    try:
        from accessible_output2.outputs.auto import Auto
        candidate = Auto()
        for out in getattr(candidate, "outputs", []):
            try:
                if out.is_active() and "sapi" not in type(out).__name__.lower():
                    _ao2 = candidate
                    return
            except Exception:
                pass
    except Exception:
        pass


def anunciar(texto: str) -> None:
    if _ao2 is None:
        return
    try:
        _ao2.speak(texto, interrupt=True)
    except Exception:
        pass


# ── Paleta «piedra cálida + terracota» ───────────────────────────────────────
# Base de carbón CÁLIDO (warm stone), no negro puro ni el típico azul/morado.
# Un acento terracota con personalidad y un teal secundario; saturación
# contenida para sesiones largas y buen contraste para quien la ve.

class _T:
    bg      = wx.Colour(28,  25,  23)   # #1C1917  carbón cálido
    surface = wx.Colour(41,  37,  36)   # #292524  paneles, grupos, pestañas
    field   = wx.Colour(54,  49,  46)   # #36312E  campos
    border  = wx.Colour(87,  83,  78)   # #57534E
    text    = wx.Colour(231, 229, 228)  # #E7E5E4  texto principal
    dim     = wx.Colour(168, 162, 158)  # #A8A29E  texto secundario
    accent  = wx.Colour(232, 116, 92)   # #E8745C  terracota (primario)
    accent2 = wx.Colour(45,  157, 143)  # #2D9D8F  teal (secundario)
    gold    = wx.Colour(230, 179, 95)   # #E6B35F  Super Chats
    green   = wx.Colour(138, 176, 120)  # #8AB078  conectado / éxito
    red     = wx.Colour(224, 122, 108)  # #E07A6C  error
    btn     = wx.Colour(54,  49,  46)   # botones secundarios
    btn_t   = wx.Colour(231, 229, 228)
    # Botón primario (Conectar): fondo acento con texto oscuro para destacar.
    primary   = wx.Colour(232, 116, 92)
    primary_t = wx.Colour(28,  25,  23)


def _tc(w, bg=None, fg=None):
    w.SetBackgroundColour(bg or _T.field)
    w.SetForegroundColour(fg or _T.text)


def _titulo(w, color=None):
    """Etiqueta de sección: color de acento y seminegrita, para jerarquía."""
    w.SetForegroundColour(color or _T.accent)
    w.SetFont(w.GetFont().Bold())


_ACCEL_NOMBRES = {
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift",
    "enter": "Enter", "left": "Left", "right": "Right",
    "up": "Up", "down": "Down", "space": "Space",
}


def _fmt_accel(texto: str) -> str:
    """'f5'->'F5', 'ctrl+left'->'Ctrl+Left', 'alt+enter'->'Alt+Enter'.

    Formato que entiende wx para los aceleradores de menú.
    """
    if not texto:
        return ""
    partes = []
    for p in texto.split("+"):
        partes.append(_ACCEL_NOMBRES.get(p, p.upper()))
    return "+".join(partes)


class WxAnnouncingHandler(logging.Handler):
    """Reenvía los mensajes del logger al lector de pantalla."""

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        try:    anunciar(self.format(record))
        except Exception: pass


# ── Frame principal ──────────────────────────────────────────────────────────

class YTChatFrame(wx.Frame):

    def __init__(self, parent, config, cola, stats, worker, parada):
        super().__init__(
            parent,
            title=f"{APP_NAME} v{APP_VERSION}",
            size=(ANCHO_DEFECTO, ALTO_DEFECTO),
            name="VentanaPrincipal",
        )
        self._config    = config
        self._cola      = cola
        self._stats     = stats
        self._worker    = worker
        self._parada    = parada
        self._alive     = True
        self._conectado = False
        self._titulo_stream = ""
        self._tipo_video = deteccion.DESCONOCIDO

        self._chat_all: list = []
        self._chat_vis: list[int] = []
        self._filtro = None

        self._sc_totales: dict[str, float] = {}
        self._canal_por_autor: dict[str, str] = {}
        self._live_chat_id = ""

        # Voz activa (antes era un wx.Choice; ahora es un submenú de radio).
        self._voz_idx = 0
        self._voz_nombre = "—"

        self.on_conectar_cb    = None
        self.on_desconectar_cb = None

        self._atajos = parsear_atajos(config.get("atajos_raw", {}))

        self.SetBackgroundColour(_T.bg)
        self._build_menubar()
        self._build_ui()
        self._bind_events()
        self._init_timer()
        self.Centre()

    # ── Barra de menú ────────────────────────────────────────────────────────

    def _accel(self, accion: str) -> str:
        at = self._atajos.get(accion)
        return ("\t" + _fmt_accel(at.texto)) if at else ""

    def _build_menubar(self):
        mb = wx.MenuBar()

        # Archivo
        m = wx.Menu()
        self.mi_conectar = m.Append(wx.ID_ANY, "&Conectar" + self._accel("conectar"))
        self.mi_desconectar = m.Append(wx.ID_ANY, "&Desconectar" + self._accel("desconectar"))
        m.AppendSeparator()
        mi_salir = m.Append(wx.ID_EXIT, "&Salir\tAlt+F4")
        mb.Append(m, "&Archivo")
        self.Bind(wx.EVT_MENU, lambda e: self._conectar_si_procede(), self.mi_conectar)
        self.Bind(wx.EVT_MENU, lambda e: self._desconectar_si_procede(), self.mi_desconectar)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), mi_salir)

        # Ver
        m = wx.Menu()
        mi_sig = m.Append(wx.ID_ANY, "Región &siguiente\tF6")
        mi_ant = m.Append(wx.ID_ANY, "Región &anterior\tShift+F6")
        m.AppendSeparator()
        mi_conx = m.Append(wx.ID_ANY, "Ir a co&nexión (URL)")
        mi_lista = m.Append(wx.ID_ANY, "Ir a la &lista del panel actual\tAlt+L")
        mi_chat = m.Append(wx.ID_ANY, "Ir a &Chat en vivo")
        mi_com  = m.Append(wx.ID_ANY, "Ir a Co&mentarios")
        mi_rep  = m.Append(wx.ID_ANY, "Ir al &Reproductor")
        m.AppendSeparator()
        # Submenú de filtro (radio).
        sub_f = wx.Menu()
        self.fi_items = []
        for i, (nombre, _) in enumerate(FILTROS):
            it = sub_f.AppendRadioItem(wx.ID_ANY, nombre)
            self.fi_items.append(it)
            self.Bind(wx.EVT_MENU, lambda e, idx=i: self._aplicar_filtro(idx), it)
        m.AppendSubMenu(sub_f, "&Filtro de mensajes")
        m.AppendSeparator()
        mi_estado = m.Append(wx.ID_ANY, "&Anunciar estado" + self._accel("anunciar_estado"))
        mb.Append(m, "&Ver")
        self.Bind(wx.EVT_MENU, lambda e: self._navegar_region(+1), mi_sig)
        self.Bind(wx.EVT_MENU, lambda e: self._navegar_region(-1), mi_ant)
        self.Bind(wx.EVT_MENU, lambda e: self._ir_region(REG_CONEXION), mi_conx)
        self.Bind(wx.EVT_MENU, lambda e: self._ir_lista(), mi_lista)
        self.Bind(wx.EVT_MENU, lambda e: self._ir_pestana(PAG_CHAT), mi_chat)
        self.Bind(wx.EVT_MENU, lambda e: self._ir_pestana(PAG_COMENTARIOS), mi_com)
        self.Bind(wx.EVT_MENU, lambda e: self._ir_region(REG_REPRODUCTOR), mi_rep)
        self.Bind(wx.EVT_MENU, lambda e: self._anunciar_estado(), mi_estado)

        # Voz (TTS)
        m = wx.Menu()
        self.mi_pausa = m.Append(wx.ID_ANY, "&Pausar lectura" + self._accel("pausa"))
        mi_det = m.Append(wx.ID_ANY, "&Detener voz" + self._accel("detener_tts"))
        mi_vac = m.Append(wx.ID_ANY, "&Vaciar cola")
        m.AppendSeparator()
        mi_vmenos = m.Append(wx.ID_ANY, "Hablar más &lento" + self._accel("velocidad_menos"))
        mi_vmas   = m.Append(wx.ID_ANY, "Hablar más &rápido" + self._accel("velocidad_mas"))
        mi_volm   = m.Append(wx.ID_ANY, "&Bajar volumen de la voz" + self._accel("volumen_menos"))
        mi_volM   = m.Append(wx.ID_ANY, "&Subir volumen de la voz" + self._accel("volumen_mas"))
        m.AppendSeparator()
        self.mi_sil_lectura = m.AppendCheckItem(
            wx.ID_ANY, "Silenciar &lectura TTS" + self._accel("silenciar_lectura"))
        self.mi_sil_sonidos = m.AppendCheckItem(
            wx.ID_ANY, "Silenciar s&onidos" + self._accel("silenciar_sonidos"))
        m.AppendSeparator()
        self.voz_submenu = wx.Menu()
        m.AppendSubMenu(self.voz_submenu, "Seleccionar vo&z")
        mb.Append(m, "Vo&z")
        self.Bind(wx.EVT_MENU, self._on_pausa, self.mi_pausa)
        self.Bind(wx.EVT_MENU, self._on_detener_tts, mi_det)
        self.Bind(wx.EVT_MENU, self._on_vaciar, mi_vac)
        self.Bind(wx.EVT_MENU, lambda e: self._ajustar_rate(-1), mi_vmenos)
        self.Bind(wx.EVT_MENU, lambda e: self._ajustar_rate(+1), mi_vmas)
        self.Bind(wx.EVT_MENU, lambda e: self._ajustar_volume(-5), mi_volm)
        self.Bind(wx.EVT_MENU, lambda e: self._ajustar_volume(+5), mi_volM)
        self.Bind(wx.EVT_MENU, lambda e: self._toggle_silenciar_lectura(), self.mi_sil_lectura)
        self.Bind(wx.EVT_MENU, lambda e: self._toggle_silenciar_sonidos(), self.mi_sil_sonidos)

        # Reproductor
        m = wx.Menu()
        mi_rep_play  = m.Append(wx.ID_ANY, "&Reproducir o pausa" + self._accel("rep_play"))
        mi_rep_retro = m.Append(wx.ID_ANY, "R&etroceder 1 minuto" + self._accel("rep_retro"))
        mi_rep_avanz = m.Append(wx.ID_ANY, "&Avanzar 1 minuto" + self._accel("rep_avanz"))
        mi_rep_stop  = m.Append(wx.ID_ANY, "De&tener reproducción" + self._accel("rep_detener"))
        mi_rep_mute  = m.Append(wx.ID_ANY, "&Silenciar o activar audio" + self._accel("rep_mute"))
        mi_rep_fs    = m.Append(wx.ID_ANY, "Pantalla &completa\tCtrl+F")
        # Submenú de calidad (radio). Se elige la disponible más cercana.
        sub_cal = wx.Menu()
        for etiqueta, altura in (("Automática", None), ("1080p", 1080), ("720p", 720),
                                 ("480p", 480), ("360p", 360), ("240p", 240), ("144p", 144)):
            it = sub_cal.AppendRadioItem(wx.ID_ANY, etiqueta)
            self.Bind(wx.EVT_MENU, lambda e, a=altura: self._rep_accion("set_calidad", a), it)
        m.AppendSubMenu(sub_cal, "Ca&lidad del vídeo")
        m.AppendSeparator()
        mi_rep_volm  = m.Append(wx.ID_ANY, "&Bajar volumen del reproductor" + self._accel("rep_vol_menos"))
        mi_rep_volM  = m.Append(wx.ID_ANY, "S&ubir volumen del reproductor" + self._accel("rep_vol_mas"))
        mb.Append(m, "&Reproductor")
        self.Bind(wx.EVT_MENU, lambda e: self._rep_accion("_toggle_play"), mi_rep_play)
        self.Bind(wx.EVT_MENU, lambda e: self._rep_accion("_buscar_rel", -60_000), mi_rep_retro)
        self.Bind(wx.EVT_MENU, lambda e: self._rep_accion("_buscar_rel", +60_000), mi_rep_avanz)
        self.Bind(wx.EVT_MENU, lambda e: self._rep_accion("_detener"), mi_rep_stop)
        self.Bind(wx.EVT_MENU, lambda e: self._rep_accion("_toggle_mute"), mi_rep_mute)
        self.Bind(wx.EVT_MENU, lambda e: self._rep_accion("alternar_pantalla_completa"), mi_rep_fs)
        self.Bind(wx.EVT_MENU, lambda e: self._rep_accion("ajustar_volumen", -20), mi_rep_volm)
        self.Bind(wx.EVT_MENU, lambda e: self._rep_accion("ajustar_volumen", +20), mi_rep_volM)

        # Herramientas
        m = wx.Menu()
        mi_pref = m.Append(wx.ID_ANY, "&Preferencias…")
        m.AppendSeparator()
        self.mi_enviar_live = m.Append(
            wx.ID_ANY, "&Enviar mensaje al chat del directo…" + self._accel("enviar_chat"))
        mb.Append(m, "&Herramientas")
        self.Bind(wx.EVT_MENU, self._on_preferencias, mi_pref)
        self.Bind(wx.EVT_MENU, self._on_enviar_live, self.mi_enviar_live)

        # Ayuda
        m = wx.Menu()
        mi_guia = m.Append(wx.ID_ANY, "&Guía de configuración de la API…")
        mi_about = m.Append(wx.ID_ABOUT, "&Acerca de")
        mb.Append(m, "A&yuda")
        self.Bind(wx.EVT_MENU, lambda e: webbrowser.open(
            "https://github.com/miguel-cinsfran/ytchat-tts/blob/main/docs/CONFIGURACION_API.md"),
            mi_guia)
        self.Bind(wx.EVT_MENU, self._on_about, mi_about)

        self.SetMenuBar(mb)
        self.mi_enviar_live.Enable(False)

    # ── Construcción de la UI ────────────────────────────────────────────────

    def _build_ui(self):
        # Importes diferidos para evitar el ciclo (esos módulos importan de gui).
        from gui_comentarios import ComentariosPanel
        from reproductor import ReproductorPanel

        panel = wx.Panel(self, name="PanelPrincipal")
        panel.SetBackgroundColour(_T.bg)
        panel.SetForegroundColour(_T.text)
        vs = wx.BoxSizer(wx.VERTICAL)

        # ── Barra superior: URL + tipo + Conectar ──
        row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(panel, label="&URL/ID:", name="EtiquetaURL")
        _titulo(lbl)
        row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.txt_url = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER, name="URL del directo o vídeo")
        _tc(self.txt_url)
        self.txt_url.SetToolTip(
            "URL de YouTube o ID de 11 caracteres. Pulsa Enter para conectar.")
        row.Add(self.txt_url, 1, wx.EXPAND | wx.RIGHT, 8)
        self.btn_conectar = wx.Button(panel, label="&Conectar", name="Conectar")
        self.btn_conectar.SetBackgroundColour(_T.primary)
        self.btn_conectar.SetForegroundColour(_T.primary_t)
        self.btn_conectar.SetFont(self.btn_conectar.GetFont().Bold())
        row.Add(self.btn_conectar, 0, wx.ALIGN_CENTER_VERTICAL)
        vs.Add(row, 0, wx.EXPAND | wx.ALL, 12)

        self.lbl_tipo = wx.StaticText(panel, label="Sin conectar. Pega una URL y pulsa Conectar.",
                                      name="TipoVideo")
        self.lbl_tipo.SetForegroundColour(_T.dim)
        vs.Add(self.lbl_tipo, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ── Zona de contenido: notebook + reproductor. Se oculta hasta que hay
        # conexión y se vuelve a ocultar al desconectar (queda solo la barra
        # superior), para que no aparezca todo a medio cargar. ──
        self._zona = wx.Panel(panel, name="ZonaContenido")
        self._zona.SetBackgroundColour(_T.bg)
        zvs = wx.BoxSizer(wx.VERTICAL)

        self.nb = wx.Notebook(self._zona, name="Paneles")
        _tc(self.nb, bg=_T.surface)
        self._pag_chat = self._build_pagina_chat(self.nb)
        self._com_panel = ComentariosPanel(self.nb, self._cola, self._config)
        self.nb.AddPage(self._pag_chat, "Chat en vivo")
        self.nb.AddPage(self._com_panel, "Comentarios")
        # Piso para que la lista del chat no quede aplastada por el reproductor
        # en ventanas bajas.
        self.nb.SetMinSize((-1, 170))
        zvs.Add(self.nb, 3, wx.EXPAND | wx.BOTTOM, 10)

        # Proporción 3/2 (antes el reproductor iba fijo en 0): chat y reproductor
        # comparten el alto sobrante con algo más de peso para el chat —que tiene
        # menos mínimo— para que queden equilibrados; el vídeo crece al agrandar la
        # ventana en vez de quedar fijo y comerse el espacio del chat.
        self._rep_panel = ReproductorPanel(self._zona, self._config)
        zvs.Add(self._rep_panel, 2, wx.EXPAND)

        self._zona.SetSizer(zvs)
        vs.Add(self._zona, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self._zona.Hide()

        panel.SetSizer(vs)
        self._panel_principal = panel

        # Regiones que recorre F6 / Shift+F6.
        self._region_idx = REG_CONTENIDO
        self._regiones = [
            lambda: self.txt_url.SetFocus(),
            self._foco_contenido,
            self._rep_panel.anclar_foco,
        ]

        # 7 campos: estado, velocidad, voz, cola, leídos, volumen, total SC.
        self.sb = self.CreateStatusBar(7, name="BarraEstado")
        self.sb.SetBackgroundColour(_T.surface)
        self.sb.SetForegroundColour(_T.dim)
        self.sb.SetStatusWidths([-3, -1, -3, -1, -1, -1, -2])
        self._actualizar_sb()
        self._set_conectado_ui(False)   # estado inicial: desconectado

    def _build_pagina_chat(self, parent) -> wx.Panel:
        pag = wx.Panel(parent, name="PaginaChat")
        pag.SetBackgroundColour(_T.bg)
        pag.SetForegroundColour(_T.text)
        vs = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(pag, label="Mensajes del chat:", name="EtiquetaChat")
        _titulo(lbl)
        vs.Add(lbl, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        self.lb_chat = wx.ListBox(
            pag, style=wx.LB_SINGLE | wx.LB_HSCROLL, name="Chat en vivo")
        _tc(self.lb_chat)
        pt = int(self._config.get("tamanio_fuente_chat", 12))
        self.lb_chat.SetFont(wx.Font(
            pt, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.lb_chat.SetToolTip(
            "Mensajes del chat. Enter copia el mensaje. "
            "Tecla aplicaciones abre el menú contextual.")
        vs.Add(self.lb_chat, 1, wx.EXPAND | wx.ALL, 8)

        pag.SetSizer(vs)
        return pag

    # ── Enlaces de eventos ───────────────────────────────────────────────────

    def _bind_events(self):
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_ACTIVATE, self._on_activate)
        self.btn_conectar.Bind(wx.EVT_BUTTON, self._on_conectar)
        self.txt_url.Bind(wx.EVT_TEXT_ENTER,  self._on_conectar)
        self.nb.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_nb_page)
        self.lb_chat.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._copiar_mensaje())
        self.lb_chat.Bind(wx.EVT_KEY_DOWN,       self._on_chat_key)
        self.lb_chat.Bind(wx.EVT_CONTEXT_MENU,   self._on_chat_menu)

    def _on_nb_page(self, event):
        # No hay anuncio nativo del cambio de pestaña: lo decimos a mano.
        idx = event.GetSelection()
        if 0 <= idx < self.nb.GetPageCount():
            anunciar(self.nb.GetPageText(idx))
        event.Skip()

    def _on_activate(self, event):
        # Al volver el foco a la app, llevarlo al contenido (chat/comentarios);
        # si aún no hay conexión, al campo de URL.
        if event.GetActive() and self._alive:
            if self._conectado:
                wx.CallAfter(self._foco_contenido)
            else:
                wx.CallAfter(self.txt_url.SetFocus)
        event.Skip()

    def _init_timer(self):
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)
        self._timer.Start(TIMER_STATUS_MS)

    # ── Navegación de paneles ────────────────────────────────────────────────

    def _navegar_region(self, delta: int):
        if not self._conectado:
            self.txt_url.SetFocus()
            anunciar("Conéctate primero para usar los paneles")
            return
        self._region_idx = (self._region_idx + delta) % len(self._regiones)
        self._ir_region(self._region_idx)

    def _ir_region(self, idx: int):
        if not (0 <= idx < len(self._regiones)):
            return
        if idx != REG_CONEXION and not self._conectado:
            anunciar("Conéctate primero para usar los paneles")
            return
        self._region_idx = idx
        try:    self._regiones[idx]()
        except Exception as exc: logger.debug("ir_region %d: %s", idx, exc)
        nombre = _NOMBRE_REGION[idx]
        if idx == REG_CONTENIDO:
            nombre += f": {self.nb.GetPageText(self.nb.GetSelection())}"
        anunciar(nombre)

    def _ir_lista(self):
        """Alt+L: foco directo a la lista de la pestaña actual (chat o comentarios)."""
        if not self._conectado:
            anunciar("Conéctate primero")
            return
        self._region_idx = REG_CONTENIDO
        self._foco_contenido()

    def _foco_contenido(self):
        pag = self.nb.GetCurrentPage()
        if pag is self._pag_chat:
            self.lb_chat.SetFocus()
        elif pag is self._com_panel:
            self._com_panel.anclar_foco()
        else:
            self.nb.SetFocus()

    def _ir_pestana(self, idx: int):
        """Selecciona una pestaña del notebook y deja el foco en su contenido."""
        if 0 <= idx < self.nb.GetPageCount():
            self.nb.SetSelection(idx)
            self._region_idx = REG_CONTENIDO
            self._foco_contenido()
            anunciar(self.nb.GetPageText(idx))

    def _rep_accion(self, metodo: str, *args):
        try:
            getattr(self._rep_panel, metodo)(*args)
        except Exception as exc:
            logger.debug("acción reproductor %s: %s", metodo, exc)

    # ── Handlers de conexión ─────────────────────────────────────────────────

    def _conectar_si_procede(self):
        if not self._conectado:
            self._on_conectar(None)

    def _desconectar_si_procede(self):
        if self._conectado:
            self._on_conectar(None)

    def _on_conectar(self, event):
        if self._conectado:
            if self.on_desconectar_cb:
                self.on_desconectar_cb()
            self.set_conectado(False)
        else:
            url = self.txt_url.GetValue().strip()
            if not url:
                wx.MessageBox("Introduce una URL o ID de YouTube.",
                              "Falta URL", wx.OK | wx.ICON_WARNING, self)
                self.txt_url.SetFocus()
                return
            self.btn_conectar.SetLabel("Conectando...")
            self.btn_conectar.Disable()
            self.mi_conectar.Enable(False)
            self.txt_url.Disable()
            _snd.reproducir("conectando")
            anunciar("Conectando")
            if self.on_conectar_cb:
                self.on_conectar_cb(url)

    def url_invalida(self):
        """La URL/ID no es válida: restaurar la UI y avisar (sin esperas)."""
        if not self._alive:
            return
        _snd.reproducir("error")
        self._set_conectado_ui(False)
        anunciar("La URL o el ID de YouTube no es válido")
        self.txt_url.SetFocus()
        wx.MessageBox("La URL o el ID de YouTube no es válido. Revisa lo que pegaste.",
                      "URL no válida", wx.OK | wx.ICON_WARNING, self)

    def _on_preferencias(self, event):
        try:
            from gui_preferencias import abrir_preferencias
            if abrir_preferencias(self, self._config):
                self._aplicar_preferencias_en_caliente()
        except Exception as exc:
            logger.warning("No se pudo abrir preferencias: %s", exc)
            wx.MessageBox(f"No se pudo abrir Preferencias:\n{exc}",
                          "Error", wx.OK | wx.ICON_ERROR, self)
        # La pestaña API puede haber cambiado la sesión: refrescar.
        self._actualizar_estado_online()

    def _aplicar_preferencias_en_caliente(self):
        # Reconstruir atajos y menú por si cambiaron las teclas.
        self._atajos = parsear_atajos(self._config.get("atajos_raw", {}))
        try:
            voces_actuales = [self.voz_submenu.FindItemByPosition(i).GetItemLabelText()
                              for i in range(self.voz_submenu.GetMenuItemCount())]
        except Exception:
            voces_actuales = []
        self._build_menubar()
        # Restaurar submenú de voz y filtro tras reconstruir.
        if voces_actuales:
            self.poblar_voces(voces_actuales, self._voz_idx)
        self._marcar_filtro()
        self._sincronizar_checks()
        # Reconstruir la lista por si cambió "quitar emojis" o el filtro.
        self._rebuild_listbox()
        # Restaurar estado de los items de conexión y del envío al chat tras
        # reconstruir el menú.
        self._set_conectado_ui(self._conectado)
        self._actualizar_estado_online()
        # Tamaño de fuente del chat.
        try:
            pt = int(self._config.get("tamanio_fuente_chat", 12))
            self.lb_chat.SetFont(wx.Font(pt, wx.FONTFAMILY_DEFAULT,
                                         wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        except Exception:
            pass
        anunciar("Preferencias aplicadas")

    def _on_about(self, event):
        wx.MessageBox(
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "Lector accesible del chat de YouTube Live con voz SAPI5.",
            "Acerca de", wx.OK | wx.ICON_INFORMATION, self)

    # ── Handlers de voz / TTS ────────────────────────────────────────────────

    def _on_pausa(self, event):
        self._worker.toggle_pausa()
        pausado = self._worker.esta_pausado()
        self.mi_pausa.SetItemLabel(
            ("&Reanudar lectura" if pausado else "&Pausar lectura") + self._accel("pausa"))
        _snd.reproducir("pausa" if pausado else "reanudar")
        anunciar("Pausado" if pausado else "Reanudado")

    def _on_vaciar(self, event):
        self._worker.vaciar_cola()
        _snd.reproducir("cola_vaciada")
        anunciar("Cola vaciada")

    def _on_detener_tts(self, event):
        self._worker.detener_actual()
        anunciar("TTS detenido")

    def _aplicar_voz(self, idx: int):
        self._worker.cambiar_voz(idx)
        self._voz_idx = idx
        try:    self._voz_nombre = self._nombre_voz(idx)
        except Exception: self._voz_nombre = "—"
        self._config["voz"] = str(idx)
        guardar_opcion(RUTA_CONFIG, "voz", "voz", str(idx))
        _snd.reproducir("voz_cambiada")
        anunciar(f"Voz: {self._voz_nombre}")

    def _nombre_voz(self, idx: int) -> str:
        it = self.voz_submenu.FindItemByPosition(idx)
        return it.GetItemLabelText() if it else "—"

    def _aplicar_filtro(self, idx: int):
        self._filtro = FILTROS[idx][1] if idx < len(FILTROS) else None
        self._rebuild_listbox()
        guardar_opcion(RUTA_CONFIG, "ui", "filtro_activo",
                       _NOMBRES_FILTRO[idx] if idx < len(_NOMBRES_FILTRO) else "todos")
        anunciar(f"Filtro: {FILTROS[idx][0]}. {self.lb_chat.GetCount()} mensajes")

    def _ajustar_rate(self, delta):
        self._worker.cambiar_rate(delta)
        r = max(-10, min(10, self._worker.get_rate() + delta))
        wpm = max(50, min(500, r * 20 + 180))
        guardar_opcion(RUTA_CONFIG, "voz", "velocidad", str(wpm))
        anunciar(f"Velocidad de la voz: {r:+d}")

    def _ajustar_volume(self, delta):
        self._worker.cambiar_volumen(delta)
        v = max(0, min(100, self._worker.get_volume() + delta))
        guardar_opcion(RUTA_CONFIG, "voz", "volumen", f"{v / 100:.2f}")
        anunciar(f"Volumen de la voz: {v}%")

    def _toggle_silenciar_sonidos(self):
        nuevo = not _snd.esta_silenciado()
        _snd.silenciar_todo(nuevo)
        self._config["silenciar_sonidos"] = nuevo
        self.mi_sil_sonidos.Check(nuevo)
        guardar_opcion(RUTA_CONFIG, "ui", "silenciar_sonidos", "true" if nuevo else "false")
        anunciar("Sonidos silenciados" if nuevo else "Sonidos activados")

    def _toggle_silenciar_lectura(self):
        nuevo = not self._config.get("silenciar_lectura", False)
        self._config["silenciar_lectura"] = nuevo
        self.mi_sil_lectura.Check(nuevo)
        guardar_opcion(RUTA_CONFIG, "sesion", "silenciar_lectura", "true" if nuevo else "false")
        anunciar("Lectura TTS silenciada" if nuevo else "Lectura TTS activada")

    def _anunciar_estado(self):
        partes = []
        if self._conectado and self._titulo_stream:
            partes.append(f"Conectado a {self._titulo_stream[:40]}")
        elif self._conectado:
            partes.append("Conectado")
        else:
            partes.append("Desconectado")
        try:    partes.append(f"cola {self._cola.qsize()}")
        except Exception: pass
        try:    partes.append(f"leídos {self._stats.leidos}")
        except Exception: pass
        try:    partes.append(f"velocidad {self._worker.get_rate():+d}")
        except Exception: pass
        try:    partes.append(f"volumen {self._worker.get_volume()} por ciento")
        except Exception: pass
        if self._config.get("silenciar_lectura", False):
            partes.append("lectura silenciada")
        anunciar(". ".join(partes))

    # ── Enviar al chat del directo (API oficial) ─────────────────────────────

    def _on_enviar_live(self, event):
        if not self._puede_escribir_live():
            return
        dlg = wx.TextEntryDialog(self, "Mensaje a enviar al chat del directo:",
                                 "Enviar al chat")
        if dlg.ShowModal() == wx.ID_OK:
            texto = dlg.GetValue().strip()
            if texto:
                lcid = self._live_chat_id
                self._accion_api(lambda cli: cli.enviar_mensaje_live(lcid, texto),
                                 "Mensaje enviado al chat")
        dlg.Destroy()

    def _puede_escribir_live(self) -> bool:
        if not (youtube_api.google_disponible() and credenciales.hay_sesion()):
            anunciar("Inicia sesión en Configuración de API para usar esta función")
            return False
        if not self._live_chat_id:
            anunciar("No hay un chat en vivo activo en este directo")
            return False
        return True

    def _accion_api(self, accion, mensaje_ok: str, sonido: str = "enviado") -> None:
        anunciar("Enviando")

        def _run():
            try:
                cli = youtube_api.ClienteYouTube(credenciales.cargar())
                accion(cli)
                if cli.token_actualizado():
                    credenciales.guardar_campo("token", cli.token_actualizado())
                wx.CallAfter(self._api_ok, mensaje_ok, sonido)
            except Exception as exc:
                logger.warning("acción API: %s", exc)
                wx.CallAfter(self._api_err, exc)

        import threading
        threading.Thread(target=_run, daemon=True, name="AccionAPI").start()

    def _api_ok(self, mensaje, sonido: str = "enviado"):
        _snd.reproducir(sonido)
        anunciar(mensaje)

    def _api_err(self, exc):
        _snd.reproducir("error")
        msg = youtube_api.mensaje_error_api(exc)
        anunciar(msg)
        wx.MessageBox(msg, "Error de la API", wx.OK | wx.ICON_ERROR, self)

    def _actualizar_estado_online(self):
        puede = bool(self._conectado and self._live_chat_id
                     and youtube_api.google_disponible() and credenciales.hay_sesion())
        try:    self.mi_enviar_live.Enable(puede)
        except Exception: pass

    def _moderar(self, autor: str, canal_id: str, segundos: int | None) -> None:
        accion = "expulsar 5 minutos a" if segundos else "banear permanentemente a"
        if wx.MessageBox(f"¿Seguro que quieres {accion} {autor}?",
                         "Confirmar moderación",
                         wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return
        lcid = self._live_chat_id
        ok = f"{autor} expulsado 5 minutos" if segundos else f"{autor} baneado del directo"
        self._accion_api(
            lambda cli: cli.banear_usuario(lcid, canal_id, segundos), ok,
            sonido="moderacion")

    # ── Atajos sobre la lista de chat ────────────────────────────────────────

    def _copiar_atajo(self):
        if self.lb_chat.GetSelection() == wx.NOT_FOUND:
            anunciar("Sin mensaje seleccionado")
        else:
            self._copiar_mensaje()

    # ── Chat: teclado, menú, copiar, silenciar ───────────────────────────────

    def _on_chat_key(self, event):
        k = event.GetKeyCode()
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._copiar_mensaje()
        elif k == ord('C') and event.ControlDown():
            self._copiar_mensaje()
        elif k == wx.WXK_WINDOWS_MENU:
            self._mostrar_menu_chat()
        else:
            event.Skip()

    def _on_chat_menu(self, event):
        self._mostrar_menu_chat()

    def _mostrar_menu_chat(self):
        idx = self.lb_chat.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        menu = wx.Menu()

        id_copiar   = wx.NewIdRef()
        id_copiar2  = wx.NewIdRef()
        id_releer   = wx.NewIdRef()
        id_link     = wx.NewIdRef()
        id_sil_tts  = wx.NewIdRef()
        id_sil_full = wx.NewIdRef()
        id_rehab    = wx.NewIdRef()

        menu.Append(id_copiar,  "Copiar mensaje")
        menu.Append(id_copiar2, "Copiar todo (autor: mensaje, hora)")
        menu.Append(id_releer,  "Releer con TTS")
        menu.AppendSeparator()
        menu.Append(id_link,    "Abrir enlace")
        menu.AppendSeparator()

        autor = self._autor_seleccionado() or ""
        if autor:
            if self._autor_esta_silenciado(autor):
                menu.Append(id_rehab, f"Rehabilitar a {autor} (dejar de silenciar)")
            else:
                menu.Append(id_sil_tts,  f"Silenciar a {autor} (solo TTS)")
                menu.Append(id_sil_full, f"Silenciar a {autor} (ocultar y TTS)")

        id_ban     = wx.NewIdRef()
        id_timeout = wx.NewIdRef()
        canal_autor = self._canal_por_autor.get(autor.lower().strip(), "")
        moderable = bool(autor and canal_autor and self._live_chat_id
                         and youtube_api.google_disponible() and credenciales.hay_sesion())
        if moderable:
            menu.AppendSeparator()
            menu.Append(id_timeout, f"Expulsar 5 min a {autor} (timeout)")
            menu.Append(id_ban,     f"Banear a {autor} del directo (permanente)")
            self.Bind(wx.EVT_MENU, lambda e: self._moderar(autor, canal_autor, 300), id=id_timeout)
            self.Bind(wx.EVT_MENU, lambda e: self._moderar(autor, canal_autor, None), id=id_ban)

        self.Bind(wx.EVT_MENU, lambda e: self._copiar_mensaje(), id=id_copiar)
        self.Bind(wx.EVT_MENU, lambda e: self._copiar_todo(),    id=id_copiar2)
        self.Bind(wx.EVT_MENU, lambda e: self._releer_mensaje(), id=id_releer)
        self.Bind(wx.EVT_MENU, lambda e: self._abrir_enlace(),   id=id_link)
        self.Bind(wx.EVT_MENU, lambda e: self._silenciar_autor(autor, ocultar=False), id=id_sil_tts)
        self.Bind(wx.EVT_MENU, lambda e: self._silenciar_autor(autor, ocultar=True),  id=id_sil_full)
        self.Bind(wx.EVT_MENU, lambda e: self._rehabilitar_autor(autor),              id=id_rehab)

        self.lb_chat.PopupMenu(menu)
        menu.Destroy()

    def _copiar_mensaje(self):
        data = self._get_selected_data()
        if data is None:
            return
        _, mensaje, _, _, _ = data
        self._clipboard_set(mensaje)
        _snd.reproducir("copiar")
        anunciar("Mensaje copiado")

    def _copiar_todo(self):
        data = self._get_selected_data()
        if data is None:
            return
        autor, msg, hora, _, monto = data
        linea = f"{autor}: {msg}, {hora}"
        if monto:
            linea += f" [{monto}]"
        self._clipboard_set(linea)
        _snd.reproducir("copiar")
        anunciar("Línea copiada")

    def _releer_mensaje(self):
        data = self._get_selected_data()
        if data is None:
            return
        autor, msg, _, _, _ = data
        from tts_worker import construir_tts
        self._cola.put({"texto_tts": construir_tts(autor, msg, self._config)})

    def _abrir_enlace(self):
        data = self._get_selected_data()
        if data is None:
            return
        _, msg, _, _, _ = data
        urls = _URL_RE.findall(msg)
        if not urls:
            anunciar("No se encontró ningún enlace")
            wx.MessageBox("No se encontró ningún enlace en este mensaje.",
                          "Sin enlace", wx.OK | wx.ICON_INFORMATION, self)
            return
        webbrowser.open(urls[0])
        anunciar("Abriendo enlace")

    # ── Silenciado en caliente ───────────────────────────────────────────────

    def _silenciar_autor(self, autor: str, ocultar: bool) -> None:
        if not autor:
            return
        al = autor.lower().strip()
        self._config.setdefault("silenciados_runtime", set()).add(al)
        sil_oculto = self._config.setdefault("silenciados_ocultar", set())
        if ocultar:
            sil_oculto.add(al)
            self._rebuild_listbox()
        else:
            sil_oculto.discard(al)
        anunciar(f"{autor} silenciado")

    def _rehabilitar_autor(self, autor: str) -> None:
        if not autor:
            return
        al = autor.lower().strip()
        self._config.setdefault("silenciados_runtime", set()).discard(al)
        self._config.setdefault("silenciados_ocultar", set()).discard(al)
        self._rebuild_listbox()
        anunciar(f"{autor} rehabilitado")

    def _autor_esta_silenciado(self, autor: str) -> bool:
        return autor.lower().strip() in self._config.get("silenciados_runtime", set())

    def _autor_esta_oculto(self, autor: str) -> bool:
        return autor.lower().strip() in self._config.get("silenciados_ocultar", set())

    def _autor_seleccionado(self) -> str | None:
        data = self._get_selected_data()
        return data[0] if data else None

    # ── Selección y portapapeles ─────────────────────────────────────────────

    def _get_selected_data(self):
        idx = self.lb_chat.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._chat_vis):
            return None
        real_idx = self._chat_vis[idx]
        if real_idx >= len(self._chat_all):
            return None
        return self._chat_all[real_idx]

    def _clipboard_set(self, text: str) -> None:
        try:
            if wx.TheClipboard.Open():
                try:
                    wx.TheClipboard.SetData(wx.TextDataObject(text))
                    wx.TheClipboard.Flush()
                finally:
                    wx.TheClipboard.Close()
                return
        except Exception:
            pass
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            u32 = ctypes.windll.user32
            if not u32.OpenClipboard(0):
                return
            try:
                u32.EmptyClipboard()
                encoded = text.encode("utf-16-le") + b"\x00\x00"
                h = k32.GlobalAlloc(0x0042, len(encoded))
                if not h:
                    return
                p = k32.GlobalLock(h)
                if not p:
                    k32.GlobalFree(h)
                    return
                ctypes.memmove(p, encoded, len(encoded))
                k32.GlobalUnlock(h)
                if not u32.SetClipboardData(13, h):  # CF_UNICODETEXT
                    k32.GlobalFree(h)
            finally:
                u32.CloseClipboard()
        except Exception:
            pass

    # ── Cierre y timer ───────────────────────────────────────────────────────

    def _on_close(self, event):
        self._alive = False
        try:    self._timer.Stop()
        except Exception: pass
        if self.on_desconectar_cb:
            try:    self.on_desconectar_cb()
            except Exception: pass
        self._parada.set()
        try:
            self._rep_panel.detener_todo()
        except Exception: pass
        try:
            # Interrumpir lo que se esté leyendo (purga) antes de parar, para que
            # el cierre sea inmediato y no termine el mensaje en curso.
            self._worker.detener_actual()
            self._worker.detener()
        except Exception: pass
        try:    _snd.cerrar()
        except Exception: pass
        self.Destroy()

    def _on_timer(self, event):
        if self._alive:
            try:    self._actualizar_sb()
            except Exception: pass

    # ── API pública (main.py la invoca vía wx.CallAfter) ─────────────────────

    def agregar_mensaje_chat(self, autor: str, mensaje: str, hora: str,
                             tipo: str = TIPO_TEXTO, monto: str = "",
                             canal_id: str = "") -> None:
        if not self._alive:
            return
        if canal_id:
            self._canal_por_autor[autor.lower().strip()] = canal_id
        if self._autor_esta_oculto(autor):
            return

        while len(self._chat_all) >= MAX_ITEMS_CHAT:
            self._chat_all.pop(0)
            self._chat_vis = [i - 1 for i in self._chat_vis if i > 0]

        idx_all = len(self._chat_all)
        self._chat_all.append((autor, mensaje, hora, tipo, monto))

        if tipo in (TIPO_SUPERCHAT, TIPO_STICKER):
            _snd.reproducir("superchat")
            self._sumar_superchat(monto)
        elif tipo == TIPO_MIEMBRO:
            _snd.reproducir("nuevo_miembro")
        else:
            _snd.reproducir("mensaje_nuevo")

        if self._filtro is None or tipo == self._filtro:
            self._chat_vis.append(idx_all)
            self.lb_chat.Append(self._format_display(autor, mensaje, hora, tipo, monto))
            while self.lb_chat.GetCount() > MAX_ITEMS_CHAT:
                self.lb_chat.Delete(0)
                if self._chat_vis:
                    self._chat_vis.pop(0)
            if wx.Window.FindFocus() is not self.lb_chat:
                self.lb_chat.SetFirstItem(self.lb_chat.GetCount() - 1)

    def set_conectado(self, conectado: bool) -> None:
        if not self._alive:
            return
        estaba = self._conectado
        self._conectado = conectado
        if conectado:
            if not estaba:
                self._mostrar_zona(True)
                self._region_idx = REG_CONTENIDO
                self._anunciar_conectado()
                wx.CallAfter(self._foco_contenido)
        else:
            self._live_chat_id = ""
            self._canal_por_autor.clear()
            try:    self._rep_panel.detener_todo()
            except Exception: pass
            # Al desconectar se corta la lectura: vaciar la cola y detener lo
            # que se esté leyendo en ese momento.
            try:
                self._worker.vaciar_cola()
                self._worker.detener_actual()
            except Exception: pass
            # Solo si veníamos de una conexión real: ocultar, sonar y avisar.
            # (Un fallo de conexión nunca llegó a "conectado", así que no suena.)
            if estaba:
                self._mostrar_zona(False)
                self.set_titulo_stream("")
                self.lbl_tipo.SetLabel("Sin conectar. Pega una URL y pulsa Conectar.")
                _snd.reproducir("desconectado")
                anunciar("Desconectado")
        self._set_conectado_ui(conectado)
        self._actualizar_estado_online()

    def _mostrar_zona(self, mostrar: bool) -> None:
        self._zona.Show(mostrar)
        self._panel_principal.Layout()

    def _anunciar_conectado(self) -> None:
        t = self._tipo_video
        if t == deteccion.LIVE:
            msg = "Conectado al directo. Leyendo el chat en vivo."
        elif t == deteccion.UPCOMING:
            msg = "Directo programado. Aún no hay chat; puedes ver los comentarios."
        elif t == deteccion.VOD:
            msg = "Vídeo conectado. Comentarios y reproductor disponibles."
        else:
            msg = "Conectado."
        anunciar(msg)

    def set_live_chat_id(self, live_chat_id: str) -> None:
        if not self._alive:
            return
        self._live_chat_id = live_chat_id or ""
        self._actualizar_estado_online()

    def set_tipo_video(self, tipo: str, video_id: str) -> None:
        if not self._alive:
            return
        self._tipo_video = tipo
        es_live = deteccion.tiene_chat_en_vivo(tipo)
        autoplay = bool(self._config.get("autoplay_reproductor", True))
        # Comentarios: autocargar solo cuando no hay chat en vivo (en un directo
        # no queremos saturar). Reproductor: siempre, con autoplay según prefs.
        try:    self._com_panel.set_video(video_id, autocargar=not es_live)
        except Exception: pass
        try:    self._rep_panel.set_video(video_id, autoplay=autoplay)
        except Exception: pass

        if tipo == deteccion.LIVE:
            self.lbl_tipo.SetLabel("Directo en vivo: leyendo el chat.")
            self.nb.SetSelection(PAG_CHAT)
        elif tipo == deteccion.UPCOMING:
            self.lbl_tipo.SetLabel("Directo programado: aún sin chat. Hay comentarios.")
            self.nb.SetSelection(PAG_COMENTARIOS)
        elif tipo == deteccion.VOD:
            self.lbl_tipo.SetLabel("Vídeo subido: comentarios y reproductor.")
            self.nb.SetSelection(PAG_COMENTARIOS)
        else:
            self.lbl_tipo.SetLabel("Tipo no determinado: intentando leer el chat.")

    def set_url(self, url: str) -> None:
        self.txt_url.SetValue(url)

    def set_titulo_stream(self, titulo: str) -> None:
        if not self._alive:
            return
        self._titulo_stream = (titulo or "").strip()
        if self._titulo_stream:
            # Formato tipo navegador: «Nombre del vídeo — YTChat TTS».
            self.SetTitle(f"{self._titulo_stream} — {APP_NAME}")
        else:
            self.SetTitle(f"{APP_NAME} v{APP_VERSION}")

    def auto_conectar(self) -> None:
        self._on_conectar(None)

    def poblar_voces(self, voces: list, idx_actual: int = 0) -> None:
        # Vaciar el submenú de voz y reconstruir con radio items.
        for it in list(self.voz_submenu.GetMenuItems()):
            self.voz_submenu.Delete(it)
        if not voces:
            it = self.voz_submenu.Append(wx.ID_ANY, "(no disponible)")
            it.Enable(False)
            self._voz_nombre = "—"
            return
        for i, nombre in enumerate(voces):
            it = self.voz_submenu.AppendRadioItem(wx.ID_ANY, nombre)
            self.Bind(wx.EVT_MENU, lambda e, idx=i: self._aplicar_voz(idx), it)
        idx_actual = idx_actual if 0 <= idx_actual < len(voces) else 0
        self.voz_submenu.FindItemByPosition(idx_actual).Check(True)
        self._voz_idx = idx_actual
        self._voz_nombre = voces[idx_actual]

    def _marcar_filtro(self):
        idx = _IDX_FILTRO.get(
            _NOMBRES_FILTRO[0] if self._filtro is None else "", 0)
        # Buscar el índice cuyo valor coincide con self._filtro.
        for i, (_, val) in enumerate(FILTROS):
            if val == self._filtro:
                idx = i
                break
        if 0 <= idx < len(self.fi_items):
            self.fi_items[idx].Check(True)

    def _sincronizar_checks(self):
        try:    self.mi_sil_sonidos.Check(_snd.esta_silenciado())
        except Exception: pass
        try:    self.mi_sil_lectura.Check(self._config.get("silenciar_lectura", False))
        except Exception: pass

    # ── Formato y helpers ────────────────────────────────────────────────────

    def _format_display(self, autor, msg, hora, tipo, monto):
        # Si "quitar emojis" está activo, también se ocultan en la lista (incluye
        # los shortcodes :nombre: de YouTube). Los marcadores 💲🎨⭐ se conservan.
        if self._config.get("limpiar_emojis", True):
            from tts_worker import quitar_emojis
            msg = quitar_emojis(msg)
        if tipo == TIPO_SUPERCHAT and monto:
            return f"💲 [{monto}] {autor}: {msg}, {hora}"
        if tipo == TIPO_STICKER and monto:
            return f"🎨 [{monto}] {autor}, {hora}"
        if tipo == TIPO_MIEMBRO:
            return f"⭐ NUEVO MIEMBRO: {autor}, {hora}"
        return f"{autor}: {msg}, {hora}"

    def _rebuild_listbox(self) -> None:
        self.lb_chat.Clear()
        self._chat_vis.clear()
        for i, (autor, msg, hora, tipo, monto) in enumerate(self._chat_all):
            if self._autor_esta_oculto(autor):
                continue
            if self._filtro is None or tipo == self._filtro:
                self._chat_vis.append(i)
                self.lb_chat.Append(self._format_display(autor, msg, hora, tipo, monto))

    def _set_conectado_ui(self, conectado: bool) -> None:
        # Botón (toggle), items de menú Conectar/Desconectar y campo URL. El
        # resto (ocultar zona, sonido, título) lo gestiona set_conectado.
        self.btn_conectar.SetLabel("&Desconectar" if conectado else "&Conectar")
        self.btn_conectar.Enable()
        self.mi_conectar.Enable(not conectado)
        self.mi_desconectar.Enable(conectado)
        self.txt_url.Enable(not conectado)

    def _actualizar_sb(self) -> None:
        sin_tts = " [sin TTS]" if self._config.get("silenciar_lectura", False) else ""
        if self._conectado and self._titulo_stream:
            estado = f"Conectado: {self._titulo_stream[:35]}{sin_tts}"
        elif self._conectado:
            estado = f"Conectado{sin_tts}"
        else:
            estado = f"Desconectado{sin_tts}"
        self.sb.SetStatusText(estado, 0)

        try:    self.sb.SetStatusText(f"Voz vel: {self._worker.get_rate():+d}", 1)
        except Exception: self.sb.SetStatusText("Voz vel: --", 1)

        nombre = self._voz_nombre or "—"
        if len(nombre) > 28:
            nombre = nombre[:25] + "..."
        self.sb.SetStatusText(f"Voz: {nombre}", 2)

        try:    self.sb.SetStatusText(f"Cola: {self._cola.qsize()}", 3)
        except Exception: self.sb.SetStatusText("Cola: —", 3)
        try:    self.sb.SetStatusText(f"Leídos: {self._stats.leidos}", 4)
        except Exception: self.sb.SetStatusText("Leídos: —", 4)

        try:    self.sb.SetStatusText(f"Voz vol: {self._worker.get_volume()}%", 5)
        except Exception: self.sb.SetStatusText("Voz vol: --", 5)

        if self._config.get("mostrar_total_superchats", True):
            self.sb.SetStatusText(self._formato_total_sc(), 6)
        else:
            self.sb.SetStatusText("", 6)

    # ── Acumulación de Super Chats ───────────────────────────────────────────

    def _sumar_superchat(self, monto: str) -> None:
        from montos import parsear_monto
        r = parsear_monto(monto)
        if r is None:
            return
        divisa, valor = r
        self._sc_totales[divisa] = self._sc_totales.get(divisa, 0.0) + valor

    def _formato_total_sc(self) -> str:
        try:    n = self._stats.superchats
        except Exception: n = 0
        if not self._sc_totales:
            return f"SC: {n}"
        if len(self._sc_totales) == 1:
            d, t = next(iter(self._sc_totales.items()))
            return f"SC: {n} ({d}{t:.2f})"
        partes = [f"{d}{t:.0f}" for d, t in self._sc_totales.items()]
        return f"SC: {n} ({', '.join(partes)})"


# ── Helpers de voces ─────────────────────────────────────────────────────────

def _listar_voces_sapi5() -> list:
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass
    try:
        import win32com.client
        tts   = win32com.client.Dispatch("SAPI.SpVoice")
        voces = tts.GetVoices()
        return [voces.Item(i).GetDescription() for i in range(voces.Count)]
    except Exception:
        return []


def _resolver_idx_voz(cfg: str, voces: list) -> int:
    try:
        idx = int(cfg)
        return idx if 0 <= idx < len(voces) else 0
    except ValueError:
        t = str(cfg).lower()
        for i, v in enumerate(voces):
            if t in v.lower():
                return i
        return 0


# ── Entrada ──────────────────────────────────────────────────────────────────

_gui_frame: YTChatFrame | None = None


def iniciar_gui(config, cola, stats, worker, parada,
                url_inicial: str = "",
                iniciar_captura_cb=None,
                detener_captura_cb=None) -> None:
    global _gui_frame, RUTA_CONFIG

    RUTA_CONFIG = app_dir() / "config.ini"
    _ao2_init()

    app = wx.App(redirect=False)
    frame = YTChatFrame(None, config, cola, stats, worker, parada)
    _gui_frame = frame
    frame.on_conectar_cb    = iniciar_captura_cb
    frame.on_desconectar_cb = detener_captura_cb

    h = WxAnnouncingHandler()
    h.setLevel(logging.INFO)
    logging.getLogger().addHandler(h)

    voces = _listar_voces_sapi5()
    frame.poblar_voces(voces, _resolver_idx_voz(config.get("voz", "0"), voces))

    # Restaurar filtro de la sesión anterior.
    fa = config.get("filtro_activo", "todos")
    idx_f = _IDX_FILTRO.get(fa, 0)
    if 0 <= idx_f < len(FILTROS):
        frame._filtro = FILTROS[idx_f][1]
        frame._marcar_filtro()

    # Restaurar silenciado de sonidos si la sesión anterior lo tenía activo.
    if config.get("silenciar_sonidos", False):
        _snd.silenciar_todo(True)
    frame._sincronizar_checks()

    if url_inicial:
        frame.set_url(url_inicial)

    frame.Show()
    _snd.reproducir("app_inicio")

    if url_inicial and iniciar_captura_cb:
        wx.CallAfter(frame.auto_conectar)

    app.MainLoop()
    _gui_frame = None

    try:    logging.getLogger().removeHandler(h)
    except Exception: pass
