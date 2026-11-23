from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from uuid import uuid4

from operix_engine.clip_capacity import exclusive_file_slot, publish_clip
from operix_engine.rtsp_lab_clips import ClipStore, RETENTION_SCOPE
from operix_engine.rtsp_lab_policy import CameraRateBudget, EventAdmission, EventPolicy, InvalidEventPolicy, MAX_PENDING
from operix_engine.rules import EventCandidate, InteractionIdentity, PairEventCandidate
from operix_engine.spatiotemporal import ObjectIdentity


class AdmissionTests(TestCase):
    def setUp(self):
        self.media_root = Path(self.enterContext(TemporaryDirectory()))
        self.wall_clock = 1_800_000_000.

    def budget(self, camera="lab-cam-01"):
        return CameraRateBudget(self.media_root, camera, clock=lambda: self.wall_clock)

    def test_rolling_rate_expires_and_has_no_run_quota(self):
        admission = EventAdmission(EventPolicy(events_per_minute=2), rate_budget=self.budget())
        candidate = EventCandidate("dwell", 1, 1, 1., 1, "person", "zone", {}, True, 1.)
        started_at = self.wall_clock
        for minute in range(11):
            self.wall_clock = started_at + minute * 60
            for index in range(2):
                submitted = minute * 2 + index
                next_candidate = replace(candidate, frame_index=submitted)
                self.assertIsNone(admission.suppress(next_candidate, now=minute * 60., submitted=submitted, pending=0))
            self.assertEqual(admission.suppress(candidate, now=minute * 60. + 59.99,
                                                submitted=minute * 2 + 2, pending=0),
                             "episode_duplicate" if minute < 2 else "rate_limit")
        self.assertTrue(admission.has_quota(22))
        self.assertLessEqual(len(admission.episodes), 4)

    def test_pair_episode_uses_start_frame_and_epoch(self):
        pair = InteractionIdentity(ObjectIdentity("person", 1), ObjectIdentity("forklift", 1))
        event = PairEventCandidate("proximity", 1, 10, 1., pair, "zone", {}, 8, .8, .1, .2, epoch=1)
        admission = EventAdmission(EventPolicy(dedup_seconds=10), rate_budget=self.budget())
        self.assertEqual(admission.suppress(event, now=0., submitted=0, pending=MAX_PENDING), "backpressure")
        self.assertIsNone(admission.suppress(event, now=1., submitted=0, pending=0))
        duplicate = replace(event, frame_index=11, timestamp_s=1.1)
        self.assertEqual(admission.suppress(duplicate, now=2., submitted=1, pending=0), "episode_duplicate")
        self.assertIsNone(admission.suppress(replace(event, started_frame_index=9), now=3., submitted=1, pending=0))
        self.assertIsNone(admission.suppress(replace(event, epoch=2), now=4., submitted=2, pending=0))
        self.assertIsNone(admission.suppress(duplicate, now=11., submitted=3, pending=0))

    def test_segment_rotations_and_worker_restart_share_only_the_camera_rate(self):
        policy = EventPolicy(events_per_minute=2)
        candidate = EventCandidate("dwell", 1, 1, 1., 1, "person", "zone", {}, True, 1., epoch=1)

        def start_segment(camera="lab-cam-01"):
            # The process-local clock, episode identities and submitted count all
            # start over. Only the shared volume carries state into a new run.
            admission = EventAdmission(policy, rate_budget=self.budget(camera))
            return admission.suppress(candidate, now=0., submitted=0, pending=0)

        self.assertIsNone(start_segment())
        self.wall_clock += 10
        self.assertIsNone(start_segment())  # Reused track and episode IDs in a different run.
        self.wall_clock += 10
        self.assertEqual(start_segment(), "rate_limit")
        self.assertIsNone(start_segment("lab-cam-02"))
        self.wall_clock += 40
        self.assertIsNone(start_segment())
        self.assertEqual(start_segment(), "rate_limit")

    def test_concurrent_reservations_do_not_exceed_camera_budget(self):
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda _: self.budget().reserve(3), range(12)))
        self.assertEqual(sum(results), 3)

    def test_fresh_process_respects_reservation_until_wall_clock_expiry(self):
        self.assertTrue(self.budget().reserve(1))
        script = """
from pathlib import Path
import sys
from operix_engine.rtsp_lab_policy import CameraRateBudget
budget = CameraRateBudget(Path(sys.argv[1]), "lab-cam-01", clock=lambda: float(sys.argv[2]))
print(budget.reserve(1))
"""
        for offset, expected in ((59.99, "False"), (60, "True")):
            with self.subTest(offset=offset):
                result = subprocess.run(
                    [sys.executable, "-c", script, str(self.media_root), str(self.wall_clock + offset)],
                    capture_output=True, text=True, check=True, timeout=10,
                )
                self.assertEqual(result.stdout.strip(), expected)

    def test_unavailable_budget_suppresses_without_marking_episode(self):
        budget = self.budget()
        admission = EventAdmission(EventPolicy(), rate_budget=budget)
        candidate = EventCandidate("dwell", 1, 1, 1., 1, "person", "zone", {}, True, 1.)
        budget.path.write_bytes(b"broken database")
        self.assertEqual(admission.suppress(candidate, now=0., submitted=0, pending=0), "rate_unavailable")
        self.assertEqual(admission.episodes, {})
        budget.path.unlink()
        self.assertIsNone(admission.suppress(candidate, now=1., submitted=0, pending=0))

    def test_only_explicit_benchmark_uses_quota_and_operational_config_is_validated(self):
        self.assertIsNone(EventPolicy.from_env({}).status()["event_limit"])
        benchmark = EventPolicy.from_env({"OPERIX_RTSP_LAB_EVENT_POLICY": "benchmark",
                                          "OPERIX_RTSP_LAB_CLIP_RETENTION_DAYS": "365"})
        self.assertEqual(benchmark.status()["event_limit"], 20)
        self.assertEqual(benchmark.status()["clip_retention_days"], 0)
        configured = EventPolicy.from_env({"OPERIX_RTSP_LAB_EVENTS_PER_MINUTE": "10",
                                           "OPERIX_RTSP_LAB_EVENT_DEDUP_SECONDS": "30",
                                           "OPERIX_RTSP_LAB_PNG_TOTAL_BYTES": "200",
                                           "OPERIX_RTSP_LAB_CLIP_TOTAL_BYTES": "400",
                                           "OPERIX_RTSP_LAB_CLIP_RETENTION_DAYS": "7"})
        self.assertEqual(configured, EventPolicy("operational", 10, 30, 200, 400, 7))
        for name, value in (("EVENT_POLICY", "typo"), ("EVENTS_PER_MINUTE", "0"), ("CLIP_RETENTION_DAYS", "-1"),
                            ("CLIP_TOTAL_BYTES", "nan")):
            with self.subTest(name=name), self.assertRaisesRegex(InvalidEventPolicy, name):
                EventPolicy.from_env({f"OPERIX_RTSP_LAB_{name}": value})


class EvidenceStorageTests(TestCase):
    def test_clip_publication_respects_capacity_lock_in_another_process(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scratch = root / ".clip-staged"
            scratch.mkdir()
            (scratch / "clip.mp4").write_bytes(b"clip")
            destination = root / str(uuid4()) / str(uuid4())
            script = """
from pathlib import Path
import sys
from operix_engine.clip_capacity import publish_clip
root, scratch, destination = map(Path, sys.argv[1:])
print(publish_clip(root, scratch, destination, total_bytes=4))
"""
            with exclusive_file_slot(root / ".capacity.lock") as acquired:
                self.assertTrue(acquired)
                result = subprocess.run(
                    [sys.executable, "-c", script, str(root), str(scratch), str(destination)],
                    capture_output=True, text=True, check=True, timeout=10,
                )
                self.assertEqual(result.stdout.strip(), "storage_busy")
            self.assertFalse(destination.exists())
            self.assertEqual(publish_clip(root, scratch, destination, total_bytes=4), "saved")

    def test_retention_is_opt_in_and_only_expires_tagged_old_clips(self):
        with TemporaryDirectory() as directory:
            media = Path(directory)

            def create_clip(tag, old, *, extra=False):
                event_id, run_id = str(uuid4()), str(uuid4())
                path = media / "evidence-clips" / event_id / run_id
                path.mkdir(parents=True)
                clip = path / "clip.mp4"
                clip.write_bytes(b"clip")
                if old:
                    os.utime(clip, (1, 1))
                (path / "metadata.json").write_text(json.dumps({
                    "retention_scope": tag, "event_id": event_id, "analysis_run_id": run_id,
                }), encoding="utf-8")
                if extra:
                    (path / "protected.bin").write_bytes(b"other")
                return clip

            eligible = create_clip(RETENTION_SCOPE, True)
            unrelated = create_clip(None, True)
            recent = create_clip(RETENTION_SCOPE, False)
            additional_files = create_clip(RETENTION_SCOPE, True, extra=True)
            png = media / "events" / str(uuid4()) / "evidence.png"
            png.parent.mkdir(parents=True)
            png.write_bytes(b"png")
            self.assertEqual(ClipStore(media, 12).expire(), (0, 0))
            self.assertTrue(eligible.exists())

            store = ClipStore(media, 12, retention_days=1, operational=True)
            self.assertEqual(store.expire(), (1, 0))
            self.assertFalse(eligible.parent.exists())
            self.assertTrue(all(path.is_file() for path in (unrelated, recent, additional_files, png)))
            self.assertTrue(store.png_fits(2, 5))
            self.assertFalse(store.png_fits(3, 5))

    def test_storage_lock_is_shared_and_released(self):
        with TemporaryDirectory() as directory:
            first, second = (ClipStore(Path(directory), 12) for _ in range(2))
            with first.evidence_slot(timeout_s=0) as acquired:
                self.assertTrue(acquired)
                with second.evidence_slot(timeout_s=0) as conflicting:
                    self.assertFalse(conflicting)
            with second.evidence_slot(timeout_s=0) as acquired:
                self.assertTrue(acquired)
