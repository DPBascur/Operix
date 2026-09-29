# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas de OP-38 con variables OP-37 controladas, sin YOLO ni ByteTrack."""

from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone, load_operational_config
from operix_engine.rules import RuleEngine, RuleEngineError
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track


EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "examples" / "op30-zone-rule.json"


def make_track(track_id: int = 1, *, inside: bool = True, class_name: str = "person") -> Track:
    x = 40 if inside else 80
    return Track(track_id, 0, class_name, 0.9, BoundingBox(x - 5, 40, x + 5, 50))


class RuleEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_operational_config(EXAMPLE)
        self.analyzer = SpatiotemporalAnalyzer(
            width=100, height=100, fps=2, zones=self.config.zones
        )
        self.engine = RuleEngine(self.config)

    def configure(self, *, enabled: bool = True, version: int = 1,
                  rule_id: str = "restricted_zone_presence", **parameters: object) -> None:
        values = dict(self.config.rules[0].parameters)
        values.update(parameters)
        rule = RuleConfig(rule_id, version, enabled, values)
        self.config = OperationalConfig(1, self.config.view_id, self.config.zones, (rule,))
        self.engine = RuleEngine(self.config)

    def step(self, frame_index: int, *tracks: Track):
        return self.engine.evaluate(self.analyzer.update(frame_index, tuple(tracks)))

    def test_positive_rule_at_threshold(self) -> None:
        for frame in range(4):
            self.assertEqual(self.step(frame, make_track()).candidates, ())
        result = self.step(4, make_track())
        self.assertEqual(len(result.candidates), 1)
        self.assertTrue(result.evaluations[0].satisfied)

    def test_outside_zone_is_negative(self) -> None:
        result = self.step(0, make_track(inside=False))
        self.assertEqual(result.evaluations[0].reason, "outside_zone")
        self.assertFalse(result.evaluations[0].satisfied)
        self.assertEqual(result.candidates, ())

    def test_insufficient_dwell_is_negative(self) -> None:
        result = self.step(0, make_track())
        self.assertEqual(result.evaluations[0].observed_dwell_time_s, 0)
        self.assertEqual(result.evaluations[0].reason, "insufficient_dwell")

    def test_exact_threshold_is_inclusive(self) -> None:
        for frame in range(4):
            self.step(frame, make_track())
        result = self.step(4, make_track())
        self.assertEqual(result.candidates[0].observed_dwell_time_s, 2.0)

    def test_above_threshold_is_positive_without_duplicate(self) -> None:
        for frame in range(5):
            self.step(frame, make_track())
        result = self.step(5, make_track())
        self.assertTrue(result.evaluations[0].satisfied)
        self.assertEqual(result.evaluations[0].observed_dwell_time_s, 2.5)
        self.assertEqual(result.candidates, ())

    def test_disabled_rule_is_not_evaluated(self) -> None:
        self.configure(enabled=False, min_duration_s=0)
        result = self.step(0, make_track())
        self.assertEqual(result.evaluations[0].reason, "disabled")
        self.assertFalse(result.evaluations[0].evaluated)
        self.assertEqual(result.candidates, ())

    def test_class_mismatch_is_not_applicable(self) -> None:
        self.configure(min_duration_s=0)
        result = self.step(0, make_track(class_name="truck"))
        self.assertEqual(result.evaluations[0].reason, "class_mismatch")
        self.assertFalse(result.evaluations[0].evaluated)
        self.assertEqual(result.candidates, ())

    def test_different_observed_zone_is_not_the_configured_zone(self) -> None:
        self.configure(min_duration_s=0)
        other = Zone("otra_zona", "Otra zona", ((0.2, 0.2), (0.6, 0.2), (0.6, 0.7), (0.2, 0.7)))
        other_zone_analyzer = SpatiotemporalAnalyzer(
            width=100, height=100, fps=2, zones=(other,)
        )
        result = self.engine.evaluate(other_zone_analyzer.update(0, (make_track(),)))
        self.assertEqual(result.evaluations[0].reason, "zone_missing")
        self.assertEqual(result.candidates, ())

    def test_threshold_is_configurable(self) -> None:
        self.configure(min_duration_s=0.5)
        self.assertEqual(self.step(0, make_track()).candidates, ())
        self.assertEqual(len(self.step(1, make_track()).candidates), 1)

    def test_id_version_and_parameters_preserved(self) -> None:
        self.configure(rule_id="custom", version=3, min_duration_s=0)
        result = self.step(0, make_track())
        candidate = result.candidates[0]
        self.assertEqual((candidate.rule_id, candidate.rule_version), ("custom", 3))
        self.assertEqual(dict(candidate.parameters), dict(self.config.rules[0].parameters))
        self.assertEqual(dict(result.evaluations[0].parameters), dict(candidate.parameters))
        with self.assertRaises(TypeError):
            candidate.parameters["min_duration_s"] = 99  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            candidate.track_id = 2  # type: ignore[misc]

    def test_false_true_emits_candidate(self) -> None:
        self.configure(min_duration_s=0)
        self.assertEqual(self.step(0, make_track(inside=False)).candidates, ())
        self.assertEqual(len(self.step(1, make_track()).candidates), 1)

    def test_true_true_does_not_duplicate(self) -> None:
        self.configure(min_duration_s=0)
        self.step(0, make_track())
        self.assertTrue(self.step(1, make_track()).evaluations[0].satisfied)
        self.assertEqual(self.step(2, make_track()).candidates, ())

    def test_true_false_rearms(self) -> None:
        self.configure(min_duration_s=0)
        self.step(0, make_track())
        result = self.step(1, make_track(inside=False))
        self.assertFalse(result.evaluations[0].satisfied)
        self.assertEqual(len(self.step(2, make_track()).candidates), 1)

    def test_false_true_again_emits_second_candidate(self) -> None:
        self.configure(min_duration_s=0)
        first = self.step(0, make_track()).candidates
        self.step(1, make_track(inside=False))
        second = self.step(2, make_track()).candidates
        self.assertEqual((len(first), len(second)), (1, 1))

    def test_multiple_tracks_are_independent(self) -> None:
        self.configure(min_duration_s=0)
        first = self.step(0, make_track(1), make_track(2))
        self.assertEqual({item.track_id for item in first.candidates}, {1, 2})
        second = self.step(1, make_track(1), make_track(2))
        self.assertEqual(second.candidates, ())

    def test_absent_track_rearms(self) -> None:
        self.configure(min_duration_s=0)
        self.step(0, make_track())
        self.assertEqual(self.step(1).evaluations, ())
        self.assertEqual(len(self.step(2, make_track()).candidates), 1)

    def test_gap_from_op37_resets_dwell_and_rearms(self) -> None:
        self.configure(min_duration_s=0)
        self.step(0, make_track())
        result = self.step(2, make_track())
        self.assertEqual(result.evaluations[0].observed_dwell_time_s, 0)
        self.assertEqual(len(result.candidates), 1)

    def test_invalid_min_duration_and_fields(self) -> None:
        for value in (True, -1, math.inf, math.nan, "2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.configure(min_duration_s=value)
        for name, value in (("class_name", ""), ("class_name", 2), ("zone_id", 1)):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                self.configure(**{name: value})
        for omitted in ("kind", "class_name", "zone_id", "min_duration_s"):
            with self.subTest(omitted=omitted), self.assertRaises(RuleEngineError):
                values = dict(self.config.rules[0].parameters)
                values.pop(omitted)
                config = OperationalConfig(1, "view", self.config.zones,
                                           (RuleConfig("r", 1, True, values),))
                RuleEngine(config)

    def test_unsupported_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuleEngineError, "kind no soportado"):
            self.configure(kind="proximity")
        with self.assertRaises(RuleEngineError):
            self.configure(unexpected=1)

    def test_reset_and_new_configuration_start_new_session(self) -> None:
        self.configure(min_duration_s=0)
        frame = self.analyzer.update(0, (make_track(),))
        self.assertEqual(len(self.engine.evaluate(frame).candidates), 1)
        self.engine.reset()
        self.assertEqual(len(self.engine.evaluate(frame).candidates), 1)
        self.configure(version=2, min_duration_s=0)
        self.assertEqual(self.step(1, make_track()).candidates[0].rule_version, 2)

    def test_nonmonotonic_frame_is_rejected_without_losing_state(self) -> None:
        self.configure(min_duration_s=0)
        frame = self.analyzer.update(0, (make_track(),))
        self.engine.evaluate(frame)
        with self.assertRaises(RuleEngineError):
            self.engine.evaluate(frame)
        self.assertEqual(self.step(1, make_track()).candidates, ())


if __name__ == "__main__":
    unittest.main()
