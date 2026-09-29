# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prueba optativa de inferencia real; requiere recursos locales explícitos."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from operix_engine.detection import Detection
from operix_engine.video_processor import RecordedVideoSource
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


WEIGHTS = os.environ.get("OPERIX_YOLO11_WEIGHTS")
VIDEO = os.environ.get("OPERIX_OP18_VIDEO")


@unittest.skipUnless(WEIGHTS and VIDEO, "requiere pesos y muestra OP-18 explícitos")
class YoloDetectorIntegrationTest(unittest.TestCase):
    def test_detects_one_real_frame_without_leaking_backend_types(self) -> None:
        detector = YoloDetector(YoloDetectorConfig(Path(WEIGHTS), device="cuda"))
        with RecordedVideoSource(Path(VIDEO)) as source:
            _, frame = next(source.frames())

        detections = detector.detect(frame)
        self.assertIsInstance(detections, tuple)
        self.assertTrue(all(isinstance(item, Detection) for item in detections))


if __name__ == "__main__":
    unittest.main()
