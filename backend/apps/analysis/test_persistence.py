"""Web/API → worker real (detecciones fixture) → HTTP → DB/evidencia/consultas."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch
from uuid import UUID

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import LiveServerTestCase, SimpleTestCase, override_settings
from rest_framework.test import APIClient

from apps.events.models import Event
from . import sessions


@override_settings(EVENT_POST_ENABLED=True, ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"])
class WebPersistenceTests(LiveServerTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = Path(__file__).resolve().parents[3]
        self.python = Path(os.environ.get(
            "OPERIX_ENGINE_PYTHON", str(self.repo / "engine/.venv/Scripts/python.exe")))
        self.video = self.root / "TEST_DATA.avi"
        make = "import cv2,numpy as np,sys; w=cv2.VideoWriter(sys.argv[1],cv2.VideoWriter_fourcc(*'MJPG'),1,(200,100)); assert w.isOpened(); [w.write(np.full((100,200,3),80,np.uint8)) for _ in range(4)]; w.release()"
        subprocess.run([str(self.python), "-B", "-c", make, str(self.video)], check=True, timeout=30)
        self.config = self.root / "controlled.json"
        self.config.write_text(json.dumps({"schema_version": 1, "view_id": "TEST_DATA_VIEW",
            "coordinate_system": "normalized", "zones": [{"zone_id": "TEST_DATA_ZONE", "name": "Fixture",
            "polygon": [[0,0],[1,0],[1,1],[0,1]]}], "rules": [{"rule_id": "TEST_DATA_PAIR", "version": 1,
            "enabled": True, "parameters": {"kind": "person_forklift_proximity", "zone_id": "TEST_DATA_ZONE",
            "person_class": "person", "forklift_class": "forklift", "max_distance": .25,
            "minimum_duration_seconds": 1.}}]}), encoding="utf-8")
        settings = override_settings(MEDIA_ROOT=str(self.root / "media"),
            OPERIX_ENGINE_PYTHON=str(self.python), OPERIX_PERSON_WEIGHTS=str(self.config),
            OPERIX_FORKLIFT_WEIGHTS=str(self.config), OPERIX_EVENT_API_BASE_URL=self.live_server_url + "/api/v1")
        settings.enable()
        self.addCleanup(settings.disable)
        profiles = patch.dict(sessions.PROFILES, {"A": self.config})
        profiles.start()
        self.addCleanup(profiles.stop)
        self.identities = []
        self.addCleanup(lambda: [sessions.remove_session(identity) for identity in self.identities])
        self.real_popen = subprocess.Popen
        fixture = Path(__file__).parent / "fixtures/perception_worker.py"

        def spawn(command, **kwargs):
            return self.real_popen([command[0], "-B", str(fixture), *command[1:]], **kwargs)

        # Solo se sustituye percepción/carga CUDA en el proceso hijo. El bucle real,
        # OpenCV, ByteTrack, reglas, outbox, HTTP, PostgreSQL y rutas API se ejecutan.
        self.spawn = spawn
        self.client = APIClient()

    def create(self):
        with self.video.open("rb") as source:
            response = self.client.post("/api/v1/analysis/sessions/", {
                "video": SimpleUploadedFile(self.video.name, source.read()), "profile": "A"}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        identity = UUID(response.data["id"])
        self.identities.append(identity)
        return identity

    def run_analysis(self, identity):
        with patch("apps.analysis.sessions.subprocess.Popen", side_effect=self.spawn):
            response = self.client.post(f"/api/v1/analysis/sessions/{identity}/start/")
        self.assertEqual(response.status_code, 202, response.data)
        session = sessions.get_session(identity)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            data = self.client.get(f"/api/v1/analysis/sessions/{identity}/status/").json()
            if session.process is None:
                return data
            time.sleep(.05)
        self.fail("Worker no terminó dentro del límite del test")

    def test_web_pair_persistence_result_evidence_history_and_retention(self):
        identity = self.create()
        data = self.run_analysis(identity)
        self.assertEqual(data["state"], "completed", data)
        self.assertEqual(data["persistence"]["state"], "saved", data)
        self.assertEqual(data["persistence"]["saved"], 2)
        self.assertEqual(data["frame"], 4)
        self.assertEqual(Event.objects.count(), 2)
        session = sessions.get_session(identity)
        receipts = json.loads((session.directory / "TEST_ONLY_overlay_receipts.json").read_text(encoding="utf-8"))
        self.assertEqual([row["frame"] for row in receipts], [0, 1, 2, 3])
        self.assertEqual(set(Event.objects.values_list("analysis_run_id", flat=True)), {UUID(data["analysis_run_id"])})
        result = self.client.get(f"/api/v1/analysis/sessions/{identity}/result/")
        self.assertEqual(result.status_code, 200)
        result.close()
        for event in Event.objects.all():
            receipt = receipts[event.frame_index]
            relation = next(item for item in receipt["relations"]
                            if item["forklift"] == event.interaction["forklift"]["track_id"])
            self.assertEqual(relation["state"], "CONDITION_SATISFIED")
            self.assertAlmostEqual(relation["distance"], float(event.observations["normalized_distance"]))
            self.assertAlmostEqual(relation["duration"], float(event.observations["duration_s"]))
            self.assertEqual(relation["geometry_version"], "person_equipment_nearest_ground_edges_v1")
            self.assertAlmostEqual(relation["distance"], {1: 0., 2: .1}[relation["forklift"]])
            if relation["forklift"] == 1:
                self.assertEqual(relation["person_anchor"], [.2875, .7])
                self.assertEqual(relation["equipment_target"], [.2875, .7])
            self.assertEqual(event.observations["proximity_geometry"], {
                "version": relation["geometry_version"], "person_anchor": relation["person_anchor"],
                "equipment_target": relation["equipment_target"]})
            verify = "import cv2,hashlib,sys; a=cv2.imread(sys.argv[1]); print(hashlib.sha256(a.tobytes()).hexdigest())"
            raw_hash = subprocess.check_output([str(self.python), "-B", "-c", verify, event.evidence_image.path], text=True).strip()
            self.assertEqual(raw_hash, receipt["image_sha256"])
            self.assertEqual(event.source["perception"]["person"], {
                "model_id": "YOLO11M_COCO_PERSON", "weights_sha256": sessions.PERSON_SHA256,
                "class_filter": "person", "imgsz": 640, "confidence": 0.10, "nms_iou": 0.70,
            })
            self.assertEqual(event.source["person_weights_sha256"], sessions.PERSON_SHA256)
            self.assertEqual(event.source["perception"]["forklift"]["model_id"], "FORKLIFT_SPECIALIST_V2")
            self.assertEqual(data["result"]["person"], event.source["perception"]["person"])
            evidence = self.client.get(f"/api/v1/events/{event.id}/evidence/")
            self.assertEqual(evidence.status_code, 200)
            self.assertTrue(b"".join(evidence.streaming_content).startswith(b"\x89PNG"))
            self.assertEqual(event.source["session_id"], str(identity))
        self.assertEqual(self.client.get("/api/v1/events/frequencies/").json()["total"], 2)
        directory = sessions.get_session(identity).outbox_directory
        self.client.delete(f"/api/v1/analysis/sessions/{identity}/")
        self.assertTrue(directory.is_dir())
        self.assertEqual(Event.objects.count(), 2)

    def test_second_analysis_has_separate_run_source_and_evidence(self):
        first = self.create()
        one = self.run_analysis(first)
        second = self.create()
        two = self.run_analysis(second)
        self.assertNotEqual(one["analysis_run_id"], two["analysis_run_id"])
        self.assertEqual(Event.objects.count(), 4)
        self.assertEqual(len(set(Event.objects.values_list("evidence_image", flat=True))), 4)

    def test_operator_like_projection_preserves_person_and_both_equipment_relations(self):
        # Fixture de contención, no una afirmación de ocupancia física confirmada.
        identity = self.create()
        with patch.dict(os.environ,{"OPERIX_TEST_OCCUPANCY_SCENARIO":"contained"}):
            data = self.run_analysis(identity)
        self.assertEqual(data["state"],"completed",data)
        self.assertEqual(data["persistence"]["saved"],2)
        events = list(Event.objects.all())
        self.assertEqual(len(events),2)
        self.assertEqual({event.interaction["person"]["track_id"] for event in events},{1})
        self.assertEqual({event.interaction["forklift"]["track_id"] for event in events},{1,2})
        session = sessions.get_session(identity)
        receipts = json.loads((session.directory/"TEST_ONLY_overlay_receipts.json").read_text(encoding="utf-8"))
        for event in events:
            relation = next(item for item in receipts[event.frame_index]["relations"]
                            if item["forklift"]==event.interaction["forklift"]["track_id"])
            self.assertEqual(relation["geometry_version"],"person_equipment_nearest_ground_edges_v1")
            self.assertEqual(event.observations["proximity_geometry"]["person_anchor"],relation["person_anchor"])
            evidence = self.client.get(f"/api/v1/events/{event.id}/evidence/")
            self.assertEqual(evidence.status_code,200)
            self.assertTrue(b"".join(evidence.streaming_content).startswith(b"\x89PNG"))
        self.assertEqual(self.client.get("/api/v1/events/frequencies/").json()["total"],2)
        result = self.client.get(f"/api/v1/analysis/sessions/{identity}/result/")
        self.assertEqual(result.status_code,200)
        result.close()

    def test_http_failure_completes_analysis_but_is_not_saved_then_replay_recovers(self):
        with override_settings(OPERIX_EVENT_API_BASE_URL="http://127.0.0.1:1/api/v1"):
            identity = self.create()
            data = self.run_analysis(identity)
        self.assertEqual(data["state"], "completed", data)
        self.assertEqual(data["persistence"]["state"], "failed")
        self.assertEqual(Event.objects.count(), 0)
        recovered = self.client.post(f"/api/v1/analysis/sessions/{identity}/persistence/retry/")
        self.assertEqual(recovered.status_code, 200, recovered.data)
        self.assertEqual(recovered.data["persistence"]["saved"], 2)
        again = self.client.post(f"/api/v1/analysis/sessions/{identity}/persistence/retry/")
        self.assertEqual(again.data["persistence"]["saved"], 2)
        self.assertEqual(Event.objects.count(), 2)


class PersistenceFailureStatusTests(SimpleTestCase):
    def setUp(self):
        from uuid import uuid4
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        session_dir = root / "session"
        session_dir.mkdir()
        self.session = sessions.AnalysisSession(uuid4(), session_dir, "TEST_DATA.mp4", "A",
            session_dir / "input.mp4", "0" * 64, 0, "manual", None, {}, state="completed")
        self.session.active_config = {"profile": "A", "zone": {}}
        (session_dir / "annotated.mp4").write_bytes(b"TEST_DATA")
        self.session.outbox_directory = root / "outbox"
        self.session.outbox_directory.mkdir()
        registry = patch.dict(sessions._sessions, {self.session.id: self.session}, clear=True)
        registry.start()
        self.addCleanup(registry.stop)
        self.client = APIClient()
        self.url = f"/api/v1/analysis/sessions/{self.session.id}/persistence/retry/"

    @override_settings(EVENT_POST_ENABLED=True)
    def test_invalid_replay_output_is_controlled_without_false_success(self):
        from unittest.mock import Mock
        for text in ("invalid", "[]", '{"state":"saved"}', '{"state":"saved","candidates":2,"saved":1,"failed":0}'):
            with self.subTest(output=text), patch("apps.analysis.views.subprocess.run", return_value=Mock(stdout=text, returncode=0)):
                response = self.client.post(self.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["state"], "completed")
                self.assertEqual(response.data["persistence"]["state"], "failed")

    @override_settings(EVENT_POST_ENABLED=True)
    def test_timeout_is_controlled_and_retains_outbox(self):
        with patch("apps.analysis.views.subprocess.run", side_effect=subprocess.TimeoutExpired("fixture", 120)):
            response = self.client.post(self.url)
        self.assertEqual(response.data["persistence"]["state"], "failed")
        self.assertTrue(self.session.outbox_directory.exists())

    @override_settings(EVENT_POST_ENABLED=False)
    def test_disabled_post_blocks_replay(self):
        self.assertEqual(self.client.post(self.url).status_code, 403)
