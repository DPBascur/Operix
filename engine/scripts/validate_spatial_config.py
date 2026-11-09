"""Valida configuración web usando los mismos contratos que el Motor."""
import json
from pathlib import Path
import sys
import tempfile
from dataclasses import replace

from operix_engine.operational_config import load_operational_config
from operix_engine.rules import RuleEngine
from operix_engine.zone_geometry import NormalizedPoint, point_in_zone


def validate(document, source_sha256):
    if not isinstance(document, dict) or not 1 <= len(document.get("zones", [])) <= 16 or len(document.get("rules", [])) > 32:
        raise ValueError("Se requieren 1–16 zonas y hasta 32 reglas")
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "config.json"
        path.write_text(json.dumps(document, allow_nan=False), encoding="utf8")
        config = load_operational_config(path)
    for zone in config.zones:
        if len(zone.polygon) > 32 or len(zone.zone_id) > 64 or len(zone.name) > 100:
            raise ValueError("Límites de zona excedidos")
        point_in_zone(NormalizedPoint(0,0), zone)
    zones = {z.zone_id:z for z in config.zones}
    for rule in config.rules:
        if rule.parameters.get("kind") in {"person_forklift_proximity", "zone_coexistence"} and (rule.parameters.get("person_class", "person") != "person" or rule.parameters.get("forklift_class", "forklift") != "forklift"):
            raise ValueError("Solo se admiten roles persona y montacargas")
        if len(rule.rule_id) > 64 or rule.parameters.get("class_name", "person") not in {"person","forklift"}:
            raise ValueError("Identificador o clase no soportados")
        if rule.parameters.get("kind") == "zone_entry" and (
            zones[rule.parameters["zone_id"]].purpose != "restricted" or rule.parameters.get("min_duration_s") != 0
        ):
            raise ValueError("Ingreso requiere zona restringida y duración cero")
        if rule.parameters.get("kind") == "zone_coexistence" and (
            rule.parameters.get("distance_unit", "normalized") != "normalized"
            or abs(rule.parameters.get("max_distance",0)-2**.5) > 1e-12
        ):
            raise ValueError("Coexistencia usa presencia conjunta en zona")
    checked_config = config
    if config.calibration and config.calibration["status"] == "invalid":
        checked_config = replace(config, rules=tuple(replace(r, enabled=False) for r in config.rules))
    RuleEngine(checked_config)
    if config.calibration:
        if config.calibration["source_sha256"] != source_sha256:
            raise ValueError("Calibración de otra fuente")
        document = {**document, "calibration": config.calibration}
    return document


if __name__ == "__main__":
    try:
        print(json.dumps(validate(json.load(sys.stdin), sys.argv[1]), allow_nan=False))
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print("No se pudo validar la configuración espacial", file=sys.stderr)
        raise SystemExit(1)
