"""Pruebas de la tabla de opciones simples de Preferencias.

La lista de 19 va literal en este módulo, no se lee de la tabla nueva:
así protege la tabla en vez de repetirla.
"""

import unittest
from unittest import mock

from ytchat.ui import gui
from ytchat.ui import gui_preferencias
from ytchat.core import config_predeterminada as pred
from tests.rutas_temporales import redirigir_rutas
from pathlib import Path


# (atributo del control, sección, clave ini, clave en memoria, tipo).
OPCIONES_ESPERADAS = [
    ("chk_programados", "programados", "activo", "programados_activo", bool),
    ("sp_fuente", "ui", "tamanio_fuente_chat", "tamanio_fuente_chat", int),
    ("chk_total_sc", "ui", "mostrar_total_superchats", "mostrar_total_superchats", bool),
    ("chk_autoplay", "ui", "autoplay_reproductor", "autoplay_reproductor", bool),
    ("chk_metadatos", "ui", "mostrar_metadatos", "mostrar_metadatos", bool),
    ("chk_botones_rep", "ui", "mostrar_botones_reproductor", "mostrar_botones_reproductor", bool),
    ("sp_cache_video", "ui", "cache_video_mb", "cache_video_mb", int),
    ("chk_multivoz", "voz", "multivoz", "multivoz", bool),
    ("chk_emojis", "texto", "limpiar_emojis", "limpiar_emojis", bool),
    ("chk_urls", "texto", "eliminar_urls", "eliminar_urls", bool),
    ("chk_entradas", "tiktok", "anunciar_entradas", "tiktok_anunciar_entradas", bool),
    ("sp_long", "texto", "max_longitud_mensaje", "max_longitud_mensaje", int),
    ("sp_cola_maxima", "cola", "tamanio_maximo", "tamanio_maximo", int),
    ("sp_umbral_nombre", "cola", "umbral_solo_nombre", "umbral_solo_nombre", int),
    ("chk_reconectar", "reconexion", "reconectar", "reconectar", bool),
    ("sp_espera_reconexion", "reconexion", "espera_entre_intentos", "espera_entre_intentos", int),
    ("sp_max_intentos", "reconexion", "max_intentos", "max_intentos", int),
    ("chk_registro_detallado", "diagnostico", "registro_detallado", "registro_detallado", bool),
    ("sp_puerto_overlay", "overlay", "puerto", "overlay_puerto", int),
]

VALORES_SPIN = {
    "sp_fuente": 18,
    "sp_cache_video": 1500,
    "sp_long": 250,
    "sp_cola_maxima": 42,
    "sp_umbral_nombre": 7,
    "sp_espera_reconexion": 12,
    "sp_max_intentos": 3,
    "sp_puerto_overlay": 9000,
}


class TestTablaOpcionesSimples(unittest.TestCase):

    def setUp(self):
        self.app = gui.wx.App(False) if not gui.wx.App.Get() else gui.wx.App.Get()
        self.ruta = Path.cwd()
        self.parche_ruta = redirigir_rutas(self.ruta)
        self.parche_ruta.__enter__()
        self.addCleanup(self.parche_ruta.__exit__, None, None, None)

    def _dialogo(self):
        with mock.patch.object(gui, "_listar_voces_sapi5", return_value=["Voz de prueba"]):
            dialogo = gui_preferencias.PreferenciasDialog(None, {})
        self.addCleanup(dialogo.Destroy)
        return dialogo

    def test_guardar_escribe_texto_y_memoria_con_tipo_exacto(self):
        dialogo = self._dialogo()
        esperados = {}
        for atributo, seccion, clave, en_memoria, tipo in OPCIONES_ESPERADAS:
            control = getattr(dialogo, atributo)
            if tipo is bool:
                control.SetValue(not control.GetValue())
                valor = control.GetValue()
                esperados[(seccion, clave)] = ("true" if valor else "false", en_memoria, valor)
            else:
                control.SetValue(VALORES_SPIN[atributo])
                valor = VALORES_SPIN[atributo]
                esperados[(seccion, clave)] = (str(valor), en_memoria, valor)
        with mock.patch.object(gui_preferencias.cfg, "guardar_opcion",
                               return_value=True) as guardar, \
                mock.patch.object(gui_preferencias._snd, "reproducir"), \
                mock.patch.object(gui_preferencias, "anunciar"), \
                mock.patch.object(dialogo, "EndModal"):
            dialogo._on_guardar(None)
        escritos = {(llamada.args[1], llamada.args[2]): llamada.args[3]
                   for llamada in guardar.call_args_list}
        for (seccion, clave), (texto, en_memoria, valor) in esperados.items():
            with self.subTest(seccion=seccion, clave=clave):
                self.assertEqual(escritos.get((seccion, clave)), texto)
                self.assertIs(type(dialogo._config[en_memoria]), type(valor))
                self.assertEqual(dialogo._config[en_memoria], valor)

    def test_cada_atributo_existe_y_cada_clave_esta_en_fabrica(self):
        dialogo = self._dialogo()
        marca = object()
        for atributo, seccion, clave, _en_memoria, _tipo in OPCIONES_ESPERADAS:
            with self.subTest(atributo=atributo, clave=clave):
                self.assertTrue(hasattr(dialogo, atributo))
                self.assertIsNotNone(getattr(dialogo, atributo))
                self.assertIsNot(pred.obtener(seccion, clave, marca), marca)


if __name__ == "__main__":
    unittest.main()
