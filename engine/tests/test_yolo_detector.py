"""Pruebas del adaptador YOLO sin pesos ni inferencias reales."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
