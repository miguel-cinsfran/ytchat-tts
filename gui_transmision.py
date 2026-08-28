"""Diálogo accesible para colocar el panel de chat en OBS."""

from __future__ import annotations

import threading

import wx

import ajuste_fino
import obs_cliente
import obs_disposicion
import obs_estado
import overlay_servidor
from gui import ContadorAccesible, _T, anunciar, nombre_accesible
from obs_panel import GestorPanelObs, NOMBRE_FUENTE
import sound_player


_TEXTO_LIENZO = (
    "El programa de emisión compone lo que ven los espectadores sobre un\n"
    "rectángulo de tamaño fijo, llamado lienzo. No es la pantalla del equipo\n"
    "ni la ventana del juego.\n\n"
    "Lo que queda dentro del lienzo se emite. Lo que sobresale del borde se\n"
    "recorta, sin ningún aviso.\n\n"
    "Que dos fuentes se superpongan no es necesariamente un problema. El\n"
    "fondo de este panel es transparente: solo se ven las tarjetas de los\n"
    "mensajes, y solo tapan lo que hay justo debajo de ellas.")

_PUERTO_PANEL_DEFECTO = 8730
_RUTA_PANEL_CHAT = "/chat"


class TransmisionDialog(wx.Dialog):

    def __init__(self, parent, gestor=None):
        super().__init__(parent, title="Transmisión", size=(620, 680),
                         name="DialogoTransmision")
        self._gestor = gestor or GestorPanelObs()
        self._restablecer = {}
        self._ultimo_snap = None
        self._ajuste_en_curso = False
        self._ajuste_transformacion = None
        self._movimiento_en_vuelo = False
        self._cerrando = False
        self._operacion_en_vuelo = False
        self.SetBackgroundColour(_T.bg)
        self._crear_controles()
        self._temporizador_consulta = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._anunciar_consulta, self._temporizador_consulta)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)
        self.Centre()
        self._en_hilo(self._cargar_inicial, self._inicial_cargada)

    def _crear_controles(self):
        panel = wx.Panel(self, name="PanelTransmision")
        panel.SetBackgroundColour(_T.bg)
        panel.SetForegroundColour(_T.text)
        caja = wx.BoxSizer(wx.VERTICAL)
        nota = wx.StaticText(panel, name="NotaTransmision", label=(
            "Coloca el panel de chat dentro de una escena de OBS. Cada cambio se "
            "aplica en el momento y se anuncia. «Restablecer» deshace todo lo hecho "
            "desde que se abrió esta ventana."))
        nota.SetForegroundColour(_T.dim)
        nota.Wrap(560)
        caja.Add(nota, 0, wx.ALL, 10)

        self.txt_estado = wx.TextCtrl(
            panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="Estado de la transmisión")
        self.txt_estado.SetBackgroundColour(_T.field)
        self.txt_estado.SetForegroundColour(_T.text)
        nombre_accesible(self.txt_estado, "Estado de la transmisión")
        caja.Add(self.txt_estado, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.btn_actualizar = self._boton(panel, "&Actualizar estado", "ActualizarEstado")
        caja.Add(self.btn_actualizar, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.btn_preparar = self._boton(panel, "&Preparar el panel", "Preparar el panel")
        caja.Add(self.btn_preparar, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.cho_escena = wx.Choice(panel, name="Escena")
        nombre_accesible(self.cho_escena, "Escena")
        caja.Add(self.cho_escena, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.btn_poner_al_aire = self._boton(panel, "Poner al &aire", "Poner al aire")
        caja.Add(self.btn_poner_al_aire, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.cho_fuente = wx.Choice(panel, name="Fuente")
        nombre_accesible(self.cho_fuente, "Fuente")
        caja.Add(self.cho_fuente, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.cho_posicion = wx.Choice(
            panel, choices=[nombre.replace("-", " ").capitalize()
                            for nombre in obs_disposicion.ANCLAJES],
            name="Posición del panel")
        nombre_accesible(self.cho_posicion, "Posición del panel")
        caja.Add(self.cho_posicion, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.btn_colocar = self._boton(
            panel, "&Colocar en esa posición", "Colocar en esa posición")
        caja.Add(self.btn_colocar, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.sp_ancho = ContadorAccesible(panel, min=100, max=4000, initial=460,
                                    name="Ancho del panel en píxeles")
        self.sp_alto = ContadorAccesible(panel, min=100, max=4000, initial=620,
                                   name="Alto del panel en píxeles")
        caja.Add(self.sp_ancho, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        caja.Add(self.sp_alto, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.btn_tamano = self._boton(panel, "Aplicar &tamaño", "AplicarTamano")
        caja.Add(self.btn_tamano, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.chk_mostrar = wx.CheckBox(panel, label="&Mostrar el panel en la escena",
                                       name="MostrarPanel")
        self.chk_fijar = wx.CheckBox(panel, label="&Fijar el panel para que no se mueva",
                                     name="FijarPanel")
        caja.Add(self.chk_mostrar, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        caja.Add(self.chk_fijar, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.btn_frente = self._boton(panel, "Poner al &frente", "PonerAlFrente")
        self._etiqueta_ajuste = "Ajuste &fino"
        self.btn_ajuste = self._boton(panel, self._etiqueta_ajuste, "AjusteFino")
        self.btn_captura = self._boton(panel, "&Guardar una captura de la escena…", "GuardarCaptura")
        self.btn_lienzo = self._boton(panel, "&Qué es el lienzo", "QueEsElLienzo")
        self.btn_restaurar = self._boton(panel, "&Restablecer", "RestablecerTransmision")
        self.btn_transmitir = self._boton(panel, "&Transmitir", "Transmitir")
        self.btn_grabar = self._boton(panel, "&Grabar", "Grabar")
        self.btn_pausar_grabacion = self._boton(
            panel, "Pausar la gra&bacion", "Pausar la grabacion")
        for boton in (self.btn_frente, self.btn_ajuste, self.btn_captura,
                      self.btn_lienzo, self.btn_restaurar, self.btn_transmitir,
                      self.btn_grabar, self.btn_pausar_grabacion):
            caja.Add(boton, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.btn_cerrar = self._boton(panel, "C&errar", "CerrarTransmision", wx.ID_CANCEL)
        caja.Add(self.btn_cerrar, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(caja)
        self._acciones = (self.btn_actualizar, self.btn_preparar, self.cho_escena,
                          self.btn_poner_al_aire, self.cho_fuente, self.cho_posicion,
                          self.btn_colocar, self.sp_ancho, self.sp_alto, self.btn_tamano, self.chk_mostrar,
                          self.chk_fijar, self.btn_frente, self.btn_ajuste, self.btn_captura,
                          self.btn_restaurar, self.btn_transmitir, self.btn_grabar,
                          self.btn_pausar_grabacion)
        self.btn_actualizar.Bind(wx.EVT_BUTTON, self._actualizar)
        self.btn_preparar.Bind(wx.EVT_BUTTON, self._preparar)
        self.cho_escena.Bind(wx.EVT_CHOICE, self._cambiar_escena)
        self.btn_poner_al_aire.Bind(wx.EVT_BUTTON, self._poner_al_aire)
        self.cho_fuente.Bind(wx.EVT_CHOICE, self._cambiar_fuente)
        # Recorrer con flechas dispara EVT_CHOICE y esto sale al aire.
        self.btn_colocar.Bind(wx.EVT_BUTTON, self._colocar)
        self.btn_tamano.Bind(wx.EVT_BUTTON, self._tamano)
        self.chk_mostrar.Bind(wx.EVT_CHECKBOX, self._mostrar)
        self.chk_fijar.Bind(wx.EVT_CHECKBOX, self._fijar)
        self.btn_frente.Bind(wx.EVT_BUTTON, self._frente)
        self.btn_ajuste.Bind(wx.EVT_BUTTON, self._iniciar_ajuste)
        self.btn_ajuste.Bind(wx.EVT_KILL_FOCUS, self._ajuste_perdio_foco)
        self.btn_captura.Bind(wx.EVT_BUTTON, self._captura)
        self.btn_lienzo.Bind(wx.EVT_BUTTON, self._lienzo)
        self.btn_restaurar.Bind(wx.EVT_BUTTON, self._restaurar)
        self.btn_transmitir.Bind(wx.EVT_BUTTON, self._transmitir)
        self.btn_grabar.Bind(wx.EVT_BUTTON, self._grabar)
        self.btn_pausar_grabacion.Bind(wx.EVT_BUTTON, self._pausar_grabacion)
        self.btn_cerrar.Bind(wx.EVT_BUTTON, self._cerrar)
        self.Bind(wx.EVT_CLOSE, self._cerrar)
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla_ajuste)

    @staticmethod
    def _boton(panel, etiqueta, nombre, identificador=wx.ID_ANY):
        boton = wx.Button(panel, identificador, etiqueta, name=nombre)
        boton.SetBackgroundColour(_T.btn)
        boton.SetForegroundColour(_T.btn_t)
        return boton

    def _en_hilo(self, funcion, al_terminar=None):
        self._activar(False)
        self._operacion_en_vuelo = True
        self._temporizador_consulta.StartOnce(400)
        def ejecutar():
            try:
                resultado = funcion()
            except obs_cliente.ObsError as error:
                wx.CallAfter(self._fallo, str(error))
            else:
                wx.CallAfter(self._terminar, resultado, al_terminar)
        threading.Thread(target=ejecutar, daemon=True, name="TransmisionOBS").start()

    def _activar(self, activo):
        for control in self._acciones:
            control.Enable(activo)

    def _terminar(self, resultado, al_terminar):
        self._temporizador_consulta.Stop()
        self._operacion_en_vuelo = False
        if self._cerrando:
            return
        self._activar(True)
        if isinstance(resultado, obs_disposicion.SnapshotPanel):
            self._mostrar_snap(resultado)
        if al_terminar:
            al_terminar(resultado)

    def _fallo(self, mensaje):
        self._temporizador_consulta.Stop()
        self._operacion_en_vuelo = False
        if self._cerrando:
            return
        self._activar(False)
        self.txt_estado.SetValue(mensaje)
        sound_player.reproducir("error")
        anunciar(mensaje)
        self.btn_actualizar.Enable(True)
        self.btn_actualizar.SetFocus()

    def _anunciar_consulta(self, event):
        if self._operacion_en_vuelo and not self._cerrando:
            # Puede repetirse mientras espera la operación y no debe interrumpir.
            anunciar("Consultando OBS", False)

    def _al_destruir(self, event):
        self._temporizador_consulta.Stop()
        event.Skip()

    def _cargar_inicial(self):
        self._gestor.conectar()
        escenas = self._gestor.escenas()
        al_aire = self._gestor.escena_al_aire()
        escena = al_aire if al_aire in escenas else (escenas[0] if escenas else "")
        fuentes = self._gestor.fuentes(escena)
        fuente = NOMBRE_FUENTE if NOMBRE_FUENTE in fuentes else (fuentes[0] if fuentes else "")
        snap = self._gestor.instantanea(escena, fuente=fuente)
        return (escenas, escena, al_aire, fuentes, fuente, snap,
                self._gestor.transformacion(escena, fuente=fuente),
                self._gestor.estado_transmision(), self._gestor.estado_grabacion())

    def _inicial_cargada(self, datos):
        escenas, escena, al_aire, fuentes, fuente, snap, transformacion, transmision, grabacion = datos
        self.cho_escena.Set(list(escenas))
        if escena:
            self.cho_escena.SetStringSelection(escena)
        self._cargar_fuentes(fuentes, fuente)
        self._mostrar_snap(snap)
        anunciar(obs_disposicion.describir_preparacion(
            snap.conectado, overlay_servidor.esta_encendido(),
            overlay_servidor.puerto_actual(), NOMBRE_FUENTE in fuentes))
        self._mostrar_estados(transmision, grabacion, al_aire)
        self._anunciar_estados(transmision, grabacion, al_aire)

    def _mostrar_snap(self, snap):
        self._ultimo_snap = snap
        self.txt_estado.SetValue(obs_disposicion.describir_fuente(
            self._fuente(), snap, obs_disposicion.COMPONENTES, "largo"))
        anclaje = obs_disposicion.anclaje_de(
            (snap.izquierda, snap.arriba, snap.ancho, snap.alto),
            snap.lienzo_ancho, snap.lienzo_alto)
        self.cho_posicion.SetSelection(
            tuple(obs_disposicion.ANCLAJES).index(anclaje)
            if anclaje else wx.NOT_FOUND)
        if snap.ancho:
            self.sp_ancho.SetValue(snap.ancho)
        if snap.alto:
            self.sp_alto.SetValue(snap.alto)
        self.chk_mostrar.SetValue(snap.visible)
        self.chk_fijar.SetValue(snap.bloqueada)

    def _cargar_fuentes(self, fuentes, fuente=""):
        self.cho_fuente.Set(list(fuentes))
        if fuente:
            self.cho_fuente.SetStringSelection(fuente)
        if not fuentes:
            self.txt_estado.SetValue("La escena no tiene fuentes.")

    def _escena(self):
        return self.cho_escena.GetStringSelection()

    def _fuente(self):
        return self.cho_fuente.GetStringSelection()

    def _leer(self, escena=None):
        return self._gestor.instantanea(escena or self._escena(), fuente=self._fuente())

    def _guardar_restauracion(self, escena, fuente):
        clave = escena, fuente
        if not fuente or clave in self._restablecer:
            return
        snap = self._gestor.instantanea(escena, fuente=fuente)
        self._restablecer[clave] = {
            "transformacion": self._gestor.transformacion(escena, fuente=fuente),
            "ancho": snap.ancho, "alto": snap.alto, "visible": snap.visible,
            "bloqueada": snap.bloqueada,
        }

    def _anunciar_snap(self, snap):
        anunciar(obs_disposicion.describir_fuente(
            self._fuente(), snap, obs_disposicion.ACTIVOS_DEFECTO))

    def _actualizar_boton(self, boton, etiqueta, nombre):
        boton.SetLabel(etiqueta)
        boton.SetName(nombre)

    def _mostrar_estados(self, transmision, grabacion, al_aire):
        activa = bool(transmision.get("outputActive", False))
        self._actualizar_boton(
            self.btn_transmitir,
            "&Detener la transmision" if activa else "&Transmitir",
            "Detener la transmision" if activa else "Transmitir")
        grabando = bool(grabacion.get("outputActive", False))
        self._actualizar_boton(
            self.btn_grabar,
            "&Detener la grabacion" if grabando else "&Grabar",
            "Detener la grabacion" if grabando else "Grabar")
        self.btn_pausar_grabacion.Enable(grabando)
        self.txt_estado.AppendText(f"\n{self._frase_escena_al_aire(al_aire)}")

    @staticmethod
    def _frase_transmision(estado):
        return obs_estado.frase_transmision(
            estado.get("outputActive", False), estado.get("outputDuration", 0),
            estado.get("outputSkippedFrames", 0), estado.get("outputTotalFrames", 0))

    @staticmethod
    def _frase_grabacion(estado):
        return obs_estado.frase_grabacion(
            estado.get("outputActive", False), estado.get("outputPaused", False),
            estado.get("outputTimecode", ""))

    @staticmethod
    def _frase_escena_al_aire(escena):
        return obs_estado.frase_escena_al_aire(escena)

    def _anunciar_estados(self, transmision, grabacion, al_aire):
        anunciar(self._frase_transmision(transmision))
        anunciar(self._frase_grabacion(grabacion))
        anunciar(self._frase_escena_al_aire(al_aire))

    def _actualizar(self, event):
        self._en_hilo(self._leer_estados, self._estados_leidos)

    def _leer_estados(self):
        return (self._leer(), self._gestor.escena_al_aire(), self._gestor.estado_transmision(),
                self._gestor.estado_grabacion())

    def _estados_leidos(self, datos):
        snap, al_aire, transmision, grabacion = datos
        self._mostrar_snap(snap)
        self._mostrar_estados(transmision, grabacion, al_aire)
        self._anunciar_snap(snap)
        self._anunciar_estados(transmision, grabacion, al_aire)

    def _poner_al_aire(self, event):
        self._en_hilo(lambda: self._gestor.poner_escena_al_aire(self._escena()),
                      self._escena_puesta_al_aire)

    def _escena_puesta_al_aire(self, escena):
        anunciar(self._frase_escena_al_aire(escena))

    def _transmitir(self, event):
        self._en_hilo(self._gestor.alternar_transmision, self._transmision_alternada)

    def _transmision_alternada(self, activa):
        self._actualizar_boton(
            self.btn_transmitir,
            "&Detener la transmision" if activa else "&Transmitir",
            "Detener la transmision" if activa else "Transmitir")
        accion = "transmision_iniciada" if activa else "transmision_detenida"
        anunciar(obs_estado.frase_resultado(accion))

    def _grabar(self, event):
        self._en_hilo(self._gestor.alternar_grabacion, self._grabacion_alternada)

    def _grabacion_alternada(self, activa):
        self._actualizar_boton(
            self.btn_grabar,
            "&Detener la grabacion" if activa else "&Grabar",
            "Detener la grabacion" if activa else "Grabar")
        self.btn_pausar_grabacion.Enable(activa)
        accion = "grabacion_iniciada" if activa else "grabacion_detenida"
        anunciar(obs_estado.frase_resultado(accion))

    def _pausar_grabacion(self, event):
        self._en_hilo(self._gestor.alternar_pausa_grabacion,
                      self._pausa_grabacion_alternada)

    def _pausa_grabacion_alternada(self, en_pausa):
        accion = "grabacion_en_pausa" if en_pausa else "grabacion_reanudada"
        anunciar(obs_estado.frase_resultado(accion))

    def _preparar(self, event):
        self._en_hilo(self._preparar_panel, self._panel_preparado)

    def _preparar_panel(self):
        puerto = overlay_servidor.puerto_actual() or _PUERTO_PANEL_DEFECTO
        if not overlay_servidor.esta_encendido():
            try:
                overlay_servidor.encender(puerto)
            except overlay_servidor.OverlayPuertoOcupadoError:
                return f"No se pudo encender el panel, el puerto {puerto} está ocupado", (), None
        puerto = overlay_servidor.puerto_actual() or puerto
        escena = self._escena()
        fuentes = self._gestor.fuentes(escena)
        if NOMBRE_FUENTE not in fuentes:
            url = f"http://127.0.0.1:{puerto}{_RUTA_PANEL_CHAT}"
            self._gestor.asegurar_fuente(escena, url, self.sp_ancho.GetValue(), self.sp_alto.GetValue())
            fuentes = self._gestor.fuentes(escena)
        snap = self._gestor.instantanea(escena, fuente=NOMBRE_FUENTE)
        frase = obs_disposicion.describir_preparacion(
            snap.conectado, overlay_servidor.esta_encendido(), puerto,
            NOMBRE_FUENTE in fuentes)
        return frase, fuentes, snap

    def _panel_preparado(self, datos):
        frase, fuentes, snap = datos
        if snap is not None:
            self._cargar_fuentes(fuentes, NOMBRE_FUENTE)
            self._mostrar_snap(snap)
        anunciar(frase)

    def _cambiar_escena(self, event):
        if self._operacion_en_vuelo:
            return
        self._en_hilo(self._leer_escena, self._escena_cambiada)
        event.Skip()

    def _leer_escena(self):
        escena = self._escena()
        fuentes = self._gestor.fuentes(escena)
        fuente = NOMBRE_FUENTE if NOMBRE_FUENTE in fuentes else (fuentes[0] if fuentes else "")
        return fuentes, fuente, self._gestor.instantanea(escena, fuente=fuente)

    def _escena_cambiada(self, datos):
        fuentes, fuente, snap = datos
        self._cargar_fuentes(fuentes, fuente)
        if fuentes:
            self._mostrar_snap(snap)
            self._anunciar_snap(snap)

    def _cambiar_fuente(self, event):
        if self._operacion_en_vuelo:
            return
        self._en_hilo(self._leer, self._anunciar_snap)
        event.Skip()

    def _colocar(self, event):
        anclaje = tuple(obs_disposicion.ANCLAJES)[self.cho_posicion.GetSelection()]
        self._en_hilo(lambda: self._cambiar_y_leer(self._gestor.colocar, anclaje),
                      self._anunciar_snap)
        event.Skip()

    def _tamano(self, event):
        ancho, alto = self.sp_ancho.GetValue(), self.sp_alto.GetValue()
        self._en_hilo(lambda: self._aplicar_tamano(ancho, alto), self._tamano_aplicado)

    def _aplicar_tamano(self, ancho, alto):
        escena, fuente = self._escena(), self._fuente()
        self._guardar_restauracion(escena, fuente)
        if fuente == NOMBRE_FUENTE:
            self._gestor.redimensionar(escena, ancho, alto)
            return self._leer(), True
        if not self._gestor.escalar(escena, ancho, alto, fuente=fuente):
            return self._leer(), False
        return self._leer(), True

    def _tamano_aplicado(self, datos):
        snap, aplicado = datos
        self._mostrar_snap(snap)
        if aplicado:
            self._anunciar_snap(snap)
        else:
            anunciar(f"{self._fuente()} todavía no informa su tamaño.")

    def _mostrar(self, event):
        visible = self.chk_mostrar.GetValue()
        self._en_hilo(lambda: self._cambiar_y_leer(self._gestor.mostrar, visible),
                      self._anunciar_snap)
        event.Skip()

    def _fijar(self, event):
        fijada = self.chk_fijar.GetValue()
        self._en_hilo(lambda: self._cambiar_y_leer(self._gestor.fijar, fijada),
                      self._anunciar_snap)
        event.Skip()

    def _frente(self, event):
        self._en_hilo(lambda: self._cambiar_y_leer(self._gestor.al_frente), self._anunciar_snap)

    def _iniciar_ajuste(self, event):
        if self._ajuste_en_curso:
            return
        escena = self._escena()
        self._en_hilo(lambda: self._preparar_ajuste(escena), self._ajuste_iniciado)

    def _preparar_ajuste(self, escena):
        fuente = self._fuente()
        self._guardar_restauracion(escena, fuente)
        return self._gestor.transformacion(escena, fuente=fuente), self._leer(escena)

    def _ajuste_iniciado(self, datos):
        self._ajuste_transformacion, snap = datos
        self._ajuste_en_curso = True
        self.btn_ajuste.SetLabel(ajuste_fino.etiqueta_boton(True, self._etiqueta_ajuste))
        self._mostrar_snap(snap)
        anunciar(ajuste_fino.texto_de_entrada())
        self._anunciar_ajuste(snap)

    def _tecla_ajuste(self, event):
        if not self._ajuste_en_curso:
            event.Skip()
            return
        accion, dx, dy = ajuste_fino.resolver(
            event.GetKeyCode(), event.ControlDown(), event.ShiftDown())
        if accion == "mover":
            if not self._movimiento_en_vuelo:
                self._mover_ajuste(dx, dy)
            return
        if accion == "cancelar":
            self._salir_ajuste(False)
            return
        if accion in ("confirmar", "salir"):
            self._salir_ajuste(True)
            if accion == "salir":
                event.Skip()
            return

    def _mover_ajuste(self, dx, dy):
        self._movimiento_en_vuelo = True
        escena = self._escena()
        fuente = self._fuente()
        def mover():
            try:
                self._gestor.mover(escena, dx, dy, fuente=fuente)
                snap = self._leer(escena)
            except obs_cliente.ObsError as error:
                wx.CallAfter(self._movimiento_fallo, str(error))
            else:
                wx.CallAfter(self._movimiento_terminado, snap)
        threading.Thread(target=mover, daemon=True, name="AjusteFinoOBS").start()

    def _movimiento_terminado(self, snap):
        self._movimiento_en_vuelo = False
        if not self._ajuste_en_curso:
            return
        self._mostrar_snap(snap)
        self._anunciar_ajuste(snap)

    def _movimiento_fallo(self, mensaje):
        self._movimiento_en_vuelo = False
        if self._ajuste_en_curso:
            self._fallo(mensaje)

    def _anunciar_ajuste(self, snap):
        # Aquí la fuente no cambia y ya se anunció al entrar; los otros anuncios pueden cambiar de fuente y llevan nombre.
        anunciar(obs_disposicion.describir(
            snap, ("posicion", "solape", "fuera")), "ajuste")

    def _ajuste_perdio_foco(self, event):
        if self._ajuste_en_curso:
            self._salir_ajuste(True)
        event.Skip()

    def _salir_ajuste(self, confirmar):
        if not self._ajuste_en_curso:
            return
        self._ajuste_en_curso = False
        self.btn_ajuste.SetLabel(ajuste_fino.etiqueta_boton(False, self._etiqueta_ajuste))
        if confirmar:
            anunciar("Ajuste confirmado")
            return
        transformacion = self._ajuste_transformacion
        escena = self._escena()
        self._en_hilo(
            lambda: self._gestor.posicionar(
                escena, transformacion["positionX"],
                transformacion["positionY"], transformacion["alignment"], fuente=self._fuente()),
            lambda resultado: anunciar("Ajuste deshecho"))

    def _cambiar_y_leer(self, funcion, *argumentos):
        escena, fuente = self._escena(), self._fuente()
        self._guardar_restauracion(escena, fuente)
        funcion(escena, *argumentos, fuente=fuente)
        return self._leer()

    def _captura(self, event):
        with wx.FileDialog(self, "Guardar una captura de la escena", wildcard="Imagen PNG (*.png)|*.png",
                           defaultFile="captura-escena.png", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            ruta = dialogo.GetPath()
        self._en_hilo(lambda: self._guardar_captura(ruta), lambda resultado: anunciar("Captura guardada"))

    def _guardar_captura(self, ruta):
        self._gestor.captura_de_escena(self._escena(), ruta)
        return self._leer()

    def _lienzo(self, event):
        wx.MessageBox(_TEXTO_LIENZO, "Qué es el lienzo", wx.OK | wx.ICON_INFORMATION, self)

    def _restaurar(self, event):
        self._en_hilo(self._aplicar_restauracion, lambda snap: anunciar("Restablecido"))

    def _aplicar_restauracion(self):
        for (escena, fuente), datos in self._restablecer.items():
            transformacion = datos["transformacion"]
            if transformacion:
                self._gestor.posicionar(escena, transformacion["positionX"],
                                        transformacion["positionY"], transformacion["alignment"],
                                        fuente=fuente)
            if fuente == NOMBRE_FUENTE:
                self._gestor.redimensionar(escena, datos["ancho"], datos["alto"])
            else:
                self._gestor.escalar(escena, datos["ancho"], datos["alto"], fuente=fuente)
            self._gestor.mostrar(escena, datos["visible"], fuente=fuente)
            self._gestor.fijar(escena, datos["bloqueada"], fuente=fuente)
        return self._leer()

    def _cerrar(self, event):
        if self._cerrando:
            return
        self._cerrando = True
        self._temporizador_consulta.Stop()
        threading.Thread(target=self._cerrar_gestor, daemon=True,
                         name="CerrarTransmisionOBS").start()
        self.EndModal(wx.ID_CANCEL)

    def _cerrar_gestor(self):
        try:
            self._gestor.cerrar()
        except Exception:
            pass


def abrir_transmision(parent) -> None:
    dialogo = TransmisionDialog(parent)
    try:
        dialogo.ShowModal()
    finally:
        dialogo.Destroy()
