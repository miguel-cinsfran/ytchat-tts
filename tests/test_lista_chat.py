"""Tests del modelo de la lista de chat (recorte, filtro y selección).

Incluye la regresión del bug de v0.8.2: al superar el máximo de mensajes, la
primera fila visible se descontaba dos veces y desde entonces cada acción del
menú contextual (copiar, silenciar, banear) caía sobre el mensaje equivocado.
"""

import unittest

from lista_chat import ListaChat


def _msg(n, tipo="text"):
    return (f"autor{n}", f"mensaje {n}", "12:00:00", tipo, "")


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
        # Mensaje 6: recorta el 0 (que estaba visible) y añade el nuevo.
        borrar = lc.agregar(_msg(5), es_visible=True)
        self.assertEqual(borrar, 1)
        filas += 1 - borrar
        self.assertEqual(filas, 5)
        self.assertEqual(len(lc.visibles), filas)  # sin desalineación
        # La fila 0 ahora es el mensaje 1 y la última el recién llegado.
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
        lc.agregar(_msg(0), es_visible=False)   # este caerá primero
        lc.agregar(_msg(1), es_visible=True)
        lc.agregar(_msg(2), es_visible=True)
        borrar = lc.agregar(_msg(3), es_visible=True)
        self.assertEqual(borrar, 0)   # el recortado no estaba en pantalla
        self.assertEqual(len(lc.visibles), 3)
        self.assertEqual(lc.dato_en_fila(0), _msg(1))
        self.assertEqual(lc.dato_en_fila(2), _msg(3))

    def test_recorte_con_filtro_mixto(self):
        lc = ListaChat(max_items=4)
        # Alterna visible / oculto; el recorte debe quitar filas solo cuando el
        # mensaje que cae estaba visible.
        lc.agregar(_msg(0), es_visible=True)
        lc.agregar(_msg(1), es_visible=False)
        lc.agregar(_msg(2), es_visible=True)
        lc.agregar(_msg(3), es_visible=False)
        borrar = lc.agregar(_msg(4), es_visible=True)   # cae el 0 (visible)
        self.assertEqual(borrar, 1)
        borrar = lc.agregar(_msg(5), es_visible=True)   # cae el 1 (oculto)
        self.assertEqual(borrar, 0)
        # Filas actuales: 2, 4, 5.
        self.assertEqual(lc.dato_en_fila(0), _msg(2))
        self.assertEqual(lc.dato_en_fila(1), _msg(4))
        self.assertEqual(lc.dato_en_fila(2), _msg(5))


class TestReconstruir(unittest.TestCase):

    def test_filtra_por_tipo(self):
        lc = ListaChat(max_items=10)
        lc.agregar(_msg(0, "text"), es_visible=True)
        lc.agregar(_msg(1, "superchat"), es_visible=True)
        lc.agregar(_msg(2, "text"), es_visible=True)
        visibles = lc.reconstruir(lambda it: it[3] == "superchat")
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


if __name__ == "__main__":
    unittest.main()
