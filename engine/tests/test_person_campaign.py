# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contratos de campaña PERSON sin CVAT real, modelos ni GPU."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from operix_engine.person_campaign import CampaignImage, freeze_payload, plan_split, plan_tasks, readiness


class PersonCampaignTest(unittest.TestCase):
    def script(self, name: str):
        path = Path(__file__).resolve().parents[1] / "scripts" / name
        spec = importlib.util.spec_from_file_location(name[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def image(self, index: int, status: str, source: str = "KEREMBERKE") -> CampaignImage:
        return CampaignImage(str(index), f"{index}.jpg", source, f"group:{index}",
                             100, 100, f"{index:064X}", status, "MODEL_ONLY", 1, "WEAK")

    def test_task_plan_balanced_and_test3_not_split(self):
        rows = [self.image(i, "PENDING_HUMAN_REANNOTATION") for i in range(99)]
        rows += [self.image(i + 100, "PENDING_FULL_FRAME_NEGATIVE_REVIEW") for i in range(106)]
        rows += [self.image(i + 300, "UNANNOTATED", "TEST3") for i in range(48)]
        tasks = plan_tasks(rows)
        self.assertEqual([len(v) for v in tasks.values()], [50, 49, 53, 53, 48])
        self.assertEqual(len(tasks["TEST3-PERSON-REVIEW"]), 48)
        self.assertEqual(tasks, plan_tasks(rows))

    def test_duplicate_image_rejected(self):
        first = self.image(1, "PENDING_HUMAN_REANNOTATION")
        duplicate = self.image(2, "PENDING_HUMAN_REANNOTATION")
        duplicate = CampaignImage(**{**duplicate.__dict__, "sha256": first.sha256})
        with self.assertRaisesRegex(ValueError, "duplicada"):
            plan_tasks([first, duplicate])

    def test_split_uses_groups_and_excludes_test3(self):
        rows = []
        for i in range(3):
            rows.append({"source_group": f"positive:{i}", "annotation_status": "HUMAN_VERIFIED",
                         "person_box_count": "1", "source": "OTHER", "split_eligibility": "ELIGIBLE",
                         "provenance": "STRONG", "source_group_confidence": "STRONG"})
            rows.append({"source_group": f"negative:{i}", "annotation_status": "VERIFIED_NEGATIVE",
                         "person_box_count": "0", "source": "OTHER", "split_eligibility": "ELIGIBLE",
                         "provenance": "STRONG", "source_group_confidence": "STRONG"})
        rows.append({"source_group": "TEST3_VIDEO", "annotation_status": "HUMAN_VERIFIED",
                     "person_box_count": "1", "source": "TEST3", "split_eligibility": "DEVELOPMENT_ONLY"})
        split = plan_split(rows, seed=42)
        self.assertNotIn("TEST3_VIDEO", split)
        self.assertEqual(set(split.values()), {"TRAIN", "CALIBRATION", "LOCKED_EVALUATION"})
        self.assertEqual(split, plan_split(rows, seed=42))
        with self.assertRaises(ValueError):
            plan_split(rows[:2], seed=42)
        weak = [{**row, "provenance": "WEAK"} if row.get("source") != "TEST3" else row
                for row in rows]
        with self.assertRaisesRegex(ValueError, "procedencia fuerte"):
            plan_split(weak, seed=42)
        ineligible = [{**row, "split_eligibility": "PENDING_REVIEW"}
                      if row.get("source") != "TEST3" else row for row in rows]
        with self.assertRaisesRegex(ValueError, "elegibles"):
            plan_split(ineligible, seed=42)

    def test_freeze_requires_strong_verified_positive_and_negative(self):
        base = {"source_group": "group:1", "provenance": "STRONG",
                "source_group_confidence": "STRONG", "split_eligibility": "ELIGIBLE",
                "source": "OTHER", "label_sha256": "B",
                "image_sha256": "A", "annotation_status": "HUMAN_VERIFIED",
                "person_box_count": "1", "image_id": "a"}
        negative = {**base, "image_id": "b", "annotation_status": "VERIFIED_NEGATIVE",
                    "person_box_count": "0"}
        payload = freeze_payload([base, negative], {"group:1": "LOCKED_EVALUATION"})
        self.assertEqual(len(payload["images"]), 2)
        self.assertEqual(payload, freeze_payload([negative, base], {"group:1": "LOCKED_EVALUATION"}))
        with self.assertRaises(ValueError):
            freeze_payload([{**base, "provenance": "WEAK"}, negative],
                           {"group:1": "LOCKED_EVALUATION"})
        with self.assertRaises(ValueError):
            freeze_payload([{**base, "source_group_confidence": "WEAK"}, negative],
                           {"group:1": "LOCKED_EVALUATION"})

    def test_readiness_gate_needs_human_provenance_and_freeze(self):
        rows = [{"source_group": "s1", "provenance": "STRONG", "source": "OTHER",
                 "source_group_confidence": "STRONG", "split_eligibility": "ELIGIBLE",
                 "annotation_status": "HUMAN_VERIFIED", "person_box_count": "1"},
                {"source_group": "s2", "provenance": "STRONG", "source": "OTHER",
                 "source_group_confidence": "STRONG", "split_eligibility": "ELIGIBLE",
                 "annotation_status": "VERIFIED_NEGATIVE", "person_box_count": "0"}]
        result = readiness(rows, {"task": {"completed": True}}, [], False,
                           minimum_negative_images=1, minimum_independent_groups=3,
                           split={"s1": "TRAIN", "s2": "CALIBRATION"})
        self.assertIn("EVALUATION_NOT_FROZEN", result["blockers"])
        self.assertEqual(result["decision"], "PERSON_V2_BLOCKED_BY_PROVENANCE")

    def test_complete_annotations_with_weak_provenance_are_not_ready(self):
        rows = [{"source_group": "weak:1", "provenance": "WEAK", "source": "OTHER",
                 "source_group_confidence": "WEAK", "split_eligibility": "PENDING_REVIEW",
                 "annotation_status": "HUMAN_VERIFIED", "person_box_count": "2"},
                {"source_group": "weak:2", "provenance": "WEAK", "source": "OTHER",
                 "source_group_confidence": "WEAK", "split_eligibility": "PENDING_REVIEW",
                 "annotation_status": "VERIFIED_NEGATIVE", "person_box_count": "0"}]
        result = readiness(rows, {"task": {"completed": True}}, [], False,
                           minimum_negative_images=1)
        self.assertEqual(result["decision"], "PERSON_V2_BLOCKED_BY_PROVENANCE")
        self.assertNotIn("ANNOTATION_REVIEW_PENDING", result["blockers"])
        self.assertEqual(result["strong_positive_groups"], 0)
        self.assertEqual(result["strong_negative_groups"], 0)

    def make_task_export(self, folder: Path, *, confirmed: bool = True,
                         bbox: list[float] | None = None) -> tuple[Path, list[dict]]:
        folder.mkdir(parents=True)
        archive = folder / "annotations.zip"
        coco = {"categories": [{"id": 1, "name": "person"}],
                "images": [{"id": 1, "file_name": "a.jpg", "width": 100, "height": 100}],
                "annotations": [] if bbox is None else [{"image_id": 1, "category_id": 1, "bbox": bbox}]}
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("annotations/instances_default.json", json.dumps(coco))
        (folder / "review.csv").write_text("image,status,reviewer,reviewed_at\n"
            "a.jpg,HUMAN_VERIFIED,Daniel,2026-10-23\n", encoding="utf-8")
        receipt = {"task_id": "TASK", "reviewer": "Daniel", "completed_at": "2026-10-23",
                   "image_count": 1, "export_sha256": hashlib.sha256(archive.read_bytes()).hexdigest().upper(),
                   "confirmation": "FULL_FRAME_HUMAN_REVIEW_COMPLETED" if confirmed else "DRAFT"}
        (folder / "completion.json").write_text(json.dumps(receipt), encoding="utf-8")
        expected = [{"filename": "a.jpg", "width": "100", "height": "100"}]
        return archive, expected

    def test_cvat_export_requires_explicit_completion_and_valid_box(self):
        module = self.script("process_person_cvat_export.py")
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "export"
            _, expected = self.make_task_export(folder, bbox=[10, 20, 30, 40])
            state, issues, labels, statuses = module.inspect_task("TASK", expected, folder)
            self.assertTrue(state["completed"])
            self.assertFalse(issues)
            self.assertEqual(statuses["a.jpg"], "HUMAN_VERIFIED")
            self.assertEqual(len(labels["a.jpg"]), 1)
            receipt = json.loads((folder / "completion.json").read_text(encoding="utf-8"))
            receipt["confirmation"] = "DRAFT"
            (folder / "completion.json").write_text(json.dumps(receipt), encoding="utf-8")
            state, issues, labels, statuses = module.inspect_task("TASK", expected, folder)
            self.assertFalse(state["completed"])
            self.assertEqual(labels, {})
            self.assertIn("INVALID_HUMAN_COMPLETION_RECEIPT", [r["code"] for r in issues])

    def test_cvat_export_accepts_utf8_bom_in_powershell_receipt_and_review(self):
        module = self.script("process_person_cvat_export.py")
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "export"
            self.make_task_export(folder, bbox=[10, 20, 30, 40])
            for name in ("completion.json", "review.csv"):
                path = folder / name
                path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
            expected = [{"filename": "a.jpg", "width": "100", "height": "100"}]
            state, issues, labels, statuses = module.inspect_task("TASK", expected, folder)
            self.assertTrue(state["completed"])
            self.assertFalse(issues)
            self.assertEqual(statuses, {"a.jpg": "HUMAN_VERIFIED"})
            self.assertEqual(len(labels["a.jpg"]), 1)

    def test_cvat_qa_rejects_out_of_range_and_status_mismatch(self):
        module = self.script("process_person_cvat_export.py")
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "export"
            _, expected = self.make_task_export(folder, bbox=[90, 20, 30, 40])
            state, issues, _, _ = module.inspect_task("TASK", expected, folder)
            self.assertFalse(state["completed"])
            self.assertIn("BOX_OUT_OF_RANGE_OR_ZERO_AREA", [r["code"] for r in issues])

    def test_completion_record_requires_human_confirmation_and_does_not_overwrite(self):
        module = self.script("process_person_cvat_export.py")
        with tempfile.TemporaryDirectory() as temporary:
            campaign = Path(temporary)
            (campaign / "00-inventory").mkdir()
            row = {"image_id": "OTHER:a", "filename": "a.jpg", "source": "OTHER",
                   "source_group": "source:1", "width": "100", "height": "100",
                   "annotation_status": "PENDING_HUMAN_REANNOTATION", "person_box_count": "0",
                   "recommended_task": "TASK", "image_sha256": "A", "provenance": "STRONG",
                   "split_eligibility": "ELIGIBLE"}
            with (campaign / "00-inventory" / "consolidated-images.csv").open(
                    "w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            for name in ("03-manifests", "01-cvat-packages/TASK", "04-qa",
                         "06-split-planning", "07-readiness", "final"):
                (campaign / name).mkdir(parents=True)
            (campaign / "03-manifests" / "tasks.json").write_text(
                json.dumps([{"task_id": "TASK", "images": 1}]), encoding="utf-8")
            folder = campaign / "exports" / "TASK"
            self.make_task_export(folder, bbox=[10, 20, 30, 40])
            (folder / "review.csv").unlink()
            (folder / "completion.json").unlink()
            command = [sys.executable, str(Path(module.__file__)), "--campaign", str(campaign),
                       "--complete-human-task", "TASK", "--reviewer", "Daniel"]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((folder / "review.csv").exists())
            result = subprocess.run([*command, "--confirm-full-frame-human-review"],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(module.csv_rows(folder / "review.csv")[0]["status"], "HUMAN_VERIFIED")
            state, issues, _, _ = module.inspect_task("TASK", [{"filename": "a.jpg",
                "width": "100", "height": "100"}], folder)
            self.assertTrue(state["completed"], issues)
            with self.assertRaises(FileExistsError):
                module.record_human_completion(campaign, "TASK", "Daniel")

    def test_completion_record_preserves_human_ambiguity(self):
        module = self.script("process_person_cvat_export.py")
        with tempfile.TemporaryDirectory() as temporary:
            campaign = Path(temporary)
            (campaign / "00-inventory").mkdir()
            (campaign / "00-inventory" / "consolidated-images.csv").write_text(
                "filename,recommended_task\na.jpg,TASK\n", encoding="utf-8")
            folder = campaign / "exports" / "TASK"
            self.make_task_export(folder)
            (folder / "review.csv").unlink()
            (folder / "completion.json").unlink()
            with self.assertRaisesRegex(ValueError, "ajena"):
                module.record_human_completion(campaign, "TASK", "Daniel", {"other.jpg"})
            result = module.record_human_completion(campaign, "TASK", "Daniel", {"a.jpg"})
            self.assertEqual(result["ambiguous"], 1)
            self.assertEqual(module.csv_rows(folder / "review.csv")[0]["status"],
                             "REVIEW_AMBIGUOUS")
            state, issues, _, statuses = module.inspect_task("TASK", [{"filename": "a.jpg",
                "width": "100", "height": "100"}], folder)
            self.assertTrue(state["completed"], issues)
            self.assertEqual(statuses["a.jpg"], "REVIEW_AMBIGUOUS")

    def test_post_export_pipeline_writes_normalized_label_without_claiming_readiness(self):
        module = self.script("process_person_cvat_export.py")
        with tempfile.TemporaryDirectory() as temporary:
            campaign = Path(temporary)
            for name in ("00-inventory", "03-manifests", "01-cvat-packages/TASK",
                         "04-qa", "06-split-planning", "07-readiness", "final"):
                (campaign / name).mkdir(parents=True)
            export = campaign / "exports" / "TASK"
            self.make_task_export(export, bbox=[10, 20, 30, 40])
            row = {"image_id": "OTHER:a", "filename": "a.jpg", "source": "OTHER",
                   "source_group": "source:1", "width": "100", "height": "100",
                   "annotation_status": "PENDING_HUMAN_REANNOTATION", "person_box_count": "0",
                   "recommended_task": "TASK", "image_sha256": "A", "provenance": "STRONG",
                   "split_eligibility": "ELIGIBLE"}
            with (campaign / "00-inventory" / "consolidated-images.csv").open(
                    "w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            (campaign / "03-manifests" / "tasks.json").write_text(
                json.dumps([{"task_id": "TASK", "images": 1}]), encoding="utf-8")
            result = module.process(campaign)
            self.assertEqual(result["qa"]["completed_tasks"], 1)
            self.assertEqual(result["qa"]["blocking_issues"], 0)
            self.assertEqual(result["readiness"], "PERSON_V2_BLOCKED_BY_PROVENANCE")
            self.assertEqual(result["split"], "BLOCKED")
            labels = (campaign / "final" / "labels" / "OTHER_a.txt").read_text(encoding="utf-8")
            self.assertEqual(labels, "0 0.25000000 0.40000000 0.30000000 0.40000000\n")
            manifest = module.csv_rows(campaign / "final" / "verified-manifest.csv")
            self.assertEqual(manifest[0]["annotation_status"], "HUMAN_VERIFIED")
            self.assertTrue(manifest[0]["label_sha256"])


if __name__ == "__main__":
    unittest.main()
