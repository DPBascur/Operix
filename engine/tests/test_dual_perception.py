# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas sin GPU de los dos canales de percepción experimental."""

from __future__ import annotations

import unittest
import importlib.util
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
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
        evaluated = RuleEngine(config).evaluate(
            analyzer.update(0, result.person_tracks + result.forklift_tracks)
        )
        self.assertEqual(len(evaluated.candidates), 1)
        self.assertEqual(evaluated.candidates[0].class_name, "person")
        self.assertEqual(evaluated.candidates[0].track_id, 1)

    def test_multiclass_person_rule_matches_person_only_across_loss_and_recovery(self):
        zone = Zone("all", "Zona", ((0, 0), (1, 0), (1, 1), (0, 1)))
        rule = RuleConfig("demo_zone_dwell", 1, True, {
            "kind": "zone_dwell", "class_name": "person", "zone_id": "all", "min_duration_s": 1.0,
        })
        config = OperationalConfig(1, "view", (zone,), (rule,))
        mixed_analyzer = SpatiotemporalAnalyzer(width=120, height=100, fps=2, zones=config.zones)
        person_analyzer = SpatiotemporalAnalyzer(width=120, height=100, fps=2, zones=config.zones)
        mixed_rules, person_rules = RuleEngine(config), RuleEngine(config)
        emitted = []
        for frame in range(8):
            self.person_model.detections = () if frame == 4 else (PERSON,)
            observed, _ = self.dual.process(self.frame)
            mixed = mixed_rules.evaluate(mixed_analyzer.update(
                frame, observed.person_tracks + observed.forklift_tracks,
            ))
            baseline = person_rules.evaluate(person_analyzer.update(frame, observed.person_tracks))
            self.assertEqual(mixed.candidates, baseline.candidates)
            self.assertTrue(all(not item.satisfied and item.reason == "class_mismatch"
                                for item in mixed.evaluations if item.class_name == "forklift"))
            emitted.extend(mixed.candidates)
        self.assertEqual([item.frame_index for item in emitted], [2, 7])
        self.assertTrue(all(item.class_name == "person" for item in emitted))

    def test_forklift_only_spatial_state_does_not_emit_person_candidates(self):
        zone = Zone("all", "Zona", ((0, 0), (1, 0), (1, 1), (0, 1)))
        rule = RuleConfig("demo_zone_dwell", 1, True, {
            "kind": "zone_dwell", "class_name": "person", "zone_id": "all", "min_duration_s": 0.0,
        })
        config = OperationalConfig(1, "view", (zone,), (rule,))
        analyzer = SpatiotemporalAnalyzer(width=120, height=100, fps=30, zones=config.zones)
        rules = RuleEngine(config)
        self.person_model.detections = ()
        for frame in range(3):
            observed, _ = self.dual.process(self.frame)
            spatial = analyzer.update(frame, observed.person_tracks + observed.forklift_tracks)
            self.assertEqual(len(spatial.objects), 1)
            self.assertEqual(spatial.objects[0].class_name, "forklift")
            self.assertEqual(rules.evaluate(spatial).candidates, ())

    def test_both_orchestrators_deliver_both_classes_to_spatial_analysis(self):
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        zone = Zone("all", "Zona", ((0, 0), (1, 0), (1, 1), (0, 1)))
        rule = RuleConfig("demo_zone_dwell", 1, True, {
            "kind": "zone_dwell", "class_name": "person", "zone_id": "all", "min_duration_s": 0.0,
        })
        config = OperationalConfig(1, "view", (zone,), (rule,))

        def load_script(name):
            spec = importlib.util.spec_from_file_location(name, scripts / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        diagnostic = load_script("run_dual_perception")
        streaming = load_script("stream_dual_perception")

        def detector(settings):
            model = self.person_model if settings.weights_path.name == "person.pt" else self.forklift_model
            model.model_device = "cuda:0"
            return model

        for module in (diagnostic, streaming):
            with self.subTest(script=module.__name__), tempfile.TemporaryDirectory() as directory:
                session_dir = Path(directory) / "session"
                session_dir.mkdir()
                person_weights = Path(directory) / "person.pt"
                forklift_weights = Path(directory) / "forklift.pt"
                person_weights.touch()
                forklift_weights.touch()
                # Solo un archivo temporal para probar la finalización; no contiene video real.
                (session_dir / "annotated.partial.mp4").touch()
                args = SimpleNamespace(
                    video=Path("synthetic.mp4"), config=Path("synthetic.json"),
                    person_weights=person_weights, forklift_weights=forklift_weights,
                    expected_video_sha256="0" * 64, expected_person_sha256="0" * 64,
                    expected_forklift_sha256="0" * 64, person_sha256="0" * 64,
                    forklift_sha256="0" * 64, output_dir=Path(directory) / "diagnostic",
                    session_dir=session_dir, polygon=None, disable_person=False,
                    disable_forklift=False, person_conf=0.10, person_iou=0.70,
                    forklift_conf=0.45, forklift_iou=0.55, device="cpu",
                    capture_frames=(), preview_width=0,
                )
                source = MagicMock()
                source.__enter__.return_value = source
                source.metadata.return_value = SimpleNamespace(
                    width=120, height=100, declared_fps=30.0, declared_frame_count=2,
                )
                source.frames.return_value = iter(((0, self.frame), (1, self.frame)))
                writer = MagicMock()
                writer.isOpened.return_value = True
                writer.getBackendName.return_value = "synthetic"
                capture = MagicMock()
                capture.get.side_effect = lambda key: {
                    cv2.CAP_PROP_FRAME_COUNT: 2, cv2.CAP_PROP_FPS: 30,
                    cv2.CAP_PROP_FRAME_WIDTH: 120, cv2.CAP_PROP_FRAME_HEIGHT: 100,
                }[key]
                capture.read.side_effect = ((True, self.frame), (True, self.frame), (False, None))
                analyzer = SpatiotemporalAnalyzer(width=120, height=100, fps=30, zones=(zone,))
                rules = RuleEngine(config)
                with (
                    patch.dict(sys.modules, {"run_dual_perception": diagnostic}),
                    patch.object(diagnostic, "checked_file", return_value="0" * 64),
                    patch.object(module, "YoloDetector", side_effect=detector),
                    patch.object(module, "ByteTracker", side_effect=lambda _: FakeTracker()),
                    patch.object(module, "RecordedVideoSource", return_value=source),
                    patch.object(module, "load_operational_config", return_value=config),
                    patch.object(module, "SpatiotemporalAnalyzer", return_value=analyzer),
                    patch.object(module, "RuleEngine", return_value=rules),
                    patch.object(module.cv2, "VideoWriter", return_value=writer),
                    patch.object(module.cv2, "VideoCapture", return_value=capture),
                    patch.object(module.torch.cuda, "is_available", return_value=True),
                    patch.object(module.torch.cuda, "synchronize"),
                    patch.object(rules, "evaluate", wraps=rules.evaluate) as evaluate,
                ):
                    if module is diagnostic:
                        summary = module.run(args)
                        self.assertEqual(summary["candidate_count"], 1)
                    else:
                        module.process(args)
                    self.assertEqual(evaluate.call_count, 2)
                    for call in evaluate.call_args_list:
                        objects = call.args[0].objects
                        self.assertEqual({obj.class_name for obj in objects}, {"person", "forklift"})
                        self.assertEqual({obj.track_id for obj in objects}, {1})

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
