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
from operix_engine.operational_config import Zone, RelationDisplayConfig
from operix_engine.tracking import Track
from operix_engine.rules import PairEventCandidate, PairRuleEvaluation, RuleFrameResult
from operix_engine.spatiotemporal import FrameSpatialState
from operix_engine.proximity_geometry import PROXIMITY_GEOMETRY_VERSION


OverlayRect = tuple[int, int, int, int]


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
    relations: RelationDisplayConfig | None = None

    def __post_init__(self) -> None:
        if self.relations is None:
            object.__setattr__(self, "relations", RelationDisplayConfig())
        elif not isinstance(self.relations, RelationDisplayConfig):
            raise TypeError("relations debe ser RelationDisplayConfig")
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
        boxes = self._object_rects(detection.bounding_box for detection in detections)
        occupied: list[OverlayRect] = []
        for detection in detections:
            self._draw_box_and_label(
                annotated,
                detection.bounding_box,
                f"{detection.class_name} {detection.confidence:.2f}",
                self._DETECTION_COLOR, occupied, boxes,
            )
        return annotated

    def render_tracks(
        self,
        frame: NDArray[np.uint8],
        tracks: tuple[Track, ...],
        trajectories: Mapping[int, Sequence[TrajectoryPoint]] | None = None,
        *,
        occupied: list[OverlayRect] | None = None,
        object_boxes: Sequence[BoundingBox] | None = None,
    ) -> NDArray[np.uint8]:
        """Dibuja trayectoria, ID y caja para cada track activo."""
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
        occupied = [] if occupied is None else occupied
        boxes = self._object_rects(
            object_boxes if object_boxes is not None else (track.bounding_box for track in tracks),
        )
        for track in tracks:
            if track.class_name == "person":
                label = f"P{track.track_id}"
            elif track.class_name == "forklift":
                label = f"F{track.track_id}"
            else:
                label = f"{track.class_name} {track.track_id}"
            self._draw_box_and_label(
                annotated,
                track.bounding_box,
                label,
                self._track_color(track.track_id, track.class_name), occupied, boxes,
            )
        return annotated

    def render_proximity(
        self, frame: NDArray[np.uint8], spatial: FrameSpatialState,
        result: RuleFrameResult | None, *, max_pairs: int | None = None, metric_expected: bool = False,
        occupied: list[OverlayRect] | None = None,
    ) -> NDArray[np.uint8]:
        """Muestra una medición por par visible y el estado de sus reglas.

        Hasta cuatro relaciones activas por defecto; emisiones del frame siempre
        visibles con la política activa. El conjunto visual no limita evaluaciones ni candidatos.
        """
        self._validate_frame(frame)
        occupied = [] if occupied is None else occupied
        display = self.config.relations
        max_pairs = display.max_pairs if max_pairs is None else max_pairs
        if type(max_pairs) is not int or max_pairs <= 0:
            raise ValueError("max_pairs debe ser entero positivo")
        if result is None:
            return self._render_observed_proximity(frame, spatial, max_pairs, metric_expected, occupied, suspended=True)
        if (spatial.frame_index, spatial.timestamp_s) != (result.frame_index, result.timestamp_s):
            raise ValueError("El overlay y las reglas deben pertenecer al mismo frame/tiempo")
        if spatial.epoch != result.epoch:
            raise ValueError("El overlay y las reglas deben pertenecer a la misma época")
        evaluations = [item for item in result.evaluations if isinstance(item, PairRuleEvaluation)]
        if not evaluations:
            return self._render_observed_proximity(frame, spatial, max_pairs, metric_expected, occupied)
        objects = {obj.identity: obj for obj in spatial.objects}
        emitted = {candidate.episode_key for candidate in result.candidates if isinstance(candidate, PairEventCandidate)}
        if any((item.frame_index, item.timestamp_s, item.epoch) !=
               (spatial.frame_index, spatial.timestamp_s, spatial.epoch)
               for item in evaluations):
            raise ValueError("La evaluación pertenece a otro frame, tiempo o época")
        evaluations.sort(key=lambda item: (
            item.episode_key not in emitted, not item.satisfied, item.observed_normalized_distance,
            item.rule_id, item.rule_version, item.interaction.person, item.interaction.forklift,
        ))
        if display.policy == "active":
            relevant = [item for item in evaluations
                        if item.episode_key is not None or item.reason == "calibration_unavailable"]
            if not relevant:
                relevant = [item for item in evaluations if item.reason in {
                    "outside_distance", "outside_zone", "motion_unknown", "equipment_stationary",
                }]
        else:
            relevant = [item for item in evaluations
                        if item.reason != "outside_zone"
                        and (display.policy == "all" or item.satisfied or item.reason == "calibration_unavailable"
                             or (item.ground["distance"] if item.ground else item.observed_normalized_distance)
                             <= item.parameters["max_distance"] * (1 + display.near_margin))]
            relevant.sort(key=lambda item: (not item.satisfied, item.observed_normalized_distance))
        visible_pairs = set(tuple(dict.fromkeys(item.interaction for item in relevant))[:max_pairs])
        selected = [item for item in relevant if item.interaction in visible_pairs
                    or (display.policy == "active" and item.episode_key in emitted)]
        annotated = frame.copy()
        ground_by_pair = {frozenset((pair.identity_a, pair.identity_b)): pair.ground for pair in spatial.proximities}
        labels = []
        displayed = set()
        normalized = False
        for item in selected:
            if (item.proximity_geometry_version != PROXIMITY_GEOMETRY_VERSION
                    or item.person_anchor is None or item.equipment_target is None):
                raise ValueError("El overlay requiere los puntos geométricos versionados de la regla")
            person, forklift = item.interaction.person, item.interaction.forklift
            if person not in objects or forklift not in objects:
                raise ValueError("La relación no corresponde a objetos presentes")
            identity = f"P{person.track_id}/F{forklift.track_id}"
            ground = ground_by_pair.get(frozenset((person, forklift)), item.ground)
            color = self._ZONE_EVENT_COLOR if item.satisfied else self._ZONE_NORMAL_COLOR
            if item.interaction not in displayed:
                displayed.add(item.interaction)
                normalized |= ground is None
                labels.append(self._draw_pair_line(
                    annotated, identity, ground, (item.person_anchor, item.equipment_target),
                    item.observed_normalized_distance, color,
                ))
        total_pairs = len({item.interaction for item in relevant})
        notice = self._normalized_notice(metric_expected) if normalized else None
        self._draw_pair_overlays(annotated, spatial, labels, total_pairs, notice, occupied)
        return annotated

    def _render_observed_proximity(self, frame, spatial, max_pairs, metric_expected, occupied, *, suspended=False):
        # El analizador ya mide los pares con o sin una regla de proximidad activa.
        pairs = sorted(
            (pair for pair in spatial.proximities
             if {pair.class_name_a, pair.class_name_b} == {"person", "forklift"}
             and pair.geometry_version == PROXIMITY_GEOMETRY_VERSION
             and pair.point_a is not None and pair.point_b is not None),
            key=lambda pair: (metric_expected and pair.ground is None,
                              pair.normalized_distance, pair.identity_a, pair.identity_b),
        )
        annotated = frame.copy()
        color = self._ZONE_NORMAL_COLOR
        labels = []
        for pair in pairs[:max_pairs]:
            person_first = pair.class_name_a == "person"
            person, forklift = ((pair.track_id_a, pair.track_id_b) if person_first
                                else (pair.track_id_b, pair.track_id_a))
            labels.append(self._draw_pair_line(
                annotated, f"P{person}/F{forklift}", None if suspended else pair.ground,
                (pair.point_a, pair.point_b), pair.normalized_distance, color,
            ))
        notice = None
        if suspended:
            notice = "Encuadre sin validar"
        elif any(pair.ground is None for pair in pairs[:max_pairs]) or not metric_expected:
            notice = self._normalized_notice(metric_expected)
        self._draw_pair_overlays(annotated, spatial, labels, len(pairs), notice, occupied)
        return annotated

    @staticmethod
    def _normalized_notice(metric_expected):
        return "Fuera del plano" if metric_expected else "Sin calibracion metrica"

    def _draw_pair_line(self, frame, identity, ground, normalized_points, normalized_distance, color):
        height, width = frame.shape[:2]
        if ground is not None:
            points = (ground["person_anchor"], ground["equipment_target"])
            meters = ground["distance"]
            # Hershey de OpenCV admite el indicador ASCII de aproximación.
            measure = (f"~{meters * 100:.0f} cm" if meters < 1 else f"~{meters:.2f} m").replace(".", ",")
        else:
            points = tuple((point.x, point.y) for point in normalized_points)
            value = f"{normalized_distance:.4g}".replace(".", ",")
            measure = f"{value} norm."
        endpoints = tuple((min(width - 1, max(0, round(x * width))),
                           min(height - 1, max(0, round(y * height)))) for x, y in points)
        cv2.line(frame, *endpoints, color, self.config.box_thickness, self._LINE_TYPE)
        for point in endpoints:
            cv2.circle(frame, point, 4, color, -1, self._LINE_TYPE)
        midpoint = tuple(round((a + b) / 2) for a, b in zip(*endpoints))
        return f"{identity}  {measure}", midpoint, color, endpoints

    def _draw_pair_overlays(self, frame, spatial, labels, total_pairs, notice, occupied):
        boxes = self._object_rects(obj.bounding_box for obj in spatial.objects)
        shown = 0
        for label, midpoint, color, endpoints in labels:
            shown += self._draw_tag(
                frame, label, color, midpoint, occupied, boxes, placement="pair", line=endpoints,
            )
        if shown == total_pairs == 1:
            summary = "1 par observado"
        elif shown == total_pairs:
            summary = f"{total_pairs} pares observados"
        else:
            summary = f"Pares visibles: {shown}/{total_pairs}"
        # Una sola placa de estado, siempre después de las mediciones.
        status = f"{notice} | {summary}" if notice else summary
        if not self._draw_tag(frame, status, None, (0, 0), occupied, boxes, placement="hud") and notice:
            self._draw_tag(frame, notice, None, (0, 0), occupied, boxes, placement="hud")
            self._draw_tag(frame, summary, None, (0, 0), occupied, boxes, placement="hud")

    @staticmethod
    def _object_rects(boxes):
        return [(math.floor(box.x_min), math.floor(box.y_min),
                 math.ceil(box.x_max) + 1, math.ceil(box.y_max) + 1) for box in boxes]

    @staticmethod
    def _overlaps(first: OverlayRect, second: OverlayRect) -> bool:
        x1, y1, x2, y2 = first
        left, top, right, bottom = second
        return x1 < right and x2 > left and y1 < bottom and y2 > top

    def _draw_tag(self, frame, label, color, anchor, occupied, boxes, *, placement="object", line=None):
        height, width = frame.shape[:2]
        # Escala con el lado corto, de forma sublineal y acotada para UHD.
        media_scale = max(.62, (min(width, height) / 490) ** .82)
        scale = min(1.76, self.config.font_scale * media_scale)
        if placement == "hud":
            scale *= .88
        thickness = min(3, max(1, round(scale * self.config.text_thickness * .78)))
        pad_x, pad_y = max(2, round(5 * scale)), max(1, round(2.8 * scale))
        gap = max(2, round(5 * scale))
        inset = pad_x + (2 * pad_y + gap if color is not None else 0)
        (text_w, text_h), baseline = cv2.getTextSize(label, self._FONT, scale, thickness)
        if placement == "zone":
            available = min(width - 2 * gap, width // 2) - inset - pad_x
            if text_w > available:
                ellipsis = "..."
                ellipsis_w = cv2.getTextSize(ellipsis, self._FONT, scale, thickness)[0][0]
                label = label[:max(1, int(len(label) * max(0, available - ellipsis_w) / text_w))]
                while label and cv2.getTextSize(label, self._FONT, scale, thickness)[0][0] > available - ellipsis_w:
                    label = label[:-1]
                label = label.rstrip() + ellipsis if label else ""
                (text_w, text_h), baseline = cv2.getTextSize(label, self._FONT, scale, thickness)
        tag_w, tag_h = text_w + inset + pad_x, text_h + baseline + 2 * pad_y
        max_left, max_top = width - tag_w - gap, height - tag_h - gap
        if not label or max_left < gap or max_top < gap:
            return False

        if placement == "hud":
            positions = ((gap, gap), (max_left, gap), (gap, max_top), (max_left, max_top))
        elif placement == "pair":
            x, y = anchor
            center = x - tag_w // 2
            step = tag_h + gap
            positions = (
                (left, top)
                for offset in range(5)
                for left in (center, center - tag_w // 2, center + tag_w // 2, x - tag_w - gap, x + gap)
                for top in (y + gap + offset * step, y - tag_h - gap - offset * step)
            )
        else:
            left, top, right, bottom = anchor
            positions = ((left, top - tag_h - gap), (left, bottom + gap),
                         (right + gap, top), (left - tag_w - gap, top),
                         (right + gap, bottom - tag_h), (left - tag_w - gap, bottom - tag_h))

        for left, top in positions:
            left, top = min(max_left, max(gap, left)), min(max_top, max(gap, top))
            rect = (left, top, left + tag_w, top + tag_h)
            if any(self._overlaps(rect, other) for other in occupied) or any(
                self._overlaps(rect, box) for box in boxes
            ):
                continue
            if line is not None and cv2.clipLine((left, top, tag_w, tag_h), *line)[0]:
                continue
            occupied.append(rect)
            self._paint_tag(frame, rect, alpha=.70 if placement == "hud" else .78)
            if color is not None:
                cv2.circle(frame, (left + pad_x + pad_y, top + tag_h // 2), pad_y, color, -1, self._LINE_TYPE)
            cv2.putText(frame, label, (left + inset, top + pad_y + text_h),
                        self._FONT, scale, (245, 247, 250), thickness, self._LINE_TYPE)
            return True
        return False

    @staticmethod
    def _paint_tag(frame, rect: OverlayRect, *, alpha: float) -> None:
        left, top, right, bottom = rect
        region = frame[top:bottom, left:right]
        h, w = region.shape[:2]
        radius = max(2, h // 4)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.rectangle(mask, (radius, 0), (w - 1 - radius, h - 1), 255, -1)
        cv2.rectangle(mask, (0, radius), (w - 1, h - 1 - radius), 255, -1)
        for x in (radius, w - 1 - radius):
            for y in (radius, h - 1 - radius):
                cv2.circle(mask, (x, y), radius, 255, -1)
        solid = np.empty_like(region)
        solid[:] = (25, 22, 19)
        cv2.copyTo(cv2.addWeighted(region, 1 - alpha, solid, alpha, 0), mask, region)

    def render_zone(
        self,
        frame: NDArray[np.uint8],
        zone: Zone,
        *,
        event: bool = False,
        rule_kind: str | None = None,
        frame_index: int | None = None,
        occupied: list[OverlayRect] | None = None,
        object_boxes: Sequence[BoundingBox] = (),
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
        self._draw_zone_labels(
            annotated, zone.name, points, color, rule_kind, frame_index,
            [] if occupied is None else occupied, self._object_rects(object_boxes),
        )
        return annotated

    def _draw_zone_labels(self, frame, name, points, color, rule_kind, frame_index, occupied, boxes):
        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        lines = [name]
        if rule_kind is not None:
            lines.append(f"Regla: {rule_kind}")
        if frame_index is not None:
            lines.append(f"Frame {frame_index}")
        top_vertex = min(points, key=lambda point: (point[1], point[0]))
        left, top = (int(value) for value in top_vertex)
        anchor = (left, top, left, top)
        for index, label in enumerate(lines):
            placement = "zone" if index == 0 else "object"
            if self._draw_tag(frame, label, color, anchor, occupied, boxes, placement=placement):
                _, _, _, bottom = occupied[-1]
                anchor = (left, bottom, left, bottom)

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
        occupied: list[OverlayRect],
        boxes: list[OverlayRect],
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
        self._draw_tag(frame, label, color, (left, top, right, bottom), occupied, boxes)
