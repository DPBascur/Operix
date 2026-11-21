import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.events.test_pair_events import pair_payload

from .models import AnalysisRunSnapshot, CameraRevision, CameraRun


class PatternCalibrationTests(APITestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory())
        manifest = Path(root, "manifest.json")
        manifest.write_text(json.dumps({"clips": [
            {"camera_id": "lab-cam-01", "filename": "pattern.mp4", "sha256": "a" * 64},
        ]}), encoding="utf-8")
        self.enterContext(patch.dict(os.environ, {"OPERIX_CAMERA_LAB_ENABLED": "1",
                                                "OPERIX_CAMERA_LAB_MANIFEST": str(manifest)}))
        self.admin = APIClient()
        self.admin.force_authenticate(user=get_user_model().objects.create_superuser(username="calibration-test"))
        self.endpoint = "/api/v1/analysis/cameras/"
        self.camera = self.endpoint + "lab-cam-01/"

    def proposal(self, actor=None):
        layout = {"dictionary": "DICT_4X4_50", "provenance": "Plano sintético de prueba",
                  "markers": [{"id": i, "x_m": x, "y_m": y, "size_m": .5, "rotation_deg": 0}
                              for i, (x, y) in enumerate(((.5, .5), (4, .5), (.5, 4)))]}
        corners = {str(m["id"]): [[(m["x_m"] + dx*.5)/5,(m["y_m"] + dy*.5)/5]
                                    for dx,dy in ((0,0),(1,0),(1,1),(0,1))] for m in layout["markers"]}
        points = [p for quad in corners.values() for p in quad]
        report = {"status": "candidate", "width": 960, "height": 540, "marker_corners": corners,
                  "reference_marker_corners": corners, "quality": {}, "coverage": .4,
                  "image_points": points, "ground_points_m": [[5*x,5*y] for x,y in points],
                  "preview_jpeg": base64.b64encode(b"\xff\xd8\xfftest").decode()}
        with (patch("apps.analysis.calibration_views._detect", return_value=report),
              patch("apps.analysis.calibration_views._live_source", return_value={})):
            return (actor or self.admin).post(self.camera + "calibration/proposal/", {
                "layout": layout, "revision": 0,
            }, format="json")

    def confirm_body(self):
        response = self.proposal()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(response.data["preview_url"].startswith("data:image/jpeg;base64,"))
        return {"proposal_id": response.data["proposal_id"], "revision": 0,
                "ground_confirmed": True, "zones_reviewed": True,
                "control": {"image_points": [[.2,.3],[.4,.3]], "distance_m": 1,
                            "tolerance_m": .02, "provenance": "Segmento sintético independiente"}}

    def test_confirmation_uses_measured_control_and_preserves_revision(self):
        original = self.confirm_body()
        self.assertFalse(CameraRevision.objects.exists())
        route = self.camera + "calibration/confirm/"
        wrong = deepcopy(original)
        wrong["control"]["distance_m"] = 2
        refused = self.admin.post(route, wrong, format="json")
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertFalse(CameraRevision.objects.exists())
        accepted = self.admin.post(route, original, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        cfg = accepted.data["configuration"]["calibration"]
        self.assertAlmostEqual(cfg["pattern_evidence"]["control"]["observed_m"], 1)
        self.assertEqual(cfg["validity_policy"], "GROUND_PATTERN_CONTROL_HUMAN_CONFIRMED")
        self.assertEqual(cfg["version"], 1)
        self.assertEqual(self.admin.post(route, original, format="json").status_code, 409)
        self.assertEqual(CameraRevision.objects.count(), 1)

    def test_anonymous_forged_and_cross_camera_requests_are_rejected(self):
        body = self.confirm_body()
        route = self.camera + "calibration/confirm/"
        self.assertEqual(APIClient().post(route, body, format="json").status_code, 401)
        cross = self.endpoint + "lab-cam-02/calibration/confirm/"
        self.assertEqual(self.admin.post(cross, body, format="json").status_code, 400)
        self.assertEqual(self.admin.post(route, {**body, "proposal_id": body["proposal_id"] + "x"}, format="json").status_code, 400)
        self.assertFalse(CameraRevision.objects.exists())

    @override_settings(EVENT_POST_ENABLED=True)
    def test_camera_invalidated_by_worker_cannot_restart_on_same_calibration(self):
        response = self.admin.post(self.camera + "calibration/confirm/", self.confirm_body(), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        config = response.data["configuration"]
        snapshot = AnalysisRunSnapshot.objects.create(
            id=uuid4(), source_sha256=config["calibration"]["source_sha256"],
            profile="A", configuration=config, config_sha256="a" * 64,
        )
        CameraRun.objects.create(snapshot=snapshot, camera_id="lab-cam-01", active=False,
                                 terminal_state="stopped", metrics={"framing": {"state": "INVALID"}})
        self.assertTrue(self.admin.get(self.camera).data["calibration_requires_reconfirmation"])
        with (patch("apps.analysis.cameras.camera_worker_destination", return_value=("10.0.0.2", "rtsp://10.0.0.2/live")),
              patch("apps.analysis.cameras.subprocess") as worker):
            refused = self.admin.post(self.camera + "start/", {}, format="json")
        self.assertEqual(refused.status_code, 409, refused.data)
        self.assertIn("invalidó", str(refused.data["detail"]))
        worker.Popen.assert_not_called()

    @override_settings(EVENT_POST_ENABLED=True)
    def test_metric_event_must_use_the_confirmed_calibration_in_its_camera_run(self):
        response = self.admin.post(self.camera + "calibration/confirm/", self.confirm_body(), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        config = response.data["configuration"]
        calibration = config["calibration"]
        snapshot = AnalysisRunSnapshot.objects.create(
            id=uuid4(), source_sha256=calibration["source_sha256"], profile="A",
            configuration=config, config_sha256="b" * 64,
        )
        camera_id = "lab-cam-01"
        CameraRun.objects.create(snapshot=snapshot, camera_id=camera_id, provenance={"sha256": "a" * 64})
        payload = pair_payload()
        instant = payload["occurred_at"]
        payload.update(analysis_run_id=str(snapshot.pk), view_id=camera_id, zone_id="frame", source={
            "kind": "lab", "camera_id": camera_id, "video_sha256": "a" * 64,
            "config_sha256": snapshot.config_sha256, "spatial_configuration": config,
            "timestamp_basis": "LAB_RECEPTION_UTC", "capture": {
                "received_at": instant, "processed_at": instant, "source_pts_s": 2.0, "time_basis": "source_pts",
            },
        })
        payload["rule_parameters"].update(distance_unit="m", max_distance=2.0, zone_id="frame")
        payload["observations"]["ground"] = {"method": calibration["method"], "units": "m", "distance": 1.0,
            "person_anchor": [.2,.3], "equipment_target": [.4,.3], "calibration": calibration}
        publisher = APIClient()
        publisher.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.OPERIX_EVENT_PUBLISH_TOKEN}")
        url = "/api/v1/events/"
        persisted = publisher.post(url, payload, format="json")
        self.assertEqual(persisted.status_code, 201, persisted.data)
        altered = deepcopy(payload)
        replaced = deepcopy(calibration)
        altered["observations"]["ground"]["calibration"] = replaced
        replaced.pop("sha256")
        replaced["version"] += 1
        replaced["sha256"] = hashlib.sha256(json.dumps(replaced, sort_keys=True, allow_nan=False).encode()).hexdigest()
        rejected = publisher.post(url, altered, format="json")
        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.assertIn("calibración confirmada", str(rejected.data))
