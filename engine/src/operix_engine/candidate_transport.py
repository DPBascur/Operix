# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Payloads JSON de candidatos transitorios; no son eventos del Backend."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence

from operix_engine.rules import EventCandidate, InteractionIdentity, PairEventCandidate
from operix_engine.spatiotemporal import ObjectIdentity


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} debe ser texto no vacío")


def _number(value: object, name: str) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} debe ser finito y no negativo")


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} debe ser entero >= {minimum}")


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        for key in value:
            _text(key, "clave de parámetros")
        return {key: _json_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("El candidato contiene un valor no serializable como JSON")


def _subject(role: str, identity: ObjectIdentity) -> dict[str, object]:
    # Validar también payloads creados manualmente fuera de RuleEngine.
    if not isinstance(identity, ObjectIdentity):
        raise ValueError("El sujeto requiere ObjectIdentity")
    checked = ObjectIdentity(identity.class_name, identity.track_id)
    return {"role": role, "class_name": checked.class_name, "track_id": checked.track_id}


def candidate_payload(candidate: EventCandidate | PairEventCandidate) -> dict[str, object]:
    """Añade discriminador/sujetos sin retirar los campos históricos de cada tipo."""
    if type(candidate) not in (EventCandidate, PairEventCandidate):
        raise TypeError("Tipo de candidato no soportado para transporte")
    _text(candidate.rule_id, "rule_id")
    _text(candidate.zone_id, "zone_id")
    _integer(candidate.rule_version, "rule_version", 1)
    _integer(candidate.frame_index, "frame_index")
    _number(candidate.timestamp_s, "timestamp_s")
    if not isinstance(candidate.parameters, Mapping):
        raise ValueError("parameters debe ser un mapping")

    if isinstance(candidate, EventCandidate):
        if candidate.parameters.get("kind") != "zone_dwell":
            raise ValueError("EventCandidate requiere kind=zone_dwell")
        if type(candidate.observed_inside) is not bool:
            raise ValueError("observed_inside debe ser booleano")
        _number(candidate.observed_dwell_time_s, "observed_dwell_time_s")
        identity = ObjectIdentity(candidate.class_name, candidate.track_id)
        payload = {
            "rule_id": candidate.rule_id, "rule_version": candidate.rule_version,
            "frame_index": candidate.frame_index, "timestamp_s": candidate.timestamp_s,
            "track_id": candidate.track_id, "class_name": candidate.class_name,
            "zone_id": candidate.zone_id, "parameters": candidate.parameters,
            "observed_inside": candidate.observed_inside,
            "observed_dwell_time_s": candidate.observed_dwell_time_s,
            "candidate_kind": "zone_dwell", "subjects": [_subject("object", identity)],
        }
    else:
        if candidate.parameters.get("kind") != "person_forklift_proximity":
            raise ValueError("PairEventCandidate requiere kind=person_forklift_proximity")
        if not isinstance(candidate.interaction, InteractionIdentity):
            raise ValueError("El candidato por pares requiere InteractionIdentity")
        person, forklift = candidate.interaction.person, candidate.interaction.forklift
        if not isinstance(person, ObjectIdentity) or not isinstance(forklift, ObjectIdentity):
            raise ValueError("Ambos roles requieren ObjectIdentity")
        if (person.class_name != candidate.parameters.get("person_class", "person")
                or forklift.class_name != candidate.parameters.get("forklift_class", "forklift")
                or person.class_name == forklift.class_name):
            raise ValueError("Identidades incompatibles con los roles de la interacción")
        _integer(candidate.started_frame_index, "started_frame_index")
        for name, value in (
            ("started_timestamp_s", candidate.started_timestamp_s),
            ("observed_normalized_distance", candidate.observed_normalized_distance),
            ("observed_duration_s", candidate.observed_duration_s),
            ("max_distance", candidate.parameters.get("max_distance")),
            ("minimum_duration_seconds", candidate.parameters.get("minimum_duration_seconds")),
        ):
            _number(value, name)
        if (candidate.started_frame_index > candidate.frame_index
                or candidate.started_timestamp_s > candidate.timestamp_s):
            raise ValueError("El inicio del episodio no puede ser posterior al disparo")
        payload = candidate.to_dict() | {
            "candidate_kind": "person_forklift_proximity",
            "subjects": [_subject("person", person), _subject("forklift", forklift)],
        }
    result = _json_value(payload)
    # Frontera explícita: ni dataclasses, ni NaN, ni objetos Python opacos.
    json.dumps(result, allow_nan=False, sort_keys=True)
    return result


def candidate_payloads(
    candidates: Sequence[EventCandidate | PairEventCandidate],
) -> list[dict[str, object]]:
    """Conserva el orden de emisión y permite colecciones heterogéneas."""
    return [candidate_payload(candidate) for candidate in candidates]
