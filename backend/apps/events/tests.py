import uuid
import json
import struct
import tempfile
import zlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from .models import Event


class EventApiTests(APITestCase):
    def setUp(self):
        self.occurred_at = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
        self.payload = {
            "analysis_run_id": str(uuid.uuid4()),
            "view_id": "DEMO-VIEW-01",
            "occurred_at": self.occurred_at.isoformat(),
            "video_timestamp_s": "12.400",
            "frame_index": 310,
            "event_type": "zone_dwell",
            "rule_id": "DEMO-R-01",
            "rule_version": 2,
            "rule_parameters": {
                "kind": "zone_dwell",
                "class_name": "person",
                "zone_id": "DEMO-Z-01",
                "min_duration_s": 3.0,
            },
            "zone_id": "DEMO-Z-01",
            "track_id": 36,
            "class_name": "person",
            "observed_inside": True,
            "observed_dwell_time_s": "3.400",
        }

    def create_event(self, payload=None):
        return self.client.post("/api/v1/events/", payload or self.payload, format="json")

    def test_health_checks_database(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "ok", "database": "ok"})

    def test_database_outage_is_controlled_without_private_details(self):
        from unittest.mock import patch
        from django.db import DatabaseError
        with patch("apps.events.views.Event.objects.get_or_create",
                   side_effect=DatabaseError("private database detail")):
            response = self.create_event()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", json.dumps(response.data))
        self.assertEqual(Event.objects.count(), 0)

    def test_create_persists_and_preserves_trace(self):
        response = self.create_event()
        self.assertEqual(response.status_code, 201)
        self.assertIs(response.data["created"], True)
        self.assertEqual(Event.objects.count(), 1)
        saved = Event.objects.get(pk=response.data["id"])
        self.assertEqual(saved.rule_id, "DEMO-R-01")
        self.assertEqual(saved.rule_version, 2)
        self.assertEqual(saved.rule_parameters, self.payload["rule_parameters"])
        self.assertEqual(str(saved.analysis_run_id), self.payload["analysis_run_id"])
        self.assertEqual(saved.track_id, 36)
        self.assertEqual(saved.zone_id, "DEMO-Z-01")

    def test_submillisecond_dwell_boundary_and_materially_lower_value(self):
        self.payload["rule_parameters"]["min_duration_s"] = 1 / 30
        self.payload["observed_dwell_time_s"] = "0.033333333"
        self.assertEqual(self.create_event().status_code, 201)
        self.payload["frame_index"] += 1
        self.payload["observed_dwell_time_s"] = "0.033"
        self.assertEqual(self.create_event().status_code, 400)
        self.assertEqual(Event.objects.count(), 1)

    def test_historical_rounded_observation_is_not_silently_replaced(self):
        self.payload["rule_parameters"]["min_duration_s"] = 0.06
        self.payload["observed_dwell_time_s"] = "0.067"
        first = self.create_event()
        self.assertEqual(first.status_code, 201)
        self.payload["observed_dwell_time_s"] = "0.066666667"
        self.assertEqual(self.create_event().status_code, 409)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(str(Event.objects.get().id), first.data["id"])
        self.assertEqual(float(Event.objects.get().observed_dwell_time_s), 0.067)

    def test_retry_returns_existing_event_without_new_row(self):
        first = self.create_event()
        retry = deepcopy(self.payload)
        retry["occurred_at"] = (self.occurred_at + timedelta(minutes=1)).isoformat()
        second = self.create_event(retry)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertIs(second.data["created"], False)
        self.assertEqual(second.data["id"], first.data["id"])
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.get().occurred_at, self.occurred_at)

    def test_distinct_analysis_frame_and_rule_create_new_events(self):
        self.assertEqual(self.create_event().status_code, 201)
        other_run = deepcopy(self.payload)
        other_run["analysis_run_id"] = str(uuid.uuid4())
        self.assertEqual(self.create_event(other_run).status_code, 201)
        other_frame = deepcopy(self.payload)
        other_frame["frame_index"] += 1
        self.assertEqual(self.create_event(other_frame).status_code, 201)
        other_rule = deepcopy(self.payload)
        other_rule["rule_version"] += 1
        other_rule["rule_parameters"]["min_duration_s"] = 2.0
        self.assertEqual(self.create_event(other_rule).status_code, 201)
        self.assertEqual(Event.objects.count(), 4)

    def test_same_identity_with_incompatible_rule_parameters_is_rejected(self):
        first = self.create_event()
        changed = deepcopy(self.payload)
        changed["rule_parameters"]["min_duration_s"] = 2.0
        response = self.create_event(changed)
        self.assertEqual((first.status_code, response.status_code), (201, 409))
        self.assertEqual(Event.objects.count(), 1)

    def test_database_constraint_rejects_duplicate_key(self):
        created = self.create_event()
        event = Event.objects.get(pk=created.data["id"])
        event.pk = uuid.uuid4()
        event._state.adding = True
        with self.assertRaises(IntegrityError), transaction.atomic():
            event.save(force_insert=True)
        self.assertEqual(Event.objects.count(), 1)

    def test_create_rejects_missing_required_field(self):
        payload = deepcopy(self.payload)
        del payload["rule_id"]
        response = self.create_event(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("rule_id", response.data)
        self.assertEqual(Event.objects.count(), 0)

    def test_create_rejects_invalid_timestamp(self):
        payload = deepcopy(self.payload)
        payload["occurred_at"] = "2026-99-99"
        self.assertEqual(self.create_event(payload).status_code, 400)
        payload["occurred_at"] = "2026-10-13T12:00:00"
        self.assertEqual(self.create_event(payload).status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_create_rejects_inconsistent_parameters(self):
        payload = deepcopy(self.payload)
        payload["rule_parameters"]["zone_id"] = "OTHER-ZONE"
        self.assertEqual(self.create_event(payload).status_code, 400)
        payload = deepcopy(self.payload)
        payload["rule_parameters"]["min_duration_s"] = 9.0
        self.assertEqual(self.create_event(payload).status_code, 400)
        payload = deepcopy(self.payload)
        payload["rule_parameters"]["extra"] = "not allowed"
        self.assertEqual(self.create_event(payload).status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_create_rejects_non_candidate_or_unknown_fields(self):
        payload = deepcopy(self.payload)
        payload["observed_inside"] = False
        self.assertEqual(self.create_event(payload).status_code, 400)
        payload = deepcopy(self.payload)
        payload["classification"] = "near_miss"
        self.assertEqual(self.create_event(payload).status_code, 400)

    def test_list_is_ordered_newest_first(self):
        older = deepcopy(self.payload)
        older["occurred_at"] = (self.occurred_at - timedelta(hours=1)).isoformat()
        self.assertEqual(self.create_event(older).status_code, 201)
        newer_payload = deepcopy(self.payload)
        newer_payload["analysis_run_id"] = str(uuid.uuid4())
        newer = self.create_event(newer_payload)
        self.assertEqual(newer.status_code, 201)
        response = self.client.get("/api/v1/events/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["id"], newer.data["id"])

    def test_detail_returns_persisted_event(self):
        created = self.create_event()
        response = self.client.get(f"/api/v1/events/{created.data['id']}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rule_parameters"], self.payload["rule_parameters"])
        self.assertEqual(response.data["frame_index"], 310)

    def test_filter_by_period_and_type(self):
        self.create_event()
        after = (self.occurred_at - timedelta(minutes=1)).isoformat()
        before = (self.occurred_at + timedelta(minutes=1)).isoformat()
        response = self.client.get("/api/v1/events/", {
            "event_type": "zone_dwell",
            "occurred_after": after,
            "occurred_before": before,
        })
        self.assertEqual(len(response.data), 1)
        response = self.client.get("/api/v1/events/", {
            "occurred_after": (self.occurred_at + timedelta(minutes=1)).isoformat(),
        })
        self.assertEqual(response.data, [])

    def test_filters_use_inclusive_bounds_and_timezone_offsets(self):
        ids = []
        for minutes in (-60, 0, 60):
            payload = deepcopy(self.payload)
            payload["analysis_run_id"] = str(uuid.uuid4())
            payload["occurred_at"] = (self.occurred_at + timedelta(minutes=minutes)).isoformat()
            ids.append(self.create_event(payload).data["id"])
        self.assertEqual(len(self.client.get("/api/v1/events/").data), 3)
        instant = "2026-10-13T09:00:00-03:00"
        for params, expected in (
            ({"occurred_after": instant}, ids[1:]),
            ({"occurred_before": instant}, ids[:2]),
            ({"occurred_after": instant, "occurred_before": instant}, ids[1:2]),
            ({"event_type": "zone_dwell"}, ids),
            ({"event_type": "zone_dwell", "occurred_after": instant,
              "occurred_before": instant}, ids[1:2]),
            ({"occurred_after": "2026-10-14T00:00:00Z"}, []),
        ):
            with self.subTest(params=params):
                response = self.client.get("/api/v1/events/", params)
                self.assertEqual(response.status_code, 200)
                self.assertCountEqual([item["id"] for item in response.data], expected)

    def test_filter_rejects_reverse_range_and_naive_time(self):
        for params in (
            {"occurred_after": "2026-10-13T12:01:00Z", "occurred_before": "2026-10-13T12:00:00Z"},
            {"occurred_after": "2026-10-13T12:00:00"},
            {"occurred_before": "2026-10-13T12:00:00"},
            {"event_type": "unknown"},
        ):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/v1/events/", params).status_code, 400)

    def test_invalid_filters_are_rejected(self):
        self.assertEqual(self.client.get("/api/v1/events/?unexpected=x").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/events/?occurred_after=bad").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/events/?event_type=unknown").status_code, 400)

    def test_update_and_delete_are_not_supported(self):
        created = self.create_event()
        path = f"/api/v1/events/{created.data['id']}/"
        self.assertEqual(self.client.patch(path, {"rule_id": "OTHER"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(path).status_code, 405)

    @override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:3000"])
    def test_cors_is_allowlisted(self):
        allowed = self.client.get("/api/v1/health/", HTTP_ORIGIN="http://localhost:3000")
        blocked = self.client.get("/api/v1/health/", HTTP_ORIGIN="https://unlisted.example")
        self.assertEqual(allowed["Access-Control-Allow-Origin"], "http://localhost:3000")
        self.assertNotIn("Access-Control-Allow-Origin", blocked)

    @override_settings(EVENT_POST_ENABLED=False)
    def test_post_is_disabled_when_not_configured(self):
        self.assertEqual(self.create_event().status_code, 403)


def sample_png():
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


class EventEvidenceTests(APITestCase):
    create_event = EventApiTests.create_event

    def setUp(self):
        EventApiTests.setUp(self)
        self.media_dir = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_dir.cleanup)

    def upload(self, event_id, *, frame_index="310", video_timestamp_s="12.400", image=None):
        return self.client.post(
            f"/api/v1/events/{event_id}/evidence/",
            {
                "frame_index": frame_index,
                "video_timestamp_s": video_timestamp_s,
                "image": image or SimpleUploadedFile("frame.png", sample_png(), content_type="image/png"),
            },
            format="multipart",
        )

    def test_event_without_evidence_is_compatible(self):
        created = self.create_event()
        self.assertEqual(created.status_code, 201)
        self.assertIsNone(created.data["evidence_url"])
        self.assertIsNone(self.client.get("/api/v1/events/").data[0]["evidence_url"])
        self.assertEqual(self.client.get(f"/api/v1/events/{created.data['id']}/evidence/").status_code, 404)

    def test_unwritable_evidence_is_controlled_and_does_not_change_record(self):
        from unittest.mock import patch
        event_id = self.create_event().data["id"]
        with patch("django.core.files.storage.filesystem.FileSystemStorage._save",
                   side_effect=PermissionError("private filesystem detail")):
            response = self.upload(event_id)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", json.dumps(response.data))
        self.assertFalse(Event.objects.get(pk=event_id).evidence_image)

    def test_evidence_is_persisted_and_retrievable(self):
        created = self.create_event()
        event_id = created.data["id"]
        uploaded = self.upload(event_id)
        self.assertEqual(uploaded.status_code, 201)
        url = f"/api/v1/events/{event_id}/evidence/"
        self.assertEqual(uploaded.data["evidence_url"], url)
        saved = Event.objects.get(pk=event_id)
        self.assertTrue(saved.evidence_image.name.startswith(f"events/{event_id}/"))
        self.assertEqual(self.client.get("/api/v1/events/").data[0]["evidence_url"], url)
        self.assertEqual(self.client.get(f"/api/v1/events/{event_id}/").data["evidence_url"], url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(b"".join(response.streaming_content), sample_png())

    def test_wrong_frame_or_invalid_image_is_rejected(self):
        event_id = self.create_event().data["id"]
        self.assertEqual(self.upload(event_id, frame_index="311").status_code, 400)
        self.assertEqual(self.upload(event_id, video_timestamp_s="12.401").status_code, 400)
        bad = SimpleUploadedFile("frame.png", b"not a png", content_type="image/png")
        self.assertEqual(self.upload(event_id, image=bad).status_code, 400)
        self.assertFalse(Event.objects.get(pk=event_id).evidence_image)

    def test_missing_file_is_not_advertised(self):
        event_id = self.create_event().data["id"]
        self.assertEqual(self.upload(event_id).status_code, 201)
        saved = Event.objects.get(pk=event_id)
        saved.evidence_image.storage.delete(saved.evidence_image.name)
        self.assertIsNone(self.client.get(f"/api/v1/events/{event_id}/").data["evidence_url"])
        self.assertEqual(self.client.get(f"/api/v1/events/{event_id}/evidence/").status_code, 404)

    def test_png_with_valid_crc_but_unreadable_pixels_is_rejected(self):
        def chunk(kind, body):
            return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

        event_id = self.create_event().data["id"]
        for data in (b"not a zlib stream", zlib.compress(b""),
                     zlib.compress(b"\x05\x00\x00\x00"),
                     zlib.compress(b"\x00" * 10000)):
            with self.subTest(data=data[:20]):
                payload = (b"\x89PNG\r\n\x1a\n"
                           + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", data) + chunk(b"IEND", b""))
                image = SimpleUploadedFile("frame.png", payload, content_type="image/png")
                self.assertEqual(self.upload(event_id, image=image).status_code, 400)
                self.assertFalse(Event.objects.get(pk=event_id).evidence_image)

    def test_duplicate_upload_reuses_evidence_without_new_file(self):
        event_id = self.create_event().data["id"]
        self.assertEqual(self.upload(event_id).status_code, 201)
        original_name = Event.objects.get(pk=event_id).evidence_image.name
        self.assertEqual(self.upload(event_id).status_code, 200)
        self.assertEqual(Event.objects.get(pk=event_id).evidence_image.name, original_name)
        storage = Event.objects.get(pk=event_id).evidence_image.storage
        self.assertEqual(len(storage.listdir(f"events/{event_id}")[1]), 1)

    def test_adam7_png_remains_supported_and_decode_limit_is_enforced(self):
        from .views import validate_png
        from rest_framework.exceptions import ValidationError

        def chunk(kind, body):
            return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

        def png(width, height, depth, color, interlace, pixels):
            return (b"\x89PNG\r\n\x1a\n"
                    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, interlace))
                    + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))

        validate_png(png(1, 1, 8, 2, 1, b"\x00\x00\x00\x00"))
        with self.assertRaises(ValidationError):
            validate_png(png(4096, 4096, 16, 6, 0, b""))

    def test_retry_can_complete_missing_evidence(self):
        event_id = self.create_event().data["id"]
        self.assertEqual(self.create_event().status_code, 200)
        self.assertEqual(self.upload(event_id).status_code, 201)
        saved = Event.objects.get(pk=event_id)
        old_name = saved.evidence_image.name
        saved.evidence_image.storage.delete(old_name)
        self.assertIsNone(self.create_event().data["evidence_url"])
        self.assertEqual(self.upload(event_id).status_code, 201)
        refreshed = Event.objects.get(pk=event_id)
        self.assertNotEqual(refreshed.evidence_image.name, old_name)
        self.assertTrue(refreshed.evidence_image.storage.exists(refreshed.evidence_image.name))
        self.assertEqual(Event.objects.count(), 1)

    @override_settings(EVENT_POST_ENABLED=False)
    def test_upload_disabled_with_event_post(self):
        event_id = Event.objects.create(
            analysis_run_id=uuid.uuid4(), view_id="DEMO-VIEW-01", occurred_at=self.occurred_at,
            video_timestamp_s="12.400", frame_index=310, event_type="zone_dwell",
            rule_id="DEMO-R-01", rule_version=2, rule_parameters=self.payload["rule_parameters"],
            zone_id="DEMO-Z-01", track_id=36, class_name="person", observed_inside=True,
            observed_dwell_time_s="3.400",
        ).pk
        self.assertEqual(self.upload(event_id).status_code, 403)
