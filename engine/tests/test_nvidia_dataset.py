# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas de tooling de anotaciones sin red, GPU ni datos NVIDIA."""

from __future__ import annotations

import json
import csv
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from operix_engine.nvidia_dataset import (
    HOLDOUT_RUNS, audit, build_manifest, candidate_class, read_catalog, split_runs, yolo_box,
)


class NvidiaDatasetTest(unittest.TestCase):
    def _tooling(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_nvidia_dataset.py"
        spec = importlib.util.spec_from_file_location("prepare_nvidia_dataset", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_manual_add_uses_original_yolo_converter_and_preserves_source(self):
        module = self._tooling()
        frame = {"agents": {}, "objects": {}}
        original = json.dumps(frame)
        review = {"state": "MANUAL_ADD", "actions": [{"action": "ADD",
                  "target_class": "forklift", "bbox_xyxy": [10, 20, 30, 60],
                  "reason": "missing_source_annotation"}],
                  "source_annotation_sha256": "ABC"}
        boxes = module.apply_manual_review({}, frame, review, 100, 100)
        self.assertEqual(boxes[0]["bbox"], yolo_box(
            {"x_min": 10, "y_min": 20, "x_max": 30, "y_max": 60}, 100, 100))
        self.assertEqual(boxes[0]["source"], "OPERIX_MANUAL")
        self.assertEqual(boxes[0]["source_annotation_sha256"], "ABC")
        self.assertEqual(original, json.dumps(frame))
        self.assertEqual(boxes, module.apply_manual_review({}, frame, review, 100, 100))

    def test_review_plan_materializes_source_hash_without_overwriting(self):
        module = self._tooling()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_text('{"agents":{},"objects":{}}\n', encoding="utf-8")
            catalog = root / "catalog.csv"
            row = {"run_id": "0123456789abcdefabcd_run_1_seed_1234", "seed": "1234",
                   "scenario": "fire", "camera": "ceiling_04", "split": "train",
                   "annotation_path": str(source)}
            with catalog.open("w", newline="", encoding="utf-8") as sink:
                writer = csv.DictWriter(sink, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            plan = root / "plan.json"
            plan.write_text(json.dumps({"schema_version": 1, "dataset_revision": module.REVISION,
                                        "groups": [{"run_id": row["run_id"], "camera": "ceiling_04",
                                                    "state": "MANUAL_ADD", "frames": [0],
                                                    "bbox_xyxy": [10, 20, 30, 60]}]}),
                            encoding="utf-8")
            output = root / "overlay.json"
            self.assertEqual(module.materialize_review_overlay([catalog], plan, output),
                             {"frames": 1, "runs": 1})
            review = json.loads(output.read_text(encoding="utf-8"))["frames"][0]
            self.assertEqual(review["source_annotation_sha256"],
                             hashlib.sha256(source.read_bytes()).hexdigest().upper())
            self.assertEqual(review["actions"][0]["reason"], "missing_source_annotation")
            second = root / "overlay-second.json"
            module.materialize_review_overlay([catalog], plan, second)
            self.assertEqual(output.read_bytes(), second.read_bytes())
            with self.assertRaisesRegex(ValueError, "sobrescribe"):
                module.materialize_review_overlay([catalog], plan, output)

    def test_manual_review_rejects_duplicate_conflict_and_invalid_coordinates(self):
        module = self._tooling()
        frame = {"agents": {}, "objects": {}}
        action = {"action": "ADD", "target_class": "forklift",
                  "bbox_xyxy": [10, 20, 30, 60], "reason": "missing_source_annotation"}
        with self.assertRaisesRegex(ValueError, "duplicada"):
            module.apply_manual_review({}, frame, {"state": "MANUAL_ADD",
                                                   "actions": [action, action],
                                                   "source_annotation_sha256": "ABC"}, 100, 100)
        with self.assertRaisesRegex(ValueError, "fuera del frame"):
            module.apply_manual_review({}, frame, {"state": "MANUAL_ADD",
                                                   "actions": [action | {"bbox_xyxy": [-1, 20, 30, 60]}]},
                                       100, 100)
        with self.assertRaisesRegex(ValueError, "contradice"):
            source = {"agents": {"/Forklift/0": {"label": {"class": "robot"},
                      "metro_agent_data": {"agent_group": "forklift", "agent_name": "forklift_0",
                                           "asset_url": "omniverse://x/forklift.usd"},
                      "annotators": {"bounding_box_2d_tight_fast":
                                     {"x_min": 10, "y_min": 20, "x_max": 30, "y_max": 60}}}}}
            module.apply_manual_review({}, source, {"state": "VERIFIED_NEGATIVE", "actions": []},
                                       100, 100)
        with self.assertRaisesRegex(ValueError, "conflicto"):
            module.apply_manual_review({}, source, {"state": "MANUAL_ADD", "actions": [action],
                                                    "source_annotation_sha256": "ABC"},
                                       100, 100)

    def test_exclude_frame_is_explicit_and_incompatible_with_add(self):
        module = self._tooling()
        frame = {"agents": {}, "objects": {}}
        review = {"state": "EXCLUDE_FRAME", "actions": [{"action": "EXCLUDE_FRAME"}]}
        self.assertIsNone(module.apply_manual_review({}, frame, review, 100, 100))
        with self.assertRaisesRegex(ValueError, "no admite"):
            module.apply_manual_review({}, frame, {"state": "EXCLUDE_FRAME", "actions":
                                       [{"action": "EXCLUDE_FRAME"}, {"action": "ADD"}]},
                                       100, 100)

    def test_curated_export_preserves_jsonl_and_tracks_manual_source(self):
        import cv2
        import numpy as np
        module = self._tooling()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "0123456789abcdefabcd_run_1_seed_1234"
            annotation = root / "source.jsonl"
            annotation.write_text('{"agents": {}, "objects": {}}\n', encoding="utf-8")
            before = hashlib.sha256(annotation.read_bytes()).hexdigest().upper()
            video = root / "source.avi"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30, (1920, 1080))
            self.assertTrue(writer.isOpened())
            writer.write(np.zeros((1080, 1920, 3), dtype=np.uint8))
            writer.release()
            row = {"run_id": run_id, "seed": "1234", "scenario": "fire", "camera": "ceiling_04",
                   "split": "train", "video_path": str(video), "annotation_path": str(annotation)}
            catalog = root / "catalog.csv"
            with catalog.open("w", newline="", encoding="utf-8") as sink:
                csv_writer = csv.DictWriter(sink, fieldnames=list(row))
                csv_writer.writeheader()
                csv_writer.writerow(row)
            reviews = root / "reviews.json"
            reviews.write_text(json.dumps({"schema_version": 1, "dataset_revision": module.REVISION,
                "frames": [{"run_id": run_id, "seed": "1234", "scenario": "fire",
                            "camera": "ceiling_04", "frame": 0, "split": "train",
                            "source_annotation_sha256": before, "state": "MANUAL_ADD",
                            "actions": [{"action": "ADD", "target_class": "forklift",
                                         "bbox_xyxy": [100, 200, 300, 500],
                                         "reason": "missing_source_annotation"}]}]}), encoding="utf-8")
            plan = root / "protected.json"
            plan.write_text(json.dumps({"dataset_revision": module.REVISION, "runs": []}),
                            encoding="utf-8")
            summary = module.curate_yolo([catalog], reviews, root / "curated", [plan])
            self.assertEqual(summary, {"reviewed": 1, "exported": 1, "excluded": 0})
            self.assertEqual(before, hashlib.sha256(annotation.read_bytes()).hexdigest().upper())
            with (root / "curated" / "box-ledger.jsonl").open(encoding="utf-8") as source:
                ledger = json.loads(source.readline())
            self.assertEqual(ledger["boxes"][0]["source"], "OPERIX_MANUAL")
            self.assertEqual(ledger["source_annotation_sha256"], before)
            self.assertEqual(ledger["manual_forklift_boxes"], 1)
            self.assertEqual(ledger["nvidia_forklift_boxes"], 0)
            with self.assertRaisesRegex(ValueError, "vacía"):
                module.curate_yolo([catalog], reviews, root / "curated", [plan])
            plan.write_text(json.dumps({"dataset_revision": module.REVISION,
                "runs": [{"run_id": run_id, "seed": "1234", "split": "test"}]}),
                encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "elegible"):
                module.curate_yolo([catalog], reviews, root / "blocked", [plan])

    def test_v2_plan_reserves_unseen_runs_by_seed_without_annotations(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_nvidia_dataset.py"
        spec = importlib.util.spec_from_file_location("prepare_nvidia_dataset", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = []
            splits = {}
            shards = []
            scenarios = tuple(module.ARTIFACT_SHARDS)
            for scenario_index, scenario in enumerate(scenarios):
                for number in range(120):
                    seed = str(scenario_index * 10000 + number + 1)
                    run_id = f"{number + 1:020x}_run_1_seed_{seed}"
                    runs.append({"run_id": run_id, "seed": seed, "scenario": scenario,
                                 "source_kind": "multi_camera_run"})
                    splits[run_id] = "train" if number < 65 else "validation" if number < 90 else "test"
                for number, start in enumerate(("0" * 20 + "_run_1_seed_0",
                                                "f" * 20 + "_run_1_seed_999999")):
                    shards.append({"scenario": scenario, "number": number,
                                   "shard": f"artifacts/{scenario}/{number:05d}.tar",
                                   "first_run": start})
            for filename, rows in (("runs.csv", runs), ("shards.csv", shards)):
                with (root / filename).open("w", newline="", encoding="utf-8") as sink:
                    writer = csv.DictWriter(sink, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
            (root / "registry.json").write_text(json.dumps({"dataset_revision": module.REVISION,
                                                             "splits": splits}), encoding="utf-8")
            (root / "v1.json").write_text(json.dumps({"dataset_revision": module.REVISION,
                                                      "runs": [runs[0]]}), encoding="utf-8")
            module.plan_v2(root / "runs.csv", root / "registry.json", root / "shards.csv",
                           root / "v1.json", root / "v2.json")
            selected = json.loads((root / "v2.json").read_text(encoding="utf-8"))["runs"]
            self.assertEqual(len(selected), 36)
            self.assertEqual(len({row["seed"] for row in selected}), 36)
            self.assertNotIn(runs[0]["run_id"], {row["run_id"] for row in selected})
            self.assertEqual(sum(row["split"] == "test" for row in selected), 12)

    def test_compose_v2_reuses_only_train_and_validation(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_nvidia_dataset.py"
        spec = importlib.util.spec_from_file_location("prepare_nvidia_dataset", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source_name in ("base", "extra"):
                for split in ("train", "val"):
                    stem = f"{source_name}.{split}.0000"
                    for folder, suffix in (("images", ".jpg"), ("labels", ".txt")):
                        path = root / source_name / folder / split / f"{stem}{suffix}"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b"sample")
                    row = {"run_id": source_name, "seed": "1" if source_name == "base" else "2",
                           "scenario": "fire", "camera": split, "frame": "0", "split": split,
                           "image_stem": stem, "person_boxes": "0", "forklift_boxes": "0",
                           "ignored_targets_without_box": "0", "background": "True"}
                    with (root / source_name / f"manifest-{split}.csv").open(
                            "w", newline="", encoding="utf-8") as sink:
                        writer = csv.DictWriter(sink, fieldnames=list(row))
                        writer.writeheader()
                        writer.writerow(row)
            module.compose_v2(root / "base", root / "extra", root / "combined")
            for split in ("train", "val"):
                with (root / "combined" / f"manifest-{split}.csv").open(
                        newline="", encoding="utf-8") as source:
                    self.assertEqual(len(list(csv.DictReader(source))), 2)
            self.assertFalse((root / "combined" / "images" / "test").exists())

    def test_test2_negative_measurement_requires_selected_best(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_nvidia_dataset.py"
        spec = importlib.util.spec_from_file_location("prepare_nvidia_dataset", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "TEST 2 reservado"):
                module.mine_hard_negatives(root, root / "best.pt", "test", root / "report.json")
            with self.assertRaisesRegex(ValueError, "Test reservado"):
                module.export_yolo(root / "plan.json", root / "catalog.csv", root / "dataset",
                                   "test")
            with self.assertRaisesRegex(ValueError, "Solo train/validation"):
                module.mine_video_negatives(root / "catalog.csv", root / "best.pt", "test",
                                            root / "report.json")

    def test_test_catalog_requires_selected_weights(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_nvidia_dataset.py"
        spec = importlib.util.spec_from_file_location("prepare_nvidia_dataset", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "best.pt seleccionado"):
                module.catalog_from_cache(root / "plan.json", root, root / "test.csv", "test")

    def test_camera_fallback_requires_rgb_annotation_pair(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_nvidia_dataset.py"
        spec = importlib.util.spec_from_file_location("prepare_nvidia_dataset", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.choose_cameras(["cam_00", "cam_03"], {"cam_01", "cam_02"}),
                         ["cam_01", "cam_02"])
        self.assertEqual(module.choose_cameras(["cam_00", "cam_03"], {"cam_03", "cam_01"}),
                         ["cam_03", "cam_01"])
        self.assertEqual(module.choose_cameras(["cam_00", "cam_03"], set()), [])

    def test_blind_test_frame_indices_use_only_count(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_nvidia_dataset.py"
        spec = importlib.util.spec_from_file_location("prepare_nvidia_dataset", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.temporal_test_indices(100, 10),
                         [5, 15, 25, 35, 45, 55, 65, 75, 85, 95])
        with self.assertRaises(ValueError):
            module.temporal_test_indices(5, 10)

    def test_pilot_plan_uses_frozen_metadata_splits_without_opening_annotations(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_nvidia_dataset.py"
        spec = importlib.util.spec_from_file_location("prepare_nvidia_dataset", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs_path = root / "runs.csv"
            registry_path = root / "registry.json"
            shards_path = root / "shards.csv"
            plan_path = root / "plan.json"
            scenarios = ("nearmiss", "forklift_collision", "box_pickup", "fire")
            runs = []
            splits = {}
            for scenario_index, scenario in enumerate(scenarios):
                for index in range(100):
                    seed = str(scenario_index * 1000 + index + 1)
                    run_id = f"{index + 1:020x}_run_1_seed_{seed}"
                    runs.append({"run_id": run_id, "seed": seed,
                                 "scenario": scenario, "source_kind": "multi_camera_run"})
                    splits[run_id] = "train" if index < 70 else "validation" if index < 85 else "test"
            with runs_path.open("w", newline="", encoding="utf-8") as sink:
                writer = csv.DictWriter(sink, fieldnames=list(runs[0]))
                writer.writeheader()
                writer.writerows(runs)
            registry_path.write_text(json.dumps({"dataset_revision": module.REVISION,
                                                 "splits": splits}), encoding="utf-8")
            shard_rows = []
            for scenario in scenarios:
                for number, start in enumerate(("0" * 20 + "_run_1_seed_0",
                                                "f" * 20 + "_run_1_seed_999999")):
                    shard_rows.append({"scenario": scenario, "number": number,
                                       "shard": f"artifacts/{scenario}/{number:05d}.tar",
                                       "first_run": start})
            with shards_path.open("w", newline="", encoding="utf-8") as sink:
                writer = csv.DictWriter(sink, fieldnames=list(shard_rows[0]))
                writer.writeheader()
                writer.writerows(shard_rows)
            module.plan_pilot(runs_path, registry_path, shards_path, plan_path)
            selected = json.loads(plan_path.read_text(encoding="utf-8"))["runs"]
            self.assertEqual(len(selected), 80)
            self.assertEqual(len({row["run_id"] for row in selected}), 80)
            self.assertEqual(len({row["seed"] for row in selected}), 80)
            self.assertEqual(sum(row["split"] == "test" for row in selected), 12)
            self.assertEqual(sum(row["scenario"] == "nearmiss" for row in selected), 30)

    def test_mapping_strict(self):
        worker = dict(label_class="character", group="Worker", name="Worker_0",
                      agent_type="IRACharacterAPI", asset_url="person.usd")
        forklift = dict(label_class="robot", group="forklift_group", name="Forklift_Scenario",
                        agent_type="AnimRobotAPI", asset_url="omniverse://x/forklift.usd")
        self.assertEqual(candidate_class(worker), "person")
        self.assertEqual(candidate_class(forklift), "forklift")
        self.assertIsNone(candidate_class(worker | {"group": "Visitor"}))
        self.assertIsNone(candidate_class(forklift | {"group": "pallet_jack"}))
        self.assertIsNone(candidate_class(forklift | {"asset_url": "robot.usd"}))
        self.assertIsNone(candidate_class(forklift | {"label_class": "truck"}))

    def test_box_tight_pixel_to_yolo_and_clipping(self):
        box = dict(x_min=10, y_min=20, x_max=30, y_max=60)
        self.assertEqual(yolo_box(box, 100, 100), (.2, .4, .2, .4))
        self.assertEqual(yolo_box(dict(x_min=-10, y_min=0, x_max=10, y_max=20), 100, 100),
                         (.05, .1, .1, .2))
        self.assertIsNone(yolo_box(dict(x_min=30, y_min=20, x_max=10, y_max=60), 100, 100))
        self.assertIsNone(yolo_box(dict(x_min=200, y_min=0, x_max=300, y_max=20), 100, 100))

    def test_split_grouped_seed_and_holdout(self):
        rows = [dict(run_id="r1", seed="4", scenario="fire", camera="a"),
                dict(run_id="r1", seed="4", scenario="fire", camera="b"),
                dict(run_id="r2", seed="4", scenario="box", camera="a"),
                dict(run_id=next(iter(HOLDOUT_RUNS)), seed="5", scenario="nearmiss", camera="a")]
        first = split_runs(rows)
        self.assertEqual(first, split_runs(list(reversed(rows))))
        self.assertEqual(first["r1"], first["r2"])
        self.assertEqual(first[next(iter(HOLDOUT_RUNS))], "known_regression")
        self.assertEqual(split_runs(rows, exploration_runs=frozenset({"r1"}))["r1"], "exploration_seen")
        self.assertEqual(split_runs([dict(run_id="other_camera_run", seed="4731920",
                                          scenario="box", camera="b")])["other_camera_run"], "known_regression")
        with self.assertRaises(ValueError):
            split_runs([dict(run_id="missing", seed="", scenario="fire", camera="a")])

    def test_audit_and_manifest_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            annotation = Path(directory) / "sample.jsonl"
            person = {"label": {"class": "character"},
                      "metro_agent_data": {"agent_group": "Worker", "agent_name": "Worker_0",
                                           "agent_type": "IRACharacterAPI", "prim_path": "/Worker/0"},
                      "annotators": {"bounding_box_2d_tight_fast":
                                     {"x_min": 0, "y_min": 0, "x_max": 50, "y_max": 50}}}
            forklift = {"label": {"class": "robot"},
                        "metro_agent_data": {"agent_group": "forklift", "agent_name": "forklift_0",
                                             "asset_url": "omniverse://x/forklift.usd", "prim_path": "/Forklift/0"},
                        "annotators": {"bounding_box_2d_tight_fast":
                                       {"x_min": 50, "y_min": 20, "x_max": 100, "y_max": 100}}}
            frames = [dict(agents={"/Worker/0": person, "/Forklift/0": forklift}),
                      dict(agents={"/Worker/0": person})]
            annotation.write_text("\n".join(json.dumps(frame) for frame in frames) + "\n", encoding="utf-8")
            row = dict(run_id="new_run", seed="123", scenario="nearmiss", camera="cam_00",
                       annotation_path=str(annotation), width=100, height=100)
            summary = audit([row])
            self.assertEqual(summary["scenarios"][0]["frames"], 2)
            self.assertEqual(summary["scenarios"][0]["person_boxes"], 2)
            self.assertEqual(summary["scenarios"][0]["forklift_boxes"], 1)
            self.assertEqual(summary["scenarios"][0]["frames_with_both"], 1)
            self.assertEqual(summary["scenarios"][0]["unique_person_instances"], 1)
            first = build_manifest([row], 1)
            self.assertEqual(first, build_manifest([row], 1))
            self.assertEqual(len(first["entries"]), 1)
            self.assertEqual({box["class_id"] for box in first["entries"][0]["boxes"]}, {0, 1})
            with self.assertRaises(ValueError):
                build_manifest([row], 1, reserved_splits={"new_run": "test"})

    def test_catalog_seed_is_canonical_and_duplicate_camera_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.csv"
            header = "run_id,seed,scenario,camera,annotation_path,width,height\n"
            line = "one,4731920.0,box_pickup,cam_00,a.jsonl,1920,1080\n"
            catalog.write_text(header + line, encoding="utf-8")
            self.assertEqual(read_catalog(catalog)[0]["seed"], "4731920")
            catalog.write_text(header + line + line, encoding="utf-8")
            with self.assertRaises(ValueError):
                read_catalog(catalog)


if __name__ == "__main__":
    unittest.main()
