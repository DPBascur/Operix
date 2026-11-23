from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Condition
from types import SimpleNamespace
from unittest import TestCase, mock
from uuid import uuid4

import numpy as np

from operix_engine.detection import BoundingBox, Detection
from operix_engine.operational_config import OperationalConfig, Zone
from operix_engine.rtsp_lab_overlay import MAX_BYTES, MAX_ITEMS, MAX_OBJECTS, OverlayMetadata, frame_fingerprint
from operix_engine.rtsp_pilot import Frame
from operix_engine.tracking import Track

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_rtsp_lab as lab


RECEIVED_UTC = datetime(2026, 11, 23, tzinfo=timezone.utc)


class OverlayTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name)
        self.run_id = uuid4()
        self.image = np.zeros((25, 33, 3), dtype=np.uint8)

    def producer(self, zones=(), writer=lab._write_atomic):
        return OverlayMetadata(self.output, self.run_id, zones, write_atomic=writer)

    def read(self):
        return json.loads((self.output / "overlay.json").read_bytes())

    def observe(self, producer, index, received, *, epoch=1, tracks=(), spatial_allowed=True):
        producer.observe(Frame(index, 1, received, None, self.image), tracks, epoch=epoch,
                         received_utc=RECEIVED_UTC, spatial_allowed=spatial_allowed)

    def test_fingerprint_samples_cell_centers_in_bgr_row_major_order(self):
        image = np.zeros((27, 35, 3), dtype=np.uint8)
        expected = []
        for row in range(12):
            for col in range(16):
                red, green, blue = (row * 23 + col) % 256, col * 17, (col * 19 + row) % 256
                image[int((row + .5) * 27 / 12), int((col + .5) * 35 / 16)] = blue, green, red
                expected.append(int((77 * red + 150 * green + 29 * blue) / 256 + .5))
        self.assertEqual(frame_fingerprint(image), expected)
        self.assertEqual(frame_fingerprint(np.array([[[0, 64, 0]]], dtype=np.uint8)), [38] * 192)

    def test_pipeline_uses_current_visible_tracks_and_samples_before_rendering(self):
        zone = Zone("area", "Area", ((0, 0), (1, 0), (1, 1), (0, 1)))
        pipeline = lab.LabPipeline(OperationalConfig(1, "lab", (zone,), ()),
                                   SimpleNamespace(width=33, height=25, fps=12), infer_remotely=True)
        producer = self.producer((zone,))
        frame = Frame(7, 1, 10, .625, self.image)
        detections = SimpleNamespace(
            person=(Detection(0, "person", .95, BoundingBox(8.25, 5, 45, 30)),),
            forklift=(Detection(0, "forklift", .95, BoundingBox(2, 2, 7, 7)),),
        )

        def consume(frame, tracks, *, spatial_allowed):
            producer.observe(frame, tracks, epoch=1, received_utc=RECEIVED_UTC, spatial_allowed=spatial_allowed)

        def render(image, *_args, **_kwargs):
            image[:] = 255
            return image

        with mock.patch.object(pipeline.renderer, "render_zone", side_effect=render):
            _, candidates, _, _ = pipeline.process(frame, 0., detected=detections, observe_overlay=consume)
        self.assertTrue(np.all(frame.image == 255))
        self.assertEqual(candidates, ())
        producer.publish(10)
        document = self.read()
        self.assertEqual(document["run_id"], str(self.run_id))
        item, = document["items"]
        self.assertEqual(set(item), {"index", "epoch", "pts_s", "received_utc", "processed_utc", "fingerprint",
                                     "objects", "zones"})
        self.assertEqual((item["index"], item["epoch"], item["pts_s"]), (7, 1, .625))
        self.assertEqual(item["received_utc"], RECEIVED_UTC.isoformat())
        self.assertGreaterEqual(datetime.fromisoformat(item["processed_utc"]), RECEIVED_UTC)
        self.assertEqual(item["fingerprint"], [0] * 192)
        self.assertCountEqual(item["objects"], [
            {"role": "person", "track_id": 1, "box": [.25, .2, 1., 1.]},
            {"role": "forklift", "track_id": 1, "box": [2 / 33, 2 / 25, 7 / 33, 7 / 25]},
        ])
        self.assertEqual(item["zones"], [{"zone_id": "area", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]}])
        no_detections = SimpleNamespace(person=(), forklift=())
        pipeline.process(Frame(8, 1, 10.25, None, self.image), .25,
                         detected=no_detections, observe_overlay=consume)
        producer.publish(10.25)
        self.assertEqual(self.read()["items"][-1]["objects"], [])
        self.assertIsNone(self.read()["items"][-1]["pts_s"])

    def test_rate_limit_age_limit_and_count_limit(self):
        writer = mock.Mock(wraps=lab._write_atomic)
        producer = self.producer(writer=writer)
        producer.clear()
        self.observe(producer, 0, 10)
        producer.publish(10)
        self.observe(producer, 1, 10.1)
        producer.publish(10.1)
        self.assertEqual(writer.call_count, 2)
        producer.publish(10.21)
        self.assertEqual([item["index"] for item in self.read()["items"]], [0, 1])
        for index in range(2, 80):
            self.observe(producer, index, 13.5 + index / 100)
        producer.publish(14.4)
        self.assertEqual([item["index"] for item in self.read()["items"]], list(range(80 - MAX_ITEMS, 80)))
        self.observe(producer, 80, 18.25)
        producer.publish(18.25)
        self.assertEqual([item["index"] for item in self.read()["items"]], [75, 76, 77, 78, 79, 80])

    def test_payload_drops_oldest_items_and_caps_objects(self):
        tracks = tuple(Track(index, 0, "person", .95, BoundingBox(3, 5, 20, 22))
                       for index in range(1, MAX_OBJECTS + 10))
        producer = self.producer()
        for index in range(MAX_ITEMS):
            self.observe(producer, index, 10 + index / 20, tracks=tracks)
        producer.publish(13.25)
        self.assertLessEqual((self.output / "overlay.json").stat().st_size, MAX_BYTES)
        items = self.read()["items"]
        self.assertLess(len(items), MAX_ITEMS)
        self.assertEqual(items[-1]["index"], MAX_ITEMS - 1)
        self.assertEqual(len(items[-1]["objects"]), MAX_OBJECTS)

    def test_epoch_framing_and_stall_clear_published_observations(self):
        zone = Zone("area", "Area", ((0, 0), (1, 0), (1, 1)))
        invalid = Zone("crossed", "Crossed", ((0, 0), (1, 1), (1, 0), (0, 1)))
        disabled = Zone("off", "Off", zone.polygon, enabled=False)
        producer = self.producer((zone, invalid, disabled))
        self.observe(producer, 0, 10)
        producer.publish(10)
        self.assertEqual([zone["zone_id"] for zone in self.read()["items"][0]["zones"]], ["area"])
        self.observe(producer, 1, 10.1, spatial_allowed=False)
        self.assertEqual(self.read()["items"], [])
        producer.publish(10.25)
        item, = self.read()["items"]
        self.assertEqual(item["index"], 1)
        self.assertNotIn("zones", item)
        self.observe(producer, 2, 10.3, epoch=2, spatial_allowed=False)
        self.assertEqual(self.read()["items"], [])
        producer.publish(10.5)
        self.assertEqual([item["epoch"] for item in self.read()["items"]], [2])
        producer.expire(11.31)
        self.assertEqual(self.read(), {"run_id": str(self.run_id), "items": []})

    def test_write_error_is_nonfatal_and_clear_can_retry(self):
        writer = mock.Mock(side_effect=[PermissionError("file busy"), None])
        producer = self.producer(writer=writer)
        with self.assertLogs("operix_engine.rtsp_lab_overlay", level="WARNING"):
            producer.clear()
        producer.clear()
        producer.clear()
        self.assertEqual(writer.call_count, 2)
        self.assertEqual(json.loads(writer.call_args.args[1]), {"run_id": str(self.run_id), "items": []})

    def test_marked_history_keeps_exact_frames_until_spatial_invalidation_or_disconnect(self):
        zone = Zone("area", "Area", ((0, 0), (1, 0), (1, 1)))
        producer = OverlayMetadata(self.output, self.run_id, (zone,),
                                   write_atomic=lab._write_atomic, stream_id="a" * 32)
        for index, epoch, allowed in ((3, 1, True), (5, 2, True), (6, 2, False)):
            frame = Frame(index, 1, 10 + index, index / 15, self.image, source_ordinal=index)
            producer.observe(frame, (), epoch=epoch, received_utc=RECEIVED_UTC, spatial_allowed=allowed)
            producer.publish(frame.received)
            if index == 5:
                self.assertEqual([(i["source_ordinal"], i["epoch"]) for i in self.read()["items"]],
                                 [(3, 1), (5, 2)])
        item, = self.read()["items"]
        self.assertEqual(item["source_ordinal"], 6)
        self.assertNotIn("zones", item)
        producer.clear()
        self.assertEqual(self.read()["items"], [])

    def test_runner_clears_live_metadata_on_disconnect_and_worker_end(self):
        capture = mock.MagicMock()
        capture.ready = Condition()
        capture.counts = lab.Counter()
        capture.queue = []
        capture.depth = 0
        args = SimpleNamespace(output=self.output, fps=12, width=33, height=25, seconds=10, config=None)
        status = lab.WorkerStatus(args)
        context = SimpleNamespace(analysis_run_id=self.run_id, source={"camera_id": "lab-cam-01"})
        config = OperationalConfig(1, "lab", (), ())
        pipeline = lab.LabPipeline(config, args, infer_remotely=True)
        detected = SimpleNamespace(person=(), forklift=(), wait_ms=0, person_ms=0, forklift_ms=0, batch_size=1)
        snapshots = {}
        real_write = status.write

        def record(state, *args):
            snapshots.setdefault(state, []).append(self.read())
            return real_write(state, *args)

        def frames():
            yield Frame(0, 1, lab.monotonic(), 0., self.image)
            capture.counts["read_failure"] += 1
            yield None
            yield Frame(1, 2, lab.monotonic(), 0., self.image)

        capture.next.side_effect = frames()
        with (
            mock.patch.object(lab, "Capture", return_value=capture),
            mock.patch.object(lab, "LabPipeline", return_value=pipeline),
            mock.patch.object(lab, "InferenceClient", return_value=mock.Mock(infer=mock.Mock(return_value=detected))),
            mock.patch.object(lab, "load_context", return_value=(context, config)),
            mock.patch("operix_engine.rtsp_lab_overlay.WRITE_INTERVAL_S", 0),
            mock.patch.object(status, "write", side_effect=record),
            mock.patch.dict(lab.os.environ, {
                "OPERIX_RTSP_URL": "rtsp://127.0.0.1/camera",
                "OPERIX_RTSP_ALLOWED_IP": "127.0.0.1",
                "OPERIX_EVENT_PUBLISH_TOKEN": "test",
                "OPERIX_EVENT_API_BASE_URL": "http://127.0.0.1:8000/api/v1",
                "OPERIX_RTSP_INFERENCE_SOCKET": "/private/lab.sock",
                "OPERIX_RTSP_LAB_CAMERA_ID": "lab-cam-01",
                "OPERIX_RTSP_LAB_INFERENCE_PROFILE": "pytorch-fp32",
            }),
        ):
            reason = lab.run(args, status, lambda: "OPERATOR_STOP" if status.metrics["frames_processed"] == 2 else None)
        self.assertEqual(reason, "OPERATOR_STOP")
        self.assertEqual([[item["epoch"] for item in snapshot["items"]]
                          for snapshot in snapshots["processing"]], [[1], [2]])
        self.assertEqual(snapshots["reconnecting"], [{"run_id": str(self.run_id), "items": []}])
        self.assertEqual(self.read(), {"run_id": str(self.run_id), "items": []})
