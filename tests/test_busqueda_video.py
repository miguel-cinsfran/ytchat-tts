"""Pruebas de las decisiones puras del reproductor."""

import unittest

from busqueda_video import (
    TOLERANCIA_DESTINO_MS, accion_play_pausa, destino_acumulado,
    destino_alcanzado, posicion_a_mostrar,
)


class TestDestinoAcumulado(unittest.TestCase):

    def test_empieza_en_la_posicion_real_si_no_hay_salto_pendiente(self):
        self.assertEqual(destino_acumulado(None, 10_000, 10_000, 60_000), 20_000)

    def test_acumula_sobre_el_salto_pendiente(self):
        self.assertEqual(destino_acumulado(20_000, 10_000, 10_000, 60_000), 30_000)

    def test_recorta_en_los_dos_extremos(self):
        self.assertEqual(destino_acumulado(None, 1_000, -10_000, 60_000), 0)
        self.assertEqual(destino_acumulado(None, 59_000, 10_000, 60_000), 60_000)


class TestDestinoAlcanzado(unittest.TestCase):

    def test_sin_destino_pendiente_esta_alcanzado(self):
        self.assertTrue(destino_alcanzado(None, 0, TOLERANCIA_DESTINO_MS))

    def test_acepta_la_tolerancia_en_ambos_sentidos(self):
        self.assertTrue(destino_alcanzado(10_000, 8_500, TOLERANCIA_DESTINO_MS))
        self.assertTrue(destino_alcanzado(10_000, 11_500, TOLERANCIA_DESTINO_MS))
        self.assertFalse(destino_alcanzado(10_000, 8_499, TOLERANCIA_DESTINO_MS))


class TestPosicionAMostrar(unittest.TestCase):

    def test_prioriza_el_destino_pendiente(self):
        self.assertEqual(posicion_a_mostrar(20_000, 10_000), 20_000)

    def test_usa_la_posicion_real_sin_destino(self):
        self.assertEqual(posicion_a_mostrar(None, 10_000), 10_000)


class TestAccionPlayPausa(unittest.TestCase):

    def test_sin_medio_carga(self):
        self.assertEqual(accion_play_pausa("playing", False, True), "cargar")

    def test_estados_estables(self):
        self.assertEqual(accion_play_pausa("playing", True, True), "pausar")
        self.assertEqual(accion_play_pausa("paused", True, False), "reanudar")

    def test_estados_finales_recargan(self):
        for estado in ("ended", "stopped", "error", "nothingspecial"):
            with self.subTest(estado=estado):
                self.assertEqual(accion_play_pausa(estado, True, False), "cargar")

    def test_estados_transitorios_siguen_la_intencion(self):
        for estado in ("opening", "buffering", "futuro"):
            with self.subTest(estado=estado):
                self.assertEqual(accion_play_pausa(estado, True, True), "pausar")
                self.assertEqual(accion_play_pausa(estado, True, False), "reanudar")


if __name__ == "__main__":
    unittest.main()
