import uuid
from datetime import datetime, timedelta, timezone

from django.test import TestCase
from rest_framework.test import APIClient

from config.test_clients import administrator_client

from .models import Event


class EventHistoryPaginationTests(TestCase):
    url = "/api/v1/events/"
    instant = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)

    @classmethod
    def setUpTestData(cls):
        run = uuid.uuid4()
        Event.objects.bulk_create([
            Event(
                id=uuid.UUID(int=index + 1),
                analysis_run_id=run,
                view_id="vista",
                occurred_at=cls.instant + timedelta(minutes=index // 2),
                video_timestamp_s=index,
                frame_index=index,
                event_type="zone_entry" if index % 2 else "zone_dwell",
                rule_id="regla",
                rule_version=1,
                rule_parameters={},
                zone_id="Pasillo Norte" if index < 68 else "Patio",
                track_id=1,
                class_name="person",
                source=(
                    {"kind": "lab", "camera_id": "lab-cam-01", "filename": "Turno.mp4"}
                    if index < 68 else {"kind": "manual"}
                ),
                evidence_stage="finished" if index < 36 else "",
            )
            for index in range(72)
        ])
        # Tie both timestamps so the UUID tie-breaker is exercised at page boundaries.
        Event.objects.update(created_at=cls.instant)

    def setUp(self):
        self.client = administrator_client()

    def get(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_legacy_shape_and_scope(self):
        legacy = self.get()
        self.assertIsInstance(legacy, list)
        self.assertEqual(len(legacy), 4)
        self.assertEqual(len(self.get(camera_id="lab-cam-01")), 68)

    def test_paginated_default_includes_virtual_cameras_but_legacy_stays_operational(self):
        first = self.get(page=1)
        self.assertEqual(first["count"], 72)
        self.assertEqual({row["source"]["kind"] for row in first["results"]}, {"lab", "manual"})
        manual = self.get(page=1, source_kind="manual")
        self.assertEqual(manual["results"], self.get())
        frequencies = self.client.get(f"{self.url}frequencies/")
        self.assertEqual(frequencies.status_code, 200)
        self.assertEqual(frequencies.data["total"], 4)

    def test_fixed_pages_match_legacy_order_and_bounded_batches(self):
        camera = {"camera_id": "lab-cam-01"}
        legacy_ids = [row["id"] for row in self.get(**camera)]
        paged_ids = []
        for number, size in enumerate((15, 15, 15, 15, 8), 1):
            page = self.get(page=number, **camera)
            self.assertEqual((page["count"], page["page"], page["page_size"], page["total_pages"]),
                             (68, number, 15, 5))
            self.assertEqual(len(page["results"]), size)
            paged_ids.extend(row["id"] for row in page["results"])
        self.assertEqual(paged_ids, legacy_ids)

        for number, expected in ((1, legacy_ids[:60]), (2, legacy_ids[60:])):
            batch = self.get(page=number, page_size=60, **camera)
            self.assertEqual((batch["count"], batch["page_size"], batch["total_pages"]), (68, 60, 2))
            self.assertEqual([row["id"] for row in batch["results"]], expected)

    def test_filters_share_count_and_order_and_clamp_a_stale_page(self):
        params = {
            "camera_id": "lab-cam-01",
            "source_kind": "lab",
            "event_type": "zone_dwell",
            "occurred_after": self.instant.isoformat(),
            "occurred_before": (self.instant + timedelta(minutes=17)).isoformat(),
            "evidence_stage": "finished",
            "search": "tUrNo.mp4",
            "order": "oldest",
        }
        first = self.get(page=1, **params)
        last = self.get(page=1000000, **params)
        self.assertEqual((first["count"], first["total_pages"], last["page"]), (18, 2, 2))
        self.assertEqual(
            [row["id"] for row in first["results"] + last["results"]],
            [str(uuid.UUID(int=index)) for index in range(1, 36, 2)],
        )
        empty = self.get(page=10, **{**params, "search": "sin coincidencias"})
        self.assertEqual(empty, {"count": 0, "page": 1, "page_size": 15, "total_pages": 1, "results": []})

    def test_pagination_is_opt_in_validated_and_role_protected(self):
        for params in (
            {"page": 0}, {"page": "bad"}, {"page_size": 15},
            {"page": 1, "page_size": 999}, {"page": 1, "order": "other"},
            {"page": 1, "evidence_stage": "other"},
            {"page": 1, "search": "x" * 121}, {"page": 1, "unexpected": "x"},
        ):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.url, params).status_code, 400)
        self.assertEqual(self.client.get(f"{self.url}frequencies/", {"page": 1}).status_code, 400)
        self.assertIn(APIClient().get(self.url, {"page": 1}).status_code, (401, 403))
