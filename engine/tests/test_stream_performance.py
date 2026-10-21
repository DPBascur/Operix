"""El preview es independiente de la secuencia completa de análisis."""
import importlib.util
from pathlib import Path
import sys
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch


class PreviewScheduleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/stream_dual_perception.py"
        spec = importlib.util.spec_from_file_location("stream_performance_test", path)
        cls.worker = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.worker
        spec.loader.exec_module(cls.worker)

    def test_first_and_final_preview_are_always_published(self):
        due = self.worker._preview_due
        self.assertTrue(due(0, 300, 30.0, None, 10.0))
        self.assertTrue(due(299, 300, 30.0, 297, 10.0))

    def test_preview_throttle_never_drops_analysis_indices(self):
        processed, previews = [], []
        previous = None
        for index in range(300):
            processed.append(index)
            if self.worker._preview_due(index, 300, 30.0, previous, 10.0):
                previews.append(index)
                previous = index
        self.assertEqual(processed, list(range(300)))
        self.assertEqual(previews, list(range(0, 300, 3)) + [299])
        self.assertEqual((previews[0], previews[-1]), (0, 299))

    def test_invalid_preview_rate_is_rejected(self):
        for rate in (0, -1, float("nan"), float("inf")):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                self.worker._preview_due(0, 300, 30.0, None, rate)

    def test_prefetch_preserves_partial_tail_and_frame_order(self):
        class Perception:
            sizes = []
            def process_batch(self, frames, **kwargs):
                self.sizes.append(len(frames))
                return tuple((frame, "timing") for frame in frames)
        perception = Perception()
        results = list(self.worker._analyzed_frames(iter(enumerate(range(9))), perception, 4, None))
        self.assertEqual([r[0] for r in results], list(range(9)))
        self.assertEqual([r[2] for r in results], list(range(9)))
        self.assertEqual(perception.sizes, [4, 4, 1])

    def test_prefetch_propagates_decode_errors_without_hiding_them(self):
        def frames():
            raise ValueError("decode failure")
            yield
        with self.assertRaisesRegex(ValueError, "decode failure"):
            list(self.worker._analyzed_frames(frames(), None, 4, None))

    def test_prefetch_is_bounded_when_consumer_closes_early(self):
        consumed = []
        def frames():
            for index in range(100):
                consumed.append(index)
                yield index, index
        class Perception:
            def process_batch(self, frames, **kwargs):
                return tuple((frame, None) for frame in frames)
        iterator = self.worker._analyzed_frames(frames(), Perception(), 4, None)
        self.assertEqual(next(iterator)[0], 0)
        iterator.close()
        self.assertLessEqual(len(consumed), 8)

    def test_worker_reports_runtime_failures_without_sensitive_detail(self):
        worker = self.worker
        for failure in (FileNotFoundError("sensitive-path"), ValueError("corrupt video"),
                        RuntimeError("CUDA failure"), MemoryError("VRAM exhausted"),
                        RuntimeError("YOLO exception"), PermissionError("sensitive-path")):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                argv = ["stream_dual_perception.py", "--session-dir", str(root), "--video", "missing.mp4",
                        "--config", "config.json", "--person-weights", "person.pt", "--person-sha256", "0",
                        "--forklift-weights", "forklift.pt", "--forklift-sha256", "0"]
                with patch.object(sys, "argv", argv), patch.object(worker, "process", side_effect=failure):
                    self.assertEqual(worker.main(), 1)
                import json
                status = json.loads((root / "status.json").read_text(encoding="utf-8"))
                self.assertEqual(status["state"], "error")
                self.assertNotIn("sensitive-path", status["detail"])
                self.assertTrue((root / "error.log").is_file())

    def test_writer_is_released_even_when_prefetch_close_fails(self):
        worker = self.worker
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            weights = root / "fake.pt"
            weights.touch()
            config = SimpleNamespace(zones=(), rules=())
            metadata = SimpleNamespace(declared_fps=30, width=64, height=64, declared_frame_count=0)
            source = Mock()
            source.__enter__ = Mock(return_value=source)
            source.__exit__ = Mock(return_value=False)
            source.metadata.return_value = metadata
            class Frames:
                def __iter__(self):
                    return self
                def __next__(self):
                    raise StopIteration
                def close(self):
                    raise RuntimeError("prefetch close failed")
            frames = Frames()
            writer = Mock()
            detector = Mock(class_names={0: "person", 1: "forklift"})
            args = SimpleNamespace(person_weights=weights, forklift_weights=weights, person_sha256="0",
                                   forklift_sha256="0", config=root / "config.json", polygon=None,
                                   video=root / "video.mp4", session_dir=root)
            # checked_file is imported inside process from its script sibling.
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
            try:
                with patch("run_dual_perception.checked_file"), patch.object(worker.torch.cuda, "is_available", return_value=True), \
                     patch.object(worker, "load_operational_config", return_value=config), \
                     patch.object(worker, "RuleEngine"), \
                     patch.object(worker, "RecordedVideoSource", return_value=source), \
                     patch.object(worker.cv2, "VideoWriter", return_value=writer), \
                     patch.object(worker, "_analyzed_frames", return_value=frames):
                    with self.assertRaisesRegex(RuntimeError, "prefetch close failed"):
                        worker.process(args, detector_factory=lambda _: detector)
                writer.release.assert_called_once()
            finally:
                sys.path.pop(0)
