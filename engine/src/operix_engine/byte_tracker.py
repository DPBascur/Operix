# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adaptador de ByteTrack para los tipos propios de Operix."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import numpy as np
from numpy.typing import NDArray

from operix_engine.detection import BoundingBox, Detection
from operix_engine.tracking import Track


@dataclass(frozen=True, slots=True)
class ByteTrackConfig:
    """Configuración mínima del ciclo de asociación de ByteTrack."""

    track_high_thresh: float = 0.25
    track_low_thresh: float = 0.10
    new_track_thresh: float = 0.25
    track_buffer: int = 30
    match_thresh: float = 0.80
    fuse_score: bool = True

    def __post_init__(self) -> None:
        thresholds = (
            self.track_high_thresh,
            self.track_low_thresh,
            self.new_track_thresh,
            self.match_thresh,
        )
        if not all(0 <= value <= 1 for value in thresholds):
            raise ValueError("Los umbrales de ByteTrack deben estar entre 0 y 1")
        if self.track_low_thresh > self.track_high_thresh:
            raise ValueError("track_low_thresh no puede superar track_high_thresh")
        if self.track_buffer <= 0:
            raise ValueError("track_buffer debe ser positivo")
        if not isinstance(self.fuse_score, bool):
            raise TypeError("fuse_score debe ser booleano")


class _ByteTrackInput:
    """Vista NumPy privada compatible con BYTETracker.update()."""

    def __init__(self, detections: tuple[Detection, ...]) -> None:
        if detections:
            xyxy = np.asarray(
                [
                    [
                        item.bounding_box.x_min,
                        item.bounding_box.y_min,
                        item.bounding_box.x_max,
                        item.bounding_box.y_max,
                    ]
                    for item in detections
                ],
                dtype=np.float32,
            )
            xywh = xyxy.copy()
            xywh[:, 0] = (xyxy[:, 0] + xyxy[:, 2]) / 2
            xywh[:, 1] = (xyxy[:, 1] + xyxy[:, 3]) / 2
            xywh[:, 2] = xyxy[:, 2] - xyxy[:, 0]
            xywh[:, 3] = xyxy[:, 3] - xyxy[:, 1]
        else:
            xywh = np.empty((0, 4), dtype=np.float32)
        self.xywh = xywh
        self.conf = np.asarray([item.confidence for item in detections], dtype=np.float32)
        self.cls = np.asarray([item.class_id for item in detections], dtype=np.float32)

    @classmethod
    def _from_arrays(
        cls,
        xywh: NDArray[np.float32],
        confidence: NDArray[np.float32],
        class_ids: NDArray[np.float32],
    ) -> _ByteTrackInput:
        instance = cls.__new__(cls)
        instance.xywh = np.asarray(xywh, dtype=np.float32).reshape((-1, 4))
        instance.conf = np.asarray(confidence, dtype=np.float32).reshape((-1,))
        instance.cls = np.asarray(class_ids, dtype=np.float32).reshape((-1,))
        return instance

    def __len__(self) -> int:
        return len(self.conf)

    def __getitem__(self, index: Any) -> _ByteTrackInput:
        return self._from_arrays(self.xywh[index], self.conf[index], self.cls[index])


class ByteTracker:
    """Encapsula Ultralytics ByteTrack sin filtrar ni reinterpretar clases."""

    def __init__(
        self,
        config: ByteTrackConfig | None = None,
        tracker_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self.config = config or ByteTrackConfig()
        if tracker_factory is None:
            from ultralytics.trackers.byte_tracker import BYTETracker

            tracker_factory = BYTETracker
        self._tracker_factory = tracker_factory
        self._tracker = self._create_backend()

    def _create_backend(self) -> Any:
        arguments = SimpleNamespace(
            tracker_type="bytetrack",
            track_high_thresh=self.config.track_high_thresh,
            track_low_thresh=self.config.track_low_thresh,
            new_track_thresh=self.config.new_track_thresh,
            track_buffer=self.config.track_buffer,
            match_thresh=self.config.match_thresh,
            fuse_score=self.config.fuse_score,
        )
        return self._tracker_factory(arguments)

    def update(self, detections: tuple[Detection, ...]) -> tuple[Track, ...]:
        if not isinstance(detections, tuple):
            raise TypeError("detections debe ser una tupla")
        if not all(isinstance(item, Detection) for item in detections):
            raise TypeError("detections solo puede contener objetos Detection")

        output = np.asarray(self._tracker.update(_ByteTrackInput(detections)))
        if output.size == 0:
            return ()
        output = output.reshape((-1, output.shape[-1]))

        class_names = {item.class_id: item.class_name for item in detections}
        tracks = []
        for row in output:
            if len(row) < 7:
                raise RuntimeError("ByteTrack devolvió una fila con formato inesperado")
            class_id = int(row[6])
            class_name = class_names.get(class_id, f"class_{class_id}")
            x_min, y_min, x_max, y_max = (float(value) for value in row[:4])
            tracks.append(
                Track(
                    track_id=int(row[4]),
                    class_id=class_id,
                    class_name=class_name,
                    confidence=float(row[5]),
                    bounding_box=BoundingBox(
                        max(0.0, x_min),
                        max(0.0, y_min),
                        max(0.0, x_max),
                        max(0.0, y_max),
                    ),
                )
            )
        return tuple(tracks)

    def reset(self) -> None:
        self._tracker.reset()
