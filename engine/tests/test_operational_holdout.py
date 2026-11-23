from copy import deepcopy
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_operational_holdout as evaluation


class OperationalHoldoutTests(unittest.TestCase):
    def test_sampling_is_source_driven_and_dense_windows_are_contiguous(self):
        rows = evaluation.sampling(1800, 30)
        self.assertEqual(sum(sparse for sparse, _ in rows.values()), 12)
        self.assertEqual([i for i, (_, window) in rows.items() if window == "10"], list(range(300, 390)))
        self.assertEqual([i for i, (_, window) in rows.items() if window == "40"], list(range(1200, 1290)))
        self.assertEqual(list(rows)[-1], 1799)

    def test_seal_requires_human_confirmation_and_class_negatives(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            pack = root / "annotation"
            pack.mkdir()
            with ZipFile(pack / "camera.zip", "w") as archive:
                archive.writestr("frame.jpg", b"test fixture")
            manifest = {"rule_snapshots": {},
                        "sources": [{"id": "camera", "archive_sha256": evaluation.sha256_file(pack / "camera.zip").lower()}],
                        "frames": [{"name": "frame.jpg", "source": "camera", "index": 42, "sparse": True,
                                    "window": None, "width": 60, "height": 40}]}
            evaluation.write(pack / "manifest.json", manifest)
            digest = evaluation.sha256_file(pack / "manifest.json").lower()
            review = {"blind": True, "reviewer": "test reviewer", "annotation_manifest_sha256": digest,
                      "checked_frames": {"frame.jpg": ["negative"]}, "reviewed_event_windows": [],
                      "events": [], "rule_snapshots": {}}
            evaluation.write(root / "empty.json", {**review, "blind": False})
            evaluation.write(root / "review.json", review)
            export = root / "annotations.xml"
            export.write_text("<annotations/>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "revisión humana"):
                evaluation.freeze(root, [export], root / "empty.json")
            with self.assertRaisesRegex(ValueError, "negativos"):
                evaluation.freeze(root, [export], root / "review.json")
            export.write_text('<annotations><image name="frame.jpg" width="60" height="40"/></annotations>', encoding="utf-8")
            sealed = evaluation.freeze(root, [export], root / "review.json")
            evaluation.write(root / "pred.json", {"freeze_sha256": sealed["sha256"], "model_receipt": {"fixture": True},
                                                  "frames": {"frame.jpg": []}})
            score = evaluation.score(root, root / "pred.json", sealed["sha256"])
            self.assertEqual(score["detection"]["all"]["person"]["negative_frames"], 1)
            self.assertIsNone(score["detection"]["all"]["person"]["ap_sampled"])
            with self.assertRaisesRegex(ValueError, "SHA"):
                evaluation.score(root, root / "pred.json", "f" * 64)

    def test_one_to_one_matching_scores_duplicates_false_positives_and_false_negatives(self):
        truth = {"pos": [{"role": "person", "xyxy": [0, 0, 10, 10]}], "neg": []}
        pos = {"role": "person", "xyxy": [0, 0, 10, 10], "confidence": .9}
        outputs = {"pos": [pos, {**pos, "confidence": .8}], "neg": [pos]}
        result = evaluation.detection_scores(truth, truth, outputs, "person", .5)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 2, 0))
        self.assertEqual(result["negative_frames_with_fp"], 1)
        missed = evaluation.detection_scores(truth, truth, {}, "person", .5)
        self.assertEqual((missed["fn"], missed["f1"], missed["ap_sampled"]), (1, 0, 0))

    def test_tracking_prefers_two_valid_matches_to_the_single_nearest_box(self):
        gt = [{"role": "person", "xyxy": [x, 0, x + 10, 10]} for x in (5, 7)]
        tracks = [{"role": "person", "id": i, "xyxy": [x, 0, x + 10, 10]}
                  for i, x in enumerate((5, 2), start=1)]
        matches = evaluation.match_tracks(gt, tracks)
        self.assertEqual({i: track["id"] for i, track in matches.items()}, {0: 2, 1: 1})

    def test_temporal_score_scopes_roles_and_excludes_unobserved_events(self):
        frames = [{"name": str(i), "source": "A", "index": i, "window": "10"} for i in range(5)]
        truth = [{"role": "person", "actor": "p", "occupancy": "ONBOARD", "xyxy": [0, 0, 3, 4]},
                 {"role": "forklift", "actor": "f", "motion": "STATIONARY", "xyxy": [3, 4, 7, 8]}]
        tracks = [{"role": "person", "id": 1, "occupancy": "UNKNOWN", "xyxy": truth[0]["xyxy"]},
                  {"role": "forklift", "id": 1, "motion": "STATIONARY", "xyxy": truth[1]["xyxy"]}]
        event = {"source": "A", "rule": "proximity", "zone": "floor", "version": 1}
        trigger = {**event, "frame": 1, "epoch": 1, "actors": [{"role": "person", "id": 2}, {"role": "forklift", "id": 1}]}
        human = {"rule_snapshots": {"A": "hash"}, "events": [
            {**event, "from_frame": 0, "to_frame": 1, "actors": ["person/p", "forklift/f"]},
            {**event, "from_frame": 1, "to_frame": 3, "actors": ["person/p", "forklift/f"]}]}
        tracking = {f["name"]: {"epoch": 1 if i < 2 else 2, "tracks": deepcopy(tracks)} for i, f in enumerate(frames)}
        tracking["1"]["tracks"][0]["id"] = 2
        tracking["2"] = {"epoch": None, "tracks": []}
        result = evaluation.evaluate_temporal(frames, {f["name"]: truth for f in frames},
                                              {"tracking": tracking, "rule_snapshots": human["rule_snapshots"],
                                               "events": [trigger, trigger]}, human)
        self.assertEqual(result["tracking"]["person"], {"visible": 5, "matched": 4, "switches": 1, "max_loss": 1})
        self.assertEqual(result["occupancy"], {"ONBOARD→UNKNOWN": 4, "ONBOARD→UNMATCHED": 1})
        self.assertEqual(result["events"]["observable"], 1)
        self.assertEqual(len(result["events"]["unobservable"]), 1)
        self.assertEqual(len(result["events"]["matched"]), 1)
        self.assertEqual(len(result["events"]["unmatched"]), 1)
