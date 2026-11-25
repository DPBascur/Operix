import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from .sessions import INDUSTRIAL_DEMOS, profile_catalog


class AuthorizedMediaTests(APITestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.video = self.directory / "sample.mp4"
        self.video.write_bytes(b"0123456789")
        self.digest = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.manifest = self.directory / "catalog.json"
        self.manifest.write_text(json.dumps({"clips": [{
            "id": "recorded", "filename": self.video.name, "sha256": self.digest,
            "footage": "real industrial CCTV", "license": "CC BY 4.0", "duration_s": 10, "fps": 15,
        }]}))
        self.enterContext(patch.dict(os.environ, {
            "OPERIX_CAMERA_LAB_ENABLED": "1", "OPERIX_CAMERA_LAB_MANIFEST": str(self.manifest),
        }))
        self.enterContext(override_settings(MEDIA_ROOT=self.directory))
        self.admin = get_user_model().objects.create_user("media-admin", is_superuser=True)
        self.base = "/api/v1/analysis/camera-media/"

    def test_media_requires_administrator_and_matches_inventory(self):
        url = self.base + "recorded/video/"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_authenticate(get_user_model().objects.create_user("media-viewer"))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.admin)
        response = self.client.get(url, HTTP_RANGE="bytes=2-4")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b"".join(response.streaming_content), b"234")
        self.assertEqual(self.client.get(self.base + "missing/video/").status_code, 404)
        self.video.write_bytes(b"unexpected")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_thumbnail_reads_cached_image_for_the_verified_content(self):
        self.client.force_authenticate(self.admin)
        cache = self.directory / "lab-thumbnails-v1"
        cache.mkdir()
        (cache / f"{self.digest}.jpg").write_bytes(b"jpeg")
        response = self.client.get(self.base + "recorded/thumbnail/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(b"".join(response.streaming_content), b"jpeg")

    def test_industrial_release_rejects_unverified_media_without_legacy_fallback(self):
        video = self.directory / INDUSTRIAL_DEMOS["A"][1]
        video.write_bytes(b"unverified")
        with patch.dict(os.environ, {"OPERIX_INDUSTRIAL_DEMO_DIR": str(self.directory)}):
            self.assertIsNone(profile_catalog()[0]["default_demo_video"])
            with patch.dict(INDUSTRIAL_DEMOS, {"A": (
                INDUSTRIAL_DEMOS["A"][0], video.name, hashlib.sha256(video.read_bytes()).hexdigest(),
            )}):
                profile = profile_catalog()[0]
                self.assertEqual(profile["default_demo_video"]["id"], "cctv_proximidad")
                self.assertEqual(profile["configuration"]["rules"][0]["parameters"]["distance_unit"], "normalized")
