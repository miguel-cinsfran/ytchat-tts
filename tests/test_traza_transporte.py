"""Pruebas del formato de las trazas del transporte."""

import itertools
import unittest

from traza_transporte import traza_salto, traza_sin_barra, traza_transporte


class TestTrazaTransporte(unittest.TestCase):

    def test_traza_transporte_corriente(self):
        self.assertEqual(
            traza_transporte("playing", "pausar", True, True, True, False),
            "TRANSPORTE estado=playing accion=pausar medio=si intencion=si "
            "puede_pausar=si buscable=no")

    def test_traza_transporte_consulta_desconocida(self):
        self.assertEqual(
            traza_transporte("paused", "reanudar", False, False, None, None),
            "TRANSPORTE estado=paused accion=reanudar medio=no intencion=no "
            "puede_pausar=desconocido buscable=desconocido")

    def test_traza_transporte_booleanos_de_vlc(self):
        self.assertIn("puede_pausar=no", traza_transporte(
            "playing", "pausar", True, False, False, True))
        self.assertIn("puede_pausar=si", traza_transporte(
            "playing", "pausar", True, False, True, False))

    def test_traza_salto_corriente(self):
        self.assertEqual(
            traza_salto("relativo", 3000, 5000, -1000, 4000, 10000),
            "SALTO origen=relativo pendiente=3000 pos=5000 delta=-1000 "
            "destino=4000 dur=10000")

    def test_traza_salto_pendiente_nulo_y_destinos_limite(self):
        self.assertEqual(
            traza_salto("porcentaje", None, 0, 0, 0, 10000),
            "SALTO origen=porcentaje pendiente=ninguno pos=0 delta=0 "
            "destino=0 dur=10000")
        self.assertEqual(
            traza_salto("deslizador", 0, 10000, 0, 10000, 10000),
            "SALTO origen=deslizador pendiente=0 pos=10000 delta=0 "
            "destino=10000 dur=10000")

    def test_traza_sin_barra_corriente(self):
        self.assertEqual(traza_sin_barra("relativo", 0),
                         "SALTO_SIN_BARRA origen=relativo dur=0")

    def test_propiedad_sin_saltos_y_campos_en_orden(self):
        for estado, accion, medio, intencion, puede, buscable in itertools.product(
                ("playing", "paused"), ("pausar", "reanudar"),
                (False, True), (False, True), (None, False, True),
                (None, False, True)):
            linea = traza_transporte(
                estado, accion, medio, intencion, puede, buscable)
            self.assertNotIn("\n", linea)
            self.assertEqual(
                [campo.split("=", 1)[0] for campo in linea.split()],
                ["TRANSPORTE", "estado", "accion", "medio", "intencion",
                 "puede_pausar", "buscable"])
        for origen, pendiente, numero in itertools.product(
                ("relativo", "porcentaje", "deslizador"), (None, 0, 1),
                (0, 1)):
            linea = traza_salto(origen, pendiente, numero, -numero, numero, numero)
            self.assertNotIn("\n", linea)
            self.assertEqual(
                [campo.split("=", 1)[0] for campo in linea.split()],
                ["SALTO", "origen", "pendiente", "pos", "delta", "destino", "dur"])
            linea = traza_sin_barra(origen, numero)
            self.assertNotIn("\n", linea)
            self.assertEqual(
                [campo.split("=", 1)[0] for campo in linea.split()],
                ["SALTO_SIN_BARRA", "origen", "dur"])


if __name__ == "__main__":
    unittest.main()
