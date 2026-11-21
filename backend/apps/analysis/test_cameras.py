import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from .camera_registry import approved_destination
from .cameras import default_document
from .camera_registry import inventory


class CameraLabTests(APITestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        manifest = Path(temporary.name, "manifest.json")
        manifest.write_text(json.dumps({"clips": [{"camera_id": "lab-cam-01",
                                                  "filename": "lab-cam-01.mp4", "sha256": "a" * 64}]}))
        env = patch.dict(os.environ, {"OPERIX_CAMERA_LAB_ENABLED": "1", "OPERIX_CAMERA_LAB_MANIFEST": str(manifest)})
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
