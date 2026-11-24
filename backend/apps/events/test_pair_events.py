"""Contrato de pares y consultas mixtas: fixtures, no evaluación de percepción."""

from copy import deepcopy
import json
import math
import sys
from uuid import uuid4

from django.conf import settings
from django.test import override_settings
from rest_framework.test import APITestCase
from config.test_clients import administrator_client

from .models import Event
from .pair_contract import validate_pair_parameters


def pair_payload():
    return {
        "analysis_run_id": str(uuid4()), "view_id": "TEST_DATA_VIEW",
        "occurred_at": "2026-10-24T12:00:02Z", "video_timestamp_s": "2.000", "frame_index": 60,
        "event_type": "person_forklift_proximity", "rule_id": "TEST_DATA_PAIR", "rule_version": 1,
        "zone_id": "TEST_DATA_ZONE", "rule_parameters": {
            "kind": "person_forklift_proximity", "zone_id": "TEST_DATA_ZONE",
            "person_class": "person", "forklift_class": "forklift",
            "max_distance": .25, "minimum_duration_seconds": 1.0},
        "interaction": {"person": {"class_name": "person", "track_id": 1},
                        "forklift": {"class_name": "forklift", "track_id": 1}},
        "observations": {"normalized_distance": .2, "duration_s": 1.0},
        "episode": {"started_frame_index": 30, "started_timestamp_s": 1.0, "timestamp_s": 2.0},
        "source": {"filename": "TEST_DATA.mp4", "kind": "controlled_fixture",
                   "timestamp_basis": "ANALYSIS_START_PROXY_NOT_RECORDING_TIME"},
    }


@override_settings(EVENT_POST_ENABLED=True)
class PairEventApiTests(APITestCase):
    def setUp(self):
        self.client = administrator_client()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.OPERIX_EVENT_PUBLISH_TOKEN}")
        self.payload = pair_payload()

    def post(self, payload=None):
        return self.client.post("/api/v1/events/", payload or self.payload, format="json")

    def test_equipment_scope_preserves_authorized_profile_in_dossier(self):
        payload = deepcopy(self.payload)
        category = "ELECTRIC_STACKER"
        profile = {"category": category, "source_sha256": "a" * 64, "authority_reference": "review-1"}
        payload["source"].update(video_sha256=profile["source_sha256"],
                                 spatial_configuration={"equipment_profile": profile})
        payload["rule_parameters"].update(equipment_category=category, unknown_equipment_policy="exclude")
        taxonomy = {"perception_class": "FORKLIFT", "operational_role": "MOBILE_EQUIPMENT",
                    "subtype": "UNKNOWN", "category": category, "category_source": "AUTHORIZED_PROFILE",
                    "profile": profile}
        payload["observations"]["equipment_taxonomy"] = taxonomy
        for changes in ({"subtype": "ELECTRIC_STACKER"}, {"category": "MANUAL_STACKER"}, {"profile": {}}):
            invalid = deepcopy(payload)
            invalid["observations"]["equipment_taxonomy"].update(changes)
            self.assertEqual(self.post(invalid).status_code, 400)
        wrong_source = deepcopy(payload)
        wrong_source["source"]["video_sha256"] = "b" * 64
        self.assertEqual(self.post(wrong_source).status_code, 400)
        created = self.post(payload)
        self.assertEqual(created.status_code, 201, created.data)
        dossier = self.client.get(f"/api/v1/events/{created.data['id']}/")
        self.assertEqual(dossier.data["observations"]["equipment_taxonomy"], taxonomy)
        self.assertEqual(self.post(payload).status_code, 200)

    def test_equipment_scope_requires_compatible_unknown_policy_and_snapshot(self):
        payload = deepcopy(self.payload)
        payload["rule_parameters"].update(equipment_category="ELECTRIC_PALLET_JACK",
                                          unknown_equipment_policy="include")
        self.assertEqual(self.post(payload).status_code, 400)
        payload["observations"]["equipment_taxonomy"] = {
            "perception_class": "FORKLIFT", "operational_role": "MOBILE_EQUIPMENT",
            "subtype": "UNKNOWN", "category": "UNKNOWN", "category_source": "UNKNOWN",
        }
        excluded = deepcopy(payload)
        excluded["rule_parameters"]["unknown_equipment_policy"] = "exclude"
        self.assertEqual(self.post(excluded).status_code, 400)
        included = self.post(payload)
        self.assertEqual(included.status_code, 201, included.data)

    def test_non_string_distance_unit_is_400_without_persistence(self):
        for unit in ([], {}):
            with self.subTest(unit=unit):
                payload = deepcopy(self.payload)
                payload["rule_parameters"]["distance_unit"] = unit
                self.assertEqual(self.post(payload).status_code, 400)
        self.assertFalse(Event.objects.exists())

    def test_extreme_pair_parameters_are_400_without_persistence(self):
        for name in ("max_distance", "minimum_duration_seconds"):
            for value in (10**1000, math.nan, math.inf, -math.inf, "9" * 5000, "bad", True, None, [], -1):
                with self.subTest(name=name, value_type=type(value).__name__):
                    payload = deepcopy(self.payload)
                    payload["rule_parameters"][name] = value
                    response = self.client.post("/api/v1/events/", json.dumps(payload), content_type="application/json")
                    self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Event.objects.count(), 0)

    def test_pair_numeric_domain_preserves_valid_values_above_one(self):
        for distance in (0, .25, 1, 1.2, math.sqrt(2)):
            with self.subTest(distance=distance):
                payload = deepcopy(self.payload)
                payload["analysis_run_id"] = str(uuid4())
                payload["rule_parameters"]["max_distance"] = distance
                payload["observations"]["normalized_distance"] = min(.2, distance)
                self.assertEqual(self.post(payload).status_code, 201)
        parameters = self.payload["rule_parameters"] | {"minimum_duration_seconds": sys.float_info.max}
        validate_pair_parameters(parameters)
        payload = deepcopy(self.payload)
        payload["rule_parameters"]["max_distance"] = math.nextafter(math.sqrt(2), math.inf)
        self.assertEqual(self.post(payload).status_code, 400)

    def test_metric_snapshot_keeps_normalized_geometry_and_rejects_tampering(self):
        import hashlib
        payload=deepcopy(self.payload)
        payload["source"]["video_sha256"]="a"*64
        payload["rule_parameters"].update(distance_unit="m",max_distance=2.)
        calibration={"status":"valid","source_sha256":"a"*64,"method":"ground_plane_contact_edges_v1","units":"m","zones_reviewed":True,"version":1,"homography":[[10,0,0],[0,10,0],[0,0,1]],"image_points":[[0,0],[1,0],[1,1],[0,1]],"ground_points_m":[[0,0],[10,0],[10,10],[0,10]],"calibrated_at":"2026-11-09T00:00:00Z"}
        calibration["sha256"]=hashlib.sha256(json.dumps(calibration,sort_keys=True,allow_nan=False).encode()).hexdigest()
        payload["observations"]["ground"]={"method":"ground_plane_contact_edges_v1","units":"m","distance":1.5,"person_anchor":[.1,.2],"equipment_target":[.25,.2],"calibration":calibration}
        response=self.post(payload)
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(self.client.get(f"/api/v1/events/{response.data['id']}/").data["observations"],payload["observations"])
        payload["analysis_run_id"]=str(uuid4())
        calibration["version"]=2
        self.assertEqual(self.post(payload).status_code,400)
        payload["observations"].pop("ground")
        self.assertEqual(self.post(payload).status_code,400)

    def test_coexistence_is_persisted_and_idempotent_without_metric_unit(self):
        payload=deepcopy(self.payload)
        payload["event_type"]=payload["rule_parameters"]["kind"]="zone_coexistence"
        payload["rule_parameters"]["max_distance"]=math.sqrt(2)
        response=self.post(payload)
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(self.post(payload).status_code,200)
        payload["rule_parameters"]["distance_unit"]="m"
        self.assertEqual(self.post(payload).status_code,400)

    def test_pair_snapshot_survives_retrieval_without_fictitious_primary_object(self):
        result = self.post()
        self.assertEqual(result.status_code, 201, result.data)
        event = Event.objects.get()
        self.assertIsNone(event.track_id)
        self.assertEqual(event.class_name, "")
        self.assertEqual(len(event.pair_key), 64)
        recovered = self.client.get(f"/api/v1/events/{event.id}/").json()
        for key in ("rule_parameters", "interaction", "observations", "episode", "source"):
            self.assertEqual(recovered[key], self.payload[key])

    def test_retry_same_pair_new_pair_new_episode_and_new_run_are_distinct(self):
        first, retry = self.post(), self.post()
        self.assertEqual((first.status_code, retry.status_code), (201, 200))
        self.assertEqual(first.data["id"], retry.data["id"])
        other = deepcopy(self.payload)
        other["interaction"]["forklift"]["track_id"] = 2
        self.assertEqual(self.post(other).status_code, 201)
        episode = deepcopy(self.payload)
        episode.update(frame_index=120, video_timestamp_s="4.000")
        episode["episode"] = {"started_frame_index": 90, "started_timestamp_s": 3., "timestamp_s": 4.}
        self.assertEqual(self.post(episode).status_code, 201)
        run = deepcopy(self.payload)
        run["analysis_run_id"] = str(uuid4())
        self.assertEqual(self.post(run).status_code, 201)
        self.assertEqual(Event.objects.count(), 4)

    def test_incompatible_retry_is_conflict_not_overwrite(self):
        self.assertEqual(self.post().status_code, 201)
        changed = deepcopy(self.payload)
        changed["observations"]["normalized_distance"] = .1
        self.assertEqual(self.post(changed).status_code, 409)
        self.assertEqual(Event.objects.get().observations["normalized_distance"], .2)

    def test_geometry_snapshot_is_optional_for_history_and_explicit_for_new_events(self):
        historical = self.post()
        self.assertEqual(historical.status_code, 201)
        self.assertNotIn("proximity_geometry", historical.data["observations"])
        updated = deepcopy(self.payload)
        updated["analysis_run_id"] = str(uuid4())
        updated["observations"]["proximity_geometry"] = {
            "version": "person_bottom_center_to_equipment_ground_edge_v1",
            "person_anchor": [.2,.5], "equipment_target": [.4,.5]}
        new = self.post(updated)
        self.assertEqual(new.status_code, 201, new.data)
        self.assertEqual(self.client.get(f"/api/v1/events/{new.data['id']}/").data["observations"], updated["observations"])
        old = self.client.get(f"/api/v1/events/{historical.data['id']}/").data
        self.assertNotIn("proximity_geometry", old["observations"])

    def test_invalid_geometry_or_retroactive_reinterpretation_is_rejected(self):
        for geometry in ({}, {"version":"unknown","person_anchor":[.2,.5],"equipment_target":[.4,.5]},
                {"version":"person_bottom_center_to_equipment_ground_edge_v1", "person_anchor":[2,.5],"equipment_target":[.4,.5]}):
            data = deepcopy(self.payload)
            data["observations"]["proximity_geometry"] = geometry
            self.assertEqual(self.post(data).status_code, 400)
        self.assertEqual(self.post().status_code, 201)
        changed = deepcopy(self.payload)
        changed["observations"]["proximity_geometry"] = {
            "version":"person_bottom_center_to_equipment_ground_edge_v1",
            "person_anchor":[.2,.5],"equipment_target":[.4,.5]}
        self.assertEqual(self.post(changed).status_code, 409)
        self.assertNotIn("proximity_geometry", Event.objects.get().observations)

    def test_D_snapshot_and_retry_preserve_historical_B_version(self):
        old = deepcopy(self.payload)
        old["observations"]["proximity_geometry"] = {
            "version":"person_bottom_center_to_equipment_ground_edge_v1",
            "person_anchor":[.2,.5],"equipment_target":[.4,.5]}
        first = self.post(old)
        self.assertEqual(first.status_code, 201)
        changed = deepcopy(old)
        changed["observations"]["proximity_geometry"]["version"] = "person_equipment_nearest_ground_edges_v1"
        self.assertEqual(self.post(changed).status_code, 409)
        recovered = self.client.get(f"/api/v1/events/{first.data['id']}/").data
        self.assertEqual(recovered["observations"], old["observations"])
        changed["analysis_run_id"] = str(uuid4())
        new = self.post(changed)
        self.assertEqual(new.status_code, 201, new.data)
        self.assertEqual(new.data["observations"], changed["observations"])

    def test_invalid_roles_observations_time_and_source_are_rejected(self):
        changes = [
            ("interaction", {}), ("interaction", {"person": {"class_name": "forklift", "track_id": 1}}),
            ("observations", {"normalized_distance": .3, "duration_s": 1.}),
            ("observations", {"normalized_distance": .2, "duration_s": .9}),
            ("episode", {"started_frame_index": 100, "started_timestamp_s": 1., "timestamp_s": 2.}),
            ("source", {"filename": "C:/private/video.mp4"}), ("track_id", 1),
        ]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                data = deepcopy(self.payload)
                data[key] = value
                self.assertEqual(self.post(data).status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_mixed_filters_and_counts_reconcile_independently(self):
        from .tests import EventApiTests
        legacy = EventApiTests()
        legacy.setUp()
        self.assertEqual(self.post(legacy.payload).status_code, 201)
        self.assertEqual(self.post().status_code, 201)
        for filters, expected in (({}, 2), ({"event_type": "zone_dwell"}, 1),
                                  ({"event_type": "person_forklift_proximity"}, 1),
                                  ({"occurred_after": "2030-01-01T00:00:00Z"}, 0),
                                  ({"event_type": "person_forklift_proximity", "occurred_before": "2026-10-24T12:00:02Z"}, 1)):
            listed = self.client.get("/api/v1/events/", filters)
            frequencies = self.client.get("/api/v1/events/frequencies/", filters)
            self.assertEqual(len(listed.json()), expected)
            self.assertEqual(frequencies.json()["total"], expected)
            self.assertEqual(sum(row["count"] for row in frequencies.json()["by_type"]), expected)

    def test_post_disabled_does_not_expand_existing_access(self):
        with override_settings(EVENT_POST_ENABLED=False):
            self.assertEqual(self.post().status_code, 403)
        self.assertEqual(Event.objects.count(), 0)

    def test_evidence_rollback_removes_new_file_on_database_failure(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.db import DatabaseError
        from .tests import sample_png
        created = self.post()
        identity = created.data["id"]
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            with patch.object(Event, "save", side_effect=DatabaseError("private database failure")):
                response = self.client.post(f"/api/v1/events/{identity}/evidence/", {
                    "frame_index": 60, "video_timestamp_s": "2.000",
                    "image": SimpleUploadedFile("frame.png", sample_png(), content_type="image/png"),
                }, format="multipart")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(list(Path(root).rglob("*.png")), [])
            self.assertFalse(Event.objects.get().evidence_image)
