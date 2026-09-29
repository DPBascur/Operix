# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render reutilizable de detecciones, tracks y trayectorias sobre frames OpenCV."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from operix_engine.detection import BoundingBox, Detection
from operix_engine.tracking import Track


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    """Centro observado de un track en un frame específico."""

    frame_index: int
    x: float
    y: float

    def __post_init__(self) -> None:
        if not isinstance(self.frame_index, int) or isinstance(self.frame_index, bool):
            raise TypeError("frame_index debe ser int")
        if self.frame_index < 0:
            raise ValueError("frame_index no puede ser negativo")
        if not all(math.isfinite(value) and value >= 0 for value in (self.x, self.y)):
            raise ValueError("Las coordenadas de trayectoria deben ser finitas y no negativas")


@dataclass(frozen=True, slots=True)
class VisualizationConfig:
    """Configuración visual acotada de OP-60."""

    box_thickness: int = 2
    font_scale: float = 0.55
    text_thickness: int = 2
    trajectory_thickness: int = 2
    max_trajectory_points: int = 60
    inactive_retention_frames: int = 30

    def __post_init__(self) -> None:
        integer_values = (
            self.box_thickness,
            self.text_thickness,
            self.trajectory_thickness,
            self.max_trajectory_points,
            self.inactive_retention_frames,
        )
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in integer_values
        ):
            raise TypeError("Los parámetros enteros de visualización deben ser int")
        if min(integer_values) <= 0:
            raise ValueError("Los parámetros enteros de visualización deben ser positivos")
        if not math.isfinite(self.font_scale) or self.font_scale <= 0:
            raise ValueError("font_scale debe ser positivo y finito")


class TrajectoryAccumulator:
    """Mantiene historial acotado fuera del tipo público Track."""

    def __init__(self, config: VisualizationConfig | None = None) -> None:
        self.config = config or VisualizationConfig()
        self._points: dict[int, deque[TrajectoryPoint]] = {}
        self._last_seen: dict[int, int] = {}
        self._last_frame_index: int | None = None

    def update(
        self,
        frame_index: int,
        tracks: tuple[Track, ...],
    ) -> dict[int, tuple[TrajectoryPoint, ...]]:
        """Actualiza el historial y devuelve solo trayectorias de tracks presentes."""
        if not isinstance(frame_index, int) or isinstance(frame_index, bool):
            raise TypeError("frame_index debe ser int")
        if frame_index < 0:
            raise ValueError("frame_index no puede ser negativo")
        if self._last_frame_index is not None and frame_index <= self._last_frame_index:
            raise ValueError("frame_index debe avanzar de forma estrictamente creciente")
        if not isinstance(tracks, tuple):
            raise TypeError("tracks debe ser una tupla")
        if not all(isinstance(track, Track) for track in tracks):
            raise TypeError("tracks solo puede contener objetos Track")

        active_ids = [track.track_id for track in tracks]
        if len(active_ids) != len(set(active_ids)):
            raise ValueError("Cada track_id puede aparecer una sola vez por frame")

        expired_ids = [
            track_id
            for track_id, last_seen in self._last_seen.items()
            if frame_index - last_seen > self.config.inactive_retention_frames
        ]
        for track_id in expired_ids:
            del self._points[track_id]
            del self._last_seen[track_id]

        for track in tracks:
            box = track.bounding_box
            point = TrajectoryPoint(
                frame_index=frame_index,
                x=(box.x_min + box.x_max) / 2,
                y=(box.y_min + box.y_max) / 2,
            )
            history = self._points.setdefault(
                track.track_id,
                deque(maxlen=self.config.max_trajectory_points),
            )
            history.append(point)
            self._last_seen[track.track_id] = frame_index

        self._last_frame_index = frame_index
        return {track_id: tuple(self._points[track_id]) for track_id in active_ids}

    def reset(self) -> None:
        """Elimina completamente el estado acumulado entre videos."""
        self._points.clear()
        self._last_seen.clear()
        self._last_frame_index = None


class OpenCvRenderer:
    """Anota copias de frames sin gestionar inferencia, video ni persistencia."""

    _DETECTION_COLOR = (0, 255, 0)
    _FONT = cv2.FONT_HERSHEY_SIMPLEX
    _LINE_TYPE = cv2.LINE_AA

    def __init__(self, config: VisualizationConfig | None = None) -> None:
        self.config = config or VisualizationConfig()

    def render_detections(
        self,
        frame: NDArray[np.uint8],
        detections: tuple[Detection, ...],
    ) -> NDArray[np.uint8]:
        """Dibuja clase, confianza y caja para cada detección."""
        self._validate_frame(frame)
        self._validate_items(detections, Detection, "detections")
        annotated = frame.copy()
        for detection in detections:
            self._draw_box_and_label(
                annotated,
                detection.bounding_box,
                f"{detection.class_name} {detection.confidence:.2f}",
                self._DETECTION_COLOR,
            )
        return annotated

    def render_tracks(
        self,
        frame: NDArray[np.uint8],
        tracks: tuple[Track, ...],
        trajectories: Mapping[int, Sequence[TrajectoryPoint]] | None = None,
    ) -> NDArray[np.uint8]:
        """Dibuja trayectoria, ID, clase, confianza y caja para cada track activo."""
        self._validate_frame(frame)
        self._validate_items(tracks, Track, "tracks")
        trajectory_map = {} if trajectories is None else trajectories
        self._validate_trajectories(trajectory_map)

        annotated = frame.copy()
        for track in tracks:
            color = self._track_color(track.track_id)
            self._draw_trajectory(
                annotated,
                trajectory_map.get(track.track_id, ()),
                color,
            )
        for track in tracks:
            self._draw_box_and_label(
                annotated,
                track.bounding_box,
                f"ID {track.track_id} {track.class_name} {track.confidence:.2f}",
                self._track_color(track.track_id),
            )
        return annotated

    @staticmethod
    def _validate_frame(frame: NDArray[np.uint8]) -> None:
        if not isinstance(frame, np.ndarray):
            raise TypeError("El frame debe ser un numpy.ndarray")
        if frame.dtype != np.uint8:
            raise ValueError("El frame debe usar dtype uint8")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("El frame debe tener forma (alto, ancho, 3) en BGR")
        if frame.size == 0:
            raise ValueError("El frame no puede estar vacío")

    @staticmethod
    def _validate_items(items: object, item_type: type, name: str) -> None:
        if not isinstance(items, tuple):
            raise TypeError(f"{name} debe ser una tupla")
        if not all(isinstance(item, item_type) for item in items):
            raise TypeError(f"{name} contiene un tipo no admitido")

    @staticmethod
    def _validate_trajectories(
        trajectories: Mapping[int, Sequence[TrajectoryPoint]],
    ) -> None:
        if not isinstance(trajectories, Mapping):
            raise TypeError("trajectories debe implementar Mapping")
        for track_id, points in trajectories.items():
            if not isinstance(track_id, int) or track_id <= 0:
                raise ValueError("Las claves de trajectories deben ser track_id positivos")
            if not all(isinstance(point, TrajectoryPoint) for point in points):
                raise TypeError("Las trayectorias solo pueden contener TrajectoryPoint")

    @staticmethod
    def _track_color(track_id: int) -> tuple[int, int, int]:
        return (
            64 + (track_id * 67) % 192,
            64 + (track_id * 97) % 192,
            64 + (track_id * 131) % 192,
        )

    def _draw_trajectory(
        self,
        frame: NDArray[np.uint8],
        points: Sequence[TrajectoryPoint],
        color: tuple[int, int, int],
    ) -> None:
        for previous, current in zip(points, points[1:]):
            if current.frame_index != previous.frame_index + 1:
                continue
            cv2.line(
                frame,
                (round(previous.x), round(previous.y)),
                (round(current.x), round(current.y)),
                color,
                self.config.trajectory_thickness,
                self._LINE_TYPE,
            )

    def _draw_box_and_label(
        self,
        frame: NDArray[np.uint8],
        box: BoundingBox,
        label: str,
        color: tuple[int, int, int],
    ) -> None:
        height, width = frame.shape[:2]
        left = min(width - 1, max(0, round(box.x_min)))
        top = min(height - 1, max(0, round(box.y_min)))
        right = min(width - 1, max(0, round(box.x_max)))
        bottom = min(height - 1, max(0, round(box.y_max)))
        cv2.rectangle(
            frame,
            (left, top),
            (right, bottom),
            color,
            self.config.box_thickness,
        )
        self._draw_label(frame, label, (left, top), color)

    def _draw_label(
        self,
        frame: NDArray[np.uint8],
        label: str,
        anchor: tuple[int, int],
        color: tuple[int, int, int],
    ) -> None:
        height, width = frame.shape[:2]
        (text_width, text_height), baseline = cv2.getTextSize(
            label,
            self._FONT,
            self.config.font_scale,
            self.config.text_thickness,
        )
        padding = 3
        left = min(max(0, anchor[0]), max(0, width - text_width - 2 * padding))
        if anchor[1] >= text_height + baseline + 2 * padding:
            text_baseline = anchor[1] - padding - baseline
        else:
            text_baseline = anchor[1] + text_height + padding
        text_baseline = min(
            max(text_height + padding, text_baseline),
            height - baseline - padding,
        )
        rectangle_top = max(0, text_baseline - text_height - padding)
        rectangle_bottom = min(height - 1, text_baseline + baseline + padding)
        rectangle_right = min(width - 1, left + text_width + 2 * padding)
        cv2.rectangle(
            frame,
            (left, rectangle_top),
            (rectangle_right, rectangle_bottom),
            (0, 0, 0),
            -1,
        )
        cv2.putText(
            frame,
            label,
            (left + padding, text_baseline),
            self._FONT,
            self.config.font_scale,
            color,
            self.config.text_thickness,
            self._LINE_TYPE,
        )
