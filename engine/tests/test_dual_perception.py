# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas sin GPU de los dos canales de percepción experimental."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import cv2
import numpy as np

from operix_engine.detection import BoundingBox, Detection
from operix_engine.dual_perception import ClassPerceptionChannel, DualPerception
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track
from operix_engine.visualization import OpenCvRenderer, TrajectoryAccumulator


PERSON = Detection(0, "person", 0.9, BoundingBox(10, 10, 30, 40))
FORKLIFT_FROM_PERSON_MODEL = Detection(1, "forklift", 0.8, BoundingBox(50, 10, 90, 50))
FORKLIFT = Detection(0, "forklift", 0.95, BoundingBox(50, 10, 90, 50))


class FakeDetector:
    def __init__(self, names, detections):
        self.class_names = names
        self.detections = detections
        self.calls = 0

    def detect(self, _frame):
        self.calls += 1
        return self.detections


class FakeTracker:
    def __init__(self):
        self.calls = []
        self.reset_count = 0
        self.raw_id = 1

    def update(self, detections):
        self.calls.append(detections)
        return tuple(Track(self.raw_id, d.class_id, d.class_name, d.confidence, d.bounding_box) for d in detections)

    def reset(self):
        self.reset_count += 1


class DualPerceptionTest(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((100, 120, 3), dtype=np.uint8)
        self.person_model = FakeDetector({0: "person", 1: "forklift"}, (PERSON, FORKLIFT_FROM_PERSON_MODEL))
        self.forklift_model = FakeDetector({0: "forklift"}, (FORKLIFT,))
        self.person_tracker = FakeTracker()
        self.forklift_tracker = FakeTracker()
        self.dual = DualPerception(
            person=ClassPerceptionChannel("person", self.person_model, self.person_tracker),
            forklift=ClassPerceptionChannel("forklift", self.forklift_model, self.forklift_tracker),
        )

    def test_filters_person_models_forklift_and_keeps_independent_ids(self):
        result, timing = self.dual.process(self.frame)
        self.assertEqual(result.person_detections, (PERSON,))
        self.assertEqual(result.forklift_detections, (FORKLIFT,))
        self.assertEqual(self.person_tracker.calls, [(PERSON,)])
        self.assertEqual(self.forklift_tracker.calls, [(FORKLIFT,)])
        self.assertEqual(result.track_identities, (("person", 1), ("forklift", 1)))
        self.assertGreaterEqual(timing.person_inference_s, 0)
        self.assertEqual((self.person_model.calls, self.forklift_model.calls), (1, 1))

    def test_both_trackers_advance_when_their_class_is_absent(self):
        self.person_model.detections = (FORKLIFT_FROM_PERSON_MODEL,)
        self.forklift_model.detections = ()
        result, _ = self.dual.process(self.frame)
        self.assertEqual(result.track_identities, ())
        self.assertEqual(self.person_tracker.calls, [()])
        self.assertEqual(self.forklift_tracker.calls, [()])

    def test_backend_global_ids_are_remapped_to_class_local_ids(self):
        self.person_tracker.raw_id = 7
        self.forklift_tracker.raw_id = 18
        result, _ = self.dual.process(self.frame)
        self.assertEqual(result.track_identities, (("person", 1), ("forklift", 1)))
        self.person_tracker.raw_id = 25
        next_frame, _ = self.dual.process(self.frame)
        self.assertEqual(next_frame.track_identities, (("person", 2), ("forklift", 1)))
        self.dual.reset()
        fresh, _ = self.dual.process(self.frame)
        self.assertEqual(fresh.track_identities, (("person", 1), ("forklift", 1)))

    def test_rejects_shared_tracker(self):
        with self.assertRaisesRegex(ValueError, "trackers independientes"):
            DualPerception(
                person=ClassPerceptionChannel("person", self.person_model, self.person_tracker),
                forklift=ClassPerceptionChannel("forklift", self.forklift_model, self.person_tracker),
            )

    def test_one_detector_can_be_disabled_and_reset_is_separate(self):
        self.dual.reset()
        self.assertEqual((self.person_tracker.reset_count, self.forklift_tracker.reset_count), (1, 1))
        only_person = DualPerception(person=self.dual.person, forklift=None)
        result, timing = only_person.process(self.frame)
        self.assertEqual(result.forklift_detections, ())
        self.assertEqual(timing.forklift_inference_s, 0)
        self.assertEqual(self.forklift_model.calls, 0)

    def test_inference_synchronizes_each_active_model(self):
        calls = []
        self.dual.process(self.frame, synchronize=lambda: calls.append("sync"))
        self.assertEqual(calls, ["sync"] * 4)

    def test_invalid_class_is_not_accepted_by_tracker(self):
        with self.assertRaises(ValueError):
            self.dual.person.track((FORKLIFT_FROM_PERSON_MODEL,))

    def test_forklift_never_reaches_existing_person_rule(self):
        zone = Zone("all", "Zona", ((0, 0), (1, 0), (1, 1), (0, 1)))
        rule = RuleConfig("dwell", 1, True, {
            "kind": "zone_dwell", "class_name": "person", "zone_id": "all", "min_duration_s": 0.0,
        })
        config = OperationalConfig(1, "view", (zone,), (rule,))
        analyzer = SpatiotemporalAnalyzer(width=120, height=100, fps=30, zones=config.zones)
        result, _ = self.dual.process(self.frame)
        evaluated = RuleEngine(config).evaluate(analyzer.update(0, result.person_tracks))
        self.assertEqual(len(evaluated.candidates), 1)
        self.assertEqual(evaluated.candidates[0].class_name, "person")
        self.assertEqual(evaluated.candidates[0].track_id, 1)

    def test_visualization_namespaces_labels_and_trajectories(self):
        result, _ = self.dual.process(self.frame)
        renderer = OpenCvRenderer()
        person_history = TrajectoryAccumulator().update(0, result.person_tracks)
        forklift_history = TrajectoryAccumulator().update(0, result.forklift_tracks)
        with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as put_text:
            image = renderer.render_tracks(self.frame, result.person_tracks, person_history)
            image = renderer.render_tracks(image, result.forklift_tracks, forklift_history)
        labels = [call.args[1] for call in put_text.call_args_list]
        self.assertIn("Person P-1 0.90", labels)
        self.assertIn("Forklift F-1 0.95", labels)
        self.assertGreater(np.count_nonzero(image), 0)


if __name__ == "__main__":
    unittest.main()
