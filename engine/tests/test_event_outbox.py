"""Outbox local sin red ni modelos: orden, recuperación y evidencia íntegra."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from operix_engine.event_outbox import EventOutbox
from operix_engine.event_publishing import EventContext, PublishResult
from operix_engine.rules import EventCandidate


class Sink:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def publish_document(self, payload, image):
        self.calls.append((payload, image))
        return (PublishResult("failed", http_status=503) if self.fail else
                PublishResult("published", event_id=str(uuid4())))


class EventOutboxTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.context = EventContext(uuid4(), "TEST_DATA_VIEW", datetime.now(timezone.utc))
        self.candidate = EventCandidate("TEST_DATA_RULE", 1, 1, 1., 1, "person", "zone",
            {"kind": "zone_dwell", "class_name": "person", "zone_id": "zone", "min_duration_s": 1.}, True, 1.)
        self.image = b"\x89PNG\r\n\x1a\nfixture"

    def test_zero_candidates_has_no_fake_events(self):
        sink = Sink()
        box = EventOutbox(self.root, sink)
        box.enqueue((), self.context, None)
        self.assertEqual(box.summary()["candidates"], 0)
        self.assertEqual(sink.calls, [])

    def test_absent_journal_or_unjournaled_candidate_is_not_saved(self):
        box = EventOutbox(self.root, Sink())
        self.assertEqual(box.replay()["state"], "failed")
        box.enqueue((), self.context, None)
        self.assertEqual(box.replay()["state"], "saved")
        (self.root / ("a" * 64 + ".pending.json")).write_text('{}')
        self.assertEqual(box.replay()["state"], "failed")

    def test_all_candidates_same_and_different_frames_keep_order(self):
        sink = Sink()
        box = EventOutbox(self.root, sink)
        box.enqueue((self.candidate, replace(self.candidate, track_id=2)), self.context, self.image)
        box.enqueue((replace(self.candidate, frame_index=3, timestamp_s=3.),), self.context, self.image)
        self.assertEqual([(p["frame_index"], p["track_id"]) for p, _ in sink.calls], [(1,1),(1,2),(3,1)])
        self.assertEqual(box.summary()["saved"], 3)
        self.assertEqual(len(box.journal.read_text().splitlines()), 3)

    def test_failed_http_keeps_durable_evidence_and_bounded_retry(self):
        sink = Sink(fail=True)
        box = EventOutbox(self.root, sink)
        with patch("operix_engine.event_publishing.time.sleep"):
            box.enqueue((self.candidate,), self.context, self.image)
        self.assertEqual(len(sink.calls), 3)
        self.assertEqual(box.summary()["state"], "failed")
        recovered = Sink()
        replay = EventOutbox(self.root, recovered)
        self.assertEqual(replay.replay()["saved"], 1)
        self.assertEqual(recovered.calls[0][0], sink.calls[0][0])
        replay.replay()
        self.assertEqual(len(recovered.calls), 1)

    def test_missing_or_modified_png_does_not_claim_saved(self):
        box = EventOutbox(self.root, Sink())
        box.enqueue((self.candidate,), self.context, None)
        self.assertEqual(box.summary()["state"], "failed")
        self.assertEqual(box.summary()["saved"], 0)

    def test_interrupted_journal_is_not_silently_skipped(self):
        sink = Sink(fail=True)
        box = EventOutbox(self.root, sink)
        with patch("operix_engine.event_publishing.time.sleep"):
            box.enqueue((self.candidate,), self.context, self.image)
        with box.journal.open("a", encoding="utf-8") as output:
            output.write('{"incomplete":')
        sink.fail = False
        summary = box.replay()
        self.assertEqual(summary["saved"], 1)
        self.assertEqual(summary["invalid_records"], 1)
        self.assertEqual(summary["state"], "failed")

    def test_failed_png_can_recover_from_retained_candidate_frame(self):
        import cv2
        import numpy as np
        sink = Sink()
        box = EventOutbox(self.root, sink)
        with patch("cv2.imencode", return_value=(False, None)):
            box.enqueue((self.candidate,), self.context, None,
                        fallback_frame=np.zeros((24, 32, 3), dtype=np.uint8))
        self.assertEqual(box.summary()["state"], "failed")
        self.assertEqual(sink.calls, [])
        self.assertEqual(box.replay()["saved"], 1)
        recovered = cv2.imdecode(np.frombuffer(sink.calls[0][1], dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(recovered.shape, (24, 32, 3))

    def test_corrupted_recovery_frame_is_not_published(self):
        import numpy as np
        sink = Sink(fail=True)
        box = EventOutbox(self.root, sink)
        with patch("cv2.imencode", return_value=(False, None)):
            box.enqueue((self.candidate,), self.context, None,
                        fallback_frame=np.zeros((24, 32, 3), dtype=np.uint8))
        next(self.root.glob("*.npy")).write_bytes(b"corrupted")
        self.assertEqual(box.replay()["saved"], 0)
        self.assertEqual(sink.calls, [])

    def test_local_publisher_rejects_external_target_and_redirects(self):
        from operix_engine.event_publishing import HttpEventSink, _NoEventRedirect
        with self.assertRaises(ValueError):
            HttpEventSink("https://example.com/api/v1", local_only=True)
        self.assertIsNone(_NoEventRedirect().redirect_request(None, None, 302, "redirect", {}, "https://example.com"))

    def test_two_runs_have_separate_journals_and_images(self):
        first = EventOutbox(self.root / "first", Sink())
        second = EventOutbox(self.root / "second", Sink())
        first.enqueue((self.candidate,), self.context, self.image)
        second.enqueue((self.candidate,), replace(self.context, analysis_run_id=uuid4()), self.image)
        self.assertNotEqual(first.journal.read_bytes(), second.journal.read_bytes())
