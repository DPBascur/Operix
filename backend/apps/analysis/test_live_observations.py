import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from config.access import VIEWER_GROUP
from .cameras import playback_clock_id


class CameraObservationTests(APITestCase):
    endpoint = "/api/v1/analysis/cameras/lab-cam-01/live/observations/"

    def setUp(self):
        env = patch.dict(os.environ, {
            "OPERIX_CAMERA_LAB_ENABLED": "1",
            "OPERIX_CAMERA_LAB_LIVE_ENABLED": "1",
            "OPERIX_CAMERA_LAB_CONTROL_DIR": "/private/lab",
        })
        env.start()
        self.addCleanup(env.stop)
        self.admin = get_user_model().objects.create(username="overlay-admin", is_superuser=True)

    def test_requires_authorized_session(self):
        self.assertEqual(self.client.get(self.endpoint).status_code, 401)
        viewer = get_user_model().objects.create(username="overlay-viewer")
        viewer.groups.add(Group.objects.get_or_create(name=VIEWER_GROUP)[0])
        self.client.force_authenticate(viewer)
        self.assertEqual(self.client.get(self.endpoint).status_code, 403)

    def test_observations_belong_to_the_active_run_and_expire(self):
        self.client.force_authenticate(self.admin)
        run = SimpleNamespace(pk=uuid4(), active=True, managed=True)
        with (TemporaryDirectory() as directory,
              patch("apps.analysis.live_observations.last_run", return_value=run),
              patch("apps.analysis.live_observations.run_dir", return_value=Path(directory))):
            file = Path(directory) / "overlay.json"
            payload = {"run_id": str(run.pk), "items": [{"index": 12, "epoch": 2}]}
            file.write_text(json.dumps(payload))
            result = self.client.get(self.endpoint)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), payload)
            self.assertIn("no-store", result["Cache-Control"])
            run.active = False
            self.assertEqual(self.client.get(self.endpoint).status_code, 204)
            run.active = True
            os.utime(file, (0, 0))
            self.assertEqual(self.client.get(self.endpoint).status_code, 204)
            file.write_text(json.dumps({**payload, "run_id": str(uuid4())}))
            self.assertEqual(self.client.get(self.endpoint).status_code, 204)
            file.write_bytes(b" " * (512 * 1024 + 1))
            self.assertEqual(self.client.get(self.endpoint).status_code, 204)

    def test_clocked_endpoint_rejects_marks_from_a_different_playback(self):
        self.client.force_authenticate(self.admin)
        token = uuid4().hex
        run = SimpleNamespace(pk=uuid4(), active=True, managed=True, playback={"token": token})
        with (TemporaryDirectory() as directory,
              patch.dict(os.environ, {"OPERIX_CAMERA_LAB_FRAME_CLOCK": "1"}),
              patch("apps.analysis.live_observations.last_run", return_value=run),
              patch("apps.analysis.live_observations.run_dir", return_value=Path(directory))):
            file = Path(directory) / "overlay.json"
            payload = {"run_id": str(run.pk), "items": [], "stream_id": "a" * 32}
            file.write_text(json.dumps(payload))
            self.assertEqual(self.client.get(self.endpoint).status_code, 204)
            file.write_text(json.dumps({**payload, "stream_id": playback_clock_id(token)}))
            result = self.client.get(self.endpoint)
            self.assertEqual(result.status_code, 200)
            self.assertNotIn(token.encode(), result.content)
