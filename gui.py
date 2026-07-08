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
import metadatos
import estado_sesion
from lista_chat import ListaChat
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

# Mensaje bajo la barra de URL cuando no hay conexión. Breve pero completo:
# qué se puede pegar y cómo conectar.
MENSAJE_INICIAL = ("Sin conectar. Pega un enlace de YouTube (directo o vídeo) o "
                   "de un directo de TikTok y pulsa Conectar (Alt+C). En YouTube "
                   "podrás leer el chat y los comentarios; en TikTok, el chat del "
                   "directo.")
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

# Posición del menú «Reproductor» en la barra (Archivo, Ver, Voz, Reproductor,
# Herramientas, Ayuda). Se deshabilita entero cuando no hay conexión.
POS_MENU_REPRODUCTOR = 3

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
    # También a la línea braille, como hace TWBlue (output.speak): quien usa
    # pantalla braille sin voz recibe igualmente los anuncios de la app.
    try:
        _ao2.braille(texto)
    except Exception:
        pass


# ── Nombre accesible reforzado (MSAA) ─────────────────────────────────────────
# Patrón tomado de eleven-tts-studio: en Windows, `SetName` por sí solo no
# siempre lo anuncian NVDA/JAWS de forma fiable (sobre todo en deslizadores y en
# ventanas genéricas como la superficie de vídeo). Reforzamos con un
# `wx.Accessible` explícito que expone el nombre por MSAA. Solo se usa en los
# controles donde el nombre flojea; los estándar (botones, casillas) ya se leen
# bien con `name=` y no hace falta.

class _NombreAccesible(wx.Accessible):
    """Expone el nombre del control por MSAA. Solo nombra el control en sí
    (childId 0); las filas/hijos (p. ej. cada línea de una lista) las deja al
    proveedor por defecto, o todas se anunciarían con el nombre de la lista."""

    def __init__(self, nombre: str):
        super().__init__()
        self._nombre = nombre

    def GetName(self, childId):
        if childId == 0:
            return (wx.ACC_OK, self._nombre)
        return (wx.ACC_NOT_IMPLEMENTED, "")


def nombre_accesible(ctrl, nombre: str) -> None:
    """Refuerza el nombre accesible de un control. Mantiene los tooltips ricos
    que ya tengamos (solo pone uno si falta) y no altera el rol ni el valor: el
    `wx.Accessible` solo sobrescribe el nombre y delega el resto."""
    ctrl.SetName(nombre)
    if not ctrl.GetToolTip():
        ctrl.SetToolTip(nombre)
    try:    ctrl.SetHelpText(nombre)   # JAWS lee el help text en algunos controles
    except Exception: pass
    try:
        acc = _NombreAccesible(nombre)
        ctrl.SetAccessible(acc)
        ctrl._nombre_accesible = acc   # evita que el GC se lo lleve
    except Exception:
        pass  # fuera de Windows o sin MSAA: el name/tooltip siguen aplicando


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
        self._es_tiktok = False   # para que F2 distinga TikTok de YouTube (ambos LIVE)

        self._chat = ListaChat(MAX_ITEMS_CHAT)
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
        self._mi_filtro_sub = m.AppendSubMenu(sub_f, "&Filtro de mensajes")
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
        # De «Ver», solo tiene sentido con conexión la navegación por paneles;
        # «Ir a conexión (URL)» y «Anunciar estado» quedan siempre disponibles.
        self._mi_ver_conexion = [mi_sig, mi_ant, mi_lista, mi_chat, mi_com, mi_rep]

        # Voz (TTS)
        m = wx.Menu()
        self.mi_pausa = m.Append(wx.ID_ANY, "&Pausar lectura" + self._accel("pausa"))
        mi_det = m.Append(wx.ID_ANY, "&Detener voz" + self._accel("detener_tts"))
        mi_vac = m.Append(wx.ID_ANY, "&Vaciar cola")
        # Estas tres actúan sobre una lectura en curso: sin conexión no hay nada
        # que pausar/detener/vaciar. Los ajustes de voz de abajo sí quedan libres.
        self._mi_voz_conexion = [self.mi_pausa, mi_det, mi_vac]
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
        m.AppendSeparator()
        self.mi_rep_botones = m.AppendCheckItem(wx.ID_ANY, "Mostrar &botones en pantalla")
        self.mi_rep_botones.Check(bool(self._config.get("mostrar_botones_reproductor", False)))
        self.Bind(wx.EVT_MENU, lambda e: self._toggle_botones_rep(), self.mi_rep_botones)
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
            wx.ID_ANY,
            "&Enviar mensaje al chat del directo (solo YouTube)…" + self._accel("enviar_chat"))
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
            "Enlace de YouTube (directo o vídeo) o de un directo de TikTok "
            "(tiktok.com/@usuario/live). También vale el ID de 11 caracteres de "
            "YouTube. Pulsa Enter para conectar.")
        row.Add(self.txt_url, 1, wx.EXPAND | wx.RIGHT, 8)
        self.btn_conectar = wx.Button(panel, label="&Conectar", name="Conectar")
        self.btn_conectar.SetBackgroundColour(_T.primary)
        self.btn_conectar.SetForegroundColour(_T.primary_t)
        self.btn_conectar.SetFont(self.btn_conectar.GetFont().Bold())
        row.Add(self.btn_conectar, 0, wx.ALIGN_CENTER_VERTICAL)
        vs.Add(row, 0, wx.EXPAND | wx.ALL, 12)

        self.lbl_tipo = wx.StaticText(panel, label=MENSAJE_INICIAL, name="TipoVideo")
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
        # Pestaña de información del vídeo (solo lectura). Se añade SIEMPRE al
        # final, para no alterar los índices de Chat/Comentarios, y se puede
        # ocultar por preferencia. La rellena set_metadatos con lo de yt-dlp.
        self._pag_info = self._build_pagina_info(self.nb)
        self._metadatos = {}
        if bool(self._config.get("mostrar_metadatos", True)):
            self.nb.AddPage(self._pag_info, "Información")
        else:
            self._pag_info.Hide()
        # Piso para que la lista del chat no quede aplastada por el reproductor
        # en ventanas bajas.
        self.nb.SetMinSize((-1, 170))
        zvs.Add(self.nb, 3, wx.EXPAND | wx.BOTTOM, 10)

        # Proporción 3/2 (antes el reproductor iba fijo en 0): chat y reproductor
        # comparten el alto sobrante con algo más de peso para el chat —que tiene
        # menos mínimo— para que queden equilibrados; el vídeo crece al agrandar la
        # ventana en vez de quedar fijo y comerse el espacio del chat.
        self._rep_panel = ReproductorPanel(self._zona, self._config)
        # Al alternar los botones del reproductor (desde su interruptor o el menú),
        # sincronizamos la casilla del menú y persistimos la preferencia.
        self._rep_panel.on_botones_toggle = self._on_botones_rep_cambio
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
        nombre_accesible(self.lb_chat, "Chat en vivo")
        vs.Add(self.lb_chat, 1, wx.EXPAND | wx.ALL, 8)

        pag.SetSizer(vs)
        return pag

    def _build_pagina_info(self, parent) -> wx.Panel:
        pag = wx.Panel(parent, name="PaginaInfo")
        pag.SetBackgroundColour(_T.bg)
        pag.SetForegroundColour(_T.text)
        vs = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(pag, label="Información del vídeo:", name="EtiquetaInfo")
        _titulo(lbl)
        vs.Add(lbl, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        # Solo lectura y multilínea. TE_AUTO_URL (con TE_RICH2, necesario en
        # Windows) hace clicables los enlaces de la descripción SIN romper la
        # lectura con NVDA, que recorre el cuadro como texto normal (flechas,
        # selección, copiar). Es la opción accesible frente a un wx.html.
        self.txt_info = wx.TextCtrl(
            pag, value="", name="Información del vídeo",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_AUTO_URL | wx.TE_RICH2)
        _tc(self.txt_info)
        self.txt_info.SetToolTip(
            "Datos del vídeo: canal, vistas, descripción. Solo lectura. Los "
            "enlaces se abren con clic o se copian y pegan en el navegador.")
        vs.Add(self.txt_info, 1, wx.EXPAND | wx.ALL, 8)

        pag.SetSizer(vs)
        self.txt_info.Bind(wx.EVT_TEXT_URL, self._on_info_url)
        return pag

    def _on_info_url(self, event):
        # TE_AUTO_URL dispara este evento para CADA movimiento del ratón sobre el
        # enlace; abrir solo al soltar el botón izquierdo (si no, abriría a cada
        # paso del cursor).
        mouse = event.GetMouseEvent()
        if mouse.LeftUp():
            url = self.txt_info.GetRange(event.GetURLStart(), event.GetURLEnd())
            if url:
                webbrowser.open(url)
        else:
            event.Skip()

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
        elif pag is self._pag_info:
            self.txt_info.SetFocus()
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

    def _toggle_botones_rep(self):
        """Desde el menú: alterna los botones del reproductor. El panel avisa de
        vuelta (on_botones_toggle → _on_botones_rep_cambio) para sincronizar."""
        try:    self._rep_panel.alternar_botones()
        except Exception as exc:
            logger.debug("alternar botones reproductor: %s", exc)

    def _on_botones_rep_cambio(self, visibles: bool):
        """El panel cambió la visibilidad de los botones (por su interruptor o por
        el menú): sincronizar la casilla del menú y guardar la preferencia."""
        try:    self.mi_rep_botones.Check(bool(visibles))
        except Exception: pass
        self._config["mostrar_botones_reproductor"] = bool(visibles)
        guardar_opcion(RUTA_CONFIG, "ui", "mostrar_botones_reproductor",
                       "true" if visibles else "false")

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
            # Solo los radio items: si no había voces, el submenú tiene un item
            # deshabilitado «(no disponible)» que no debe repoblarse como voz.
            voces_actuales = [it.GetItemLabelText()
                              for it in self.voz_submenu.GetMenuItems()
                              if it.GetKind() == wx.ITEM_RADIO]
        except Exception:
            voces_actuales = []
        self._build_menubar()
        # Restaurar submenú de voz y filtro tras reconstruir (con lista vacía,
        # poblar_voces repone el item «(no disponible)»).
        self.poblar_voces(voces_actuales, self._voz_idx)
        if voces_actuales:
            # Preferencias puede haber cambiado la voz: aplicarla en caliente.
            try:
                idx_cfg = _resolver_idx_voz(self._config.get("voz", "0"), voces_actuales)
                if idx_cfg != self._voz_idx:
                    self._aplicar_voz(idx_cfg)
            except Exception as exc:
                logger.debug("aplicar voz desde preferencias: %s", exc)
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
        # Panel de información del vídeo: mostrar u ocultar la pestaña.
        try:
            self.set_metadatos_visible(bool(self._config.get("mostrar_metadatos", True)))
        except Exception:
            pass
        # Botones del reproductor: aplicar la preferencia al panel (que a su vez
        # sincroniza la casilla del menú vía on_botones_toggle).
        try:
            self._rep_panel.set_botones_visibles(
                bool(self._config.get("mostrar_botones_reproductor", False)))
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
        # Marcar el radio del submenú: al clicar lo hace wx solo, pero si
        # llegamos aquí desde Preferencias hay que marcarlo a mano.
        try:    self.voz_submenu.FindItemByPosition(idx).Check(True)
        except Exception: pass
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
        # El worker actualiza su contador al instante (aplica a SAPI en su hilo),
        # así que get_rate() ya devuelve el valor nuevo sin predecirlo aquí.
        self._worker.cambiar_rate(delta)
        r = self._worker.get_rate()
        wpm = max(50, min(500, r * 20 + 180))
        guardar_opcion(RUTA_CONFIG, "voz", "velocidad", str(wpm))
        anunciar(f"Velocidad de la voz: {r:+d}")

    def _ajustar_volume(self, delta):
        self._worker.cambiar_volumen(delta)
        v = self._worker.get_volume()
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

    def _snapshot_sesion(self) -> estado_sesion.SnapshotSesion:
        """Reúne el estado actual para F2. Los datos del vídeo salen de los
        metadatos capturados al conectar (título, canal, espectadores)."""
        # Tipo: hay que distinguir TikTok de YouTube (ambos son LIVE por dentro).
        if self._conectado and self._es_tiktok:
            tipo = "live_tiktok"
        elif self._tipo_video == deteccion.LIVE:
            tipo = "live_youtube"
        elif self._tipo_video == deteccion.VOD:
            tipo = "vod"
        elif self._tipo_video == deteccion.UPCOMING:
            tipo = "upcoming"
        else:
            tipo = ""
        meta = self._metadatos or {}
        espectadores = meta.get("vistas")
        try:    espectadores = int(espectadores) if espectadores is not None else None
        except (TypeError, ValueError): espectadores = None
        def _seguro(fn, defecto):
            try:    return fn()
            except Exception: return defecto
        return estado_sesion.SnapshotSesion(
            conectado=self._conectado,
            tipo=tipo,
            titulo=self._titulo_stream,
            canal=(meta.get("canal") or "").strip(),
            espectadores=espectadores,
            mensajes_leidos=_seguro(lambda: self._stats.leidos, 0),
            aportes=_seguro(lambda: self._stats.superchats, 0),
            total_aportes=self._total_aportes_texto(),
            en_cola=_seguro(lambda: self._cola.qsize(), 0),
            voz_velocidad=_seguro(lambda: self._worker.get_rate(), 0),
            voz_volumen=_seguro(lambda: self._worker.get_volume(), 0),
            lectura_silenciada=bool(self._config.get("silenciar_lectura", False)),
        )

    def _total_aportes_texto(self) -> str:
        """Solo el importe acumulado de Super Chats (sin el «SC: n»), para F2."""
        if not self._sc_totales:
            return ""
        if len(self._sc_totales) == 1:
            d, t = next(iter(self._sc_totales.items()))
            return f"{d}{t:.2f}"
        return ", ".join(f"{d}{t:.0f}" for d, t in self._sc_totales.items())

    def _anunciar_estado(self):
        toggles = self._config.get("estado_toggles") or estado_sesion.ACTIVOS_DEFECTO
        texto = estado_sesion.formatear_estado(self._snapshot_sesion(), toggles)
        anunciar(texto or "Sin información de estado.")

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
            menu.Bind(wx.EVT_MENU, lambda e: self._moderar(autor, canal_autor, 300), id=id_timeout)
            menu.Bind(wx.EVT_MENU, lambda e: self._moderar(autor, canal_autor, None), id=id_ban)

        # Los handlers van sobre el propio menú (no sobre la ventana): así mueren
        # con él y no se acumulan bindings en cada apertura del menú contextual.
        menu.Bind(wx.EVT_MENU, lambda e: self._copiar_mensaje(), id=id_copiar)
        menu.Bind(wx.EVT_MENU, lambda e: self._copiar_todo(),    id=id_copiar2)
        menu.Bind(wx.EVT_MENU, lambda e: self._releer_mensaje(), id=id_releer)
        menu.Bind(wx.EVT_MENU, lambda e: self._abrir_enlace(),   id=id_link)
        menu.Bind(wx.EVT_MENU, lambda e: self._silenciar_autor(autor, ocultar=False), id=id_sil_tts)
        menu.Bind(wx.EVT_MENU, lambda e: self._silenciar_autor(autor, ocultar=True),  id=id_sil_full)
        menu.Bind(wx.EVT_MENU, lambda e: self._rehabilitar_autor(autor),              id=id_rehab)

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
        if idx == wx.NOT_FOUND:
            return None
        return self._chat.dato_en_fila(idx)

    def _clipboard_set(self, text: str) -> None:
        copiar_al_portapapeles(text)

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
        # Si ya no estamos conectados, descartar: puede ser un mensaje rezagado
        # de un hilo de captura anterior (bloqueado en una lectura de red) que
        # llega tras desconectar. Si no, se solaparía con el directo siguiente.
        # La captura solo emite mensajes tras «conectado», así que en uso normal
        # esto no descarta nada legítimo.
        if not self._conectado:
            return
        if canal_id:
            self._canal_por_autor[autor.lower().strip()] = canal_id
        if self._autor_esta_oculto(autor):
            return

        # El modelo (lista_chat) recorta el historial y nos dice cuántas filas
        # viejas borrar por arriba, manteniendo fila ↔ mensaje siempre alineados
        # (antes se descontaba dos veces y, pasados 500 mensajes, copiar o
        # banear caían sobre el mensaje equivocado).
        visible = self._filtro is None or tipo == self._filtro
        borrar = self._chat.agregar((autor, mensaje, hora, tipo, monto), visible)
        for _ in range(borrar):
            self.lb_chat.Delete(0)

        if tipo in (TIPO_SUPERCHAT, TIPO_STICKER):
            _snd.reproducir("superchat")
            self._sumar_superchat(monto)
        elif tipo == TIPO_MIEMBRO:
            _snd.reproducir("nuevo_miembro")
        else:
            _snd.reproducir("mensaje_nuevo")

        if visible:
            self.lb_chat.Append(self._format_display(autor, mensaje, hora, tipo, monto))
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
            self._reiniciar_datos_sesion()
            # Solo si veníamos de una conexión real: ocultar, sonar y avisar.
            # (Un fallo de conexión nunca llegó a "conectado", así que no suena.)
            if estaba:
                self._mostrar_zona(False)
                self.set_titulo_stream("")
                self.lbl_tipo.SetLabel(MENSAJE_INICIAL)
                _snd.reproducir("desconectado")
                anunciar("Desconectado")
                # Sacar el foco del panel del reproductor ANTES de que quede
                # oculto: si el foco sigue dentro, wx tarda en repintar y el
                # panel «se queda» visible hasta que tabulas. Al campo URL.
                wx.CallAfter(self.txt_url.SetFocus)
        self._set_conectado_ui(conectado)
        self._actualizar_estado_online()

    def _reiniciar_datos_sesion(self) -> None:
        """Borra TODO el estado de la sesión para que volver a conectar sea como
        recién abierta la app y nada del directo anterior se solape: chat,
        comentarios, reproductor, cola de lectura, super chats y contadores. NO
        toca las preferencias del usuario (filtro, voz, sonidos, tema)."""
        self._live_chat_id = ""
        self._canal_por_autor.clear()
        self._tipo_video = deteccion.DESCONOCIDO
        self._es_tiktok = False
        # Chat: datos y lista visible.
        self._chat.limpiar()
        try:    self.lb_chat.Clear()
        except Exception: pass
        # Super Chats acumulados de la sesión.
        self._sc_totales.clear()
        # Panel de información del vídeo.
        self._metadatos = {}
        try:    self.txt_info.SetValue("")
        except Exception: pass
        # Reproductor y panel de comentarios.
        try:    self._rep_panel.detener_todo()
        except Exception: pass
        try:    self._com_panel.limpiar()
        except Exception: pass
        # Cola de lectura y lo que se esté leyendo ahora mismo.
        try:
            self._worker.vaciar_cola()
            self._worker.detener_actual()
        except Exception: pass
        # Contadores a cero.
        try:    self._stats.reset()
        except Exception: pass
        self._actualizar_sb()

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

    def set_espectadores(self, n: int) -> None:
        """Actualiza el conteo de espectadores en vivo (TikTok lo refresca cada
        pocos segundos). Así F2 dice cuántos hay AHORA, no solo al conectar."""
        if not self._alive:
            return
        try:    self._metadatos["vistas"] = int(n)
        except Exception: pass

    def set_tipo_video(self, tipo: str, video_id: str) -> None:
        if not self._alive:
            return
        self._tipo_video = tipo
        self._es_tiktok = False   # esta ruta es la de YouTube
        # Empezar el chat en limpio en cada conexión: el reset al desconectar ya
        # lo hace, pero así garantizamos que nunca quede nada del vídeo anterior.
        self._chat.limpiar()
        self._sc_totales.clear()
        try:    self.lb_chat.Clear()
        except Exception: pass
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

    def configurar_tiktok(self, usuario: str, url_flujo: str) -> None:
        """Prepara la ventana para un directo de TikTok: chat en limpio, pestaña
        de chat al frente, comentarios fuera (TikTok no los tiene aquí) y el
        reproductor con la URL HLS directa. Lo llama main vía wx.CallAfter."""
        if not self._alive:
            return
        self._tipo_video = deteccion.LIVE
        self._es_tiktok = True
        self._chat.limpiar()
        self._sc_totales.clear()
        try:    self.lb_chat.Clear()
        except Exception: pass
        try:    self._com_panel.mostrar_no_disponible(
                    "Los comentarios no están disponibles en los directos de TikTok.")
        except Exception: pass
        autoplay = bool(self._config.get("autoplay_reproductor", True))
        try:    self._rep_panel.set_flujo(url_flujo, autoplay=autoplay)
        except Exception as exc: logger.debug("reproductor tiktok: %s", exc)
        self.lbl_tipo.SetLabel(f"Directo de TikTok de @{usuario}: leyendo el chat.")
        self.nb.SetSelection(PAG_CHAT)

    def set_url(self, url: str) -> None:
        self.txt_url.SetValue(url)

    def set_metadatos(self, meta: dict) -> None:
        """Rellena el panel de información con lo que trae yt-dlp. Se llama desde
        el hilo de conexión vía wx.CallAfter; el panel puede estar oculto por
        preferencia (igual guardamos el texto, para que aparezca ya hecho si lo
        muestran)."""
        if not self._alive:
            return
        self._metadatos = meta or {}
        try:
            self.txt_info.SetValue(metadatos.formatear(self._metadatos))
            self.txt_info.SetInsertionPoint(0)   # que el lector empiece arriba
        except Exception as exc:
            logger.debug("set_metadatos: %s", exc)

    def _idx_pag_info(self) -> int:
        for i in range(self.nb.GetPageCount()):
            if self.nb.GetPage(i) is self._pag_info:
                return i
        return -1

    def set_metadatos_visible(self, visible: bool) -> None:
        """Añade o quita la pestaña de Información según la preferencia. Al
        ocultarla NO se destruye el panel, así reaparece con su contenido."""
        idx = self._idx_pag_info()
        if visible and idx == -1:
            self.nb.AddPage(self._pag_info, "Información")
            self._pag_info.Show()
        elif not visible and idx != -1:
            self.nb.RemovePage(idx)
            self._pag_info.Hide()
        self._zona.Layout()

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
        visibles = self._chat.reconstruir(
            lambda it: not self._autor_esta_oculto(it[0])
            and (self._filtro is None or it[3] == self._filtro))
        for autor, msg, hora, tipo, monto in visibles:
            self.lb_chat.Append(self._format_display(autor, msg, hora, tipo, monto))

    def _set_conectado_ui(self, conectado: bool) -> None:
        # Botón (toggle), items de menú Conectar/Desconectar y campo URL. El
        # resto (ocultar zona, sonido, título) lo gestiona set_conectado.
        self.btn_conectar.SetLabel("&Desconectar" if conectado else "&Conectar")
        self.btn_conectar.Enable()
        self.mi_conectar.Enable(not conectado)
        self.mi_desconectar.Enable(conectado)
        self.txt_url.Enable(not conectado)
        self._actualizar_menus_por_conexion()

    def _actualizar_menus_por_conexion(self) -> None:
        """Deshabilita en la barra de menú lo que solo aplica con una conexión
        activa: navegar por paneles, el filtro, todo el menú Reproductor y las
        acciones de voz sobre una lectura en curso. Así el usuario no llega por
        el menú a paneles que no existen aún. Los ajustes de voz y «Ir a URL» /
        «Anunciar estado» quedan siempre disponibles."""
        con = bool(self._conectado)
        mb = self.GetMenuBar()
        if mb is not None:
            try:    mb.EnableTop(POS_MENU_REPRODUCTOR, con)
            except Exception: pass
        for it in getattr(self, "_mi_ver_conexion", []):
            try:    it.Enable(con)
            except Exception: pass
        try:    self._mi_filtro_sub.Enable(con)
        except Exception: pass
        for it in getattr(self, "_mi_voz_conexion", []):
            try:    it.Enable(con)
            except Exception: pass

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


# ── Portapapeles ─────────────────────────────────────────────────────────────
# Compartido con el panel de comentarios: primero wx y, si falla (p. ej. otro
# proceso tiene el portapapeles abierto), la vía Win32 directa como respaldo.

def copiar_al_portapapeles(text: str) -> None:
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
