"""El preview es independiente de la secuencia completa de análisis."""
import importlib.util
from pathlib import Path
import sys
import unittest


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
        self.assertTrue(due(0, 300, 0.0, None, 10.0))
        self.assertTrue(due(299, 300, 1.001, 1.0, 10.0))

    def test_preview_throttle_never_drops_analysis_indices(self):
        processed, previews = [], []
        previous = None
        for index in range(300):
            processed.append(index)
            now = index / 100
            if self.worker._preview_due(index, 300, now, previous, 10.0):
                previews.append(index)
                previous = now
        self.assertEqual(processed, list(range(300)))
        self.assertLess(len(previews), 40)
        self.assertEqual((previews[0], previews[-1]), (0, 299))

    def test_invalid_preview_rate_is_rejected(self):
        for rate in (0, -1, float("nan"), float("inf")):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                self.worker._preview_due(0, 300, 0.0, None, rate)

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
