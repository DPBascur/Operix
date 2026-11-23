"""Validation of the optional operational equipment snapshot."""

from operix_engine.equipment_taxonomy import (
    EquipmentProfile, EquipmentTaxonomy, validate_equipment_scope as check_equipment_scope,
)
from rest_framework.exceptions import ValidationError


def validate_equipment_scope(parameters, equipment_class):
    try:
        check_equipment_scope(parameters, equipment_class)
    except ValueError as error:
        raise ValidationError(str(error)) from error


def validate_equipment_taxonomy(attrs, equipment_class):
    parameters = attrs["rule_parameters"]
    scoped = "equipment_category" in parameters
    observations = attrs.get("observations", {})
    if not isinstance(observations, dict):
        raise ValidationError("Las observaciones de equipo requieren un objeto JSON.")
    if "equipment_taxonomy" not in observations and not scoped:
        return
    taxonomy = observations.get("equipment_taxonomy")
    if equipment_class != "forklift" or not isinstance(taxonomy, dict):
        raise ValidationError("Taxonomía de equipo incompleta o incompatible con la clase.")
    source = attrs.get("source", {})
    source_key = source.get("video_sha256")
    configured = source.get("spatial_configuration", {}).get("equipment_profile")
    profile = None
    if source_key and isinstance(configured, dict) and configured.get("source_sha256") == source_key.lower():
        try:
            profile = EquipmentProfile(**configured)
        except (TypeError, ValueError) as error:
            raise ValidationError("Perfil de equipo de la fuente inválido.") from error
    expected = EquipmentTaxonomy(profile)
    if taxonomy != expected.to_dict():
        raise ValidationError("La taxonomía no corresponde al perfil de la fuente.")
    if not scoped:
        return
    if ((profile is None and parameters["unknown_equipment_policy"] != "include")
            or (profile is not None and parameters["equipment_category"] != profile.category)):
        raise ValidationError("La categoría no satisface el alcance de la regla.")
