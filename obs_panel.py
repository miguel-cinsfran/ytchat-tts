"""Orquestación del panel de chat dentro de una escena de OBS."""

from __future__ import annotations

import obs_disposicion
import obs_cliente


NOMBRE_FUENTE = "Chat YTChat"
TIPO_FUENTE = "browser_source"


class GestorPanelObs:
    def __init__(self, cliente=None, ajustes=None):
        if cliente is None:
            if ajustes is None:
                ajustes = obs_cliente.leer_ajustes()
            cliente = obs_cliente.ClienteObs(ajustes)
        self._cliente = cliente

    def conectar(self, parada=None) -> None:
        self._cliente.conectar(parada)

    def cerrar(self) -> None:
        self._cliente.cerrar()

    @property
    def conectado(self) -> bool:
        return self._cliente.conectado

    def _pedir(self, tipo, datos=None, parada=None):
        respuesta = self._cliente.pedir(tipo, datos, parada)
        return respuesta.get("responseData", {})

    def escenas(self, parada=None) -> tuple:
        datos = self._pedir("GetSceneList", parada=parada)
        return tuple(escena["sceneName"] for escena in datos.get("scenes", ()))

    def escena_al_aire(self, parada=None) -> str:
        datos = self._pedir("GetCurrentProgramScene", parada=parada)
        return datos.get("currentProgramSceneName", "")

    def _elementos(self, escena, parada=None):
        datos = self._pedir("GetSceneItemList", {"sceneName": escena}, parada)
        return list(datos.get("sceneItems", ()))

    def _elemento_panel(self, escena, parada=None):
        return next((elemento for elemento in self._elementos(escena, parada)
                     if elemento.get("sourceName") == NOMBRE_FUENTE), None)

    def asegurar_fuente(self, escena, url, ancho, alto, parada=None) -> int:
        elemento = self._elemento_panel(escena, parada)
        if elemento is not None:
            identificador = elemento["sceneItemId"]
        else:
            entradas = self._pedir("GetInputList", parada=parada).get("inputs", ())
            existe = any(entrada.get("inputName") == NOMBRE_FUENTE
                         for entrada in entradas)
            if existe:
                datos = self._pedir(
                    "CreateSceneItem", {"sceneName": escena,
                                        "sourceName": NOMBRE_FUENTE}, parada)
            else:
                datos = self._pedir(
                    "CreateInput", {"sceneName": escena,
                                    "inputName": NOMBRE_FUENTE,
                                    "inputKind": TIPO_FUENTE}, parada)
            identificador = datos.get("sceneItemId")
            elemento = self._elemento_panel(escena, parada)
            if elemento is not None:
                identificador = elemento["sceneItemId"]

        self._pedir("SetInputSettings", {
            "inputName": NOMBRE_FUENTE,
            "inputSettings": {"url": url, "width": ancho, "height": alto},
        }, parada)
        self._pedir("PressInputPropertiesButton", {
            "inputName": NOMBRE_FUENTE,
            "propertyName": "refreshnocache",
        }, parada)
        self.al_frente(escena, parada)
        elemento = self._elemento_panel(escena, parada)
        return elemento["sceneItemId"] if elemento is not None else identificador

    def colocar(self, escena, anclaje, parada=None) -> None:
        elemento = self._elemento_panel(escena, parada)
        lienzo = self._pedir("GetVideoSettings", parada=parada)
        x, y, alineacion = obs_disposicion.coordenadas(
            anclaje, lienzo["baseWidth"], lienzo["baseHeight"])
        # OBS devuelve boundsWidth y boundsHeight en cero con OBS_BOUNDS_NONE,
        # pero rechaza esos valores al recibir de nuevo la transformación.
        transformacion = {"positionX": x, "positionY": y,
                          "alignment": alineacion}
        self._pedir("SetSceneItemTransform", {
            "sceneName": escena, "sceneItemId": elemento["sceneItemId"],
            "sceneItemTransform": transformacion,
        }, parada)
        self._elemento_panel(escena, parada)

    def mover(self, escena, dx, dy, parada=None) -> None:
        elemento = self._elemento_panel(escena, parada)
        transformacion_actual = elemento["sceneItemTransform"]
        transformacion = {
            "positionX": transformacion_actual["positionX"] + dx,
            "positionY": transformacion_actual["positionY"] + dy,
        }
        self._pedir("SetSceneItemTransform", {
            "sceneName": escena, "sceneItemId": elemento["sceneItemId"],
            "sceneItemTransform": transformacion,
        }, parada)
        self._elemento_panel(escena, parada)

    def redimensionar(self, escena, ancho, alto, parada=None) -> None:
        self._elemento_panel(escena, parada)
        ajustes = self._pedir("GetInputSettings", {
            "inputName": NOMBRE_FUENTE,
        }, parada).get("inputSettings", {})
        ajustes = dict(ajustes)
        ajustes.update(width=ancho, height=alto)
        self._pedir("SetInputSettings", {
            "inputName": NOMBRE_FUENTE, "inputSettings": ajustes,
        }, parada)
        self._elemento_panel(escena, parada)

    def mostrar(self, escena, visible, parada=None) -> None:
        elemento = self._elemento_panel(escena, parada)
        self._pedir("SetSceneItemEnabled", {
            "sceneName": escena, "sceneItemId": elemento["sceneItemId"],
            "sceneItemEnabled": visible,
        }, parada)
        self._elemento_panel(escena, parada)

    def fijar(self, escena, fijada, parada=None) -> None:
        elemento = self._elemento_panel(escena, parada)
        self._pedir("SetSceneItemLocked", {
            "sceneName": escena, "sceneItemId": elemento["sceneItemId"],
            "sceneItemLocked": fijada,
        }, parada)
        self._elemento_panel(escena, parada)

    def al_frente(self, escena, parada=None) -> None:
        elementos = self._elementos(escena, parada)
        panel = next((elemento for elemento in elementos
                      if elemento.get("sourceName") == NOMBRE_FUENTE), None)
        if panel is None:
            return
        indice_mayor = max((elemento.get("sceneItemIndex", 0) for elemento in elementos),
                           default=0)
        if panel.get("sceneItemIndex", 0) == indice_mayor:
            return
        self._pedir("SetSceneItemIndex", {
            "sceneName": escena, "sceneItemId": panel["sceneItemId"],
            "sceneItemIndex": indice_mayor,
        }, parada)
        self._elementos(escena, parada)

    def instantanea(self, escena, parada=None) -> obs_disposicion.SnapshotPanel:
        elementos = self._elementos(escena, parada)
        panel = next((elemento for elemento in elementos
                      if elemento.get("sourceName") == NOMBRE_FUENTE), None)
        al_aire = self.escena_al_aire(parada) == escena
        lienzo = self._pedir("GetVideoSettings", parada=parada)
        conectado = self.conectado
        if panel is None:
            return obs_disposicion.SnapshotPanel(
                conectado=conectado, escena=escena, al_aire=al_aire,
                lienzo_ancho=lienzo.get("baseWidth", 0),
                lienzo_alto=lienzo.get("baseHeight", 0))

        transformacion = panel["sceneItemTransform"]
        rect_panel = obs_disposicion.rectangulo(
            transformacion.get("positionX", 0), transformacion.get("positionY", 0),
            transformacion.get("width", 0), transformacion.get("height", 0),
            transformacion.get("alignment", 0))
        solapes = []
        delante = []
        for elemento in elementos:
            if elemento["sceneItemId"] == panel["sceneItemId"]:
                continue
            transformacion_otro = elemento["sceneItemTransform"]
            rect_otro = obs_disposicion.rectangulo(
                transformacion_otro.get("positionX", 0),
                transformacion_otro.get("positionY", 0),
                transformacion_otro.get("width", 0),
                transformacion_otro.get("height", 0),
                transformacion_otro.get("alignment", 0))
            porcentaje = obs_disposicion.solape(rect_otro, rect_panel)
            if porcentaje:
                solapes.append((elemento.get("sourceName", ""), porcentaje))
                if elemento.get("sceneItemIndex", 0) > panel.get("sceneItemIndex", 0):
                    delante.append((elemento.get("sceneItemIndex", 0),
                                    elemento.get("sourceName", "")))
        solapes.sort(key=lambda pareja: pareja[1], reverse=True)
        tapada_por = max(delante, default=(0, ""))[1]
        visible = panel.get("sceneItemEnabled", True)
        bloqueada = panel.get("sceneItemLocked", False)
        return obs_disposicion.SnapshotPanel(
            conectado=conectado, escena=escena, al_aire=al_aire,
            izquierda=rect_panel[0], arriba=rect_panel[1], ancho=int(rect_panel[2]),
            alto=int(rect_panel[3]), lienzo_ancho=lienzo.get("baseWidth", 0),
            lienzo_alto=lienzo.get("baseHeight", 0), visible=visible,
            bloqueada=bloqueada, tapada_por=tapada_por, solapes=tuple(solapes),
            fuera=obs_disposicion.fuera_del_lienzo(
                rect_panel, lienzo.get("baseWidth", 0), lienzo.get("baseHeight", 0)))

    def captura_de_escena(self, escena, ruta, parada=None) -> None:
        self._pedir("SaveSourceScreenshot", {
            "sourceName": escena, "imageFormat": "png", "imageFilePath": ruta,
        }, parada)
