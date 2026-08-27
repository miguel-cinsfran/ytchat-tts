import base64
import hashlib
import json
import os
import tempfile
import threading
import unittest

import obs_cliente


class AjustesObsTest(unittest.TestCase):
    def test_lee_configuracion(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                         encoding="utf-8") as archivo:
            json.dump({"server_enabled": True, "server_port": 4456,
                       "server_password": "secreto"}, archivo)
            ruta = archivo.name
        try:
            self.assertEqual(obs_cliente.leer_ajustes(ruta),
                             obs_cliente.AjustesObs(True, 4456, "secreto"))
        finally:
            os.unlink(ruta)

    def test_usa_valores_por_defecto_ausentes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                         encoding="utf-8") as archivo:
            archivo.write("{}")
            ruta = archivo.name
        try:
            self.assertEqual(obs_cliente.leer_ajustes(ruta), obs_cliente.AjustesObs())
        finally:
            os.unlink(ruta)

    def test_archivo_inexistente_no_revienta(self):
        self.assertEqual(obs_cliente.leer_ajustes("ruta-que-no-existe.json"),
                         obs_cliente.AjustesObs())

    def test_archivo_invalido_no_revienta(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                         encoding="utf-8") as archivo:
            archivo.write("no es json")
            ruta = archivo.name
        try:
            self.assertEqual(obs_cliente.leer_ajustes(ruta), obs_cliente.AjustesObs())
        finally:
            os.unlink(ruta)


class AutenticacionTest(unittest.TestCase):
    def test_respuesta_auth_hace_las_dos_pasadas(self):
        password, salt, challenge = "clave", "sal", "desafio"
        intermedio = base64.b64encode(
            hashlib.sha256((password + salt).encode()).digest()
        ).decode()
        esperado = base64.b64encode(
            hashlib.sha256((intermedio + challenge).encode()).digest()
        ).decode()
        self.assertEqual(obs_cliente.respuesta_auth(password, salt, challenge), esperado)

    def test_respuesta_auth_acepta_textos_vacios(self):
        resultado = obs_cliente.respuesta_auth("", "", "")
        self.assertIsInstance(resultado, str)
        self.assertEqual(len(resultado), 44)


class MensajesDeFalloTest(unittest.TestCase):
    def test_fallo_de_conexion(self):
        self.assertIn("No se pudo conectar", obs_cliente.mensaje_de_fallo_obs("Connection refused"))

    def test_fallo_de_autenticacion(self):
        self.assertEqual(obs_cliente.mensaje_de_fallo_obs("error 4009 unauthorized"),
                         "OBS rechazó la contraseña guardada. Vuelve a conectar para leerla de nuevo.")

    def test_fuente_duplicada(self):
        self.assertEqual(obs_cliente.mensaje_de_fallo_obs("601"),
                         "Ya existe una fuente con ese nombre en OBS.")

    def test_escena_o_fuente_inexistente(self):
        self.assertEqual(obs_cliente.mensaje_de_fallo_obs("No scene"),
                         "OBS no encuentra la escena o la fuente indicada.")

    def test_fallo_desconocido(self):
        self.assertEqual(obs_cliente.mensaje_de_fallo_obs("fallo extraño"),
                         "OBS no pudo completar la operación. Inténtalo de nuevo.")

    def test_motivo_vacio(self):
        self.assertEqual(obs_cliente.mensaje_de_fallo_obs(None),
                         "OBS no pudo completar la operación. Inténtalo de nuevo.")


class TransporteDoble:
    def __init__(self, mensajes):
        self.mensajes = list(mensajes)
        self.enviados = []
        self.cerrado = False

    def send(self, mensaje):
        datos = json.loads(mensaje)
        self.enviados.append(datos)
        if datos.get("op") == 6:
            self.mensajes.append(json.dumps({
                "op": 7,
                "d": {
                    "requestId": datos["d"]["requestId"],
                    "requestStatus": {"result": True},
                    "responseData": {"ok": True},
                },
            }))

    def recv(self, timeout=None):
        if not self.mensajes:
            raise TimeoutError()
        return self.mensajes.pop(0)

    def close(self):
        self.cerrado = True


class TransporteSinRespuesta(TransporteDoble):
    def send(self, mensaje):
        self.enviados.append(json.loads(mensaje))


class ClienteObsTest(unittest.TestCase):
    def cliente(self, transporte, password=""):
        return obs_cliente.ClienteObs(
            obs_cliente.AjustesObs(True, 4455, password),
            lambda uri: transporte,
        )

    def test_conectar_sin_autenticacion(self):
        transporte = TransporteDoble([
            json.dumps({"op": 0, "d": {"rpcVersion": 1}}),
            json.dumps({"op": 2, "d": {}}),
        ])
        cliente = self.cliente(transporte)
        cliente.conectar()
        self.assertTrue(cliente.conectado)
        self.assertEqual(transporte.enviados[0], {"op": 1, "d": {"rpcVersion": 1}})

    def test_conectar_con_autenticacion(self):
        transporte = TransporteDoble([
            json.dumps({"op": 0, "d": {"rpcVersion": 1,
                                         "authentication": {"salt": "sal",
                                                             "challenge": "reto"}}}),
            json.dumps({"op": 2, "d": {}}),
        ])
        cliente = self.cliente(transporte, "clave")
        cliente.conectar()
        enviado = transporte.enviados[0]["d"]
        self.assertEqual(enviado["rpcVersion"], 1)
        self.assertEqual(enviado["authentication"],
                         obs_cliente.respuesta_auth("clave", "sal", "reto"))

    def test_salta_eventos_y_devuelve_respuesta(self):
        transporte = TransporteDoble([
            json.dumps({"op": 5, "d": {"eventType": "CurrentProgramSceneChanged"}}),
            json.dumps({"op": 7, "d": {"requestId": "otro",
                                         "requestStatus": {"result": True}}}),
        ])
        cliente = self.cliente(transporte)
        cliente._transporte = transporte
        resultado = cliente.pedir("GetVersion", {"campo": 1})
        self.assertEqual(resultado["responseData"], {"ok": True})
        pedido = transporte.enviados[0]
        self.assertEqual(pedido["d"]["requestType"], "GetVersion")
        self.assertEqual(pedido["d"]["requestData"], {"campo": 1})

    def test_cerrar_libera_el_transporte(self):
        transporte = TransporteDoble([])
        cliente = self.cliente(transporte)
        cliente._transporte = transporte
        cliente.cerrar()
        self.assertFalse(cliente.conectado)
        self.assertTrue(transporte.cerrado)

    def test_pedir_traduce_error_de_obs(self):
        transporte = TransporteDoble([])
        cliente = self.cliente(transporte)
        cliente._transporte = transporte
        transporte.recv = lambda timeout=None: json.dumps({
            "op": 7,
            "d": {"requestId": transporte.enviados[0]["d"]["requestId"],
                  "requestStatus": {"result": False, "code": 601,
                                     "comment": "A source already exists"}},
        })
        with self.assertRaisesRegex(obs_cliente.ObsError,
                                    "Ya existe una fuente"):
            cliente.pedir("CreateInput")

    def test_pedir_sin_conexion_falla(self):
        with self.assertRaisesRegex(obs_cliente.ObsError, "no pudo completar"):
            self.cliente(TransporteDoble([])).pedir("GetVersion")


class CancelacionYTiempoTest(unittest.TestCase):
    def cliente_sin_respuesta(self):
        transporte = TransporteSinRespuesta([])
        cliente = obs_cliente.ClienteObs(
            obs_cliente.AjustesObs(True, 4455, ""), lambda uri: transporte
        )
        cliente._transporte = transporte
        return cliente

    def test_pedir_se_cancela_mientras_recv_espera(self):
        cliente = self.cliente_sin_respuesta()
        parada = threading.Event()
        resultado = []

        def ejecutar():
            try:
                cliente.pedir("GetVersion", parada=parada)
            except obs_cliente.ObsError as error:
                resultado.append(str(error))

        hilo = threading.Thread(target=ejecutar)
        hilo.start()
        parada.set()
        hilo.join(1.5)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(resultado, ["Operación cancelada."])

    def test_pedir_respeta_el_tiempo_total(self):
        cliente = self.cliente_sin_respuesta()
        original = cliente._TIEMPO_LIMITE
        cliente._TIEMPO_LIMITE = 0.02
        try:
            with self.assertRaisesRegex(obs_cliente.ObsError, "No se pudo conectar"):
                cliente.pedir("GetVersion")
        finally:
            cliente._TIEMPO_LIMITE = original
