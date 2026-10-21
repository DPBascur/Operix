"""Pruebas de API temporal sin cargar YOLO ni procesar videos completos."""

import json
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from . import sessions


class AnalysisCandidateTransportTests(SimpleTestCase):
    """GET de candidatos transitorios; SimpleTestCase prohíbe consultas a la BD."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.identity = uuid.uuid4()
        self.session = sessions.AnalysisSession(
            id=self.identity, directory=Path(self.directory.name), filename="synthetic.mp4",
            profile="A", video_path=Path(self.directory.name) / "unused.mp4",
            source_sha256="0" * 64, source_bytes=0, source_kind="manual",
            demo_source_id=None, zone={}, state="processing",
        )
        registry = patch.dict(sessions._sessions, {self.identity: self.session})
        registry.start()
        self.addCleanup(registry.stop)
        self.client = APIClient()
        self.url = f"/api/v1/analysis/sessions/{self.identity}/status/"

    def update(self, **fields):
        (self.session.directory / "status.json").write_text(
            json.dumps({"state": "processing", "frame": 5, **fields}), encoding="utf-8",
        )

    def test_get_preserves_mixed_candidates_and_both_class_scoped_identities(self):
        single = {"candidate_kind": "zone_dwell", "track_id": 1, "class_name": "person",
                  "subjects": [{"role": "object", "class_name": "person", "track_id": 1}]}
        pair = {"candidate_kind": "person_forklift_proximity", "subjects": [
            {"role": "person", "class_name": "person", "track_id": 1},
            {"role": "forklift", "class_name": "forklift", "track_id": 1},
        ], "observed_normalized_distance": 0.2,
            "parameters": {"max_distance": 0.25, "minimum_duration_seconds": 1.0},
            "started_frame_index": 2, "started_timestamp_s": 1.0,
            "frame_index": 4, "timestamp_s": 2.0}
        self.update(candidates=[single, pair])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["candidates"], [single, pair])
        self.assertNotIn("track_id", response.json()["candidates"][1])
        self.assertEqual(response.json()["frame"], 5)
        self.assertEqual(response.json()["state"], "processing")

    def test_candidates_are_latest_frame_only_without_accumulation(self):
        self.update(candidates=[{"candidate_kind": "zone_dwell", "track_id": 1}])
        self.assertEqual(len(self.client.get(self.url).json()["candidates"]), 1)
        self.update(candidates=[])
        self.assertEqual(self.client.get(self.url).json()["candidates"], [])

    def test_legacy_status_without_candidates_remains_compatible(self):
        self.update(person_tracks=2)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["person_tracks"], 2)
        self.assertEqual(response.json()["candidates"], [])


@override_settings(
    OPERIX_ANALYSIS_MAX_UPLOAD_BYTES=1024,
    OPERIX_ANALYSIS_MAX_SESSIONS=2,
    OPERIX_ANALYSIS_RETENTION_SECONDS=60,
)
class AnalysisSessionApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.identities = []
        self.demo_directory = tempfile.TemporaryDirectory()
        demo_root = Path(self.demo_directory.name)
        self.demo_paths = {}
        for profile in ("A", "B", "C"):
            path = demo_root / f"demo-{profile}.mp4"
            path.write_bytes(b"\x00\x00\x00\x10ftypisomvideo")
            self.demo_paths[profile] = path
        self.demo_settings = override_settings(
            OPERIX_DEMO_VIDEO_A=str(self.demo_paths["A"]),
            OPERIX_DEMO_VIDEO_B=str(self.demo_paths["B"]),
            OPERIX_DEMO_VIDEO_C=str(self.demo_paths["C"]),
        )
        self.demo_settings.enable()

    def tearDown(self):
        for identity in self.identities:
            sessions.remove_session(identity)
        self.demo_settings.disable()
        self.demo_directory.cleanup()

    def create(self, profile="A", name="sample.mp4"):
        upload = SimpleUploadedFile(name, b"\x00\x00\x00\x10ftypisomvideo", content_type="video/mp4")
        response = self.client.post("/api/v1/analysis/sessions/", {"video": upload, "profile": profile}, format="multipart")
        if response.status_code == 201:
            self.identities.append(uuid.UUID(response.data["id"]))
        return response

    def test_create_returns_profile_and_temporary_video(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["state"], "ready")
        self.assertEqual(response.data["zone"]["zone_id"], "area_transito_demo")
        self.assertTrue(sessions.get_session(self.identities[0]).video_path.is_file())
        self.assertEqual(response.data["source_bytes"], 17)
        self.assertEqual(self.client.get(f"/api/v1/analysis/sessions/{self.identities[0]}/status/").status_code, 200)
        self.assertEqual(response.data["source_kind"], "manual")
        self.assertIsNone(response.data["demo_source_id"])

    def test_profiles_expose_only_authorized_demo_ids(self):
        response = self.client.get("/api/v1/analysis/profiles/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["default_demo_video"]["id"] for item in response.data],
            ["warehouse_fire", "forklift_human_nearmiss", "warehouse_box_pickup"],
        )
        self.assertNotIn(str(self.demo_directory.name), json.dumps(response.data))

    def test_demo_session_uses_profile_source_and_same_start_cycle(self):
        response = self.client.post(
            "/api/v1/analysis/sessions/",
            {"profile": "B", "demo_source_id": "forklift_human_nearmiss"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        identity = uuid.UUID(response.data["id"])
        self.identities.append(identity)
        session = sessions.get_session(identity)
        self.assertEqual(session.video_path, self.demo_paths["B"].resolve())
        self.assertEqual(response.data["source_kind"], "demo")
        self.assertEqual(response.data["demo_source_id"], "forklift_human_nearmiss")
        with patch("apps.analysis.views.start_session") as start:
            start.side_effect = lambda value: setattr(value, "state", "processing")
            started = self.client.post(f"/api/v1/analysis/sessions/{identity}/start/")
        self.assertEqual(started.status_code, 202)
        self.assertEqual(started.data["state"], "processing")

    def test_each_profile_uses_its_own_demo_source(self):
        expected_sources = {
            "A": "warehouse_fire",
            "B": "forklift_human_nearmiss",
            "C": "warehouse_box_pickup",
        }
        for profile, source_id in expected_sources.items():
            with self.subTest(profile=profile):
                response = self.client.post(
                    "/api/v1/analysis/sessions/",
                    {"profile": profile, "demo_source_id": source_id},
                    format="json",
                )
                self.assertEqual(response.status_code, 201)
                identity = uuid.UUID(response.data["id"])
                self.identities.append(identity)
                self.assertEqual(sessions.get_session(identity).video_path, self.demo_paths[profile].resolve())
                self.assertEqual(response.data["demo_source_id"], source_id)
                sessions.remove_session(identity)
                self.identities.remove(identity)

    def test_demo_endpoints_reject_arbitrary_paths_and_missing_profile_demo(self):
        self.assertEqual(
            self.client.post(
                "/api/v1/analysis/sessions/",
                {"profile": "A", "demo_source_id": "../../test.mp4"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/api/v1/analysis/profiles/A/demo/../../test.mp4/").status_code,
            404,
        )
        with override_settings(OPERIX_DEMO_VIDEO_C=""):
            catalog = self.client.get("/api/v1/analysis/profiles/").data
            self.assertIsNone(catalog[2]["default_demo_video"])
            self.assertEqual(
                self.client.post(
                    "/api/v1/analysis/sessions/",
                    {"profile": "C", "demo_source_id": "warehouse_box_pickup"},
                    format="json",
                ).status_code,
                400,
            )

    def test_demo_and_session_source_support_video_ranges(self):
        demo = self.client.get(
            "/api/v1/analysis/profiles/A/demo/warehouse_fire/",
            HTTP_RANGE="bytes=4-7",
        )
        self.assertEqual(demo.status_code, 206)
        self.assertEqual(b"".join(demo.streaming_content), b"ftyp")
        response = self.client.post(
            "/api/v1/analysis/sessions/",
            {"profile": "A", "demo_source_id": "warehouse_fire"},
            format="json",
        )
        identity = uuid.UUID(response.data["id"])
        self.identities.append(identity)
        source = self.client.get(
            f"/api/v1/analysis/sessions/{identity}/source/",
            HTTP_RANGE="bytes=-5",
        )
        self.assertEqual(source.status_code, 206)
        self.assertEqual(b"".join(source.streaming_content), b"video")

    def test_manual_video_survives_profile_change(self):
        response = self.create("A")
        identity = response.data["id"]
        session = sessions.get_session(uuid.UUID(identity))
        original = session.video_path
        updated = self.client.put(
            f"/api/v1/analysis/sessions/{identity}/zone/",
            {"profile": "C"}, format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["source_kind"], "manual")
        self.assertEqual(session.video_path, original)

    def test_invalid_upload_and_missing_session(self):
        self.assertEqual(self.create(name="secret.txt").status_code, 400)
        self.assertEqual(self.create(profile="unknown").status_code, 400)
        unknown = uuid.uuid4()
        self.assertEqual(self.client.get(f"/api/v1/analysis/sessions/{unknown}/status/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/analysis/sessions/{unknown}/stream/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/analysis/sessions/{unknown}/result/").status_code, 404)

    def test_rejects_oversize_and_bad_header(self):
        with override_settings(OPERIX_ANALYSIS_MAX_UPLOAD_BYTES=8):
            self.assertEqual(self.create().status_code, 400)
        upload = SimpleUploadedFile("bad.mp4", b"not-a-real-mp4", content_type="video/mp4")
        self.assertEqual(self.client.post("/api/v1/analysis/sessions/", {"video": upload, "profile": "A"}, format="multipart").status_code, 400)

    def test_zone_edit_is_isolated_and_locked_after_start(self):
        first = self.create("A")
        second = self.create("B")
        identity = first.data["id"]
        polygon = [[0.1, 0.1], [0.9, 0.1], [0.8, 0.9]]
        updated = self.client.put(f"/api/v1/analysis/sessions/{identity}/zone/", {"polygon": polygon}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["zone"]["polygon"], polygon)
        self.assertNotEqual(second.data["zone"]["polygon"], polygon)
        self.assertEqual(self.client.put(f"/api/v1/analysis/sessions/{identity}/zone/", {"polygon": [[2, 0], [0, 1], [1, 1]]}, format="json").status_code, 400)
        self.assertEqual(self.client.put(f"/api/v1/analysis/sessions/{identity}/zone/", {"profile": ["A"]}, format="json").status_code, 400)
        self.assertEqual(self.client.put(f"/api/v1/analysis/sessions/{identity}/zone/", {"profile": "C"}, format="json").data["profile"], "C")
        with patch("apps.analysis.views.start_session") as start:
            start.side_effect = lambda session: setattr(session, "state", "processing")
            self.assertEqual(self.client.post(f"/api/v1/analysis/sessions/{identity}/start/").status_code, 202)
        self.assertEqual(self.client.put(f"/api/v1/analysis/sessions/{identity}/zone/", {"polygon": polygon}, format="json").status_code, 409)

    def test_cancel_preserves_source_and_removes_partial_result(self):
        self.create()
        identity = self.identities[0]
        session = sessions.get_session(identity)
        session.state = "processing"
        process = Mock()
        process.poll.return_value = None
        session.process = process
        (session.directory / "annotated.partial.mp4").write_bytes(b"partial")
        self.assertEqual(self.client.post(f"/api/v1/analysis/sessions/{identity}/stop/").data["state"], "cancelled")
        process.terminate.assert_called_once()
        self.assertTrue(session.video_path.exists())
        self.assertFalse((session.directory / "annotated.partial.mp4").exists())

    def test_stream_exposes_latest_jpeg_then_ends(self):
        self.create()
        session = sessions.get_session(self.identities[0])
        url = f"/api/v1/analysis/sessions/{session.id}/stream/"
        self.assertEqual(self.client.get(url).status_code, 409)
        session.state = "processing"
        (session.directory / "frame.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        (session.directory / "annotated.mp4").write_bytes(b"abcdefghijkl")
        session.active_config = {"profile": "A", "zone": session.zone}
        (session.directory / "status.json").write_text(json.dumps({"state": "completed", "frame": 1}), encoding="utf-8")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"image/jpeg", b"".join(response.streaming_content))

    def test_close_terminates_active_preview_stream(self):
        self.create()
        session = sessions.get_session(self.identities[0])
        session.state = "processing"
        (session.directory / "frame.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        response = self.client.get(f"/api/v1/analysis/sessions/{session.id}/stream/")
        stream = iter(response.streaming_content)
        self.assertIn(b"image/jpeg", next(stream))
        self.assertEqual(self.client.delete(f"/api/v1/analysis/sessions/{session.id}/").status_code, 204)
        self.assertEqual(list(stream), [])

    def test_result_range_and_snapshot_after_completion(self):
        self.create()
        session = sessions.get_session(self.identities[0])
        url = f"/api/v1/analysis/sessions/{session.id}/result/"
        self.assertEqual(self.client.get(url).status_code, 409)
        session.state = "processing"
        session.active_config = {"profile": "A", "zone": json.loads(json.dumps(session.zone))}
        (session.directory / "annotated.mp4").write_bytes(b"abcdefghijkl")
        (session.directory / "status.json").write_text(json.dumps({"state": "completed", "frame": 277, "source_fps": 30}), encoding="utf-8")
        response = self.client.get(url, HTTP_RANGE="bytes=2-5")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 2-5/12")
        self.assertEqual(b"".join(response.streaming_content), b"cdef")
        self.assertEqual(self.client.get(url, HTTP_RANGE="bytes=99-").status_code, 416)
        suffix = self.client.get(url, HTTP_RANGE="bytes=-3")
        self.assertEqual(suffix.status_code, 206)
        self.assertEqual(b"".join(suffix.streaming_content), b"jkl")
        full = self.client.get(url)
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full["Accept-Ranges"], "bytes")
        full.close()
        edited = self.client.put(f"/api/v1/analysis/sessions/{session.id}/zone/", {"profile": "B"}, format="json")
        self.assertTrue(edited.data["pending_changes"])
        self.assertEqual(edited.data["result"]["profile"], "A")
        self.assertTrue(session.video_path.exists())

    def test_restart_same_source_clears_old_result_and_resets_run(self):
        self.create()
        session = sessions.get_session(self.identities[0])
        session.state = "completed"
        (session.directory / "annotated.mp4").write_bytes(b"old")
        (session.directory / "status.json").write_text('{"state":"completed"}', encoding="utf-8")
        fake = Mock()
        fake.poll.return_value = 0
        existing = Path(__file__)
        with override_settings(OPERIX_ENGINE_PYTHON=str(existing), OPERIX_PERSON_WEIGHTS=str(existing), OPERIX_FORKLIFT_WEIGHTS=str(existing)), patch("apps.analysis.sessions.subprocess.Popen", return_value=fake), patch("apps.analysis.sessions.threading.Thread.start"):
            sessions.start_session(session)
        self.assertEqual(session.state, "preparing")
        self.assertEqual(session.run, 1)
        self.assertTrue(session.video_path.exists())
        self.assertFalse((session.directory / "annotated.mp4").exists())
        self.assertFalse((session.directory / "status.json").exists())

    def test_close_deletes_source_result_and_session(self):
        self.create()
        session = sessions.get_session(self.identities[0])
        directory = session.directory
        (directory / "annotated.mp4").write_bytes(b"result")
        self.assertEqual(self.client.delete(f"/api/v1/analysis/sessions/{session.id}/").status_code, 204)
        self.assertFalse(directory.exists())
        self.assertIsNone(sessions.get_session(session.id))

    def test_close_while_result_response_is_open(self):
        self.create()
        session = sessions.get_session(self.identities[0])
        session.state = "completed"
        session.active_config = {"profile": "A", "zone": session.zone}
        (session.directory / "annotated.mp4").write_bytes(b"result")
        response = self.client.get(f"/api/v1/analysis/sessions/{session.id}/result/")
        self.assertEqual(response.status_code, 200)
        directory = session.directory
        self.assertEqual(self.client.delete(f"/api/v1/analysis/sessions/{session.id}/").status_code, 204)
        response.close()
        for _ in range(20):
            if not directory.exists():
                break
            time.sleep(0.1)
        self.assertFalse(directory.exists())

    def test_session_limit_and_cleanup(self):
        self.create("A")
        self.create("B")
        self.assertEqual(self.create("C").status_code, 400)
        identity = self.identities.pop()
        directory = sessions.get_session(identity).directory
        sessions.remove_session(identity)
        self.assertFalse(directory.exists())
        self.assertIsNone(sessions.get_session(identity))

    def test_idle_cleanup_keeps_recent_or_active_session(self):
        self.create()
        identity = self.identities[0]
        session = sessions.get_session(identity)
        session._cleanup_timer.cancel()
        session._cleanup_timer = None
        with patch.object(session, "_schedule_after") as schedule:
            with patch("apps.analysis.sessions.time.monotonic", return_value=session.last_access + 30):
                sessions.expire_session(identity)
            schedule.assert_called_once()
            self.assertIsNotNone(sessions.get_session(identity))
            schedule.reset_mock()
            session.state = "processing"
            with patch("apps.analysis.sessions.time.monotonic", return_value=session.last_access + 90):
                sessions.expire_session(identity)
            schedule.assert_called_once()
            self.assertIsNotNone(sessions.get_session(identity))
            session.state = "completed"
            with patch("apps.analysis.sessions.time.monotonic", return_value=session.last_access + 90):
                sessions.expire_session(identity)
            self.assertIsNone(sessions.get_session(identity))
