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
                patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as labels:
            annotated = self.renderer.render_proximity(self.frame, spatial, result)
        self.assertEqual(line.call_args.args[1:3], ((25, 20), (45, 60)))
        self.assertTrue(any(call.args[1] == "P1/F1  0,4472 norm." for call in labels.call_args_list))
        self.assertEqual(evaluation.parameters["max_distance"], .5)
        self.assertEqual(evaluation.parameters["minimum_duration_seconds"], 1.)
        self.assertEqual(evaluation.reason, "insufficient_duration")
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

    def test_no_pair_has_no_line(self):
        for tracks in ((), (self.person,)):
            self.setUp()
            spatial, result = self.step(0, tracks)
            with patch("operix_engine.visualization.cv2.line") as line:
                self.renderer.render_proximity(self.frame, spatial, result)
            line.assert_not_called()

    def test_dwell_only_profile_displays_observations_without_pair_events(self):
        spatial, _ = self.step(0, (self.person, self.forklift, track("person", 2, 40, 50)))
        dwell = RuleEngine(replace(self.config, rules=(
            RuleConfig("dwell", 1, True, {"kind": "zone_dwell", "zone_id": "floor",
                                         "class_name": "person", "min_duration_s": 1.}),)))
        result = dwell.evaluate(spatial)
        with patch("operix_engine.visualization.cv2.line", wraps=cv2.line) as lines, \
                patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as labels:
            self.renderer.render_proximity(self.frame, spatial, result)
        self.assertEqual(lines.call_count, 2)
        self.assertTrue(any(call.args[1] == "P1/F1  0,4472 norm." for call in labels.call_args_list))
        self.assertEqual(result.candidates, ())
        with patch("operix_engine.visualization.cv2.line") as lines, \
                patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as labels:
            self.renderer.render_proximity(self.frame, spatial, result, metric_expected=True)
        self.assertEqual(lines.call_count, 2)
        self.assertTrue(any("Fuera del plano" in call.args[1] for call in labels.call_args_list))

    def test_outside_threshold_displays_one_observation_without_an_event(self):
        spatial, result = self.step(0, (self.person, track("forklift", 1, 95, 95)))
        with patch("operix_engine.visualization.cv2.line", wraps=cv2.line) as line:
            self.renderer.render_proximity(self.frame, spatial, result)
        line.assert_called_once()
        self.assertEqual(result.evaluations[0].reason, "outside_distance")
        self.assertEqual(line.call_args.args[3], self.renderer._ZONE_NORMAL_COLOR)
        self.assertEqual(result.candidates, ())

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

    def test_coincident_lines_get_distinct_readable_labels(self):
        analyzer = SpatiotemporalAnalyzer(width=640, height=360, fps=30, zones=(self.zone,))
        tracks = tuple(track(name, number, x, 200)
                       for name, x in (("person", 200), ("forklift", 400)) for number in (1, 2))
        spatial = analyzer.update(0, tracks)
        result = self.rules.evaluate(spatial)
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as text, \
                patch.object(self.renderer, "_paint_tag", wraps=self.renderer._paint_tag) as rect:
            self.renderer.render_proximity(frame, spatial, result)
        badges = [(t.args[1], r.args[1][:2], r.args[1][2:])
                  for t, r in zip(text.call_args_list, rect.call_args_list, strict=True)
                  if t.args[1].endswith("0,2969 norm.")]
        self.assertEqual({label.split()[0] for label, _, _ in badges},
                         {"P1/F1", "P1/F2", "P2/F1", "P2/F2"})
        for i, (_, (left, top), (right, bottom)) in enumerate(badges):
            self.assertLessEqual(left, 300)
            self.assertGreaterEqual(right, 300)
            for _, (other_left, other_top), (other_right, other_bottom) in badges[i + 1:]:
                self.assertTrue(right < other_left or other_right < left
                                or bottom < other_top or other_bottom < top)

    def test_compact_tags_stay_inside_landscape_and_portrait_frames(self):
        for width, height in ((1280, 720), (1920, 1080), (2560, 1440), (3840, 2160), (1080, 1920)):
            with self.subTest(width=width, height=height):
                frame = np.full((height, width, 3), 160, dtype=np.uint8)
                tracks = (
                    track("person", 1, .42 * width, .46 * height),
                    track("person", 2, .42 * width, .54 * height),
                    track("forklift", 1, .56 * width, .46 * height),
                    track("forklift", 2, .56 * width, .54 * height),
                )
                boxes = tuple(item.bounding_box for item in tracks)
                analyzer = SpatiotemporalAnalyzer(width=width, height=height, fps=30, zones=(self.zone,))
                spatial = analyzer.update(0, tracks)
                occupied = []
                frame = self.renderer.render_zone(frame, self.zone, occupied=occupied, object_boxes=boxes)
                frame = self.renderer.render_tracks(frame, tracks, occupied=occupied)
                with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as text:
                    self.renderer.render_proximity(frame, spatial, RuleEngine(self.config).evaluate(spatial), occupied=occupied)
                labels = [call.args[1] for call in text.call_args_list]
                self.assertEqual(len([label for label in labels if label.endswith("norm.")]), 4)
                self.assertEqual(len(occupied), 10)  # Zona, cuatro tracks, cuatro pares y HUD.
                for index, rect in enumerate(occupied):
                    left, top, right, bottom = rect
                    self.assertTrue(0 <= left < right <= width and 0 <= top < bottom <= height)
                    self.assertLess(bottom - top, min(width, height) * .04)
                    for other in occupied[index + 1:] + self.renderer._object_rects(boxes):
                        self.assertFalse(self.renderer._overlaps(rect, other))

    def test_tag_fill_is_translucent_and_rounded(self):
        frame = np.full((60, 100, 3), 180, dtype=np.uint8)
        self.renderer._paint_tag(frame, (10, 10, 90, 50), alpha=.78)
        self.assertTrue(np.all(frame[10, 10] == 180))
        self.assertTrue(np.all(frame[9, 50] == 180))
        self.assertTrue(np.all((frame[30, 50] > 25) & (frame[30, 50] < 180)))

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
        with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as label:
            self.renderer.render_proximity(self.frame, spatial, result)
        self.assertTrue(any(call.args[1] == "P1/F1  0,123 norm." for call in label.call_args_list))

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
