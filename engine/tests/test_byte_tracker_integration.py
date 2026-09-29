# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prueba optativa de YOLO11, filtro person y ByteTrack sobre OP-35."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from operix_engine.byte_tracker import ByteTracker
from operix_engine.tracking import Track
from operix_engine.video_processor import RecordedVideoSource
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


WEIGHTS = os.environ.get("OPERIX_YOLO11_WEIGHTS")
VIDEO = os.environ.get("OPERIX_OP35_VIDEO")


@unittest.skipUnless(WEIGHTS and VIDEO, "requiere pesos y muestra OP-35 explícitos")
class ByteTrackerIntegrationTest(unittest.TestCase):
    def test_tracks_person_detections_without_leaking_backend_types(self) -> None:
        detector = YoloDetector(
            YoloDetectorConfig(Path(WEIGHTS), confidence_threshold=0.10, device="cuda")
        )
        tracker = ByteTracker()
        observed_tracks = []

        with RecordedVideoSource(Path(VIDEO)) as source:
            for frame_index, frame in source.frames():
                detections = tuple(
                    item for item in detector.detect(frame) if item.class_name == "person"
                )
                observed_tracks.extend(tracker.update(detections))
                if frame_index >= 4:
                    break

        self.assertTrue(observed_tracks)
        self.assertTrue(all(isinstance(item, Track) for item in observed_tracks))
        self.assertTrue(all(item.class_name == "person" for item in observed_tracks))


if __name__ == "__main__":
    unittest.main()
