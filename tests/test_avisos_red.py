"""Pruebas de los avisos accesibles para fallos de red."""

import unittest

from avisos_red import mensaje_de_fallo


class TestMensajeDeFallo(unittest.TestCase):

    def test_limite_de_peticion(self):
        self.assertEqual(
            mensaje_de_fallo("ERROR: 429 Too Many Requests"),
            "El servicio está recibiendo demasiadas solicitudes. "
            "Vuelve a intentarlo en unos minutos.")

    def test_red_sin_respuesta(self):
        self.assertEqual(
            mensaje_de_fallo("Connection timed out"),
            "No se pudo consultar el vídeo porque la red no responde. "
            "Comprueba la conexión e inténtalo de nuevo.")

    def test_video_no_disponible(self):
        self.assertEqual(
            mensaje_de_fallo("Private video removed"),
            "El vídeo no está disponible. Comprueba la dirección o que no "
            "sea privado.")

    def test_motivo_desconocido(self):
        self.assertEqual(
            mensaje_de_fallo("fallo inesperado"),
            "No se pudo consultar la información del vídeo. Inténtalo de nuevo más tarde.")

    def test_motivo_vacio(self):
        general = "No se pudo consultar la información del vídeo. Inténtalo de nuevo más tarde."
        self.assertEqual(mensaje_de_fallo(None), general)
        self.assertEqual(mensaje_de_fallo(""), general)


if __name__ == "__main__":
    unittest.main()
