"""Diálogo «Gestor de descargas» (yt-dlp) — accesible y nativo.

Diálogo modal que deja al usuario pegar URLs de YouTube, elegir formato/bitrate/
carpeta/enumerar, y ver la cola con progreso y botón «Cancelar» por ítem. El
motor puro está en `descargas.py` (sin wx, testeable en Linux); este módulo
solo monta la UI y empuja progreso al `wx.ListCtrl` con `wx.CallAfter`.

Accesibilidad (regla de oro NVDA):
  - Cada control interactivo tiene `name=` accesible.
  - Sin color personalizado en casillas ni radios (en Windows rompe su rol).
  - Errores 3-vías: `_snd.reproducir("error")` + `anunciar()` + texto en la
    columna Estado del `ListCtrl`. Nunca se re-lanza una excepción fuera del
    hilo de descarga.
  - Toda mutación de la GUI desde el hilo de descarga va con `wx.CallAfter`.

Apertura: `abrir(parent, url_inicial=None)` desde `gui._abrir_descargas`.
"""
from __future__ import annotations

import logging
import threading

import wx

import config as cfg
from descargas import GestorDescargas
from gui import anunciar, nombre_accesible, _T, _tc
import sound_player as _snd

logger = logging.getLogger(__name__)


# Paleta neutral para el diálogo (no la de la ventana principal): misma lógica
# que `gui_preferencias._T` — apariencia nativa para no romper NVDA en Windows.


# Etiquetas legibles para el Choice de formato. mp3/m4a abren el bitrate.
_FORMATOS_OPCIONES = [
    ("Vídeo MP4 (muxed)", "mp4"),
    ("Vídeo WebM",        "webm"),
    ("Audio MP3",         "mp3"),
    ("Audio M4A",         "m4a"),
]
_BITRATE_OPCIONES = [192, 256, 320]


def _es_formato_audio(formato: str) -> bool:
    return (formato or "").lower() in ("mp3", "m4a")


class GestorDescargasDialog(wx.Dialog):
    """Diálogo principal del gestor de descargas."""

    def __init__(self, parent, url_inicial: str | None = None):
        super().__init__(parent, title="Gestor de descargas",
                         size=(720, 560),
                         name="DialogoGestorDescargas")
        self.SetBackgroundColour(_T.bg)
        self._opciones = cfg.obtener_opciones_descarga()
        self._gestor = GestorDescargas(self._opciones)
        self._items_fila: dict[str, int] = {}   # item_id -> índice en ListCtrl
        self._fila_items: dict[int, str] = {}   # índice -> item_id
        self._build_ui()
        if url_inicial:
            self.txt_url.SetValue(url_inicial)
        self.Centre()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        panel = wx.Panel(self, name="PanelGestorDescargas")
        panel.SetBackgroundColour(_T.bg)
        panel.SetForegroundColour(_T.text)
        vs = wx.BoxSizer(wx.VERTICAL)

        vs.Add(self._seccion_opciones(panel), 0, wx.EXPAND | wx.ALL, 10)
        vs.Add(self._seccion_anadir(panel), 0, wx.EXPAND | wx.ALL, 10)
        vs.Add(self._seccion_cola(panel), 1, wx.EXPAND | wx.ALL, 10)
        vs.Add(self._seccion_botones(panel), 0, wx.EXPAND | wx.ALL, 10)
        panel.SetSizer(vs)

    def _seccion_opciones(self, parent):
        box = wx.StaticBoxSizer(wx.VERTICAL, parent, "Opciones de descarga")
        # Formato (Choice, no RadioBox: menos carga cognitiva y mejor con NVDA).
        fila_fmt = wx.BoxSizer(wx.HORIZONTAL)
        lbl_fmt = wx.StaticText(parent, label="&Formato:", name="EtiquetaFormato")
        lbl_fmt.SetForegroundColour(_T.text)
        fila_fmt.Add(lbl_fmt, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        etiquetas = [et for et, _ in _FORMATOS_OPCIONES]
        valores = [v for _, v in _FORMATOS_OPCIONES]
        self.cho_formato = wx.Choice(parent, choices=etiquetas, name="Formato")
        _tc(self.cho_formato)
        actual = self._opciones.get("formato", "mp4")
        try:    self.cho_formato.SetSelection(valores.index(actual))
        except ValueError: self.cho_formato.SetSelection(0)
        self.cho_formato.Bind(wx.EVT_CHOICE, self._on_formato)
        fila_fmt.Add(self.cho_formato, 1, wx.EXPAND)
        box.Add(fila_fmt, 0, wx.EXPAND | wx.ALL, 6)

        # Bitrate (solo se habilita si formato es audio).
        fila_bit = wx.BoxSizer(wx.HORIZONTAL)
        lbl_bit = wx.StaticText(parent, label="&Bitrate (kbps):", name="EtiquetaBitrate")
        lbl_bit.SetForegroundColour(_T.text)
        fila_bit.Add(lbl_bit, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.cho_bitrate = wx.Choice(parent,
                                     choices=[str(b) for b in _BITRATE_OPCIONES],
                                     name="Bitrate")
        _tc(self.cho_bitrate)
        try:    self.cho_bitrate.SetSelection(
                    _BITRATE_OPCIONES.index(int(self._opciones.get("bitrate", 192))))
        except ValueError: self.cho_bitrate.SetSelection(0)
        fila_bit.Add(self.cho_bitrate, 1, wx.EXPAND)
        box.Add(fila_bit, 0, wx.EXPAND | wx.ALL, 6)

        # Carpeta destino.
        fila_carp = wx.BoxSizer(wx.HORIZONTAL)
        lbl_carp = wx.StaticText(parent, label="Carpeta &destino:", name="EtiquetaCarpeta")
        lbl_carp.SetForegroundColour(_T.text)
        fila_carp.Add(lbl_carp, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.dir_carpeta = wx.DirPickerCtrl(
            parent, path=self._opciones.get("carpeta") or str(cfg.app_dir() / "Descargas"),
            name="Carpeta destino", message="Elige la carpeta de descargas")
        _tc(self.dir_carpeta)
        fila_carp.Add(self.dir_carpeta, 1, wx.EXPAND)
        box.Add(fila_carp, 0, wx.EXPAND | wx.ALL, 6)

        # Enumerar playlist (casilla, sin color).
        self.chk_enumerar = wx.CheckBox(
            parent, name="EnumerarPlaylist",
            label="&Enumerar ítems de playlist (01_, 02_…)")
        self.chk_enumerar.SetForegroundColour(_T.text)
        self.chk_enumerar.SetValue(bool(self._opciones.get("enumerar", False)))
        box.Add(self.chk_enumerar, 0, wx.ALL, 6)

        self._on_formato()   # ajusta habilitación del bitrate
        return box

    def _seccion_anadir(self, parent):
        box = wx.StaticBoxSizer(wx.VERTICAL, parent, "Añadir URL")
        fila = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(parent, label="&URL del vídeo o playlist:",
                            name="EtiquetaURL")
        lbl.SetForegroundColour(_T.text)
        fila.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.txt_url = wx.TextCtrl(parent, value="",
                                   style=wx.TE_PROCESS_ENTER,
                                   name="URL del vídeo o playlist")
        _tc(self.txt_url)
        self.txt_url.SetToolTip("Pega un enlace de YouTube (vídeo o playlist).")
        self.txt_url.Bind(wx.EVT_TEXT_ENTER, lambda e: self._on_anadir(None))
        fila.Add(self.txt_url, 1, wx.EXPAND)
        self.btn_anadir = wx.Button(parent, label="Aña&dir", name="AnadirURL")
        self.btn_anadir.SetBackgroundColour(_T.btn)
        self.btn_anadir.SetForegroundColour(_T.btn_t)
        self.btn_anadir.Bind(wx.EVT_BUTTON, self._on_anadir)
        fila.Add(self.btn_anadir, 0, wx.LEFT, 6)
        box.Add(fila, 0, wx.EXPAND | wx.ALL, 6)
        return box

    def _seccion_cola(self, parent):
        box = wx.StaticBoxSizer(wx.VERTICAL, parent, "Cola de descargas")
        self.lista = wx.ListCtrl(parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL,
                                 name="ColaDescargas")
        nombre_accesible(self.lista, "Cola de descargas", msaa=False)
        self.lista.InsertColumn(0, "Nombre", width=320)
        self.lista.InsertColumn(1, "Progreso", width=100)
        self.lista.InsertColumn(2, "Estado", width=160)
        box.Add(self.lista, 1, wx.EXPAND | wx.ALL, 6)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_cancelar = wx.Button(parent, label="&Cancelar seleccionado",
                                      name="CancelarDescarga")
        self.btn_cancelar.SetBackgroundColour(_T.btn)
        self.btn_cancelar.SetForegroundColour(_T.btn_t)
        self.btn_cancelar.Bind(wx.EVT_BUTTON, self._on_cancelar)
        fila.Add(self.btn_cancelar, 0)
        box.Add(fila, 0, wx.ALL, 6)
        return box

    def _seccion_botones(self, parent):
        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_cerrar = wx.Button(parent, wx.ID_CANCEL, "&Cerrar",
                                    name="CerrarGestorDescargas")
        self.btn_cerrar.SetBackgroundColour(_T.btn)
        self.btn_cerrar.SetForegroundColour(_T.btn_t)
        self.btn_cerrar.Bind(wx.EVT_BUTTON, self._on_cerrar)
        fila.Add(self.btn_cerrar, 0, wx.RIGHT, 6)
        return fila

    # ── Callbacks de UI ──────────────────────────────────────────────────────

    def _on_formato(self, _event=None):
        idx = self.cho_formato.GetSelection()
        if idx < 0 or idx >= len(_FORMATOS_OPCIONES):
            return
        _, valor = _FORMATOS_OPCIONES[idx]
        es_audio = _es_formato_audio(valor)
        self.cho_bitrate.Enable(es_audio)
        # Si pasó de audio a vídeo, no escondemos el valor: el usuario lo
        # verá gris. Si era vídeo y pasa a audio, ya está en 192/256/320.

    def _opciones_actuales(self) -> dict:
        idx = self.cho_formato.GetSelection()
        formato = (_FORMATOS_OPCIONES[idx][1]
                   if 0 <= idx < len(_FORMATOS_OPCIONES) else "mp4")
        try:    bitrate = _BITRATE_OPCIONES[self.cho_bitrate.GetSelection()]
        except Exception: bitrate = 192
        carpeta = self.dir_carpeta.GetPath() or str(cfg.app_dir() / "Descargas")
        enumerar = bool(self.chk_enumerar.GetValue())
        return {"formato": formato, "bitrate": bitrate,
                "carpeta": carpeta, "enumerar": enumerar}

    def _on_anadir(self, _event):
        url = self.txt_url.GetValue().strip()
        if not url:
            wx.MessageBox("Pega una URL de YouTube (vídeo o playlist) antes de añadir.",
                          "Falta la URL", wx.OK | wx.ICON_INFORMATION, self)
            return
        # Persistimos las opciones elegidas antes de encolar (así el Gestor
        # las ve). Si luego el usuario cambia el formato en medio, la nueva
        # descarga usará la nueva config.
        op = self._opciones_actuales()
        try:    cfg.guardar_opciones_descarga(op)
        except Exception as exc: logger.debug("guardar opciones: %s", exc)
        self._opciones = op
        self._gestor.set_opciones(op)

        # Inserción optimista en la cola (estado «en_cola»), luego el hilo
        # actualiza estado/progreso vía CallAfter.
        idx = self.lista.InsertItem(self.lista.GetItemCount(), url[:300])
        self.lista.SetItem(idx, 1, "0 %")
        self.lista.SetItem(idx, 2, "en cola")

        def _cb_progreso(item_id, pct, _vel, _eta, nombre):
            wx.CallAfter(self._actualizar_progreso, item_id, pct, nombre)

        def _cb_estado(item_id, estado, mensaje):
            wx.CallAfter(self._actualizar_estado, item_id, estado, mensaje)

        item_id = self._gestor.encolar(url, _cb_progreso, _cb_estado)
        self._items_fila[item_id] = idx
        self._fila_items[idx] = item_id
        self.txt_url.SetValue("")
        anunciar("Añadido a la cola")

    def _on_cancelar(self, _event):
        idx = self.lista.GetFirstSelected()
        if idx < 0:
            wx.MessageBox("Selecciona una descarga de la cola para cancelar.",
                          "Nada seleccionado", wx.OK | wx.ICON_INFORMATION, self)
            return
        item_id = self._fila_items.get(idx)
        if item_id is None:
            return
        self._gestor.cancelar(item_id)
        # El estado lo confirmará el propio hilo («cancelado»).
        anunciar("Cancelando descarga")

    def _on_cerrar(self, _event):
        self.EndModal(wx.ID_CANCEL)

    # ── Callbacks del hilo de descarga (CallAfter) ──────────────────────────

    def _actualizar_progreso(self, item_id: str, pct: float, nombre: str) -> None:
        idx = self._items_fila.get(item_id)
        if idx is None:
            return
        texto = f"{pct:.0f} %"
        if nombre:
            self.lista.SetItem(idx, 0, nombre[:300])
        self.lista.SetItem(idx, 1, texto)

    def _actualizar_estado(self, item_id: str, estado: str, mensaje: str) -> None:
        idx = self._items_fila.get(item_id)
        if idx is None:
            return
        if mensaje and estado in ("error", "cancelado"):
            texto = f"{estado}: {mensaje[:80]}"
        else:
            texto = estado
        self.lista.SetItem(idx, 2, texto[:200])
        # Anunciar SOLO inicio/fin/error/cancel (no cada %). La transición a
        # «completado/error/cancelado» es la que el lector verbaliza.
        if estado in ("descargando", "completado", "error", "cancelado"):
            try:    _snd.reproducir("error" if estado == "error" else "copiar")
            except Exception: pass
            if estado == "error":
                anunciar(f"Error: {mensaje or 'fallo en la descarga'}")
            elif estado == "completado":
                anunciar("Descarga completada")
            elif estado == "cancelado":
                anunciar("Descarga cancelada")


def abrir(parent, url_inicial: str | None = None) -> bool:
    """Abre el gestor como modal y devuelve True si el usuario lo usó (siempre,
    salvo que falle la apertura). El diálogo persiste las opciones al cerrarse
    vía `cfg.guardar_opciones_descarga` desde los callbacks."""
    dlg = GestorDescargasDialog(parent, url_inicial=url_inicial)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()
    return True
