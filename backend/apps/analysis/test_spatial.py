"""Configuración espacial persistida y aislada; validación real del Motor."""
from copy import deepcopy
from pathlib import Path
import tempfile
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from . import sessions
from .models import SpatialConfiguration


class SpatialConfigurationTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.user = get_user_model().objects.create(username="spatial_test", is_superuser=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.session = sessions.AnalysisSession(
            id=uuid4(), directory=Path(self.directory.name), filename="fixture.mp4", profile="A",
            video_path=Path(self.directory.name)/"fixture.mp4", source_sha256="a"*64,
            source_bytes=0, source_kind="manual", demo_source_id=None, zone={}, owner_id=self.user.pk)
        sessions._sessions[self.session.id] = self.session
        self.addCleanup(lambda: sessions._sessions.pop(self.session.id, None))
        self.url = f"/api/v1/analysis/sessions/{self.session.id}/configuration/"
        self.document = {"schema_version": 1, "view_id": "fixture", "coordinate_system": "normalized",
            "zones": [{"zone_id": "z", "name": "Zona", "polygon": [[0,0],[1,0],[1,1],[0,1]], "purpose": "restricted", "enabled": True}],
            "rules": [{"rule_id": "r", "version": 1, "enabled": True, "parameters": {
                "kind": "zone_entry", "zone_id": "z", "class_name": "person", "min_duration_s": 0}}]}

    def save(self, document=None, revision=0):
        return self.client.put(self.url, {"document": document or self.document, "revision": revision}, format="json")

    def test_persists_revisions_without_mutating_previous_snapshot(self):
        response = self.save()
        self.assertEqual(response.status_code, 200, response.data)
        old = deepcopy(self.session.operational_config())
        self.document["rules"][0]["enabled"] = False
        self.assertEqual(self.save(revision=1).status_code, 200)
        self.assertEqual(self.session.profile_config["rules"][0]["version"], 2)
        self.assertEqual(SpatialConfiguration.objects.get(revision=1).document, old)
        self.assertEqual(self.save(revision=1).status_code, 409)
        self.assertEqual(self.client.get(self.url).data["saved"], self.session.profile_config)

    def test_rejects_invalid_polygon_and_inconsistent_entry(self):
        for change in ("polygon", "purpose", "duration"):
            doc = deepcopy(self.document)
            if change == "polygon": doc["zones"][0]["polygon"] = [[0,0],[1,1],[0,1],[1,0]]
            if change == "purpose": doc["zones"][0]["purpose"] = "observation"
            if change == "duration": doc["rules"][0]["parameters"]["min_duration_s"] = 2
            self.assertEqual(self.save(doc).status_code, 400, change)
        self.assertEqual(SpatialConfiguration.objects.count(), 0)

    def test_auth_ownership_and_busy_sessions(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, (401,403))
        other = get_user_model().objects.create(username="other")
        from django.contrib.auth.models import Group
        from config.access import OPERATOR_GROUP
        other.groups.add(Group.objects.get_or_create(name=OPERATOR_GROUP)[0])
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_authenticate(self.user)
        self.session.state = "processing"
        self.assertEqual(self.save().status_code, 409)

    def test_calibration_source_invalidation_and_versioning(self):
        calibration = {"image_points": [[0,0],[1,0],[1,1],[0,1]], "ground_points_m": [[0,0],[10,0],[10,10],[0,10]],
            "source_sha256": "b"*64, "version": 99, "status": "valid", "units": "m",
            "calibrated_at": "2026-11-09T00:00:00Z", "zones_reviewed": True}
        self.document["calibration"] = calibration
        self.assertEqual(self.save().status_code, 400)
        calibration["source_sha256"] = self.session.source_sha256
        first = self.save()
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data["document"]["calibration"]["version"], 1)
        calibration["status"] = "invalid"
        self.document["zones"][0]["enabled"] = False
        second = self.save(revision=1)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data["document"]["calibration"]["version"], 2)
        self.assertFalse(self.session.operational_config()["zones"][0]["enabled"])

    def test_reintroduced_rule_keeps_monotonic_identity_version(self):
        self.assertEqual(self.save().status_code, 200)
        self.document["rules"][0]["enabled"] = False
        self.assertEqual(self.save(revision=1).data["document"]["rules"][0]["version"], 2)
        rule = deepcopy(self.document["rules"][0])
        self.document["rules"] = []
        self.assertEqual(self.save(revision=2).status_code, 200)
        self.document["rules"] = [rule]
        restored = self.save(revision=3)
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertEqual(restored.data["document"]["rules"][0]["version"], 3)

    def test_reintroduced_calibration_does_not_reuse_pre_invalidation_version(self):
        calibration = {"image_points": [[0,0],[1,0],[1,1],[0,1]],
            "ground_points_m": [[0,0],[10,0],[10,10],[0,10]], "source_sha256": "a"*64,
            "version": 1, "status": "valid", "units": "m",
            "calibrated_at": "2026-11-09T00:00:00Z", "zones_reviewed": True}
        self.document["calibration"] = calibration
        self.assertEqual(self.save().status_code, 200)
        calibration["status"] = "invalid"
        self.assertEqual(self.save(revision=1).data["document"]["calibration"]["version"], 2)
        self.document.pop("calibration")
        self.assertEqual(self.save(revision=2).status_code, 200)
        self.document["calibration"] = {**calibration, "status": "valid"}
        restored = self.save(revision=3)
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertEqual(restored.data["document"]["calibration"]["version"], 3)
        self.assertEqual(SpatialConfiguration.objects.get(revision=2).document["calibration"]["status"], "invalid")

    def test_saved_configuration_is_bound_to_owner_and_video_hash(self):
        self.assertEqual(self.save().status_code, 200)
        other = sessions.AnalysisSession(id=uuid4(), directory=Path(self.directory.name),
            filename="other.mp4", profile="A", video_path=Path(self.directory.name)/"other.mp4",
            source_sha256="b"*64, source_bytes=0, source_kind="manual", demo_source_id=None,
            zone={"zone_id":"other", "name":"Other", "polygon":[[0,0],[1,0],[1,1],[0,1]]}, owner_id=self.user.pk)
        sessions._sessions[other.id] = other
        self.addCleanup(lambda: sessions._sessions.pop(other.id,None))
        url=f"/api/v1/analysis/sessions/{other.id}/configuration/"
        response=self.client.get(url)
        self.assertIsNone(response.data["saved"])
        self.assertEqual(response.data["revision"],0)
        self.assertEqual(response.data["document"]["zones"][0]["zone_id"],"other")
        self.assertEqual(self.client.get(self.url).data["saved"]["zones"][0]["zone_id"],"z")
