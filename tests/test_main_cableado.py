import unittest
from unittest.mock import patch

import main


class ConexionFalsa:
    def __init__(self, *args):
        self.llamadas = []

    def conectar(self, url):
        self.llamadas.append(("conectar", url))

    def desconectar(self):
        self.llamadas.append(("desconectar",))


class PruebasCableadoMain(unittest.TestCase):
    def test_los_callbacks_comparten_el_registro_de_conexiones(self):
        with patch.object(main.conexion, "Conexiones", ConexionFalsa):
            conectar, desconectar = main.armar_callbacks_captura(
                object(), {}, object(), object())

        conectar("directo")
        desconectar()
        self.assertIs(conectar.__self__, desconectar.__self__)
        self.assertEqual(conectar.__self__.llamadas,
                         [("conectar", "directo"), ("desconectar",)])


if __name__ == "__main__":
    unittest.main()
