import hashlib
import subprocess
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from config.access import SAFETY_GROUP, VIEWER_GROUP

from . import sessions
from .models import AnalysisRunSnapshot, AnalysisSource, SpatialConfiguration


BASE = "/api/v1/analysis/"
VIDEO = b"\x00\x00\x00\x18ftypisom" + b"source-policy-fixture"
POLYGON = [[0, 0], [1, 0], [1, 1], [0, 1]]


@override_settings(EVENT_POST_ENABLED=False)
class RuleCatalogTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create(username="catalog_owner")
        self.other = get_user_model().objects.create(username="catalog_other", is_superuser=True)
        self.owner.groups.add(Group.objects.get_or_create(name=SAFETY_GROUP)[0])
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.demo = Path(self.directory.name) / "demo.mp4"
        self.demo.write_bytes(VIDEO)
        settings = override_settings(
            OPERIX_PERSON_WEIGHTS=str(self.demo), OPERIX_FORKLIFT_WEIGHTS=str(self.demo),
            OPERIX_DEMO_VIDEO_B=str(self.demo), OPERIX_DEMO_VIDEO_A="",
        )
        settings.enable()
        self.addCleanup(settings.disable)

    def post(self, resource, body):
        response = self.client.post(f"{BASE}{resource}/", body, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def put(self, resource, entry, **updates):
        response = self.client.put(f"{BASE}{resource}/{entry['id']}/", {
            **{key: value for key, value in entry.items() if key not in {"id", "updated_at"}},
            **updates,
        }, format="json")
        return response

    def template(self, zone_id="custom_zone"):
        return self.post("rule-templates", {"name": "Permanencia", "enabled": True,
            "parameters": {"kind": "zone_dwell", "class_name": "person",
                           "zone_id": zone_id, "min_duration_s": 2}})

    def create_manual(self, video=VIDEO, **fields):
        return self.client.post(f"{BASE}sessions/", {
            "profile": "A", "video": SimpleUploadedFile("pasillo.mp4", video), **fields,
        }, format="multipart")

    def track(self, response):
        self.assertEqual(response.status_code, 201, response.data)
        session_id = UUID(response.data["id"])
        self.addCleanup(sessions.remove_session, session_id)
        return sessions.get_session(session_id)

    def test_history_validation_and_account_permissions(self):
        template = self.template()
        self.post("rule-sets", {"name": "Conjunto", "enabled": True, "rules": [
            {"template_id": template["id"], "overrides": {"parameters": {"min_duration_s": 3}}},
        ]})
        updated = self.put("rule-templates", template, name="Vigente")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["version"], 2)
        self.assertEqual(self.put("rule-templates", template, name="Obsoleta").status_code, 409)
        url = f"{BASE}rule-templates/{template['id']}/"
        history = self.client.get(url + "history/").data["results"]
        self.assertEqual([(item["version"], item["name"]) for item in history],
                         [(2, "Vigente"), (1, "Permanencia")])
        self.assertEqual(self.put("rule-templates", updated.data, parameters={
            **template["parameters"], "kind": "zone_entry", "min_duration_s": 0,
        }).status_code, 400)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(url + "history/").status_code, 404)
        response = self.client.post(f"{BASE}rule-sets/", {"name": "Ajeno", "enabled": True,
            "rules": [{"template_id": template["id"]}]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.owner.groups.set([Group.objects.get_or_create(name=VIEWER_GROUP)[0]])
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertFalse(self.client.get(f"{BASE}rule-templates/").data["can_edit"])
        self.assertEqual(self.put("rule-templates", updated.data, name="Cambio").status_code, 403)
        self.assertEqual(self.client.post(f"{BASE}rule-assignments/", {}, format="json").status_code, 403)

    def test_source_inventory_links_and_reopens_only_same_video(self):
        session = self.track(self.create_manual())
        url = f"{BASE}sources/{session.source_sha256}/"
        listed = self.client.get(f"{BASE}sources/").data["sources"]
        self.assertEqual(len(listed), 1)
        source = self.client.get(url).data
        self.assertEqual(source["filename"], "pasillo.mp4")
        self.assertEqual(source["zones"], [])
        self.assertEqual(source["effective_rules"], session.operational_config()["rules"])
        raw = self.client.get(source["video_url"], HTTP_RANGE="bytes=4-7")
        self.assertEqual(raw.status_code, 206)
        self.assertEqual(b"".join(raw.streaming_content), b"ftyp")
        document = session.operational_config()
        document["zones"][0]["polygon"] = POLYGON
        saved = self.client.put(source["configuration_url"], {"document": document, "revision": 0}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        expected = session.source_sha256
        sessions.remove_session(session.id)
        source = self.client.get(url).data
        self.assertIsNone(source["video_url"])
        self.assertIsNone(source["configuration_url"])
        self.assertEqual(source["zones"][0]["rules"][0]["kind"], "zone_dwell")
        self.assertEqual(source["zones"][0]["polygon"], POLYGON)
        self.assertEqual(source["effective_rules"], saved.data["document"]["rules"])
        self.assertEqual(self.create_manual(video=VIDEO + b"different", source_sha256=expected).status_code, 400)
        self.assertEqual(AnalysisSource.objects.count(), 1)
        reopened = self.track(self.create_manual(source_sha256=expected))
        self.assertEqual(reopened.spatial_revision, 1)
        self.assertEqual(reopened.operational_config(), saved.data["document"])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}sources/").data["sources"], [])

    def test_expired_manual_source_without_spatial_document_omits_effective_rules(self):
        session = self.track(self.create_manual())
        sessions.remove_session(session.id)
        response = self.client.get(f"{BASE}sources/{session.source_sha256}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["zones"], [])
        self.assertNotIn("effective_rules", response.data)

    def test_legacy_spatial_records_are_listed_at_latest_revision(self):
        digest = hashlib.sha256(VIDEO).hexdigest()
        document = sessions.read_profile("A")
        SpatialConfiguration.objects.create(owner=self.owner, source_sha256=digest, revision=1, document=document)
        document["zones"][0]["name"] = "Última revisión"
        SpatialConfiguration.objects.create(owner=self.owner, source_sha256=digest, revision=2, document=document)
        source, = self.client.get(f"{BASE}sources/").data["sources"]
        self.assertEqual(source["revision"], 2)
        self.assertIsNone(source["profile"])
        self.assertIsNone(source["filename"])
        self.assertEqual(source["zones"][0]["name"], "Última revisión")
        reopened = self.track(self.create_manual(source_sha256=digest))
        self.assertEqual(reopened.spatial_revision, 2)
        self.assertEqual(SpatialConfiguration.objects.count(), 2)

    def test_precedence_effective_worker_config_and_persistent_snapshot(self):
        profile = next(item for item in self.client.get(f"{BASE}profiles/").data if item["id"] == "B")
        demo = profile["default_demo_video"]
        self.assertEqual(demo["video_url"], f"{BASE}profiles/B/demo/forklift_human_nearmiss/")
        session = self.track(self.client.post(demo["session_create_url"], {
            "profile": "B", "demo_source_id": demo["id"],
        }, format="json"))
        template = self.template(session.zone["zone_id"])
        rule_id = template["id"]
        rule_set = self.post("rule-sets", {"name": "Pasillo", "enabled": True, "rules": [
            {"template_id": rule_id, "overrides": {"parameters": {"min_duration_s": 3}}},
        ]})
        assignment = {"enabled": True, "rule_set_id": rule_set["id"]}
        self.post("rule-assignments", {**assignment, "name": "Perfil", "target_type": "profile", "target_id": "B"})
        self.post("rule-assignments", {**assignment, "name": "Demo", "target_type": "demo",
            "target_id": demo["id"], "overrides": {rule_id: {"parameters": {"min_duration_s": 4}}}})
        source_url = f"{BASE}sources/{session.source_sha256}/"
        self.assertEqual(self.client.get(source_url).data["policy"]["assignment"]["target_type"], "demo")
        source_assignment = self.post("rule-assignments", {**assignment, "name": "Fuente", "target_type": "source",
            "target_id": session.source_sha256, "overrides": {rule_id: {"parameters": {"min_duration_s": 5}}}})
        duplicate = {key: value for key, value in source_assignment.items() if key not in {"id", "version", "updated_at"}}
        self.assertEqual(self.client.post(f"{BASE}rule-assignments/", duplicate, format="json").status_code, 409)
        source = self.client.get(source_url).data
        self.assertEqual(source["zones"][0]["rules"][0]["rule_id"], rule_id)
        self.assertEqual(source["policy"]["assignment"]["target_type"], "source")
        self.assertEqual(source["effective_rules"][0]["parameters"]["min_duration_s"], 5)
        self.assertEqual(self.client.get(source["configuration_url"]).data["effective_rules"],
                         source["effective_rules"])
        with patch.object(sessions, "load_catalog", side_effect=AssertionError("status must not load the catalog")):
            self.assertEqual(self.client.get(f"{BASE}sessions/{session.id}/status/").status_code, 200)
        launcher = Mock(wraps=subprocess)
        process = Mock()
        process.poll.return_value = None
        launcher.Popen = Mock(return_value=process)
        threads = Mock(wraps=threading)
        threads.Thread.return_value = Mock()
        with patch.object(sessions, "subprocess", launcher), patch.object(sessions, "threading", threads):
            started = self.client.post(f"{BASE}sessions/{session.id}/start/")
        self.assertEqual(started.status_code, 202, started.data)
        snapshot_id = started.data["analysis_run_id"]
        snapshot_url = f"{BASE}run-snapshots/{snapshot_id}/"
        snapshot = self.client.get(snapshot_url).data
        worker_config = (session.directory / "operational_config.json").read_bytes()
        self.assertEqual(snapshot["config_sha256"], hashlib.sha256(worker_config).hexdigest())
        self.assertEqual(snapshot["document"]["rules"][0]["parameters"]["min_duration_s"], 5)
        self.assertEqual(snapshot["document"]["rules"], source["effective_rules"])
        self.assertEqual(snapshot["policy"]["templates"][0]["version"], 1)
        self.assertNotIn("--polygon", launcher.Popen.call_args.args[0])
        self.assertEqual(self.put("rule-assignments", source_assignment, enabled=False).status_code, 200)
        self.assertEqual(self.put("rule-templates", template, name="Actualizada").status_code, 200)
        self.assertEqual(self.client.get(source_url).data["policy"]["assignment"]["target_type"], "demo")
        process.poll.return_value = 0
        sessions.remove_session(session.id)
        self.assertEqual(self.client.get(snapshot_url).data, snapshot)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(snapshot_url).status_code, 404)

    def test_preflight_blocks_incompatible_zone_without_creating_snapshot(self):
        session = self.track(self.client.post(f"{BASE}sessions/", {
            "profile": "B", "demo_source_id": "forklift_human_nearmiss",
        }, format="json"))
        template = self.template("zona_inexistente")
        rule_set = self.post("rule-sets", {"name": "Pasillo", "enabled": True,
                                         "rules": [{"template_id": template["id"]}]})
        self.post("rule-assignments", {"name": "Perfil", "enabled": True, "rule_set_id": rule_set["id"],
                                      "target_type": "profile", "target_id": "B"})
        started = self.client.post(f"{BASE}sessions/{session.id}/start/")
        self.assertEqual(started.status_code, 409, started.data)
        self.assertIn("zone_id", started.data["detail"])
        self.assertEqual(session.run, 0)
        self.assertFalse(AnalysisRunSnapshot.objects.exists())

    def test_snapshot_database_failure_preserves_previous_result(self):
        session = self.track(self.client.post(f"{BASE}sessions/", {
            "profile": "B", "demo_source_id": "forklift_human_nearmiss",
        }, format="json"))
        session.state = "completed"
        session.run = 1
        result = session.directory / "annotated.mp4"
        result.write_bytes(VIDEO)
        with patch.object(AnalysisRunSnapshot.objects, "create", side_effect=DatabaseError):
            started = self.client.post(f"{BASE}sessions/{session.id}/start/")
        self.assertEqual(started.status_code, 503, started.data)
        self.assertEqual(session.run, 1)
        self.assertEqual(result.read_bytes(), VIDEO)
