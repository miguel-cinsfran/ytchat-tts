"""Pruebas de la compatibilidad con TikTokLive 6.6.6 (suscripción y errores)."""

import builtins
import threading
import unittest
from unittest import mock

from ytchat.capture import tiktok_captura
from ytchat.capture.tiktok_captura import (
    _clase_suscripcion, _TEXTO_VERSION_INCOMPATIBLE)

_HAY_TIKTOKLIVE = tiktok_captura.disponible()


class TestClaseSuscripcion(unittest.TestCase):

    def test_con_subscribe_event_devuelve_ese(self):
        class Viejo:
            pass
        modulo = mock.Mock()
        modulo.SubscribeEvent = Viejo
        modulo.SubNotifyEvent = mock.Mock()
        self.assertIs(_clase_suscripcion(modulo), Viejo)

    def test_solo_con_sub_notify_devuelve_ese(self):
        modulo = mock.Mock(spec=["SubNotifyEvent"])
        self.assertIs(_clase_suscripcion(modulo), modulo.SubNotifyEvent)

    def test_sin_ninguno_devuelve_none(self):
        self.assertIsNone(_clase_suscripcion(mock.Mock(spec=[])))

    @unittest.skipUnless(_HAY_TIKTOKLIVE, "TikTokLive no está instalado")
    def test_con_el_tiktoklive_instalado_no_es_none(self):
        import TikTokLive.events as eventos
        self.assertIsNotNone(_clase_suscripcion(eventos))


class TestCableadoPreparacion(unittest.TestCase):

    def _correr(self, paradas_import=False, max_intentos=3):
        estados = []
        parada = threading.Event()
        real_import = builtins.__import__

        def falla(nombre, *args, **kwargs):
            if nombre == "TikTokLive.events":
                raise ImportError("cannot import name 'SubscribeEvent'")
            return real_import(nombre, *args, **kwargs)

        ctx = (mock.patch.object(builtins, "__import__", side_effect=falla)
               if paradas_import else mock.patch.object(threading, "Event"))
        with ctx:
            tiktok_captura.capturar_con_reconexion(
                "pepe", {"max_intentos": max_intentos, "espera_entre_intentos": 0},
                parada, on_evento=lambda *a: None,
                on_estado=lambda tipo, texto: estados.append((tipo, texto)))
        return parada, estados

    def test_sesion_devuelve_el_error_de_preparacion_en_vez_de_lanzarlo(self):
        real_import = builtins.__import__

        def falla(nombre, *args, **kwargs):
            if nombre == "TikTokLive.events":
                raise ImportError("cannot import name 'SubscribeEvent'")
            return real_import(nombre, *args, **kwargs)

        with mock.patch.object(builtins, "__import__", side_effect=falla):
            resultado = tiktok_captura._sesion(
                "pepe", threading.Event(), lambda *a: None, None, None, None)
        self.assertIsInstance(resultado, ImportError)

    def test_import_roto_es_error_permanente_sin_reintentos_ni_excepcion(self):
        with mock.patch.object(tiktok_captura, "disponible", return_value=True):
            parada, estados = self._correr(paradas_import=True)
            permanentes = [x for t, x in estados if t == "error_permanente"]
            self.assertEqual(len(permanentes), 1)
            self.assertEqual(permanentes[0], _TEXTO_VERSION_INCOMPATIBLE)
            self.assertEqual(sum(1 for t, _ in estados if t == "conectando"), 1)
            self.assertFalse(any(t == "reintentando" for t, _ in estados))
            self.assertTrue(parada.is_set())

    @unittest.skipUnless(_HAY_TIKTOKLIVE, "TikTokLive no está instalado")
    def test_cliente_incompatible_es_error_permanente(self):
        estados = []
        parada = threading.Event()
        with mock.patch("TikTokLive.TikTokLiveClient",
                        side_effect=AttributeError("unique_id")):
            tiktok_captura.capturar_con_reconexion(
                "pepe", {"max_intentos": 3, "espera_entre_intentos": 0},
                parada, on_evento=lambda *a: None,
                on_estado=lambda tipo, texto: estados.append((tipo, texto)))
        self.assertIn(("error_permanente", _TEXTO_VERSION_INCOMPATIBLE), estados)
        self.assertTrue(parada.is_set())

    def test_excepcion_inesperada_no_mata_el_hilo_y_avisa_error(self):
        estados = []
        with mock.patch.object(tiktok_captura, "disponible", return_value=True), \
                mock.patch.object(tiktok_captura, "_sesion",
                                  side_effect=RuntimeError("boom")):
            tiktok_captura.capturar_con_reconexion(
                "pepe", {"max_intentos": 2, "espera_entre_intentos": 0},
                threading.Event(), on_evento=lambda *a: None,
                on_estado=lambda tipo, texto: estados.append((tipo, texto)))
        self.assertTrue(any(t == "error" for t, _ in estados))


if __name__ == "__main__":
    unittest.main()
