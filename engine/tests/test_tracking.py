"""Pruebas de los tipos públicos de tracking."""

import unittest
from dataclasses import FrozenInstanceError

from operix_engine.detection import BoundingBox
from operix_engine.tracking import Track


class TrackTypesTest(unittest.TestCase):
    def test_track_is_immutable_and_reuses_bounding_box(self) -> None:
        box = BoundingBox(1.0, 2.0, 20.0, 30.0)
        track = Track(1, 0, "person", 0.9, box)

        self.assertEqual(track.bounding_box, box)
        with self.assertRaises(FrozenInstanceError):
            track.track_id = 2  # type: ignore[misc]

    def test_track_id_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "positivo"):
            Track(0, 0, "person", 0.9, BoundingBox(1.0, 2.0, 20.0, 30.0))

    def test_track_confidence_must_be_valid(self) -> None:
        with self.assertRaisesRegex(ValueError, "entre 0 y 1"):
            Track(1, 0, "person", 1.1, BoundingBox(1.0, 2.0, 20.0, 30.0))


if __name__ == "__main__":
    unittest.main()
