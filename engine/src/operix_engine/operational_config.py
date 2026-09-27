"""Carga y validación estructural de zonas y reglas configuradas."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


class OperationalConfigError(ValueError):
    """Indica que el archivo o un valor de configuración no es válido."""


def _nonempty_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise OperationalConfigError(f"{field} debe ser texto no vacío")


def _freeze_json(value: object, field: str) -> object:
    """Valida valores JSON y elimina estructuras mutables de parámetros."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise OperationalConfigError(f"{field} debe contener números finitos")
        return value
    if isinstance(value, Mapping):
        frozen = {}
        for key, item in value.items():
            _nonempty_text(key, f"clave de {field}")
            frozen[key] = _freeze_json(item, f"{field}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, field) for item in value)
    raise OperationalConfigError(f"{field} contiene un tipo no compatible con JSON")


@dataclass(frozen=True, slots=True)
class Zone:
    """Zona definida por vértices normalizados para una vista configurada."""

    zone_id: str
    name: str
    polygon: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        _nonempty_text(self.zone_id, "zone_id")
        _nonempty_text(self.name, "name")
        if not isinstance(self.polygon, (list, tuple)) or len(self.polygon) < 3:
            raise OperationalConfigError("polygon debe contener al menos tres vértices")
        vertices = []
        for vertex in self.polygon:
            if not isinstance(vertex, (list, tuple)) or len(vertex) != 2:
                raise OperationalConfigError("Cada vértice de polygon debe tener dos coordenadas")
            if any(type(coordinate) not in (int, float) for coordinate in vertex):
                raise OperationalConfigError("Las coordenadas de polygon deben ser numéricas")
            if any(
                not 0 <= coordinate <= 1 or not math.isfinite(coordinate)
                for coordinate in vertex
            ):
                raise OperationalConfigError("Las coordenadas de polygon deben estar en [0,1]")
            vertices.append((float(vertex[0]), float(vertex[1])))
        object.__setattr__(self, "polygon", tuple(vertices))


@dataclass(frozen=True, slots=True)
class RuleConfig:
    """Parámetros de regla, sin lógica de evaluación operacional."""

    rule_id: str
    version: int
    enabled: bool
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        _nonempty_text(self.rule_id, "rule_id")
        if type(self.version) is not int or self.version <= 0:
            raise OperationalConfigError("version de regla debe ser entero positivo")
        if type(self.enabled) is not bool:
            raise OperationalConfigError("enabled debe ser booleano")
        if not isinstance(self.parameters, Mapping) or not self.parameters:
            raise OperationalConfigError("parameters debe ser un objeto JSON no vacío")
        object.__setattr__(self, "parameters", _freeze_json(self.parameters, "parameters"))


@dataclass(frozen=True, slots=True)
class OperationalConfig:
    """Configuración validada de una única vista de video."""

    schema_version: int
    view_id: str
    zones: tuple[Zone, ...]
    rules: tuple[RuleConfig, ...]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise OperationalConfigError("schema_version soportada: 1")
        _nonempty_text(self.view_id, "view_id")
        if not isinstance(self.zones, (list, tuple)) or not all(
            isinstance(zone, Zone) for zone in self.zones
        ):
            raise OperationalConfigError("zones debe contener objetos Zone")
        if not isinstance(self.rules, (list, tuple)) or not all(
            isinstance(rule, RuleConfig) for rule in self.rules
        ):
            raise OperationalConfigError("rules debe contener objetos RuleConfig")
        object.__setattr__(self, "zones", tuple(self.zones))
        object.__setattr__(self, "rules", tuple(self.rules))

        zone_ids = {zone.zone_id for zone in self.zones}
        if len(zone_ids) != len(self.zones):
            raise OperationalConfigError("zone_id duplicado")
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise OperationalConfigError("rule_id duplicado")
        for rule in self.rules:
            if "zone_id" in rule.parameters:
                zone_id = rule.parameters["zone_id"]
                _nonempty_text(zone_id, "parameters.zone_id")
                if zone_id not in zone_ids:
                    raise OperationalConfigError(f"zone_id inexistente: {zone_id}")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise OperationalConfigError(f"Clave JSON duplicada: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise OperationalConfigError(f"Número JSON no finito: {value}")


def _object_fields(value: object, field: str, expected: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise OperationalConfigError(f"{field} debe ser un objeto JSON")
    missing = expected - value.keys()
    unknown = value.keys() - expected
    if missing or unknown:
        raise OperationalConfigError(
            f"{field}: claves faltantes {sorted(missing)}; desconocidas {sorted(unknown)}"
        )
    return value


def load_operational_config(path: str | Path) -> OperationalConfig:
    """Carga JSON UTF-8, valida su versión y devuelve tipos propios de Operix."""
    source = Path(path)
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise OperationalConfigError(f"No se pudo leer la configuración: {error}") from error
    try:
        document = json.loads(
            content,
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, OperationalConfigError) as error:
        raise OperationalConfigError(f"JSON de configuración inválido: {error}") from error

    root = _object_fields(
        document,
        "raíz",
        {"schema_version", "view_id", "coordinate_system", "zones", "rules"},
    )
    if root["coordinate_system"] != "normalized":
        raise OperationalConfigError("coordinate_system soportado: normalized")
    if not isinstance(root["zones"], list):
        raise OperationalConfigError("zones debe ser una lista")
    if not isinstance(root["rules"], list):
        raise OperationalConfigError("rules debe ser una lista")

    zones = tuple(
        Zone(**_object_fields(item, "zone", {"zone_id", "name", "polygon"}))
        for item in root["zones"]
    )
    rules = tuple(
        RuleConfig(
            **_object_fields(
                item,
                "rule",
                {"rule_id", "version", "enabled", "parameters"},
            )
        )
        for item in root["rules"]
    )
    return OperationalConfig(root["schema_version"], root["view_id"], zones, rules)
