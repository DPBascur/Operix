import tempfile
from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from config.access import OPERATOR_GROUP
from config.test_clients import administrator_client

from .clips import clip_directory, clip_info, clip_window, generate_clips
from .models import Event


class EvidenceClipTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=media.name))
        self.run = uuid4()
        self.source = {"session_id": str(uuid4()), "session_run": 1,
                       "video_sha256": "1" * 64, "config_sha256": "2" * 64}
        self.config = {"analysis_run_id": str(self.run), "source": self.source, "video": {"fps": 30, "frames": 300}}
        self.event = Event.objects.create(
            analysis_run_id=self.run, view_id="test", occurred_at=timezone.now(),
            video_timestamp_s="1.000", frame_index=30, event_type="zone_dwell",
            rule_id="test", rule_version=1, rule_parameters={}, zone_id="test", source=self.source)
        self.event.refresh_from_db()
        self.admin = administrator_client()
        self.detail = f"/api/v1/events/{self.event.pk}/"

    def test_window_stays_within_source_and_contains_event(self):
        self.assertEqual(clip_window(0, 300, 30, 5), (0, 151))
        self.assertEqual(clip_window(299, 300, 30, 5), (149, 300))
        self.assertEqual(clip_window(180, 500, 30, 5), (30, 331))
        self.assertEqual(clip_window(1, 3, 12.5, 5), (0, 3))

    def test_bound_generation_range_duplicate_access_and_retention(self):
        path = Path("unused.mp4")
        def encode(command, **kwargs):
            self.assertEqual(command[5:8], ["0", "181", "30"])
            Path(command[4]).write_bytes(b"fixture-only-mp4")
        with patch("apps.events.clips.subprocess.run", side_effect=encode) as worker:
            generate_clips(path, {**self.config, "source": {**self.source, "session_run": 2}})
            self.assertIsNone(clip_info(self.event))
            generate_clips(path, self.config)
            generate_clips(path, self.config)
            self.assertEqual(worker.call_count, 1)
        clip = self.admin.get(self.detail).json()["evidence_clip"]
        self.assertEqual(clip["event_frame"], 30)
        self.assertEqual(clip["event_timestamp_s"], "1.000")
        self.assertEqual(clip["event_offset_s"], 1)
        self.assertEqual(clip["kind"], "annotated")
        url = clip["url"]
        self.assertEqual(APIClient().get(url).status_code, 401)
        user = get_user_model().objects.create_user(username="other")
        user.groups.add(Group.objects.create(name=OPERATOR_GROUP))
        operator = APIClient()
        operator.force_authenticate(user=user)
        self.assertEqual(operator.get(url).status_code, 403)
        self.assertEqual(self.admin.get(url.replace(str(self.run), str(uuid4()))).status_code, 404)
        response = self.admin.get(url, HTTP_RANGE="bytes=0-6")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b"".join(response.streaming_content), b"fixture")
        directory = clip_directory(self.event)
        (directory / "clip.mp4").write_bytes(b"truncated")
        self.assertIsNone(self.admin.get(self.detail).json()["evidence_clip"])
        self.assertEqual(self.admin.get(url, HTTP_RANGE="bytes=0-6").status_code, 404)
        with self.captureOnCommitCallbacks(execute=True):
            self.event.delete()
        self.assertFalse(directory.exists())
        self.assertEqual(self.admin.get(url).status_code, 404)

    def test_failed_encoder_leaves_no_partial_clip(self):
        def fail(command, **kwargs):
            Path(command[4]).write_bytes(b"partial")
            raise CalledProcessError(1, command)
        with patch("apps.events.clips.subprocess.run", side_effect=fail):
            generate_clips(Path("unused.mp4"), self.config)
        self.assertIsNone(self.admin.get(self.detail).json()["evidence_clip"])
        from django.conf import settings
        self.assertFalse(list(Path(settings.MEDIA_ROOT).rglob("*.mp4")))

    @override_settings(OPERIX_CLIP_TOTAL_BYTES=2)
    def test_clip_exceeding_quota_is_not_published(self):
        def encode(command, **kwargs):
            self.assertEqual(command[8], "2")
            Path(command[4]).write_bytes(b"too large")
        with patch("apps.events.clips.subprocess.run", side_effect=encode):
            generate_clips(Path("unused.mp4"), self.config)
        self.assertIsNone(clip_info(self.event))
