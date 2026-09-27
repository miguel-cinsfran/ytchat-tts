"""Estado puro del ciclo de vida del reproductor VLC.

Evita que se cree un segundo ``MediaPlayer`` mientras el anterior sigue en
``stop()`` / ``release()`` y recuerda solo la última intención de carga
durante la retirada.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IntencionCarga:
    tipo: str  # "video" o "flujo"
    valor: str
    autoplay: bool


class CicloReproductor:
    """Máquina mínima sin dependencias de wx ni hilos."""

    def __init__(self) -> None:
        self._siguiente_id: int = 1
        self._id_actual: int | None = None
        self._en_retirada: bool = False
        self._pendiente: IntencionCarga | None = None
        self._anuncio_hecho: bool = False

    @property
    def en_retirada(self) -> bool:
        return self._en_retirada

    @property
    def id_actual(self) -> int | None:
        return self._id_actual

    @property
    def anuncio_hecho(self) -> bool:
        return self._anuncio_hecho

    @property
    def pendiente(self) -> IntencionCarga | None:
        return self._pendiente

    def iniciar_retirada(self) -> int:
        rid = self._siguiente_id
        self._siguiente_id += 1
        self._id_actual = rid
        self._en_retirada = True
        self._anuncio_hecho = False
        return rid

    def _diferir(self, tipo: str, valor: str, autoplay: bool) -> bool:
        self._pendiente = IntencionCarga(tipo=tipo, valor=valor, autoplay=bool(autoplay))
        if self._anuncio_hecho:
            return False
        self._anuncio_hecho = True
        return True

    def diferir_video(self, video_id: str, autoplay: bool) -> bool:
        return self._diferir("video", video_id or "", bool(autoplay))

    def diferir_flujo(self, url: str, autoplay: bool) -> bool:
        return self._diferir("flujo", url or "", bool(autoplay))

    def diferir(self, tipo: str, valor: str, autoplay: bool) -> bool:
        return self._diferir(tipo, valor, autoplay)

    def cancelar_pendiente(self) -> None:
        self._pendiente = None

    def finalizar_retirada(self, rid: int) -> bool:
        if not self._en_retirada or self._id_actual != rid:
            return False
        self._en_retirada = False
        self._id_actual = None
        return True

    def tomar_pendiente(self) -> IntencionCarga | None:
        pendiente = self._pendiente
        self._pendiente = None
        return pendiente
