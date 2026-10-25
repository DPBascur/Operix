# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Proximidad aparente de una persona al borde inferior de un equipo rectangular."""
from dataclasses import dataclass
import math

from operix_engine.detection import BoundingBox
from operix_engine.zone_geometry import NormalizedPoint, normalized_bottom_center


PROXIMITY_GEOMETRY_VERSION = "person_bottom_center_to_equipment_ground_edge_v1"


@dataclass(frozen=True, slots=True)
class GroundEdgeMeasurement:
    person_anchor: NormalizedPoint
    equipment_target: NormalizedPoint
    normalized_distance: float


def person_to_equipment_ground_edge(
    person: BoundingBox, equipment: BoundingBox, width: int, height: int,
) -> GroundEdgeMeasurement:
    """Única geometría productiva de pares; no mide metros ni superficie física."""
    anchor = normalized_bottom_center(person, width, height)
    normalized_bottom_center(equipment, width, height)  # Misma validación de cajas/frame.
    target = NormalizedPoint(
        min(equipment.x_max / width, max(equipment.x_min / width, anchor.x)),
        equipment.y_max / height,
    )
    return GroundEdgeMeasurement(anchor, target, math.hypot(anchor.x - target.x, anchor.y - target.y))
