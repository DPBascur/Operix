# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Captura técnica del estado sintético exacto que produjo un candidato.

No representa píxeles de cámara ni resultados de detección por IA.
"""

from __future__ import annotations

import cv2
import numpy as np

from operix_engine.operational_config import Zone
from operix_engine.rules import EventCandidate
from operix_engine.tracking import Track


def render_track_frame(
    candidate: EventCandidate,
    tracks: tuple[Track, ...],
    zones: tuple[Zone, ...],
    *,
    width: int,
    height: int,
) -> bytes:
    """Codifica un PNG del frame de tracks evaluado, sin inventar imagen de cámara."""
    matching = [track for track in tracks if track.track_id == candidate.track_id]
    if len(matching) != 1 or matching[0].class_name != candidate.class_name:
        raise ValueError("El track del candidato no aparece en su frame")
    if not any(zone.zone_id == candidate.zone_id for zone in zones):
        raise ValueError("La zona del candidato no aparece en la configuración")
    if width <= 0 or height <= 0 or width > 2048 or height > 2048:
        raise ValueError("Dimensiones de evidencia no válidas")
    scale = min(6, max(1, 600 // max(width, height)))
    canvas = np.full((height * scale, width * scale, 3), 245, dtype=np.uint8)
    for zone in zones:
        vertices = np.array(
            [[round(x * width * scale), round(y * height * scale)] for x, y in zone.polygon],
            dtype=np.int32,
        )
        cv2.polylines(canvas, [vertices], True, (110, 105, 30), 2)
    for track in tracks:
        box = track.bounding_box
        color = (150, 70, 30) if track.track_id == candidate.track_id else (120, 120, 120)
        cv2.rectangle(
            canvas,
            (round(box.x_min * scale), round(box.y_min * scale)),
            (round(box.x_max * scale), round(box.y_max * scale)),
            color,
            2,
        )
        cv2.putText(
            canvas, f"track {track.track_id}",
            (round(box.x_min * scale), max(14, round(box.y_min * scale) - 5)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1,
        )
    cv2.putText(
        canvas,
        f"SINTETICO frame {candidate.frame_index}  t={candidate.timestamp_s:.3f}s",
        (8, canvas.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (35, 35, 35), 1,
    )
    ok, encoded = cv2.imencode(".png", canvas)
    if not ok:
        raise OSError("No se pudo codificar la evidencia PNG")
    return encoded.tobytes()
