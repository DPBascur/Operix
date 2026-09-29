# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Variables descriptivas por frame a partir de tracks y zonas de Operix."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from operix_engine.operational_config import Zone
from operix_engine.tracking import Track
from operix_engine.zone_geometry import NormalizedPoint, normalized_bottom_center, point_in_zone


@dataclass(frozen=True, slots=True)
class TrajectorySample:
    frame_index: int
    timestamp_s: float
    position: NormalizedPoint


@dataclass(frozen=True, slots=True)
class ZoneMembershipState:
    track_id: int
    zone_id: str
    frame_index: int
    timestamp_s: float
    inside: bool
    dwell_time_s: float


@dataclass(frozen=True, slots=True)
class ObjectSpatialState:
    track_id: int
    class_name: str
    frame_index: int
    timestamp_s: float
    position: NormalizedPoint
    zones: tuple[ZoneMembershipState, ...]
    trajectory: tuple[TrajectorySample, ...]


@dataclass(frozen=True, slots=True)
class PairwiseProximity:
    track_id_a: int
    track_id_b: int
    frame_index: int
    timestamp_s: float
    normalized_distance: float


@dataclass(frozen=True, slots=True)
class FrameSpatialState:
    frame_index: int
    timestamp_s: float
    objects: tuple[ObjectSpatialState, ...]
    proximities: tuple[PairwiseProximity, ...]


class SpatiotemporalAnalyzer:
    """Acumula solo observaciones consecutivas; no evalúa reglas ni riesgo."""

    def __init__(
        self,
        *,
        width: int,
        height: int,
        fps: float,
        zones: tuple[Zone, ...],
        max_trajectory_points: int = 60,
    ) -> None:
        if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
            raise ValueError("width y height deben ser enteros positivos")
        if type(fps) not in (int, float) or not math.isfinite(fps) or fps <= 0:
            raise ValueError("fps debe ser positivo y finito")
        if type(max_trajectory_points) is not int or max_trajectory_points <= 0:
            raise ValueError("max_trajectory_points debe ser entero positivo")
        if not isinstance(zones, tuple) or not all(isinstance(zone, Zone) for zone in zones):
            raise TypeError("zones debe ser una tupla de Zone")
        if len({zone.zone_id for zone in zones}) != len(zones):
            raise ValueError("zone_id duplicado")

        self.width = width
        self.height = height
        self.fps = float(fps)
        self.zones = zones
        self.max_trajectory_points = max_trajectory_points
        self.reset()

    def reset(self) -> None:
        """Inicia una nueva secuencia sin historial ni permanencia previa."""
        self._last_frame_index: int | None = None
        self._last_seen: dict[int, int] = {}
        self._trajectories: dict[int, deque[TrajectorySample]] = {}
        self._dwell_starts: dict[tuple[int, str], int] = {}

    def update(self, frame_index: int, tracks: tuple[Track, ...]) -> FrameSpatialState:
        """Calcula variables para un frame; un gap rompe toda continuidad."""
        if type(frame_index) is not int or frame_index < 0:
            raise ValueError("frame_index debe ser entero no negativo")
        if self._last_frame_index is not None and frame_index <= self._last_frame_index:
            raise ValueError("frame_index debe avanzar estrictamente")
        if not isinstance(tracks, tuple) or not all(isinstance(track, Track) for track in tracks):
            raise TypeError("tracks debe ser una tupla de Track")
        ids = [track.track_id for track in tracks]
        if len(ids) != len(set(ids)):
            raise ValueError("track_id duplicado en el frame")

        # Validar todas las cajas y zonas antes de cambiar el estado interno.
        prepared = tuple(
            (
                track,
                position := normalized_bottom_center(track.bounding_box, self.width, self.height),
                tuple((zone.zone_id, point_in_zone(position, zone)) for zone in self.zones),
            )
            for track in sorted(tracks, key=lambda item: item.track_id)
        )

        if self._last_frame_index is not None and frame_index != self._last_frame_index + 1:
            self._last_seen.clear()
            self._trajectories.clear()
            self._dwell_starts.clear()

        present = set(ids)
        for track_id in tuple(self._last_seen):
            if track_id not in present:
                del self._last_seen[track_id]
                del self._trajectories[track_id]
        for key in tuple(self._dwell_starts):
            if key[0] not in present:
                del self._dwell_starts[key]

        timestamp_s = frame_index / self.fps
        objects = []
        for track, position, memberships in prepared:
            track_id = track.track_id
            previous_frame = self._last_seen.get(track_id)
            if previous_frame != frame_index - 1:
                self._trajectories[track_id] = deque(maxlen=self.max_trajectory_points)
                for key in tuple(self._dwell_starts):
                    if key[0] == track_id:
                        del self._dwell_starts[key]

            history = self._trajectories[track_id]
            history.append(TrajectorySample(frame_index, timestamp_s, position))
            self._last_seen[track_id] = frame_index

            zone_states = []
            for zone_id, inside in memberships:
                key = (track_id, zone_id)
                if inside:
                    start = self._dwell_starts.setdefault(key, frame_index)
                    dwell_time_s = (frame_index - start) / self.fps
                else:
                    self._dwell_starts.pop(key, None)
                    dwell_time_s = 0.0
                zone_states.append(
                    ZoneMembershipState(
                        track_id, zone_id, frame_index, timestamp_s, inside, dwell_time_s
                    )
                )
            objects.append(
                ObjectSpatialState(
                    track_id, track.class_name, frame_index, timestamp_s,
                    position, tuple(zone_states), tuple(history),
                )
            )

        proximities = tuple(
            PairwiseProximity(
                left.track_id, right.track_id, frame_index, timestamp_s,
                math.dist((left.position.x, left.position.y), (right.position.x, right.position.y)),
            )
            for index, left in enumerate(objects)
            for right in objects[index + 1:]
        )
        self._last_frame_index = frame_index
        return FrameSpatialState(frame_index, timestamp_s, tuple(objects), proximities)
