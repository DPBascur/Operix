# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tipos y contrato de detección independientes del backend de inferencia."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Caja ``xyxy`` expresada en píxeles del frame original."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        coordinates = (self.x_min, self.y_min, self.x_max, self.y_max)
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("Las coordenadas de la caja deben ser finitas")
        if min(coordinates) < 0:
            raise ValueError("Las coordenadas de la caja no pueden ser negativas")
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("La caja debe tener ancho y alto positivos")


@dataclass(frozen=True, slots=True)
class Detection:
    """Detección normalizada que no expone tipos internos del backend."""

    class_id: int
    class_name: str
    confidence: float
    bounding_box: BoundingBox

    def __post_init__(self) -> None:
        if self.class_id < 0:
            raise ValueError("class_id no puede ser negativo")
        if not self.class_name.strip():
            raise ValueError("class_name no puede estar vacío")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence debe estar entre 0 y 1")


class Detector(Protocol):
    """Contrato mínimo de un detector de objetos para un frame BGR."""

    @property
    def class_names(self) -> dict[int, str]:
        """Devuelve el vocabulario de clases declarado por el modelo."""
        ...

    def detect(self, frame: NDArray[np.uint8]) -> tuple[Detection, ...]:
        """Transforma un frame BGR uint8 en detecciones estructuradas."""
        ...
