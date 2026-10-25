# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""PERSON V1 exclusivamente con fixtures sintéticos, sin modelos ni holdout real."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from operix_engine.person_protocol import (
    DATASET_SHA, INFERENCE, MODEL_HASHES, canonical, digest, evaluate, ground_truth_records, match, metrics,
    seal_run, source_digest, technical_invalidation, validate_dataset, validate_protocol, validate_shape,
)


class PersonProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads((Path(__file__).parents[1] /
            "config/evaluation/person-evaluation-protocol-v1.json").read_text(encoding="utf-8"))

    def prediction(self, box=None, confidence=.9, index=0, name="person"):
        return dict(stable_index=index, class_name=name, confidence=confidence,
                    bbox_xyxy=box or [0, 0, 10, 10])

    def gt(self, box=None, annotation_id=1):
        return dict(annotation_id=annotation_id, bbox_xyxy=box or [0, 0, 10, 10])

    def fixture(self):
        records, frames = [], []
        for i in range(91):
            # 25 singles + 17*4 + 25*3 persons = 168, then 24 negatives.
            n = 1 if i < 25 else 4 if i < 42 else 3 if i < 67 else 0
            gt = [self.gt([j*20, 0, j*20+10, 10], j+1) for j in range(n)]
            image_sha = hashlib.sha256(f"synthetic-image-{i}".encode()).hexdigest()
            row = dict(image_id=f"synthetic:{i}", image_sha256=image_sha,
                       source_group=f"HOLDOUT_PERSON_{101+i%5}", filename=f"synthetic_{i:06d}.png",
                       evaluation_included=True, person_boxes=n, ground_truth=gt)
            records.append(row)
            frames.append(dict(image_id=row["image_id"], image_sha256=image_sha,
                               predictions=[self.prediction(g["bbox_xyxy"], index=j) for j, g in enumerate(gt)]))
        raw = dict(protocol_id=self.protocol["protocol_id"], protocol_sha256=digest(self.protocol),
                   dataset_id="PERSON_FINAL_HOLDOUT_V2", dataset_freeze_sha256=DATASET_SHA,
                   model_id="CURRENT_PERSON", model_sha256=MODEL_HASHES["CURRENT_PERSON"],
                   inference_configuration=copy.deepcopy(INFERENCE),
                   software_versions=copy.deepcopy(self.protocol["software_versions"]), frames=frames)
        return records, raw

    def test_perfect_match(self):
        self.assertEqual(match([self.gt()], [self.prediction()], .5)["tp"], 1)

    def test_iou_exactly_half(self):
        result = match([self.gt()], [self.prediction([0, 0, 5, 10])], .5)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 0))

    def test_iou_below_half(self):
        result = match([self.gt()], [self.prediction([0, 0, 4.999, 10])], .5)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 1, 1))

    def test_multiple_predictions_same_gt(self):
        result = match([self.gt()], [self.prediction(index=i) for i in range(3)], .5)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 2, 0))

    def test_multiple_gt_and_iou_tie_annotation_id(self):
        gt = [self.gt(annotation_id=9), self.gt(annotation_id=2)]
        result = match(gt, [self.prediction()], .5)
        self.assertEqual(result["assignments"][0]["annotation_id"], 2)
        self.assertEqual(result["fn"], 1)

    def test_confidence_ordering(self):
        result = match([self.gt()], [self.prediction(confidence=.5, index=0),
                                    self.prediction(confidence=.9, index=1)], .5)
        self.assertEqual(result["assignments"][0]["prediction_index"], 1)

    def test_equal_confidence_stable_index(self):
        predictions = [self.prediction(index=7), self.prediction(index=2)]
        result = match([self.gt()], predictions, .5)
        self.assertEqual(result["assignments"][0]["prediction_index"], 2)
        self.assertEqual(result, match([self.gt()], list(reversed(predictions)), .5))

    def test_zero_predictions(self):
        self.assertEqual(match([self.gt()], [], .5)["fn"], 1)
        self.assertEqual(metrics([match([self.gt()], [], .5)]),
                         dict(tp=0, fp=0, fn=1, precision=None, recall=0, f1=0))

    def test_zero_gt_and_empty_denominators(self):
        self.assertEqual(match([], [self.prediction()], .5)["fp"], 1)
        self.assertEqual(metrics([]), dict(tp=0, fp=0, fn=0, precision=None, recall=None, f1=None))

    def test_class_and_confidence_filter(self):
        result = match([self.gt()], [self.prediction(name="forklift"),
                                    self.prediction(confidence=.09, index=1)], .5)
        self.assertEqual((result["accepted_predictions"], result["fn"]), (0, 1))
        self.assertEqual(match([self.gt()], [self.prediction(confidence=.10)], .5)["tp"], 1)

    def test_iou_075_secondary(self):
        p = self.prediction([0, 0, 7.5, 10])
        self.assertEqual(match([self.gt()], [p], .75)["tp"], 1)
        self.assertEqual(match([self.gt()], [self.prediction([0, 0, 7.49, 10])], .75)["tp"], 0)

    def test_micro_family_and_multi_person(self):
        records, raw = self.fixture()
        result = evaluate(records, raw, self.protocol, {})
        self.assertEqual(result["overall"], dict(tp=168, fp=0, fn=0, precision=1, recall=1, f1=1))
        self.assertEqual(sum(r["tp"] for r in result["per_family"].values()), 168)
        self.assertEqual(result["secondary"]["multi_person_recall"]["frames"], 42)
        self.assertEqual(result["secondary"]["multi_person_recall"]["recall"], 1)

    def test_negative_false_alarm_and_positive_complete_miss(self):
        records, raw = self.fixture()
        raw["frames"][-1]["predictions"] = [self.prediction()]
        raw["frames"][0]["predictions"] = []
        result = evaluate(records, raw, self.protocol, {})
        self.assertEqual(result["overall"]["tp"], 167)
        self.assertEqual(result["secondary"]["negative_frame_false_alarm_rate"]["rate"], 1/24)
        self.assertEqual(result["secondary"]["positive_frame_complete_miss_rate"]["rate"], 1/67)

    def test_duplicate_image_and_expected_91(self):
        records, raw = self.fixture()
        with self.assertRaisesRegex(ValueError, "91"):
            validate_dataset(records[:-1], self.protocol, DATASET_SHA)
        records[1]["image_sha256"] = records[0]["image_sha256"]
        with self.assertRaisesRegex(ValueError, "duplicada"):
            evaluate(records, raw, self.protocol, {})

    def test_wrong_dataset_freeze_sha(self):
        records, raw = self.fixture()
        raw["dataset_freeze_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "freeze SHA"):
            evaluate(records, raw, self.protocol, {})

    def test_wrong_model_sha(self):
        records, raw = self.fixture()
        raw["model_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "model SHA"):
            evaluate(records, raw, self.protocol, {})

    def test_config_mismatch(self):
        records, raw = self.fixture()
        raw["inference_configuration"]["confidence_threshold"] = .2
        with self.assertRaisesRegex(ValueError, "configuraci"):
            evaluate(records, raw, self.protocol, {})

    def test_protocol_and_software_mismatch(self):
        for field in ("protocol_sha256", "software_versions"):
            records, raw = self.fixture()
            raw[field] = "wrong" if field.endswith("sha256") else {}
            with self.assertRaises(ValueError):
                evaluate(records, raw, self.protocol, {})

    def test_predictions_missing_or_duplicate_frames(self):
        for field in ("missing", "duplicate"):
            records, raw = self.fixture()
            if field == "missing":
                raw["frames"].pop()
            else:
                raw["frames"][1] = copy.deepcopy(raw["frames"][0])
            with self.assertRaises(ValueError):
                evaluate(records, raw, self.protocol, {})

    def test_nan_bbox_and_schema(self):
        records, raw = self.fixture()
        raw["frames"][0]["predictions"][0]["bbox_xyxy"][0] = float("nan")
        with self.assertRaises(ValueError):
            evaluate(records, raw, self.protocol, {})
        with self.assertRaises(ValueError):
            validate_shape({}, self.protocol["artifact_schemas"]["run_receipt"])

    def test_serialization_order_and_protocol_schema(self):
        validate_protocol(self.protocol)
        self.assertEqual(canonical(self.protocol), canonical(dict(reversed(list(self.protocol.items())))))
        records, raw = self.fixture()
        result = evaluate(records, raw, self.protocol, {})
        self.assertEqual(canonical(result), canonical(evaluate(list(reversed(records)), raw, self.protocol, {})))

    def test_receipt_and_artifact_sealing_no_overwrite(self):
        records, raw = self.fixture()
        metadata = dict(date_time_utc="2026-01-01T00:00:00Z", git_head="synthetic", python="synthetic",
                        pytorch="synthetic", ultralytics="synthetic", cuda="none", gpu="none", os="synthetic",
                        device="cuda:0", batch_size=1, seed=0)
        result = evaluate(records, raw, self.protocol, metadata)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/"synthetic-run"
            receipt = seal_run(output, raw, result, self.protocol, metadata)
            self.assertEqual(receipt["prediction_artifact_sha256"], digest(raw))
            self.assertEqual(receipt["metrics_artifact_sha256"], digest(result))
            self.assertEqual(hashlib.sha256((output/"metrics.json").read_bytes()).hexdigest().upper(), digest(result))
            with self.assertRaises(ValueError):
                seal_run(output, raw, result, self.protocol, metadata)

    def test_invalidation_preserves_original_receipt(self):
        receipt = dict(protocol_sha256="synthetic", dataset_freeze_sha256="synthetic",
                       model_id="synthetic", model_sha256="synthetic", inference_configuration=INFERENCE)
        before = copy.deepcopy(receipt)
        invalid = technical_invalidation(receipt, bug="synthetic reader bug", correction="reader fix",
                                        regression_tests="synthetic regression, independent of detector performance")
        self.assertEqual(invalid["status"], "INVALIDATED_TECHNICAL_RUN")
        self.assertEqual(receipt, before)
        self.assertEqual(invalid["original_receipt_sha256"], digest(receipt))
        with self.assertRaises(ValueError):
            technical_invalidation(receipt, bug="", correction="fix", regression_tests="test")

    def test_seal_rejects_changed_model_identity(self):
        records, raw = self.fixture()
        result = evaluate(records, raw, self.protocol, {})
        raw["model_sha256"] = "wrong"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            seal_run(Path(tmp)/"run", raw, result, self.protocol, {})

    def test_family_rates_never_replace_micro(self):
        records, raw = self.fixture()
        raw["frames"][0]["predictions"] = []
        raw["frames"][-1]["predictions"] = [self.prediction()]
        result = evaluate(records, raw, self.protocol, {})
        self.assertEqual(result["overall"]["tp"], sum(v["tp"] for v in result["per_family"].values()))
        self.assertEqual(result["overall"]["recall"], 167/168)

    def test_source_hash_survives_windows_checkout_eol(self):
        with tempfile.TemporaryDirectory() as tmp:
            lf, crlf = Path(tmp)/"lf.py", Path(tmp)/"crlf.py"
            lf.write_bytes(b"first\nsecond\n")
            crlf.write_bytes(b"first\r\nsecond\r\n")
            self.assertEqual(source_digest(lf), source_digest(crlf))

    def test_coco_reader_preserves_ids_and_boxes_without_images(self):
        data = dict(categories=[dict(id=1, name="person")],
                    images=[dict(id=4, file_name="synthetic.png")],
                    annotations=[dict(id=19, image_id=4, category_id=1, bbox=[1.25, 2.5, 10, 20])])
        raw = canonical(data)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root/"04-exports/HOLDOUT_PERSON_101/annotations.zip"
            archive.parent.mkdir(parents=True)
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("annotations/instances_default.json", raw)
            before = archive.read_bytes()
            manifest = dict(freeze_sha256=DATASET_SHA, records=[dict(source_group="HOLDOUT_PERSON_101",
                coco_image_id=4, filename="synthetic.png", annotation_export_sha256=hashlib.sha256(before).hexdigest().upper(),
                annotation_json_sha256=hashlib.sha256(raw).hexdigest().upper())])
            result = ground_truth_records(root, manifest)
            self.assertEqual(result[0]["ground_truth"], [dict(annotation_id=19, bbox_xyxy=[1.25, 2.5, 11.25, 22.5])])
            self.assertEqual(archive.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
