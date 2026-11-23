import os
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time_ns
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from config.access import VIEWER_GROUP
from .lab_control import media_eligible


class LiveVideoTests(APITestCase):
    endpoint = "/api/v1/analysis/cameras/lab-cam-01/live/"

    def setUp(self):
        env = patch.dict(os.environ, {"OPERIX_CAMERA_LAB_ENABLED": "1",
                                     "OPERIX_CAMERA_LAB_LIVE_ENABLED": "1",
                                     "OPERIX_CAMERA_LAB_CONTROL_DIR": "/private/lab"})
        env.start()
        self.addCleanup(env.stop)
        self.admin = get_user_model().objects.create(username="live-admin", is_superuser=True)

    @patch("apps.analysis.live_video.http.client.HTTPConnection")
    def test_media_requires_session_and_analysis_permission(self, upstream):
        self.assertEqual(self.client.get(self.endpoint + "index.m3u8").status_code, 401)
        viewer = get_user_model().objects.create(username="live-viewer")
        viewer.groups.add(Group.objects.get_or_create(name=VIEWER_GROUP)[0])
        self.client.force_authenticate(viewer)
        self.assertEqual(self.client.get(self.endpoint + "part.mp4/").status_code, 403)
        upstream.assert_not_called()

    @patch("apps.analysis.live_video.http.client.HTTPConnection")
    def test_allowed_asset_and_bounded_hls_query_pass_to_the_fixed_relay(self, upstream):
        self.client.force_authenticate(self.admin)
        relay = upstream.return_value
        part = relay.getresponse.return_value.__enter__.return_value
        part.status = 200
        part.read.return_value = b"#EXTM3U\nstream.m3u8\n"
        part.headers = Message()
        part.headers["Set-Cookie"] = "hlsSession=aa112233-4455-6677-8899-aabbccddeeff; Secure; HttpOnly"
        response = self.client.get(self.endpoint + "index.m3u8/?_HLS_msn=23&_HLS_part=3&foo=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.apple.mpegurl")
        self.assertIn("private", response["Cache-Control"])
        self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(response.content, part.read.return_value)
        upstream.assert_called_once_with("mediamtx", port=8888, timeout=4)
        relay.request.assert_called_once_with("GET", "/lab-cam-01/index.m3u8?cookieCheck=1&_HLS_msn=23&_HLS_part=3",
                                             headers={"Cookie": "cookieCheck=1"})
        self.assertFalse(response.cookies)
        relay.close.assert_called_once()

    @patch("apps.analysis.live_video.http.client.HTTPConnection")
    def test_unapproved_media_and_physical_sources_are_not_relayed(self, upstream):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.endpoint + "index.html").status_code, 404)
        with patch.dict(os.environ, {"OPERIX_LAB_CAM_01_RTSP_URL": "rtsp://10.70.3.4/live",
                                     "OPERIX_LAB_CAM_01_ALLOWED_IP": "10.70.3.4"}):
            self.assertEqual(self.client.get(self.endpoint + "index.m3u8").status_code, 404)
        upstream.assert_not_called()

    @patch("apps.analysis.live_video.http.client.HTTPConnection")
    def test_unavailable_relay_returns_transient_error(self, upstream):
        self.client.force_authenticate(self.admin)
        upstream.return_value.getresponse.side_effect = TimeoutError
        self.assertEqual(self.client.get(self.endpoint + "index.m3u8").status_code, 503)
        upstream.return_value.close.assert_called_once()

    def test_synthetic_input_is_opt_in_and_does_not_claim_real_footage(self):
        source = {"filename": "bench.mp4", "sha256": "a" * 64, "fps": 30, "real": False,
                  "footage": "synthetic validation video", "license": "Local fixture"}
        with patch.dict(os.environ, {"OPERIX_CAMERA_LAB_ALLOW_SYNTHETIC": "0"}):
            self.assertFalse(media_eligible(source, 30))
        with patch.dict(os.environ, {"OPERIX_CAMERA_LAB_ALLOW_SYNTHETIC": "1"}):
            self.assertTrue(media_eligible(source, 30))
            self.assertFalse(media_eligible(source, 60))

    def test_annotated_image_reports_exact_file_age_and_rejects_expired_frame(self):
        self.client.force_authenticate(self.admin)
        route = "/api/v1/analysis/cameras/lab-cam-01/preview/"
        with TemporaryDirectory() as media:
            file = Path(media) / "preview.jpg"
            file.write_bytes(b"recent JPEG")
            measured = time_ns() - 200_000_000
            os.utime(file, ns=(measured, measured))
            status = ("analyzing", {}, {"metrics": {"preview_clock_basis": "local_receive_mtime"}})
            with (patch("apps.analysis.cameras.last_run", return_value=SimpleNamespace(pk="last")),
                  patch("apps.analysis.cameras.status_for", return_value=status),
                  patch("apps.analysis.cameras.recent_frame", return_value=True),
                  patch("apps.analysis.cameras.run_dir", return_value=Path(media))):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response["Server-Timing"].startswith("preview-receive-age;dur="))
                self.assertEqual(b"".join(response.streaming_content), b"recent JPEG")
                expired = measured - 10_000_000_000
                os.utime(file, ns=(expired, expired))
                self.assertEqual(self.client.get(route).status_code, 404)
