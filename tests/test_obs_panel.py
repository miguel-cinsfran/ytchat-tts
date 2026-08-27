import unittest

import obs_panel


def elemento(identificador, nombre, indice, x=32, y=882, ancho=460, alto=620,
             alineacion=9, visible=True, bloqueada=False):
    return {"sceneItemId": identificador, "sourceName": nombre,
            "sceneItemIndex": indice, "sceneItemEnabled": visible,
            "sceneItemLocked": bloqueada,
            "sceneItemTransform": {"positionX": x, "positionY": y,
                                   "width": ancho, "height": alto,
                                   "alignment": alineacion}}


class DobleObs:
    def __init__(self, elementos=None, entradas=(), escena="Escena"):
        self.elementos = list(elementos or ())
        self.entradas = list(entradas)
        self.escena = escena
        self.llamadas = []
        self.conectado = True
        self.siguiente_id = 20

    def conectar(self, parada=None):
        self.conectado = True

    def cerrar(self):
        self.conectado = False

    def pedir(self, tipo, datos=None, parada=None):
        datos = datos or {}
        self.llamadas.append((tipo, datos, parada))
        if tipo == "GetSceneItemList":
            return {"responseData": {"sceneItems": list(self.elementos)}}
        if tipo == "GetInputList":
            return {"responseData": {"inputs": list(self.entradas)}}
        if tipo == "GetCurrentProgramScene":
            return {"responseData": {"currentProgramSceneName": self.escena}}
        if tipo == "GetVideoSettings":
            return {"responseData": {"baseWidth": 1600, "baseHeight": 900}}
        if tipo in ("CreateSceneItem", "CreateInput"):
            self.siguiente_id += 1
            nuevo = elemento(self.siguiente_id, obs_panel.NOMBRE_FUENTE, 0)
            self.elementos.append(nuevo)
            return {"responseData": {"sceneItemId": self.siguiente_id}}
        if tipo == "SetSceneItemIndex":
            identificador = datos["sceneItemId"]
            nuevo_indice = datos["sceneItemIndex"]
            for item in self.elementos:
                if item["sceneItemId"] == identificador:
                    item["sceneItemIndex"] = nuevo_indice
            return {"responseData": {}}
        if tipo == "SetSceneItemTransform":
            for item in self.elementos:
                if item["sceneItemId"] == datos["sceneItemId"]:
                    item["sceneItemTransform"] = datos["sceneItemTransform"]
        if tipo == "SetSceneItemEnabled":
            for item in self.elementos:
                if item["sceneItemId"] == datos["sceneItemId"]:
                    item["sceneItemEnabled"] = datos["sceneItemEnabled"]
        if tipo == "SetSceneItemLocked":
            for item in self.elementos:
                if item["sceneItemId"] == datos["sceneItemId"]:
                    item["sceneItemLocked"] = datos["sceneItemLocked"]
        return {"responseData": {}}


class GestorPanelObsTest(unittest.TestCase):
    def gestor(self, doble):
        return obs_panel.GestorPanelObs(doble)

    def test_asegura_adoptando_elemento_de_la_escena(self):
        doble = DobleObs([elemento(3, obs_panel.NOMBRE_FUENTE, 1)])
        identificador = self.gestor(doble).asegurar_fuente("Escena", "http://x", 460, 620)
        self.assertEqual(identificador, 3)
        self.assertNotIn("CreateInput", [llamada[0] for llamada in doble.llamadas])

    def test_asegura_agregando_fuente_existente(self):
        doble = DobleObs(entradas=[{"inputName": obs_panel.NOMBRE_FUENTE}])
        self.assertEqual(self.gestor(doble).asegurar_fuente("Escena", "u", 1, 2), 21)
        self.assertIn("CreateSceneItem", [llamada[0] for llamada in doble.llamadas])

    def test_asegura_creando_fuente_nueva(self):
        doble = DobleObs()
        self.assertEqual(self.gestor(doble).asegurar_fuente("Escena", "u", 1, 2), 21)
        llamada = next(llamada for llamada in doble.llamadas if llamada[0] == "CreateInput")
        self.assertEqual(llamada[1]["inputKind"], "browser_source")

    def test_al_frente_no_manda_si_ya_esta_arriba(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 2), elemento(2, "Juego", 1)])
        self.gestor(doble).al_frente("Escena")
        self.assertNotIn("SetSceneItemIndex", [llamada[0] for llamada in doble.llamadas])

    def test_al_frente_sube_al_indice_mayor(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0), elemento(2, "Juego", 4)])
        self.gestor(doble).al_frente("Escena")
        llamada = next(llamada for llamada in doble.llamadas if llamada[0] == "SetSceneItemIndex")
        self.assertEqual(llamada[1]["sceneItemIndex"], 4)

    def test_instantanea_sin_solapes(self):
        snap = self.gestor(DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0)])).instantanea("Escena")
        self.assertEqual(snap.solapes, ())

    def test_instantanea_con_un_solape(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0, x=0),
                          elemento(2, "Barra", 1, x=0, y=882, ancho=230)])
        self.assertEqual(self.gestor(doble).instantanea("Escena").solapes, (("Barra", 50.0),))

    def test_instantanea_ordena_dos_solapes(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0, x=0),
                          elemento(2, "Mitad", 1, x=0, y=882, ancho=230),
                          elemento(3, "Todo", 2, x=0, y=0, ancho=1600, alto=900, alineacion=5)])
        self.assertEqual(tuple(nombre for nombre, _ in self.gestor(doble).instantanea("Escena").solapes),
                         ("Todo", "Mitad"))

    def test_instantanea_identifica_fuente_delante_que_solapa(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0),
                          elemento(2, "Tapa", 3, x=0, y=0, ancho=1600, alto=900, alineacion=5)])
        self.assertEqual(self.gestor(doble).instantanea("Escena").tapada_por, "Tapa")

    def test_instantanea_ignora_fuente_delante_sin_solape(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0),
                          elemento(2, "Lejos", 3, x=1000, y=0, ancho=100, alto=100, alineacion=5)])
        self.assertEqual(self.gestor(doble).instantanea("Escena").tapada_por, "")

    def test_mover_suma_a_la_posicion_leida(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0, x=40, y=50)])
        self.gestor(doble).mover("Escena", 7, -3)
        transformacion = doble.elementos[0]["sceneItemTransform"]
        self.assertEqual((transformacion["positionX"], transformacion["positionY"]), (47, 47))

    def test_instantanea_no_guarda_estado(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0)])
        gestor = self.gestor(doble)
        primera = gestor.instantanea("Escena")
        doble.elementos[0]["sceneItemTransform"]["positionX"] = 300
        segunda = gestor.instantanea("Escena")
        self.assertNotEqual(primera.izquierda, segunda.izquierda)


if __name__ == "__main__":
    unittest.main()
