from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import stat
import tempfile
from threading import BoundedSemaphore, Event
from time import perf_counter, sleep
import unittest
from unittest.mock import patch

import numpy as np

from operix_engine.detection import BoundingBox, Detection
from operix_engine.rtsp_inference import (
    FatalInferenceError, InferenceBroker, InferenceBusy, InferenceClient, InferenceError, InferenceGenerationChanged,
    InferenceTimeout, check_ready, _Identity, _LENGTH, _REQUEST_LIMIT, _RESPONSE_LIMIT, _Request,
    _json_packet, _read, _read_json, _send,
)


class Detector:
    def __init__(self, role):
        self.role = role
        self.calls = []

    def detect(self, frame):
        return self.detect_batch((frame,))[0]

    def detect_batch(self, frames):
        markers = tuple(int(frame[0, 0, 0]) for frame in frames)
        self.calls.append(markers)
        return tuple((Detection(marker, self.role, .5, BoundingBox(0, 0, 1, 1)),
                      Detection(99, "other", .9, BoundingBox(0, 0, 1, 1))) for marker in markers)


def frame(marker=1, width=4):
    return np.full((2, width, 3), marker, dtype=np.uint8)


class InferenceTests(unittest.TestCase):
    def setUp(self):
        self.person, self.forklift = Detector("person"), Detector("forklift")
        self.client = InferenceClient("unused", camera_id="cam-01", run_id="run-01")

    def broker(self, **kwargs):
        return InferenceBroker("unused", person=self.person, forklift=self.forklift, **kwargs)

    def infer(self, client=None, image=None, *, budget=.8, frame_index=42):
        return (client or self.client).infer(
            frame() if image is None else image, epoch=1, frame_index=frame_index, deadline=perf_counter() + budget,
        )

    @contextmanager
    def transport(self, handler):
        with ThreadPoolExecutor(max_workers=8) as workers:
            futures = []

            def connect(_client, _deadline):
                client, server = socket.socketpair()
                futures.append(workers.submit(handler, server))
                return client

            with patch.object(InferenceClient, "_connect", connect):
                yield
            for future in futures:
                future.result(timeout=1)

    @contextmanager
    def running(self, broker):
        slots = BoundedSemaphore(broker.max_clients)

        def handle(sock):
            self.assertTrue(slots.acquire(timeout=1))
            broker._handle(sock, slots)

        with ThreadPoolExecutor(max_workers=1) as worker:
            scheduler = worker.submit(broker._schedule)
            try:
                with self.transport(handle):
                    yield scheduler
            finally:
                broker.stop()

    def test_round_trip_uses_bgr_and_keeps_role_detections(self):
        image = np.arange(48, dtype=np.uint8).reshape(2, 8, 3)[:, 1::2]
        timeline = []
        person_detect, forklift_detect = self.person.detect, self.forklift.detect

        def detect(role, implementation, image):
            timeline.append(role)
            return implementation(image)

        with (patch.object(self.person, "detect", side_effect=lambda image: detect("person", person_detect, image)),
              patch.object(self.forklift, "detect", side_effect=lambda image: detect("forklift", forklift_detect, image)),
              self.running(self.broker(synchronize=lambda: timeline.append("sync")))):
            result = self.infer(image=image)
        self.assertEqual(result.person, (Detection(3, "person", .5, BoundingBox(0, 0, 1, 1)),))
        self.assertEqual(result.forklift, (Detection(3, "forklift", .5, BoundingBox(0, 0, 1, 1)),))
        self.assertEqual(timeline, ["sync", "person", "sync", "forklift", "sync"])
        self.assertEqual(result.batch_size, 1)
        self.assertGreaterEqual(result.wait_ms, 0)
        self.assertGreater(result.person_ms, 0)
        self.assertGreater(result.forklift_ms, 0)

    def test_oldest_shape_leads_each_batch_and_cap_is_hard(self):
        for cap in (1, 2, 4):
            with self.subTest(cap=cap):
                self.person.calls.clear()
                broker = self.broker(batch_cap=cap, batch_wait_s=0)
                now = perf_counter()
                for index, width in enumerate((4, 2, 4, 4, 4, 4)):
                    identity = _Identity(f"cam-{index}", "run", 1, 0, str(index), now + .8, 2, width)
                    broker._pending.append(_Request(identity, frame(index, width), now))
                while broker._pending:
                    broker._infer(broker._next_batch())
                self.assertEqual(self.person.calls[0], (0, 2, 3, 4)[:cap])
                self.assertEqual(self.person.calls[1], (1,))
                self.assertEqual(sorted(marker for call in self.person.calls for marker in call), list(range(6)))

    def test_bounded_wait_dispatches_a_single_frame(self):
        broker = self.broker(batch_cap=4, batch_wait_s=.010)
        with self.running(broker):
            self.infer()
        self.assertEqual(self.person.calls, [(1,)])

    def test_duplicate_camera_run_rejected_even_after_first_client_times_out(self):
        entered, release = Event(), Event()
        original = self.person.detect

        def stalled(image):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test did not release detector")
            return original(image)

        duplicate = InferenceClient("unused", camera_id="cam-01", run_id="run-01")
        with patch.object(self.person, "detect", stalled), self.running(self.broker()):
            with ThreadPoolExecutor(max_workers=1) as worker:
                first = worker.submit(self.infer, budget=.2)
                try:
                    self.assertTrue(entered.wait(1))
                    with self.assertRaises(InferenceBusy):
                        self.infer()
                    with self.assertRaises(InferenceTimeout):
                        first.result(timeout=1)
                    with self.assertRaises(InferenceBusy):
                        self.infer(duplicate)
                finally:
                    release.set()

    def test_client_checks_each_response_identity_field(self):
        broker = self.broker()
        for field in _Identity.__slots__:
            with self.subTest(field=field):
                def wrong_identity(sock):
                    deadline = perf_counter() + .8
                    with sock:
                        identity = _Identity(**_read_json(sock, _REQUEST_LIMIT, deadline))
                        _send(sock, broker._response(identity, "ready"), deadline)
                        _read(sock, bytearray(identity.height * identity.width * 3), deadline)
                        wire = identity.wire()
                        wire[field] = wire[field] + (".5" if isinstance(wire[field], str) else 1)
                        reply = _json_packet({
                            "identity": wire, "status": "ok", "generation": broker._generation,
                            "person": [], "forklift": [], "batch_size": 1, "wait_ms": 0,
                            "person_ms": 0, "forklift_ms": 0,
                        }, _RESPONSE_LIMIT)
                        _send(sock, reply, deadline)

                with self.transport(wrong_identity), self.assertRaises(InferenceError):
                    self.infer()

    def test_invalid_reply_timing_is_rejected(self):
        broker = self.broker()
        for field, value in (("batch_size", True), ("batch_size", 5), ("wait_ms", -1),
                             ("person_ms", "0"), ("forklift_ms", None)):
            with self.subTest(field=field, value=value):
                def invalid_timing(sock):
                    deadline = perf_counter() + .8
                    with sock:
                        identity = _Identity(**_read_json(sock, _REQUEST_LIMIT, deadline))
                        _send(sock, broker._response(identity, "ready"), deadline)
                        _read(sock, bytearray(identity.height * identity.width * 3), deadline)
                        timing = {"batch_size": 1, "wait_ms": 0, "person_ms": 0, "forklift_ms": 0}
                        timing[field] = value
                        _send(sock, broker._response(
                            identity, "ok", person=[], forklift=[], **timing,
                        ), deadline)

                with self.transport(invalid_timing), self.assertRaises(InferenceError):
                    self.infer()

    def test_client_stays_invalid_after_broker_restart_between_frames(self):
        first, restarted = self.broker(), self.broker()
        with self.running(first):
            self.assertEqual(self.infer().person[0].class_id, 1)
        with self.running(restarted):
            with self.assertRaises(InferenceGenerationChanged):
                self.infer(frame_index=43)
            fresh = InferenceClient("unused", camera_id="cam-01", run_id="run-02")
            self.assertEqual(self.infer(fresh).person[0].class_id, 1)
        with patch.object(InferenceClient, "_connect", side_effect=AssertionError("invalid client connected")):
            with self.assertRaises(InferenceGenerationChanged):
                self.infer(frame_index=44)

    def test_client_checks_generation_on_result_after_admission(self):
        first, other = self.broker(), self.broker()

        def wrong_generation(sock):
            deadline = perf_counter() + .8
            with sock:
                identity = _Identity(**_read_json(sock, _REQUEST_LIMIT, deadline))
                _send(sock, first._response(identity, "ready"), deadline)
                _read(sock, bytearray(identity.height * identity.width * 3), deadline)
                _send(sock, other._response(
                    identity, "ok", person=[], forklift=[], batch_size=1, wait_ms=0, person_ms=0, forklift_ms=0,
                ), deadline)

        with self.transport(wrong_generation), self.assertRaises(InferenceGenerationChanged):
            self.infer()

    def test_eof_is_timeout_only_at_or_after_deadline(self):
        for eof, error in ((1.9, InferenceError), (2.0, InferenceTimeout), (2.1, InferenceTimeout)):
            with self.subTest(eof=eof):
                client, server = socket.socketpair()
                server.close()
                with client, patch("operix_engine.rtsp_inference.perf_counter", side_effect=(1, eof)):
                    with self.assertRaises(error) as raised:
                        _read(client, bytearray(1), 2)
                self.assertIs(type(raised.exception), error)

    def test_bad_exchange_does_not_stop_broker(self):
        broker = self.broker()
        slots = BoundedSemaphore(1)
        with self.running(broker), ThreadPoolExecutor(max_workers=1) as worker:
            client, server = socket.socketpair()
            self.assertTrue(slots.acquire(blocking=False))
            future = worker.submit(broker._handle, server, slots)
            with client:
                client.sendall(_LENGTH.pack(_REQUEST_LIMIT + 1))
            future.result(timeout=1)
            self.assertTrue(slots.acquire(blocking=False))
            slots.release()
            self.assertEqual(self.infer().person[0].class_id, 1)

    def test_detector_error_is_contained_or_fatal_as_configured(self):
        for fatal in (False, True):
            client = InferenceClient("unused", camera_id="cam-01", run_id="run-01")
            with self.subTest(fatal=fatal), self.running(self.broker(fatal_detector_errors=fatal)) as scheduler:
                with patch.object(self.person, "detect", side_effect=RuntimeError("detector failure")):
                    with self.assertRaisesRegex(InferenceError, "closed" if fatal else "could not infer"):
                        self.infer(client)
                if fatal:
                    with self.assertRaises(FatalInferenceError):
                        scheduler.result(timeout=1)
                else:
                    self.assertEqual(self.infer(client).person[0].class_id, 1)

    @unittest.skipUnless(os.name == "posix" and hasattr(socket, "AF_UNIX"), "requires POSIX Unix sockets")
    def test_unix_socket_directory_permissions_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "infer.sock"
            path.parent.mkdir(mode=0o700)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale:
                stale.bind(os.fspath(path))
            self.assertFalse(check_ready(path))
            broker = InferenceBroker(path, person=self.person, forklift=self.forklift, max_clients=1)
            client = InferenceClient(path, camera_id="cam", run_id="run")

            def wait_ready(serving):
                until = perf_counter() + 1
                while not check_ready(path):
                    if serving.done():
                        serving.result()
                    self.assertLess(perf_counter(), until, "broker never became ready")
                    sleep(.01)

            with ThreadPoolExecutor(max_workers=1) as worker:
                serving = worker.submit(broker.serve_forever)
                try:
                    wait_ready(serving)
                    self.assertEqual(self.infer(client, budget=.3).person[0].class_id, 1)
                    self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                    competing = InferenceBroker(path, person=self.person, forklift=self.forklift)
                    with self.assertRaisesRegex(InferenceError, "running broker"):
                        competing.serve_forever()
                    self.assertTrue(check_ready(path))
                finally:
                    broker.stop()
                serving.result(timeout=1)
            self.assertFalse(path.exists())
            self.assertFalse(check_ready(path))
            restarted = InferenceBroker(path, person=self.person, forklift=self.forklift)
            with ThreadPoolExecutor(max_workers=1) as worker:
                serving = worker.submit(restarted.serve_forever)
                try:
                    wait_ready(serving)
                    with self.assertRaises(InferenceGenerationChanged):
                        self.infer(client, frame_index=43)
                finally:
                    restarted.stop()
                serving.result(timeout=1)
            path.write_text("keep")
            with self.assertRaisesRegex(ValueError, "not a socket"):
                competing.serve_forever()
            self.assertEqual(path.read_text(), "keep")
            path.parent.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "0700"):
                broker.serve_forever()
