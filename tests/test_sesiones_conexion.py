import queue
import sys
import threading
import types
import unittest
from unittest import mock

from conexion import Conexiones
from sesiones import RegistroSesiones


class RegistroEspia(RegistroSesiones):
    def __init__(self):
        super().__init__()
        self.sesiones = []

    def abrir(self):
        sesion = super().abrir()
        self.sesiones.append(sesion)
        return sesion


class HiloInerte:
    def start(self):
        return None


def crear_hilo_inerte(*args, **kwargs):
    return HiloInerte()


class PruebasSesiones(unittest.TestCase):
    def test_abrir_dos_veces_para_la_sesion_anterior(self):
        registro = RegistroSesiones()
        anterior = registro.abrir()
        nueva = registro.abrir()
        self.assertTrue(anterior.parada.is_set())
        self.assertFalse(nueva.parada.is_set())

    def test_vigente_solo_acepta_el_gen_recien_abierto(self):
        registro = RegistroSesiones()
        anterior = registro.abrir()
        nueva = registro.abrir()
        self.assertTrue(registro.vigente(nueva.gen))
        self.assertFalse(registro.vigente(anterior.gen))

    def test_cerrar_es_idempotente_y_para_la_vigente(self):
        registro = RegistroSesiones()
        sesion = registro.abrir()
        self.assertTrue(registro.cerrar())
        self.assertTrue(sesion.parada.is_set())
        self.assertFalse(registro.cerrar())


class PruebasCableadoConexiones(unittest.TestCase):
    def setUp(self):
        self.gui_falsa = types.SimpleNamespace(_gui_frame=None)
        self.modulo_gui_anterior = sys.modules.get("gui")
        sys.modules["gui"] = self.gui_falsa
        self.registro = RegistroEspia()
        self.conexiones = Conexiones(
            queue.Queue(), {}, mock.Mock(), threading.Event(),
            crear_hilo=crear_hilo_inerte, registro=self.registro)

    def tearDown(self):
        if self.modulo_gui_anterior is None:
            sys.modules.pop("gui", None)
        else:
            sys.modules["gui"] = self.modulo_gui_anterior

    def test_conectar_dos_veces_para_la_sesion_de_youtube(self):
        self.conexiones.conectar("dQw4w9WgXcQ")
        self.conexiones.conectar("9bZkp7q19f0")
        self.assertTrue(self.registro.sesiones[0].parada.is_set())
        self.assertFalse(self.registro.sesiones[1].parada.is_set())

    def test_conectar_youtube_y_tiktok_para_youtube(self):
        self.conexiones.conectar("dQw4w9WgXcQ")
        self.conexiones.conectar("https://www.tiktok.com/@pepe/live")
        self.assertTrue(self.registro.sesiones[0].parada.is_set())
        self.assertFalse(self.registro.sesiones[1].parada.is_set())

    def test_desconectar_para_la_sesion_vigente(self):
        self.conexiones.conectar("dQw4w9WgXcQ")
        self.conexiones.desconectar()
        self.assertTrue(self.registro.sesiones[0].parada.is_set())


if __name__ == "__main__":
    unittest.main()
