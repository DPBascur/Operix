# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas de configuración y reglas con tracks sintéticos."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from uuid import uuid4

from operix_engine.candidate_transport import candidate_payload
from operix_engine.detection import BoundingBox
from operix_engine.equipment_taxonomy import EquipmentProfile
from operix_engine.event_publishing import EventContext, event_candidate_payload
from operix_engine.operational_config import OperationalConfig, OperationalConfigError, RuleConfig, Zone, load_operational_config
from operix_engine.rules import EquipmentScopeAudit, RuleEngine, RuleEngineError
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track


SOURCE = "a" * 64
ZONE = Zone("z", "Zona", ((.1, .1), (.9, .1), (.9, .9), (.1, .9)), purpose="restricted")
PERSON = Track(1, 0, "person", .99, BoundingBox(20, 30, 30, 50))
EQUIPMENT = Track(1, 0, "forklift", .99, BoundingBox(35, 25, 45, 55))
PAIR = {"kind": "person_forklift_proximity", "zone_id": "z",
        "max_distance": .2, "minimum_duration_seconds": 1}
ELECTRIC = {"equipment_category": "ELECTRIC_PALLET_JACK", "unknown_equipment_policy": "exclude"}


def configure(parameters, profile=None, source=SOURCE):
    config = OperationalConfig(1, "fixture", (ZONE,), (RuleConfig("r", 2, True, parameters),),
                               equipment_profile=profile)
    return RuleEngine(config), SpatiotemporalAnalyzer(
        width=100, height=100, fps=1, zones=config.zones, proximity_roles=config.proximity_roles,
        equipment_profile=config.equipment_profile, source_sha256=source,
    )


class EquipmentTaxonomyTests(TestCase):
    def test_manual_and_electric_declarations_are_source_bound_and_do_not_predict_subtype(self):
        categories = ("MANUAL_PALLET_JACK", "MANUAL_STACKER", "ELECTRIC_STACKER", "ELECTRIC_PALLET_JACK",
                      "COUNTERBALANCE_FORKLIFT", "REACH_TRUCK", "POWERED_PALLET_TRUCK")
        for category in categories:
            for source in (SOURCE, "b" * 64, None):
                with self.subTest(category=category, source=source):
                    profile = EquipmentProfile(category, SOURCE, "review-1")
                    _, analyzer = configure(PAIR, profile, source)
                    forklift, person = analyzer.update(0, (PERSON, EQUIPMENT)).objects
                    self.assertEqual(forklift.class_name, "forklift")
                    self.assertIsNone(person.equipment_taxonomy)
                    taxonomy = forklift.equipment_taxonomy.to_dict()
                    self.assertEqual(taxonomy["subtype"], "UNKNOWN")
                    self.assertEqual(taxonomy["category"], category if source == SOURCE else "UNKNOWN")
                    self.assertEqual("profile" in taxonomy, source == SOURCE)

    def test_manual_unknown_and_electric_pair_scope_and_audit(self):
        for category, decision, emits in (
            (None, "equipment_unknown_excluded", False),
            ("MANUAL_PALLET_JACK", "equipment_category_mismatch", False),
            ("ELECTRIC_PALLET_JACK", "equipment_category_match", True),
        ):
            with self.subTest(category=category):
                profile = EquipmentProfile(category, SOURCE, "review-1") if category else None
                engine, analyzer = configure(PAIR | ELECTRIC, profile)
                audit = EquipmentScopeAudit()
                for index in range(3):
                    result = engine.evaluate(analyzer.update(index, (PERSON, EQUIPMENT)))
                    audit.update(result)
                    self.assertEqual(result.evaluations[0].equipment_scope, decision)
                    self.assertEqual(bool(result.candidates), emits and index == 1)
                    if not emits:
                        self.assertEqual(result.evaluations[0].reason, decision)
                        self.assertIsNone(result.evaluations[0].episode_key)
                snapshot, = audit.snapshot()
                self.assertEqual(snapshot["counts"], {decision: 3})
                if not emits:
                    self.assertEqual(snapshot["last_exclusion"]["frame_index"], 2)
                    self.assertEqual(snapshot["last_exclusion"]["equipment_track_id"], 1)

    def test_unknown_inclusion_is_independent_of_legacy_rule_and_stays_unknown_on_the_wire(self):
        for scope in ({}, ELECTRIC | {"unknown_equipment_policy": "include"}):
            with self.subTest(scope=scope):
                engine, analyzer = configure(PAIR | scope)
                engine.evaluate(analyzer.update(0, (PERSON, EQUIPMENT)))
                result = engine.evaluate(analyzer.update(1, (PERSON, EQUIPMENT)))
                candidate, = result.candidates
                self.assertEqual(candidate.interaction.forklift.class_name, "forklift")
                payload = candidate_payload(candidate)
                context = EventContext(uuid4(), "fixture", datetime.now(timezone.utc))
                posted = event_candidate_payload(candidate, context)
                self.assertEqual("equipment_taxonomy" in payload, bool(scope))
                self.assertEqual("equipment_taxonomy" in posted["observations"], bool(scope))
                if scope:
                    self.assertEqual(result.evaluations[0].equipment_scope, "equipment_unknown_included")
                    self.assertEqual(payload["equipment_taxonomy"]["category"], "UNKNOWN")
                else:
                    self.assertIsNone(result.evaluations[0].equipment_scope)

    def test_zone_entry_and_dwell_apply_scope_to_equipment_only(self):
        outside = replace(EQUIPMENT, bounding_box=BoundingBox(0, 20, 8, 45))
        for kind in ("zone_entry", "zone_dwell"):
            parameters = {"kind": kind, "zone_id": "z", "class_name": "forklift", "min_duration_s": 0}
            for include in (False, True):
                with self.subTest(kind=kind, include=include):
                    engine, analyzer = configure(parameters | ELECTRIC | {
                        "unknown_equipment_policy": "include" if include else "exclude",
                    })
                    engine.evaluate(analyzer.update(0, (outside, PERSON)))
                    result = engine.evaluate(analyzer.update(1, (EQUIPMENT, PERSON)))
                    self.assertEqual(len(result.candidates), int(include))
                    self.assertIsNone(result.evaluations[1].equipment_scope)
                    if include:
                        context = EventContext(uuid4(), "fixture", datetime.now(timezone.utc))
                        posted = event_candidate_payload(result.candidates[0], context)
                        self.assertEqual(posted["observations"]["equipment_taxonomy"]["category"], "UNKNOWN")
                    else:
                        self.assertEqual(result.evaluations[0].reason, "equipment_unknown_excluded")

    def test_rejects_partial_scope_or_scope_on_non_equipment(self):
        for parameters in (
            PAIR | {"equipment_category": "ELECTRIC_STACKER"},
            PAIR | ELECTRIC | {"equipment_category": "UNKNOWN"},
            PAIR | ELECTRIC | {"unknown_equipment_policy": "motorized"},
            {"kind": "zone_dwell", "zone_id": "z", "class_name": "person", "min_duration_s": 1} | ELECTRIC,
        ):
            with self.subTest(parameters=parameters), self.assertRaises(RuleEngineError):
                configure(parameters)

    def test_loads_only_explicit_well_formed_profiles(self):
        document = {"schema_version": 1, "view_id": "fixture", "coordinate_system": "normalized",
                    "zones": [], "rules": []}
        profile = {"category": "MANUAL_STACKER", "source_sha256": SOURCE, "authority_reference": "review-1"}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(document), encoding="utf8")
            self.assertIsNone(load_operational_config(path).equipment_profile)
            path.write_text(json.dumps(document | {"equipment_profile": profile}), encoding="utf8")
            self.assertEqual(load_operational_config(path).equipment_profile, EquipmentProfile(**profile))
            for invalid in (None, profile | {"category": "UNKNOWN"}, profile | {"source_sha256": ""},
                            profile | {"authority_reference": ""}, profile | {"mixed": True}):
                path.write_text(json.dumps(document | {"equipment_profile": invalid}), encoding="utf8")
                with self.assertRaises(OperationalConfigError):
                    load_operational_config(path)
