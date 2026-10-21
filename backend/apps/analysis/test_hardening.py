"""Fallos y concurrencia local sin GPU, modelos ni base de datos."""

import json
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
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
                                     OPERIX_FORKLIFT_WEIGHTS=existing, OPERIX_ANALYSIS_TIMEOUT_SECONDS=10)
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
