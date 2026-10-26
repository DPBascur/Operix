"""Validación del snapshot de un candidato por pares, sin recalcular su regla."""

import hashlib
import json
import math

from rest_framework.exceptions import ValidationError


EVENT_TYPES = ("zone_dwell", "person_forklift_proximity")


def number(value, name):
    if type(value) not in (int, float):
        raise ValidationError({name: "Debe ser numérico, finito y no negativo."})
    try:
        converted = float(value)
    except (OverflowError, ValueError, TypeError):
        raise ValidationError({name: "Número no representable."}) from None
    if not math.isfinite(converted) or converted < 0:
        raise ValidationError({name: "Debe ser finito y no negativo."})
    return value


def validate_pair_parameters(parameters):
    expected = {"kind", "zone_id", "person_class", "forklift_class",
                "max_distance", "minimum_duration_seconds"}
    if set(parameters) != expected:
        raise ValidationError({"rule_parameters": "Snapshot de parámetros por pares incompleto."})
    if not all(isinstance(parameters[k], str) and parameters[k].strip()
               for k in ("zone_id", "person_class", "forklift_class")):
        raise ValidationError({"rule_parameters": "Roles y zona requieren texto."})
    if parameters["person_class"] == parameters["forklift_class"]:
        raise ValidationError({"rule_parameters": "Las clases de los roles deben ser distintas."})
    number(parameters["max_distance"], "max_distance")
    # hypot(dx/width, dy/height): ambos ejes en [0,1], diagonal máxima sqrt(2).
    if parameters["max_distance"] > math.sqrt(2):
        raise ValidationError({"max_distance": "Debe estar entre 0 y sqrt(2) normalizado en imagen."})
    number(parameters["minimum_duration_seconds"], "minimum_duration_seconds")


def validate_pair(attrs):
    parameters = attrs["rule_parameters"]
    interaction = attrs.get("interaction", {})
    if not isinstance(interaction, dict) or set(interaction) != {"person", "forklift"}:
        raise ValidationError({"interaction": "Se requieren los dos roles explícitos."})
    for role in ("person", "forklift"):
        subject = interaction[role]
        if (not isinstance(subject, dict) or set(subject) != {"class_name", "track_id"}
                or subject["class_name"] != parameters[f"{role}_class"]
                or type(subject["track_id"]) is not int or not 0 <= subject["track_id"] <= 2147483647):
            raise ValidationError({"interaction": "Identidad incompatible con el rol."})
    observations, episode = attrs.get("observations", {}), attrs.get("episode", {})
    if (not isinstance(observations, dict) or set(observations) not in (
            {"normalized_distance", "duration_s"},
            {"normalized_distance", "duration_s", "proximity_geometry"})):
        raise ValidationError({"observations": "Se requieren distancia y duración observadas."})
    if "proximity_geometry" in observations:
        geometry = observations["proximity_geometry"]
        if (not isinstance(geometry, dict) or set(geometry) != {"version", "person_anchor", "equipment_target"}
                or geometry["version"] not in {
                    "person_bottom_center_to_equipment_ground_edge_v1",  # Snapshot histórico B.
                    "person_equipment_nearest_ground_edges_v1",
                }):
            raise ValidationError({"observations": "Contrato geométrico no soportado o incompleto."})
        for key in ("person_anchor", "equipment_target"):
            point = geometry[key]
            if (not isinstance(point, list) or len(point) != 2
                    or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in point)):
                raise ValidationError({"observations": "Puntos geométricos normalizados inválidos."})
    distance = number(observations["normalized_distance"], "normalized_distance")
    duration = number(observations["duration_s"], "duration_s")
    if distance > parameters["max_distance"] or parameters["minimum_duration_seconds"] - duration > 1e-9:
        raise ValidationError({"observations": "No satisface los parámetros registrados."})
    if not isinstance(episode, dict) or set(episode) != {"started_frame_index", "started_timestamp_s", "timestamp_s"}:
        raise ValidationError({"episode": "Se requieren inicio y tiempo de emisión reales."})
    first = episode["started_frame_index"]
    if type(first) is not int or not 0 <= first <= attrs["frame_index"]:
        raise ValidationError({"episode": "Frame inicial inválido."})
    start = number(episode["started_timestamp_s"], "started_timestamp_s")
    end = number(episode["timestamp_s"], "timestamp_s")
    if (start > end or abs((end - start) - duration) > 1e-9
            or abs(end - float(attrs["video_timestamp_s"])) > 0.000500001):
        raise ValidationError({"episode": "Tiempos incompatibles con la observación."})
    if any(attrs.get(key) is not None for key in ("track_id", "observed_inside", "observed_dwell_time_s")) or attrs.get("class_name"):
        raise ValidationError({"interaction": "Un par no tiene un objeto primario ficticio."})
    attrs.update(track_id=None, class_name="", observed_inside=None, observed_dwell_time_s=None)
    canonical = json.dumps(interaction, sort_keys=True, separators=(",", ":"))
    attrs["pair_key"] = hashlib.sha256(canonical.encode()).hexdigest()
    return attrs
