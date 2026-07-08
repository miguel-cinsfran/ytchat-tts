"""Tests del formateo del estado de sesión (F2)."""

import unittest

from estado_sesion import (SnapshotSesion, formatear_estado, COMPONENTES,
                           ACTIVOS_DEFECTO)


class TestFormatoBasico(unittest.TestCase):

    def test_desconectado(self):
        s = SnapshotSesion(conectado=False)
        self.assertEqual(formatear_estado(s, {"estado"}), "Desconectado.")

    def test_conectado_tiktok_con_datos(self):
        s = SnapshotSesion(conectado=True, tipo="live_tiktok",
                           titulo="Charla nocturna", canal="Fulano",
                           espectadores=1234, mensajes_leidos=10)
        out = formatear_estado(s, ACTIVOS_DEFECTO)
        self.assertIn("Directo de TikTok", out)
        self.assertIn("Charla nocturna", out)
        self.assertIn("Canal: Fulano", out)
        self.assertIn("1.234 espectadores", out)   # miles con punto
        self.assertIn("10 leídos", out)
        self.assertTrue(out.endswith("."))

    def test_orden_de_componentes(self):
        s = SnapshotSesion(conectado=True, tipo="vod", titulo="T", canal="C")
        out = formatear_estado(s, {"estado", "titulo", "canal"})
        self.assertLess(out.index("Vídeo"), out.index("T"))
        self.assertLess(out.index("T"), out.index("Canal: C"))


class TestOmisiones(unittest.TestCase):

    def test_omite_componentes_sin_dato(self):
        # Sin espectadores ni aportes: esos componentes desaparecen.
        s = SnapshotSesion(conectado=True, tipo="live_youtube", titulo="Hola",
                           espectadores=None, aportes=0)
        out = formatear_estado(s, ACTIVOS_DEFECTO)
        self.assertNotIn("espectadores", out)
        self.assertNotIn("Super Chats", out)

    def test_toggle_desactivado_no_aparece(self):
        s = SnapshotSesion(conectado=True, tipo="vod", titulo="Hola", canal="C")
        out = formatear_estado(s, {"estado"})   # solo estado
        self.assertEqual(out, "Vídeo.")

    def test_lectura_silenciada_solo_si_activa(self):
        s = SnapshotSesion(conectado=True, tipo="vod", lectura_silenciada=False)
        self.assertNotIn("silenciada", formatear_estado(s, {"lectura_silenciada"}))
        s2 = SnapshotSesion(conectado=True, tipo="vod", lectura_silenciada=True)
        self.assertIn("Lectura silenciada", formatear_estado(s2, {"lectura_silenciada"}))


class TestAportes(unittest.TestCase):

    def test_youtube_dice_super_chats(self):
        s = SnapshotSesion(conectado=True, tipo="live_youtube", aportes=3,
                           total_aportes="US$12,50")
        out = formatear_estado(s, {"aportes"})
        self.assertIn("3 Super Chats", out)
        self.assertIn("US$12,50", out)

    def test_tiktok_dice_regalos(self):
        s = SnapshotSesion(conectado=True, tipo="live_tiktok", aportes=5)
        self.assertIn("5 regalos", formatear_estado(s, {"aportes"}))


class TestModoLargo(unittest.TestCase):

    def test_largo_es_multilinea_con_etiquetas(self):
        s = SnapshotSesion(conectado=True, tipo="live_tiktok", titulo="T",
                           espectadores=50)
        out = formatear_estado(s, {"estado", "titulo", "espectadores"}, modo="largo")
        lineas = out.split("\n")
        self.assertEqual(lineas[0], "Directo de TikTok")
        self.assertIn("Título: T", lineas)
        self.assertIn("Espectadores: 50", lineas)

    def test_vacio_si_nada_que_mostrar(self):
        s = SnapshotSesion(conectado=True, tipo="vod")
        self.assertEqual(formatear_estado(s, {"titulo", "canal"}), "")


class TestCoherencia(unittest.TestCase):

    def test_activos_defecto_son_componentes_validos(self):
        for nombre in ACTIVOS_DEFECTO:
            self.assertIn(nombre, COMPONENTES)


if __name__ == "__main__":
    unittest.main()
