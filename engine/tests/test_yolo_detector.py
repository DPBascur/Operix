# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas del adaptador YOLO sin pesos ni inferencias reales."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from operix_engine.detection import Detection
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


class FakeBoxes:
    def __init__(self, xyxy, confidence, class_ids) -> None:
        self.xyxy = np.asarray(xyxy, dtype=np.float32).reshape((-1, 4))
        self.conf = np.asarray(confidence, dtype=np.float32)
        self.cls = np.asarray(class_ids, dtype=np.float32)

    def __len__(self) -> int:
        return len(self.conf)


class FakeResult:
    def __init__(self, boxes: FakeBoxes | None) -> None:
        self.boxes = boxes


class FakeModel:
    names = {0: "person"}
    device = "cpu"

    def __init__(self, result: FakeResult) -> None:
        self.result = result
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        return [self.result]


class YoloDetectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.weights = Path(self.directory.name) / "weights.pt"
        self.weights.write_bytes(b"fake weights")
        self.frame = np.zeros((48, 64, 3), dtype=np.uint8)

    def make_detector(self, result: FakeResult):
        model = FakeModel(result)
        factory_calls = []

        def factory(*args, **kwargs):
            factory_calls.append((args, kwargs))
            return model

        config = YoloDetectorConfig(
            self.weights,
            confidence_threshold=0.40,
            device="cpu",
            image_size=320,
            iou_threshold=0.50,
        )
        return YoloDetector(config, model_factory=factory), model, factory_calls

    def test_converts_backend_result_to_operix_detections(self) -> None:
        result = FakeResult(FakeBoxes([[1.25, 2.5, 30.75, 40.5]], [0.875], [0]))
        detector, _, _ = self.make_detector(result)

        detections = detector.detect(self.frame)

        self.assertEqual(len(detections), 1)
        self.assertIsInstance(detections[0], Detection)
        self.assertEqual(detections[0].class_id, 0)
        self.assertEqual(detections[0].class_name, "person")
        self.assertAlmostEqual(detections[0].confidence, 0.875)
        self.assertEqual(
            detections[0].bounding_box,
            detections[0].bounding_box.__class__(1.25, 2.5, 30.75, 40.5),
        )

    def test_empty_result_returns_empty_tuple(self) -> None:
        detector, _, _ = self.make_detector(FakeResult(FakeBoxes([], [], [])))
        self.assertEqual(detector.detect(self.frame), ())

    def test_passes_only_approved_parameters_without_class_filter(self) -> None:
        detector, model, factory_calls = self.make_detector(FakeResult(None))
        detector.detect(self.frame)

        self.assertEqual(factory_calls, [((str(self.weights),), {"task": "detect"})])
        call = model.calls[0]
        self.assertEqual(call["conf"], 0.40)
        self.assertEqual(call["device"], "cpu")
        self.assertEqual(call["imgsz"], 320)
        self.assertEqual(call["iou"], 0.50)
        self.assertNotIn("classes", call)
        self.assertFalse(call["save"])
        self.assertFalse(call["show"])

    def test_rejects_invalid_frames_before_calling_backend(self) -> None:
        detector, model, _ = self.make_detector(FakeResult(None))
        invalid_frames = [
            np.zeros((48, 64), dtype=np.uint8),
            np.zeros((48, 64, 3), dtype=np.float32),
        ]
        for frame in invalid_frames:
            with self.subTest(shape=frame.shape, dtype=frame.dtype):
                with self.assertRaises(ValueError):
                    detector.detect(frame)
        self.assertEqual(model.calls, [])

    def test_requires_existing_local_weights_without_calling_factory(self) -> None:
        missing = Path(self.directory.name) / "missing.pt"
        with self.assertRaisesRegex(ValueError, "No existe"):
            YoloDetectorConfig(missing)

    def test_reports_effective_predictor_device(self) -> None:
        detector, model, _ = self.make_detector(FakeResult(None))
        self.assertEqual(detector.model_device, "cpu")
        model.predictor = SimpleNamespace(model=SimpleNamespace(device="cuda:0"))
        self.assertEqual(detector.model_device, "cuda:0")

    def test_batch_preserves_result_order_and_detection_parameters(self) -> None:
        first = FakeResult(FakeBoxes([[1, 2, 30, 40]], [0.875], [0]))
        second = FakeResult(FakeBoxes([[3, 4, 32, 42]], [0.75], [0]))
        detector, model, _ = self.make_detector(first)
        calls = []
        def predict(**kwargs):
            calls.append(kwargs)
            return [first, second]
        model.predict = predict
        results = detector.detect_batch((self.frame, self.frame.copy()))
        self.assertEqual([items[0].bounding_box.x_min for items in results], [1, 3])
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0]["conf"], calls[0]["iou"], calls[0]["imgsz"]), (0.40, 0.50, 320))
        self.assertIs(calls[0]["source"][0], self.frame)

    def test_empty_batch_does_not_call_backend(self) -> None:
        detector, model, _ = self.make_detector(FakeResult(None))
        self.assertEqual(detector.detect_batch(()), ())
        self.assertEqual(model.calls, [])

    def test_batch_rejects_mixed_shapes_and_missing_results(self) -> None:
        detector, model, _ = self.make_detector(FakeResult(None))
        with self.assertRaises(ValueError):
            detector.detect_batch((self.frame, np.zeros((24, 32, 3), dtype=np.uint8)))
        self.assertEqual(model.calls, [])
        with self.assertRaises(RuntimeError):
            detector.detect_batch((self.frame, self.frame))


if __name__ == "__main__":
    unittest.main()
