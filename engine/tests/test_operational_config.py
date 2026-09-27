"""Pruebas de configuración estructural de OP-30, sin inferencia ni GPU."""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from operix_engine.operational_config import (
    OperationalConfig,
    OperationalConfigError,
    RuleConfig,
    Zone,
    load_operational_config,
)


EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "examples" / "op30-zone-rule.json"
MODULE = Path(__file__).resolve().parents[1] / "src" / "operix_engine" / "operational_config.py"


class OperationalConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.document = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def load(self, document: object, name: str = "config.json") -> OperationalConfig:
        path = self.directory / name
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return load_operational_config(path)

    def assert_invalid(self, fragment: str) -> None:
        with self.assertRaisesRegex(OperationalConfigError, fragment):
            self.load(self.document)

    def test_loads_example_and_creates_immutable_models(self) -> None:
        config = load_operational_config(EXAMPLE)

        self.assertIsInstance(config, OperationalConfig)
        self.assertEqual((config.schema_version, config.view_id), (1, "ceiling_04"))
        self.assertIsInstance(config.zones[0], Zone)
        self.assertEqual(config.zones[0].zone_id, "zona_critica_01")
        self.assertEqual(config.zones[0].polygon[0], (0.2, 0.2))
        self.assertIsInstance(config.rules[0], RuleConfig)
        self.assertEqual(config.rules[0].rule_id, "restricted_zone_presence")
        self.assertIs(config.rules[0].enabled, True)
        self.assertEqual(config.rules[0].parameters["min_duration_s"], 2.0)
        with self.assertRaises(FrozenInstanceError):
            config.zones[0].name = "otra"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            config.rules[0].parameters["min_duration_s"] = 3.0  # type: ignore[index]

    def test_changing_parameter_in_json_changes_loaded_value_only(self) -> None:
        first = self.load(self.document, "first.json")
        self.document["rules"][0]["parameters"]["min_duration_s"] = 3.5
        second = self.load(self.document, "second.json")

        self.assertEqual(first.rules[0].parameters["min_duration_s"], 2.0)
        self.assertEqual(second.rules[0].parameters["min_duration_s"], 3.5)
        self.assertEqual(first.zones, second.zones)

    def test_parameters_are_deeply_immutable(self) -> None:
        self.document["rules"][0]["parameters"]["extra"] = {"values": [1, 2]}
        config = self.load(self.document)
        original = config.rules[0].parameters["extra"]
        self.document["rules"][0]["parameters"]["extra"]["values"].append(3)
        self.assertEqual(original["values"], (1, 2))
        with self.assertRaises(TypeError):
            original["values"] = ()

    def test_invalid_json_and_root_are_rejected(self) -> None:
        path = self.directory / "invalid.json"
        path.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(OperationalConfigError, "JSON"):
            load_operational_config(path)
        self.document = []
        self.assert_invalid("raíz")

    def test_duplicate_json_keys_are_rejected(self) -> None:
        path = self.directory / "duplicate.json"
        path.write_text('{"view_id":"one","view_id":"two"}', encoding="utf-8")
        with self.assertRaisesRegex(OperationalConfigError, "duplicada"):
            load_operational_config(path)

    def test_schema_version_and_coordinate_system_are_fixed(self) -> None:
        for value in (0, 2, True, "1"):
            with self.subTest(schema_version=value):
                self.document["schema_version"] = value
                self.assert_invalid("schema_version")
        self.document["schema_version"] = 1
        self.document["coordinate_system"] = "pixels"
        self.assert_invalid("coordinate_system")

    def test_view_id_must_be_nonempty(self) -> None:
        self.document["view_id"] = "   "
        self.assert_invalid("view_id")

    def test_root_and_collections_require_known_structure(self) -> None:
        self.document["typo"] = 1
        self.assert_invalid("desconocidas")
        del self.document["typo"]
        self.document["zones"] = {}
        self.assert_invalid("zones debe ser una lista")

    def test_zone_id_and_name_must_be_nonempty(self) -> None:
        zone = self.document["zones"][0]
        zone["zone_id"] = ""
        self.assert_invalid("zone_id")
        zone["zone_id"] = "zona_critica_01"
        zone["name"] = " "
        self.assert_invalid("name")

    def test_duplicate_zone_ids_are_rejected(self) -> None:
        self.document["zones"].append(dict(self.document["zones"][0]))
        self.assert_invalid("zone_id duplicado")

    def test_polygon_requires_three_vertices(self) -> None:
        self.document["zones"][0]["polygon"] = [[0, 0], [1, 1]]
        self.assert_invalid("tres vértices")

    def test_polygon_rejects_malformed_vertices(self) -> None:
        for vertex in ([0.2], [0.2, 0.3, 0.4], "0.2,0.3"):
            with self.subTest(vertex=vertex):
                self.document["zones"][0]["polygon"][0] = vertex
                self.assert_invalid("dos coordenadas")

    def test_polygon_rejects_nonnumeric_and_out_of_range_values(self) -> None:
        for value, message in (
            (True, "numéricas"),
            ("0.2", "numéricas"),
            (-0.1, r"\[0,1\]"),
            (1.1, r"\[0,1\]"),
        ):
            with self.subTest(value=value):
                self.document["zones"][0]["polygon"][0] = [value, 0.2]
                self.assert_invalid(message)

    def test_nan_and_infinity_are_rejected(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.document["zones"][0]["polygon"][0] = [value, 0.2]
                self.assert_invalid("no finito")

    def test_rule_id_version_enabled_and_parameters_are_validated(self) -> None:
        rule = self.document["rules"][0]
        rule["rule_id"] = " "
        self.assert_invalid("rule_id")
        rule["rule_id"] = "restricted_zone_presence"
        for value in (0, -1, True, "1"):
            with self.subTest(version=value):
                rule["version"] = value
                self.assert_invalid("version")
        rule["version"] = 1
        rule["enabled"] = 1
        self.assert_invalid("enabled")
        rule["enabled"] = True
        rule["parameters"] = []
        self.assert_invalid("parameters")

    def test_duplicate_rules_and_missing_zone_reference_are_rejected(self) -> None:
        rule = self.document["rules"][0]
        rule["parameters"]["zone_id"] = "no_existe"
        self.assert_invalid("zone_id inexistente")
        rule["parameters"]["zone_id"] = "zona_critica_01"
        self.document["rules"].append(dict(rule))
        self.assert_invalid("rule_id duplicado")

    def test_configuration_module_has_no_perception_backend_imports(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        forbidden = {
            "cv2",
            "ultralytics",
            "operix_engine.detection",
            "operix_engine.tracking",
            "operix_engine.yolo_detector",
            "operix_engine.byte_tracker",
            "operix_engine.visualization",
        }
        self.assertTrue(imported.isdisjoint(forbidden))


if __name__ == "__main__":
    unittest.main()
