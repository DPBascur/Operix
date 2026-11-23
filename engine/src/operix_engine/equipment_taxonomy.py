# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Categoría operacional declarada para una fuente con equipo homogéneo."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass


EQUIPMENT_CATEGORIES = (
    "COUNTERBALANCE_FORKLIFT", "REACH_TRUCK", "POWERED_PALLET_TRUCK",
    "MANUAL_PALLET_JACK", "MANUAL_STACKER", "ELECTRIC_STACKER", "ELECTRIC_PALLET_JACK",
)
EQUIPMENT_SCOPE_KEYS = frozenset({"equipment_category", "unknown_equipment_policy"})
EQUIPMENT_SCOPE_EXCLUSIONS = ("equipment_category_mismatch", "equipment_unknown_excluded")


@dataclass(frozen=True, slots=True)
class EquipmentProfile:
    """Declaración explícita del perfil autorizado, ligada a la identidad de la fuente."""

    category: str
    source_sha256: str
    authority_reference: str

    def __post_init__(self) -> None:
        if self.category not in EQUIPMENT_CATEGORIES:
            raise ValueError("Categoría operacional de equipo no soportada")
        if not isinstance(self.source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("El perfil de equipo requiere una huella SHA-256 de fuente")
        if not isinstance(self.authority_reference, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", self.authority_reference
        ):
            raise ValueError("El perfil de equipo requiere un identificador de autorización")


@dataclass(frozen=True, slots=True)
class EquipmentTaxonomy:
    profile: EquipmentProfile | None = None

    @property
    def category(self) -> str:
        return self.profile.category if self.profile else "UNKNOWN"

    def to_dict(self) -> dict:
        return {
            "perception_class": "FORKLIFT",
            "operational_role": "MOBILE_EQUIPMENT",
            "subtype": "UNKNOWN",
            "category": self.category,
            "category_source": "AUTHORIZED_PROFILE" if self.profile else "UNKNOWN",
            **({"profile": asdict(self.profile)} if self.profile else {}),
        }


def validate_equipment_scope(parameters: Mapping[str, object], equipment_class: str) -> None:
    keys = EQUIPMENT_SCOPE_KEYS & parameters.keys()
    if keys and (
        keys != EQUIPMENT_SCOPE_KEYS
        or equipment_class != "forklift"
        or parameters["equipment_category"] not in EQUIPMENT_CATEGORIES
        or parameters["unknown_equipment_policy"] not in ("include", "exclude")
    ):
        raise ValueError("El alcance de equipo requiere una categoría válida y política UNKNOWN include/exclude")


def equipment_scope_decision(parameters: Mapping[str, object], taxonomy: EquipmentTaxonomy | None) -> str | None:
    if "equipment_category" not in parameters or taxonomy is None:
        return None
    if taxonomy.category == "UNKNOWN":
        if parameters["unknown_equipment_policy"] == "include":
            return "equipment_unknown_included"
        return "equipment_unknown_excluded"
    if taxonomy.category == parameters["equipment_category"]:
        return "equipment_category_match"
    return "equipment_category_mismatch"
