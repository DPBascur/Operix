# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transporte sintético sin modelos, HTTP ni persistencia."""

import json
import math
import hashlib
import io
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import asdict, replace
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from operix_engine.candidate_transport import candidate_payload, candidate_payloads
from operix_engine.detection import BoundingBox
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone, load_operational_config
from operix_engine.rules import EventCandidate, InteractionIdentity, PairEventCandidate
from operix_engine.spatiotemporal import ObjectIdentity
from operix_engine.tracking import Track


class CandidateTransportTest(unittest.TestCase):
    def setUp(self):
        self.single = EventCandidate(
            "demo_zone_dwell", 1, 4, 2.0, 1, "person", "lane",
            MappingProxyType({"kind": "zone_dwell", "class_name": "person",
                              "zone_id": "lane", "min_duration_s": 1.0}), True, 2.0,
        )
        self.pair = PairEventCandidate(
            "pair_demo", 1, 4, 2.0,
            InteractionIdentity(ObjectIdentity("person", 1), ObjectIdentity("forklift", 1)),
            "lane", MappingProxyType({"kind": "person_forklift_proximity", "zone_id": "lane",
                                      "person_class": "person", "forklift_class": "forklift",
                                      "max_distance": 0.25, "minimum_duration_seconds": 1.0}),
            2, 1.0, 0.2, 1.0,
        )

    def test_exact_legacy_zone_dwell_fields_are_preserved(self):
        legacy = {
            "rule_id": "demo_zone_dwell", "rule_version": 1, "frame_index": 4,
            "timestamp_s": 2.0, "track_id": 1, "class_name": "person", "zone_id": "lane",
            "parameters": {"kind": "zone_dwell", "class_name": "person",
                           "zone_id": "lane", "min_duration_s": 1.0},
            "observed_inside": True, "observed_dwell_time_s": 2.0,
        }
        payload = candidate_payload(self.single)
        self.assertEqual({key: payload[key] for key in legacy}, legacy)
        self.assertEqual(set(payload) - legacy.keys(), {"candidate_kind", "subjects"})

    def test_single_subject_is_explicit_without_changing_local_id(self):
        payload = candidate_payload(self.single)
        self.assertEqual(payload["candidate_kind"], "zone_dwell")
        self.assertEqual(payload["subjects"], [{"role": "object", "class_name": "person", "track_id": 1}])

    def test_pair_preserves_every_existing_to_dict_field(self):
        payload = candidate_payload(self.pair)
        previous = self.pair.to_dict()
        self.assertEqual({key: payload[key] for key in previous}, previous)
        self.assertEqual(payload["candidate_kind"], "person_forklift_proximity")

    def test_same_numeric_ids_keep_both_roles_without_primary_or_global_id(self):
        payload = candidate_payload(self.pair)
        self.assertNotIn("track_id", payload)
        self.assertNotIn("class_name", payload)
        self.assertEqual(payload["subjects"], [
            {"role": "person", "class_name": "person", "track_id": 1},
            {"role": "forklift", "class_name": "forklift", "track_id": 1},
        ])
        self.assertNotEqual(payload["interaction"]["person"], payload["interaction"]["forklift"])

    def test_roles_follow_named_fields_not_sorted_class_order(self):
        person = ObjectIdentity("person", 7)
        forklift = ObjectIdentity("forklift", 3)
        payload = candidate_payload(replace(self.pair, interaction=InteractionIdentity(person, forklift)))
        roles = {subject["role"]: subject for subject in reversed(payload["subjects"])}
        self.assertEqual(roles["person"]["track_id"], 7)
        self.assertEqual(roles["forklift"]["track_id"], 3)

    def test_distance_and_rule_parameters_keep_image_plane_names(self):
        payload = candidate_payload(self.pair)
        self.assertEqual(payload["observed_normalized_distance"], 0.2)
        self.assertEqual(payload["parameters"]["max_distance"], 0.25)
        self.assertEqual(payload["parameters"]["minimum_duration_seconds"], 1.0)
        for forbidden in ("meters", "metres", "centimeters", "physical_distance", "safe_distance"):
            self.assertNotIn(forbidden, payload)
            self.assertNotIn(forbidden, payload["parameters"])

    def test_start_and_trigger_coordinates_are_preserved(self):
        payload = candidate_payload(self.pair)
        self.assertEqual((payload["started_frame_index"], payload["started_timestamp_s"]), (2, 1.0))
        self.assertEqual((payload["frame_index"], payload["timestamp_s"]), (4, 2.0))
        self.assertEqual(payload["observed_duration_s"], 1.0)
        self.assertIn("revisión humana", payload["reason"])

    def test_mixed_collection_is_json_serializable_and_deterministic(self):
        candidates = (self.single, self.pair)
        first = json.dumps(candidate_payloads(candidates), allow_nan=False)
        self.assertEqual(first, json.dumps(candidate_payloads(candidates), allow_nan=False))
        self.assertEqual([item["candidate_kind"] for item in json.loads(first)],
                         ["zone_dwell", "person_forklift_proximity"])
        self.assertEqual(candidate_payloads(()), [])

    def test_parameter_order_does_not_change_serialized_output(self):
        candidate = replace(self.single, parameters=dict(reversed(list(self.single.parameters.items()))))
        self.assertEqual(json.dumps(candidate_payload(candidate)), json.dumps(candidate_payload(self.single)))

    def test_unknown_candidate_is_rejected_explicitly(self):
        for value in (None, {}, object(), self.pair.to_dict()):
            with self.subTest(type=type(value)), self.assertRaises(TypeError):
                candidate_payload(value)

    def test_mismatched_discriminators_are_rejected(self):
        for candidate in (self.single, self.pair):
            with self.subTest(type=type(candidate)), self.assertRaises(ValueError):
                candidate_payload(replace(candidate, parameters={"kind": "unknown"}))

    def test_invalid_identity_or_pair_roles_are_rejected(self):
        for candidate in (replace(self.single, track_id=0), replace(self.single, class_name=""),
                          replace(self.pair, interaction=None),
                          replace(self.pair, interaction=InteractionIdentity(None, None)),
                          replace(self.pair, interaction=InteractionIdentity(
                              self.pair.interaction.forklift, self.pair.interaction.person))):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                candidate_payload(candidate)

    def test_nonfinite_numbers_and_invalid_episode_are_rejected(self):
        for candidate in (replace(self.single, timestamp_s=math.nan),
                          replace(self.single, observed_dwell_time_s=-1),
                          replace(self.pair, observed_normalized_distance=math.inf),
                          replace(self.pair, started_frame_index=5),
                          replace(self.pair, started_timestamp_s=3)):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                candidate_payload(candidate)

    def test_python_objects_cannot_leak_into_parameters(self):
        with self.assertRaises(ValueError):
            candidate_payload(replace(self.single, parameters=dict(self.single.parameters) | {"bad": object()}))

    def test_transport_neither_posts_nor_mutates_candidates(self):
        before = self.pair.to_dict()
        with patch("urllib.request.urlopen") as send:
            payload = candidate_payload(self.pair)
        send.assert_not_called()
        payload["subjects"][0]["track_id"] = 99
        self.assertEqual(self.pair.to_dict(), before)

    def test_pair_rule_remains_absent_from_active_demo_profiles(self):
        examples = Path(__file__).resolve().parents[1] / "config/examples"
        for name in ("desktop-zone-dwell.json", "warehouse-nearmiss-zone-dwell.json",
                     "warehouse-box-pickup-zone-dwell.json"):
            with self.subTest(profile=name):
                config = load_operational_config(examples / name)
                self.assertFalse(any(rule.enabled and rule.parameters.get("kind") == "person_forklift_proximity"
                                     for rule in config.rules))

    def _replay(self, *, publish_pair_only):
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        zone = Zone("lane", "Sintética", ((0, 0), (1, 0), (1, 1), (0, 1)))
        single = RuleConfig("single", 1, True, dict(self.single.parameters) | {"min_duration_s": 0})
        pair = RuleConfig("pair", 1, True, dict(self.pair.parameters) | {"minimum_duration_seconds": 0})
        config = OperationalConfig(1, "synthetic", (zone,), (pair,) if publish_pair_only else (single, pair))
        tracks = [asdict(Track(1, 0, name, 0.9, BoundingBox(x, 10, x + 10, 40)))
                  for name, x in (("person", 10), ("forklift", 20))]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.jsonl"
            path.write_text(json.dumps({"frame_index": 0, "tracks": tracks}) + "\n", encoding="utf-8")
            args = [str(scripts / "evaluate_rules.py"), str(path),
                    "--expected-jsonl-sha256", hashlib.sha256(path.read_bytes()).hexdigest(),
                    "--config", "synthetic.json", "--view-id", "synthetic",
                    "--width", "100", "--height", "100", "--fps", "30", "--end-frame", "0"]
            if publish_pair_only:
                args += ["--publish-api", "--analysis-run-id", "00000000-0000-0000-0000-000000000001",
                         "--recording-start-at", "2026-01-01T00:00:00Z"]
            output = io.StringIO()
            with (
                patch.object(sys, "argv", args),
                patch("operix_engine.operational_config.load_operational_config", return_value=config),
                patch("operix_engine.event_publishing.HttpEventSink") as sink,
                patch("urllib.request.urlopen") as send,
                redirect_stdout(output),
                self.assertRaises(SystemExit) as result,
            ):
                runpy.run_path(args[0], run_name="__main__")
            self.assertEqual(result.exception.code, 0)
            sink.return_value.publish.assert_not_called()
            send.assert_not_called()
            return json.loads(output.getvalue())

    def test_replay_transports_both_kinds_without_publication(self):
        payload = self._replay(publish_pair_only=False)
        self.assertEqual([c["candidate_kind"] for c in payload["candidates"]],
                         ["zone_dwell", "person_forklift_proximity"])
        self.assertNotIn("publications", payload)

    def test_replay_explicitly_skips_pair_at_legacy_publication_boundary(self):
        payload = self._replay(publish_pair_only=True)
        self.assertEqual(payload["publications"][0]["reason"], "pair_persistence_not_supported")
        self.assertEqual(payload["publications"][0]["status"], "skipped")
        self.assertEqual(len(payload["publications"][0]["candidate"]["subjects"]), 2)


if __name__ == "__main__":
    unittest.main()
