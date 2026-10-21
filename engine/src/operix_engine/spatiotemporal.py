# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Variables descriptivas por frame a partir de tracks y zonas de Operix."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import Zone
from operix_engine.tracking import Track
from operix_engine.zone_geometry import NormalizedPoint, normalized_bottom_center, point_in_zone


@dataclass(frozen=True, slots=True, order=True)
class ObjectIdentity:
    """Identidad lógica; track_id es local al tracker de cada clase."""

    class_name: str
    track_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.class_name, str) or not self.class_name.strip():
            raise ValueError("class_name debe ser texto no vacío")
        if type(self.track_id) is not int or self.track_id <= 0:
            raise ValueError("track_id debe ser entero positivo")


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
    class_name: str = "person"

    @property
    def identity(self) -> ObjectIdentity:
        return ObjectIdentity(self.class_name, self.track_id)


@dataclass(frozen=True, slots=True)
class ObjectSpatialState:
    track_id: int
    class_name: str
    frame_index: int
    timestamp_s: float
    position: NormalizedPoint
    zones: tuple[ZoneMembershipState, ...]
    trajectory: tuple[TrajectorySample, ...]
    bounding_box: BoundingBox
    confidence: float
    identity: ObjectIdentity = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", ObjectIdentity(self.class_name, self.track_id))


@dataclass(frozen=True, slots=True)
class PairwiseProximity:
    """Distancia en el plano normalizado de imagen, sin calibración métrica ni riesgo."""

    track_id_a: int
    track_id_b: int
    frame_index: int
    timestamp_s: float
    normalized_distance: float
    class_name_a: str = "person"
    class_name_b: str = "person"
    identity_a: ObjectIdentity = field(init=False)
    identity_b: ObjectIdentity = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity_a", ObjectIdentity(self.class_name_a, self.track_id_a))
        object.__setattr__(self, "identity_b", ObjectIdentity(self.class_name_b, self.track_id_b))


@dataclass(frozen=True, slots=True)
class FrameSpatialState:
    """Observaciones multiclase; los IDs numéricos no son globales."""

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
        self._last_seen: dict[ObjectIdentity, int] = {}
        self._trajectories: dict[ObjectIdentity, deque[TrajectorySample]] = {}
        self._dwell_starts: dict[tuple[ObjectIdentity, str], int] = {}

    def update(self, frame_index: int, tracks: tuple[Track, ...]) -> FrameSpatialState:
        """Calcula variables para un frame; un gap rompe toda continuidad."""
        if type(frame_index) is not int or frame_index < 0:
            raise ValueError("frame_index debe ser entero no negativo")
        if self._last_frame_index is not None and frame_index <= self._last_frame_index:
            raise ValueError("frame_index debe avanzar estrictamente")
        if not isinstance(tracks, tuple) or not all(isinstance(track, Track) for track in tracks):
            raise TypeError("tracks debe ser una tupla de Track")
        ids = [ObjectIdentity(track.class_name, track.track_id) for track in tracks]
        if len(ids) != len(set(ids)):
            raise ValueError("Identidad de objeto duplicado en el frame")

        # Validar todas las cajas y zonas antes de cambiar el estado interno.
        prepared = tuple(
            (
                track,
                position := normalized_bottom_center(track.bounding_box, self.width, self.height),
                tuple((zone.zone_id, point_in_zone(position, zone)) for zone in self.zones),
            )
            for track in sorted(tracks, key=lambda item: ObjectIdentity(item.class_name, item.track_id))
        )

        if self._last_frame_index is not None and frame_index != self._last_frame_index + 1:
            self._last_seen.clear()
            self._trajectories.clear()
            self._dwell_starts.clear()

        present = set(ids)
        for identity in tuple(self._last_seen):
            if identity not in present:
                del self._last_seen[identity]
                del self._trajectories[identity]
        for key in tuple(self._dwell_starts):
            if key[0] not in present:
                del self._dwell_starts[key]

        timestamp_s = frame_index / self.fps
        objects = []
        for track, position, memberships in prepared:
            track_id = track.track_id
            identity = ObjectIdentity(track.class_name, track_id)
            previous_frame = self._last_seen.get(identity)
            if previous_frame != frame_index - 1:
                self._trajectories[identity] = deque(maxlen=self.max_trajectory_points)
                for key in tuple(self._dwell_starts):
                    if key[0] == identity:
                        del self._dwell_starts[key]

            history = self._trajectories[identity]
            history.append(TrajectorySample(frame_index, timestamp_s, position))
            self._last_seen[identity] = frame_index

            zone_states = []
            for zone_id, inside in memberships:
                key = (identity, zone_id)
                if inside:
                    start = self._dwell_starts.setdefault(key, frame_index)
                    dwell_time_s = (frame_index - start) / self.fps
                else:
                    self._dwell_starts.pop(key, None)
                    dwell_time_s = 0.0
                zone_states.append(
                    ZoneMembershipState(
                        track_id, zone_id, frame_index, timestamp_s, inside, dwell_time_s,
                        track.class_name,
                    )
                )
            objects.append(
                ObjectSpatialState(
                    track_id, track.class_name, frame_index, timestamp_s,
                    position, tuple(zone_states), tuple(history), track.bounding_box, track.confidence,
                )
            )

        proximities = tuple(
            PairwiseProximity(
                left.track_id, right.track_id, frame_index, timestamp_s,
                math.dist((left.position.x, left.position.y), (right.position.x, right.position.y)),
                left.class_name, right.class_name,
            )
            for index, left in enumerate(objects)
            for right in objects[index + 1:]
        )
        self._last_frame_index = frame_index
        return FrameSpatialState(frame_index, timestamp_s, tuple(objects), proximities)
