# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "industrial_detector"))
from evaluate import calculate_ap, eligibility, operating_point
from distill import mean_response_loss, trusted_pairs
from evaluate_v2 import forklift_diagnostics, quality
from prepare import digest, normalize_box
from prepare_v2 import crop_labels
from prepare_v3 import mirrored_consensus
from prepare_verified_crops import prepare as prepare_verified_crops
from rtsp_probe_worker import SinglePerception
from train import freeze_person_outputs, mask_class_loss, mask_pseudo_class_loss
from specialized import SpecializedClassifier

from operix_engine.person_metrics import Prediction


class IndustrialDetectorResearchTest(unittest.TestCase):
    def test_distillation_rejects_far_ambiguous_and_duplicate_teacher_boxes(self):
        truth = torch.tensor([[0., 0., 10., 10.], [2., 0., 12., 10.], [30., 30., 40., 40.]])
        proposals = torch.tensor([[1., 0., 11., 10., .99], [50., 50., 60., 60., .99],
                                  [30., 30., 40., 40., .75], [31., 30., 40., 40., .95]])
        targets, responses = trusted_pairs(truth, proposals, .65)
        self.assertEqual(targets.tolist(), [2])
        torch.testing.assert_close(responses, proposals[2:3])

    def test_balanced_distillation_does_not_weight_role_by_number_of_matches(self):
        groups = [[torch.tensor(0.)] * 9, [torch.tensor(1.)]]
        self.assertAlmostEqual(float(mean_response_loss(groups, balanced=True)), .5)
        self.assertAlmostEqual(float(mean_response_loss(groups, balanced=False)), .1)

    def test_specialized_head_preserves_logits_and_keeps_person_branch_frozen(self):
        nn = torch.nn
        tower = nn.Sequential(nn.Conv2d(4, 4, 1), nn.Sequential(nn.BatchNorm2d(4), nn.SiLU()),
                              nn.Conv2d(4, 3, 1)).eval()
        inputs = torch.ones(1, 4, 5, 5)
        expected = tower(inputs).detach()
        split = SpecializedClassifier(tower).eval()
        torch.testing.assert_close(split(inputs), expected)
        split.train()
        self.assertFalse(split.person.training)
        split(inputs).sum().backward()
        self.assertTrue(all(p.grad is None for p in split.person.parameters()))
        self.assertTrue(all(p.grad is not None for p in split.equipment.parameters()))
    def test_teacher_supervises_only_positive_assignments(self):
        logits = torch.zeros((1, 2, 3), requires_grad=True)
        labels = torch.tensor([[[1., 0., 0.], [0., 0., 0.]]])
        bce = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels, reduction="none")
        trusted = torch.tensor([[[False, True, False]]])
        pseudo = torch.tensor([[[True, False, False]]])
        mask_pseudo_class_loss(bce, labels, trusted, pseudo).sum().backward()
        torch.testing.assert_close(logits.grad, torch.tensor([[[-.175, .5, 0.], [0., .5, 0.]]]))

    def test_teacher_mirror_check_favors_verified_labels_and_deduplicates(self):
        a = (.25, .25, .5, .75)
        b = (.75, .25, .875, .75)
        mirrored = [((.5, .25, .75, .75), .9), ((.125, .25, .25, .75), .8)]
        self.assertEqual(mirrored_consensus([(a, .99), (a, .9), (b, .9)], mirrored, [(1, b)]),
                         [(a, .9)])

    def test_reviewed_machine_crop_only_supervises_forklift(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            base.mkdir()
            image = base / "images/train/base.jpg"
            image.parent.mkdir(parents=True)
            Image.new("RGB", (100, 80)).save(image)
            label = base / "labels/train/base.txt"
            label.parent.mkdir(parents=True)
            label.touch()
            manifest = base / "manifest.json"
            manifest.write_text(json.dumps([{"image": "images/train/base.jpg", "split": "train",
                                             "source_sha256": digest(image)}]))
            (base / "dataset.yaml").write_text(f'path: "{base.as_posix()}"\n')
            source = root / "station.jpg"
            Image.new("RGB", (100, 80), "white").save(source)
            reviews = root / "reviews.json"
            reviews.write_text(json.dumps({"parent_manifest_sha256": digest(manifest), "crops": [
                {"file": source.name, "sha256": digest(source), "member": "reviewed.jpg",
                 "window": [.25, .25, .75, .75], "source": "camera", "capture_group": "01",
                 "review": "Fixed press inside crop", "split": "development"},
            ]}))
            output = root / "output"
            prepare_verified_crops(base, reviews, output)
            row = json.loads((output / "manifest.json").read_text())[-1]
            self.assertEqual((row["supervised"], row["boxes"]), ([1], []))
            with Image.open(output / row["image"]) as crop:
                self.assertEqual(crop.size, (50, 40))
            self.assertEqual(len(json.loads(manifest.read_text())), 1)

    def test_unsupervised_class_has_zero_gradient(self):
        logits = torch.zeros((2, 1, 3), requires_grad=True)
        bce = torch.nn.functional.binary_cross_entropy_with_logits(
            logits, torch.zeros_like(logits), reduction="none"
        )
        mask = torch.tensor([[[True, True, False]], [[False, True, True]]])
        mask_class_loss(bce, mask).sum().backward()
        torch.testing.assert_close(logits.grad, mask.float() * .5)

    def test_trained_classifier_only_changes_equipment_rows(self):
        nn = torch.nn
        detector = nn.Module()
        detector.names = {0: "person", 1: "forklift", 2: "pallet_jack"}
        feature = nn.BatchNorm2d(4)
        head = nn.Module()
        head.cv3 = nn.ModuleList(nn.Sequential(nn.Conv2d(4, 3, 1)) for _ in range(3))
        detector.model = nn.ModuleList([feature, head])
        norms = freeze_person_outputs(detector)
        self.assertEqual(norms, (feature,))
        optimizer = torch.optim.AdamW(detector.parameters(), lr=.1, weight_decay=0)
        classifier = head.cv3[0][-1]
        before = classifier.weight.detach().clone()
        classifier(torch.ones((1, 4, 2, 2))).sum().backward()
        optimizer.step()
        torch.testing.assert_close(before[0], classifier.weight[0], rtol=0, atol=0)
        self.assertFalse(torch.equal(before[1:], classifier.weight[1:]))
        self.assertFalse(feature.weight.requires_grad)

    def test_ap_one_to_one_and_false_positive_count(self):
        box = (0., 0., 1., 1.)
        ground = {"a": (box,), "b": ()}
        predicted = {"a": (Prediction(box, .9), Prediction(box, .8)),
                     "b": (Prediction(box, .7),)}
        self.assertAlmostEqual(calculate_ap(ground, predicted, .5), 1.)
        self.assertEqual(operating_point(ground, predicted, .6)["fp"], 2)

    def test_promotion_rejects_person_regression_despite_equipment_gain(self):
        def score(p_recall, f_f1):
            return {
                "person": {"ap50": .8, "operating_point": {"recall": p_recall, "precision": .8}},
                "forklift": {"operating_point": {"recall": .7, "precision": .8, "f1": f_f1, "fp_per_image": .2}},
            }
        self.assertFalse(eligibility(score(.8, .61), score(.7, .78))["passed"])
        self.assertTrue(eligibility(score(.8, .61), score(.79, .78))["passed"])

    def test_normalized_box_codec_preserves_class_and_bounds(self):
        self.assertEqual(normalize_box(2, (10, 30, 80, 100), 100, 200),
                         (2, (.1, .15, .8, .5)))
        with self.assertRaises(ValueError):
            normalize_box(1, (100, 20, 90, 40), 150, 150)

    def test_one_inference_routes_only_supported_operational_roles(self):
        person = SimpleNamespace(class_name="person", confidence=.9)
        low_forklift = SimpleNamespace(class_name="forklift", confidence=.2)
        forklift = SimpleNamespace(class_name="forklift", confidence=.8)
        pallet = SimpleNamespace(class_name="pallet_jack", confidence=1.)
        channels = SimpleNamespace(person=Mock(class_name="person"), forklift=Mock(class_name="forklift"))
        channels.person.track.return_value = ()
        channels.forklift.track.return_value = ()
        detector = Mock()
        detector.detect.return_value = (person, low_forklift, forklift, pallet)
        perception = SinglePerception(channels, detector, {"person": .1, "forklift": .45, "pallet_jack": .5})
        frame = object()
        result, _ = perception.process(frame)
        detector.detect.assert_called_once_with(frame)
        channels.person.track.assert_called_once_with((person,))
        channels.forklift.track.assert_called_once_with((forklift,))
        self.assertEqual(result.person_detections, (person,))
        self.assertEqual(result.forklift_detections, (forklift,))

    def test_small_object_crop_relabels_visible_boxes_and_rejects_bad_truncation(self):
        window = (.25, .25, .75, .75)
        boxes = [(1, (.375, .375, .5, .5)), (0, (0., 0., .125, .125))]
        self.assertEqual(crop_labels(boxes, window), [(1, (.25, .25, .5, .5))])
        self.assertIsNone(crop_labels(boxes + [(2, (.5, .5, 1., 1.))], window))

    def test_v2_reserve_without_person_annotations_blocks_promotion(self):
        forklift = {"operating_point":{"precision":1.,"recall":1.,"f1":1.,"fp_per_image":0.},
                    "instances":32,"small_recall":{"instances":12,"recall":.5}}
        scores = {"classes":{"forklift":forklift},"false_positives":{}}
        gate = quality(scores, scores, scores, real=True)
        self.assertFalse(gate["checks"]["real_person_coverage"])
        self.assertFalse(gate["passed"])

    def test_v2_duplicate_may_overlap_reference_without_large_pairwise_iou(self):
        row = {"image":"a","supervised":[1],"boxes":[(1,(0.,0.,1.,1.))]}
        detections = {"forklift":{"a":(Prediction((0.,0.,.6,1.),.9),Prediction((.4,0.,1.,1.),.8))}}
        report = forklift_diagnostics([row],detections,.5)
        distribution = report["duplicate_iou_to_matched_prediction"]
        self.assertEqual(distribution["count"],1)
        self.assertAlmostEqual(distribution["median"],.2)
