"""Tarea de caché de vídeo para ReproductorPanel."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading


@dataclass(eq=False)
class TareaCacheVideo:
    """Identidad de una descarga de caché con evento propio."""

    video_id: str
    generacion: int
    destino: Path
    cancelacion: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self):
        self.destino = Path(self.destino)
