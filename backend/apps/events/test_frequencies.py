"""OP-41: agregados UTC reconciliados contra los registros de PostgreSQL."""

from collections import Counter
from datetime import datetime, timezone
import uuid

from rest_framework.test import APITestCase

from .models import Event


class EventFrequencyTests(APITestCase):
    url = "/api/v1/events/frequencies/"

    def setUp(self):
        self.dates = [
            "2026-10-19T23:59:59+00:00", "2026-10-20T00:00:00+00:00",
            "2026-10-20T01:00:00+00:00", "2026-10-21T00:30:00+03:00",
        ]
        for index, date in enumerate(self.dates):
            Event.objects.create(
                analysis_run_id=uuid.uuid4(), view_id="SYNTHETIC",
                occurred_at=datetime.fromisoformat(date), video_timestamp_s=2,
                frame_index=index, event_type="zone_dwell", rule_id="synthetic",
                rule_version=1, rule_parameters={"kind": "zone_dwell"},
                zone_id="synthetic", track_id=1, class_name="person",
                observed_inside=True, observed_dwell_time_s=2,
            )

    def test_counts_match_independent_utc_counter(self):
        expected = Counter(
            datetime.fromisoformat(date).astimezone(timezone.utc).date().isoformat()
            for date in self.dates
        )
        with self.assertNumQueries(1):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 4)
        self.assertEqual({row["date"]: row["count"] for row in data["by_period"]}, expected)
        self.assertEqual(data["by_type"], [{"event_type": "zone_dwell", "count": 4}])
        self.assertEqual(sum(row["count"] for row in data["by_period"]), data["total"])
        self.assertEqual(sum(row["count"] for row in data["by_type"]), data["total"])
        self.assertEqual(data["timezone"], "UTC")

    def test_period_filters_match_event_list_including_boundaries(self):
        params = {
            "occurred_after": self.dates[1], "occurred_before": self.dates[2],
            "event_type": "zone_dwell",
        }
        aggregate = self.client.get(self.url, params).json()
        listed = self.client.get("/api/v1/events/", params).json()
        self.assertEqual(aggregate["total"], 2)
        self.assertEqual(aggregate["total"], len(listed))

    def test_empty_range_has_no_fabricated_days_or_types(self):
        response = self.client.get(self.url, {"occurred_after": "2030-01-01T00:00:00Z"})
        self.assertEqual(response.json(), {
            "total": 0, "timezone": "UTC", "period": "day",
            "by_period": [], "by_type": [],
        })

    def test_empty_database(self):
        Event.objects.all().delete()
        self.assertEqual(self.client.get(self.url).json()["total"], 0)

    def test_invalid_filters_are_rejected(self):
        for filters in (
            {"unexpected": "1"}, {"event_type": "invented"},
            {"occurred_after": "2026-10-20T00:00:00"},
            {"occurred_after": self.dates[2], "occurred_before": self.dates[1]},
        ):
            with self.subTest(filters=filters):
                self.assertEqual(self.client.get(self.url, filters).status_code, 400)

    def test_endpoint_is_read_only(self):
        for method in (self.client.post, self.client.put, self.client.delete):
            self.assertEqual(method(self.url, {}, format="json").status_code, 405)
        self.assertEqual(Event.objects.count(), 4)
