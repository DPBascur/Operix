"""El preview es independiente de la secuencia completa de análisis."""
import importlib.util
from pathlib import Path
import sys
import json
import tempfile
import unittest
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

    def test_operational_cli_defaults_to_single_frame_batch(self):
        arguments = ["worker", "--session-dir", "fixture", "--video", "fixture.mp4",
                     "--config", "fixture.json", "--person-weights", "person.pt",
                     "--person-sha256", "a" * 64, "--forklift-weights", "forklift.pt",
                     "--forklift-sha256", "b" * 64]
        with patch.object(sys, "argv", arguments), patch.object(self.worker, "process") as process:
            self.assertEqual(self.worker.main(), 0)
        self.assertEqual(process.call_args.args[0].batch_size, 1)

    def test_wrong_operational_person_hash_rejects_before_loading_models(self):
        with tempfile.TemporaryDirectory() as directory:
            weights = Path(directory) / "person.pt"
            weights.write_bytes(b"not-an-approved-checkpoint")
            arguments = SimpleNamespace(person_weights=weights,
                person_sha256="d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95")
            scripts = str(Path(__file__).resolve().parents[1] / "scripts")
            with patch.object(sys, "path", [scripts, *sys.path]), patch.object(self.worker, "YoloDetector") as detector:
                with self.assertRaisesRegex(ValueError, "SHA-256 distinto"):
                    self.worker.process(arguments)
            detector.assert_not_called()

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

    def test_cleanup_releases_both_resources_normally(self):
        frames, writer = Mock(), Mock()
        self.assertIsNone(self.worker._release_analysis_resources(frames, writer))
        frames.close.assert_called_once_with()
        writer.release.assert_called_once_with()

    def test_writer_is_released_when_frame_close_fails(self):
        failure = RuntimeError("frame close failed")
        frames, writer = Mock(), Mock()
        frames.close.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            self.worker._release_analysis_resources(frames, writer)
        self.assertIs(caught.exception, failure)
        writer.release.assert_called_once_with()

    def test_both_cleanup_errors_are_preserved(self):
        frames, writer = Mock(), Mock()
        first, second = RuntimeError("frames"), RuntimeError("writer")
        frames.close.side_effect, writer.release.side_effect = first, second
        with self.assertRaises(ExceptionGroup) as caught:
            self.worker._release_analysis_resources(frames, writer)
        self.assertEqual(caught.exception.exceptions, (first, second))

    def test_original_analysis_error_survives_successful_cleanup(self):
        frames, writer = Mock(), Mock()
        original = ValueError("analysis")
        with self.assertRaises(ValueError) as caught:
            try:
                raise original
            finally:
                self.worker._release_analysis_resources(frames, writer)
        self.assertIs(caught.exception, original)
        writer.release.assert_called_once_with()

    def test_analysis_and_both_cleanup_errors_are_preserved(self):
        frames, writer = Mock(), Mock()
        original, first, second = ValueError("analysis"), RuntimeError("frames"), RuntimeError("writer")
        frames.close.side_effect, writer.release.side_effect = first, second
        with self.assertRaises(ExceptionGroup) as caught:
            try:
                raise original
            finally:
                self.worker._release_analysis_resources(frames, writer)
        self.assertEqual(caught.exception.exceptions, (original, first, second))

    def test_worker_reports_failures_without_exposing_sensitive_detail(self):
        for failure in (FileNotFoundError("private-path"), ValueError("corrupt video"),
                        RuntimeError("CUDA failure"), MemoryError("VRAM exhausted"),
                        PermissionError("private-path")):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                argv = ["stream_dual_perception.py", "--session-dir", str(root), "--video", "missing.mp4",
                        "--config", "config.json", "--person-weights", "person.pt", "--person-sha256", "0",
                        "--forklift-weights", "forklift.pt", "--forklift-sha256", "0"]
                with patch.object(sys, "argv", argv), patch.object(self.worker, "process", side_effect=failure):
                    self.assertEqual(self.worker.main(), 1)
                status = json.loads((root / "status.json").read_text(encoding="utf8"))
                self.assertEqual(status["state"], "error")
                self.assertNotIn("private-path", status["detail"])
                self.assertTrue((root / "error.log").is_file())

    def test_truncated_worker_preserves_observed_progress_without_success(self):
        from operix_engine.video_processor import VideoContractError
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.worker._status(root, state="processing", frame=2, total=100, percent=2,
                                persistence={"state": "saved", "candidates": 1, "saved": 1, "failed": 0})
            argv = ["worker", "--session-dir", str(root), "--video", "missing.mp4",
                    "--config", "config.json", "--person-weights", "person.pt", "--person-sha256", "0",
                    "--forklift-weights", "forklift.pt", "--forklift-sha256", "0"]
            with patch.object(sys, "argv", argv), patch.object(self.worker, "process", side_effect=
                    VideoContractError("TRUNCATED_INPUT", "private-path")):
                self.assertEqual(self.worker.main(), 1)
            status = json.loads((root / "status.json").read_text(encoding="utf-8"))
            self.assertEqual((status["state"], status["termination_reason"]), ("error", "TRUNCATED_INPUT"))
            self.assertEqual((status["frame"], status["total"], status["percent"]), (2, 100, 2))
            self.assertEqual(status["persistence"]["saved"], 1)
            self.assertNotIn("private-path", json.dumps(status))

    def test_invalid_video_is_rejected_before_loading_models(self):
        from operix_engine.video_processor import VideoContractError
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(session_dir=Path(directory), video=Path("synthetic.mp4"),
                person_weights=Path("person.pt"), person_sha256="0" * 64,
                forklift_weights=Path("forklift.pt"), forklift_sha256="0" * 64)
            with patch.dict(sys.modules, {"run_dual_perception": SimpleNamespace(checked_file=Mock(), model_identity=Mock())}), \
                    patch.object(self.worker, "inspect_recorded_video", side_effect=
                        VideoContractError("UNSUPPORTED_VFR", "Cadencia irregular")), \
                    patch.object(self.worker, "YoloDetector") as detector:
                with self.assertRaises(VideoContractError):
                    self.worker.process(args)
            detector.assert_not_called()
