"""La residencia conserva modelos, no identidades ni estados de análisis."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.dual_perception import ClassPerceptionChannel
from operix_engine.model_residency import ResidentDetectors
from operix_engine.yolo_detector import YoloDetectorConfig


class ModelResidencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.weights = Path(temporary.name) / "synthetic.pt"
        self.weights.touch()

    def test_three_jobs_load_only_two_identical_detectors(self):
        factory = Mock(side_effect=lambda config: Mock(config=config))
        resident = ResidentDetectors(factory)
        configs = (YoloDetectorConfig(self.weights, confidence_threshold=0.1),
                   YoloDetectorConfig(self.weights, confidence_threshold=0.45, iou_threshold=0.55))
        jobs = [tuple(resident(config) for config in configs) for _ in range(3)]
        self.assertEqual(factory.call_count, 2)
        for job in jobs:
            self.assertIs(job[0], jobs[0][0])
            self.assertIs(job[1], jobs[0][1])

    def test_new_configuration_is_not_silently_ignored_or_unbounded(self):
        resident = ResidentDetectors(Mock())
        resident(YoloDetectorConfig(self.weights, confidence_threshold=0.1))
        resident(YoloDetectorConfig(self.weights, confidence_threshold=0.45))
        with self.assertRaisesRegex(ValueError, "reinicio"):
            resident(YoloDetectorConfig(self.weights, confidence_threshold=0.2))

    def test_tracks_and_channel_identity_maps_are_fresh_per_job(self):
        detector = Mock(class_names={0: "person"})
        resident = ResidentDetectors(lambda _: detector)
        config = YoloDetectorConfig(self.weights)
        channels = [ClassPerceptionChannel("person", resident(config), ByteTracker(ByteTrackConfig()))
                    for _ in range(3)]
        channels[0]._local_ids[99] = 1
        self.assertEqual(channels[1]._local_ids, {})
        self.assertEqual(channels[2]._local_ids, {})
        self.assertEqual(len({id(channel.tracker) for channel in channels}), 3)
