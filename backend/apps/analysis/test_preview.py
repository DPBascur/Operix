"""Pruebas deterministas del reloj visual; sin modelos, GPU ni videos reales."""

import json
from pathlib import Path
import tempfile
import uuid
from unittest.mock import patch

from django.test import SimpleTestCase

from .preview import PreviewClock
from .sessions import AnalysisSession, _clear_run_outputs, stream_frames


class PreviewClockTests(SimpleTestCase):
    def select(self, clock, now, *, latest=299, completed=True, rate=10):
        return clock.select(now=now, source_fps=30, sample_fps=rate,
                            latest=latest, total=300, completed=completed)

    def test_faster_motor_does_not_jump_to_latest_processed(self):
        clock = PreviewClock()
        self.assertEqual(self.select(clock, 100), 0)
        for seconds in (1, 2, 5, 9):
            self.assertEqual(self.select(clock, 100 + seconds), seconds * 30)

    def test_reduced_update_rate_preserves_one_times_speed(self):
        for rate in (5, 10, 30, 60):
            with self.subTest(rate=rate):
                clock = PreviewClock()
                self.select(clock, 0, rate=rate)
                self.assertEqual(self.select(clock, 5, rate=rate), 150)

    def test_completed_motor_does_not_finish_preview_early(self):
        clock = PreviewClock()
        self.select(clock, 0)
        self.select(clock, 8.2)
        self.assertFalse(clock.finished)
        self.assertEqual(self.select(clock, 9.97), 299)
        self.assertFalse(clock.finished)
        self.assertEqual(self.select(clock, 10), 299)
        self.assertTrue(clock.finished)

    def test_slow_motor_never_exposes_future_or_unprocessed_frames(self):
        clock = PreviewClock()
        self.select(clock, 0, latest=0, completed=False)
        self.assertEqual(self.select(clock, 5, latest=60, completed=False), 60)
        self.select(clock, 12, latest=297, completed=False)
        self.assertFalse(clock.finished)
        self.assertEqual(self.select(clock, 13, latest=299), 299)
        self.assertTrue(clock.finished)

    def test_fractional_source_fps_selects_only_sampled_indices(self):
        clock = PreviewClock()
        for tenth in range(30):
            index = clock.select(now=tenth / 10, source_fps=29.97, sample_fps=10,
                                 latest=299, total=300, completed=False)
            self.assertGreaterEqual(index / 29.97, tenth / 10 - 0.134)
            self.assertLessEqual(index / 29.97, tenth / 10 + 1e-9)


class PreviewStreamTests(SimpleTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.session = AnalysisSession(
            id=uuid.uuid4(), directory=self.directory, filename="synthetic.mp4",
            profile="B", video_path=self.directory / "input.mp4",
            source_sha256="0" * 64, source_bytes=0, source_kind="manual",
            demo_source_id=None, zone={}, state="processing", run=1,
        )
        (self.directory / "preview").mkdir()

    def status_file(self, state="processing", latest=299):
        (self.directory / "status.json").write_text(json.dumps({
            "state": state, "frame": latest + 1, "total": 300, "source_fps": 30,
            "preview_sample_fps": 10, "preview_latest_frame": latest, "percent": 100,
        }), encoding="utf-8")

    def test_stream_uses_source_clock_and_exposes_timing_headers(self):
        for index in (0, 30, 150, 299):
            (self.directory / "preview" / f"{index:09d}.jpg").write_bytes(b"jpeg")
        self.status_file()
        with patch("apps.analysis.sessions.time.monotonic", return_value=100) as clock:
            stream = stream_frames(self.session)
            self.assertIn(b"X-Frame-Index: 0\r\n", next(stream))
            clock.return_value = 101
            frame = next(stream)
            self.assertIn(b"X-Frame-Index: 30\r\n", frame)
            self.assertIn(b"X-Source-Timestamp: 1.000000", frame)
            clock.return_value = 105
            self.assertIn(b"X-Frame-Index: 150\r\n", next(stream))
            stream.close()

    def test_status_keeps_result_pending_until_visual_end_then_transitions(self):
        self.session.active_config = {"profile": "B", "zone": {}}
        (self.directory / "annotated.mp4").write_bytes(b"mp4")
        self.status_file(state="completed")
        for index in (0, 299):
            (self.directory / "preview" / f"{index:09d}.jpg").write_bytes(b"jpeg")
        with patch("apps.analysis.sessions.time.monotonic", return_value=0) as clock:
            stream = stream_frames(self.session)
            next(stream)
            self.assertTrue(self.session.status()["preview"]["pending"])
            self.assertEqual(self.session.status()["percent"], 100)
            clock.return_value = 10
            self.assertIn(b"X-Frame-Index: 299", next(stream))
            self.assertFalse(self.session.status()["preview"]["pending"])
            with self.assertRaises(StopIteration):
                next(stream)

    def test_new_run_clears_spool_and_clock(self):
        (self.directory / "preview" / "000000000.jpg").write_bytes(b"jpeg")
        self.session.preview_clock.started_at = 100
        _clear_run_outputs(self.session)
        self.assertFalse((self.directory / "preview").exists())
        self.assertIsNone(self.session.preview_clock.started_at)

    def test_cancelled_or_restarted_stream_ends_without_serving_stale_images(self):
        self.status_file(latest=0)
        (self.directory / "preview" / "000000000.jpg").write_bytes(b"jpeg")
        stream = stream_frames(self.session)
        next(stream)
        self.session.run += 1
        with self.assertRaises(StopIteration):
            next(stream)
