import hashlib
from io import BytesIO
import json
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Condition
from types import SimpleNamespace
from unittest import TestCase, mock
from uuid import uuid4

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_rtsp_lab as lab
from operix_engine.event_publishing import EventContext, HttpEventSink, PublishResult
from operix_engine.rtsp_lab_clips import ClipStore, JpegRing
from operix_engine.rtsp_pilot import Frame
from operix_engine.rules import EventCandidate


class ImmediateExecutor:
    def submit(self, operation, *args):
        future = Future()
        future.set_result(operation(*args))
        return future


class WorkerTests(TestCase):
    def test_requires_explicit_pinned_literal_rtsp_address(self):
        for url, address in (
            ("rtsp://mediamtx:8554/camera", "192.168.1.2"),
            ("rtsp://192.168.1.3/camera", "192.168.1.2"),
            ("http://192.168.1.2/camera", "192.168.1.2"),
            ("rtsp://192.168.1.2/camera", ""),
        ):
            with self.subTest(url=url, address=address), self.assertRaises(ValueError):
                lab.authorized_url({"OPERIX_RTSP_URL": url, "OPERIX_RTSP_ALLOWED_IP": address})
        url = "rtsp://[fd00::2]:8554/camera"
        self.assertEqual(lab.authorized_url({"OPERIX_RTSP_URL": url, "OPERIX_RTSP_ALLOWED_IP": "fd00::2"}), url)

    def test_stop_file_is_terminal_without_opening_capture(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "stop").touch()
            arguments = ["run_rtsp_lab.py", "--output", directory, "--config", "unused.json",
                         "--person-weights", "unused.pt", "--forklift-weights", "unused.pt"]
            with mock.patch.object(sys, "argv", arguments), mock.patch.object(lab.signal, "signal"):
                self.assertEqual(lab.main(), 0)
            status = json.loads((folder / "status.json").read_bytes())
            self.assertEqual((status["state"], status["termination_reason"]), ("stopped", "OPERATOR_STOP"))
            self.assertIsNone(status["last_frame_at"])
            self.assertEqual(status["metrics"]["frames_processed"], 0)
            self.assertFalse((folder / "status.json.tmp").exists())

    def test_capture_reconnects_resets_pipeline_and_writes_preview_and_metrics(self):
        class FakeCapture:
            def __init__(self, _reader, *, fps, trace):
                self.trace = trace
                self.ready = Condition()
                self.counts = lab.Counter()
                self.thread = SimpleNamespace(is_alive=lambda: True)
                self.step = 0

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def next(self):
                self.step += 1
                if self.step == 2:
                    self.counts["read_failure"] += 1
                    return None
                now = lab.monotonic()
                self.trace("open", self.step, now - .2)
                for offset in (.2, .1, 0):
                    self.trace("decoded", self.step, now - offset)
                return Frame(self.step, self.step, now, float(self.step), image)

        image = np.zeros((16, 32, 3), dtype=np.uint8)
        pipeline = mock.Mock()
        pipeline.process.return_value = (image, (), 7.0, 2.0)
        context = SimpleNamespace(analysis_run_id=uuid4())
        with TemporaryDirectory() as directory:
            args = SimpleNamespace(output=Path(directory), fps=10.0, width=32, height=16, seconds=10, config=None)
            status = lab.WorkerStatus(args)
            states = mock.Mock(wraps=status.write)
            with (mock.patch.object(lab, "Capture", FakeCapture), mock.patch.object(lab, "LabPipeline", return_value=pipeline),
                  mock.patch.object(lab, "load_context", return_value=(context, None)), mock.patch.object(status, "write", states),
                  mock.patch.dict(lab.os.environ, {"OPERIX_RTSP_URL": "rtsp://127.0.0.1/camera",
                      "OPERIX_RTSP_ALLOWED_IP": "127.0.0.1", "OPERIX_EVENT_PUBLISH_TOKEN": "test",
                      "OPERIX_EVENT_API_BASE_URL": "http://127.0.0.1:8000/api/v1"})):
                reason = lab.run(args, status, lambda: "OPERATOR_STOP" if status.metrics["frames_processed"] == 2 else None)
            self.assertEqual(reason, "OPERATOR_STOP")
            self.assertEqual(states.call_args_list, [mock.call(name) for name in (
                "connecting", "processing", "reconnecting", "processing",
            )])
            self.assertEqual(pipeline.reset.call_args_list, [mock.call(1), mock.call(2)])
            status.write("stopped", reason)
            data = json.loads((args.output / "status.json").read_bytes())
            self.assertIsNotNone(datetime.fromisoformat(data["last_frame_at"]).utcoffset())
            self.assertEqual(data["metrics"]["received_fps"], 10.0)
            self.assertEqual(data["metrics"]["epochs"], {"initial": 1, "reconnect": 1})
            self.assertEqual(data["metrics"]["p95_inference_ms"], 7)
            self.assertEqual(data["metrics"]["p95_rules_ms"], 2)
            self.assertGreaterEqual(data["metrics"]["p95_arrival_to_result_ms"], 0)
            self.assertTrue((args.output / "preview.jpg").read_bytes().startswith(b"\xff\xd8"))


class EventTests(TestCase):
    def setUp(self):
        self.event_id = str(uuid4())
        self.received = datetime(2026, 11, 21, 16, 0, 0, 543210, tzinfo=timezone.utc)
        self.context = EventContext(uuid4(), "lab-cam-01", self.received, {
            "kind": "lab", "video_sha256": "a" * 64, "config_sha256": "b" * 64,
            "spatial_configuration": {"view_id": "lab-cam-01"},
        })
        self.candidate = EventCandidate(
            "rule", 1, 8, 1.23456, 1, "person", "zone", {"kind": "zone_dwell"}, True, 1.2, 2,
        )
        self.processed = self.received + timedelta(milliseconds=75)
        self.frame = SimpleNamespace(index=8, pts=51.0)
        self.epoch = SimpleNamespace(uses_pts=True)
        self.image = np.full((28, 32, 3), 170, dtype=np.uint8)

    def test_event_posts_reception_time_and_real_png_with_post_context(self):
        def response(status, document):
            reply = BytesIO(json.dumps(document).encode())
            reply.status = status
            return reply

        with mock.patch.dict(lab.os.environ, {"OPERIX_EVENT_PUBLISH_TOKEN": "test-token"}):
            sink = HttpEventSink("http://127.0.0.1:8000/api/v1", local_only=True)
        metrics = lab.Counter()
        clips = mock.Mock()
        clips.save.return_value = "saved"
        publisher = lab.EventPublisher(sink, clips, ImmediateExecutor(), metrics, fps=2)
        ring = JpegRing(2)
        ring.append(7, b"previous")
        ring.append(8, b"trigger")
        with mock.patch.object(sink, "_request", side_effect=[
            response(201, {"id": self.event_id}), response(201, {}),
        ]) as request:
            publisher.submit((self.candidate,), self.context, self.received, self.processed,
                             self.frame, self.epoch, ring, self.image)
            publisher.advance(9, b"following")
            request.assert_not_called()
            publisher.advance(10, b"last")
            publisher.collect()
        event_request, evidence_request = [call.args[0] for call in request.call_args_list]
        payload = json.loads(event_request.data)
        self.assertEqual(event_request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(evidence_request.get_header("Authorization"), "Bearer test-token")
        self.assertTrue(evidence_request.full_url.endswith(f"/{self.event_id}/evidence/"))
        self.assertEqual(payload["occurred_at"], self.received.isoformat())
        self.assertEqual(payload["video_timestamp_s"], "1.235")
        self.assertEqual(payload["source"]["epoch"], 2)
        self.assertEqual(payload["source"]["spatial_configuration"], self.context.source["spatial_configuration"])
        self.assertEqual(payload["source"]["capture"], {
            "received_at": self.received.isoformat(), "processed_at": self.processed.isoformat(),
            "source_pts_s": 51.0, "time_basis": "source_pts",
        })
        png = evidence_request.data[evidence_request.data.index(b"\x89PNG"):].rsplit(b"\r\n--", 1)[0]
        image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertTrue(np.array_equal(image, self.image))
        clips.save.assert_called_once_with(self.event_id, payload, [(7, b"previous"), (8, b"trigger"),
                                                                  (9, b"following"), (10, b"last")])
        self.assertEqual((metrics["events_published"], metrics["evidence_saved"], metrics["clips_saved"]), (1, 1, 1))

    def test_epoch_cut_flushes_pending_and_quota_survives_reset(self):
        sink = mock.Mock()
        sink.publish_document.return_value = PublishResult("published", http_status=201, event_id=self.event_id)
        clips = mock.Mock(save=mock.Mock(return_value="saved"))
        metrics = lab.Counter({"events_submitted": lab.MAX_EVENTS - 1})
        publisher = lab.EventPublisher(sink, clips, ImmediateExecutor(), metrics, fps=12)
        ring = JpegRing(12)
        ring.append(8, b"trigger")
        publisher.submit((self.candidate,) * 2, self.context, self.received, self.processed,
                         self.frame, self.epoch, ring, self.image)
        publisher.flush()
        ring.clear()
        publisher.advance(9, b"new epoch")
        publisher.collect()
        self.assertEqual(metrics["events_submitted"], lab.MAX_EVENTS)
        self.assertEqual(metrics["events_skipped_quota"], 1)
        event_id, _, frames = clips.save.call_args.args
        self.assertEqual((event_id, frames), (self.event_id, [(8, b"trigger")]))

    def test_clip_matches_authorized_path_and_event_metadata(self):
        payload = lab.reception_payload(self.candidate, self.context, self.received, self.processed, None, False)
        frames = [(7, b"before"), (8, b"at"), (9, b"after")]
        mp4 = b"encoded test file"
        with TemporaryDirectory() as directory:
            store = ClipStore(Path(directory), 12)
            with mock.patch("operix_engine.rtsp_lab_clips._encode_clip", side_effect=lambda path, *_: path.write_bytes(mp4)):
                self.assertEqual(store.save(self.event_id, payload, frames), "saved")
                self.assertEqual(store.save(self.event_id, payload, frames), "existing")
            folder = Path(directory) / "evidence-clips" / self.event_id / str(self.context.analysis_run_id)
            metadata = json.loads((folder / "metadata.json").read_bytes())
            self.assertEqual(metadata, {
                "kind": "annotated", "event_id": self.event_id, "analysis_run_id": str(self.context.analysis_run_id),
                "source_sha256": "a" * 64, "config_sha256": "b" * 64, "event_frame": 8,
                "event_timestamp_s": "1.235", "start_frame": 7, "end_frame_exclusive": 10, "fps": 12,
                "duration_s": .25, "event_offset_s": 1 / 12, "bytes": len(mp4),
                "sha256": hashlib.sha256(mp4).hexdigest(),
            })

    def test_ring_bounds_memory_and_drops_context_across_index_gap(self):
        ring = JpegRing(2, seconds=1, max_bytes=7)
        for index in range(4):
            ring.append(index, b"123")
        self.assertEqual([index for index, _ in ring.snapshot()], [2, 3])
        ring.append(6, b"123")
        self.assertEqual(ring.snapshot(), ((6, b"123"),))
