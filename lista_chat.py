"""Modelo de la lista de mensajes del chat (lógica pura, sin wx).

Mantiene sincronizados el historial completo (`todos`) y las filas visibles
(`visibles`: índices dentro de `todos`, en el orden en que se muestran), con
recorte al superar el máximo y filtrado por autor/tipo. Aislado aquí para poder
probarlo sin GUI: la desincronización entre estas dos listas hacía que copiar,
silenciar o banear actuaran sobre el mensaje equivocado pasados 500 mensajes.

La GUI (gui.py) es quien toca el wx.ListBox: `agregar` le dice cuántas filas
debe borrar por arriba y si debe añadir la nueva; `reconstruir` le devuelve los
mensajes visibles para repoblarla de cero.
"""

from __future__ import annotations


class ListaChat:
    """Historial + filas visibles del chat, con recorte y filtro coherentes."""

    def __init__(self, max_items: int = 500):
        self.max_items = int(max_items)
        # Cada mensaje es una tupla (autor, mensaje, hora, tipo, monto).
        self.todos: list[tuple] = []
        # Índices en `todos` de las filas mostradas, en orden.
        self.visibles: list[int] = []

    def agregar(self, item: tuple, es_visible: bool) -> int:
        """Añade un mensaje al historial (y a las filas si `es_visible`).

        Devuelve cuántas filas debe borrar la GUI POR ARRIBA de su ListBox
        (mensajes viejos recortados que estaban visibles). El recorte quita de
        `todos` y de `visibles` el MISMO mensaje una sola vez, manteniendo la
        correspondencia fila ↔ mensaje.
        """
        borrar_arriba = 0
        while len(self.todos) >= self.max_items:
            self.todos.pop(0)
            if self.visibles and self.visibles[0] == 0:
                self.visibles.pop(0)
                borrar_arriba += 1
            self.visibles = [i - 1 for i in self.visibles]
        idx = len(self.todos)
        self.todos.append(item)
        if es_visible:
            self.visibles.append(idx)
        return borrar_arriba

    def dato_en_fila(self, fila: int) -> tuple | None:
        """Mensaje que corresponde a una fila del ListBox. None si no hay."""
        if 0 <= fila < len(self.visibles):
            idx = self.visibles[fila]
            if 0 <= idx < len(self.todos):
                return self.todos[idx]
        return None

    def reconstruir(self, es_visible) -> list[tuple]:
        """Recalcula `visibles` con el predicado dado y devuelve, en orden, los
        mensajes que la GUI debe volver a pintar (tras un Clear())."""
        self.visibles = [i for i, it in enumerate(self.todos) if es_visible(it)]
        return [self.todos[i] for i in self.visibles]

    def limpiar(self) -> None:
        self.todos.clear()
        self.visibles.clear()
