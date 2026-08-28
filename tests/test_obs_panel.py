import unittest
from unittest import mock

import obs_panel


def elemento(identificador, nombre, indice, x=32, y=882, ancho=460, alto=620,
             alineacion=9, visible=True, bloqueada=False, ancho_fuente=460,
             alto_fuente=620):
    return {"sceneItemId": identificador, "sourceName": nombre,
            "sceneItemIndex": indice, "sceneItemEnabled": visible,
            "sceneItemLocked": bloqueada,
            "sceneItemTransform": {"positionX": x, "positionY": y,
                                   "width": ancho, "height": alto,
                                   "alignment": alineacion,
                                   "sourceWidth": ancho_fuente,
                                   "sourceHeight": alto_fuente,
                                   "boundsWidth": 0.0, "boundsHeight": 0.0}}


class DobleObs:
    def __init__(self, elementos=None, entradas=(), escena="Escena", escenas=None,
                 silencios=None):
        self.elementos = list(elementos or ())
        self.entradas = list(entradas)
        self.escena = escena
        self.escenas = tuple(escenas if escenas is not None else (escena,))
        self.llamadas = []
        self.conectado = True
        self.siguiente_id = 20
        self.silencios = dict(silencios or {})

    def conectar(self, parada=None):
        self.conectado = True

    def cerrar(self):
        self.conectado = False

    def pedir(self, tipo, datos=None, parada=None):
        datos = datos or {}
        self.llamadas.append((tipo, datos, parada))
        if tipo == "GetSceneItemList":
            return {"responseData": {"sceneItems": list(self.elementos)}}
        if tipo == "GetSceneList":
            return {"responseData": {"scenes": [
                {"sceneName": escena} for escena in self.escenas]}}
        if tipo == "GetInputList":
            return {"responseData": {"inputs": list(self.entradas)}}
        if tipo == "GetInputMute":
            nombre = datos["inputName"]
            if nombre not in self.silencios:
                raise RuntimeError("No es una fuente de audio")
            return {"responseData": {"inputMuted": self.silencios[nombre]}}
        if tipo == "ToggleInputMute":
            nombre = datos["inputName"]
            if nombre not in self.silencios:
                raise RuntimeError("No es una fuente de audio")
            self.silencios[nombre] = not self.silencios[nombre]
            return {"responseData": {"inputMuted": self.silencios[nombre]}}
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

    @mock.patch("obs_panel.obs_cliente.leer_ajustes")
    def test_sin_argumentos_lee_los_ajustes_de_obs(self, leer_ajustes):
        ajustes = object()
        leer_ajustes.return_value = ajustes
        with mock.patch("obs_panel.obs_cliente.ClienteObs") as cliente_obs:
            gestor = obs_panel.GestorPanelObs()
        leer_ajustes.assert_called_once_with()
        cliente_obs.assert_called_once_with(ajustes)
        self.assertIs(gestor._cliente, cliente_obs.return_value)

    @mock.patch("obs_panel.obs_cliente.leer_ajustes")
    def test_con_cliente_no_lee_los_ajustes_de_obs(self, leer_ajustes):
        cliente = object()
        gestor = obs_panel.GestorPanelObs(cliente=cliente)
        leer_ajustes.assert_not_called()
        self.assertIs(gestor._cliente, cliente)

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

    def test_fuentes_ordena_del_frente_hacia_atras(self):
        doble = DobleObs([elemento(1, "Juego", 3), elemento(2, "Cámara", 8),
                          elemento(3, obs_panel.NOMBRE_FUENTE, 5)])
        self.assertEqual(self.gestor(doble).fuentes("Escena"),
                         ("Cámara", "Chat YTChat", "Juego"))

    def test_fuentes_devuelve_vacio_sin_fuentes_o_escena(self):
        self.assertEqual(self.gestor(DobleObs([])).fuentes("Escena"), ())
        self.assertEqual(self.gestor(DobleObs(escenas=())).fuentes("Ausente"), ())

    def test_fuentes_audio_descarta_las_que_obs_no_puede_silenciar(self):
        doble = DobleObs(
            entradas=({"inputName": "Mic/Aux"}, {"inputName": "Cámara"}),
            silencios={"Mic/Aux": False})
        self.assertEqual(self.gestor(doble).fuentes_audio(), ("Mic/Aux",))

    def test_consulta_el_silencio_de_una_fuente_de_audio(self):
        gestor = self.gestor(DobleObs(silencios={"Mic/Aux": True}))
        self.assertTrue(gestor.silenciada("Mic/Aux"))

    def test_alterna_el_silencio_y_devuelve_el_estado_resultante(self):
        doble = DobleObs(silencios={"Mic/Aux": False})
        self.assertTrue(self.gestor(doble).alternar_silencio("Mic/Aux"))
        self.assertTrue(doble.silencios["Mic/Aux"])

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

    def test_colocar_manda_solo_las_claves_de_posicion_y_alineacion(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0)])
        self.gestor(doble).colocar("Escena", "superior-izquierda")
        llamada = next(llamada for llamada in doble.llamadas
                       if llamada[0] == "SetSceneItemTransform")
        self.assertEqual(set(llamada[1]["sceneItemTransform"]),
                         {"positionX", "positionY", "alignment"})

    def test_colocar_manda_la_posicion_calculada(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0)])
        self.gestor(doble).colocar("Escena", "superior-izquierda")
        llamada = next(llamada for llamada in doble.llamadas
                       if llamada[0] == "SetSceneItemTransform")
        self.assertEqual(llamada[1]["sceneItemTransform"],
                         {"positionX": 32.0, "positionY": 18.0, "alignment": 5})

    def test_transformacion_devuelve_solo_posicion_y_alineacion(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0, x=40, y=50)])
        transformacion = self.gestor(doble).transformacion("Escena")
        self.assertEqual(set(transformacion),
                         {"positionX", "positionY", "alignment"})
        self.assertEqual(transformacion,
                         {"positionX": 40, "positionY": 50, "alignment": 9})

    def test_transformacion_devuelve_vacio_si_no_hay_panel(self):
        doble = DobleObs([])
        self.assertEqual(self.gestor(doble).transformacion("Escena"), {})

    def test_posicionar_manda_la_posicion_y_alineacion_recibidas(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0)])
        self.gestor(doble).posicionar("Escena", 123.5, 456.25, 7)
        llamada = next(llamada for llamada in doble.llamadas
                       if llamada[0] == "SetSceneItemTransform")
        self.assertEqual(llamada[1]["sceneItemTransform"],
                         {"positionX": 123.5, "positionY": 456.25,
                          "alignment": 7})

    def test_mover_manda_solo_las_claves_de_posicion(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0)])
        self.gestor(doble).mover("Escena", 7, -3)
        llamada = next(llamada for llamada in doble.llamadas
                       if llamada[0] == "SetSceneItemTransform")
        self.assertEqual(set(llamada[1]["sceneItemTransform"]),
                         {"positionX", "positionY"})

    def test_mover_manda_la_posicion_desplazada(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0)])
        self.gestor(doble).mover("Escena", 7, -3)
        llamada = next(llamada for llamada in doble.llamadas
                       if llamada[0] == "SetSceneItemTransform")
        self.assertEqual(llamada[1]["sceneItemTransform"],
                         {"positionX": 39, "positionY": 879})

    def test_instantanea_no_guarda_estado(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0)])
        gestor = self.gestor(doble)
        primera = gestor.instantanea("Escena")
        doble.elementos[0]["sceneItemTransform"]["positionX"] = 300
        segunda = gestor.instantanea("Escena")
        self.assertNotEqual(primera.izquierda, segunda.izquierda)

    def test_metodos_con_fuente_operan_sobre_el_elemento_nombrado(self):
        operaciones = (
            ("colocar", ("Escena", "superior-izquierda"), "SetSceneItemTransform"),
            ("posicionar", ("Escena", 10, 20, 5), "SetSceneItemTransform"),
            ("mover", ("Escena", 10, 20), "SetSceneItemTransform"),
            ("mostrar", ("Escena", False), "SetSceneItemEnabled"),
            ("fijar", ("Escena", True), "SetSceneItemLocked"),
            ("al_frente", ("Escena",), "SetSceneItemIndex"),
        )
        for metodo, argumentos, solicitud in operaciones:
            with self.subTest(metodo=metodo):
                doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 1),
                                  elemento(2, "Cámara", 0)])
                getattr(self.gestor(doble), metodo)(*argumentos, fuente="Cámara")
                llamada = next(llamada for llamada in doble.llamadas
                               if llamada[0] == solicitud)
                self.assertEqual(llamada[1]["sceneItemId"], 2)

    def test_lecturas_con_fuente_leen_el_elemento_nombrado(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0, x=10),
                          elemento(2, "Cámara", 1, x=300, ancho=640, alto=480)])
        self.assertEqual(self.gestor(doble).transformacion("Escena", fuente="Cámara")["positionX"], 300)
        self.assertEqual(self.gestor(doble).instantanea("Escena", fuente="Cámara").ancho, 640)

    def test_sin_fuente_sigue_operando_sobre_el_panel(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0),
                          elemento(2, "Cámara", 1)])
        self.gestor(doble).mostrar("Escena", False)
        llamada = next(llamada for llamada in doble.llamadas
                       if llamada[0] == "SetSceneItemEnabled")
        self.assertEqual(llamada[1]["sceneItemId"], 1)

    def test_escalar_manda_solo_las_escalas_de_la_fuente_nombrada(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0),
                          elemento(2, "Cámara", 1, ancho_fuente=1280,
                                   alto_fuente=720)])
        self.assertTrue(self.gestor(doble).escalar("Escena", 640, 360,
                                                   fuente="Cámara"))
        llamada = next(llamada for llamada in doble.llamadas
                       if llamada[0] == "SetSceneItemTransform")
        self.assertEqual(llamada[1]["sceneItemId"], 2)
        self.assertEqual(llamada[1]["sceneItemTransform"],
                         {"scaleX": 0.5, "scaleY": 0.5})

    def test_escalar_no_manda_nada_si_la_fuente_no_tiene_tamano(self):
        doble = DobleObs([elemento(1, obs_panel.NOMBRE_FUENTE, 0,
                                  ancho_fuente=0)])
        self.assertFalse(self.gestor(doble).escalar("Escena", 640, 360))
        self.assertNotIn("SetSceneItemTransform",
                         [llamada[0] for llamada in doble.llamadas])


if __name__ == "__main__":
    unittest.main()
