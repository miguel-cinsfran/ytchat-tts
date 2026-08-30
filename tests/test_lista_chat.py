"""Tests del modelo de la lista de chat (recorte, filtro y selección).

Incluye la regresión del bug de v0.8.2: al superar el máximo de mensajes, la
primera fila visible se descontaba dos veces y desde entonces cada acción del
menú contextual (copiar, silenciar, banear) caía sobre el mensaje equivocado.
"""

import unittest

from lista_chat import ListaChat, MensajeChat


def _msg(n, tipo="text", plataforma="youtube", identificador=None, autor=None):
    return MensajeChat(
        plataforma=plataforma,
        autor=autor if autor is not None else f"autor{n}",
        identificador=identificador if identificador is not None else f"id{n}",
        texto=f"mensaje {n}",
        hora="12:00:00",
        tipo=tipo,
        monto="",
    )


def _homonimo(texto_n, identificador, plataforma="youtube"):
    return MensajeChat(
        plataforma=plataforma,
        autor="Igual",
        identificador=identificador,
        texto=texto_n,
        hora="12:00:00",
        tipo="text",
        monto="",
    )


class TestAgregarBasico(unittest.TestCase):

    def test_visible_mapea_fila_a_dato(self):
        lc = ListaChat(max_items=10)
        for n in range(3):
            borrar = lc.agregar(_msg(n), es_visible=True)
            self.assertEqual(borrar, 0)
        self.assertEqual(lc.dato_en_fila(0), _msg(0))
        self.assertEqual(lc.dato_en_fila(2), _msg(2))

    def test_no_visible_no_crea_fila(self):
        lc = ListaChat(max_items=10)
        lc.agregar(_msg(0), es_visible=True)
        lc.agregar(_msg(1), es_visible=False)
        lc.agregar(_msg(2), es_visible=True)
        self.assertEqual(len(lc.visibles), 2)
        self.assertEqual(lc.dato_en_fila(1), _msg(2))

    def test_fila_fuera_de_rango(self):
        lc = ListaChat(max_items=10)
        lc.agregar(_msg(0), es_visible=True)
        self.assertIsNone(lc.dato_en_fila(-1))
        self.assertIsNone(lc.dato_en_fila(1))
        self.assertIsNone(lc.dato_en_fila(99))


class TestRecorte(unittest.TestCase):
    """Regresión del bug: pasado el máximo, fila y dato deben seguir alineados."""

    def test_sin_filtro_recorta_una_fila_por_mensaje(self):
        lc = ListaChat(max_items=5)
        filas = 0
        for n in range(5):
            filas += 1 - lc.agregar(_msg(n), es_visible=True)
        borrar = lc.agregar(_msg(5), es_visible=True)
        self.assertEqual(borrar, 1)
        filas += 1 - borrar
        self.assertEqual(filas, 5)
        self.assertEqual(len(lc.visibles), filas)
        self.assertEqual(lc.dato_en_fila(0), _msg(1))
        self.assertEqual(lc.dato_en_fila(4), _msg(5))

    def test_alineacion_se_mantiene_muy_pasado_el_maximo(self):
        lc = ListaChat(max_items=5)
        filas = 0
        for n in range(50):
            filas += 1 - lc.agregar(_msg(n), es_visible=True)
        self.assertEqual(filas, 5)
        self.assertEqual(len(lc.visibles), 5)
        for fila in range(5):
            self.assertEqual(lc.dato_en_fila(fila), _msg(45 + fila))

    def test_recorte_de_mensaje_oculto_no_borra_filas(self):
        lc = ListaChat(max_items=3)
        lc.agregar(_msg(0), es_visible=False)
        lc.agregar(_msg(1), es_visible=True)
        lc.agregar(_msg(2), es_visible=True)
        borrar = lc.agregar(_msg(3), es_visible=True)
        self.assertEqual(borrar, 0)
        self.assertEqual(len(lc.visibles), 3)
        self.assertEqual(lc.dato_en_fila(0), _msg(1))
        self.assertEqual(lc.dato_en_fila(2), _msg(3))

    def test_recorte_con_filtro_mixto(self):
        lc = ListaChat(max_items=4)
        lc.agregar(_msg(0), es_visible=True)
        lc.agregar(_msg(1), es_visible=False)
        lc.agregar(_msg(2), es_visible=True)
        lc.agregar(_msg(3), es_visible=False)
        borrar = lc.agregar(_msg(4), es_visible=True)
        self.assertEqual(borrar, 1)
        borrar = lc.agregar(_msg(5), es_visible=True)
        self.assertEqual(borrar, 0)
        self.assertEqual(lc.dato_en_fila(0), _msg(2))
        self.assertEqual(lc.dato_en_fila(1), _msg(4))
        self.assertEqual(lc.dato_en_fila(2), _msg(5))


class TestReconstruir(unittest.TestCase):

    def test_filtra_por_tipo(self):
        lc = ListaChat(max_items=10)
        lc.agregar(_msg(0, "text"), es_visible=True)
        lc.agregar(_msg(1, "superchat"), es_visible=True)
        lc.agregar(_msg(2, "text"), es_visible=True)
        visibles = lc.reconstruir(lambda it: it.tipo == "superchat")
        self.assertEqual(visibles, [_msg(1, "superchat")])
        self.assertEqual(lc.dato_en_fila(0), _msg(1, "superchat"))
        self.assertIsNone(lc.dato_en_fila(1))

    def test_quitar_filtro_recupera_todo(self):
        lc = ListaChat(max_items=10)
        for n in range(3):
            lc.agregar(_msg(n), es_visible=(n == 1))
        visibles = lc.reconstruir(lambda it: True)
        self.assertEqual(len(visibles), 3)
        self.assertEqual(lc.dato_en_fila(0), _msg(0))


class TestLimpiar(unittest.TestCase):

    def test_limpiar_vacia_todo(self):
        lc = ListaChat(max_items=10)
        lc.agregar(_msg(0), es_visible=True)
        lc.limpiar()
        self.assertEqual(lc.todos, [])
        self.assertEqual(lc.visibles, [])
        self.assertIsNone(lc.dato_en_fila(0))


class TestIdentidadHomonima(unittest.TestCase):
    """Dos registros homónimos con identificadores distintos conservan identidad por fila."""

    def test_homonimos_conservan_identidad_por_fila(self):
        lc = ListaChat(max_items=10)
        a = _homonimo("hola A", "AAA")
        b = _homonimo("hola B", "BBB")
        lc.agregar(a, es_visible=True)
        lc.agregar(b, es_visible=True)
        self.assertIs(lc.dato_en_fila(0), a)
        self.assertIs(lc.dato_en_fila(1), b)
        self.assertEqual(lc.dato_en_fila(0).identificador, "AAA")
        self.assertEqual(lc.dato_en_fila(1).identificador, "BBB")
        self.assertEqual(lc.dato_en_fila(0).autor, "Igual")
        self.assertEqual(lc.dato_en_fila(1).autor, "Igual")

    def test_seleccion_antigua_tras_agregar_nueva(self):
        lc = ListaChat(max_items=10)
        a = _homonimo("primero", "AAA")
        b = _homonimo("segundo", "BBB")
        lc.agregar(a, es_visible=True)
        lc.agregar(b, es_visible=True)
        # Simula seleccionar fila 0 después de agregar la nueva.
        fila_antigua = lc.dato_en_fila(0)
        self.assertIs(fila_antigua, a)
        self.assertEqual(fila_antigua.identificador, "AAA")
        self.assertNotEqual(fila_antigua.identificador, "BBB")

    def test_filtro_conserva_instancia(self):
        lc = ListaChat(max_items=10)
        a = _homonimo("hola A", "AAA")
        b = _homonimo("hola B", "BBB")
        c = MensajeChat(plataforma="youtube", autor="Otro", identificador="CCC",
                        texto="otro", hora="12:00:01", tipo="superchat", monto="$5")
        lc.agregar(a, es_visible=True)
        lc.agregar(b, es_visible=True)
        lc.agregar(c, es_visible=True)
        visibles = lc.reconstruir(lambda it: it.tipo == "text")
        self.assertEqual(len(visibles), 2)
        self.assertIs(visibles[0], a)
        self.assertIs(visibles[1], b)
        self.assertIs(lc.dato_en_fila(0), a)
        self.assertIs(lc.dato_en_fila(1), b)

    def test_reconstruccion_conserva_instancia(self):
        lc = ListaChat(max_items=10)
        a = _homonimo("hola A", "AAA")
        b = _homonimo("hola B", "BBB")
        lc.agregar(a, es_visible=False)
        lc.agregar(b, es_visible=True)
        # Reconstruir para mostrar todo recupera la misma instancia a.
        visibles = lc.reconstruir(lambda it: True)
        self.assertEqual(len(visibles), 2)
        self.assertIs(visibles[0], a)
        self.assertIs(visibles[1], b)

    def test_recorte_con_homonimos_mantiene_identidad(self):
        lc = ListaChat(max_items=3)
        a = _homonimo("a", "AAA")
        b = _homonimo("b", "BBB")
        c = _homonimo("c", "CCC")
        d = _homonimo("d", "DDD")
        lc.agregar(a, es_visible=True)
        lc.agregar(b, es_visible=True)
        lc.agregar(c, es_visible=True)
        borrar = lc.agregar(d, es_visible=True)
        self.assertEqual(borrar, 1)
        self.assertIs(lc.dato_en_fila(0), b)
        self.assertIs(lc.dato_en_fila(1), c)
        self.assertIs(lc.dato_en_fila(2), d)
        self.assertEqual(lc.dato_en_fila(0).identificador, "BBB")

    def test_limpieza_vacia_homonimos(self):
        lc = ListaChat(max_items=10)
        a = _homonimo("hola A", "AAA")
        b = _homonimo("hola B", "BBB")
        lc.agregar(a, es_visible=True)
        lc.agregar(b, es_visible=True)
        lc.limpiar()
        self.assertEqual(lc.todos, [])
        self.assertIsNone(lc.dato_en_fila(0))


if __name__ == "__main__":
    unittest.main()
