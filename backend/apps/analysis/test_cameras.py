import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from .camera_registry import approved_destination
from .cameras import default_document, reap_run, run_dir, status_for
from .models import AnalysisRunSnapshot, CameraRun
from .camera_registry import inventory


class CameraLabTests(APITestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        manifest = Path(temporary.name, "manifest.json")
        manifest.write_text(json.dumps({"clips": [{"camera_id": "lab-cam-01",
                                                  "filename": "lab-cam-01.mp4", "sha256": "a" * 64}]}))
        env = patch.dict(os.environ, {"OPERIX_CAMERA_LAB_ENABLED": "1", "OPERIX_CAMERA_LAB_MANIFEST": str(manifest),
                                      "OPERIX_CAMERA_LAB_CONTROL_DIR": ""})
        env.start()
        self.addCleanup(env.stop)
        user = get_user_model().objects.create(username="lab-admin", is_superuser=True)
        self.admin = APIClient()
        self.admin.force_authenticate(user=user)
        self.endpoint = "/api/v1/analysis/cameras/"
        self.camera = self.endpoint + "lab-cam-01/"

    def test_inventory_does_not_disclose_host_and_anonymous_cannot_read(self):
        self.assertEqual(self.client.get(self.endpoint).status_code, 401)
        result = self.admin.get(self.endpoint)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["cameras"][0]["status"], "stopped")
        self.assertEqual(result.data["cameras"][0]["provenance"]["sha256"], "a" * 64)
        self.assertNotIn("rtsp://", result.content.decode())
        self.assertEqual(self.admin.get(self.camera + "preview/").status_code, 404)

    def test_cannot_supply_network_destination_and_invalid_camera_is_not_found(self):
        self.assertEqual(self.admin.post(self.camera + "start/", {"url": "http://localhost"}, format="json").status_code, 400)
        self.assertEqual(self.admin.get(self.endpoint + "arbitrary/").status_code, 404)
        with patch.dict(os.environ, {"OPERIX_LAB_CAM_01_RTSP_URL": "rtsp://10.10.2.7/live",
                                    "OPERIX_LAB_CAM_01_ALLOWED_IP": "10.10.2.8"}):
            with self.assertRaises(ValueError):
                approved_destination("lab-cam-01")

    def test_shared_broker_unavailable_leaves_no_camera_run(self):
        with (self.settings(EVENT_POST_ENABLED=True),
              patch.dict(os.environ, {"OPERIX_RTSP_INFERENCE_SOCKET": "/private/worker.sock"}),
              patch("apps.analysis.cameras.socket.socket") as socket_factory,
              patch("apps.analysis.cameras.subprocess.Popen") as process):
            socket_factory.return_value.__enter__.return_value.connect.side_effect = ConnectionRefusedError
            response = self.admin.post(self.camera + "start/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("inferencia compartida", response.data["detail"])
        self.assertFalse(CameraRun.objects.exists())
        process.assert_not_called()

    def test_cannot_declare_a_category_for_every_object_in_an_rtsp_camera(self):
        camera = inventory()["lab-cam-01"]
        doc = default_document(camera)
        doc["equipment_profile"] = {
            "category": "COUNTERBALANCE_FORKLIFT", "source_sha256": camera.spatial_key,
            "authority_reference": "pilot-01",
        }
        saved = self.admin.put(self.camera, {"revision": 0, "document": doc}, format="json")
        self.assertEqual(saved.status_code, 400)
        self.assertEqual(self.admin.get(self.camera).data["revision"], 0)

    def test_camera_config_is_isolated_and_optimistically_versioned(self):
        doc = default_document(inventory()["lab-cam-01"])
        doc["zones"][0]["name"] = "Pasillo uno"
        with patch("apps.analysis.cameras.validate_spatial", side_effect=lambda document, *_: document):
            saved = self.admin.put(self.camera, {"revision": 0, "document": doc}, format="json")
            self.assertEqual(saved.status_code, 200, saved.content)
            self.assertEqual(saved.data["revision"], 1)
            self.assertEqual(saved.data["configuration"]["rules"][0]["version"], 2)
            conflict = self.admin.put(self.camera, {"revision": 0, "document": doc}, format="json")
            self.assertEqual(conflict.status_code, 409)
            other = self.admin.put(self.endpoint + "lab-cam-02/", {"revision": 0, "document": doc}, format="json")
            self.assertEqual(other.status_code, 400)


    def test_exited_worker_seals_run_without_an_http_poll(self):
        camera = inventory()["lab-cam-01"]
        snapshot = AnalysisRunSnapshot.objects.create(
            pk=uuid4(), source_sha256=camera.spatial_key, profile=camera.profile,
            configuration=default_document(camera), config_sha256="a" * 64,
        )
        run = CameraRun.objects.create(snapshot=snapshot, camera_id=camera.id)
        process = Mock()
        process.poll.return_value = 0
        with patch("apps.analysis.cameras.close_old_connections"), patch.dict(
            "apps.analysis.cameras._processes", {run.pk: process}
        ):
            reap_run(run.pk, process)
        run.refresh_from_db()
        self.assertFalse(run.active)
        self.assertEqual(run.terminal_state, "error")
        self.assertIsNotNone(run.ended_at)

    def test_reaper_discards_only_terminal_managed_previews(self):
        camera = inventory()["lab-cam-01"]
        with TemporaryDirectory() as root, self.settings(MEDIA_ROOT=root):
            for managed in (True, False):
                with self.subTest(managed=managed):
                    snapshot = AnalysisRunSnapshot.objects.create(
                        pk=uuid4(), source_sha256=camera.spatial_key, profile=camera.profile,
                        configuration=default_document(camera), config_sha256="a" * 64,
                    )
                    run = CameraRun.objects.create(snapshot=snapshot, camera_id=camera.id, managed=managed)
                    folder = run_dir(run.pk)
                    folder.mkdir(parents=True)
                    preview = folder / "preview.jpg"
                    preview.write_bytes(b"preview")
                    (folder / "context.json").write_text("{}")
                    (folder / "evidence.jpg").write_bytes(b"evidence")
                    process = Mock()
                    process.poll.return_value = None
                    with patch("apps.analysis.cameras.close_old_connections"), patch.dict(
                        "apps.analysis.cameras._processes", {run.pk: process}
                    ):
                        status_for(run)
                        self.assertTrue(preview.exists())
                        process.poll.return_value = 0
                        reap_run(run.pk, process)
                    self.assertEqual(preview.exists(), not managed)
                    self.assertTrue((folder / "context.json").exists())
                    self.assertTrue((folder / "evidence.jpg").exists())
                    self.assertTrue(AnalysisRunSnapshot.objects.filter(pk=run.pk).exists())
