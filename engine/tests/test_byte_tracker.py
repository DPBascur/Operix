"""Pruebas sintéticas del adaptador ByteTrack sin video ni YOLO."""

from __future__ import annotations

import unittest

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.detection import BoundingBox, Detection
from operix_engine.tracking import Track


def detection(
    x: float,
    *,
    confidence: float = 0.9,
    class_id: int = 0,
    class_name: str = "person",
) -> Detection:
    return Detection(
        class_id,
        class_name,
        confidence,
        BoundingBox(x, 10.0, x + 20.0, 50.0),
    )


class ByteTrackerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = ByteTracker()

    def test_continuous_motion_keeps_id(self) -> None:
        first = self.tracker.update((detection(10.0),))
        second = self.tracker.update((detection(12.0),))
        self.assertEqual(first[0].track_id, second[0].track_id)

    def test_two_objects_keep_separate_ids(self) -> None:
        first = self.tracker.update((detection(10.0), detection(100.0)))
        second = self.tracker.update((detection(12.0), detection(102.0)))
        self.assertEqual([item.track_id for item in first], [item.track_id for item in second])
        self.assertEqual(len({item.track_id for item in second}), 2)

    def test_new_object_is_confirmed_with_a_new_id(self) -> None:
        existing = self.tracker.update((detection(10.0),))[0].track_id
        self.tracker.update((detection(12.0), detection(100.0)))
        tracks = self.tracker.update((detection(14.0), detection(102.0)))
        self.assertEqual(len(tracks), 2)
        self.assertIn(existing, {item.track_id for item in tracks})

    def test_short_loss_recovers_same_id(self) -> None:
        original = self.tracker.update((detection(10.0),))[0].track_id
        self.assertEqual(self.tracker.update(()), ())
        recovered = self.tracker.update((detection(12.0),))[0]
        self.assertEqual(recovered.track_id, original)

    def test_loss_beyond_buffer_creates_new_id(self) -> None:
        original = self.tracker.update((detection(10.0),))[0].track_id
        # El backend pasa el track a perdido en el primer frame vacío y lo elimina
        # cuando el tiempo perdido supera (no iguala) el buffer configurado.
        for _ in range(self.tracker.config.track_buffer + 2):
            self.tracker.update(())
        self.assertEqual(self.tracker.update((detection(12.0),)), ())
        replacement = self.tracker.update((detection(14.0),))[0]
        self.assertNotEqual(replacement.track_id, original)

    def test_low_confidence_detection_recovers_existing_track(self) -> None:
        original = self.tracker.update((detection(10.0),))[0].track_id
        recovered = self.tracker.update((detection(12.0, confidence=0.2),))[0]
        self.assertEqual(recovered.track_id, original)

    def test_isolated_low_confidence_detection_does_not_start_track(self) -> None:
        self.assertEqual(self.tracker.update((detection(10.0, confidence=0.2),)), ())

    def test_class_change_keeps_id_and_exposes_latest_class(self) -> None:
        original = self.tracker.update((detection(10.0),))[0]
        changed = self.tracker.update(
            (detection(12.0, class_id=7, class_name="truck"),)
        )[0]
        self.assertEqual(changed.track_id, original.track_id)
        self.assertEqual((changed.class_id, changed.class_name), (7, "truck"))

    def test_reset_starts_a_new_session(self) -> None:
        self.assertEqual(self.tracker.update((detection(10.0),))[0].track_id, 1)
        self.tracker.reset()
        self.assertEqual(self.tracker.update((detection(10.0),))[0].track_id, 1)

    def test_empty_input_returns_no_tracks(self) -> None:
        self.assertEqual(self.tracker.update(()), ())

    def test_public_output_does_not_expose_ultralytics_types(self) -> None:
        track = self.tracker.update((detection(10.0),))[0]
        self.assertIsInstance(track, Track)
        self.assertNotIn("ultralytics", type(track).__module__)

    def test_configuration_validates_threshold_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "no puede superar"):
            ByteTrackConfig(track_low_thresh=0.5, track_high_thresh=0.25)


if __name__ == "__main__":
    unittest.main()
