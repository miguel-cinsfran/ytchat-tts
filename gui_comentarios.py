"""Ventana accesible para leer (y, con sesión, comentar) los comentarios de un vídeo.

Reutiliza la cola del TTS de la aplicación, así que los comentarios se leen con
la misma voz SAPI5. Solo necesita una API key para leer; publicar y responder
requieren haber iniciado sesión en Configuración.
"""

from __future__ import annotations

import logging
import threading

import wx

import credenciales
import youtube_api
import sound_player as _snd
from gui import anunciar, _T, _tc
from main import extraer_video_id

logger = logging.getLogger(__name__)

_ORDENES = [("Más relevantes", "relevance"), ("Más recientes", "time")]


class ComentariosFrame(wx.Frame):

    def __init__(self, parent, cola, config):
        super().__init__(parent, title="Comentarios de vídeo",
                         size=(760, 560), name="VentanaComentarios")
        self._cola = cola
        self._config = config
        self._coms: list[youtube_api.Comentario] = []
        self._video_id = ""
        self._next_token = ""
        self._cargando = False

        self.SetBackgroundColour(_T.bg)
        self._build_ui()
        self.Centre()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        panel = wx.Panel(self, name="PanelComentarios")
        panel.SetBackgroundColour(_T.bg)
        panel.SetForegroundColour(_T.text)
        vs = wx.BoxSizer(wx.VERTICAL)

        # Fila URL + orden + cargar
        row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(panel, label="&URL o ID del vídeo:")
        lbl.SetForegroundColour(_T.accent)
        row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.txt_url = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER,
                                   name="URL o ID del vídeo")
        _tc(self.txt_url)
        row.Add(self.txt_url, 1, wx.EXPAND | wx.RIGHT, 6)
        self.cho_orden = wx.Choice(panel, choices=[o[0] for o in _ORDENES],
                                   name="Orden de comentarios")
        _tc(self.cho_orden)
        self.cho_orden.SetSelection(0)
        row.Add(self.cho_orden, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.btn_cargar = wx.Button(panel, label="&Cargar", name="CargarComentarios")
        self.btn_cargar.SetBackgroundColour(_T.btn)
        self.btn_cargar.SetForegroundColour(_T.btn_t)
        row.Add(self.btn_cargar, 0, wx.ALIGN_CENTER_VERTICAL)
        vs.Add(row, 0, wx.EXPAND | wx.ALL, 10)

        # Lista
        lbl = wx.StaticText(panel, label="Comentarios:")
        lbl.SetForegroundColour(_T.accent)
        vs.Add(lbl, 0, wx.LEFT | wx.RIGHT, 10)
        self.lb = wx.ListBox(panel, style=wx.LB_SINGLE | wx.LB_HSCROLL,
                             name="Lista de comentarios")
        _tc(self.lb)
        pt = int(self._config.get("tamanio_fuente_chat", 12))
        self.lb.SetFont(wx.Font(pt, wx.FONTFAMILY_DEFAULT,
                                wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.lb.SetToolTip("Enter lee el comentario con la voz. "
                           "Tecla aplicaciones abre el menú.")
        vs.Add(self.lb, 1, wx.EXPAND | wx.ALL, 10)

        # Botones de acción
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_leer  = wx.Button(panel, label="&Leer", name="LeerComentario")
        self.btn_copiar = wx.Button(panel, label="Co&piar", name="CopiarComentario")
        self.btn_mas   = wx.Button(panel, label="Cargar &más", name="CargarMas")
        self.btn_responder = wx.Button(panel, label="&Responder", name="ResponderComentario")
        self.btn_comentar  = wx.Button(panel, label="Comen&tar en el vídeo", name="ComentarVideo")
        self.btn_cerrar = wx.Button(panel, label="C&errar", name="CerrarComentarios")
        for b in (self.btn_leer, self.btn_copiar, self.btn_mas,
                  self.btn_responder, self.btn_comentar, self.btn_cerrar):
            b.SetBackgroundColour(_T.btn)
            b.SetForegroundColour(_T.btn_t)
            row.Add(b, 0, wx.RIGHT, 6)
        self.btn_mas.Disable()
        vs.Add(row, 0, wx.ALL, 10)

        panel.SetSizer(vs)

        self.txt_url.Bind(wx.EVT_TEXT_ENTER, self._on_cargar)
        self.btn_cargar.Bind(wx.EVT_BUTTON, self._on_cargar)
        self.btn_leer.Bind(wx.EVT_BUTTON, lambda e: self._leer())
        self.btn_copiar.Bind(wx.EVT_BUTTON, lambda e: self._copiar())
        self.btn_mas.Bind(wx.EVT_BUTTON, lambda e: self._cargar_pagina(self._next_token))
        self.btn_responder.Bind(wx.EVT_BUTTON, lambda e: self._responder())
        self.btn_comentar.Bind(wx.EVT_BUTTON, lambda e: self._comentar())
        self.btn_cerrar.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        self.lb.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._leer())
        self.lb.Bind(wx.EVT_KEY_DOWN, self._on_key)

        self._actualizar_botones_sesion()

    def _actualizar_botones_sesion(self):
        hay = credenciales.hay_sesion() and youtube_api.google_disponible()
        self.btn_responder.Enable(hay)
        self.btn_comentar.Enable(hay)

    # ── Carga ────────────────────────────────────────────────────────────────

    def _cliente(self) -> youtube_api.ClienteYouTube:
        return youtube_api.ClienteYouTube(credenciales.cargar())

    def _on_cargar(self, event):
        if not youtube_api.google_disponible():
            wx.MessageBox("Faltan las librerías de la API. Instálalas con:\n"
                          "pip install google-api-python-client google-auth-oauthlib",
                          "Librerías ausentes", wx.OK | wx.ICON_WARNING, self)
            return
        if not credenciales.hay_lectura():
            wx.MessageBox("Falta la API key. Ponla en Configuración para leer comentarios.",
                          "Sin API key", wx.OK | wx.ICON_WARNING, self)
            return
        entrada = self.txt_url.GetValue().strip()
        if not entrada:
            self.txt_url.SetFocus()
            return
        self._video_id = extraer_video_id(entrada)
        self.lb.Clear()
        self._coms.clear()
        self._next_token = ""
        self.btn_mas.Disable()
        self._cargar_pagina("")

    def _cargar_pagina(self, page_token):
        if self._cargando:
            return
        self._cargando = True
        self.btn_cargar.Disable()
        self.btn_mas.Disable()
        anunciar("Cargando comentarios")
        orden = _ORDENES[max(0, self.cho_orden.GetSelection())][1]
        vid = self._video_id

        def _run():
            try:
                cli = self._cliente()
                coms, nxt = cli.leer_comentarios(vid, page_token=page_token, orden=orden)
                wx.CallAfter(self._pagina_ok, coms, nxt)
            except Exception as exc:
                logger.warning("leer_comentarios: %s", exc)
                wx.CallAfter(self._pagina_err, exc)

        threading.Thread(target=_run, daemon=True, name="Comentarios").start()

    def _pagina_ok(self, coms, nxt):
        self._cargando = False
        self.btn_cargar.Enable()
        for c in coms:
            self._coms.append(c)
            self.lb.Append(self._formato(c))
        self._next_token = nxt or ""
        self.btn_mas.Enable(bool(self._next_token))
        _snd.reproducir("conectado")
        if coms:
            anunciar(f"{len(coms)} comentarios cargados. {len(self._coms)} en total.")
            if self.lb.GetCount():
                self.lb.SetSelection(min(self.lb.GetCount() - len(coms), self.lb.GetCount() - 1))
        else:
            anunciar("No hay comentarios para mostrar.")

    def _pagina_err(self, exc):
        self._cargando = False
        self.btn_cargar.Enable()
        _snd.reproducir("error")
        msg = youtube_api.mensaje_error_api(exc)
        anunciar(msg)
        wx.MessageBox(msg, "No se pudieron cargar los comentarios",
                      wx.OK | wx.ICON_ERROR, self)

    def _formato(self, c: youtube_api.Comentario) -> str:
        if c.es_respuesta:
            return f"    Respuesta de {c.autor}: {c.texto}"
        extra = []
        if c.likes:
            extra.append(f"{c.likes} me gusta")
        if c.respuestas:
            extra.append(f"{c.respuestas} respuestas")
        sufijo = f" [{', '.join(extra)}]" if extra else ""
        return f"{c.autor}{sufijo}: {c.texto}"

    # ── Selección y acciones ─────────────────────────────────────────────────

    def _seleccionado(self) -> youtube_api.Comentario | None:
        i = self.lb.GetSelection()
        if i == wx.NOT_FOUND or i >= len(self._coms):
            return None
        return self._coms[i]

    def _on_key(self, event):
        k = event.GetKeyCode()
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._leer()
        elif k == ord('C') and event.ControlDown():
            self._copiar()
        else:
            event.Skip()

    def _leer(self):
        c = self._seleccionado()
        if not c:
            anunciar("Sin comentario seleccionado")
            return
        from tts_worker import construir_tts
        self._cola.put({"texto_tts": construir_tts(c.autor, c.texto, self._config)})

    def _copiar(self):
        c = self._seleccionado()
        if not c:
            anunciar("Sin comentario seleccionado")
            return
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(c.texto))
                wx.TheClipboard.Flush()
            finally:
                wx.TheClipboard.Close()
        _snd.reproducir("copiar")
        anunciar("Comentario copiado")

    def _responder(self):
        c = self._seleccionado()
        if not c:
            anunciar("Sin comentario seleccionado")
            return
        dlg = wx.TextEntryDialog(self, f"Responder a {c.autor}:", "Responder comentario")
        if dlg.ShowModal() == wx.ID_OK:
            texto = dlg.GetValue().strip()
            if texto:
                self._enviar_escritura(
                    lambda cli: cli.responder_comentario(c.comment_id, texto),
                    "Respuesta publicada")
        dlg.Destroy()

    def _comentar(self):
        if not self._video_id:
            anunciar("Carga primero un vídeo")
            return
        dlg = wx.TextEntryDialog(self, "Tu comentario en el vídeo:", "Comentar")
        if dlg.ShowModal() == wx.ID_OK:
            texto = dlg.GetValue().strip()
            if texto:
                self._enviar_escritura(
                    lambda cli: cli.publicar_comentario(self._video_id, texto),
                    "Comentario publicado")
        dlg.Destroy()

    def _enviar_escritura(self, accion, mensaje_ok):
        anunciar("Enviando")

        def _run():
            try:
                cli = self._cliente()
                nuevo_token = cli.token_actualizado()
                accion(cli)
                if cli.token_actualizado() and cli.token_actualizado() != nuevo_token:
                    credenciales.guardar_campo("token", cli.token_actualizado())
                wx.CallAfter(self._escritura_ok, mensaje_ok)
            except Exception as exc:
                logger.warning("escritura API: %s", exc)
                wx.CallAfter(self._escritura_err, exc)

        threading.Thread(target=_run, daemon=True, name="ComentarAPI").start()

    def _escritura_ok(self, mensaje):
        _snd.reproducir("voz_cambiada")
        anunciar(mensaje + ". Recuerda que YouTube puede tardar o retenerlo.")

    def _escritura_err(self, exc):
        _snd.reproducir("error")
        msg = youtube_api.mensaje_error_api(exc)
        anunciar(msg)
        wx.MessageBox(msg, "No se pudo enviar", wx.OK | wx.ICON_ERROR, self)


def abrir_comentarios(parent, cola, config) -> None:
    frame = ComentariosFrame(parent, cola, config)
    frame.Show()
