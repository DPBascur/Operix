# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures sintéticos: no imágenes reales, modelos, GPU ni material protegido."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


SPEC = importlib.util.spec_from_file_location("coco_freeze", Path(__file__).parents[1] /
                                              "scripts/freeze_person_coco_holdout.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class PersonCocoFreezeTests(unittest.TestCase):
    def fixture(self, root):
        def save(relative, value):
            p = root / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(tool.canonical_bytes(value))
            return tool.sha(p)
        original, records, families = {}, [], []
        for number in range(101, 106):
            group = f"HOLDOUT_PERSON_{number}"
            images, anns, local = [], [], []
            for frame in (0, 1):
                name = f"{group}_frame_{frame:06d}.png"
                content = b"shared-negative" if frame == 1 and number in (101, 104) else f"{number}-{frame}".encode()
                image = root / "02-frame-samples" / group / name
                image.parent.mkdir(parents=True, exist_ok=True)
                image.write_bytes(content)
                original[image.relative_to(root).as_posix()] = tool.sha(image)
                images.append(dict(id=frame, file_name=name, width=100, height=100))
                if frame == 0:
                    anns.append(dict(id=0, image_id=0, category_id=1, bbox=[1, 2, 10, 20]))
                local.append(dict(source_group=group, source_family=f"SESSION_{number}", filename=name,
                    width="100", height="100", coco_image_id=frame, person_boxes=int(frame == 0),
                    image_sha256=tool.sha(image), video_sha256=f"VIDEO_{number}", source_reference=f"https://example.org/{number}"))
            raw = tool.canonical_bytes(dict(categories=[dict(id=1, name="person")], images=images, annotations=anns))
            archive = root / "04-exports" / group / "annotations.zip"
            archive.parent.mkdir(parents=True)
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("annotations/instances_default.json", raw)
            export_sha, json_sha = tool.sha(archive), hashlib.sha256(raw).hexdigest().upper()
            original[archive.relative_to(root).as_posix()] = export_sha
            families.append(dict(family=group, source_family=f"SESSION_{number}",
                                 export_sha256=export_sha, json_sha256=json_sha))
            for row in local:
                records.append({**row, "annotation_export_sha256": export_sha, "annotation_json_sha256": json_sha})
        csv_path = root.parent / "synthetic-development.csv"
        csv_path.write_text("image_sha256,source_group,filename\nOTHER,DEV,unrelated.png\n", encoding="utf-8")
        qa_sha = save("05-qa/final-coco-audit/coco-integrity-qa.json", dict(issues=[dict(code="EXACT_DUPLICATE_FRAME_BYTES")]))
        audit_sha = save("05-qa/final-coco-audit/independence-documentary-audit.json",
            dict(matching_rows=0, rows_compared=1, coverage_limitations=["synthetic"],
                 manifests=[dict(manifest=csv_path.name, sha256=tool.sha(csv_path), rows=1)]))
        save("final/candidate-qa-manifest.json", dict(dataset_id="PERSON_FINAL_HOLDOUT_V2", frame_records=records,
            families=families, qa_sha256=qa_sha, documentary_audit_sha256=audit_sha,
            original_inputs_sha256=original, annotation_policy_version="SYNTHETIC_V1",
            provenance_status="SYNTHETIC", rights_status="SYNTHETIC"))
        attestation = dict(dataset_id="PERSON_FINAL_HOLDOUT_V2", annotator="synthetic", attestor="synthetic",
            declared_at_utc="2026-01-01T00:00:00Z", manual_annotations=True, no_model_generated_annotations=True,
            no_model_assisted_box_generation=True, no_automatic_box_correction=True,
            no_project_model_access_before_freeze=True, controlled_development_independence_attested=True,
            local_registry_coverage_attested=True, excluded_uses=tool.EXCLUDED_USES,
            external_pretraining_independence_claimed=False, source_groups=[f["family"] for f in families],
            annotation_policy=["synthetic test policy"])
        save("06-freeze/attestation.json", attestation)
        return root / "06-freeze/attestation.json"

    def test_determinism_unicode_and_nonfinite(self):
        self.assertEqual(tool.canonical_bytes({"b": 2, "a": "Peña"}),
                         tool.canonical_bytes({"a": "Peña", "b": 2}))
        with self.assertRaises(ValueError):
            tool.canonical_bytes({"a": float("nan")})

    def test_stable_dedup_independent_of_input_order(self):
        rows = [dict(source_group=g, filename=n, image_sha256="ABC", human_boxes=[])
                for g, n in [("B", "000001"), ("A", "000002"), ("A", "000001")]]
        before = copy.deepcopy(rows)
        kept, excluded = tool.deduplicate(rows)
        self.assertEqual(kept[0]["filename"], "000001")
        self.assertEqual(kept[0]["source_group"], "A")
        self.assertEqual(len(excluded), 2)
        self.assertEqual(tool.deduplicate(list(reversed(rows))), (kept, excluded))
        self.assertEqual(rows, before)

    def test_identical_bytes_conflicting_annotations_blocked(self):
        rows = [dict(source_group="A", filename="a", image_sha256="X", human_boxes=[]),
                dict(source_group="B", filename="b", image_sha256="X", human_boxes=[[1, 2, 3, 4]])]
        with self.assertRaisesRegex(ValueError, "incompatibles"):
            tool.deduplicate(rows)

    def test_freeze_verify_counts_history_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "holdout"
            attestation = self.fixture(root)
            inputs = tool.load(root / "final/candidate-qa-manifest.json")["original_inputs_sha256"]
            result = tool.freeze(root, attestation)
            self.assertEqual(result["evaluation_images"], 9)
            manifest = tool.load(root / tool.FINAL)
            self.assertEqual(manifest["original_sampled_records"], 10)
            self.assertEqual(manifest["evaluation_counts"]["person_boxes"], 5)
            self.assertEqual(manifest["evaluation_counts"]["negative_frames"], 4)
            self.assertEqual(len(manifest["frame_records"]), 10)
            excluded = [r for r in manifest["frame_records"] if not r["evaluation_included"]]
            self.assertEqual(excluded[0]["source_group"], "HOLDOUT_PERSON_104")
            self.assertTrue(all(tool.sha(root / p) == digest for p, digest in inputs.items()))
            with self.assertRaises(FileExistsError):
                tool.freeze(root, attestation)
            self.assertEqual(tool.verify(root), result)
            (root / tool.EVALUATION).write_text("{}")
            with self.assertRaises((ValueError, KeyError)):
                tool.verify(root)

    def test_missing_attestation_does_not_write_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "holdout"
            path = self.fixture(root)
            data = tool.load(path)
            data["local_registry_coverage_attested"] = False
            path.write_bytes(tool.canonical_bytes(data))
            with self.assertRaisesRegex(ValueError, "atestación"):
                tool.freeze(root, path)
            self.assertFalse((root / tool.FINAL).exists())

    def test_changed_input_and_manifest_block_freeze(self):
        for change in ("frame", "manifest"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "holdout"
                attestation = self.fixture(root)
                path = (next((root / "02-frame-samples").glob("*/*.png")) if change == "frame"
                        else root.parent / "synthetic-development.csv")
                path.write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "alterado"):
                    tool.freeze(root, attestation)
                self.assertFalse((root / tool.FINAL).exists())

    def test_filename_leakage_without_equal_hash_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "holdout"
            attestation = self.fixture(root)
            path = root.parent / "synthetic-development.csv"
            path.write_text("image_sha256,source_group,filename\nOTHER,DEV,HOLDOUT_PERSON_101_frame_000000.png\n")
            audit_path = root / "05-qa/final-coco-audit/independence-documentary-audit.json"
            audit = tool.load(audit_path)
            audit["manifests"][0]["sha256"] = tool.sha(path)
            audit_path.write_bytes(tool.canonical_bytes(audit))
            candidate_path = root / "final/candidate-qa-manifest.json"
            candidate = tool.load(candidate_path)
            candidate["documentary_audit_sha256"] = tool.sha(audit_path)
            candidate_path.write_bytes(tool.canonical_bytes(candidate))
            with self.assertRaisesRegex(ValueError, "coincidencia"):
                tool.freeze(root, attestation)


if __name__ == "__main__":
    unittest.main()
