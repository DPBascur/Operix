import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient, APITestCase

from config.access import SAFETY_GROUP
from . import lab_control
from .camera_registry import inventory, media_registry, public_link
from .cameras import camera_capture_signature, default_document, run_dir, start_camera
from .models import AnalysisRunSnapshot, CameraLabControl, CameraRevision, CameraRun


class ManagedLabTests(APITestCase):
    endpoint = "/api/v1/analysis/cameras/control/"

    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = self.root = Path(folder.name)
        (root / "sample.mp4").write_bytes(b"media fixture")
        source = {"id": "lab-cam-01", "filename": "sample.mp4", "average_fps": 24, "duration_seconds": 10,
                  "footage": "real industrial CCTV", "sha256": hashlib.sha256(b"media fixture").hexdigest()}
        (root / "second.mp4").write_bytes(b"second recording")
        second = {**source, "id": "second", "filename": "second.mp4", "duration_seconds": 15,
                  "sha256": hashlib.sha256(b"second recording").hexdigest()}
        (root / "manifest.json").write_text(json.dumps({"source": {"license": "CC BY 4.0"}, "clips": [source, second]}))
        env = patch.dict(os.environ, {"OPERIX_CAMERA_LAB_ENABLED": "1", "OPERIX_CAMERA_LAB_CONTROL_DIR": str(root),
                                      "OPERIX_CAMERA_LAB_MANIFEST": str(root / "manifest.json"),
                                      "OPERIX_CAMERA_LAB_ACK_DIR": str(root / "ack")})
        env.start()
        self.addCleanup(env.stop)
        self.owner = get_user_model().objects.create(username="supervisor", is_superuser=True)
        self.admin = APIClient()
        self.admin.force_authenticate(user=self.owner)
        lab_control.ack_path("lab-cam-01").parent.mkdir(parents=True)

    def test_configuration_is_admin_only_audited_and_rejects_arbitrary_destinations(self):
        self.assertEqual(self.client.get(self.endpoint).status_code, 401)
        lead = get_user_model().objects.create(username="reviewer")
        lead.groups.add(Group.objects.create(name=SAFETY_GROUP))
        self.client.force_authenticate(user=lead)
        self.assertEqual(self.client.patch(self.endpoint, {"enabled": True}, format="json").status_code, 403)
        with patch("apps.analysis.lab_control.rtsp_ready", return_value=False):
            response = self.admin.patch(self.endpoint, {"enabled": True, "cameras": {"lab-cam-02": False}}, format="json")
            self.assertEqual(response.status_code, 202, response.content)
            self.assertEqual(response.data["status"], "partial")
            self.assertEqual(self.admin.patch(self.endpoint, {"cameras": {"../../tmp": True}}, format="json").status_code, 400)
        self.assertEqual(CameraLabControl.objects.get().updated_by, self.owner)
        self.assertTrue(LogEntry.objects.filter(user=self.owner).exists())
        self.assertEqual(self.admin.post("/api/v1/analysis/cameras/lab-cam-01/start/", {}, format="json").status_code, 409)

    def test_ordered_catalog_ids_are_audited_and_cannot_supply_paths(self):
        selected = {"media_ids": ["second", "lab-cam-01", "second"], "repeat": False}
        with patch("apps.analysis.lab_control.rtsp_ready", return_value=False):
            response = self.admin.patch(self.endpoint, {"playlists": {"lab-cam-01": selected}}, format="json")
            self.assertEqual(response.status_code, 202, response.content)
            self.assertEqual(response.data["playlists"]["lab-cam-01"], selected)
            self.assertEqual([(item["id"], item["duration_s"]) for item in response.data["catalog"]],
                             [("lab-cam-01", 10), ("second", 15)])
            for invalid in ("second.mp4", "../second.mp4", "rtsp://mediamtx:8554/lab-cam-01", {}):
                response = self.admin.patch(self.endpoint, {"playlists": {"lab-cam-01": {
                    "media_ids": [invalid], "repeat": True,
                }}}, format="json")
                self.assertEqual(response.status_code, 400, invalid)
        self.assertEqual(CameraLabControl.objects.get().playlists["lab-cam-01"], selected)
        self.assertEqual(json.loads(LogEntry.objects.get().change_message)["playlists"]["lab-cam-01"], selected)

    def test_demonstration_requires_the_exact_reviewed_recording_configuration(self):
        scenarios = json.loads(lab_control.DEMONSTRATION_SCENARIOS.read_bytes())
        selections = (("01", "proximity"), ("01", "dwell"), ("02", "entry"), ("03", "negative"))
        catalog, captures, revisions = {}, {}, {}
        for slot, name in selections:
            scenario = scenarios[name]
            camera = f"lab-cam-{slot}"
            media = scenario["media_id"]
            digest = scenario["source_sha256"]
            catalog[media] = {"sha256": digest}
            captures[(camera, media)] = name
            revisions[(camera, name)] = SimpleNamespace(
                demonstration=True, source_sha256=digest,
                document={"schema_version": 1, "view_id": camera, "coordinate_system": "normalized",
                          "zones": [scenario["zone"]], "rules": [scenario["rule"]]},
            )
        plan = lab_control.demonstration_playlists(catalog, captures, revisions)
        self.assertEqual(plan["lab-cam-01"], {"media_ids": ["onal-7-tr21", "nvidia-w026-c00"], "repeat": True})
        self.assertTrue(plan["lab-cam-02"]["repeat"])
        revisions[("lab-cam-03", "negative")].document = {}
        self.assertIsNone(lab_control.demonstration_playlists(catalog, captures, revisions))

    def test_stopped_camera_configuration_matches_first_assigned_recording(self):
        camera = inventory()["lab-cam-01"]
        catalog, _ = media_registry()
        CameraLabControl.objects.create(
            pk=1, enabled=False, updated_by=self.owner,
            playlists={camera.id: {"media_ids": ["second", camera.id], "repeat": True}},
        )
        url = f"/api/v1/analysis/cameras/{camera.id}/"
        result = self.admin.get(url)
        self.assertEqual(result.data["provenance"]["sha256"], catalog["second"]["sha256"])
        document = default_document(camera)
        document["zones"][0]["polygon"] = [[0, 0], [.5, 0], [.5, .5], [0, .5]]
        saved = self.admin.put(url, {"revision": 0, "document": document}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(
            CameraRevision.objects.get(camera_id=camera.id).capture_signature,
            camera_capture_signature(replace(camera, provenance=catalog["second"])),
        )

    def test_recording_revisions_remain_bound_across_playlist_switches(self):
        camera = inventory()["lab-cam-01"]
        catalog, _ = media_registry()
        docs = {}
        for media_id in (camera.id, "second"):
            url = f"/api/v1/analysis/cameras/{camera.id}/recordings/{media_id}/"
            row = self.admin.get(url).data
            self.assertEqual(row["recording_review"]["state"], "unreviewed")
            document = default_document(camera)
            document["zones"][0]["name"] = media_id
            payload = {"revision": row["revision"], "source_sha256": catalog[media_id]["sha256"],
                       "document": document, "demonstration": True}
            self.assertEqual(self.admin.put(url, {**payload, "source_sha256": "a" * 64}, format="json").status_code, 409)
            saved = self.admin.put(url, payload, format="json")
            self.assertEqual(saved.status_code, 200, saved.data)
            self.assertEqual(self.admin.put(url, payload, format="json").status_code, 409)
            docs[media_id] = saved.data
        with (self.settings(EVENT_POST_ENABLED=True, MEDIA_ROOT=self.root),
              patch.dict(os.environ, {"OPERIX_PERSON_WEIGHTS": "person", "OPERIX_FORKLIFT_WEIGHTS": "forklift",
                                      "OPERIX_RTSP_INFERENCE_SOCKET": ""}),
              patch("apps.analysis.cameras.camera_worker_destination", return_value=("10.0.0.2", "rtsp://10.0.0.2/live")),
              patch("apps.analysis.cameras.subprocess") as worker,
              patch("apps.analysis.cameras.Thread"),
              patch("apps.analysis.cameras._processes", {})):
            worker.Popen.return_value.poll.return_value = None
            for media_id in (camera.id, "second", camera.id):
                selected = replace(camera, provenance=catalog[media_id])
                run_id = start_camera(selected, self.owner, managed=True,
                    playback={"token": uuid4().hex, "media_id": media_id})
                run = CameraRun.objects.get(pk=run_id)
                self.assertEqual(run.snapshot.spatial_revision, docs[media_id]["revision"])
                self.assertEqual(run.snapshot.configuration, docs[media_id]["configuration"])
                self.assertTrue(run.playback["demonstration"])
                self.assertNotIn("spatial_suspension_reason", run.playback)
                CameraRun.objects.filter(pk=run_id).update(active=False, terminal_state="stopped")
            self.assertEqual(CameraRun.objects.count(), 3)

    def test_opt_in_third_slot_uses_catalog_and_is_disabled_by_default(self):
        camera_id = "lab-cam-03"
        self.assertNotIn(camera_id, inventory())
        self.assertEqual(self.admin.patch(self.endpoint, {"cameras": {camera_id: True}}, format="json").status_code, 400)
        with patch.dict(os.environ, {"OPERIX_CAMERA_LAB_THIRD_SLOT": "1", "OPERIX_CAMERA_LAB_CAPACITY": "2"}), \
                patch.object(lab_control, "rtsp_ready", return_value=False):
            result = self.admin.get(self.endpoint)
            third = next(row for row in result.data["cameras"] if row["id"] == camera_id)
            self.assertFalse(third["enabled"])
            self.assertTrue(third["view_only"])
            self.assertEqual(result.data["capacity"], 2)
            self.assertEqual(result.data["playlists"][camera_id]["media_ids"], [])
            selected = {"media_ids": ["second"], "repeat": False}
            response = self.admin.patch(self.endpoint, {"cameras": {camera_id: True}, "playlists": {camera_id: selected}}, format="json")
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.data["playlists"][camera_id], selected)
            forged = {"media_ids": ["rtsp://example.invalid/source"], "repeat": True}
            self.assertEqual(self.admin.patch(self.endpoint, {"playlists": {camera_id: forged}}, format="json").status_code, 400)
            self.assertEqual(self.client.get("/api/v1/analysis/cameras/lab-cam-03/live/index.m3u8").status_code, 401)

    def test_invalid_playback_position_is_ignored_and_restarted(self):
        camera_id = "lab-cam-01"
        camera = inventory()[camera_id]
        catalog, _ = media_registry()
        playlist = {"media_ids": [camera_id], "repeat": True}
        signature = lab_control.playlist_signature(playlist, catalog)
        for position in (1, -1, "0", True, None):
            with self.subTest(position=position), patch.object(lab_control, "rtsp_ready", return_value=False):
                progress = lab_control.new_attempt(signature, position)
                CameraLabControl.objects.update_or_create(pk=lab_control.CONTROL_ID, defaults={
                    "enabled": True, "playlists": {camera_id: playlist}, "playback": {camera_id: progress},
                })
                response = self.admin.get(self.endpoint)
                self.assertEqual(response.status_code, 200)
                row = next(row for row in response.data["cameras"] if row["id"] == camera_id)
                self.assertEqual(row["playlist_position"], 0)
                self.assertEqual(CameraLabControl.objects.get().playback[camera_id], progress)

                restarted = lab_control.reconcile_slot(camera_id, camera, playlist, catalog, progress, None, self.owner)
                self.assertEqual(restarted["position"], 0)
                self.assertNotEqual(restarted["token"], progress["token"])

    def test_third_slot_video_only_reconciles_eof_without_a_worker(self):
        with patch.dict(os.environ, {"OPERIX_CAMERA_LAB_THIRD_SLOT": "1", "OPERIX_CAMERA_LAB_CAPACITY": "2"}):
            camera_id = "lab-cam-03"
            camera = inventory()[camera_id]
            catalog, _ = media_registry()
            playlist = {"media_ids": ["second", "lab-cam-01"], "repeat": False}
            signature = lab_control.playlist_signature(playlist, catalog)
            progress = {**lab_control.new_attempt(signature), "phase": "play", "launch_at": time()}
            with patch.object(lab_control, "publisher_ack", return_value="playing") as ack, \
                    patch.object(lab_control, "start_camera", side_effect=AssertionError("video-only starts no worker")):
                playing = lab_control.reconcile_slot(camera_id, camera, playlist, catalog, progress, None, self.owner)
                self.assertTrue(playing["view_started"])
                ack.return_value = "eof"
                following = lab_control.reconcile_slot(camera_id, camera, playlist, catalog, playing, None, self.owner)
                self.assertEqual(following["position"], 1)
                self.assertEqual(following["last_transition"]["reason"], "media_eof")
                self.assertNotEqual(following["token"], playing["token"])
                stopped = lab_control.reconcile_slot(camera_id, camera, None, catalog, following, None, self.owner)
                self.assertEqual(stopped, {})
                self.assertFalse(lab_control.marker(camera_id).exists())
            self.assertFalse(CameraRun.objects.filter(camera_id=camera_id).exists())
    def test_patch_verifier_rejects_wrong_digest(self):
        camera = inventory()["lab-cam-01"]
        (self.root / "sample.mp4").write_bytes(b"wrong digest")
        with self.assertRaisesRegex(ValueError, "inventario"):
            lab_control.approved_media(camera)

    def test_catalog_removes_paths_and_camera_links_drop_tokens(self):
        path = self.root / "manifest.json"
        document = json.loads(path.read_text())
        document["clips"][0].update(title=r"C:\private\sample.mp4", scenario="Recorded at /srv/private",
                                    author="https://user:password@publisher.example/",
                                    source_file_url="https://publisher.example/study?access=secret#token",
                                    license_url="file:///etc/private", license="CC BY 4.0")
        path.write_text(json.dumps(document))
        with patch("apps.analysis.lab_control.rtsp_ready", return_value=False):
            catalog = self.admin.get(self.endpoint).data["catalog"]
        self.assertEqual(catalog[0]["title"], "sample.mp4")
        self.assertIsNone(catalog[0]["scenario"])
        provenance = self.admin.get("/api/v1/analysis/cameras/lab-cam-01/").data["provenance"]
        self.assertEqual(provenance["source_url"], "https://publisher.example/study")
        self.assertIsNone(provenance["author"])
        self.assertIsNone(provenance["license_url"])

    def test_public_links_reject_credentials_private_hosts_and_encoded_paths(self):
        for url in ("http://127.0.0.1/report", "https://server.local/report",
                    "https://user:password@example.com/report", "https://example.com/C:%5cprivate",
                    "https://example.com/%2fetc/passwd", "https://example.com/%252fetc/passwd"):
            with self.subTest(url=url):
                self.assertIsNone(public_link(url))

    def test_catalog_and_patch_reject_unsupported_or_unknown_duration(self):
        path = self.root / "manifest.json"
        document = json.loads(path.read_text())
        for duration in (1801, None):
            with self.subTest(duration=duration), patch("apps.analysis.lab_control.rtsp_ready", return_value=False):
                document["clips"][1]["duration_seconds"] = duration
                path.write_text(json.dumps(document))
                result = self.admin.patch(self.endpoint, {"playlists": {"lab-cam-01": {
                    "media_ids": ["second"], "repeat": True,
                }}}, format="json")
                self.assertEqual(result.status_code, 400)
                self.assertIn(str(lab_control.MAX_CLIP_SECONDS), result.content.decode())
                self.assertNotIn("second", [clip["id"] for clip in self.admin.get(self.endpoint).data["catalog"]])

    def test_saved_oversized_media_stays_blocked_without_a_publisher_lease(self):
        control = self.configure()
        control.playlists["lab-cam-01"]["media_ids"] = ["second"]
        control.save(update_fields=["playlists"])
        path = self.root / "manifest.json"
        document = json.loads(path.read_text())
        document["clips"][1]["duration_seconds"] = 1801
        path.write_text(json.dumps(document))
        with patch("apps.analysis.lab_control.checked_hash", side_effect=AssertionError("hash under scheduler lock")):
            for _ in range(4):
                lab_control.reconcile()
        self.assertEqual(self.progress()["phase"], "duration_blocked")
        self.assertEqual(self.progress()["last_transition"]["reason"], "unsupported_duration")
        self.assertFalse(lab_control.marker("lab-cam-01").exists())

    @patch("apps.analysis.lab_control.rtsp_ready", return_value=False)
    def test_patch_hashes_before_scheduler_lock_and_get_does_not_hash(self, ready):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        original_hash = lab_control.checked_hash
        with CaptureQueriesContext(connection) as queries:
            def observe(path, identity):
                self.assertFalse(any("pg_advisory_xact_lock" in query["sql"] for query in queries))
                return original_hash(path, identity)

            with patch("apps.analysis.lab_control.checked_hash", side_effect=observe) as verify:
                response = self.admin.patch(self.endpoint, {"enabled": True, "playlists": {"lab-cam-01": {
                    "media_ids": ["second"], "repeat": False,
                }}}, format="json")
            self.assertEqual(response.status_code, 202)
            verify.assert_called_once()
        with patch("apps.analysis.lab_control.checked_hash", side_effect=AssertionError("unexpected hash")):
            self.assertEqual(self.admin.get(self.endpoint).status_code, 200)
            for _ in range(4):
                lab_control.reconcile()

    def test_lab_trial_provenance_keeps_its_distinction_from_industrial_cctv(self):
        path = self.root / "manifest.json"
        document = json.loads(path.read_text())
        document["clips"][0]["footage"] = "real recorded logistics trial"
        path.write_text(json.dumps(document))
        camera = inventory()["lab-cam-01"]
        self.assertEqual(camera.provenance["footage"], "real recorded logistics trial")
        self.assertEqual(lab_control.approved_media(camera)[0], "sample.mp4")

    def test_existing_sparl_manifest_provides_legacy_default_ids(self):
        root = Path(__file__).resolve().parents[3]
        with patch.dict(os.environ, {"OPERIX_CAMERA_LAB_MANIFEST": str(root / "deployment/rtsp-lab/sparl-catalog.v1.json")}):
            catalog, defaults = media_registry()
        self.assertEqual(defaults, {"lab-cam-01": "lab-cam-01", "lab-cam-02": "lab-cam-02"})
        self.assertEqual(catalog["lab-cam-02"]["duration_s"], 466.866667)
        self.assertTrue(catalog["lab-cam-02"]["real"])

    def test_spawn_freezes_selected_source_and_frame_independent_configuration(self):
        source = media_registry()[0]["second"]
        camera = replace(inventory()["lab-cam-01"], provenance=source, source_fps=24)
        playback = {"media_id": "second", "source_sha256": source["sha256"], "position": 1, "token": uuid4().hex}
        with (self.settings(EVENT_POST_ENABLED=True, MEDIA_ROOT=self.root),
              patch.dict(os.environ, {"OPERIX_PERSON_WEIGHTS": "person", "OPERIX_FORKLIFT_WEIGHTS": "forklift",
                                      "OPERIX_RTSP_INFERENCE_SOCKET": ""}),
              patch("apps.analysis.cameras.camera_worker_destination", return_value=("10.0.0.2", "rtsp://10.0.0.2/live")),
              patch("apps.analysis.cameras.subprocess") as worker,
              patch("apps.analysis.cameras.Thread"),
              patch("apps.analysis.cameras._processes", {})):
            run_id = start_camera(camera, self.owner, managed=True, playback=playback)
            context = json.loads((run_dir(run_id) / "context.json").read_text())
        args = worker.Popen.call_args.args[0]
        self.assertEqual(args[args.index("--fps") + 1], str(camera.expected_fps))
        self.assertEqual(args[args.index("--source-fps") + 1], str(camera.capture_fps))
        run = CameraRun.objects.get(pk=run_id)
        self.assertEqual(run.snapshot.source_sha256, source["sha256"])
        self.assertEqual(run.provenance, source)
        self.assertEqual(context["source"]["video_sha256"], source["sha256"])
        self.assertEqual(context["source"]["filename"], "second.mp4")
        self.assertEqual(context["source"]["spatial_configuration"], run.snapshot.configuration)
        self.assertEqual(run.snapshot.configuration["rules"], [])
        self.assertIn("spatial_suspension_reason", run.playback)

    def test_spawn_uses_custom_geometry_only_with_a_matching_signature(self):
        camera = inventory()["lab-cam-01"]
        document = default_document(camera)
        document["zones"][0]["polygon"][1] = [.5, 0]
        signature = camera_capture_signature(camera)
        for revision, capture_signature in enumerate(("", signature), start=1):
            with self.subTest(capture_signature=capture_signature):
                saved = CameraRevision.objects.create(camera_id=camera.id, revision=revision,
                                                      document=document, capture_signature=capture_signature)
                playback = {"token": uuid4().hex, "source_sha256": camera.provenance["sha256"]}
                with (self.settings(EVENT_POST_ENABLED=True, MEDIA_ROOT=self.root),
                      patch.dict(os.environ, {"OPERIX_PERSON_WEIGHTS": "person", "OPERIX_FORKLIFT_WEIGHTS": "forklift",
                                              "OPERIX_RTSP_INFERENCE_SOCKET": ""}),
                      patch("apps.analysis.cameras.camera_worker_destination", return_value=("10.0.0.2", "rtsp://10.0.0.2/live")),
                      patch("apps.analysis.cameras.subprocess") as worker,
                      patch("apps.analysis.cameras.Thread"),
                      patch("apps.analysis.cameras._processes", {})):
                    run_id = start_camera(camera, self.owner, managed=True, playback=playback)
                worker.Popen.assert_called_once()
                run = CameraRun.objects.get(pk=run_id)
                self.assertEqual(run.snapshot.spatial_revision, revision if capture_signature else None)
                if capture_signature:
                    self.assertEqual(run.snapshot.configuration, document)
                    self.assertNotIn("spatial_suspension_reason", run.playback)
                else:
                    self.assertEqual(run.snapshot.configuration["rules"], [])
                    self.assertFalse(run.snapshot.configuration["zones"][0]["enabled"])
                    self.assertIn("spatial_suspension_reason", run.playback)
                saved.refresh_from_db()
                self.assertEqual(saved.capture_signature, capture_signature)
                self.assertEqual(saved.document, document)
                CameraRun.objects.filter(pk=run_id).update(active=False, terminal_state="stopped")

    def test_live_camera_reports_the_run_snapshot_to_any_authorized_reviewer(self):
        rules = [{"rule_id": "effective-rule", "version": 2, "enabled": True}]
        policy = {"rule_set": {"name": "Assigned when started", "version": 2}}
        provenance = {"filename": "started.mp4", "title": "/var/lib/secret",
                      "source_url": "https://user:password@example.com/article",
                      "license_url": "https://creativecommons.org/licenses/by/4.0/",
                      "local_path": "/private/run"}
        run = SimpleNamespace(pk=self.owner.pk, active=True, provenance=provenance,
                              snapshot=SimpleNamespace(configuration={"rules": rules}, policy=policy))
        with (patch("apps.analysis.cameras.last_run", return_value=run),
              patch("apps.analysis.cameras.status_for", return_value=("analyzing", {}, None)),
              patch("apps.analysis.cameras.calibration_issue", return_value=None)):
            response = self.admin.get("/api/v1/analysis/cameras/lab-cam-01/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["effective_rules"], rules)
        self.assertEqual(response.data["policy"], policy)
        self.assertEqual(response.data["provenance"]["filename"], "started.mp4")
        self.assertEqual(response.data["provenance"]["title"], "started.mp4")
        self.assertIsNone(response.data["provenance"]["source_url"])
        self.assertEqual(response.data["provenance"]["license_url"], provenance["license_url"])
        self.assertNotIn("local_path", response.data["provenance"])
        self.assertEqual(run.provenance["title"], "/var/lib/secret")
        self.assertIsNone(response.data["preview_url"])

    def progress(self):
        return CameraLabControl.objects.get().playback["lab-cam-01"]

    def lease(self):
        return lab_control.marker("lab-cam-01").read_text().split()

    def ack(self, token, state):
        lab_control.ack_path("lab-cam-01").write_text(f"{token} {state}\n", encoding="ascii")

    def configure(self, *, repeat=False):
        return CameraLabControl.objects.create(pk=1, enabled=True, cameras={"lab-cam-02": False},
                                               playlists={"lab-cam-01": {
                                                   "media_ids": ["lab-cam-01", "second"], "repeat": repeat,
                                               }}, updated_by=self.owner)

    def simulate_worker(self, camera, owner, *, managed, playback):
        snapshot = AnalysisRunSnapshot.objects.create(pk=uuid4(), owner=owner, profile=camera.profile,
                                                       source_sha256=camera.provenance["sha256"],
                                                       configuration=default_document(camera), config_sha256="a" * 64)
        return CameraRun.objects.create(snapshot=snapshot, camera_id=camera.id, managed=managed,
                                        provenance=camera.provenance, playback=playback)

    def launch_clip(self, ready, token=None):
        ready.return_value = False
        if token is None:
            lab_control.reconcile()
            token = self.progress()["token"]
        self.assertEqual(self.lease(), [token, "idle"])
        self.ack(token, "idle")
        ready.return_value = True
        lab_control.reconcile()
        self.assertEqual(self.lease(), [token, "idle"])
        self.assertFalse(CameraRun.objects.filter(active=True).exists())
        ready.return_value = False
        lab_control.reconcile()
        run = CameraRun.objects.get(active=True)
        self.assertEqual(self.progress()["phase"], "warming")
        with patch.object(lab_control, "status_for", return_value=("connecting", {}, {})):
            lab_control.reconcile()
            self.assertEqual(self.lease(), [token, "idle"])
        with patch.object(lab_control, "status_for", return_value=("connecting", {}, {"capture_ready": True})):
            lab_control.reconcile()
        self.assertEqual(self.lease()[:2], [token, "play"])
        self.ack(token, "playing")
        ready.return_value = True
        lab_control.reconcile()
        self.assertEqual(self.progress()["phase"], "play")
        return run

    @patch("apps.analysis.lab_control.stop_camera")
    @patch("apps.analysis.lab_control.rtsp_ready")
    def test_waits_for_old_worker_and_token_ack_then_finishes_ordered_playlist(self, ready, stop):
        self.configure()
        def worker_state(run):
            return ("analyzing", {"frames_processed": 4}, None) if run and run.active else (
                "stopped", {}, {"termination_reason": "OPERATOR_STOP"})

        with (patch("apps.analysis.lab_control.status_for", side_effect=worker_state),
              patch("apps.analysis.lab_control.checked_hash", side_effect=AssertionError("hash during rotation")),
              patch("apps.analysis.lab_control.start_camera", side_effect=self.simulate_worker) as start):
            lab_control.reconcile()
            first = self.launch_clip(ready)
            self.assertEqual(first.provenance["filename"], "sample.mp4")
            self.ack(first.playback["token"], "eof")
            lab_control.reconcile()
            stop.assert_called_once()
            pending = self.progress()["pending"]["token"]
            self.assertNotEqual(pending, first.playback["token"])
            self.ack(pending, "idle")
            lab_control.reconcile()
            self.assertEqual(self.progress()["position"], 0)
            self.assertEqual(self.lease(), [pending, "idle"])
            self.assertEqual(start.call_count, 1)
            first.active = False
            first.save(update_fields=["active"])
            lab_control.reconcile()
            first.refresh_from_db()
            self.assertEqual(first.playback["transition"]["reason"], "media_eof")
            self.assertEqual(first.playback["transition"]["outcome"], "expected")
            self.assertEqual(self.progress()["position"], 1)
            self.assertEqual(self.lease(), [pending, "idle"])
            self.assertEqual(self.progress()["token"], pending)
            self.assertNotEqual(self.lease()[0], first.playback["token"])
            next_run = self.launch_clip(ready, token=pending)
            self.assertEqual(next_run.provenance["filename"], "second.mp4")
            self.assertNotEqual(next_run.snapshot.source_sha256, first.snapshot.source_sha256)
            self.ack(next_run.playback["token"], "eof")
            lab_control.reconcile()
            next_run.active = False
            next_run.save(update_fields=["active"])
            lab_control.reconcile()
            lab_control.reconcile()
            self.assertEqual(start.call_count, 2)
            self.assertEqual(self.progress()["phase"], "finished")
            self.assertFalse(lab_control.marker("lab-cam-01").exists())
            self.assertEqual(self.admin.get(self.endpoint).data["status"], "finished")
            self.admin.patch(self.endpoint, {"enabled": False}, format="json")
            self.admin.patch(self.endpoint, {"enabled": True}, format="json")
            lab_control.reconcile()
            self.assertEqual((self.progress()["phase"], self.progress()["position"]), ("idle", 0))

    @patch("apps.analysis.lab_control.status_for", return_value=("stopped", {}, {"termination_reason": "TIME_LIMIT"}))
    def test_worker_deadline_blocks_mislabeled_media_instead_of_replaying(self, status):
        control = self.configure(repeat=True)
        catalog, _ = media_registry()
        camera = inventory()["lab-cam-01"]
        progress = lab_control.new_attempt(lab_control.playlist_signature(control.playlists[camera.id], catalog))
        run = self.simulate_worker(camera, self.owner, managed=True, playback={
            "token": progress["token"], "media_id": "lab-cam-01", "position": 0, "cycle": 0,
        })
        run.active = False
        run.save(update_fields=["active"])
        control.playback = {camera.id: progress}
        control.save(update_fields=["playback"])
        lab_control.update_lease(camera.id, (progress["token"], "play", "sample.mp4", camera.provenance["sha256"]))
        lab_control.reconcile()
        blocked = self.progress()
        lab_control.reconcile()
        self.assertEqual(self.progress(), blocked)
        self.assertEqual(blocked["phase"], "duration_blocked")
        self.assertEqual(blocked["last_transition"]["reason"], "duration_exceeded")
        self.assertFalse(lab_control.marker(camera.id).exists())

    @patch("apps.analysis.lab_control.stop_camera")
    @patch("apps.analysis.lab_control.rtsp_ready")
    def test_interruption_retries_same_position_with_fresh_token(self, ready, stop):
        self.configure(repeat=True)
        with (patch("apps.analysis.lab_control.status_for", side_effect=lambda run: (
            "analyzing" if run and run.active else "stopped", {"frames_processed": 4},
            {"termination_reason": "OPERATOR_STOP"})),
              patch("apps.analysis.lab_control.start_camera", side_effect=self.simulate_worker)):
            lab_control.reconcile()
            run = self.launch_clip(ready)
            self.ack(run.playback["token"], "failed")
            lab_control.reconcile()
            stop.assert_called_once()
            run.active = False
            run.save(update_fields=["active"])
            lab_control.reconcile()
            progress = self.progress()
            self.assertEqual(progress["position"], 0)
            self.assertNotEqual(progress["token"], run.playback["token"])
            self.assertGreater(progress["retry_at"], time())
            self.assertEqual(progress["failures"], 1)
            self.assertEqual(progress["last_transition"]["reason"], "publisher_interrupted")
            self.assertEqual(progress["last_transition"]["outcome"], "interrupted")

    @patch("apps.analysis.lab_control.time", return_value=1000.)
    def test_retry_delay_grows_only_after_repeated_failure(self, clock):
        delays = [lab_control.new_attempt("signature", failures=i)["retry_at"] - clock.return_value
                  for i in range(1, lab_control.MAX_RETRY_ATTEMPTS + 1)]
        self.assertEqual(delays, [1, 2, 4, 8, 16, 30])
        self.assertEqual(lab_control.new_attempt("signature")["retry_at"], 0)

    def test_repeat_wraps_to_first_position_after_last_clip(self):
        control = self.configure(repeat=True)
        catalog, _ = media_registry()
        playlist = control.playlists["lab-cam-01"]
        progress = lab_control.new_attempt(lab_control.playlist_signature(playlist, catalog), 1, 2)
        run = self.simulate_worker(inventory()["lab-cam-01"], self.owner, managed=True, playback={
            "token": progress["token"], "position": 1, "cycle": 2, "media_id": "second",
            "transition": {"outcome": "expected", "reason": "media_eof"},
        })
        run.active = False
        run.save(update_fields=["active"])
        control.playback = {"lab-cam-01": progress}
        control.save(update_fields=["playback"])
        lab_control.reconcile()
        self.assertEqual((self.progress()["position"], self.progress()["cycle"]), (0, 3))

    @patch("apps.analysis.lab_control.stop_camera")
    @patch("apps.analysis.lab_control.status_for", return_value=("analyzing", {}, None))
    def test_does_not_take_over_manual_run(self, status, stop):
        self.configure()
        camera = inventory()["lab-cam-01"]
        manual = self.simulate_worker(camera, self.owner, managed=False, playback={})
        lab_control.update_lease(camera.id, (uuid4().hex, "idle"))
        lab_control.reconcile()
        manual.refresh_from_db()
        self.assertTrue(manual.active)
        self.assertFalse(lab_control.marker(camera.id).exists())
        stop.assert_not_called()

    def test_rejects_stale_live_acknowledgement(self):
        token = uuid4().hex
        self.ack(token, "playing")
        stale = time() - lab_control.LEASE_SECONDS - 1
        os.utime(lab_control.ack_path("lab-cam-01"), (stale, stale))
        self.assertIsNone(lab_control.publisher_ack("lab-cam-01", token))

    @patch("apps.analysis.lab_control.rtsp_ready")
    def test_bound_custom_zones_suspend_rules_but_publish_other_viewpoint(self, ready):
        control = self.configure()
        camera = inventory()["lab-cam-01"]
        document = default_document(camera)
        document["zones"][0]["polygon"][1] = [.5, 0]
        CameraRevision.objects.create(camera_id=camera.id, revision=1, document=document,
                                      capture_signature=camera_capture_signature(camera))
        control.playlists[camera.id]["media_ids"] = ["second"]
        control.save(update_fields=["playlists"])
        with (self.settings(EVENT_POST_ENABLED=True, MEDIA_ROOT=self.root),
              patch.dict(os.environ, {"OPERIX_PERSON_WEIGHTS": "person", "OPERIX_FORKLIFT_WEIGHTS": "forklift",
                                      "OPERIX_RTSP_INFERENCE_SOCKET": ""}),
              patch("apps.analysis.cameras.camera_worker_destination", return_value=("10.0.0.2", "rtsp://10.0.0.2/live")),
              patch("apps.analysis.cameras.subprocess") as worker,
              patch("apps.analysis.cameras.Thread"),
              patch("apps.analysis.cameras._processes", {})):
            worker.Popen.return_value.poll.return_value = None
            lab_control.reconcile()
            run = self.launch_clip(ready)
            row = self.admin.get(self.endpoint).data["cameras"][0]
            worker_config = json.loads((run_dir(run.pk) / "config.json").read_bytes())
        worker.Popen.assert_called_once()
        self.assertFalse(row["playlist_blocked"])
        self.assertIn("spatial_suspension_reason", row["playback"])
        self.assertEqual(row["effective_rules"], [])
        self.assertEqual(row["recording_review"]["state"], "unreviewed")
        self.assertNotEqual(row["configuration"]["zones"], document["zones"])
        self.assertEqual(worker_config, run.snapshot.configuration)
        self.assertEqual(worker_config["rules"], [])
        self.assertFalse(worker_config["zones"][0]["enabled"])
        self.assertEqual(run.provenance["filename"], "second.mp4")
        self.assertEqual(run.snapshot.source_sha256, run.provenance["sha256"])
