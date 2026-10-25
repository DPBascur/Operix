"""Fallos y concurrencia local sin GPU, modelos ni base de datos."""

import json
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from . import sessions


class SessionHardeningTests(SimpleTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.session = self.make_session("first")
        self.other = self.make_session("second")
        registry = patch.dict(sessions._sessions, {self.session.id: self.session, self.other.id: self.other}, clear=True)
        registry.start()
        self.addCleanup(registry.stop)
        for session in (self.session, self.other):
            self.addCleanup(session.close)
        existing = str(Path(__file__))
        settings = override_settings(OPERIX_ENGINE_PYTHON=existing, OPERIX_PERSON_WEIGHTS=existing,
                                     OPERIX_FORKLIFT_WEIGHTS=existing, OPERIX_ANALYSIS_TIMEOUT_SECONDS=10,
                                     MEDIA_ROOT=str(self.root / "media"))
        settings.enable()
        self.addCleanup(settings.disable)

    def make_session(self, name):
        directory = self.root / name
        directory.mkdir()
        zone = json.loads(sessions.PROFILES["B"].read_text(encoding="utf-8"))["zones"][0]
        return sessions.AnalysisSession(uuid.uuid4(), directory, "synthetic.mp4", "B",
                                        directory / "input.mp4", "0" * 64, 0, "manual", None, zone)

    def completed(self):
        self.session.state = "processing"
        self.session.active_config = {"profile": "B", "zone": self.session.zone}
        (self.session.directory / "annotated.mp4").write_bytes(b"mp4")
        (self.session.directory / "status.json").write_text(json.dumps({
            "state": "completed", "frame": 300, "total": 300, "source_fps": 30,
            "preview_sample_fps": 10, "preview_latest_frame": 299,
        }), encoding="utf-8")

    @override_settings(EVENT_POST_ENABLED=False)
    def test_operational_person_snapshot_and_worker_sha_gate(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(sessions.subprocess, "Popen", return_value=process) as spawn, \
                patch.object(sessions.threading, "Thread"):
            sessions.start_session(self.session)
        command = spawn.call_args.args[0]
        expected = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
        self.assertEqual(command[command.index("--person-sha256") + 1], expected)
        self.assertEqual(command[command.index("--person-weights") + 1], str(Path(__file__)))
        config = self.session.active_config["person"]
        self.assertEqual(config, {"model_id": "YOLO11N_COCO_PERSON", "weights_sha256": expected,
                                 "class_filter": "person", "imgsz": 640, "confidence": .10, "nms_iou": .70})
        self.assertEqual(self.session.active_config["forklift"]["weights_sha256"], sessions.FORKLIFT_SHA256)

    def test_completed_without_preview_consumer_exposes_result(self):
        self.completed()
        status = self.session.status()
        self.assertEqual(status["state"], "completed")
        self.assertFalse(status["preview"]["pending"])
        self.assertIsNotNone(status["result"])

    def test_disconnected_preview_finishes_via_status_clock(self):
        self.completed()
        self.session.preview_clock.started_at = 100
        with patch("apps.analysis.sessions.time.monotonic", return_value=105):
            self.assertTrue(self.session.status()["preview"]["pending"])
        with patch("apps.analysis.sessions.time.monotonic", return_value=110):
            status = self.session.status()
            self.assertFalse(status["preview"]["pending"])
            self.assertEqual(status["preview"]["frame_index"], 299)

    def test_live_other_worker_rejects_without_output_changes(self):
        self.other.process = Mock()
        self.other.process.poll.return_value = None
        with patch("apps.analysis.sessions.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "otro análisis"):
                sessions.start_session(self.session)
        spawn.assert_not_called()
        self.assertEqual(self.session.run, 0)
        self.assertEqual(list(self.session.directory.iterdir()), [])

    def test_dead_other_worker_does_not_block_new_job(self):
        self.other.process = Mock()
        self.other.process.poll.return_value = 1
        with patch("apps.analysis.sessions.subprocess.Popen") as spawn, patch("apps.analysis.sessions.threading.Thread.start"):
            sessions.start_session(self.session)
        spawn.assert_called_once()

    def test_concurrent_requests_start_only_one_gpu_job(self):
        fake = Mock()
        fake.poll.return_value = None
        errors = []
        barrier = threading.Barrier(2)
        real_thread = threading.Thread

        def start(session):
            barrier.wait(timeout=2)
            try:
                sessions.start_session(session)
            except ValueError as error:
                errors.append(str(error))

        # No watcher threads in this test; request threads are real.
        with patch("apps.analysis.sessions.subprocess.Popen", return_value=fake) as spawn, \
             patch("apps.analysis.sessions.threading.Thread") as factory:
            factory.side_effect = lambda *a, **kw: Mock() if kw.get("name", "").startswith("analysis-") else real_thread(*a, **kw)
            threads = [real_thread(target=start, args=(s,)) for s in (self.session, self.other)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual(len(errors), 1)

    def test_spawn_failure_is_sanitized_and_retryable(self):
        with patch("apps.analysis.sessions.subprocess.Popen", side_effect=OSError("sensitive-path")), \
             self.assertLogs("apps.analysis.sessions", level="ERROR"):
            with self.assertRaisesRegex(RuntimeError, "No se pudo iniciar"):
                sessions.start_session(self.session)
        status = self.session.status()
        self.assertEqual(status["state"], "error")
        self.assertNotIn("sensitive-path", json.dumps(status))
        with patch("apps.analysis.sessions.subprocess.Popen"), patch("apps.analysis.sessions.threading.Thread.start"):
            sessions.start_session(self.session)
        self.assertIsNone(self.session.failure_detail)
        self.assertEqual(self.session.run, 2)

    def test_hung_worker_terminates_and_cannot_publish_partial_result(self):
        fake = Mock()
        fake.wait.side_effect = [subprocess.TimeoutExpired("worker", 10), 0]
        fake.poll.return_value = 0
        callbacks = []
        with patch("apps.analysis.sessions.subprocess.Popen", return_value=fake), \
             patch("apps.analysis.sessions.threading.Thread") as thread:
            thread.side_effect = lambda **kw: callbacks.append(kw["target"]) or Mock()
            sessions.start_session(self.session)
        (self.session.directory / "annotated.partial.mp4").write_bytes(b"partial")
        callbacks[0]()
        fake.terminate.assert_called_once()
        self.assertEqual(self.session.state, "error")
        self.assertIn("tiempo máximo", self.session.status()["detail"])
        self.assertIsNone(self.session.process)
        self.assertFalse((self.session.directory / "annotated.partial.mp4").exists())

    def test_crashed_worker_has_terminal_state(self):
        self.session.state = "processing"
        self.session.process = Mock()
        self.session.process.poll.return_value = 1
        self.assertEqual(self.session.status()["state"], "error")
        self.session.process = None  # El watcher ya recogió el proceso.
        self.assertIn("volver a intentarlo", self.session.status()["detail"])

    def test_completed_status_with_nonzero_worker_exit_is_not_success(self):
        self.completed()
        self.session.process = Mock()
        self.session.process.poll.return_value = 1
        data = self.session.status()
        self.assertEqual(data["state"], "error")
        self.assertIsNone(data["result"])

    def test_completed_receipt_waits_for_successful_worker_exit(self):
        self.completed()
        self.session.process = Mock()
        self.session.process.poll.return_value = None
        data = self.session.status()
        self.assertEqual(data["state"], "processing")
        self.assertIsNone(data["result"])
        self.session.process.poll.return_value = 0
        data = self.session.status()
        self.assertEqual(data["state"], "completed")
        self.assertIsNotNone(data["result"])

    def test_stop_cannot_erase_a_newer_run_or_process(self):
        previous, new = Mock(), Mock()
        previous.poll.return_value = None
        self.session.state = "processing"
        self.session.process = previous
        def new_run(*args, **kwargs):
            self.session.run += 1
            self.session.process = new
            self.session.state = "processing"
            (self.session.directory / "status.json").write_text("new run", encoding="utf-8")
        previous.wait.side_effect = new_run
        self.session.stop()
        self.assertIs(self.session.process, new)
        self.assertEqual(self.session.state, "processing")
        self.assertEqual((self.session.directory / "status.json").read_text(), "new run")
        self.session.process = None

    def test_crash_invalidates_a_stale_saved_ipc_receipt(self):
        self.completed()
        self.session.outbox_directory = self.root / "outbox"
        self.session.outbox_directory.mkdir()
        path = self.session.directory / "status.json"
        data = json.loads(path.read_text())
        data["persistence"] = {"state":"saved","candidates":1,"saved":1,"failed":0}
        path.write_text(json.dumps(data), encoding="utf-8")
        self.session.process = Mock()
        self.session.process.poll.return_value = 1
        self.assertEqual(self.session.status()["persistence"]["state"], "failed")
        self.session.process = None

    def test_removed_session_cannot_reuse_old_outputs(self):
        identity, directory = self.session.id, self.session.directory
        (directory / "frame.jpg").write_bytes(b"jpeg")
        sessions.remove_session(identity)
        self.assertIsNone(sessions.get_session(identity))
        self.assertFalse(directory.exists())
        self.assertEqual(APIClient().get(f"/api/v1/analysis/sessions/{identity}/status/").status_code, 404)

    def test_unwritable_directory_error_does_not_expose_path(self):
        with patch("apps.analysis.views.start_session", side_effect=OSError("sensitive-path")):
            response = APIClient().post(f"/api/v1/analysis/sessions/{self.session.id}/start/")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("sensitive-path", response.content.decode())
        self.assertIn("permisos", response.json()["detail"])

    def test_zone_edit_rechecks_state_under_guard(self):
        original = self.session.zone
        def racing_status():
            self.session.state = "processing"
            return {"state": "ready"}
        with patch.object(self.session, "status", side_effect=racing_status):
            response = APIClient().put(f"/api/v1/analysis/sessions/{self.session.id}/zone/",
                                       {"profile": "A"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.session.zone, original)

    def test_graceful_shutdown_closes_only_registered_sessions(self):
        process = Mock()
        process.poll.return_value = None
        self.session.process = process
        self.session.state = "processing"
        unrelated = self.root / "unrelated.txt"
        unrelated.write_text("preserve", encoding="utf-8")
        sessions.close_all_sessions()
        process.terminate.assert_called_once()
        self.assertEqual(sessions._sessions, {})
        self.assertFalse(self.session.directory.exists())
        self.assertFalse(self.other.directory.exists())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve")

    @override_settings(EVENT_POST_ENABLED=False)
    def test_delete_before_start_rejects_retained_reference(self):
        sessions.remove_session(self.session.id)
        with patch.object(sessions.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "eliminada"):
                sessions.start_session(self.session)
        spawn.assert_not_called()

    @override_settings(EVENT_POST_ENABLED=False)
    def test_delete_keeps_gpu_reserved_until_worker_exits(self):
        entered, release = threading.Event(), threading.Event()
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = lambda **kw: (entered.set(), release.wait(3))
        self.session.state, self.session.process = "processing", process
        errors = []

        def delete():
            try:
                sessions.remove_session(self.session.id)
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=delete)
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            acquired = sessions._lock.acquire(blocking=False)
            if acquired:
                sessions._lock.release()
            self.assertFalse(acquired)
            self.assertIs(sessions._sessions[self.session.id], self.session)
            self.assertTrue(self.session._closed)
            self.assertIs(self.session.process, process)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        with self.assertRaises(ValueError):
            sessions.start_session(self.session)
        self.assertIsNone(sessions.get_session(self.session.id))

    @override_settings(EVENT_POST_ENABLED=False)
    def test_delete_during_startup_waits_then_terminates_launched_worker(self):
        entered, release = threading.Event(), threading.Event()
        process = Mock()
        process.poll.return_value = None
        errors = []

        def spawn(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test synchronization timed out")
            return process

        def start():
            try:
                sessions.start_session(self.session)
            except Exception as error:
                errors.append(error)

        real_thread = threading.Thread
        with patch.object(sessions.subprocess, "Popen", side_effect=spawn), patch.object(sessions.threading, "Thread") as factory:
            factory.side_effect = lambda *a, **kw: Mock() if kw.get("name", "").startswith("analysis-") else real_thread(*a, **kw)
            starter = real_thread(target=start)
            starter.start()
            self.assertTrue(entered.wait(3))
            deleter = real_thread(target=sessions.remove_session, args=(self.session.id,))
            deleter.start()
            release.set()
            starter.join(3)
            deleter.join(3)
        self.assertFalse(starter.is_alive() or deleter.is_alive())
        self.assertEqual(errors, [])
        process.terminate.assert_called_once()
        self.assertIsNone(sessions.get_session(self.session.id))

    @override_settings(EVENT_POST_ENABLED=False)
    def test_old_expiration_cannot_delete_restarted_session(self):
        self.session._schedule_after(3600)
        generation = self.session._cleanup_generation
        process = Mock()
        process.poll.return_value = None
        with patch.object(sessions.subprocess, "Popen", return_value=process), patch.object(sessions.threading, "Thread"):
            sessions.start_session(self.session)
        for state in ("preparing", "processing", "completed"):
            self.session.state = state
            with patch.object(sessions.time, "monotonic", return_value=self.session.last_access + 10000):
                sessions.expire_session(self.session.id, generation)
            self.assertIs(sessions.get_session(self.session.id), self.session)
        self.assertFalse(self.session._closed)

    def test_expiration_keeps_startup_and_running(self):
        for state in ("preparing", "processing"):
            self.session.state = state
            with patch.object(self.session, "_schedule_after") as schedule, \
                    patch.object(sessions.time, "monotonic", return_value=self.session.last_access + 10000):
                sessions.expire_session(self.session.id)
            self.assertIs(sessions.get_session(self.session.id), self.session)
            schedule.assert_called_once()

    def test_expiration_before_start_rejects_retained_reference(self):
        with patch.object(sessions.time, "monotonic", return_value=self.session.last_access + 10000):
            sessions.expire_session(self.session.id)
        with self.assertRaisesRegex(ValueError, "eliminada"):
            sessions.start_session(self.session)

    def test_late_cancel_does_not_overwrite_failure(self):
        self.session.state = "error"
        self.session.failure_detail = "Fallo previo"
        with self.assertRaises(ValueError):
            self.session.stop()
        self.assertEqual(self.session.state, "error")
        self.assertEqual(self.session.status()["detail"], "Fallo previo")

    def test_cancel_after_completion_preserves_result(self):
        self.completed()
        with self.assertRaisesRegex(ValueError, "No hay"):
            self.session.stop()
        self.assertEqual(self.session.state, "completed")
        self.assertTrue((self.session.directory / "annotated.mp4").is_file())

    def test_failure_or_cancel_never_exposes_100_percent(self):
        for state in ("cancelled", "error"):
            self.completed()
            self.session.state = state
            path = self.session.directory / "status.json"
            data = json.loads(path.read_text())
            data["percent"] = 100
            path.write_text(json.dumps(data), encoding="utf-8")
            status = self.session.status()
            self.assertEqual(status["state"], state)
            self.assertLess(status["percent"], 100)
            self.assertIsNone(status["result"])

    @override_settings(EVENT_POST_ENABLED=False)
    def test_old_watcher_cannot_overwrite_new_generation(self):
        callbacks = []
        process = Mock()
        process.poll.return_value = None
        with patch.object(sessions.subprocess, "Popen", return_value=process), patch.object(sessions.threading, "Thread") as factory:
            factory.side_effect = lambda **kw: callbacks.append(kw["target"]) or Mock()
            sessions.start_session(self.session)
        self.session.run += 1
        self.session.state = "preparing"
        (self.session.directory / "annotated.mp4").write_bytes(b"new generation")
        callbacks[0]()
        self.assertEqual(self.session.state, "preparing")
        self.assertTrue((self.session.directory / "annotated.mp4").is_file())

    def test_invalid_api_shapes_and_huge_coordinates_are_400(self):
        client = APIClient()
        for payload in ([], None, {"profile": []}, {"profile": {}}):
            response = client.post("/api/v1/analysis/sessions/", payload, format="json")
            self.assertEqual(response.status_code, 400)
        url = f"/api/v1/analysis/sessions/{self.session.id}/zone/"
        for payload in ([], {"polygon": [[0, 0], [1, 0], [10 ** 400, 1]]}):
            self.assertEqual(client.put(url, payload, format="json").status_code, 400)

    def test_huge_range_is_416_not_internal_error(self):
        (self.session.directory / "input.mp4").write_bytes(b"video")
        response = APIClient().get(f"/api/v1/analysis/sessions/{self.session.id}/source/",
                                   HTTP_RANGE="bytes=" + "9" * 5000 + "-")
        self.assertEqual(response.status_code, 416)

    @override_settings(OPERIX_ANALYSIS_MAX_SESSIONS=3)
    def test_upload_name_cannot_choose_storage_path(self):
        outside = self.root / "preserve.txt"
        outside.write_text("preserve", encoding="utf-8")
        upload = SimpleUploadedFile("..\\..\\clip.mp4", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32)
        created = sessions.create_session(upload, "A")
        try:
            self.assertEqual(created.filename, "clip.mp4")
            self.assertEqual(created.video_path.parent, created.directory)
            self.assertEqual(created.video_path.name, "input.mp4")
            self.assertEqual(outside.read_text(encoding="utf-8"), "preserve")
        finally:
            sessions.remove_session(created.id)

    def test_client_cannot_supply_a_local_video_path(self):
        response = APIClient().post("/api/v1/analysis/sessions/",
                                    {"profile": "A", "video_path": "../preserve.mp4"}, format="json")
        self.assertEqual(response.status_code, 400)
