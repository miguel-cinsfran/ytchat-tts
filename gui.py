"""Interfaz wxPython accesible."""

from __future__ import annotations

import logging
import re
import webbrowser
from pathlib import Path

import wx

from config import (
    APP_NAME, APP_VERSION,
    TIPO_TEXTO, TIPO_SUPERCHAT, TIPO_STICKER, TIPO_MIEMBRO,
    FILTROS,
)
from config import parsear_atajos, atajos_a_tuplas_wx, ATAJOS_DEFAULTS, app_dir, guardar_opcion
import sound_player as _snd

# Mapeo entre índice de FILTROS y clave persistida en config.ini.
_NOMBRES_FILTRO = ("todos", "texto", "superchat", "miembro")
_IDX_FILTRO     = {"todos": 0, "texto": 1, "superchat": 2, "miembro": 3}


MAX_ITEMS_CHAT  = 500
TIMER_STATUS_MS = 1000
ANCHO_DEFECTO   = 820
ALTO_DEFECTO    = 560
RUTA_CONFIG = None  # se asigna en iniciar_gui() con app_dir()
_URL_RE         = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)

# Para parsear el amountString de Super Chats ("€15.50", "5,00 €", ...)
_NUM_RE    = re.compile(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+)")
_DIVISA_RE = re.compile(r"[^\d\s,.]+")

logger = logging.getLogger(__name__)


# ── accessible_output2 (opcional) ───────────────────────────────────────────
# Si no está instalado o no hay un lector de pantalla activo, los
# `anunciar()` son no-ops silenciosos; la app funciona igual.
# Solo se activa si hay un lector real (NVDA, JAWS…); se ignora SAPI5
# para no interferir con el TTS propio de la aplicación.

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


# ── Paleta Catppuccin Mocha ──────────────────────────────────────────────────

class _T:
    bg      = wx.Colour(30,  30,  46)
    surface = wx.Colour(49,  50,  68)
    field   = wx.Colour(59,  60,  78)
    border  = wx.Colour(69,  71,  90)
    text    = wx.Colour(205, 214, 244)
    dim     = wx.Colour(166, 173, 200)
    accent  = wx.Colour(137, 180, 250)
    gold    = wx.Colour(249, 226, 175)
    green   = wx.Colour(166, 227, 161)
    red     = wx.Colour(243, 139, 168)
    btn     = wx.Colour(69,  71,  90)
    btn_t   = wx.Colour(205, 214, 244)


def _tc(w, bg=None, fg=None):
    w.SetBackgroundColour(bg or _T.field)
    w.SetForegroundColour(fg or _T.text)


class WxAnnouncingHandler(logging.Handler):
    """Reenvía los mensajes del logger al lector de pantalla.

    Sirve para que el usuario ciego se entere de los avisos sin tener
    que consultar el log.
    """

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

        # Almacenamos los mensajes como tuplas por compatibilidad histórica.
        # _chat_vis son índices en _chat_all que pasan el filtro actual.
        self._chat_all: list = []
        self._chat_vis: list[int] = []
        self._filtro = None

        # Totales acumulados por divisa (el amountString varía: €, $, ...).
        self._sc_totales: dict[str, float] = {}

        self.on_conectar_cb    = None
        self.on_desconectar_cb = None

        self._atajos = parsear_atajos(config.get("atajos_raw", {}))
        self._ids    = {accion: wx.NewIdRef() for accion in ATAJOS_DEFAULTS.keys()}

        self.SetBackgroundColour(_T.bg)
        self._build_ui()
        self._bind_events()
        self._init_timer()
        self.Centre()

    # ── Construcción de la UI ────────────────────────────────────────────────

    def _build_ui(self):
        panel = wx.Panel(self, name="PanelPrincipal")
        panel.SetBackgroundColour(_T.bg)
        panel.SetForegroundColour(_T.text)
        vs = wx.BoxSizer(wx.VERTICAL)

        # ── URL ──
        row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(panel, label="&URL/ID:", name="EtiquetaURL")
        lbl.SetForegroundColour(_T.accent)
        row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        # name= hace que NVDA lea la etiqueta al llegar al control con Tab.
        self.txt_url = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER, name="URL del directo")
        _tc(self.txt_url)
        self.txt_url.SetToolTip(
            "URL del directo de YouTube o ID de 11 caracteres. Pulsa Enter para conectar.")
        row.Add(self.txt_url, 1, wx.EXPAND)
        vs.Add(row, 0, wx.EXPAND | wx.ALL, 10)

        # ── Botones principales ──
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_conectar = wx.Button(panel, label="&Conectar",    name="Conectar")
        self.btn_pausa    = wx.Button(panel, label="&Pausa",       name="Pausar")
        self.btn_vaciar   = wx.Button(panel, label="Vaciar cola",  name="VaciarCola")
        self.btn_detener  = wx.Button(panel, label="&Detener TTS", name="DetenerTTS")
        self.btn_salir    = wx.Button(panel, label="&Salir",       name="Salir")
        self.btn_pausa.Disable()
        self.btn_vaciar.Disable()
        self.btn_detener.Disable()
        for b in (self.btn_conectar, self.btn_pausa, self.btn_vaciar,
                  self.btn_detener, self.btn_salir):
            b.SetBackgroundColour(_T.btn)
            b.SetForegroundColour(_T.btn_t)
            row.Add(b, 0, wx.RIGHT, 6)
        vs.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ── Voz + Filtro ──
        row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(panel, label="&Voz:", name="EtiquetaVoz")
        lbl.SetForegroundColour(_T.dim)
        row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.cho_voz = wx.Choice(panel, choices=[], name="Voz SAPI5")
        _tc(self.cho_voz)
        row.Add(self.cho_voz, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.btn_aplicar_voz = wx.Button(panel, label="Aplicar voz", name="AplicarVoz")
        self.btn_aplicar_voz.SetBackgroundColour(_T.btn)
        self.btn_aplicar_voz.SetForegroundColour(_T.btn_t)
        row.Add(self.btn_aplicar_voz, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        lbl = wx.StaticText(panel, label="&Filtro:", name="EtiquetaFiltro")
        lbl.SetForegroundColour(_T.dim)
        row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.cho_filtro = wx.Choice(panel, choices=[f[0] for f in FILTROS], name="Filtro de mensajes")
        _tc(self.cho_filtro)
        self.cho_filtro.SetSelection(0)
        row.Add(self.cho_filtro, 0, wx.ALIGN_CENTER_VERTICAL)
        vs.Add(row, 0, wx.EXPAND | wx.ALL, 10)

        # ── Lista de chat ──
        lbl = wx.StaticText(panel, label="Chat:", name="EtiquetaChat")
        lbl.SetForegroundColour(_T.accent)
        vs.Add(lbl, 0, wx.LEFT | wx.RIGHT, 10)

        self.lb_chat = wx.ListBox(
            panel, style=wx.LB_SINGLE | wx.LB_HSCROLL, name="Chat en vivo")
        _tc(self.lb_chat)
        pt = int(self._config.get("tamanio_fuente_chat", 12))
        self.lb_chat.SetFont(wx.Font(
            pt, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.lb_chat.SetToolTip(
            "Mensajes del chat. Enter copia el mensaje. "
            "Tecla aplicaciones abre el menú contextual.")
        vs.Add(self.lb_chat, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.SetSizer(vs)

        # 7 campos: estado, velocidad, voz, cola, leídos, volumen, total SC.
        self.sb = self.CreateStatusBar(7, name="BarraEstado")
        self.sb.SetBackgroundColour(_T.surface)
        self.sb.SetForegroundColour(_T.dim)
        self.sb.SetStatusWidths([-3, -1, -3, -1, -1, -1, -2])
        self._actualizar_sb()

    # ── Enlaces de eventos ───────────────────────────────────────────────────

    def _bind_events(self):
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.btn_conectar.Bind(wx.EVT_BUTTON,    self._on_conectar)
        self.btn_pausa.Bind(wx.EVT_BUTTON,       self._on_pausa)
        self.btn_vaciar.Bind(wx.EVT_BUTTON,      self._on_vaciar)
        self.btn_detener.Bind(wx.EVT_BUTTON,     self._on_detener_tts)
        self.btn_salir.Bind(wx.EVT_BUTTON,       lambda e: self.Close())
        self.txt_url.Bind(wx.EVT_TEXT_ENTER,     self._on_conectar)
        self.btn_aplicar_voz.Bind(wx.EVT_BUTTON, self._on_aplicar_voz)
        self.cho_filtro.Bind(wx.EVT_CHOICE,      self._on_filtro)
        self.lb_chat.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._copiar_mensaje())
        self.lb_chat.Bind(wx.EVT_KEY_DOWN,       self._on_chat_key)
        self.lb_chat.Bind(wx.EVT_CONTEXT_MENU,   self._on_chat_menu)

        handlers = {
            "url":               lambda e: self.txt_url.SetFocus(),
            "conectar":          lambda e: self._on_conectar(None),
            "pausa":             lambda e: self._on_pausa(None),
            "chat":              lambda e: self.lb_chat.SetFocus(),
            "voz":               lambda e: self.cho_voz.SetFocus(),
            "filtro":            lambda e: self.cho_filtro.SetFocus(),
            "salir":             lambda e: self.Close(),
            "velocidad_mas":     lambda e: self._ajustar_rate(+1),
            "velocidad_menos":   lambda e: self._ajustar_rate(-1),
            "detener_tts":       lambda e: self._on_detener_tts(None),
            "silenciar_sonidos": lambda e: self._toggle_silenciar_sonidos(),
            "vaciar_cola":       lambda e: self._on_vaciar(None),
            "volumen_mas":       lambda e: self._ajustar_volume(+5),
            "volumen_menos":     lambda e: self._ajustar_volume(-5),
            "silenciar_lectura": lambda e: self._toggle_silenciar_lectura(),
            "aplicar_voz":       lambda e: self._on_aplicar_voz(None),
            "copiar_mensaje":    lambda e: self._copiar_atajo(),
            "copiar_todo":       lambda e: self._copiar_todo_atajo(),
            "releer":            lambda e: self._releer_atajo(),
            "abrir_enlace":      lambda e: self._abrir_enlace_atajo(),
        }
        for accion, h in handlers.items():
            wid = self._ids.get(accion)
            if wid is not None:
                self.Bind(wx.EVT_MENU, h, id=wid)

        self.SetAcceleratorTable(wx.AcceleratorTable(
            atajos_a_tuplas_wx(self._atajos, self._ids)))

    def _init_timer(self):
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer)
        self._timer.Start(TIMER_STATUS_MS)

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _on_conectar(self, event):
        if self._conectado:
            if self.on_desconectar_cb:
                self.on_desconectar_cb()
            self._set_botones(False)
            # El sonido y el anuncio detallado vienen del hilo de captura
            # vía on_estado; aquí solo damos retroalimentación inmediata.
            anunciar("Desconectando")
        else:
            url = self.txt_url.GetValue().strip()
            if not url:
                wx.MessageBox("Introduce una URL o ID de YouTube.",
                              "Falta URL", wx.OK | wx.ICON_WARNING, self)
                self.txt_url.SetFocus()
                return
            self.btn_conectar.SetLabel("Conectando...")
            self.btn_conectar.Disable()
            self.txt_url.Disable()
            _snd.reproducir("conectando")
            anunciar("Conectando")
            if self.on_conectar_cb:
                self.on_conectar_cb(url)

    def _on_pausa(self, event):
        self._worker.toggle_pausa()
        pausado = self._worker.esta_pausado()
        self.btn_pausa.SetLabel("Reanudar" if pausado else "Pausa")
        _snd.reproducir("pausa" if pausado else "reanudar")
        anunciar("Pausado" if pausado else "Reanudado")

    def _on_vaciar(self, event):
        self._worker.vaciar_cola()
        anunciar("Cola vaciada")

    def _on_detener_tts(self, event):
        self._worker.detener_actual()
        anunciar("TTS detenido")

    def _on_aplicar_voz(self, event):
        idx = self.cho_voz.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        self._worker.cambiar_voz(idx)
        self._config["voz"] = str(idx)
        guardar_opcion(RUTA_CONFIG, "voz", "voz", str(idx))
        _snd.reproducir("voz_cambiada")
        anunciar(f"Voz: {self.cho_voz.GetString(idx)}")

    def _on_filtro(self, event):
        sel = self.cho_filtro.GetSelection()
        self._filtro = FILTROS[sel][1] if sel < len(FILTROS) else None
        self._rebuild_listbox()
        guardar_opcion(RUTA_CONFIG, "ui", "filtro_activo",
                       _NOMBRES_FILTRO[sel] if sel < len(_NOMBRES_FILTRO) else "todos")
        anunciar(f"Filtro: {FILTROS[sel][0]}. {self.lb_chat.GetCount()} mensajes")

    def _ajustar_rate(self, delta):
        self._worker.cambiar_rate(delta)
        r = max(-10, min(10, self._worker.get_rate() + delta))
        wpm = max(50, min(500, r * 20 + 180))
        guardar_opcion(RUTA_CONFIG, "voz", "velocidad", str(wpm))
        anunciar(f"Velocidad: {r:+d}")

    def _ajustar_volume(self, delta):
        self._worker.cambiar_volumen(delta)
        v = max(0, min(100, self._worker.get_volume() + delta))
        guardar_opcion(RUTA_CONFIG, "voz", "volumen", f"{v / 100:.2f}")
        anunciar(f"Volumen: {v}%")

    def _toggle_silenciar_sonidos(self):
        nuevo = not _snd.esta_silenciado()
        _snd.silenciar_todo(nuevo)
        self._config["silenciar_sonidos"] = nuevo
        guardar_opcion(RUTA_CONFIG, "ui", "silenciar_sonidos", "true" if nuevo else "false")
        anunciar("Sonidos silenciados" if nuevo else "Sonidos activados")

    def _toggle_silenciar_lectura(self):
        nuevo = not self._config.get("silenciar_lectura", False)
        self._config["silenciar_lectura"] = nuevo
        guardar_opcion(RUTA_CONFIG, "sesion", "silenciar_lectura", "true" if nuevo else "false")
        anunciar("Lectura TTS silenciada" if nuevo else "Lectura TTS activada")

    def _copiar_atajo(self):
        if self.lb_chat.GetSelection() == wx.NOT_FOUND:
            anunciar("Sin mensaje seleccionado")
        else:
            self._copiar_mensaje()

    def _copiar_todo_atajo(self):
        if self.lb_chat.GetSelection() == wx.NOT_FOUND:
            anunciar("Sin mensaje seleccionado")
        else:
            self._copiar_todo()

    def _releer_atajo(self):
        if self.lb_chat.GetSelection() == wx.NOT_FOUND:
            anunciar("Sin mensaje seleccionado")
        else:
            self._releer_mensaje()

    def _abrir_enlace_atajo(self):
        if self.lb_chat.GetSelection() == wx.NOT_FOUND:
            anunciar("Sin mensaje seleccionado")
        else:
            self._abrir_enlace()

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

        self.Bind(wx.EVT_MENU, lambda e: self._copiar_mensaje(), id=id_copiar)
        self.Bind(wx.EVT_MENU, lambda e: self._copiar_todo(),    id=id_copiar2)
        self.Bind(wx.EVT_MENU, lambda e: self._releer_mensaje(), id=id_releer)
        self.Bind(wx.EVT_MENU, lambda e: self._abrir_enlace(),   id=id_link)
        self.Bind(wx.EVT_MENU, lambda e: self._silenciar_autor(autor, ocultar=False), id=id_sil_tts)
        self.Bind(wx.EVT_MENU, lambda e: self._silenciar_autor(autor, ocultar=True),  id=id_sil_full)
        self.Bind(wx.EVT_MENU, lambda e: self._rehabilitar_autor(autor),              id=id_rehab)

        self.PopupMenu(menu)
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
    # Dos conjuntos en el dict config: uno para los que no queremos oír (el
    # TTS los salta) y otro para los que tampoco queremos ver en la lista.
    # El "modo ocultar" implica también el "modo solo TTS".

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
        # El wx.Clipboard a veces falla si otra app lo tiene abierto; el
        # fallback con ctypes usa la API nativa y casi siempre consigue copiar.
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
            self._worker.vaciar_cola()
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
                             tipo: str = TIPO_TEXTO, monto: str = "") -> None:
        if not self._alive:
            return
        if self._autor_esta_oculto(autor):
            return

        # Trim: mantener a raya el uso de memoria en directos muy largos.
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
            # Solo auto-scroll si el usuario no está leyendo la lista: si
            # tiene el foco, puede estar revisando un mensaje anterior.
            if wx.Window.FindFocus() is not self.lb_chat:
                self.lb_chat.SetFirstItem(self.lb_chat.GetCount() - 1)

    def set_conectado(self, conectado: bool) -> None:
        if not self._alive:
            return
        self._set_botones(conectado)

    def set_url(self, url: str) -> None:
        self.txt_url.SetValue(url)

    def set_titulo_stream(self, titulo: str) -> None:
        if not self._alive:
            return
        self._titulo_stream = (titulo or "").strip()
        if self._titulo_stream:
            self.SetTitle(f"{self._titulo_stream} — {APP_NAME} v{APP_VERSION}")
        else:
            self.SetTitle(f"{APP_NAME} v{APP_VERSION}")

    def auto_conectar(self) -> None:
        self._on_conectar(None)

    def poblar_voces(self, voces: list, idx_actual: int = 0) -> None:
        self.cho_voz.Set(voces)
        if voces and 0 <= idx_actual < len(voces):
            self.cho_voz.SetSelection(idx_actual)

    # ── Formato y helpers ────────────────────────────────────────────────────

    def _format_display(self, autor, msg, hora, tipo, monto):
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

    def _set_botones(self, conectado: bool) -> None:
        self._conectado = conectado
        if conectado:
            self.btn_conectar.SetLabel("Desconectar")
            self.btn_conectar.Enable()
            self.btn_pausa.Enable()
            self.btn_vaciar.Enable()
            self.btn_detener.Enable()
            self.txt_url.Disable()
        else:
            self.btn_conectar.SetLabel("Conectar")
            self.btn_conectar.Enable()
            self.btn_pausa.Disable()
            self.btn_vaciar.Disable()
            self.btn_detener.Disable()
            self.btn_pausa.SetLabel("Pausa")
            self.txt_url.Enable()

    def _actualizar_sb(self) -> None:
        sin_tts = " [sin TTS]" if self._config.get("silenciar_lectura", False) else ""
        if self._conectado and self._titulo_stream:
            estado = f"Conectado: {self._titulo_stream[:35]}{sin_tts}"
        elif self._conectado:
            estado = f"Conectado{sin_tts}"
        else:
            estado = f"Desconectado{sin_tts}"
        self.sb.SetStatusText(estado, 0)

        try:    self.sb.SetStatusText(f"Vel: {self._worker.get_rate():+d}", 1)
        except Exception: self.sb.SetStatusText("Vel: --", 1)

        try:
            idx = self.cho_voz.GetSelection()
            if idx != wx.NOT_FOUND:
                nombre = self.cho_voz.GetString(idx)
                if len(nombre) > 28:
                    nombre = nombre[:25] + "..."
                self.sb.SetStatusText(f"Voz: {nombre}", 2)
            else:
                self.sb.SetStatusText("Voz: —", 2)
        except Exception:
            self.sb.SetStatusText("Voz: —", 2)

        try:    self.sb.SetStatusText(f"Cola: {self._cola.qsize()}", 3)
        except Exception: self.sb.SetStatusText("Cola: —", 3)
        try:    self.sb.SetStatusText(f"Leídos: {self._stats.leidos}", 4)
        except Exception: self.sb.SetStatusText("Leídos: —", 4)

        try:    self.sb.SetStatusText(f"Vol: {self._worker.get_volume()}%", 5)
        except Exception: self.sb.SetStatusText("Vol: --", 5)

        if self._config.get("mostrar_total_superchats", True):
            self.sb.SetStatusText(self._formato_total_sc(), 6)
        else:
            self.sb.SetStatusText("", 6)

    # ── Acumulación de Super Chats ───────────────────────────────────────────

    def _sumar_superchat(self, monto: str) -> None:
        # El formato del amountString depende de la locale del viewer:
        # "€15.50", "$10.00", "5,00 €", "1.234,56 €"... Intentamos
        # normalizar antes de convertir a float.
        if not monto:
            return
        m = _NUM_RE.search(monto)
        if not m:
            return
        num = m.group(1)
        if "," in num and "." in num:
            # Formato europeo (1.234,56) vs anglosajón (1,234.56): gana la
            # posición del último separador.
            if num.rfind(",") > num.rfind("."):
                num = num.replace(".", "").replace(",", ".")
            else:
                num = num.replace(",", "")
        elif "," in num:
            num = num.replace(",", ".")
        try:    valor = float(num)
        except ValueError: return
        divisa_m = _DIVISA_RE.search(monto)
        divisa = divisa_m.group(0).strip() if divisa_m else "?"
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
    if voces:
        frame.poblar_voces(voces, _resolver_idx_voz(config.get("voz", "0"), voces))
    else:
        frame.cho_voz.Append("(no disponible)")
        frame.cho_voz.Disable()
        frame.btn_aplicar_voz.Disable()

    # Restaurar filtro de la sesión anterior.
    fa = config.get("filtro_activo", "todos")
    idx_f = _IDX_FILTRO.get(fa, 0)
    if idx_f > 0 and idx_f < len(FILTROS):
        frame.cho_filtro.SetSelection(idx_f)
        frame._filtro = FILTROS[idx_f][1]

    # Restaurar silenciado de sonidos si la sesión anterior lo tenía activo.
    if config.get("silenciar_sonidos", False):
        _snd.silenciar_todo(True)

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
