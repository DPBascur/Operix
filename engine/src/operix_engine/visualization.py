# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render reutilizable de detecciones, tracks y trayectorias sobre frames OpenCV."""

from __future__ import annotations

import math
import unicodedata
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from operix_engine.detection import BoundingBox, Detection
from operix_engine.operational_config import Zone
from operix_engine.tracking import Track
from operix_engine.rules import PairEventCandidate, PairRuleEvaluation, RuleFrameResult
from operix_engine.spatiotemporal import FrameSpatialState


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
    _ZONE_NORMAL_COLOR = (230, 190, 0)  # BGR: cyan discreto.
    _ZONE_EVENT_COLOR = (0, 190, 255)  # BGR: ámbar, no rojo.
    _ZONE_FILL_ALPHA = 0.08

    def __init__(self, config: VisualizationConfig | None = None) -> None:
        self.config = config or VisualizationConfig()
        # Caché acotada a la última geometría; no retiene frames ni estado lógico.
        self._zone_geometry_key = None
        self._zone_geometry_buffers = None

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
            color = self._track_color(track.track_id, track.class_name)
            self._draw_trajectory(
                annotated,
                trajectory_map.get(track.track_id, ()),
                color,
            )
        for track in tracks:
            if track.class_name == "person":
                label = f"Person P-{track.track_id} {track.confidence:.2f}"
            elif track.class_name == "forklift":
                label = f"Forklift F-{track.track_id} {track.confidence:.2f}"
            else:
                label = f"ID {track.track_id} {track.class_name} {track.confidence:.2f}"
            self._draw_box_and_label(
                annotated,
                track.bounding_box,
                label,
                self._track_color(track.track_id, track.class_name),
            )
        return annotated

    def render_proximity(
        self, frame: NDArray[np.uint8], spatial: FrameSpatialState,
        result: RuleFrameResult, *, max_pairs: int = 4,
    ) -> NDArray[np.uint8]:
        """Muestra episodios evaluados, sin geometría/distancia/estado alternativos.

        Hasta cuatro relaciones activas por defecto; emisiones del frame siempre
        visibles. El conjunto visual no limita evaluaciones ni candidatos.
        """
        self._validate_frame(frame)
        if type(max_pairs) is not int or max_pairs <= 0:
            raise ValueError("max_pairs debe ser entero positivo")
        if (spatial.frame_index, spatial.timestamp_s) != (result.frame_index, result.timestamp_s):
            raise ValueError("El overlay y las reglas deben pertenecer al mismo frame/tiempo")
        objects = {obj.identity: obj for obj in spatial.objects}
        emitted = {candidate.episode_key for candidate in result.candidates if isinstance(candidate, PairEventCandidate)}
        relevant = [evaluation for evaluation in result.evaluations
                    if isinstance(evaluation, PairRuleEvaluation) and evaluation.episode_key is not None]
        if any((item.frame_index, item.timestamp_s) != (result.frame_index, result.timestamp_s) for item in relevant):
            raise ValueError("La evaluación de proximidad pertenece a otro frame/tiempo")
        relevant.sort(key=lambda item: (
            item.episode_key not in emitted, not item.satisfied, item.observed_normalized_distance,
            item.rule_id, item.rule_version, item.interaction.person, item.interaction.forklift,
        ))
        selected = [item for index, item in enumerate(relevant)
                    if index < max_pairs or item.episode_key in emitted]
        annotated = frame.copy()
        height, width = frame.shape[:2]
        for index, item in enumerate(selected):
            left, right = (objects.get(identity) for identity in (item.interaction.person, item.interaction.forklift))
            if left is None or right is None:
                raise ValueError("La relación no corresponde a objetos presentes")
            # El analizador normaliza con width/height, no con width-1/height-1.
            endpoints = tuple((min(width - 1, max(0, round(obj.position.x * width))),
                               min(height - 1, max(0, round(obj.position.y * height)))) for obj in (left, right))
            color = self._ZONE_EVENT_COLOR if item.satisfied else self._ZONE_NORMAL_COLOR
            cv2.line(annotated, *endpoints, color, self.config.box_thickness, self._LINE_TYPE)
            for point in endpoints:
                cv2.circle(annotated, point, 4, color, -1, self._LINE_TYPE)
            midpoint = tuple(round((a + b) / 2) for a, b in zip(*endpoints))
            self._draw_label(annotated,
                f"P#{left.track_id} F#{right.track_id}: {item.observed_normalized_distance:.3f} norm",
                midpoint, color, fit_width=True)
            # Carril de trazabilidad separado de la medida junto a la línea.
            labels = (f"{item.rule_id} v{item.rule_version} | P#{left.track_id} F#{right.track_id}",
                      f"max {item.parameters['max_distance']:g} norm | {item.observed_duration_s:.2f}s"
                      f" / {item.parameters['minimum_duration_seconds']:g}s | {item.rule_state}")
            for row, label in enumerate(labels):
                self._draw_label(annotated, label, (8, 28 + index * 52 + row * 24), color, fit_width=True)
        if len(selected) < len(relevant):
            self._draw_label(annotated, f"Relaciones visibles: {len(selected)}/{len(relevant)}",
                             (8, 28 + len(selected) * 52), self._ZONE_NORMAL_COLOR, fit_width=True)
        return annotated

    def render_zone(
        self,
        frame: NDArray[np.uint8],
        zone: Zone,
        *,
        event: bool = False,
        rule_kind: str | None = None,
        frame_index: int | None = None,
    ) -> NDArray[np.uint8]:
        """Dibuja una zona configurada sin cambiar su geometría ni el frame original."""
        self._validate_frame(frame)
        if not isinstance(zone, Zone):
            raise TypeError("zone debe ser Zone")
        if not isinstance(event, bool):
            raise TypeError("event debe ser bool")
        if rule_kind is not None and (not isinstance(rule_kind, str) or not rule_kind.strip()):
            raise ValueError("rule_kind debe ser texto no vacío")
        if frame_index is not None and (
            type(frame_index) is not int or frame_index < 0
        ):
            raise ValueError("frame_index debe ser entero no negativo")

        height, width = frame.shape[:2]
        geometry_key = (height, width, tuple(zone.polygon))
        if geometry_key != self._zone_geometry_key:
            points = np.asarray(
                [(round(x * (width - 1)), round(y * (height - 1))) for x, y in zone.polygon],
                dtype=np.int32,
            )
            x, y, box_width, box_height = cv2.boundingRect(points)
            full_mask = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(full_mask, [points], 255)
            mask = full_mask[y:y + box_height, x:x + box_width].copy()
            solids = {}
            for fill_color in (self._ZONE_NORMAL_COLOR, self._ZONE_EVENT_COLOR):
                solid = np.empty((box_height, box_width, 3), dtype=np.uint8)
                solid[:] = fill_color
                solids[fill_color] = solid
            self._zone_geometry_key = geometry_key
            self._zone_geometry_buffers = (points, x, y, box_width, box_height, mask, solids)
        points, x, y, box_width, box_height, mask, solids = self._zone_geometry_buffers
        color = self._ZONE_EVENT_COLOR if event else self._ZONE_NORMAL_COLOR
        annotated = frame.copy()
        region = annotated[y:y + box_height, x:x + box_width]
        blended = cv2.addWeighted(
            region, 1 - self._ZONE_FILL_ALPHA, solids[color], self._ZONE_FILL_ALPHA, 0,
        )
        cv2.copyTo(blended, mask, region)
        cv2.polylines(annotated, [points], True, color, 2, self._LINE_TYPE)
        self._draw_zone_label(annotated, zone.name, points, rule_kind, frame_index)
        return annotated

    def _draw_zone_label(
        self,
        frame: NDArray[np.uint8],
        name: str,
        points: NDArray[np.int32],
        rule_kind: str | None,
        frame_index: int | None,
    ) -> None:
        """Etiqueta pequeña, legible sin soporte de fuentes externas a OpenCV."""
        height, width = frame.shape[:2]
        if width < 100 or height < 50:
            return
        lines = [unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()]
        details = []
        if rule_kind is not None:
            details.append(f"Regla: {rule_kind}")
        if frame_index is not None:
            details.append(f"Frame {frame_index}")
        scale = 0.65 if width >= 640 else 0.48
        line_height = 23 if width >= 640 else 17
        thickness = 1
        max_text_width = width - 20
        if details:
            combined = " | ".join(details)
            if cv2.getTextSize(combined, self._FONT, scale, thickness)[0][0] <= max_text_width:
                lines.append(combined)
            else:
                lines.extend(details)
        for index, line in enumerate(lines):
            while line and cv2.getTextSize(line, self._FONT, scale, thickness)[0][0] > max_text_width:
                line = line[:-1]
            lines[index] = line
        text_width = max(cv2.getTextSize(line, self._FONT, scale, thickness)[0][0] for line in lines)
        plaque_width = text_width + 14
        plaque_height = len(lines) * line_height + 8
        left = min(max(4, int(points[:, 0].min()) + 8), width - plaque_width - 4)
        top = min(max(4, int(points[:, 1].min()) + 8), height - plaque_height - 4)
        cv2.rectangle(
            frame, (left, top), (left + plaque_width, top + plaque_height),
            (22, 24, 26), -1,
        )
        for index, line in enumerate(lines):
            cv2.putText(
                frame, line, (left + 7, top + line_height + index * line_height),
                self._FONT, scale, (245, 245, 245), thickness, self._LINE_TYPE,
            )

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
    def _track_color(track_id: int, class_name: str = "person") -> tuple[int, int, int]:
        if class_name == "forklift":
            return (40, 155, 235)  # BGR: ámbar suave, separado del cyan de zona.
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
        *, fit_width: bool = False,
    ) -> None:
        height, width = frame.shape[:2]
        (text_width, text_height), baseline = cv2.getTextSize(
            label,
            self._FONT,
            self.config.font_scale,
            self.config.text_thickness,
        )
        font_scale = self.config.font_scale
        if fit_width and text_width > max(1, width - 14):
            font_scale *= max(1, width - 14) / text_width
            (text_width, text_height), baseline = cv2.getTextSize(
                label, self._FONT, font_scale, self.config.text_thickness,
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
            font_scale,
            color,
            self.config.text_thickness,
            self._LINE_TYPE,
        )
