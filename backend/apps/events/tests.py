import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from django.test import override_settings
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

    def test_create_persists_and_preserves_trace(self):
        response = self.create_event()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Event.objects.count(), 1)
        saved = Event.objects.get(pk=response.data["id"])
        self.assertEqual(saved.rule_id, "DEMO-R-01")
        self.assertEqual(saved.rule_version, 2)
        self.assertEqual(saved.rule_parameters, self.payload["rule_parameters"])
        self.assertEqual(str(saved.analysis_run_id), self.payload["analysis_run_id"])
        self.assertEqual(saved.track_id, 36)
        self.assertEqual(saved.zone_id, "DEMO-Z-01")

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
        newer = self.create_event()
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

    def test_invalid_filters_are_rejected(self):
        self.assertEqual(self.client.get("/api/v1/events/?unexpected=x").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/events/?occurred_after=bad").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/events/?event_type=unknown").status_code, 400)

    def test_update_and_delete_are_not_supported(self):
        created = self.create_event()
        path = f"/api/v1/events/{created.data['id']}/"
        self.assertEqual(self.client.patch(path, {"rule_id": "OTHER"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(path).status_code, 405)

    def test_cors_is_allowlisted(self):
        allowed = self.client.get("/api/v1/health/", HTTP_ORIGIN="http://localhost:3000")
        blocked = self.client.get("/api/v1/health/", HTTP_ORIGIN="https://unlisted.example")
        self.assertEqual(allowed["Access-Control-Allow-Origin"], "http://localhost:3000")
        self.assertNotIn("Access-Control-Allow-Origin", blocked)

    @override_settings(EVENT_POST_ENABLED=False)
    def test_post_is_disabled_when_not_configured(self):
        self.assertEqual(self.create_event().status_code, 403)
