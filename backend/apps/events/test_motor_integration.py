"""RF-06/RNF-01: Motor real, HTTP y PostgreSQL; percepción sintética, sin pesos."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from uuid import uuid4

from django.db import connection
from django.test import LiveServerTestCase, override_settings
from rest_framework.test import APIClient

from .models import Event


MOTOR_FIXTURE = r'''
import json, sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
import cv2
import numpy as np
from operix_engine.detection import BoundingBox, Detection
from operix_engine.event_publishing import EventContext, HttpEventSink
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.tracking import Track
from operix_engine.video_event_pipeline import run_video_event_pipeline

video, url, run = Path(sys.argv[1]), sys.argv[2], UUID(sys.argv[3])
fps, duration = float(sys.argv[4]), float(sys.argv[5])
if not video.exists():
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), fps, (200, 100))
    if not writer.isOpened(): raise RuntimeError("Fixture MJPG no disponible")
    try:
        for i in range(4): writer.write(np.full((100, 200, 3), (20, 80, 100+i), np.uint8))
    finally: writer.release()
box = BoundingBox(40, 30, 60, 70)
class Detector:
    def detect(self, frame): return (Detection(0, "person", .9, box),)
class Tracker:
    def update(self, detections): return (Track(7, 0, "person", .9, box),)
zone = Zone("TEST_DATA_ZONE", "Zona sintética", ((.1,.1),(.9,.1),(.9,.9),(.1,.9)))
rule = RuleConfig("TEST_DATA_RULE", 1, True, {
    "kind":"zone_dwell", "class_name":"person", "zone_id":zone.zone_id, "min_duration_s":duration})
config = OperationalConfig(1, "TEST_DATA_VIEW", (zone,), (rule,))
context = EventContext(run, config.view_id, datetime(2026,10,23,12,tzinfo=timezone.utc))
result = run_video_event_pipeline(video, detector=Detector(), tracker=Tracker(),
    config=config, sink=HttpEventSink(url), context=context)
print(json.dumps(result, allow_nan=False))
'''


@override_settings(EVENT_POST_ENABLED=True, ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"])
class MotorPersistenceIntegrationTests(LiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = Path(__file__).resolve().parents[3]
        cls.python = Path(os.environ.get("OPERIX_TEST_ENGINE_PYTHON", str(
            cls.repository / "engine/.venv/Scripts/python.exe"
        )))
        if not cls.python.is_file():
            raise unittest.SkipTest("Integración requiere el Python del Motor instalado")
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("Integración requiere PostgreSQL real")
        super().setUpClass()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="operix-test-data-")
        self.addCleanup(self.temporary.cleanup)
        self.media = override_settings(MEDIA_ROOT=str(Path(self.temporary.name) / "media"))
        self.media.enable()
        self.addCleanup(self.media.disable)

    def test_pair_candidates_motor_outbox_http_database_evidence_and_mixed_query(self):
        script = r'''
import json, sys
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID
import cv2, numpy as np
from operix_engine.detection import BoundingBox
from operix_engine.tracking import Track
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.rules import RuleEngine
from operix_engine.event_publishing import EventContext, HttpEventSink
from operix_engine.event_outbox import EventOutbox
root, url, run = Path(sys.argv[1]), sys.argv[2], UUID(sys.argv[3])
zone = Zone('TEST_DATA_ZONE', 'Fixture', ((0,0),(1,0),(1,1),(0,1)))
rule = RuleConfig('TEST_DATA_PAIR',1,True,{'kind':'person_forklift_proximity',
 'zone_id':zone.zone_id,'person_class':'person','forklift_class':'forklift',
 'max_distance':.25,'minimum_duration_seconds':1.0})
engine=RuleEngine(OperationalConfig(1,'TEST_DATA_VIEW',(zone,),(rule,)))
analyzer=SpatiotemporalAnalyzer(width=200,height=100,fps=1,zones=(zone,))
tracks=(Track(1,0,'person',.9,BoundingBox(40,30,60,70)),
 Track(1,0,'forklift',.9,BoundingBox(50,30,70,70)),
 Track(2,0,'forklift',.9,BoundingBox(60,30,80,70)))
video=root/'pair.avi'; writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),1,(200,100))
assert writer.isOpened()
try:
 for _ in range(4): writer.write(np.full((100,200,3),80,np.uint8))
finally: writer.release()
capture=cv2.VideoCapture(str(video)); outbox=EventOutbox(root/'outbox',HttpEventSink(url))
context=EventContext(run,'TEST_DATA_VIEW',datetime(2026,10,24,12,tzinfo=timezone.utc),{'kind':'controlled_fixture'})
try:
 for i in range(4):
  ok,frame=capture.read(); assert ok
  result=engine.evaluate(analyzer.update(i,tracks))
  success,png=cv2.imencode('.png',frame); assert success
  outbox.enqueue(result.candidates,context,png.tobytes())
finally: capture.release()
print(json.dumps(outbox.replay()))
'''
        run = uuid4()
        command = [str(self.python), "-B", "-c", script, self.temporary.name,
                   self.live_server_url + "/api/v1", str(run)]
        process = subprocess.run(command, cwd=self.repository, capture_output=True, text=True, timeout=45)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["saved"], 2)
        self.assertEqual(Event.objects.count(), 2)
        ids = set(Event.objects.values_list("id", flat=True))
        # Reenvío del mismo run desde otro proceso: la DB conserva exactamente las identidades.
        again = subprocess.run(command, cwd=self.repository, capture_output=True, text=True, timeout=45)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(set(Event.objects.values_list("id", flat=True)), ids)
        for event in Event.objects.all():
            response = APIClient().get(f"/api/v1/events/{event.id}/evidence/")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(b"".join(response.streaming_content).startswith(b"\x89PNG"))
        filters = {"event_type": "person_forklift_proximity"}
        self.assertEqual(len(APIClient().get("/api/v1/events/", filters).json()), 2)
        self.assertEqual(APIClient().get("/api/v1/events/frequencies/", filters).json()["total"], 2)

    def execute_motor(self, run, *, fps=2, duration=1):
        process = subprocess.run([
            str(self.python), "-B", "-c", MOTOR_FIXTURE,
            str(Path(self.temporary.name) / "controlled.avi"),
            self.live_server_url + "/api/v1", str(run), str(fps), str(duration),
        ], cwd=self.repository, capture_output=True, text=True, timeout=45)
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def test_fractional_frame_duration_survives_http_and_postgresql(self):
        result = self.execute_motor(uuid4(), fps=30, duration=1 / 30)
        self.assertEqual(result["published_count"], 1)
        event = Event.objects.get()
        self.assertEqual(event.frame_index, 1)
        self.assertLess(abs(float(event.observed_dwell_time_s) - 1 / 30), 1e-9)
        self.assertEqual(event.rule_parameters["min_duration_s"], 1 / 30)

    def test_motor_recovers_from_one_http_503_without_duplicate_event(self):
        from unittest.mock import patch
        from rest_framework.response import Response
        from .views import EventListCreateView
        original = EventListCreateView.create
        calls = []

        def transient(view, request, *args, **kwargs):
            calls.append(request.data["analysis_run_id"])
            if len(calls) == 1:
                return Response({"detail": "TEST_DATA transient failure"}, status=503)
            return original(view, request, *args, **kwargs)

        with patch.object(EventListCreateView, "create", transient):
            result = self.execute_motor(uuid4())
        self.assertEqual(result["published_count"], 1)
        self.assertEqual(result["publications"][0]["publish_attempts"], 2)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(Event.objects.count(), 1)
        self.assertTrue(Event.objects.get().evidence_image)

    def test_video_candidate_http_postgresql_evidence_query_and_indicator(self):
        run = uuid4()
        first = self.execute_motor(run)
        repeated = self.execute_motor(run)
        self.assertEqual(first["processed_frames"], 4)
        self.assertEqual(first["candidate_count"], 1)
        self.assertEqual(first["published_count"], 1)
        self.assertEqual(repeated["duplicate_event_count"], 1)
        self.assertEqual(Event.objects.count(), 1)
        event = Event.objects.get()
        candidate = first["publications"][0]["candidate"]
        self.assertEqual(event.analysis_run_id, run)
        self.assertEqual((event.rule_id, event.rule_version), ("TEST_DATA_RULE", 1))
        self.assertEqual(event.rule_parameters, candidate["parameters"])
        self.assertEqual((event.track_id, event.zone_id), (7, "TEST_DATA_ZONE"))
        self.assertEqual((event.frame_index, float(event.video_timestamp_s)), (2, 1.0))
        self.assertEqual(float(event.observed_dwell_time_s), candidate["observed_dwell_time_s"])
        api = APIClient()
        detail = api.get(f"/api/v1/events/{event.id}/").json()
        image = api.get(detail["evidence_url"])
        try:
            content = b"".join(image.streaming_content)
        finally:
            image.close()
        self.assertEqual(hashlib.sha256(content).hexdigest(), first["publications"][0]["evidence_png_sha256"])
        filters = {"occurred_after": "2026-10-23T12:00:01Z",
                   "occurred_before": "2026-10-23T12:00:01Z", "event_type": "zone_dwell"}
        listed = api.get("/api/v1/events/", filters).json()
        frequency = api.get("/api/v1/events/frequencies/", filters).json()
        self.assertEqual([x["id"] for x in listed], [str(event.id)])
        self.assertEqual(frequency["total"], len(listed))
        self.assertEqual(frequency["by_period"], [{"date": "2026-10-23", "count": 1}])
        other = self.execute_motor(uuid4())
        self.assertEqual(other["created_event_count"], 1)
        self.assertEqual(Event.objects.count(), 2)

        # Resumen opcional fuera de Git; no conserva imágenes ni filas de DB.
        output = os.environ.get("OPERIX_VALIDATION_OUTPUT_DIR")
        if output:
            folder = Path(output).resolve()
            if folder.is_relative_to(self.repository):
                raise ValueError("La evidencia de ejecución debe quedar fuera de Git")
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "motor-http-postgresql-smoke.json").write_text(json.dumps({
                "perception": "SYNTHETIC_FIXTURE_NOT_MODEL_EVALUATION",
                "database": connection.vendor, "first": first, "retry": repeated,
                "independent_run": other, "evidence_sha256_verified": True,
                "indicator_reconciled": True, "test_rows": 2,
                "scope": "Django isolated test database; destroyed by test runner",
            }, indent=2), encoding="utf-8")
