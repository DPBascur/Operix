import unittest
from unittest.mock import patch

import cv2
import numpy as np

from operix_engine.detection import BoundingBox
from operix_engine.framing import FramingGuard, REFERENCE, RecordedFraming
from operix_engine.calibration import calibration_snapshot
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track
from operix_engine.visualization import OpenCvRenderer
from test_calibration import calibration


class FramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(407)
        gray = np.full((360, 640), 48, np.uint8)
        for _ in range(390):
            x, y = rng.integers([12, 12], [628, 348])
            cv2.rectangle(gray, (x, y), (x + 7, y + 9), int(rng.integers(85, 250)), -1)
        cls.reference = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    def transformed(self, dx=0, dy=0, degrees=0):
        matrix = cv2.getRotationMatrix2D((320, 180), degrees, 1)
        matrix[:, 2] += (dx, dy)
        return cv2.warpAffine(self.reference, matrix, (640, 360))

    def evaluate(self, frame, boxes=()):
        guard = FramingGuard()
        self.assertEqual(guard.update(self.reference, 0, 0), "VALID")
        states = [guard.update(frame, i, i / 4, boxes) for i in range(1, 5)]
        return states, guard

    def test_labeled_background_scenarios(self):
        foreground = self.reference.copy()
        cv2.rectangle(foreground, (225, 100), (355, 320), (180, 40, 130), -1)
        partial = self.reference.copy()
        partial[:, :210] = 50
        cases = (
            ("fixed", self.reference, (), "VALID"),
            ("vibration", self.transformed(3, -2), (), "VALID"),
            ("lighting", cv2.convertScaleAbs(self.reference, alpha=.7, beta=35), (), "VALID"),
            ("person crossing", foreground, (BoundingBox(225, 100, 355, 320),), "VALID"),
            ("partial occlusion", partial, (BoundingBox(0, 0, 210, 360),), "VALID"),
            ("horizontal displacement", self.transformed(24), (), "INVALID"),
            ("orientation change", self.transformed(degrees=4), (), "INVALID"),
            ("full occlusion", np.zeros_like(self.reference), (), "UNAVAILABLE"),
        )
        for name, frame, boxes, expected in cases:
            with self.subTest(name=name):
                states, guard = self.evaluate(frame, boxes)
                self.assertEqual(states[-1], expected, guard.status())
                if expected == "INVALID":
                    self.assertEqual(states[:3], ["SUSPECT", "SUSPECT", "INVALID"])
                    self.assertEqual(guard.invalidated_frame, 3)

    def test_transient_displacement_recovers_and_invalid_is_latched(self):
        guard = FramingGuard()
        guard.update(self.reference, 0, 0)
        self.assertEqual(guard.update(self.transformed(24), 1, .25), "SUSPECT")
        self.assertEqual(guard.update(self.reference, 2, .5), "SUSPECT")
        self.assertEqual(guard.update(self.reference, 3, .75), "VALID")
        self.assertEqual(guard.first_suspended_frame, 1)
        _, invalid = self.evaluate(self.transformed(24))
        self.assertEqual(invalid.update(self.reference, 5, 1.25), "INVALID")
        recalibrated = FramingGuard()
        self.assertEqual(recalibrated.update(self.transformed(24), 0, 0), "VALID")

    def test_detected_foreground_crosses_the_scene_with_varying_light(self):
        guard = FramingGuard()
        guard.update(self.reference, 0, 0)
        for sample, left in enumerate(range(50, 480, 70), 1):
            image = cv2.convertScaleAbs(self.reference, alpha=.75 + .035 * sample, beta=18)
            person = BoundingBox(left, 120, left + 40, 260)
            forklift = BoundingBox(550 - left, 75, 650 - left, 170)
            cv2.rectangle(image, (left, 120), (left + 40, 260), (180, 80, 130), -1)
            cv2.rectangle(image, (550 - left, 75), (650 - left, 170), (40, 200, 20), -1)
            self.assertEqual(guard.update(image, sample, sample / 4, (person, forklift)), "VALID")

    def test_no_reference_without_distributed_static_features(self):
        guard = FramingGuard()
        self.assertEqual(guard.update(np.zeros_like(self.reference), 0, 0), "UNAVAILABLE")
        self.assertEqual(guard.update(self.reference, 1, .25), "UNAVAILABLE")
        self.assertEqual(guard.first_suspended_frame, 0)

    def test_camera_displacement_falls_back_and_breaks_metric_rule_continuity(self):
        snapshot = calibration_snapshot({**calibration(), "framing_reference": REFERENCE})
        zone = Zone("floor", "Floor", ((0, 0), (1, 0), (1, 1), (0, 1)))
        rule = RuleConfig("pair", 1, True, {
            "kind": "person_forklift_proximity", "zone_id": "floor",
            "distance_unit": "m", "max_distance": 3.0, "minimum_duration_seconds": .5,
        })
        config = OperationalConfig(1, "camera", (zone,), (rule,), snapshot)
        analyzer = SpatiotemporalAnalyzer(width=640, height=360, fps=4, zones=(zone,), calibration=snapshot)
        rules = RuleEngine(config)
        framing = RecordedFraming(snapshot)
        renderer = OpenCvRenderer()
        tracks = (Track(1, 0, "person", .9, BoundingBox(170, 120, 200, 180)),
                  Track(1, 0, "forklift", .9, BoundingBox(264, 120, 334, 180)))
        shifted = self.transformed(dx=24)
        emitted = []
        for i, frame in enumerate((self.reference, shifted, self.reference, self.reference,
                                   self.reference, self.reference, shifted, shifted, shifted)):
            allowed = framing.update(frame, i, i / 4, ())
            spatial = analyzer.update(i, tracks, image_only=not allowed)
            result = rules.evaluate(spatial) if allowed else None
            if result:
                emitted.extend(candidate.frame_index for candidate in result.candidates)
            with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as text:
                renderer.render_proximity(frame, spatial, result, metric_expected=True)
            visible = [call.args[1] for call in text.call_args_list]
            expected = "P1/F1  ~1,00 m" if allowed else "P1/F1  0,1 norm."
            self.assertIn(expected, visible)
            self.assertEqual(spatial.proximities[0].ground is not None, allowed)
            if not allowed:
                self.assertTrue(any("Encuadre sin validar" in label for label in visible))
                self.assertTrue(all(not obj.zones for obj in spatial.objects))
        self.assertEqual(framing.status()["state"], "INVALID")
        self.assertEqual(emitted, [5])

    def test_manual_invalidation_keeps_only_image_distances(self):
        snapshot = calibration_snapshot({**calibration(), "status": "invalid"})
        framing = RecordedFraming(snapshot)
        allowed = framing.update(self.reference, 0, 0., ())
        self.assertFalse(allowed)
        self.assertEqual(framing.status()["reason"], "operator_invalidated")
        tracks = (Track(1, 0, "person", .9, BoundingBox(170, 120, 200, 180)),
                  Track(1, 0, "forklift", .9, BoundingBox(264, 120, 334, 180)))
        analyzer = SpatiotemporalAnalyzer(width=640, height=360, fps=4, zones=(), calibration=snapshot)
        spatial = analyzer.update(0, tracks, image_only=True)
        with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as text:
            OpenCvRenderer().render_proximity(self.reference, spatial, None, metric_expected=True)
        self.assertIn("P1/F1  0,1 norm.", [call.args[1] for call in text.call_args_list])

    def test_versioned_reference_preserves_legacy_snapshot(self):
        legacy = calibration()
        monitored = calibration_snapshot({**legacy, "framing_reference": REFERENCE})
        self.assertEqual(legacy, calibration_snapshot(legacy))
        self.assertEqual(monitored, calibration_snapshot(monitored))
        self.assertNotEqual(legacy["sha256"], monitored["sha256"])
        with self.assertRaisesRegex(ValueError, "encuadre"):
            calibration_snapshot({**legacy, "framing_reference": "unknown"})
