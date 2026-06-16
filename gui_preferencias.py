"""Diálogo de Preferencias con pestañas (accesible).

Reúne en un solo sitio lo que antes solo se editaba a mano en config.ini y
sounds.ini: interfaz (fuente, tema de sonido), lectura, filtros de palabras y
usuarios, y un editor de atajos. Persiste con `config.guardar_opcion` (que
conserva comentarios y orden del INI) y actualiza el dict de config en memoria.
La configuración de API/OAuth sigue en su propio diálogo (Herramientas).
"""

from __future__ import annotations

import logging

import wx

import config as cfg
import sound_player as _snd
from gui import anunciar, _T, _tc

logger = logging.getLogger(__name__)

_FORMATOS = [
    ("Nombre y mensaje", "nombre_mensaje"),
    ("Solo el mensaje",  "solo_mensaje"),
    ("Solo el nombre",   "solo_nombre"),
]


class PreferenciasDialog(wx.Dialog):

    def __init__(self, parent, config: dict):
        super().__init__(parent, title="Preferencias", size=(620, 560),
                         name="DialogoPreferencias")
        self._config = config
        self._ruta = cfg.app_dir() / "config.ini"
        self._cambios = False
        self.SetBackgroundColour(_T.bg)
        self._build_ui()
        self.Centre()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        panel = wx.Panel(self, name="PanelPreferencias")
        panel.SetBackgroundColour(_T.bg)
        panel.SetForegroundColour(_T.text)
        vs = wx.BoxSizer(wx.VERTICAL)

        self.nb = wx.Notebook(panel, name="PestanasPreferencias")
        _tc(self.nb, bg=_T.surface)
        self.nb.AddPage(self._pag_interfaz(self.nb), "Interfaz")
        self.nb.AddPage(self._pag_lectura(self.nb), "Lectura")
        self.nb.AddPage(self._pag_filtros(self.nb), "Filtros")
        self.nb.AddPage(self._pag_atajos(self.nb), "Atajos")
        vs.Add(self.nb, 1, wx.EXPAND | wx.ALL, 10)

        row = wx.BoxSizer(wx.HORIZONTAL)
        btn_guardar = wx.Button(panel, wx.ID_OK, "&Guardar", name="GuardarPreferencias")
        btn_cancelar = wx.Button(panel, wx.ID_CANCEL, "&Cancelar", name="CancelarPreferencias")
        for b in (btn_guardar, btn_cancelar):
            b.SetBackgroundColour(_T.btn)
            b.SetForegroundColour(_T.btn_t)
            row.Add(b, 0, wx.RIGHT, 6)
        vs.Add(row, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vs)
        btn_guardar.Bind(wx.EVT_BUTTON, self._on_guardar)

    def _make_panel(self, parent, name):
        p = wx.Panel(parent, name=name)
        p.SetBackgroundColour(_T.bg)
        p.SetForegroundColour(_T.text)
        return p

    def _pag_interfaz(self, parent):
        p = self._make_panel(parent, "PagInterfaz")
        vs = wx.BoxSizer(wx.VERTICAL)

        vs.Add(self._fila_label(p, "Tamaño de &fuente del chat (8 a 24):"),
               0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.sp_fuente = wx.SpinCtrl(p, min=8, max=24,
                                     initial=int(self._config.get("tamanio_fuente_chat", 12)),
                                     name="Tamaño de fuente del chat")
        _tc(self.sp_fuente)
        vs.Add(self.sp_fuente, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        vs.Add(self._fila_label(p, "&Tema de sonido:"), 0, wx.LEFT | wx.RIGHT, 10)
        temas = cfg.listar_temas_sonido()
        self.cho_tema = wx.Choice(p, choices=temas, name="Tema de sonido")
        _tc(self.cho_tema)
        actual = cfg.tema_sonido_actual()
        self.cho_tema.SetSelection(temas.index(actual) if actual in temas else 0)
        vs.Add(self.cho_tema, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.chk_total_sc = wx.CheckBox(p, label="Mostrar el total de &Super Chats en la barra de estado",
                                        name="MostrarTotalSuperChats")
        self.chk_total_sc.SetForegroundColour(_T.text)
        self.chk_total_sc.SetValue(bool(self._config.get("mostrar_total_superchats", True)))
        vs.Add(self.chk_total_sc, 0, wx.ALL, 10)

        p.SetSizer(vs)
        return p

    def _pag_lectura(self, parent):
        p = self._make_panel(parent, "PagLectura")
        vs = wx.BoxSizer(wx.VERTICAL)

        vs.Add(self._fila_label(p, "Qué leer de cada mensaje:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.rb_formato = wx.RadioBox(
            p, choices=[f[0] for f in _FORMATOS], majorDimension=1,
            style=wx.RA_SPECIFY_COLS, name="Formato de lectura")
        self.rb_formato.SetForegroundColour(_T.text)
        self.rb_formato.SetBackgroundColour(_T.bg)
        fa = self._config.get("formato_prefijo", "nombre_mensaje")
        for i, (_, v) in enumerate(_FORMATOS):
            if v == fa:
                self.rb_formato.SetSelection(i)
                break
        vs.Add(self.rb_formato, 0, wx.ALL, 10)

        self.chk_emojis = wx.CheckBox(p, label="&Quitar emojis al leer", name="LimpiarEmojis")
        self.chk_urls   = wx.CheckBox(p, label="Quitar &URLs al leer", name="EliminarURLs")
        for c in (self.chk_emojis, self.chk_urls):
            c.SetForegroundColour(_T.text)
        self.chk_emojis.SetValue(bool(self._config.get("limpiar_emojis", True)))
        self.chk_urls.SetValue(bool(self._config.get("eliminar_urls", True)))
        vs.Add(self.chk_emojis, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        vs.Add(self.chk_urls, 0, wx.ALL, 10)

        vs.Add(self._fila_label(p, "&Longitud máxima del mensaje (caracteres):"),
               0, wx.LEFT | wx.RIGHT, 10)
        self.sp_long = wx.SpinCtrl(p, min=20, max=1000,
                                   initial=int(self._config.get("max_longitud_mensaje", 200)),
                                   name="Longitud máxima del mensaje")
        _tc(self.sp_long)
        vs.Add(self.sp_long, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        p.SetSizer(vs)
        return p

    def _pag_filtros(self, parent):
        p = self._make_panel(parent, "PagFiltros")
        vs = wx.BoxSizer(wx.VERTICAL)

        vs.Add(self._fila_label(p, "&Palabras silenciadas (separadas por comas):"),
               0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.txt_palabras = wx.TextCtrl(
            p, value=", ".join(self._config.get("palabras_silenciadas", [])),
            name="Palabras silenciadas")
        _tc(self.txt_palabras)
        vs.Add(self.txt_palabras, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        vs.Add(self._fila_label(p, "&Usuarios silenciados (separados por comas):"),
               0, wx.LEFT | wx.RIGHT, 10)
        self.txt_usuarios = wx.TextCtrl(
            p, value=", ".join(self._config.get("usuarios_silenciados", [])),
            name="Usuarios silenciados")
        _tc(self.txt_usuarios)
        vs.Add(self.txt_usuarios, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        nota = wx.StaticText(p, label=(
            "Estos filtros ocultan y no leen los mensajes que contengan esas "
            "palabras o de esos usuarios. Se aplican a partir del próximo mensaje."),
            name="NotaFiltros")
        nota.SetForegroundColour(_T.dim)
        nota.Wrap(560)
        vs.Add(nota, 0, wx.ALL, 10)

        p.SetSizer(vs)
        return p

    def _pag_atajos(self, parent):
        p = self._make_panel(parent, "PagAtajos")
        vs = wx.BoxSizer(wx.VERTICAL)

        nota = wx.StaticText(p, label=(
            "Atajos de control en tiempo real (teclas de función como F5, o "
            "Alt+letra). El resto de acciones están en la barra de menú. "
            "F9 a F12 son fijos. Deja en blanco para desactivar."),
            name="NotaAtajos")
        nota.SetForegroundColour(_T.dim)
        nota.Wrap(560)
        vs.Add(nota, 0, wx.ALL, 10)

        grid = wx.FlexGridSizer(0, 2, 6, 10)
        grid.AddGrowableCol(1, 1)
        self._campos_atajo: dict[str, wx.TextCtrl] = {}
        raw = self._config.get("atajos_raw", {})
        for accion in cfg.ATAJOS_DEFAULTS:
            etiqueta = _ETIQUETAS_ATAJO.get(accion, accion)
            valor = raw.get(accion, cfg.ATAJOS_DEFAULTS[accion])
            lbl = wx.StaticText(p, label=etiqueta + ":")
            lbl.SetForegroundColour(_T.text)
            txt = wx.TextCtrl(p, value=valor, name=etiqueta)
            _tc(txt)
            if accion in cfg.ATAJOS_FIJOS:
                txt.SetValue(valor)
                txt.Disable()
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(txt, 1, wx.EXPAND)
            self._campos_atajo[accion] = txt
        vs.Add(grid, 1, wx.EXPAND | wx.ALL, 10)

        p.SetSizer(vs)
        return p

    def _fila_label(self, p, texto):
        lbl = wx.StaticText(p, label=texto)
        lbl.SetForegroundColour(_T.accent)
        return lbl

    # ── Guardar ───────────────────────────────────────────────────────────────

    def _set(self, seccion, clave, valor):
        cfg.guardar_opcion(self._ruta, seccion, clave, valor)
        self._cambios = True

    def _on_guardar(self, event):
        c = self._config

        # Interfaz
        fuente = str(self.sp_fuente.GetValue())
        self._set("ui", "tamanio_fuente_chat", fuente)
        c["tamanio_fuente_chat"] = int(fuente)

        total_sc = self.chk_total_sc.GetValue()
        self._set("ui", "mostrar_total_superchats", "true" if total_sc else "false")
        c["mostrar_total_superchats"] = total_sc

        tema = self.cho_tema.GetStringSelection()
        if tema and tema != cfg.tema_sonido_actual():
            cfg.guardar_opcion(cfg.app_dir() / "sounds.ini", "sonidos", "tema", tema)
            try:    _snd.cargar(cfg.cargar_sonidos())
            except Exception as exc: logger.warning("recargar sonidos: %s", exc)
            self._cambios = True

        # Lectura
        formato = _FORMATOS[self.rb_formato.GetSelection()][1]
        self._set("lectura", "formato_prefijo", formato)
        c["formato_prefijo"] = formato

        emojis = self.chk_emojis.GetValue()
        self._set("texto", "limpiar_emojis", "true" if emojis else "false")
        c["limpiar_emojis"] = emojis
        urls = self.chk_urls.GetValue()
        self._set("texto", "eliminar_urls", "true" if urls else "false")
        c["eliminar_urls"] = urls
        longitud = str(self.sp_long.GetValue())
        self._set("texto", "max_longitud_mensaje", longitud)
        c["max_longitud_mensaje"] = int(longitud)

        # Filtros
        palabras = self.txt_palabras.GetValue().strip()
        self._set("filtros", "palabras_silenciadas", palabras)
        c["palabras_silenciadas"] = _lista(palabras)
        usuarios = self.txt_usuarios.GetValue().strip()
        self._set("filtros", "usuarios_silenciados", usuarios)
        c["usuarios_silenciados"] = _lista(usuarios)

        # Atajos
        raw = c.setdefault("atajos_raw", {})
        for accion, txt in self._campos_atajo.items():
            if accion in cfg.ATAJOS_FIJOS:
                continue
            valor = txt.GetValue().strip().lower()
            self._set("atajos", accion, valor)
            raw[accion] = valor

        _snd.reproducir("copiar")
        anunciar("Preferencias guardadas")
        self.EndModal(wx.ID_OK)

    def hubo_cambios(self) -> bool:
        return self._cambios


_ETIQUETAS_ATAJO = {
    "anunciar_estado":   "Anunciar estado",
    "silenciar_lectura": "Silenciar lectura TTS",
    "pausa":             "Pausar o reanudar lectura",
    "silenciar_sonidos": "Silenciar sonidos",
    "detener_tts":       "Detener voz actual",
    "velocidad_menos":   "Bajar velocidad (fijo)",
    "velocidad_mas":     "Subir velocidad (fijo)",
    "volumen_menos":     "Bajar volumen (fijo)",
    "volumen_mas":       "Subir volumen (fijo)",
}


def _lista(v: str) -> list:
    return [x.strip().lower() for x in v.split(",") if x.strip()]


def abrir_preferencias(parent, config: dict) -> bool:
    """Devuelve True si se guardaron cambios (para aplicarlos en caliente)."""
    dlg = PreferenciasDialog(parent, config)
    try:
        res = dlg.ShowModal()
        return res == wx.ID_OK and dlg.hubo_cambios()
    finally:
        dlg.Destroy()
