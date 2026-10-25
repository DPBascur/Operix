# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evaluación de reglas configuradas sobre variables descriptivas de OP-37.

Los candidatos son transitorios: este módulo no clasifica riesgos ni persiste eventos.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from operix_engine.operational_config import OperationalConfig, RuleConfig
from operix_engine.spatiotemporal import FrameSpatialState, ObjectIdentity
from operix_engine.zone_geometry import NormalizedPoint
from operix_engine.proximity_geometry import PROXIMITY_GEOMETRY_VERSION


# Tolerancia exclusivamente numérica en segundos; no es una gracia operacional.
_TEMPORAL_ABS_TOLERANCE_S = 1e-9


def _duration_reached(elapsed_s: float, minimum_s: float) -> bool:
    """Comparación inclusiva sin retrasar la igualdad por representación float."""
    return elapsed_s > minimum_s or math.isclose(
        elapsed_s, minimum_s, rel_tol=0.0, abs_tol=_TEMPORAL_ABS_TOLERANCE_S
    )


class RuleEngineError(ValueError):
    """Configuración de regla o secuencia de frames no válida."""


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    rule_id: str
    rule_version: int
    frame_index: int
    timestamp_s: float
    track_id: int
    class_name: str
    zone_id: str
    parameters: Mapping[str, object]
    observed_inside: bool | None
    observed_dwell_time_s: float | None
    evaluated: bool
    satisfied: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class EventCandidate:
    """Condición configurada satisfecha; no es un evento persistido ni un Near Miss."""

    rule_id: str
    rule_version: int
    frame_index: int
    timestamp_s: float
    track_id: int
    class_name: str
    zone_id: str
    parameters: Mapping[str, object]
    observed_inside: bool
    observed_dwell_time_s: float


@dataclass(frozen=True, slots=True)
class InteractionIdentity:
    """Par con roles explícitos; los IDs numéricos son locales a cada clase."""

    person: ObjectIdentity
    forklift: ObjectIdentity


@dataclass(frozen=True, slots=True)
class PairRuleEvaluation:
    rule_id: str
    rule_version: int
    frame_index: int
    timestamp_s: float
    interaction: InteractionIdentity
    zone_id: str
    parameters: Mapping[str, object]
    observed_normalized_distance: float
    observed_duration_s: float
    satisfied: bool
    reason: str | None
    started_frame_index: int | None = None
    started_timestamp_s: float | None = None
    proximity_geometry_version: str | None = None
    person_anchor: NormalizedPoint | None = None
    equipment_target: NormalizedPoint | None = None

    @property
    def episode_key(self) -> tuple | None:
        """Identidad local al run; no sustituye la identidad persistida del evento."""
        if self.started_frame_index is None:
            return None
        return (self.rule_id, self.rule_version, self.interaction, self.zone_id, self.started_frame_index)

    @property
    def rule_state(self) -> str:
        if self.satisfied:
            return "CONDITION_SATISFIED"
        return "DURATION_ACCUMULATING" if self.reason == "insufficient_duration" else "OBSERVED"


@dataclass(frozen=True, slots=True)
class PairEventCandidate:
    """Interés preventivo para revisión humana; únicamente en memoria, sin persistencia."""

    rule_id: str
    rule_version: int
    frame_index: int
    timestamp_s: float
    interaction: InteractionIdentity
    zone_id: str
    parameters: Mapping[str, object]
    started_frame_index: int
    started_timestamp_s: float
    observed_normalized_distance: float
    observed_duration_s: float

    proximity_geometry_version: str | None = None
    person_anchor: NormalizedPoint | None = None
    equipment_target: NormalizedPoint | None = None

    @property
    def proximity_geometry(self) -> dict | None:
        if self.proximity_geometry_version is None:
            if self.person_anchor is not None or self.equipment_target is not None:
                raise ValueError("Los puntos requieren versión geométrica")
            return None  # Candidatos históricos/manuales sin geometría versionada.
        if (self.proximity_geometry_version != PROXIMITY_GEOMETRY_VERSION
                or not isinstance(self.person_anchor, NormalizedPoint)
                or not isinstance(self.equipment_target, NormalizedPoint)):
            raise ValueError("Snapshot geométrico incompleto o no soportado")
        return {"version": self.proximity_geometry_version,
                "person_anchor": [self.person_anchor.x, self.person_anchor.y],
                "equipment_target": [self.equipment_target.x, self.equipment_target.y]}

    @property
    def episode_key(self) -> tuple:
        return (self.rule_id, self.rule_version, self.interaction, self.zone_id, self.started_frame_index)

    @property
    def candidate_type(self) -> str:
        return "person_forklift_proximity"

    @property
    def reason(self) -> str:
        return "Interacción person-forklift con proximidad sostenida; requiere revisión humana"

    def to_dict(self) -> dict[str, object]:
        """Serialización explicable; no convierte el candidato al contrato HTTP de eventos."""
        return {
            "candidate_type": self.candidate_type,
            "rule_id": self.rule_id, "rule_version": self.rule_version,
            "frame_index": self.frame_index, "timestamp_s": self.timestamp_s,
            "interaction": {
                role: {"class_name": identity.class_name, "track_id": identity.track_id}
                for role, identity in (("person", self.interaction.person),
                                       ("forklift", self.interaction.forklift))
            },
            "zone_id": self.zone_id, "parameters": dict(self.parameters),
            "started_frame_index": self.started_frame_index,
            "started_timestamp_s": self.started_timestamp_s,
            "observed_normalized_distance": self.observed_normalized_distance,
            "observed_duration_s": self.observed_duration_s,
            "reason": self.reason,
            **({"proximity_geometry": self.proximity_geometry} if self.proximity_geometry is not None else {}),
        }


@dataclass(frozen=True, slots=True)
class RuleFrameResult:
    frame_index: int
    timestamp_s: float
    evaluations: tuple[RuleEvaluation | PairRuleEvaluation, ...]
    candidates: tuple[EventCandidate | PairEventCandidate, ...]


@dataclass(frozen=True, slots=True)
class _ZoneDwellRule:
    config: RuleConfig
    class_name: str
    zone_id: str
    min_duration_s: float
    parameters: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _PairProximityRule:
    config: RuleConfig
    person_class: str
    forklift_class: str
    zone_id: str
    max_distance: float
    minimum_duration_seconds: float
    parameters: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _PairEpisode:
    started_frame_index: int
    started_timestamp_s: float
    triggered: bool


def _validate_pair_rule(rule: RuleConfig, zone_ids: set[str]) -> _PairProximityRule:
    # No hay distancia/duración industrial por defecto: la configuración debe declararlas.
    required = {"kind", "zone_id", "max_distance", "minimum_duration_seconds"}
    optional = {"person_class", "forklift_class"}
    values = dict(rule.parameters)
    if required - values.keys() or values.keys() - (required | optional):
        raise RuleEngineError(f"{rule.rule_id}: parámetros de proximidad faltantes o desconocidos")
    values.setdefault("person_class", "person")
    values.setdefault("forklift_class", "forklift")
    for name in ("person_class", "forklift_class", "zone_id"):
        if not isinstance(values[name], str) or not values[name].strip():
            raise RuleEngineError(f"{rule.rule_id}: {name} debe ser texto no vacío")
    if values["person_class"] == values["forklift_class"]:
        raise RuleEngineError(f"{rule.rule_id}: las clases de los dos roles deben ser distintas")
    if values["zone_id"] not in zone_ids:
        raise RuleEngineError(f"{rule.rule_id}: zone_id debe identificar una zona configurada")
    for name in ("max_distance", "minimum_duration_seconds"):
        value = values[name]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise RuleEngineError(f"{rule.rule_id}: {name} debe ser finito y >= 0")
    return _PairProximityRule(
        rule, values["person_class"], values["forklift_class"], values["zone_id"],
        float(values["max_distance"]), float(values["minimum_duration_seconds"]),
        MappingProxyType(values),
    )


def _validate_rule(rule: RuleConfig, zone_ids: set[str]) -> _ZoneDwellRule | _PairProximityRule:
    if rule.parameters.get("kind") == "person_forklift_proximity":
        return _validate_pair_rule(rule, zone_ids)
    expected = {"kind", "class_name", "zone_id", "min_duration_s"}
    actual = set(rule.parameters)
    if actual != expected:
        raise RuleEngineError(
            f"{rule.rule_id}: parámetros faltantes {sorted(expected - actual)}; "
            f"desconocidos {sorted(actual - expected)}"
        )
    values = rule.parameters
    if values["kind"] != "zone_dwell":
        raise RuleEngineError(f"{rule.rule_id}: kind no soportado")
    class_name = values["class_name"]
    zone_id = values["zone_id"]
    duration = values["min_duration_s"]
    if not isinstance(class_name, str) or not class_name.strip():
        raise RuleEngineError(f"{rule.rule_id}: class_name debe ser texto no vacío")
    if not isinstance(zone_id, str) or not zone_id.strip() or zone_id not in zone_ids:
        raise RuleEngineError(f"{rule.rule_id}: zone_id debe identificar una zona configurada")
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
        raise RuleEngineError(f"{rule.rule_id}: min_duration_s debe ser finito y >= 0")
    return _ZoneDwellRule(
        rule, class_name, zone_id, float(duration), MappingProxyType(dict(values))
    )


class RuleEngine:
    """Evalúa una configuración fija durante una sesión de frames consecutivos.

    Una configuración nueva requiere una nueva instancia; reset() inicia otra sesión
    con la misma configuración. Las ausencias y los gaps rearman la condición.
    """

    def __init__(self, config: OperationalConfig) -> None:
        if not isinstance(config, OperationalConfig):
            raise TypeError("config debe ser OperationalConfig")
        zone_ids = {zone.zone_id for zone in config.zones}
        self._rules = tuple(_validate_rule(rule, zone_ids) for rule in config.rules)
        self.reset()

    def reset(self) -> None:
        """Olvida activaciones y orden temporal al comenzar una sesión nueva."""
        self._last_frame_index: int | None = None
        self._active: set[tuple[str, int, ObjectIdentity, str]] = set()
        self._pair_episodes: dict[tuple[str, int, InteractionIdentity, str], _PairEpisode] = {}
        self._last_timestamp_s: float | None = None

    def _evaluate_pair_rule(
        self,
        rule: _PairProximityRule,
        frame: FrameSpatialState,
        previous: dict[tuple[str, int, InteractionIdentity, str], _PairEpisode],
        episodes: dict[tuple[str, int, InteractionIdentity, str], _PairEpisode],
    ) -> tuple[list[PairRuleEvaluation], list[PairEventCandidate]]:
        """Consume membresías/distancias ya calculadas; no recalcula geometría."""
        evaluations, candidates = [], []
        if not rule.config.enabled:
            return evaluations, candidates
        objects = {obj.identity: obj for obj in frame.objects}
        for proximity in frame.proximities:
            a, b = proximity.identity_a, proximity.identity_b
            if a.class_name == rule.person_class and b.class_name == rule.forklift_class:
                interaction = InteractionIdentity(a, b)
            elif b.class_name == rule.person_class and a.class_name == rule.forklift_class:
                interaction = InteractionIdentity(b, a)
            else:
                continue
            if (proximity.geometry_version != PROXIMITY_GEOMETRY_VERSION
                    or proximity.point_a is None or proximity.point_b is None):
                raise RuleEngineError("La regla requiere geometría ground-edge y roles configurados en el analizador")
            person_anchor, equipment_target = (proximity.point_a, proximity.point_b)
            if a != interaction.person:
                person_anchor, equipment_target = equipment_target, person_anchor
            members = tuple(objects.get(identity) for identity in
                            (interaction.person, interaction.forklift))
            memberships = tuple(
                next((zone for zone in obj.zones if zone.zone_id == rule.zone_id), None)
                if obj is not None else None for obj in members
            )
            distance = proximity.normalized_distance
            if any(obj is None for obj in members):
                reason = "object_missing"
            elif any(zone is None for zone in memberships):
                reason = "zone_missing"
            elif not all(zone.inside for zone in memberships):
                reason = "outside_zone"
            elif not math.isfinite(distance) or distance < 0 or distance > rule.max_distance:
                reason = "outside_distance"
            else:
                reason = None
            duration, satisfied = 0.0, False
            episode = None
            if reason is None:
                key = (rule.config.rule_id, rule.config.version, interaction, rule.zone_id)
                episode = previous.get(key, _PairEpisode(frame.frame_index, frame.timestamp_s, False))
                duration = frame.timestamp_s - episode.started_timestamp_s
                satisfied = _duration_reached(duration, rule.minimum_duration_seconds)
                if satisfied and not episode.triggered:
                    candidates.append(PairEventCandidate(
                        rule.config.rule_id, rule.config.version, frame.frame_index, frame.timestamp_s,
                        interaction, rule.zone_id, rule.parameters, episode.started_frame_index,
                        episode.started_timestamp_s, distance, duration,
                        proximity.geometry_version, person_anchor, equipment_target,
                    ))
                episodes[key] = _PairEpisode(
                    episode.started_frame_index, episode.started_timestamp_s,
                    episode.triggered or satisfied,
                )
                if not satisfied:
                    reason = "insufficient_duration"
            evaluations.append(PairRuleEvaluation(
                rule.config.rule_id, rule.config.version, frame.frame_index, frame.timestamp_s,
                interaction, rule.zone_id, rule.parameters, distance, duration, satisfied, reason,
                episode.started_frame_index if episode else None,
                episode.started_timestamp_s if episode else None,
                proximity.geometry_version, person_anchor, equipment_target,
            ))
        return evaluations, candidates

    def evaluate(self, frame: FrameSpatialState) -> RuleFrameResult:
        """Evalúa OP-37 sin recalcular sus variables ni modificar el frame."""
        if not isinstance(frame, FrameSpatialState):
            raise TypeError("frame debe ser FrameSpatialState")
        if type(frame.frame_index) is not int or frame.frame_index < 0:
            raise RuleEngineError("frame_index debe ser entero no negativo")
        if self._last_frame_index is not None and frame.frame_index <= self._last_frame_index:
            raise RuleEngineError("frame_index debe avanzar estrictamente")
        if any(isinstance(rule, _PairProximityRule) for rule in self._rules):
            if (type(frame.timestamp_s) not in (int, float) or not math.isfinite(frame.timestamp_s)
                    or frame.timestamp_s < 0 or (self._last_timestamp_s is not None
                    and frame.timestamp_s <= self._last_timestamp_s)):
                raise RuleEngineError("timestamp_s debe ser finito, no negativo y avanzar estrictamente")

        previous = (
            self._active
            if self._last_frame_index is not None
            and frame.frame_index == self._last_frame_index + 1
            else set()
        )
        active: set[tuple[str, int, ObjectIdentity, str]] = set()
        previous_pairs = (
            self._pair_episodes if self._last_frame_index is not None
            and frame.frame_index == self._last_frame_index + 1 else {}
        )
        episodes: dict[tuple[str, int, InteractionIdentity, str], _PairEpisode] = {}
        evaluations: list[RuleEvaluation | PairRuleEvaluation] = []
        candidates: list[EventCandidate | PairEventCandidate] = []
        for rule in self._rules:
            if isinstance(rule, _PairProximityRule):
                pair_evaluations, pair_candidates = self._evaluate_pair_rule(
                    rule, frame, previous_pairs, episodes,
                )
                evaluations.extend(pair_evaluations)
                candidates.extend(pair_candidates)
                continue
            for obj in frame.objects:
                membership = next(
                    (zone for zone in obj.zones if zone.zone_id == rule.zone_id), None
                )
                inside = membership.inside if membership is not None else None
                dwell = membership.dwell_time_s if membership is not None else None
                if not rule.config.enabled:
                    evaluated, satisfied, reason = False, False, "disabled"
                elif obj.class_name != rule.class_name:
                    evaluated, satisfied, reason = False, False, "class_mismatch"
                elif membership is None:
                    evaluated, satisfied, reason = False, False, "zone_missing"
                elif not inside:
                    evaluated, satisfied, reason = True, False, "outside_zone"
                elif not _duration_reached(dwell, rule.min_duration_s):
                    evaluated, satisfied, reason = True, False, "insufficient_dwell"
                else:
                    evaluated, satisfied, reason = True, True, None
                evaluations.append(
                    RuleEvaluation(
                        rule.config.rule_id, rule.config.version, frame.frame_index,
                        frame.timestamp_s, obj.track_id, obj.class_name, rule.zone_id,
                        rule.parameters, inside, dwell, evaluated, satisfied, reason,
                    )
                )
                if satisfied:
                    key = (rule.config.rule_id, rule.config.version, obj.identity, rule.zone_id)
                    active.add(key)
                    if key not in previous:
                        candidates.append(
                            EventCandidate(
                                rule.config.rule_id, rule.config.version, frame.frame_index,
                                frame.timestamp_s, obj.track_id, obj.class_name, rule.zone_id,
                                rule.parameters, True, dwell,
                            )
                        )
        self._active = active
        self._pair_episodes = episodes
        self._last_frame_index = frame.frame_index
        self._last_timestamp_s = frame.timestamp_s
        return RuleFrameResult(
            frame.frame_index, frame.timestamp_s, tuple(evaluations), tuple(candidates)
        )
