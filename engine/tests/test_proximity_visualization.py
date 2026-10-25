"""Relaciones reales de la regla, sin modelos ni material de evaluación."""
import unittest
from dataclasses import replace
from unittest.mock import patch

import cv2
import numpy as np

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track
from operix_engine.visualization import OpenCvRenderer


def track(name, number, x, y):
    return Track(number, 0, name, .9, BoundingBox(x - 5, y - 10, x + 5, y))


class ProximityVisualizationTests(unittest.TestCase):
    def setUp(self):
        self.zone = Zone("floor", "Fixture", ((0, 0), (1, 0), (1, 1), (0, 1)))
        self.config = OperationalConfig(1, "fixture", (self.zone,), (
            RuleConfig("pair", 1, True, {"kind": "person_forklift_proximity", "zone_id": "floor",
                "max_distance": .5, "minimum_duration_seconds": 1.}),))
        self.analyzer = SpatiotemporalAnalyzer(width=100, height=100, fps=30, zones=(self.zone,))
        self.rules = RuleEngine(self.config)
        self.renderer = OpenCvRenderer()
        self.frame = np.zeros((100, 100, 3), dtype=np.uint8)
        self.person, self.forklift = track("person", 1, 20, 20), track("forklift", 1, 50, 60)

    def step(self, index, tracks=None, timestamp=None):
        spatial = self.analyzer.update(index, tracks if tracks is not None else (self.person, self.forklift),
                                       timestamp_s=index / 30 if timestamp is None else timestamp)
        return spatial, self.rules.evaluate(spatial)

    def test_known_distance_geometry_and_same_numeric_ids(self):
        spatial, result = self.step(0)
        evaluation = result.evaluations[0]
        self.assertAlmostEqual(evaluation.observed_normalized_distance, np.hypot(.2, .4))
        self.assertNotEqual(evaluation.interaction.person, evaluation.interaction.forklift)
        with patch("operix_engine.visualization.cv2.line", wraps=cv2.line) as line, \
                patch.object(self.renderer, "_draw_label", wraps=self.renderer._draw_label) as labels:
            annotated = self.renderer.render_proximity(self.frame, spatial, result)
        self.assertEqual(line.call_args.args[1:3], ((25, 20), (45, 60)))
        self.assertTrue(any("0.447 norm" in call.args[1] for call in labels.call_args_list))
        self.assertTrue(any("DURATION_ACCUMULATING" in call.args[1] for call in labels.call_args_list))
        self.assertTrue(np.any(annotated))
        self.assertFalse(np.any(self.frame))

    def test_episode_key_matches_candidate_and_remains_stable(self):
        _, start = self.step(0, timestamp=0.)
        _, emitted = self.step(1, timestamp=1.)
        _, continued = self.step(2, timestamp=2.)
        key = start.evaluations[0].episode_key
        self.assertEqual(key, emitted.candidates[0].episode_key)
        self.assertEqual(key, continued.evaluations[0].episode_key)
        self.assertEqual(continued.evaluations[0].rule_state, "CONDITION_SATISFIED")
        self.assertEqual(continued.candidates, ())

    def test_gaps_replacements_exit_and_reentry_start_new_episode(self):
        for change in ("person_missing", "forklift_missing", "distance", "replacement", "frame_gap"):
            with self.subTest(change=change):
                self.setUp()
                _, initial = self.step(0, timestamp=0.)
                if change == "frame_gap":
                    spatial, result = self.step(2, timestamp=1.)
                    self.assertEqual(result.evaluations[0].started_frame_index, 2)
                else:
                    tracks = {"person_missing": (self.forklift,), "forklift_missing": (self.person,),
                              "distance": (self.person, track("forklift", 1, 95, 95)),
                              "replacement": (replace(self.person, track_id=2), self.forklift)}[change]
                    self.step(1, tracks, timestamp=.5)
                    spatial, result = self.step(2, timestamp=1.)
                    self.assertEqual(result.evaluations[0].started_frame_index, 2)
                self.assertNotEqual(initial.evaluations[0].episode_key, result.evaluations[0].episode_key)
                self.assertEqual(result.candidates, ())

    def test_outside_or_no_pair_has_no_line(self):
        for tracks in ((), (self.person,), (self.person, track("forklift", 1, 95, 95))):
            self.setUp()
            spatial, result = self.step(0, tracks)
            with patch("operix_engine.visualization.cv2.line") as line:
                self.renderer.render_proximity(self.frame, spatial, result)
            line.assert_not_called()

    def test_multiple_roles_and_crossing_preserve_identity(self):
        tracks = (self.person, track("person", 2, 40, 50), self.forklift, track("forklift", 2, 25, 25))
        spatial, result = self.step(0, tracks)
        self.assertEqual(len(result.evaluations), 4)
        self.assertEqual(len({item.interaction for item in result.evaluations}), 4)
        with patch("operix_engine.visualization.cv2.line", wraps=cv2.line) as lines:
            self.renderer.render_proximity(self.frame, spatial, result, max_pairs=1)
        self.assertEqual(lines.call_count, 1)
        _, crossed = self.step(1, (track("person", 1, 50, 60), track("forklift", 1, 20, 20)))
        self.assertEqual(crossed.evaluations[0].interaction, result.evaluations[0].interaction)

    def test_current_emissions_are_not_hidden_by_visual_limit(self):
        tracks = (self.person, track("person", 2, 40, 50), self.forklift)
        self.step(0, tracks, timestamp=0.)
        spatial, result = self.step(1, tracks, timestamp=1.)
        self.assertEqual(len(result.candidates), 2)
        with patch("operix_engine.visualization.cv2.line", wraps=cv2.line) as line:
            self.renderer.render_proximity(self.frame, spatial, result, max_pairs=1)
        self.assertEqual(line.call_count, 2)

    def test_overlap_containment_zero_and_edge_positions_use_anchor_distance(self):
        for forklift, expected in ((replace(self.forklift, bounding_box=self.person.bounding_box), 0.),
                (replace(self.forklift, bounding_box=BoundingBox(0, 0, 80, 80)), .6),
                (replace(self.forklift, bounding_box=BoundingBox(90, 90, 100, 100)), np.hypot(.65, .8))):
            self.setUp()
            spatial, result = self.step(0, (self.person, forklift))
            self.assertAlmostEqual(result.evaluations[0].observed_normalized_distance, expected)

    def test_overlay_uses_evaluated_distance_not_an_alternate_calculation(self):
        spatial, result = self.step(0)
        result = replace(result, evaluations=(replace(result.evaluations[0], observed_normalized_distance=.123),))
        with patch.object(self.renderer, "_draw_label") as label:
            self.renderer.render_proximity(self.frame, spatial, result)
        self.assertTrue(any("0.123 norm" in call.args[1] for call in label.call_args_list))

    def test_mismatched_frame_is_rejected(self):
        spatial, result = self.step(0)
        with self.assertRaises(ValueError):
            self.renderer.render_proximity(self.frame, spatial, replace(result, frame_index=1))
        with self.assertRaises(ValueError):
            self.renderer.render_proximity(self.frame, spatial, replace(result,
                evaluations=(replace(result.evaluations[0], frame_index=1),)))

    def test_fps_independent_explicit_time_and_flapping_do_not_add_grace(self):
        self.step(0, timestamp=0.)
        self.step(1, (self.person, track("forklift", 1, 95, 95)), timestamp=.9)
        _, reentry = self.step(2, timestamp=1.)
        self.assertEqual(reentry.evaluations[0].observed_duration_s, 0.)
        self.assertEqual(reentry.candidates, ())
        _, emitted = self.step(3, timestamp=2.)
        self.assertEqual(len(emitted.candidates), 1)
        self.assertEqual(emitted.candidates[0].started_frame_index, 2)


if __name__ == "__main__":
    unittest.main()
