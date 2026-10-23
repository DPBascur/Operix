# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas de selección y auditoría PERSON sin modelos ni GPU."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from operix_engine.person_evaluation import read_person_observations, select_annotation_frames
from operix_engine.person_metrics import Prediction, box_iou, match_frame, summarize, threshold_grid


class PersonEvaluationTest(unittest.TestCase):
    def test_read_requires_consecutive_unique_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "observations.jsonl"
            path.write_text("\n".join(json.dumps({"frame_index": i,
                "detections": {"person": []}}) for i in (0, 2)) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "consecutivos"):
                read_person_observations(path)
            path.write_text("\n".join(json.dumps({"frame_index": 0,
                "detections": {"person": []}}) for _ in range(2)) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicado"):
                read_person_observations(path)

    def test_selection_is_deterministic_and_not_labels(self):
        current = {i: ({"confidence": .8},) if i % 5 == 0 else () for i in range(200)}
        generic = {i: ({"confidence": .2},) if i % 3 == 0 else () for i in range(200)}
        first = select_annotation_frames(current, generic, total=48)
        self.assertEqual(first, select_annotation_frames(current, generic, total=48))
        self.assertEqual(len(first), 48)
        self.assertIn(0, first)
        self.assertIn(199, first)
        self.assertTrue(any("GENERIC_ONLY" in reasons for reasons in first.values()))
        self.assertTrue(any("VISUAL_OCCLUSION_REVIEW" in reasons for reasons in first.values()))

    def test_models_must_cover_same_frames(self):
        with self.assertRaises(ValueError):
            select_annotation_frames({0: ()}, {1: ()})

    def test_audit_keeps_source_boxes_unverified_and_checks_groups(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "audit_person_readiness.py"
        spec = importlib.util.spec_from_file_location("audit_person_readiness", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "image.jpg"
            image.write_bytes(b"sample")
            base = {"dataset": "nvidia", "split_candidate": "train_candidate",
                    "width": "1920", "height": "1080", "source_group": "run:1",
                    "sha256": "A", "image_path": str(image), "image_id": "a",
                    "annotation_status": "ANNOTATION_COMPLETE", "person_boxes": "2",
                    "source_group_quality": "run_level"}
            other = {**base, "split_candidate": "validation_candidate", "image_id": "b"}
            negative = {**base, "dataset": "keremberke", "source_group": "other:1",
                        "sha256": "B", "image_id": "c", "person_boxes": "0",
                        "annotation_status": "VALID_FULL_FRAME_NEGATIVE"}
            result = module.audit([base, other, negative], [])
            self.assertEqual(result["final_candidate"]["human_verified_person_boxes"], 0)
            self.assertEqual(result["final_candidate"]["human_verified_full_frame_negatives"], 1)
            self.assertEqual(result["final_candidate"]["exact_duplicate_sha256_rows"], 1)
            self.assertEqual(result["final_candidate"]["group_cross_split_conflicts"], 1)
            reviewed = {**base, "annotation_status": "HUMAN_VERIFIED",
                        "source_group": "run:2", "sha256": "C", "image_id": "d"}
            reviewed_result = module.audit([reviewed], [])
            self.assertEqual(reviewed_result["final_candidate"]["human_verified_person_boxes"], 2)
            self.assertEqual(reviewed_result["final_candidate"][
                "person_boxes_from_source_not_human_verified"], 0)

    def test_matching_counts_duplicate_and_missing_person(self):
        box = (0.0, 0.0, 10.0, 10.0)
        self.assertEqual(box_iou(box, box), 1.0)
        predictions = (Prediction(box, .9), Prediction(box, .8))
        counts = match_frame((box,), predictions, confidence=.1)
        self.assertEqual((counts.tp, counts.fp, counts.fn), (1, 1, 0))
        self.assertEqual((match_frame((box,), (), confidence=.1).tp,
                          match_frame((box,), (), confidence=.1).fn), (0, 1))

    def test_threshold_grid_and_metrics(self):
        box = (0.0, 0.0, 10.0, 10.0)
        gt = {"a": (box,), "b": ()}
        pred = {"a": (Prediction(box, .8),), "b": (Prediction(box, .2),)}
        result = threshold_grid(gt, pred, (.1, .5))
        self.assertEqual(result[.1]["tp"], 1)
        self.assertEqual(result[.1]["fp"], 1)
        self.assertEqual(result[.5]["fp"], 0)
        self.assertEqual(result[.5]["f1"], 1.0)
        self.assertIsNone(summarize(())["precision"])

    def test_invalid_box_and_mismatched_grid(self):
        with self.assertRaises(ValueError):
            box_iou((1, 1, 1, 2), (0, 0, 2, 2))
        with self.assertRaises(ValueError):
            threshold_grid({"a": ()}, {"b": ()}, (.1,))


if __name__ == "__main__":
    unittest.main()
