import unittest

from engine.scripts.compare_lab_proposals import pair_boxes


class ProposalAgreementTests(unittest.TestCase):
    def test_proposals_count_at_most_once_and_reject_low_iou(self):
        first = [{"bbox_xyxy": (0, 0, 10, 10)}, {"bbox_xyxy": (20, 20, 30, 30)}]
        second = [
            {"bbox_xyxy": (0, 0, 10, 10)},
            {"bbox_xyxy": (1, 1, 10, 10)},
            {"bbox_xyxy": (22, 22, 40, 40)},
        ]
        self.assertEqual(pair_boxes(first, second), [{"first_index": 0, "second_index": 0, "iou": 1.0}])
        self.assertEqual(pair_boxes([], second), [])
