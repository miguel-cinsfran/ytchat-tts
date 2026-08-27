"""Tests del formateo del estado de sesión (F2)."""

import unittest

from estado_sesion import (SnapshotSesion, formatear_estado, COMPONENTES,
                           ACTIVOS_DEFECTO, _duracion)


class TestDuracion(unittest.TestCase):

    def test_cero(self):
        self.assertEqual(_duracion(0), "menos de un minuto")

    def test_cincuenta_y_nueve_segundos(self):
        self.assertEqual(_duracion(59), "menos de un minuto")

    def test_un_minuto(self):
        self.assertEqual(_duracion(60), "1 min")

    def test_veintitres_minutos(self):
        self.assertEqual(_duracion(23 * 60), "23 min")

    def test_una_hora(self):
        self.assertEqual(_duracion(60 * 60), "1 h 0 min")

    def test_una_hora_y_veintitres_minutos(self):
        self.assertEqual(_duracion(83 * 60), "1 h 23 min")

    def test_treinta_horas_y_cinco_minutos(self):
        self.assertEqual(_duracion(30 * 60 * 60 + 5 * 60), "30 h 5 min")


class TestTiempoDirecto(unittest.TestCase):

    def test_corto(self):
        self.assertEqual(formatear_estado(
            SnapshotSesion(segundos_directo=83 * 60), {"tiempo_directo"}),
            "Lleva 1 h 23 min.")

    def test_largo(self):
        self.assertEqual(formatear_estado(
            SnapshotSesion(segundos_directo=83 * 60), {"tiempo_directo"}, "largo"),
            "Tiempo del directo: 1 h 23 min")

    def test_sin_dato(self):
        self.assertEqual(formatear_estado(
            SnapshotSesion(segundos_directo=None), {"tiempo_directo"}), "")

    def test_negativo(self):
        self.assertEqual(formatear_estado(
            SnapshotSesion(segundos_directo=-1), {"tiempo_directo"}), "")


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

    def test_mensajes_programados_se_anuncian_si_hay_dato(self):
        s = SnapshotSesion(programados_proximo=
                           "Próximo mensaje programado en 4 minutos")
        self.assertEqual(formatear_estado(s, {"programados"}),
                         "Próximo mensaje programado en 4 minutos.")

    def test_mensajes_programados_vacios_se_omiten(self):
        self.assertEqual(formatear_estado(SnapshotSesion(), {"programados"}), "")

    def test_activos_defecto_son_componentes_validos(self):
        for nombre in ACTIVOS_DEFECTO:
            self.assertIn(nombre, COMPONENTES)

    def test_panel_apagado_no_agrega_estado(self):
        s = SnapshotSesion(overlay_puerto=None)
        self.assertEqual(formatear_estado(s, {"overlay"}), "")

    def test_panel_activo_distingue_clientes(self):
        s = SnapshotSesion(overlay_puerto=9000, overlay_clientes=1)
        self.assertEqual(
            formatear_estado(s, {"overlay"}),
            "Panel de chat activo en el puerto 9000, mostrándose.")
        s = SnapshotSesion(overlay_puerto=9000, overlay_clientes=0)
        self.assertEqual(
            formatear_estado(s, {"overlay"}),
            "Panel de chat activo en el puerto 9000, pero nadie lo está mostrando.")


if __name__ == "__main__":
    unittest.main()
