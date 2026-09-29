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
from operix_engine.spatiotemporal import FrameSpatialState


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
class RuleFrameResult:
    frame_index: int
    timestamp_s: float
    evaluations: tuple[RuleEvaluation, ...]
    candidates: tuple[EventCandidate, ...]


@dataclass(frozen=True, slots=True)
class _ZoneDwellRule:
    config: RuleConfig
    class_name: str
    zone_id: str
    min_duration_s: float
    parameters: Mapping[str, object]


def _validate_rule(rule: RuleConfig, zone_ids: set[str]) -> _ZoneDwellRule:
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
        self._active: set[tuple[str, int, int, str]] = set()

    def evaluate(self, frame: FrameSpatialState) -> RuleFrameResult:
        """Evalúa OP-37 sin recalcular sus variables ni modificar el frame."""
        if not isinstance(frame, FrameSpatialState):
            raise TypeError("frame debe ser FrameSpatialState")
        if type(frame.frame_index) is not int or frame.frame_index < 0:
            raise RuleEngineError("frame_index debe ser entero no negativo")
        if self._last_frame_index is not None and frame.frame_index <= self._last_frame_index:
            raise RuleEngineError("frame_index debe avanzar estrictamente")

        previous = (
            self._active
            if self._last_frame_index is not None
            and frame.frame_index == self._last_frame_index + 1
            else set()
        )
        active: set[tuple[str, int, int, str]] = set()
        evaluations: list[RuleEvaluation] = []
        candidates: list[EventCandidate] = []
        for rule in self._rules:
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
                elif dwell < rule.min_duration_s:
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
                    key = (rule.config.rule_id, rule.config.version, obj.track_id, rule.zone_id)
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
        self._last_frame_index = frame.frame_index
        return RuleFrameResult(
            frame.frame_index, frame.timestamp_s, tuple(evaluations), tuple(candidates)
        )
