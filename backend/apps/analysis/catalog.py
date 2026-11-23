"""Versioned policy catalog and deterministic resolution for an analysis source."""

import math
import re
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import Http404
from operix_engine.equipment_taxonomy import EQUIPMENT_SCOPE_KEYS
from rest_framework.exceptions import APIException, ValidationError

from apps.events.equipment_contract import validate_equipment_scope
from .models import AnalysisSource, RuleCatalogEntry, RuleCatalogRevision, SpatialConfiguration


Kind = RuleCatalogEntry.Kind
SHA256 = re.compile(r"[0-9a-f]{64}")
ZONE_PARAMETERS = {"kind", "class_name", "zone_id", "min_duration_s"}
PAIR_REQUIRED = {"kind", "zone_id", "max_distance", "minimum_duration_seconds"}
PAIR_OPTIONAL = {"person_class", "forklift_class", "distance_unit", "motion_condition", "exclude_possible_occupant"}
OVERRIDABLE = {"zone_id", "min_duration_s", "max_distance", "minimum_duration_seconds",
                "distance_unit", "motion_condition"}


class CatalogConflict(APIException):
    status_code = 409
    default_detail = "El catálogo cambió. Recupere la versión actual."


def require_keys(data, required, optional=()):
    if not isinstance(data, dict) or required - data.keys() or data.keys() - (required | set(optional)):
        raise ValidationError("Revise los campos requeridos y permitidos.")


def identifier(value):
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValidationError("Identificador de catálogo inválido.") from None


def text_value(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\0" in value:
        raise ValidationError(f"Se requiere texto de hasta {limit} caracteres.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValidationError("Texto inválido.") from None
    return value


def boolean(value):
    if type(value) is not bool:
        raise ValidationError("El estado enabled debe ser booleano.")
    return value


def nonnegative(value, name):
    try:
        if type(value) in (int, float) and value >= 0 and math.isfinite(value):
            return
    except OverflowError:
        pass
    raise ValidationError(f"{name} debe ser un número no negativo y finito.")


def validate_parameters(parameters):
    if not isinstance(parameters, dict):
        raise ValidationError("parameters debe ser un objeto.")
    kind = parameters.get("kind")
    if kind in ("zone_dwell", "zone_entry"):
        require_keys(parameters, ZONE_PARAMETERS, EQUIPMENT_SCOPE_KEYS)
        if parameters["class_name"] not in ("person", "forklift"):
            raise ValidationError("La clase debe ser person o forklift.")
        validate_equipment_scope(parameters, parameters["class_name"])
        nonnegative(parameters["min_duration_s"], "min_duration_s")
        if kind == "zone_entry" and parameters["min_duration_s"] != 0:
            raise ValidationError("El ingreso observado requiere duración cero.")
    elif kind in ("person_forklift_proximity", "zone_coexistence"):
        require_keys(parameters, PAIR_REQUIRED, PAIR_OPTIONAL | EQUIPMENT_SCOPE_KEYS)
        if parameters.get("person_class", "person") != "person" or parameters.get("forklift_class", "forklift") != "forklift":
            raise ValidationError("Los roles deben ser persona y montacargas.")
        validate_equipment_scope(parameters, parameters.get("forklift_class", "forklift"))
        unit = parameters.get("distance_unit", "normalized")
        motion = parameters.get("motion_condition", "any")
        if unit not in ("normalized", "m") or motion not in ("any", "moving"):
            raise ValidationError("Unidad de distancia o condición de movimiento inválida.")
        if "exclude_possible_occupant" in parameters and (
                kind != "person_forklift_proximity" or type(parameters["exclude_possible_occupant"]) is not bool):
            raise ValidationError("La exclusión experimental es booleana y solo se admite para proximidad.")
        distance = parameters["max_distance"]
        nonnegative(distance, "max_distance")
        nonnegative(parameters["minimum_duration_seconds"], "minimum_duration_seconds")
        if unit == "normalized" and distance > math.sqrt(2):
            raise ValidationError("La distancia normalizada debe estar entre 0 y √2.")
        if kind == "zone_coexistence" and (unit != "normalized" or motion != "any" or abs(distance - math.sqrt(2)) > 1e-12):
            raise ValidationError("La coexistencia requiere distancia √2 normalizada y movimiento indistinto.")
    else:
        raise ValidationError("Tipo de regla no compatible.")
    text_value(parameters["zone_id"], 64)


def validate_overrides(data):
    require_keys(data, set(), {"enabled", "parameters"})
    if "enabled" in data:
        boolean(data["enabled"])
    if "parameters" in data:
        require_keys(data["parameters"], set(), OVERRIDABLE)
    return data


def catalog_document(kind, data):
    fields = {"name", "enabled"}
    if kind == Kind.TEMPLATE:
        require_keys(data, fields | {"parameters"})
        validate_parameters(data["parameters"])
    elif kind == Kind.SET:
        require_keys(data, fields | {"rules"})
        if not isinstance(data["rules"], list) or not 1 <= len(data["rules"]) <= 32:
            raise ValidationError("Un conjunto debe contener de 1 a 32 plantillas.")
        rules = []
        for item in data["rules"]:
            require_keys(item, {"template_id"}, {"overrides"})
            rules.append({"template_id": identifier(item["template_id"]),
                          "overrides": validate_overrides(item.get("overrides", {}))})
        if len({item["template_id"] for item in rules}) != len(rules):
            raise ValidationError("Cada plantilla puede aparecer una vez en el conjunto.")
        data = {**data, "rules": rules}
    else:
        require_keys(data, fields | {"rule_set_id", "target_type", "target_id"}, {"overrides"})
        overrides = data.get("overrides", {})
        if not isinstance(overrides, dict) or len(overrides) > 32:
            raise ValidationError("Indique ajustes por plantilla para la asignación.")
        normalized = {identifier(key): validate_overrides(value) for key, value in overrides.items()}
        if len(normalized) != len(overrides):
            raise ValidationError("Cada plantilla puede tener un ajuste por asignación.")
        data = {**data, "rule_set_id": identifier(data["rule_set_id"]), "overrides": normalized}
    text_value(data["name"], 120)
    boolean(data["enabled"])
    return {**data, "name": data["name"].strip()}


def load_catalog(owner_id):
    entries = RuleCatalogEntry.objects.filter(owner_id=owner_id)
    return {str(entry.pk): entry for entry in entries}


def get_reference(entries, key, kind):
    entry = entries.get(key)
    if entry is None or entry.kind != kind:
        raise ValidationError("Seleccione una referencia existente en su catálogo.")
    return entry


def validate_target(owner_id, document):
    from .sessions import PROFILE_DEMO_SETTINGS, PROFILES

    target = text_value(document["target_id"], 64)
    scope = document["target_type"]
    if scope == "camera":
        from .camera_registry import inventory

        if target in inventory():
            return
    if scope == "profile" and target in PROFILES:
        return
    if scope == "demo" and any(target == demo for demo, _ in PROFILE_DEMO_SETTINGS.values()):
        return
    if scope == "source" and SHA256.fullmatch(target):
        if (AnalysisSource.objects.filter(owner_id=owner_id, source_sha256=target).exists()
                or SpatialConfiguration.objects.filter(owner_id=owner_id, source_sha256=target).exists()):
            return
    raise ValidationError("Seleccione un perfil, demo o SHA-256 de una fuente de su cuenta.")


def materialize_rules(entries, rule_set, assignment=None):
    overrides = assignment.document["overrides"] if assignment else {}
    rules = []
    templates = []
    for item in rule_set.document["rules"]:
        template = get_reference(entries, item["template_id"], Kind.TEMPLATE)
        parameters = template.document["parameters"].copy()
        enabled = template.document["enabled"]
        for adjustment in (item["overrides"], overrides.get(str(template.pk), {})):
            parameters.update(adjustment.get("parameters", {}))
            enabled = adjustment.get("enabled", enabled)
        rules.append({"rule_id": str(template.pk), "version": template.version,
                      "enabled": enabled, "parameters": parameters})
        templates.append(reference_snapshot(template))
    if overrides.keys() - {rule["rule_id"] for rule in rules}:
        raise ValidationError("Los ajustes deben corresponder a plantillas del conjunto asignado.")
    return rules, templates


def reference_snapshot(entry):
    return {"id": str(entry.pk), "version": entry.version, "name": entry.document["name"]}


@transaction.atomic
def save_entry(owner_id, kind, data, pk=None):
    # A single lock orders catalog writes, including concurrent assignments to the same target.
    get_user_model().objects.select_for_update().get(pk=owner_id)
    entries = load_catalog(owner_id)
    if pk is None:
        entry = RuleCatalogEntry(kind=kind, owner_id=owner_id)
    else:
        entry = entries.get(str(pk))
        if entry is None or entry.kind != kind:
            raise Http404
        if not isinstance(data, dict) or type(data.get("version")) is not int:
            raise ValidationError("Indique la versión vigente.")
        if data["version"] != entry.version:
            raise CatalogConflict()
        data = {key: value for key, value in data.items() if key != "version"}
        entry.version += 1
    entry.document = catalog_document(kind, data)
    entries[str(entry.pk)] = entry
    if kind == Kind.ASSIGNMENT:
        validate_target(owner_id, entry.document)
        target = entry.document["target_type"], entry.document["target_id"]
        if any(other.pk != entry.pk and other.kind == Kind.ASSIGNMENT
               and (other.document["target_type"], other.document["target_id"]) == target
               for other in entries.values()):
            raise CatalogConflict("Ya existe una asignación para ese destino.")
    # Existing dependencies must remain valid when a referenced object changes.
    for other in entries.values():
        if other.kind == Kind.TEMPLATE:
            continue
        assignment = other if other.kind == Kind.ASSIGNMENT else None
        rule_set = get_reference(entries, other.document["rule_set_id"], Kind.SET) if assignment else other
        rules, _ = materialize_rules(entries, rule_set, assignment)
        for rule in rules:
            validate_parameters(rule["parameters"])
    entry.save()
    RuleCatalogRevision.objects.create(entry=entry, version=entry.version, document=entry.document)
    return entry


def resolve_policy(entries, *, profile, demo_source_id, source_sha256, camera_id=None):
    active = {
        (entry.document["target_type"], entry.document["target_id"]): entry
        for entry in entries.values()
        if entry.kind == Kind.ASSIGNMENT and entry.document["enabled"]
    }
    for target in (("camera", camera_id), ("source", source_sha256), ("demo", demo_source_id), ("profile", profile)):
        assignment = active.get(target)
        if assignment is None:
            continue
        rule_set = get_reference(entries, assignment.document["rule_set_id"], Kind.SET)
        if rule_set.document["enabled"]:
            rules, templates = materialize_rules(entries, rule_set, assignment)
            return rules, {"assignment": {**reference_snapshot(assignment), "target_type": target[0],
                                          "target_id": target[1]},
                           "rule_set": reference_snapshot(rule_set), "templates": templates}
    return None, None
