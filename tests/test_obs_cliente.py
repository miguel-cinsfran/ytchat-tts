import base64
import hashlib
import json
import os
import tempfile
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
