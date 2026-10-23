# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Holdout PERSON sintético; no usa pesos, GPU ni material protegido."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from operix_engine.person_holdout import (
    acquisition_readiness, guard_holdout_assignment, sample_indices, sha256_file,
    verify_frozen,
)


class PersonHoldoutTest(unittest.TestCase):
    def script(self, name: str):
        path = Path(__file__).resolve().parents[1] / "scripts" / name
        spec = importlib.util.spec_from_file_location(name[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def make_video(self, path: Path, *, color: int) -> None:
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48))
        self.assertTrue(writer.isOpened())
        for frame_index in range(10):
            frame = np.full((48, 64, 3), color + frame_index, dtype=np.uint8)
            writer.write(frame)
        writer.release()

    def test_sampling_and_assignment_are_deterministic_and_isolated(self):
        self.assertEqual(sample_indices(10, 10.0, sample_count=3), (0, 4, 9))
        self.assertEqual(sample_indices(10, 10.0, interval_seconds=0.3), (0, 3, 6, 9))
        self.assertEqual(sample_indices(10, 10.0, sample_count=1), (5,))
        with self.assertRaises(ValueError):
            sample_indices(10, 10.0, sample_count=3, interval_seconds=1)
        with self.assertRaisesRegex(ValueError, "reservados"):
            guard_holdout_assignment({"HOLDOUT_PERSON_001"}, {"HOLDOUT_PERSON_001": "TRAIN"})
        guard_holdout_assignment({"HOLDOUT_PERSON_001"},
                                 {"HOLDOUT_PERSON_001": "LOCKED_EVALUATION"})

    def test_ingestion_refuses_duplicate_group_and_duplicate_video(self):
        ingest = self.script("ingest_person_holdout_video.py").ingest
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            video = base / "source.avi"
            root = base / "holdout"
            self.make_video(video, color=10)
            kwargs = {"origin": "test synthetic", "camera_or_source": "camera A",
                      "scenario": "test", "rights_or_license": "test-only"}
            first = ingest(video, root, source_group="HOLDOUT_PERSON_001", **kwargs)
            self.assertEqual(first["manifest"]["sha256"], sha256_file(video))
            self.assertEqual(first["readiness"]["decision"], "PERSON_HOLDOUT_PARTIAL")
            with self.assertRaises(FileExistsError):
                ingest(video, root, source_group="HOLDOUT_PERSON_001", **kwargs)
            with self.assertRaisesRegex(ValueError, "video SHA-256"):
                ingest(video, root, source_group="HOLDOUT_PERSON_002", **kwargs)
            self.assertNotIn(str(base), (root / "01-ingested" / "HOLDOUT_PERSON_001.json").read_text())

    def test_ingestion_uses_decodable_frames_when_container_count_is_high(self):
        module = self.script("ingest_person_holdout_video.py")

        class Capture:
            remaining = 3

            def isOpened(self):
                return True

            def get(self, property_id):
                return {cv2.CAP_PROP_FRAME_WIDTH: 64, cv2.CAP_PROP_FRAME_HEIGHT: 48,
                        cv2.CAP_PROP_FPS: 10.0, cv2.CAP_PROP_FRAME_COUNT: 5,
                        cv2.CAP_PROP_FOURCC: 0}[property_id]

            def read(self):
                if not self.remaining:
                    return False, None
                self.remaining -= 1
                return True, np.zeros((48, 64, 3), dtype=np.uint8)

            def release(self):
                pass

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            video = base / "source.avi"
            video.write_bytes(b"synthetic video placeholder")
            with patch.object(module.cv2, "VideoCapture", return_value=Capture()):
                result = module.ingest(video, base / "holdout", source_group="HOLDOUT_PERSON_001",
                    origin="synthetic", camera_or_source="camera A", scenario="test",
                    rights_or_license="test-only")
            self.assertEqual(result["manifest"]["declared_frame_count"], 5)
            self.assertEqual(result["manifest"]["frame_count"], 3)
            self.assertEqual(result["manifest"]["duration_seconds"], 0.3)

    def test_cvat_package_export_gate_and_immutable_freeze(self):
        ingest = self.script("ingest_person_holdout_video.py").ingest
        prepare = self.script("prepare_person_holdout_cvat.py").prepare
        freeze = self.script("freeze_person_independent_holdout.py").freeze
        process_script = Path(__file__).resolve().parents[1] / "scripts" / "process_person_holdout_export.py"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "holdout"
            self.assertEqual(acquisition_readiness(root)["decision"],
                             "PERSON_HOLDOUT_ACQUISITION_READY")
            for number in range(1, 4):
                group = f"HOLDOUT_PERSON_{number:03d}"
                video = base / f"source-{number}.avi"
                self.make_video(video, color=number * 30)
                ingest(video, root, source_group=group, origin=f"synthetic {number}",
                       camera_or_source=f"camera {number}", scenario="unit test",
                       rights_or_license="test-only")
                result = prepare(root, group, sample_count=3)
                self.assertEqual(result["frames"], 3)
                package = root / "03-cvat-packages" / group
                self.assertFalse((package / "PREANNOTATION_ONLY.coco.zip").exists())
                with self.assertRaises(FileExistsError):
                    prepare(root, group, sample_count=3)
                with (package / "manifest.csv").open(newline="", encoding="utf-8") as stream:
                    rows = list(csv.DictReader(stream))
                annotations = ([{"id": 1, "image_id": 1, "category_id": 1,
                                 "bbox": [1, 2, 10, 10]}] if number == 1 else [])
                coco = {"categories": [{"id": 1, "name": "person"}],
                        "images": [{"id": i + 1, "file_name": row["filename"],
                                    "width": 64, "height": 48} for i, row in enumerate(rows)],
                        "annotations": annotations}
                export = root / "04-exports" / group
                export.mkdir(parents=True)
                with zipfile.ZipFile(export / "annotations.zip", "w") as archive:
                    archive.writestr("annotations/instances_default.json", json.dumps(coco))
                command = [sys.executable, str(process_script), "--output-root", str(root),
                           "--source-group", group, "--reviewer", "Daniel"]
                denied = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertNotEqual(denied.returncode, 0)
                self.assertFalse((export / "completion.json").exists())
                accepted = subprocess.run([*command, "--confirm-full-frame-human-review"],
                                          capture_output=True, text=True, check=False)
                self.assertEqual(accepted.returncode, 0, accepted.stderr)
                self.assertEqual(json.loads(accepted.stdout)["qa"]["blocking_issues"], 0)
            self.assertEqual(acquisition_readiness(root)["decision"],
                             "PERSON_HOLDOUT_READY_TO_FREEZE")
            with self.assertRaisesRegex(ValueError, "atestación"):
                freeze(root, attestor="Daniel", independent_groups_attested=False)
            result = freeze(root, attestor="Daniel", independent_groups_attested=True)
            self.assertEqual(result["readiness"]["decision"], "PERSON_EVALUATION_READY")
            self.assertEqual(len(verify_frozen(root)["source_groups"]), 3)
            with self.assertRaises(FileExistsError):
                freeze(root, attestor="Daniel", independent_groups_attested=True)
            frame = next((root / "02-frame-samples" / "HOLDOUT_PERSON_001").glob("*.png"))
            frame.write_bytes(b"tampered")
            self.assertEqual(acquisition_readiness(root)["decision"], "PERSON_HOLDOUT_BLOCKED")


if __name__ == "__main__":
    unittest.main()
