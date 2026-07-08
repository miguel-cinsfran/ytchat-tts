"""Panel de comentarios de un vídeo, integrado en la ventana principal.

Antes era una ventana aparte que volvía a pedir el enlace. Ahora es una pestaña
del notebook: trabaja sobre el vídeo que ya está conectado (la barra superior),
sin pedir el link otra vez. Reutiliza la cola del TTS, así que los comentarios
se leen con la misma voz SAPI5. Leer solo necesita una API key; publicar y
responder requieren haber iniciado sesión en Configuración.
"""

from __future__ import annotations

import logging
import threading

import wx

import credenciales
import youtube_api
import sound_player as _snd
from gui import anunciar, copiar_al_portapapeles, nombre_accesible, _T, _tc

logger = logging.getLogger(__name__)

_ORDENES = [("Más relevantes", "relevance"), ("Más recientes", "time")]


class ComentariosPanel(wx.Panel):
    """Pestaña de comentarios. El video_id se lo fija la ventana al conectar."""

    def __init__(self, parent, cola, config):
        super().__init__(parent, name="PanelComentarios")
        self._cola = cola
        self._config = config
        self._coms: list[youtube_api.Comentario] = []
        self._video_id = ""
        self._next_token = ""
        self._cargando = False
        # ids ya mostrados: con orden «relevancia» YouTube devuelve páginas que se
        # solapan o se repiten, así que deduplicamos para no contar/añadir repetidos.
        self._ids_vistos: set[str] = set()

        self.SetBackgroundColour(_T.bg)
        self.SetForegroundColour(_T.text)
        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        vs = wx.BoxSizer(wx.VERTICAL)

        # Fila de control: orden + recargar. Sin campo URL: usa el de la barra.
        row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self, label="&Orden:", name="EtiquetaOrden")
        lbl.SetForegroundColour(_T.dim)
        row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.cho_orden = wx.Choice(self, choices=[o[0] for o in _ORDENES],
                                   name="Orden de comentarios")
        _tc(self.cho_orden)
        self.cho_orden.SetSelection(0)
        self.cho_orden.Bind(wx.EVT_CHOICE, lambda e: self._recargar())
        row.Add(self.cho_orden, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        self.btn_recargar = wx.Button(self, label="&Recargar comentarios",
                                      name="RecargarComentarios")
        _btn(self.btn_recargar)
        self.btn_recargar.Bind(wx.EVT_BUTTON, lambda e: self._recargar())
        row.Add(self.btn_recargar, 0, wx.ALIGN_CENTER_VERTICAL)
        vs.Add(row, 0, wx.EXPAND | wx.ALL, 8)

        # Lista
        lbl = wx.StaticText(self, label="Co&mentarios:", name="EtiquetaListaComentarios")
        lbl.SetForegroundColour(_T.accent)
        vs.Add(lbl, 0, wx.LEFT | wx.RIGHT, 8)
        self.lb = wx.ListBox(self, style=wx.LB_SINGLE | wx.LB_HSCROLL,
                             name="Lista de comentarios")
        _tc(self.lb)
        pt = int(self._config.get("tamanio_fuente_chat", 12))
        self.lb.SetFont(wx.Font(pt, wx.FONTFAMILY_DEFAULT,
                                wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        # Leer/copiar/responder van por Enter, Ctrl+C y la tecla Aplicaciones
        # (menú contextual), igual que el chat del live: no hacen falta botones.
        self.lb.SetToolTip("Enter lee el comentario con la voz. Ctrl+C copia. "
                           "Tecla Aplicaciones (o clic derecho) abre el menú.")
        nombre_accesible(self.lb, "Lista de comentarios")
        vs.Add(self.lb, 1, wx.EXPAND | wx.ALL, 8)

        # Botones de acción: solo los que NO dependen del comentario seleccionado
        # (cargar más páginas y comentar en el vídeo). El resto, en el menú.
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_mas   = wx.Button(self, label="Cargar &más", name="CargarMas")
        self.btn_comentar  = wx.Button(self, label="Comen&tar en el vídeo", name="ComentarVideo")
        for b in (self.btn_mas, self.btn_comentar):
            _btn(b)
            row.Add(b, 0, wx.RIGHT, 6)
        self.btn_mas.Disable()
        vs.Add(row, 0, wx.ALL, 8)

        self.SetSizer(vs)

        self.btn_mas.Bind(wx.EVT_BUTTON, lambda e: self._cargar_pagina(self._next_token))
        self.btn_comentar.Bind(wx.EVT_BUTTON, lambda e: self._comentar())
        self.lb.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._leer())
        self.lb.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self.lb.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)

        self._actualizar_botones_sesion()

    def _actualizar_botones_sesion(self):
        # Comentar requiere sesión; Responder se gobierna en el menú contextual.
        hay = credenciales.hay_sesion() and youtube_api.google_disponible()
        self.btn_comentar.Enable(hay)

    # ── API pública (la ventana la llama al conectar) ─────────────────────────

    def set_video(self, video_id: str, autocargar: bool = True) -> None:
        """Fija el vídeo objetivo y, por defecto, carga la primera página."""
        self._video_id = video_id or ""
        self.lb.Clear()
        self._coms.clear()
        self._ids_vistos.clear()
        self._next_token = ""
        self.btn_mas.Disable()
        self._actualizar_botones_sesion()
        if autocargar and self._video_id:
            self._cargar_pagina("")

    def limpiar(self) -> None:
        self._video_id = ""
        self.lb.Clear()
        self._coms.clear()
        self._ids_vistos.clear()
        self._next_token = ""
        self.btn_mas.Disable()

    def mostrar_no_disponible(self, texto: str) -> None:
        """Deja la lista con un único aviso, para que quien llegue a esta pestaña
        (p. ej. en un directo de TikTok, que no tiene comentarios aquí) entienda
        por qué está vacía en vez de creer que falla. El aviso no es un
        comentario real: leer o copiar sobre él no hacen nada."""
        self.limpiar()
        self.lb.Append(texto)
        self.btn_comentar.Disable()

    def anclar_foco(self) -> None:
        try:    self.lb.SetFocus()
        except Exception: pass

    # ── Carga ────────────────────────────────────────────────────────────────

    def _cliente(self) -> youtube_api.ClienteYouTube:
        return youtube_api.ClienteYouTube(credenciales.cargar())

    def _recargar(self):
        if self._video_id:
            self.set_video(self._video_id, autocargar=True)

    def _cargar_pagina(self, page_token):
        if self._cargando:
            return
        if not youtube_api.google_disponible():
            wx.MessageBox("Faltan las librerías de la API. Instálalas con:\n"
                          "pip install google-api-python-client google-auth-oauthlib",
                          "Librerías ausentes", wx.OK | wx.ICON_WARNING, self)
            return
        if not credenciales.hay_lectura():
            wx.MessageBox("Falta la API key. Ponla en Preferencias, pestaña API, "
                          "para leer comentarios.",
                          "Sin API key", wx.OK | wx.ICON_WARNING, self)
            return
        if not self._video_id:
            anunciar("Conecta primero un vídeo")
            return
        self._cargando = True
        self.btn_recargar.Disable()
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
        self.btn_recargar.Enable()
        anteriores = self.lb.GetCount()
        # Deduplicar: con orden «relevancia» las páginas se solapan, así que solo
        # añadimos lo que no se haya mostrado ya, y contamos hilos y respuestas
        # por separado (el total por página varía mucho porque cada hilo arrastra
        # un número distinto de respuestas).
        n_hilos = n_resp = 0
        for c in coms:
            if c.comment_id and c.comment_id in self._ids_vistos:
                continue
            if c.comment_id:
                self._ids_vistos.add(c.comment_id)
            self._coms.append(c)
            self.lb.Append(self._formato(c))
            if c.es_respuesta:
                n_resp += 1
            else:
                n_hilos += 1
        self._next_token = nxt or ""
        self.btn_mas.Enable(bool(self._next_token))
        _snd.reproducir("conectado")
        nuevos = n_hilos + n_resp
        if nuevos:
            partes = []
            if n_hilos:
                partes.append(f"{n_hilos} comentario" + ("s" if n_hilos != 1 else ""))
            if n_resp:
                partes.append(f"{n_resp} respuesta" + ("s" if n_resp != 1 else ""))
            anunciar(f"{' y '.join(partes)}. {len(self._coms)} en total.")
            self.lb.SetSelection(min(anteriores, self.lb.GetCount() - 1))
        elif coms:
            # La página solo traía repetidos (típico con orden «relevancia»).
            anunciar("No hay comentarios nuevos.")
        else:
            anunciar("No hay comentarios para mostrar.")

    def _pagina_err(self, exc):
        self._cargando = False
        self.btn_recargar.Enable()
        # Si había más páginas pendientes, que un error transitorio no deje
        # «Cargar más» apagado (obligaba a recargar todo).
        self.btn_mas.Enable(bool(self._next_token))
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
        elif k == wx.WXK_WINDOWS_MENU:
            self._mostrar_menu()
        else:
            event.Skip()

    def _on_context_menu(self, event):
        self._mostrar_menu()

    def _mostrar_menu(self):
        """Menú contextual sobre el comentario seleccionado (tecla Aplicaciones o
        clic derecho), igual que el chat del live: Leer, Copiar y, con sesión
        iniciada, Responder a ese comentario en concreto."""
        c = self._seleccionado()
        if not c:
            return
        menu = wx.Menu()
        id_leer    = wx.NewIdRef()
        id_copiar  = wx.NewIdRef()
        id_copiar2 = wx.NewIdRef()
        menu.Append(id_leer,    "Leer con TTS")
        menu.Append(id_copiar,  "Copiar comentario")
        menu.Append(id_copiar2, "Copiar todo (autor: comentario)")
        # Handlers sobre el propio menú: mueren con él y no se acumulan
        # bindings en el panel con cada apertura.
        menu.Bind(wx.EVT_MENU, lambda e: self._leer(),       id=id_leer)
        menu.Bind(wx.EVT_MENU, lambda e: self._copiar(),     id=id_copiar)
        menu.Bind(wx.EVT_MENU, lambda e: self._copiar_todo(), id=id_copiar2)

        if credenciales.hay_sesion() and youtube_api.google_disponible():
            menu.AppendSeparator()
            id_resp = wx.NewIdRef()
            menu.Append(id_resp, f"Responder a {c.autor}")
            menu.Bind(wx.EVT_MENU, lambda e: self._responder(), id=id_resp)

        self.lb.PopupMenu(menu)
        menu.Destroy()

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
        copiar_al_portapapeles(c.texto)
        _snd.reproducir("copiar")
        anunciar("Comentario copiado")

    def _copiar_todo(self):
        c = self._seleccionado()
        if not c:
            anunciar("Sin comentario seleccionado")
            return
        copiar_al_portapapeles(f"{c.autor}: {c.texto}")
        _snd.reproducir("copiar")
        anunciar("Línea copiada")

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
            anunciar("Conecta primero un vídeo")
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
                token_previo = cli.token_actualizado()
                accion(cli)
                if cli.token_actualizado() and cli.token_actualizado() != token_previo:
                    credenciales.guardar_campo("token", cli.token_actualizado())
                wx.CallAfter(self._escritura_ok, mensaje_ok)
            except Exception as exc:
                logger.warning("escritura API: %s", exc)
                wx.CallAfter(self._escritura_err, exc)

        threading.Thread(target=_run, daemon=True, name="ComentarAPI").start()

    def _escritura_ok(self, mensaje):
        _snd.reproducir("comentario")
        anunciar(mensaje + ". Recuerda que YouTube puede tardar o retenerlo.")

    def _escritura_err(self, exc):
        _snd.reproducir("error")
        msg = youtube_api.mensaje_error_api(exc)
        anunciar(msg)
        wx.MessageBox(msg, "No se pudo enviar", wx.OK | wx.ICON_ERROR, self)


def _btn(b: wx.Button) -> None:
    b.SetBackgroundColour(_T.btn)
    b.SetForegroundColour(_T.btn_t)
