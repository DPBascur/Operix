import unittest

import cv2
import numpy as np

from operix_engine.detection import BoundingBox
from operix_engine.framing import FramingGuard, REFERENCE
from operix_engine.calibration import calibration_snapshot
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

    def test_versioned_reference_preserves_legacy_snapshot(self):
        legacy = calibration()
        monitored = calibration_snapshot({**legacy, "framing_reference": REFERENCE})
        self.assertEqual(legacy, calibration_snapshot(legacy))
        self.assertEqual(monitored, calibration_snapshot(monitored))
        self.assertNotEqual(legacy["sha256"], monitored["sha256"])
        with self.assertRaisesRegex(ValueError, "encuadre"):
            calibration_snapshot({**legacy, "framing_reference": "unknown"})
