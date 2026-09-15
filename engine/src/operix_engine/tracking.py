"""Tipos y contrato de tracking independientes del backend."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from operix_engine.detection import BoundingBox, Detection


@dataclass(frozen=True, slots=True)
class Track:
    """Estado observable de un track activo en el frame actual."""

    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bounding_box: BoundingBox

    def __post_init__(self) -> None:
        if self.track_id <= 0:
            raise ValueError("track_id debe ser positivo")
        if self.class_id < 0:
            raise ValueError("class_id no puede ser negativo")
        if not self.class_name.strip():
            raise ValueError("class_name no puede estar vacío")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence debe estar entre 0 y 1")


class Tracker(Protocol):
    """Contrato mínimo de seguimiento para una secuencia de frames."""

    def update(self, detections: tuple[Detection, ...]) -> tuple[Track, ...]:
        """Avanza exactamente un frame, incluso si no hay detecciones."""
        ...

    def reset(self) -> None:
        """Inicia una nueva sesión con estado e IDs reiniciados."""
        ...
