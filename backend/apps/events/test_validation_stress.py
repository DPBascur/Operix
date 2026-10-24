"""Carga acotada TEST_DATA: nunca escribe en el histórico de desarrollo."""

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time
from uuid import uuid4

from django.db import connection
from rest_framework.test import APITestCase

from .models import Event


class ControlledHistoryValidationTests(APITestCase):
    def test_thousand_rows_reconcile_under_repeated_queries(self):
        anchor = datetime(2026, 10, 1, tzinfo=timezone.utc)
        dates = [anchor + timedelta(minutes=i * 37) for i in range(1000)]
        run = uuid4()
        Event.objects.bulk_create([
            Event(analysis_run_id=run, view_id="TEST_DATA_STRESS", occurred_at=date,
                  video_timestamp_s=index, frame_index=index, event_type="zone_dwell",
                  rule_id="TEST_DATA_RULE", rule_version=1,
                  rule_parameters={"kind": "zone_dwell", "class_name": "person",
                                   "zone_id": "TEST_DATA_ZONE", "min_duration_s": 1},
                  zone_id="TEST_DATA_ZONE", track_id=index, class_name="person",
                  observed_inside=True, observed_dwell_time_s=2)
            for index, date in enumerate(dates)
        ])
        start, end = dates[100], dates[300]
        cases = [({}, dates),
                 ({"occurred_after": start.isoformat()}, [d for d in dates if d >= start]),
                 ({"occurred_before": end.isoformat()}, [d for d in dates if d <= end]),
                 ({"occurred_after": start.isoformat(), "occurred_before": end.isoformat(),
                   "event_type": "zone_dwell"}, [d for d in dates if start <= d <= end]),
                 ({"occurred_after": "2030-01-01T00:00:00Z"}, [])]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                listed = self.client.get("/api/v1/events/", filters)
                aggregated = self.client.get("/api/v1/events/frequencies/", filters)
                self.assertEqual((listed.status_code, aggregated.status_code), (200, 200))
                self.assertEqual(len(listed.json()), len(expected))
                data = aggregated.json()
                expected_days = Counter(d.date().isoformat() for d in expected)
                self.assertEqual({r["date"]: r["count"] for r in data["by_period"]}, expected_days)
                self.assertEqual(data["total"], len(expected))
        metrics = {}
        for name, url in (("health", "/api/v1/health/"), ("history_1000", "/api/v1/events/"),
                          ("frequencies_1000", "/api/v1/events/frequencies/")):
            samples = []
            for _ in range(21):
                tick = time.perf_counter_ns()
                response = self.client.get(url)
                samples.append((time.perf_counter_ns() - tick) / 1e6)
                self.assertEqual(response.status_code, 200)
            ordered = sorted(samples[1:])
            metrics[name] = {"first_request_ms": samples[0], "warm_requests": 20,
                             "mean_ms": statistics.mean(ordered), "median_ms": statistics.median(ordered),
                             "p95_ms": ordered[math.ceil(.95 * len(ordered)) - 1],
                             "min_ms": min(ordered), "max_ms": max(ordered),
                             "sample_stdev_ms": statistics.stdev(ordered)}
        self.assertEqual(Event.objects.count(), 1000)
        self.assertEqual(Event.objects.filter(view_id="TEST_DATA_STRESS").count(), 1000)
        output = os.environ.get("OPERIX_VALIDATION_OUTPUT_DIR")
        if output:
            repository = Path(__file__).resolve().parents[3]
            folder = Path(output).resolve()
            if folder.is_relative_to(repository):
                raise ValueError("Resultados fuera de Git")
            folder.mkdir(parents=True, exist_ok=True)
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                database_version = cursor.fetchone()[0]
            (folder / "controlled-history-stress.json").write_text(json.dumps({
                "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip(),
                "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "date_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
                "os": platform.platform(), "postgresql": database_version,
                "rows": 1000, "row_marker": "TEST_DATA_STRESS", "metrics": metrics,
                "latency_scope": "Django in-process APIClient + real PostgreSQL; excludes TCP/browser",
                "cold_start": "Not measured; first request is NOT a cold application process",
                "p95_method": "nearest rank ceil(0.95*n), n=20",
                "reconciliation": "PASS", "isolation": "Django test database; rolled back/destroyed",
                "threshold": "No universal latency acceptance threshold",
            }, indent=2), encoding="utf-8")


class MixedHistoryValidationTests(APITestCase):
    def test_mixed_history_reconciles_under_bounded_load(self):
        from .serializers import EventSerializer
        from .test_pair_events import pair_payload
        from .tests import EventApiTests
        anchor = datetime(2026, 10, 1, tzinfo=timezone.utc)
        run = uuid4()
        legacy = EventApiTests()
        legacy.setUp()
        rows, independent = [], []
        for index in range(1200):
            values = pair_payload() if index % 2 else dict(legacy.payload)
            occurred = anchor + timedelta(minutes=index * 7)
            values.update(analysis_run_id=str(run), view_id="TEST_DATA_STRESS",
                          frame_index=100 + index, occurred_at=occurred.isoformat())
            checked = EventSerializer(data=values)
            checked.is_valid(raise_exception=True)
            rows.append(Event(**checked.validated_data))
            independent.append((occurred, values["event_type"]))
        Event.objects.bulk_create(rows)
        after, before = independent[200][0], independent[800][0]
        filters = [({}, independent)]
        for kind in ("zone_dwell", "person_forklift_proximity"):
            filters.append(({"event_type": kind}, [r for r in independent if r[1] == kind]))
        filters += [({"occurred_after": after.isoformat(), "occurred_before": before.isoformat()},
                     [r for r in independent if after <= r[0] <= before]),
                    ({"event_type": "person_forklift_proximity", "occurred_after": after.isoformat(),
                      "occurred_before": before.isoformat()},
                     [r for r in independent if r[1] == "person_forklift_proximity" and after <= r[0] <= before])]
        for params, expected in filters:
            listed = self.client.get("/api/v1/events/", params)
            counted = self.client.get("/api/v1/events/frequencies/", params).json()
            self.assertEqual(len(listed.json()), len(expected))
            self.assertEqual(counted["total"], len(expected))
            self.assertEqual({r["event_type"]:r["count"] for r in counted["by_type"]}, Counter(kind for _,kind in expected))
            self.assertEqual({r["date"]:r["count"] for r in counted["by_period"]}, Counter(date.date().isoformat() for date,_ in expected))
        metrics = {}
        endpoints = [("history_all", "/api/v1/events/", {}),
                     ("history_type", "/api/v1/events/", filters[2][0]),
                     ("history_date", "/api/v1/events/", filters[3][0]),
                     ("history_type_date", "/api/v1/events/", filters[4][0]),
                     ("frequencies_mixed", "/api/v1/events/frequencies/", {}),
                     ("frequencies_type_date", "/api/v1/events/frequencies/", filters[4][0]),
                     ("evidence_metadata", f"/api/v1/events/{rows[1].id}/", {})]
        for name, endpoint, params in endpoints:
            values = []
            for _ in range(21):
                start = time.perf_counter_ns()
                response = self.client.get(endpoint, params)
                values.append((time.perf_counter_ns() - start)/1e6)
                self.assertEqual(response.status_code, 200)
            ordered = sorted(values[1:])
            metrics[name] = {"first_ms": values[0], "mean_ms": statistics.mean(ordered),
                             "median_ms": statistics.median(ordered), "p95_ms": ordered[18], "max_ms": max(ordered)}
        self.assertEqual(Event.objects.filter(view_id="TEST_DATA_STRESS").count(), 1200)
        output = os.environ.get("OPERIX_VALIDATION_OUTPUT_DIR")
        if output:
            repository = Path(__file__).resolve().parents[3]
            folder = Path(output).resolve()
            if folder.is_relative_to(repository):
                raise ValueError("Resultados fuera de Git")
            folder.mkdir(parents=True, exist_ok=True)
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                postgres = cursor.fetchone()[0]
            (folder / "controlled-history-mixed-stress.json").write_text(json.dumps({
                "commit": subprocess.check_output(["git","rev-parse","HEAD"],cwd=repository,text=True).strip(),
                "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "date_utc": datetime.now(timezone.utc).isoformat(), "postgresql": postgres,
                "python": platform.python_version(), "os": platform.platform(), "rows": 1200,
                "by_type": {"zone_dwell":600,"person_forklift_proximity":600},
                "scope": "Django APIClient in-process + PostgreSQL real; excludes TCP/browser",
                "method": "first separate; 20 warm; p95 nearest rank ceil(.95*20)=19; no cold process measured",
                "isolation": "TEST_DATA_STRESS only in test database, destroyed after test",
                "metrics": metrics, "reconciliation": "PASS"}, indent=2), encoding="utf-8")
