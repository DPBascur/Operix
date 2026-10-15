# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas de tooling de anotaciones sin red, GPU ni datos NVIDIA."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from operix_engine.nvidia_dataset import (
    HOLDOUT_RUNS, audit, build_manifest, candidate_class, read_catalog, split_runs, yolo_box,
)


class NvidiaDatasetTest(unittest.TestCase):
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
