"""Pruebas de los tipos propios de detección de Operix."""

import unittest
from dataclasses import FrozenInstanceError

from operix_engine.detection import BoundingBox, Detection


class DetectionTypesTest(unittest.TestCase):
    def test_detection_is_immutable_and_preserves_xyxy_floats(self) -> None:
        box = BoundingBox(1.5, 2.5, 10.5, 20.5)
        detection = Detection(0, "person", 0.875, box)

        self.assertEqual(detection.bounding_box, box)
        self.assertEqual((box.x_min, box.y_min, box.x_max, box.y_max), (1.5, 2.5, 10.5, 20.5))
        with self.assertRaises(FrozenInstanceError):
            detection.confidence = 0.5  # type: ignore[misc]

    def test_invalid_box_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ancho y alto"):
            BoundingBox(10.0, 2.0, 10.0, 20.0)

    def test_invalid_detection_is_rejected(self) -> None:
        box = BoundingBox(1.0, 2.0, 10.0, 20.0)
        with self.assertRaisesRegex(ValueError, "entre 0 y 1"):
            Detection(0, "person", 1.1, box)


if __name__ == "__main__":
    unittest.main()
