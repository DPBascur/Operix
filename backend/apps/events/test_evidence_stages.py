from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils.timezone import now
from rest_framework.test import APIClient, APITestCase

from apps.analysis.cameras import status_for
from apps.analysis.models import AnalysisRunSnapshot, CameraRun
from config.test_clients import administrator_client

from .models import Event
from .test_pair_events import pair_payload
from .tests import sample_png


@override_settings(EVENT_POST_ENABLED=True)
class EventEvidenceStagesTests(APITestCase):
    def setUp(self):
        media = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=media))
        self.media = Path(media)
        self.reader = administrator_client()
        self.worker = APIClient()
        self.worker.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.OPERIX_EVENT_PUBLISH_TOKEN}")
        self.events = "/api/v1/events/"
        camera = "lab-cam-01"
        instant = now().isoformat()
        snapshot = AnalysisRunSnapshot.objects.create(
            id=uuid4(), source_sha256="a" * 64, profile="A", configuration={"view_id": camera},
            config_sha256="b" * 64,
        )
        self.run = CameraRun.objects.create(snapshot=snapshot, camera_id=camera, provenance={"sha256": "c" * 64})
        self.payload = pair_payload() | {
            "analysis_run_id": str(self.run.pk), "view_id": camera, "evidence_pending": True,
            "source": {"kind": "lab", "camera_id": camera, "video_sha256": "c" * 64,
                       "config_sha256": snapshot.config_sha256, "spatial_configuration": snapshot.configuration,
                       "timestamp_basis": "LAB_RECEPTION_UTC",
                       "capture": {"received_at": instant, "processed_at": instant,
                                   "source_pts_s": None, "time_basis": "local_arrival"}},
        }

    def register(self):
        response = self.worker.post(self.events, self.payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["evidence_status"], "pending")
        return f"{self.events}{response.data['id']}/"

    def upload(self, client, detail):
        return client.post(detail + "evidence/", {
            "frame_index": self.payload["frame_index"], "video_timestamp_s": self.payload["video_timestamp_s"],
            "image": SimpleUploadedFile("frame.png", sample_png(), content_type="image/png"),
        }, format="multipart")

    def test_event_visible_before_evidence_and_retries_preserve_identity_and_artifacts(self):
        self.assertEqual(self.client.post(self.events, self.payload, format="json").status_code, 403)
        detail = self.register()
        self.assertEqual(self.reader.get(detail).data["evidence_status"], "pending")
        self.assertEqual(self.reader.get(detail + "evidence/").status_code, 404)
        self.assertEqual(self.client.get(detail).status_code, 401)
        self.assertEqual(self.upload(self.client, detail).status_code, 403)
        self.assertEqual(self.reader.post(detail + "evidence-status/", {}).status_code, 403)

        self.assertEqual(self.upload(self.worker, detail).status_code, 201)
        self.assertEqual(self.upload(self.worker, detail).status_code, 200)
        self.assertEqual(len(list(self.media.rglob("*.png"))), 1)
        self.assertEqual(self.reader.get(detail).data["evidence_status"], "pending")
        for _ in range(2):
            self.assertEqual(self.worker.post(detail + "evidence-status/", {}, format="json").status_code, 204)
        self.assertEqual(self.reader.get(detail).data["evidence_status"], "partial")
        retry = self.worker.post(self.events, self.payload, format="json")
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data["evidence_status"], "partial")
        self.assertEqual(Event.objects.count(), 1)
        with patch("apps.events.views.clip_info", return_value={"url": "clip"}):
            self.assertEqual(self.reader.get(detail).data["evidence_status"], "ready")

    def test_publisher_claim_does_not_create_evidence(self):
        detail = self.register()
        report = self.worker.post(detail + "evidence-status/", {"png": "ready", "clip": "ready"}, format="json")
        self.assertEqual(report.status_code, 204)
        self.assertEqual(self.reader.get(detail).data["evidence_status"], "failed")
        self.assertEqual(self.reader.get(detail + "evidence/").status_code, 404)

    def test_abandoned_publication_expires_and_run_recovery_seals_stage(self):
        detail = self.register()
        Event.objects.update(created_at=now() - timedelta(minutes=6))
        self.assertEqual(self.reader.get(detail).data["evidence_status"], "failed")
        status_for(self.run)
        self.assertEqual(Event.objects.get().evidence_stage, Event.EvidenceStage.FINISHED)

    def test_historical_and_offline_events_keep_previous_contract(self):
        response = self.worker.post(self.events, pair_payload() | {"evidence_pending": True}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.worker.post(self.events, pair_payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["evidence_status"])
        response = self.worker.post(f"{self.events}{response.data['id']}/evidence-status/", {}, format="json")
        self.assertEqual(response.status_code, 404)
