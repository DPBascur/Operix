# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regla por pares con valores sintéticos EXPERIMENTALES / NOT VALIDATED."""

from __future__ import annotations

import json
import math
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.rules import EventCandidate, PairEventCandidate, RuleEngine
from operix_engine.spatiotemporal import ObjectIdentity, SpatiotemporalAnalyzer
from operix_engine.tracking import Track


def track(name="person", number=1, x=0.25, y=0.5):
    return Track(number, 0, name, 0.9, BoundingBox(x * 100 - 2, y * 100 - 4,
                                               x * 100 + 2, y * 100))


class PairProximityRuleTest(unittest.TestCase):
    def setUp(self):
        self.zone = Zone("lane", "Zona sintética", ((0.1, 0.1), (0.9, 0.1),
                                                   (0.9, 0.9), (0.1, 0.9)))
        self.person = track()
        # El borde izquierdo queda en x=.50: distancia exacta .25 desde PERSON.
        self.forklift = track("forklift", x=0.52)
        self.parameters = {
            "kind": "person_forklift_proximity", "zone_id": "lane",
            "max_distance": 0.25, "minimum_duration_seconds": 1.0,
        }
        self.configure()

    def configure(self, *, enabled=True, **changes):
        parameters = self.parameters | changes
        self.config = OperationalConfig(1, "synthetic", (self.zone,),
                                        (RuleConfig("pair_demo", 1, enabled, parameters),))
        self.engine = RuleEngine(self.config)
        self.analyzer = SpatiotemporalAnalyzer(width=100, height=100, fps=2, zones=(self.zone,),
                                             proximity_roles=self.config.proximity_roles)

    def step(self, frame, *objects, timestamp=None):
        state = self.analyzer.update(frame, tuple(objects))
        if timestamp is not None:
            state = replace(state, timestamp_s=timestamp)
        return self.engine.evaluate(state)

    def test_outside_distance_has_no_candidates(self):
        for frame in range(5):
            result = self.step(frame, self.person, track("forklift", x=0.8))
            self.assertEqual(result.candidates, ())
            self.assertEqual(result.evaluations[0].reason, "outside_distance")

    def test_insufficient_duration_has_no_candidates(self):
        for frame in (0, 1):
            result = self.step(frame, self.person, self.forklift)
            self.assertEqual(result.candidates, ())
            self.assertEqual(result.evaluations[0].reason, "insufficient_duration")

    def test_exact_distance_and_duration_are_inclusive(self):
        for frame in (0, 1):
            self.step(frame, self.person, self.forklift)
        candidate = self.step(2, self.person, self.forklift).candidates[0]
        self.assertEqual(candidate.observed_normalized_distance, 0.25)
        self.assertEqual(candidate.observed_duration_s, 1.0)

    def test_pair_duration_consumes_decoder_time_through_analyzer(self):
        tracks = (self.person, self.forklift)
        for frame, timestamp in enumerate((0., .4, .999)):
            self.assertEqual(self.engine.evaluate(self.analyzer.update(
                frame, tracks, timestamp_s=timestamp)).candidates, ())
        candidate = self.engine.evaluate(self.analyzer.update(3, tracks, timestamp_s=1.)).candidates[0]
        self.assertEqual(candidate.observed_duration_s, 1.)
        self.assertEqual(candidate.timestamp_s, 1.)

    def test_only_one_candidate_through_long_continuous_episode(self):
        emitted = [candidate for frame in range(100)
                   for candidate in self.step(frame, self.person, self.forklift).candidates]
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].frame_index, 2)

    def test_temporal_exact_two_seconds_triggers(self):
        self.configure(minimum_duration_seconds=2.0)
        self.step(0, self.person, self.forklift, timestamp=0.0)
        candidate = self.step(1, self.person, self.forklift, timestamp=2.0).candidates[0]
        self.assertEqual(candidate.observed_duration_s, 2.0)

    def test_temporal_subtraction_roundoff_triggers_without_rewriting_elapsed(self):
        start = 199 / 30
        for end, minimum in ((259 / 30, 2.0), (289 / 30, 3.0)):
            with self.subTest(minimum=minimum):
                self.configure(minimum_duration_seconds=minimum)
                elapsed = end - start
                self.assertLess(elapsed, minimum)
                self.step(0, self.person, self.forklift, timestamp=start)
                candidate = self.step(1, self.person, self.forklift, timestamp=end).candidates[0]
                self.assertEqual(candidate.observed_duration_s, elapsed)
                self.assertEqual(candidate.started_timestamp_s, start)
                self.assertEqual(candidate.timestamp_s, end)

    def test_temporal_materially_short_durations_do_not_trigger(self):
        for elapsed in (1.999, 1.99):
            with self.subTest(elapsed=elapsed):
                self.configure(minimum_duration_seconds=2.0)
                self.step(0, self.person, self.forklift, timestamp=0.0)
                result = self.step(1, self.person, self.forklift, timestamp=elapsed)
                self.assertEqual(result.candidates, ())
                self.assertEqual(result.evaluations[0].reason, "insufficient_duration")

    def test_temporal_above_threshold_triggers(self):
        self.configure(minimum_duration_seconds=2.0)
        self.step(0, self.person, self.forklift, timestamp=0.0)
        self.assertEqual(len(self.step(1, self.person, self.forklift, timestamp=2.001).candidates), 1)

    def test_temporal_tolerance_is_absolute_and_only_numeric(self):
        for minimum, elapsed, expected in (
            (2.0, 2.0 - 0.5e-9, 1),
            (2.0, 2.0 - 2e-9, 0),
            (1_000_000.0, 1_000_000.0 - 1e-6, 0),
        ):
            with self.subTest(minimum=minimum, elapsed=elapsed):
                self.configure(minimum_duration_seconds=minimum)
                self.step(0, self.person, self.forklift, timestamp=0.0)
                self.assertEqual(len(self.step(1, self.person, self.forklift, timestamp=elapsed).candidates), expected)

    def test_temporal_roundoff_does_not_duplicate_candidates(self):
        self.configure(minimum_duration_seconds=2.0)
        self.step(0, self.person, self.forklift, timestamp=199 / 30)
        self.assertEqual(len(self.step(1, self.person, self.forklift, timestamp=259 / 30).candidates), 1)
        self.assertEqual(self.step(2, self.person, self.forklift, timestamp=260 / 30).candidates, ())

    def test_temporal_roundoff_keeps_false_condition_and_explicit_reset(self):
        self.configure(minimum_duration_seconds=2.0)
        self.step(0, self.person, self.forklift, timestamp=199 / 30)
        self.assertEqual(len(self.step(1, self.person, self.forklift, timestamp=259 / 30).candidates), 1)
        self.assertEqual(self.step(2, self.person, track("forklift", x=0.8), timestamp=9.0).candidates, ())
        self.assertEqual(self.step(3, self.person, self.forklift, timestamp=10.0).candidates, ())
        self.assertEqual(self.step(4, self.person, self.forklift, timestamp=11.999).candidates, ())
        self.assertEqual(len(self.step(5, self.person, self.forklift, timestamp=12.0).candidates), 1)
        self.engine.reset()
        self.assertEqual(self.step(6, self.person, self.forklift, timestamp=13.0).candidates, ())

    def test_temporal_tolerance_does_not_relax_distance(self):
        self.configure(minimum_duration_seconds=2.0)
        self.step(0, self.person, self.forklift, timestamp=199 / 30)
        state = self.analyzer.update(1, (self.person, self.forklift))
        state = replace(state, timestamp_s=259 / 30, proximities=(
            replace(state.proximities[0], normalized_distance=math.nextafter(0.25, math.inf)),
        ))
        result = self.engine.evaluate(state)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.evaluations[0].reason, "outside_distance")

    def test_distance_break_then_reentry_requires_new_full_duration(self):
        for frame in range(3):
            self.step(frame, self.person, self.forklift)
        self.assertEqual(self.step(3, self.person, track("forklift", x=0.8)).candidates, ())
        for frame in (4, 5):
            self.assertEqual(self.step(frame, self.person, self.forklift).candidates, ())
        second = self.step(6, self.person, self.forklift).candidates[0]
        self.assertEqual((second.started_frame_index, second.frame_index), (4, 6))

    def test_either_object_leaving_zone_resets_episode(self):
        for name in ("person", "forklift"):
            with self.subTest(leaving=name):
                self.configure(max_distance=1.0)
                for frame in range(3):
                    self.step(frame, self.person, self.forklift)
                objects = (track("person", x=0.05) if name == "person" else self.person,
                           track("forklift", x=0.05) if name == "forklift" else self.forklift)
                self.assertEqual(self.step(3, *objects).evaluations[0].reason, "outside_zone")
                for frame in (4, 5):
                    self.assertEqual(self.step(frame, self.person, self.forklift).candidates, ())
                self.assertEqual(self.step(6, self.person, self.forklift).candidates[0].started_frame_index, 4)

    def test_either_object_disappearing_resets_episode(self):
        for survivor in (self.person, self.forklift):
            with self.subTest(survivor=survivor.class_name):
                self.configure()
                for frame in range(3):
                    self.step(frame, self.person, self.forklift)
                self.assertEqual(self.step(3, survivor).candidates, ())
                for frame in (4, 5):
                    self.assertEqual(self.step(frame, self.person, self.forklift).candidates, ())
                self.assertEqual(len(self.step(6, self.person, self.forklift).candidates), 1)

    def test_shared_numeric_id_preserves_two_identities(self):
        self.configure(minimum_duration_seconds=0)
        candidate = self.step(0, self.person, self.forklift).candidates[0]
        self.assertEqual(candidate.interaction.person, ObjectIdentity("person", 1))
        self.assertEqual(candidate.interaction.forklift, ObjectIdentity("forklift", 1))
        self.assertNotEqual(candidate.interaction.person, candidate.interaction.forklift)

    def test_two_forklifts_have_independent_timers(self):
        second = track("forklift", 2, x=0.4)
        self.step(0, self.person, self.forklift)
        self.step(1, self.person, self.forklift, second)
        first = self.step(2, self.person, self.forklift, second).candidates
        later = self.step(3, self.person, self.forklift, second).candidates
        self.assertEqual([c.interaction.forklift.track_id for c in first], [1])
        self.assertEqual([c.interaction.forklift.track_id for c in later], [2])

    def test_two_people_have_independent_timers(self):
        second = track("person", 2, x=0.4)
        self.step(0, self.person, self.forklift)
        self.step(1, self.person, second, self.forklift)
        first = self.step(2, self.person, second, self.forklift).candidates
        later = self.step(3, self.person, second, self.forklift).candidates
        self.assertEqual([c.interaction.person.track_id for c in first], [1])
        self.assertEqual([c.interaction.person.track_id for c in later], [2])

    def test_many_objects_only_valid_cross_pairs_activate(self):
        self.configure(max_distance=0.125, minimum_duration_seconds=0)
        objects = (track("person", 1, 0.25), track("forklift", 1, 0.375),
                   track("person", 2, 0.75), track("forklift", 2, 0.875))
        candidates = self.step(0, *objects).candidates
        self.assertEqual({(c.interaction.person.track_id, c.interaction.forklift.track_id)
                          for c in candidates}, {(1, 1), (2, 2)})
        self.assertEqual(self.step(1, *reversed(objects)).candidates, ())

    def test_same_class_and_other_classes_are_ignored(self):
        for name in ("person", "forklift", "truck"):
            with self.subTest(class_name=name):
                self.configure(minimum_duration_seconds=0)
                result = self.step(0, track(name, 1), track(name, 2, x=0.5))
                self.assertEqual(result.candidates, ())
                self.assertEqual(result.evaluations, ())
        self.configure(minimum_duration_seconds=0)
        self.assertEqual(self.step(0, self.person, track("truck", x=0.5)).candidates, ())

    def test_disabled_rule_never_emits(self):
        self.configure(enabled=False, minimum_duration_seconds=0)
        for frame in range(5):
            self.assertEqual(self.step(frame, self.person, self.forklift).candidates, ())

    def test_uses_timestamps_rather_than_number_of_frames(self):
        self.step(0, self.person, self.forklift, timestamp=10.0)
        self.assertEqual(self.step(1, self.person, self.forklift, timestamp=10.1).candidates, ())
        candidate = self.step(2, self.person, self.forklift, timestamp=12.0).candidates[0]
        self.assertEqual(candidate.observed_duration_s, 2.0)
        self.assertEqual(candidate.started_timestamp_s, 10.0)

    def test_pair_order_is_independent_of_proximity_orientation(self):
        self.configure(minimum_duration_seconds=0)
        state = self.analyzer.update(0, (self.person, self.forklift))
        pair = state.proximities[0]
        reverse = replace(pair, track_id_a=pair.track_id_b, track_id_b=pair.track_id_a,
                          class_name_a=pair.class_name_b, class_name_b=pair.class_name_a,
                          point_a=pair.point_b, point_b=pair.point_a)
        first = self.engine.evaluate(state).candidates[0]
        self.engine.reset()
        second = self.engine.evaluate(replace(state, proximities=(reverse,))).candidates[0]
        self.assertEqual(first, second)

    def test_candidate_is_explainable_serializable_and_immutable(self):
        self.configure(person_class="person", forklift_class="forklift")
        for frame in range(3):
            result = self.step(frame, self.person, self.forklift)
        candidate = result.candidates[0]
        self.assertIsInstance(candidate, PairEventCandidate)
        self.assertNotIsInstance(candidate, EventCandidate)
        payload = json.loads(json.dumps(candidate.to_dict(), allow_nan=False))
        self.assertEqual((payload["rule_id"], payload["rule_version"]), ("pair_demo", 1))
        self.assertEqual((payload["started_frame_index"], payload["frame_index"]), (0, 2))
        self.assertEqual((payload["started_timestamp_s"], payload["timestamp_s"]), (0, 1))
        self.assertEqual(payload["candidate_type"], "person_forklift_proximity")
        self.assertEqual(payload["zone_id"], "lane")
        self.assertEqual(payload["parameters"]["max_distance"], 0.25)
        self.assertEqual(payload["parameters"]["minimum_duration_seconds"], 1)
        self.assertEqual(payload["interaction"]["person"], {"class_name": "person", "track_id": 1})
        self.assertEqual(payload["interaction"]["forklift"], {"class_name": "forklift", "track_id": 1})
        self.assertIn("revisión humana", payload["reason"])
        with self.assertRaises(TypeError):
            candidate.parameters["max_distance"] = 100
        with self.assertRaises(FrozenInstanceError):
            candidate.interaction.person = ObjectIdentity("person", 2)

    def test_zone_dwell_results_unchanged_with_pair_rule_enabled_or_disabled(self):
        dwell = RuleConfig("demo_zone_dwell", 1, True, {
            "kind": "zone_dwell", "class_name": "person", "zone_id": "lane", "min_duration_s": 1,
        })
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                self.configure(enabled=enabled)
                mixed = RuleEngine(replace(self.config, rules=(dwell,) + self.config.rules))
                baseline = RuleEngine(replace(self.config, rules=(dwell,)))
                for frame in range(7):
                    objects = (self.forklift,) if frame == 3 else (self.person, self.forklift)
                    state = self.analyzer.update(frame, objects)
                    actual, expected = mixed.evaluate(state), baseline.evaluate(state)
                    self.assertEqual(tuple(c for c in actual.candidates if isinstance(c, EventCandidate)),
                                     expected.candidates)
                    self.assertEqual(tuple(e for e in actual.evaluations if e.rule_id == dwell.rule_id),
                                     expected.evaluations)

    def test_person_only_state_preserves_existing_rule(self):
        dwell = RuleConfig("demo_zone_dwell", 1, True, {
            "kind": "zone_dwell", "class_name": "person", "zone_id": "lane", "min_duration_s": 0,
        })
        self.engine = RuleEngine(replace(self.config, rules=(dwell,) + self.config.rules))
        result = self.step(0, self.person)
        self.assertEqual(len(result.candidates), 1)
        self.assertIsInstance(result.candidates[0], EventCandidate)

    def test_forklift_only_state_has_no_pair_candidates(self):
        for frame in range(5):
            self.assertEqual(self.step(frame, self.forklift).candidates, ())

    def test_reset_and_frame_gap_start_fresh_episode(self):
        self.step(0, self.person, self.forklift)
        self.assertEqual(self.step(2, self.person, self.forklift).candidates, ())
        self.step(3, self.person, self.forklift)
        self.assertEqual(self.step(4, self.person, self.forklift).candidates[0].started_frame_index, 2)
        self.engine.reset()
        state = self.analyzer.update(5, (self.person, self.forklift))
        self.assertEqual(self.engine.evaluate(state).candidates, ())

    def test_nonmonotonic_or_invalid_timestamp_does_not_advance_state(self):
        self.step(0, self.person, self.forklift)
        state = self.analyzer.update(1, (self.person, self.forklift))
        for timestamp in (-1, math.nan, math.inf, 0, True):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.engine.evaluate(replace(state, timestamp_s=timestamp))
        self.assertEqual(self.engine.evaluate(state).candidates, ())
        self.assertEqual(len(self.step(2, self.person, self.forklift).candidates), 1)

    def test_missing_zone_or_proximity_breaks_episode_without_recalculation(self):
        for missing in ("zone", "proximity"):
            with self.subTest(missing=missing):
                self.configure()
                self.step(0, self.person, self.forklift)
                state = self.analyzer.update(1, (self.person, self.forklift))
                if missing == "zone":
                    state = replace(state, objects=tuple(replace(obj, zones=()) for obj in state.objects))
                else:
                    state = replace(state, proximities=())
                self.assertEqual(self.engine.evaluate(state).candidates, ())
                self.assertEqual(self.step(2, self.person, self.forklift).candidates, ())
                self.step(3, self.person, self.forklift)
                self.assertEqual(self.step(4, self.person, self.forklift).candidates[0].started_frame_index, 2)

    def test_consumes_supplied_distance_not_recomputed_geometry(self):
        self.configure(minimum_duration_seconds=0)
        state = self.analyzer.update(0, (self.person, self.forklift))
        state = replace(state, proximities=(replace(state.proximities[0], normalized_distance=0.9),))
        self.assertEqual(self.engine.evaluate(state).candidates, ())

    def test_unversioned_pair_geometry_is_not_silently_used_for_new_analysis(self):
        state = self.analyzer.update(0, (self.person, self.forklift))
        pair = replace(state.proximities[0], geometry_version=None, point_a=None, point_b=None)
        with self.assertRaisesRegex(ValueError, "ground-edge"):
            self.engine.evaluate(replace(state, proximities=(pair,)))

    def test_configurable_roles_and_class_ids_are_independent(self):
        self.configure(person_class="worker", forklift_class="vehicle", minimum_duration_seconds=0)
        result = self.step(0, track("worker"), replace(track("vehicle", x=0.5), class_id=99))
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].interaction.person.class_name, "worker")

    def test_multiple_configured_rules_keep_independent_episodes(self):
        second = RuleConfig("second", 2, True, self.parameters | {"minimum_duration_seconds": 0})
        self.engine = RuleEngine(replace(self.config, rules=self.config.rules + (second,)))
        self.assertEqual([c.rule_id for c in self.step(0, self.person, self.forklift).candidates], ["second"])
        self.step(1, self.person, self.forklift)
        self.assertEqual([c.rule_id for c in self.step(2, self.person, self.forklift).candidates], ["pair_demo"])

    def test_zero_duration_and_zero_distance_allow_coincident_objects(self):
        self.configure(max_distance=0, minimum_duration_seconds=0)
        self.assertEqual(len(self.step(0, self.person, track("forklift", x=0.25)).candidates), 1)

    def test_rule_stays_in_memory_and_does_not_post(self):
        self.configure(minimum_duration_seconds=0)
        with patch("operix_engine.event_publishing.urlopen") as send:
            result = self.step(0, self.person, self.forklift)
        self.assertEqual(len(result.candidates), 1)
        send.assert_not_called()

    def test_invalid_configuration_is_rejected(self):
        for field in ("max_distance", "minimum_duration_seconds"):
            for value in (-1, math.inf, math.nan, True, "1"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.configure(**{field: value})
        for field in ("person_class", "forklift_class", "zone_id"):
            for value in ("", " ", 42):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.configure(**{field: value})
        with self.assertRaises(ValueError):
            self.configure(person_class="person", forklift_class="person")
        with self.assertRaises(ValueError):
            self.configure(zone_id="unknown")
        with self.assertRaises(ValueError):
            self.configure(extra=1)
        for field in self.parameters:
            parameters = dict(self.parameters)
            del parameters[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                RuleEngine(replace(self.config, rules=(RuleConfig("r", 1, True, parameters),)))


if __name__ == "__main__":
    unittest.main()
