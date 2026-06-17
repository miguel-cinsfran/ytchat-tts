"""Diálogo de Preferencias con pestañas (accesible).

Reúne en un solo sitio lo que antes solo se editaba a mano en config.ini y
sounds.ini: interfaz (fuente, tema de sonido), lectura, filtros de palabras y
usuarios, y un editor de atajos. Persiste con `config.guardar_opcion` (que
conserva comentarios y orden del INI) y actualiza el dict de config en memoria.
La configuración de API/OAuth sigue en su propio diálogo (Herramientas).
"""

from __future__ import annotations

import logging
import threading
import webbrowser

import wx

import config as cfg
import sound_player as _snd
import credenciales
import youtube_api
from gui import anunciar

logger = logging.getLogger(__name__)


# El diálogo de Preferencias usa apariencia NATIVA (sin el tema oscuro de la
# ventana principal). Motivo de accesibilidad: en Windows, poner un color
# personalizado a una casilla o radio la convierte en un control «owner-drawn»
# que NVDA anuncia como botón y sin su estado (marcada/no marcada). Sombreamos
# aquí el tema y el helper de color para que TODAS las llamadas existentes
# dejen los controles con los colores por defecto del sistema.

class _T:
    bg = surface = field = border = text = dim = accent = gold = green = red = \
        btn = btn_t = wx.NullColour


def _tc(w, bg=None, fg=None):
    pass

URL_GUIA = "https://github.com/miguel-cinsfran/ytchat-tts/blob/main/docs/CONFIGURACION_API.md"

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
        self.nb.AddPage(self._pag_api(self.nb), "API y sesión")
        # Anunciar la pestaña al cambiar (Ctrl+Tab no lo verbaliza solo).
        self.nb.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_pestana)
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

    def _on_pestana(self, event):
        idx = event.GetSelection()
        if 0 <= idx < self.nb.GetPageCount():
            anunciar(self.nb.GetPageText(idx))
        event.Skip()

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

        self.chk_autoplay = wx.CheckBox(p, label="&Reproducir el audio automáticamente al conectar",
                                        name="AutoplayReproductor")
        self.chk_autoplay.SetForegroundColour(_T.text)
        self.chk_autoplay.SetValue(bool(self._config.get("autoplay_reproductor", True)))
        vs.Add(self.chk_autoplay, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.chk_metadatos = wx.CheckBox(p, label="Mostrar la pestaña de &información del vídeo (canal, vistas, descripción)",
                                         name="MostrarMetadatos")
        self.chk_metadatos.SetForegroundColour(_T.text)
        self.chk_metadatos.SetValue(bool(self._config.get("mostrar_metadatos", True)))
        vs.Add(self.chk_metadatos, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.chk_botones_rep = wx.CheckBox(p, label="Mostrar los &botones del reproductor (también con su interruptor y el menú Reproductor)",
                                           name="MostrarBotonesReproductor")
        self.chk_botones_rep.SetForegroundColour(_T.text)
        self.chk_botones_rep.SetValue(bool(self._config.get("mostrar_botones_reproductor", False)))
        vs.Add(self.chk_botones_rep, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

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

        self.chk_emojis = wx.CheckBox(p, label="&Quitar emojis (no mostrarlos en la lista ni leerlos)",
                                      name="LimpiarEmojis")
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
            "El modificador indica el área: Ctrl para el reproductor, Alt para "
            "conexión y chat, y teclas F para la voz. Escribe combinaciones como "
            "ctrl+d, alt+enter, ctrl+left o f5. F9 a F12 son fijas. Deja en "
            "blanco para desactivar. La navegación entre regiones (F6 y "
            "Shift+F6) no se cambia aquí."),
            name="NotaAtajos")
        nota.SetForegroundColour(_T.dim)
        nota.Wrap(560)
        vs.Add(nota, 0, wx.ALL, 10)

        self._campos_atajo: dict[str, wx.TextCtrl] = {}
        raw = self._config.get("atajos_raw", {})
        for titulo, acciones in cfg.ATAJOS_GRUPOS:
            box = wx.StaticBoxSizer(wx.VERTICAL, p, titulo)
            grid = wx.FlexGridSizer(0, 2, 6, 10)
            grid.AddGrowableCol(1, 1)
            for accion in acciones:
                etiqueta = _ETIQUETAS_ATAJO.get(accion, accion)
                valor = raw.get(accion, cfg.ATAJOS_DEFAULTS[accion])
                lbl = wx.StaticText(p, label=etiqueta + ":")
                lbl.SetForegroundColour(_T.text)
                txt = wx.TextCtrl(p, value=valor, name=etiqueta)
                _tc(txt)
                if accion in cfg.ATAJOS_FIJOS:
                    txt.Disable()
                grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
                grid.Add(txt, 1, wx.EXPAND)
                self._campos_atajo[accion] = txt
            box.Add(grid, 0, wx.EXPAND | wx.ALL, 6)
            vs.Add(box, 0, wx.EXPAND | wx.ALL, 8)

        p.SetSizer(vs)
        return p

    def _pag_api(self, parent):
        p = self._make_panel(parent, "PagApi")
        self._login_en_curso = False
        vs = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(p, name="IntroApi", label=(
            "La API key permite LEER comentarios (sin iniciar sesión). El cliente "
            "OAuth e iniciar sesión permiten MODERAR el chat, enviar mensajes al "
            "directo y publicar o responder comentarios."))
        intro.SetForegroundColour(_T.dim)
        intro.Wrap(560)
        vs.Add(intro, 0, wx.ALL, 10)

        if not youtube_api.google_disponible():
            aviso = wx.StaticText(p, name="AvisoLibreriasApi", label=(
                "AVISO: faltan las librerías de la API. Instálalas con:\n"
                "pip install google-api-python-client google-auth-oauthlib"))
            aviso.SetForegroundColour(_T.red)
            vs.Add(aviso, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        datos = credenciales.cargar()
        grid = wx.FlexGridSizer(3, 2, 8, 8)
        grid.AddGrowableCol(1, 1)
        self.txt_api = self._fila_api(p, grid, "&API key:", "API key de YouTube",
                                      datos.get("api_key", ""))
        self.txt_cid = self._fila_api(p, grid, "ID de &cliente OAuth:",
                                      "ID de cliente OAuth", datos.get("oauth_client_id", ""))
        self.txt_secret = self._fila_api(p, grid, "&Secreto de cliente OAuth:",
                                         "Secreto de cliente OAuth",
                                         datos.get("oauth_client_secret", ""), password=True)
        vs.Add(grid, 0, wx.EXPAND | wx.ALL, 10)

        self.lbl_estado_api = wx.StaticText(p, name="EstadoSesion", label="")
        self.lbl_estado_api.SetForegroundColour(_T.accent)
        vs.Add(self.lbl_estado_api, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_api_guardar = wx.Button(p, label="&Guardar claves", name="GuardarClaves")
        self.btn_api_login   = wx.Button(p, label="&Iniciar sesión", name="IniciarSesion")
        self.btn_api_logout  = wx.Button(p, label="Cerrar s&esión", name="CerrarSesion")
        self.btn_api_guia    = wx.Button(p, label="Abrir g&uía", name="AbrirGuia")
        for b in (self.btn_api_guardar, self.btn_api_login, self.btn_api_logout, self.btn_api_guia):
            b.SetBackgroundColour(_T.btn)
            b.SetForegroundColour(_T.btn_t)
            row.Add(b, 0, wx.RIGHT, 6)
        vs.Add(row, 0, wx.ALL, 10)

        p.SetSizer(vs)
        self.btn_api_guardar.Bind(wx.EVT_BUTTON, self._api_guardar)
        self.btn_api_login.Bind(wx.EVT_BUTTON, self._api_login)
        self.btn_api_logout.Bind(wx.EVT_BUTTON, self._api_logout)
        self.btn_api_guia.Bind(wx.EVT_BUTTON, lambda e: webbrowser.open(URL_GUIA))
        self._api_refrescar_estado()
        return p

    def _fila_api(self, p, grid, etiqueta, nombre, valor, password=False):
        lbl = wx.StaticText(p, label=etiqueta)
        lbl.SetForegroundColour(_T.text)
        estilo = wx.TE_PASSWORD if password else 0
        txt = wx.TextCtrl(p, value=valor or "", style=estilo, name=nombre)
        _tc(txt)
        grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(txt, 1, wx.EXPAND)
        return txt

    def _api_refrescar_estado(self):
        if credenciales.hay_sesion():
            texto = "Estado: sesión iniciada. Moderación y comentarios activos."
            self.btn_api_logout.Enable()
        else:
            texto = "Estado: sin sesión. Solo lectura de comentarios (si hay API key)."
            self.btn_api_logout.Disable()
        if not youtube_api.google_disponible():
            self.btn_api_login.Disable()
        self.lbl_estado_api.SetLabel(texto)

    def _api_guardar(self, event):
        credenciales.guardar_campo("api_key", self.txt_api.GetValue().strip())
        credenciales.guardar_campo("oauth_client_id", self.txt_cid.GetValue().strip())
        credenciales.guardar_campo("oauth_client_secret", self.txt_secret.GetValue().strip())
        _snd.reproducir("copiar")
        anunciar("Claves guardadas")
        self._api_refrescar_estado()

    def _api_login(self, event):
        if self._login_en_curso:
            return
        cid = self.txt_cid.GetValue().strip()
        secret = self.txt_secret.GetValue().strip()
        if not (cid and secret):
            wx.MessageBox("Rellena el ID y el secreto de cliente OAuth antes de "
                          "iniciar sesión.", "Faltan datos", wx.OK | wx.ICON_WARNING, self)
            return
        self._api_guardar(None)
        self._login_en_curso = True
        self.btn_api_login.Disable()
        anunciar("Abriendo el navegador para iniciar sesión. Autoriza y vuelve aquí.")

        def _run():
            try:
                token = youtube_api.iniciar_sesion(cid, secret)
                credenciales.guardar_campo("token", token)
                wx.CallAfter(self._api_login_ok)
            except Exception as exc:
                logger.warning("Login OAuth falló: %s", exc)
                wx.CallAfter(self._api_login_err, exc)

        threading.Thread(target=_run, daemon=True, name="OAuthLogin").start()

    def _api_login_ok(self):
        self._login_en_curso = False
        self.btn_api_login.Enable()
        _snd.reproducir("conectado")
        anunciar("Sesión iniciada correctamente.")
        self._api_refrescar_estado()

    def _api_login_err(self, exc):
        self._login_en_curso = False
        self.btn_api_login.Enable()
        _snd.reproducir("error")
        anunciar("No se pudo iniciar sesión.")
        wx.MessageBox(f"No se pudo iniciar sesión:\n\n{exc}", "Error de inicio de sesión",
                      wx.OK | wx.ICON_ERROR, self)

    def _api_logout(self, event):
        credenciales.cerrar_sesion()
        _snd.reproducir("desconectado")
        anunciar("Sesión cerrada.")
        self._api_refrescar_estado()

    def _fila_label(self, p, texto):
        lbl = wx.StaticText(p, label=texto)
        lbl.SetForegroundColour(_T.accent)
        return lbl

    # ── Guardar ───────────────────────────────────────────────────────────────

    def _set(self, seccion, clave, valor):
        cfg.guardar_opcion(self._ruta, seccion, clave, valor)
        self._cambios = True

    def _validar_atajos(self) -> list[str]:
        area_txt = {"ctrl": "Ctrl+algo", "alt": "Alt+algo",
                    "f": "una tecla F (f1 a f12)"}
        errores = []
        for accion, txt in self._campos_atajo.items():
            if accion in cfg.ATAJOS_FIJOS:
                continue
            valor = txt.GetValue().strip().lower()
            if valor == "":
                continue   # desactivado a propósito
            norm = cfg._normalizar_atajo(valor)
            etq = _ETIQUETAS_ATAJO.get(accion, accion)
            if norm is None:
                errores.append(f"  {etq}: «{valor}» no es un atajo válido.")
            elif not cfg.atajo_valido_para_area(accion, norm):
                req = area_txt.get(cfg.ATAJOS_AREA.get(accion), "el modificador correcto")
                errores.append(f"  {etq}: «{valor}» debe ser {req}.")
        return errores

    def _on_guardar(self, event):
        c = self._config

        # Validar atajos ANTES de guardar nada: cada uno debe respetar su área
        # (Ctrl reproductor, Alt app, F voz). Si algo está mal, no se guarda.
        errores = self._validar_atajos()
        if errores:
            self.nb.SetSelection(3)   # pestaña Atajos
            wx.MessageBox("Estos atajos no son válidos:\n\n" + "\n".join(errores),
                          "Atajos inválidos", wx.OK | wx.ICON_WARNING, self)
            return

        # Interfaz
        fuente = str(self.sp_fuente.GetValue())
        self._set("ui", "tamanio_fuente_chat", fuente)
        c["tamanio_fuente_chat"] = int(fuente)

        total_sc = self.chk_total_sc.GetValue()
        self._set("ui", "mostrar_total_superchats", "true" if total_sc else "false")
        c["mostrar_total_superchats"] = total_sc

        autoplay = self.chk_autoplay.GetValue()
        self._set("ui", "autoplay_reproductor", "true" if autoplay else "false")
        c["autoplay_reproductor"] = autoplay

        metadatos = self.chk_metadatos.GetValue()
        self._set("ui", "mostrar_metadatos", "true" if metadatos else "false")
        c["mostrar_metadatos"] = metadatos

        botones_rep = self.chk_botones_rep.GetValue()
        self._set("ui", "mostrar_botones_reproductor", "true" if botones_rep else "false")
        c["mostrar_botones_reproductor"] = botones_rep

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
    # Reproductor
    "rep_play":          "Reproducir o pausa",
    "rep_retro":         "Retroceder 10 segundos",
    "rep_avanz":         "Avanzar 10 segundos",
    "rep_detener":       "Detener vídeo",
    "rep_mute":          "Silenciar o activar audio",
    "rep_vol_menos":     "Bajar volumen del reproductor",
    "rep_vol_mas":       "Subir volumen del reproductor",
    # Conexión y chat
    "conectar":          "Conectar",
    "desconectar":       "Desconectar",
    "enviar_chat":       "Enviar mensaje al chat",
    "ir_url":            "Ir al campo URL",
    # Voz / lectura
    "pausa":             "Pausar o reanudar lectura",
    "detener_tts":       "Detener voz actual",
    "velocidad_menos":   "Bajar velocidad (fija)",
    "velocidad_mas":     "Subir velocidad (fija)",
    "volumen_menos":     "Bajar volumen del TTS (fijo)",
    "volumen_mas":       "Subir volumen del TTS (fijo)",
    "silenciar_lectura": "Silenciar lectura TTS",
    "silenciar_sonidos": "Silenciar sonidos",
    "anunciar_estado":   "Anunciar estado",
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
