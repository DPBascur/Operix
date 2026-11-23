import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient, APITestCase

from config.access import SAFETY_GROUP
from . import lab_control
from .camera_registry import inventory
from .models import CameraLabControl


class ManagedLabTests(APITestCase):
    endpoint = "/api/v1/analysis/cameras/control/"

    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = self.root = Path(folder.name)
        (root / "sample.mp4").write_bytes(b"media fixture")
        source = {"id": "lab-cam-01", "filename": "sample.mp4", "average_fps": 24,
                  "footage": "real industrial CCTV", "sha256": hashlib.sha256(b"media fixture").hexdigest()}
        (root / "manifest.json").write_text(json.dumps({"source": {"license": "CC BY 4.0"}, "clips": [source]}))
        env = patch.dict(os.environ, {"OPERIX_CAMERA_LAB_ENABLED": "1", "OPERIX_CAMERA_LAB_CONTROL_DIR": str(root),
                                      "OPERIX_CAMERA_LAB_MANIFEST": str(root / "manifest.json")})
        env.start()
        self.addCleanup(env.stop)
        self.owner = get_user_model().objects.create(username="supervisor", is_superuser=True)
        self.admin = APIClient()
        self.admin.force_authenticate(user=self.owner)

    def test_configuration_is_admin_only_audited_and_rejects_arbitrary_destinations(self):
        self.assertEqual(self.client.get(self.endpoint).status_code, 401)
        lead = get_user_model().objects.create(username="reviewer")
        lead.groups.add(Group.objects.create(name=SAFETY_GROUP))
        self.client.force_authenticate(user=lead)
        self.assertEqual(self.client.patch(self.endpoint, {"enabled": True}, format="json").status_code, 403)
        with patch("apps.analysis.lab_control.rtsp_ready", return_value=False):
            response = self.admin.patch(self.endpoint, {"enabled": True, "cameras": {"lab-cam-02": False}}, format="json")
            self.assertEqual(response.status_code, 202, response.content)
            self.assertEqual(response.data["status"], "partial")
            self.assertEqual(self.admin.patch(self.endpoint, {"cameras": {"../../tmp": True}}, format="json").status_code, 400)
        self.assertEqual(CameraLabControl.objects.get().updated_by, self.owner)
        self.assertTrue(LogEntry.objects.filter(user=self.owner).exists())
        self.assertEqual(self.admin.post("/api/v1/analysis/cameras/lab-cam-01/start/", {}, format="json").status_code, 409)

    def test_reconcile_starts_configured_camera_and_stops_only_owned_runs(self):
        CameraLabControl.objects.create(pk=1, enabled=True, cameras={"lab-cam-02": False}, updated_by=self.owner)
        manual = SimpleNamespace(active=True, managed=False)
        managed = SimpleNamespace(active=True, managed=True)
        with (patch("apps.analysis.lab_control.scheduler_lock"),
              patch("apps.analysis.lab_control.last_run", side_effect=lambda id_, **_: None if id_.endswith("01") else manual),
              patch("apps.analysis.lab_control.status_for", return_value=("stopped", {}, None)),
              patch("apps.analysis.lab_control.rtsp_ready", return_value=True),
              patch("apps.analysis.lab_control.start_camera") as start,
              patch("apps.analysis.lab_control.stop_camera") as stop):
            lab_control.reconcile()
            start.assert_called_once()
            self.assertEqual(start.call_args.args[0].id, "lab-cam-01")
            self.assertEqual(start.call_args.kwargs, {"managed": True})
            self.assertTrue((self.root / "lab-cam-01.lease").is_file())
            stop.assert_not_called()

            CameraLabControl.objects.filter(pk=1).update(enabled=False)
            with patch("apps.analysis.lab_control.last_run", side_effect=[managed, manual]):
                lab_control.reconcile()
            stop.assert_called_once_with(managed)
            self.assertFalse((self.root / "lab-cam-01.lease").exists())

    def test_invalid_media_never_receives_a_lease(self):
        camera = inventory()["lab-cam-01"]
        (self.root / "sample.mp4").write_bytes(b"wrong digest")
        with self.assertRaisesRegex(ValueError, "inventario"):
            lab_control.approved_media(camera)

    def test_lab_trial_provenance_keeps_its_distinction_from_industrial_cctv(self):
        path = self.root / "manifest.json"
        document = json.loads(path.read_text())
        document["clips"][0]["footage"] = "real recorded logistics trial"
        path.write_text(json.dumps(document))
        camera = inventory()["lab-cam-01"]
        self.assertEqual(camera.provenance["footage"], "real recorded logistics trial")
        self.assertEqual(lab_control.approved_media(camera)[0], "sample.mp4")

    def test_live_camera_reports_the_run_snapshot_to_any_authorized_reviewer(self):
        rules = [{"rule_id": "effective-rule", "version": 2, "enabled": True}]
        policy = {"rule_set": {"name": "Assigned when started", "version": 2}}
        run = SimpleNamespace(pk=self.owner.pk, active=True, provenance={"filename": "started.mp4"}, snapshot=SimpleNamespace(
            configuration={"rules": rules}, policy=policy,
        ))
        with (patch("apps.analysis.cameras.last_run", return_value=run),
              patch("apps.analysis.cameras.status_for", return_value=("analyzing", {}, None)),
              patch("apps.analysis.cameras.calibration_issue", return_value=None)):
            response = self.admin.get("/api/v1/analysis/cameras/lab-cam-01/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["effective_rules"], rules)
        self.assertEqual(response.data["policy"], policy)
        self.assertEqual(response.data["provenance"]["filename"], "started.mp4")
        self.assertIsNone(response.data["preview_url"])

    def test_source_replacement_revokes_old_publisher_before_new_start(self):
        CameraLabControl.objects.create(pk=1, enabled=True, cameras={"lab-cam-02": False}, updated_by=self.owner)
        previous = SimpleNamespace(active=True, managed=True, provenance={"sha256": "0" * 64})
        lab_control.update_lease("lab-cam-01", ("previous.mp4", "0" * 64))
        with (patch("apps.analysis.lab_control.scheduler_lock"),
              patch("apps.analysis.lab_control.last_run", side_effect=lambda id_, **_: previous if id_.endswith("01") else None),
              patch("apps.analysis.lab_control.status_for", return_value=("stopped", {}, None)),
              patch("apps.analysis.lab_control.rtsp_ready", return_value=True) as ready,
              patch("apps.analysis.lab_control.start_camera") as start,
              patch("apps.analysis.lab_control.stop_camera") as stop):
            lab_control.reconcile()
            stop.assert_called_once_with(previous)
            self.assertFalse(lab_control.marker("lab-cam-01").exists())

            previous.active = False
            lab_control.reconcile()
            self.assertFalse(lab_control.marker("lab-cam-01").exists())
            start.assert_not_called()

            ready.return_value = False
            lab_control.reconcile()
            self.assertTrue(lab_control.marker("lab-cam-01").is_file())
            start.assert_not_called()

            ready.return_value = True
            lab_control.reconcile()
            start.assert_called_once()
