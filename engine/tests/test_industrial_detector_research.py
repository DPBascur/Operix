# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "industrial_detector"))
from evaluate import calculate_ap, eligibility, operating_point
from prepare import normalize_box
from rtsp_probe_worker import SinglePerception
from train import freeze_person_outputs, mask_class_loss

from operix_engine.person_metrics import Prediction


class IndustrialDetectorResearchTest(unittest.TestCase):
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
