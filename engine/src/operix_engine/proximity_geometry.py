# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Distancia aparente mínima entre los dos segmentos inferiores de las cajas."""
from dataclasses import dataclass
import math

from operix_engine.detection import BoundingBox
from operix_engine.zone_geometry import NormalizedPoint


PROXIMITY_GEOMETRY_VERSION = "person_equipment_nearest_ground_edges_v1"
LEGACY_PROXIMITY_GEOMETRY_VERSION = "person_bottom_center_to_equipment_ground_edge_v1"


@dataclass(frozen=True, slots=True)
class GroundEdgeMeasurement:
    """person_anchor conserva el nombre del snapshot; D lo elige sobre el segmento."""
    person_anchor: NormalizedPoint
    equipment_target: NormalizedPoint
    normalized_distance: float


def nearest_ground_edges(
    person: BoundingBox, equipment: BoundingBox, width: int, height: int,
) -> GroundEdgeMeasurement:
    """Única geometría productiva de pares; no mide metros ni superficie física."""
    if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
        raise ValueError("width y height deben ser enteros positivos")
    for box in (person, equipment):
        if not isinstance(box, BoundingBox):
            raise TypeError("Los segmentos requieren BoundingBox")
        if box.x_max > width or box.y_max > height:
            raise ValueError("La caja excede las dimensiones del frame")
    if person.x_max < equipment.x_min:
        px, ex = person.x_max, equipment.x_min
    elif equipment.x_max < person.x_min:
        px, ex = person.x_min, equipment.x_max
    else:
        # Empate: punto medio de la intersección horizontal, estable/determinista.
        px = ex = (max(person.x_min, equipment.x_min) + min(person.x_max, equipment.x_max)) / 2
    anchor = NormalizedPoint(px / width, person.y_max / height)
    target = NormalizedPoint(ex / width, equipment.y_max / height)
    return GroundEdgeMeasurement(anchor, target, math.hypot(anchor.x - target.x, anchor.y - target.y))
