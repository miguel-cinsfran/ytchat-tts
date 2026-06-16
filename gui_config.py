"""Diálogo de Configuración de la API de YouTube (accesible, gestionado desde la app).

Todo lo necesario para activar las funciones online se hace aquí, sin tocar
ficheros a mano: pegar la API key, pegar el cliente OAuth, iniciar y cerrar
sesión. Se apoya en `credenciales.py` (almacén JSON) y `youtube_api.py`.
"""

from __future__ import annotations

import logging
import threading
import webbrowser

import wx

import credenciales
import youtube_api
import sound_player as _snd
from gui import anunciar, _T, _tc

logger = logging.getLogger(__name__)

URL_GUIA = "https://github.com/miguel-cinsfran/ytchat-tts/blob/main/docs/CONFIGURACION_API.md"


class ConfiguracionDialog(wx.Dialog):

    def __init__(self, parent):
        super().__init__(parent, title="Configuración de la API de YouTube",
                         size=(640, 520), name="DialogoConfiguracion")
        self.SetBackgroundColour(_T.bg)
        self._login_en_curso = False
        self._datos = credenciales.cargar()
        self._build_ui()
        self._refrescar_estado()
        self.Centre()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        panel = wx.Panel(self, name="PanelConfiguracion")
        panel.SetBackgroundColour(_T.bg)
        panel.SetForegroundColour(_T.text)
        vs = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(panel, name="IntroConfiguracion", label=(
            "La API key permite LEER comentarios de vídeos (sin iniciar sesión).\n"
            "El cliente OAuth e iniciar sesión permiten MODERAR el chat en vivo,\n"
            "enviar mensajes al directo y publicar o responder comentarios.\n"
            "Pulsa «Abrir guía» para ver cómo conseguir estos datos paso a paso."))
        intro.SetForegroundColour(_T.dim)
        vs.Add(intro, 0, wx.ALL, 12)

        if not youtube_api.google_disponible():
            aviso = wx.StaticText(panel, name="AvisoLibrerias", label=(
                "AVISO: faltan las librerías de la API. Instálalas con:\n"
                "pip install google-api-python-client google-auth-oauthlib"))
            aviso.SetForegroundColour(_T.red)
            vs.Add(aviso, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        grid = wx.FlexGridSizer(3, 2, 8, 8)
        grid.AddGrowableCol(1, 1)

        self.txt_api = self._fila(panel, grid, "&API key:",
                                  "API key de YouTube", self._datos.get("api_key", ""))
        self.txt_cid = self._fila(panel, grid, "ID de &cliente OAuth:",
                                  "ID de cliente OAuth", self._datos.get("oauth_client_id", ""))
        self.txt_secret = self._fila(panel, grid, "&Secreto de cliente OAuth:",
                                     "Secreto de cliente OAuth",
                                     self._datos.get("oauth_client_secret", ""),
                                     password=True)
        vs.Add(grid, 0, wx.EXPAND | wx.ALL, 12)

        self.lbl_estado = wx.StaticText(panel, name="EstadoSesion", label="")
        self.lbl_estado.SetForegroundColour(_T.accent)
        vs.Add(self.lbl_estado, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # Botones
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_guardar = wx.Button(panel, label="&Guardar claves", name="GuardarClaves")
        self.btn_login   = wx.Button(panel, label="&Iniciar sesión", name="IniciarSesion")
        self.btn_logout  = wx.Button(panel, label="Cerrar &sesión", name="CerrarSesion")
        self.btn_guia    = wx.Button(panel, label="Abrir g&uía", name="AbrirGuia")
        self.btn_cerrar  = wx.Button(panel, label="C&errar", name="CerrarDialogo")
        for b in (self.btn_guardar, self.btn_login, self.btn_logout,
                  self.btn_guia, self.btn_cerrar):
            b.SetBackgroundColour(_T.btn)
            b.SetForegroundColour(_T.btn_t)
            row.Add(b, 0, wx.RIGHT, 6)
        vs.Add(row, 0, wx.ALL, 12)

        panel.SetSizer(vs)

        self.btn_guardar.Bind(wx.EVT_BUTTON, self._on_guardar)
        self.btn_login.Bind(wx.EVT_BUTTON, self._on_login)
        self.btn_logout.Bind(wx.EVT_BUTTON, self._on_logout)
        self.btn_guia.Bind(wx.EVT_BUTTON, lambda e: webbrowser.open(URL_GUIA))
        self.btn_cerrar.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK))

    def _fila(self, panel, grid, etiqueta, nombre, valor, password=False):
        lbl = wx.StaticText(panel, label=etiqueta)
        lbl.SetForegroundColour(_T.text)
        estilo = wx.TE_PASSWORD if password else 0
        txt = wx.TextCtrl(panel, value=valor or "", style=estilo, name=nombre)
        _tc(txt)
        grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(txt, 1, wx.EXPAND)
        return txt

    # ── Estado ───────────────────────────────────────────────────────────────

    def _refrescar_estado(self):
        self._datos = credenciales.cargar()
        if credenciales.hay_sesion(self._datos):
            texto = "Estado: sesión iniciada. Moderación y comentarios activos."
            self.btn_logout.Enable()
        else:
            texto = "Estado: sin sesión. Solo lectura de comentarios (si hay API key)."
            self.btn_logout.Disable()
        if not youtube_api.google_disponible():
            self.btn_login.Disable()
        self.lbl_estado.SetLabel(texto)

    # ── Acciones ─────────────────────────────────────────────────────────────

    def _on_guardar(self, event):
        credenciales.guardar_campo("api_key", self.txt_api.GetValue().strip())
        credenciales.guardar_campo("oauth_client_id", self.txt_cid.GetValue().strip())
        credenciales.guardar_campo("oauth_client_secret", self.txt_secret.GetValue().strip())
        _snd.reproducir("copiar")
        anunciar("Claves guardadas")
        self._refrescar_estado()

    def _on_login(self, event):
        if self._login_en_curso:
            return
        cid = self.txt_cid.GetValue().strip()
        secret = self.txt_secret.GetValue().strip()
        if not (cid and secret):
            wx.MessageBox("Rellena el ID y el secreto de cliente OAuth antes de "
                          "iniciar sesión.", "Faltan datos",
                          wx.OK | wx.ICON_WARNING, self)
            return
        # Guardamos por si el usuario los acaba de pegar.
        self._on_guardar(None)
        self._login_en_curso = True
        self.btn_login.Disable()
        anunciar("Abriendo el navegador para iniciar sesión. Autoriza y vuelve aquí.")

        def _run():
            try:
                token = youtube_api.iniciar_sesion(cid, secret)
                credenciales.guardar_campo("token", token)
                wx.CallAfter(self._login_ok)
            except Exception as exc:
                logger.warning("Login OAuth falló: %s", exc)
                wx.CallAfter(self._login_err, exc)

        threading.Thread(target=_run, daemon=True, name="OAuthLogin").start()

    def _login_ok(self):
        self._login_en_curso = False
        self.btn_login.Enable()
        _snd.reproducir("conectado")
        anunciar("Sesión iniciada correctamente.")
        self._refrescar_estado()

    def _login_err(self, exc):
        self._login_en_curso = False
        self.btn_login.Enable()
        _snd.reproducir("error")
        anunciar("No se pudo iniciar sesión.")
        wx.MessageBox(f"No se pudo iniciar sesión:\n\n{exc}", "Error de inicio de sesión",
                      wx.OK | wx.ICON_ERROR, self)

    def _on_logout(self, event):
        credenciales.cerrar_sesion()
        _snd.reproducir("desconectado")
        anunciar("Sesión cerrada.")
        self._refrescar_estado()


def abrir_configuracion(parent) -> None:
    dlg = ConfiguracionDialog(parent)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()
