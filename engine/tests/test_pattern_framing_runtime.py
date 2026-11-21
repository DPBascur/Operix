import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock
from uuid import uuid4

import cv2
import numpy as np

from operix_engine import pattern_framing
from operix_engine.calibration import calibration_snapshot
from operix_engine.detection import BoundingBox
from operix_engine.framing import RecordedFraming
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.rtsp_pilot import Frame
from operix_engine.tracking import Track

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_rtsp_lab as lab


WIDTH, HEIGHT = 640, 360
CAMERA = "lab-cam-01"
SOURCE_KEY = hashlib.sha256(f"operix:camera:{CAMERA}".encode()).hexdigest()
CORNERS = {
    i: [[x, y], [x + .08, y], [x + .08, y + .08], [x, y + .08]]
    for i, (x, y) in enumerate(((.1, .2), (.7, .2), (.4, .7)))
}
EVIDENCE = {
    "width": WIDTH, "height": HEIGHT, "dictionary": "DICT_4X4_50",
    "marker_corners": {str(i): corners for i, corners in CORNERS.items()},
    "capture_signature": "a" * 64, "preview_sha256": "b" * 64, "image_transform": "native_frame",
    "provenance": "Test fixture", "layout": {}, "quality": {},
    "control": {"image_points": [[.2, .5], [.3, .5]], "distance_m": 1, "tolerance_m": .01,
                "provenance": "Synthetic control distance"},
}


def calibration(*, pattern=True, source_key=SOURCE_KEY):
    return calibration_snapshot({
        "status": "valid", "units": "m", "calibrated_at": "2026-11-09T00:00:00Z",
        "source_sha256": source_key, "version": 1, "zones_reviewed": True,
        "image_points": [[0, 0], [1, 0], [1, 1], [0, 1]],
        "ground_points_m": [[0, 0], [10, 0], [10, 10], [0, 10]],
        **({"pattern_evidence": EVIDENCE} if pattern else {}),
    })


def shifted_corners(dx):
    return {i: [[x + dx, y] for x, y in corners] for i, corners in CORNERS.items()}


class PatternFramingTests(TestCase):
    def setUp(self):
        self.guard = pattern_framing.PatternFramingGuard(EVIDENCE)
        self.image = np.zeros((HEIGHT, WIDTH, 3), np.uint8)

    def test_partial_and_malformed_observations_suspend_and_can_recover(self):
        for unknown in ({0: CORNERS[0]}, {**CORNERS, 0: [[float("nan"), 0]] * 4}, cv2.error()):
            with self.subTest(unknown=unknown):
                guard = pattern_framing.PatternFramingGuard(EVIDENCE)
                with mock.patch.object(pattern_framing, "_detect", side_effect=[CORNERS, unknown, CORNERS]) as detect:
                    self.assertEqual(guard.update(self.image, 0, 0), "VALID")
                    self.assertEqual(guard.update(self.image, 1, .25), "VALID")
                    self.assertEqual(guard.update(self.image, 2, 1), "UNAVAILABLE")
                    self.assertEqual(guard.update(self.image, 3, 1.75), "UNAVAILABLE")
                    self.assertEqual(guard.update(self.image, 4, 2), "VALID")
                    self.assertEqual(detect.call_count, 3)

    def test_dimensions_are_verified_even_between_samples(self):
        with mock.patch.object(pattern_framing, "_detect", return_value=CORNERS) as detect:
            self.assertEqual(self.guard.update(self.image, 0, 0), "VALID")
            self.assertEqual(self.guard.update(self.image[::2, ::2], 1, .1), "UNAVAILABLE")
            self.assertEqual(self.guard.status()["reason"], "capture_dimensions_mismatch")
            self.assertEqual(self.guard.update(self.image, 2, .2), "UNAVAILABLE")
            mismatched_profile = pattern_framing.PatternFramingGuard(EVIDENCE, dimensions=(320, 180))
            self.assertEqual(mismatched_profile.update(self.image, 0, 0), "UNAVAILABLE")
            detect.assert_called_once_with(self.image, EVIDENCE["dictionary"])

    def test_reference_survives_reconnect_and_invalidation(self):
        with mock.patch.object(pattern_framing, "_detect", return_value=shifted_corners(.04)) as detect:
            self.assertEqual(self.guard.update(self.image, 0, 0), "SUSPECT")
            self.guard.suspend("capture_unavailable")
            self.assertEqual(self.guard.update(self.image, 1, .5), "UNAVAILABLE")
            self.assertEqual(self.guard.update(self.image, 2, 1), "SUSPECT")
            self.assertEqual(self.guard.update(self.image, 3, 2), "INVALID")
            detect.return_value = CORNERS
            self.guard.suspend("awaiting_pattern_match")
            self.assertEqual(self.guard.update(self.image, 4, 3), "INVALID")
            self.assertEqual(self.guard.status()["invalidated_frame"], 3)
            self.assertEqual(detect.call_count, 3)

    def test_recorded_pattern_uses_confirmed_reference_from_first_frame(self):
        recorded = RecordedFraming(calibration())
        with mock.patch.object(pattern_framing, "_detect", side_effect=[shifted_corners(.01), CORNERS]) as detect:
            self.assertFalse(recorded.update(self.image, 0, 0, ()))
            self.assertEqual(recorded.status()["state"], "SUSPECT")
            self.assertTrue(recorded.update(self.image, 1, 1, ()))
            manual = RecordedFraming(calibration(pattern=False))
            self.assertTrue(manual.update(self.image, 0, 0, ()))
            self.assertEqual(manual.status()["reason"], "legacy_manual_only")
            self.assertEqual(detect.call_count, 2)

    def test_opencv_detection_matches_saved_order_and_normalization(self):
        from operix_engine.calibration_patterns import detect_marker_corners

        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        image = np.full((HEIGHT, WIDTH, 3), 255, np.uint8)
        for marker_id, (x, y) in enumerate(((60, 70), (430, 80), (240, 230))):
            marker = cv2.aruco.generateImageMarker(dictionary, marker_id, 48)
            image[y:y + 48, x:x + 48] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        corners = detect_marker_corners(image, EVIDENCE["dictionary"])
        self.assertEqual(set(corners), {0, 1, 2})
        guard = pattern_framing.PatternFramingGuard({
            **EVIDENCE, "marker_corners": {str(i): points for i, points in corners.items()},
        })
        self.assertEqual(guard.update(image, 0, 0), "VALID")
        shifted = np.roll(image, 24, axis=1)
        self.assertEqual(guard.update(shifted, 1, 1), "SUSPECT")
        occluded = image.copy()
        occluded[60:130, 50:115] = 255
        self.assertEqual(guard.update(occluded, 2, 2), "UNAVAILABLE")


class LabPatternTests(TestCase):
    def test_status_marks_disconnected_framing_unavailable_for_camera_ui(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            status = lab.WorkerStatus(SimpleNamespace(fps=4, width=WIDTH, height=HEIGHT, output=output))
            status.write("connecting")
            path = output / "status.json"
            self.assertNotIn("framing", json.loads(path.read_bytes())["metrics"])
            status.framing = pattern_framing.PatternFramingGuard(EVIDENCE)
            image = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
            with mock.patch.object(pattern_framing, "_detect", return_value=CORNERS):
                status.framing.update(image, 0, 0)
            status.write("processing")
            self.assertEqual(json.loads(path.read_bytes())["metrics"]["framing"]["state"], "VALID")
            status.write("reconnecting")
            framing = json.loads(path.read_bytes())["metrics"]["framing"]
            self.assertEqual((framing["state"], framing["reason"]), ("UNAVAILABLE", "capture_unavailable"))

    def test_load_context_requires_confirmed_pattern_for_same_camera(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            path = output / "config.json"
            for snapshot, accepted in (
                (None, True), (calibration(), True),
                (calibration(pattern=False), False), (calibration(source_key="c" * 64), False),
            ):
                with self.subTest(snapshot=bool(snapshot), accepted=accepted):
                    document = {"schema_version": 1, "view_id": CAMERA, "coordinate_system": "normalized",
                                "zones": [], "rules": [], "calibration": snapshot}
                    encoded = json.dumps(document).encode()
                    path.write_bytes(encoded)
                    context = {"analysis_run_id": str(uuid4()), "analysis_started_at": "2026-11-09T00:00:00Z",
                               "source": {"kind": "lab", "camera_id": CAMERA, "timestamp_basis": "LAB_RECEPTION_UTC",
                                          "video_sha256": "d" * 64, "config_sha256": hashlib.sha256(encoded).hexdigest()}}
                    (output / "context.json").write_text(json.dumps(context), encoding="utf-8")
                    if accepted:
                        _, loaded = lab.load_context(output, path)
                        self.assertEqual(loaded.calibration, snapshot)
                    else:
                        with self.assertRaisesRegex(ValueError, "patrón confirmado"):
                            lab.load_context(output, path)

    def test_runtime_uses_metric_geometry_only_while_verified_and_resets_rule_continuity(self):
        zone = Zone("floor", "Floor", ((0, 0), (1, 0), (1, 1), (0, 1)))
        rule = RuleConfig("pair", 1, True, {
            "kind": "person_forklift_proximity", "zone_id": "floor", "distance_unit": "m",
            "max_distance": 3.0, "minimum_duration_seconds": .5,
        })
        config = OperationalConfig(1, CAMERA, (zone,), (rule,), calibration())
        args = SimpleNamespace(width=WIDTH, height=HEIGHT, fps=4)
        pipeline = lab.LabPipeline(config, args, infer_remotely=True)
        image = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
        person = Track(1, 0, "person", .9, BoundingBox(170, 120, 200, 180))
        forklift = Track(1, 0, "forklift", .9, BoundingBox(264, 120, 334, 180))
        detected = SimpleNamespace(person=(), forklift=())
        pipeline.reset(1)
        with (mock.patch.object(pipeline.perception.person, "track", return_value=(person,)),
              mock.patch.object(pipeline.perception.forklift, "track", return_value=(forklift,)),
              mock.patch.object(pattern_framing, "_detect", side_effect=[CORNERS, {}, CORNERS]) as detect,
              mock.patch.object(pipeline.renderer, "render_proximity", wraps=pipeline.renderer.render_proximity) as render):
            def process(index, connection, received, timestamp):
                frame = Frame(index, connection, received, None, image)
                _, candidates, _, _ = pipeline.process(frame, timestamp, detected=detected, inference_ms=1.)
                _, spatial, result = render.call_args.args
                return spatial.proximities[0].ground, result, candidates

            ground, result, candidates = process(0, 1, 10., 0.)
            self.assertAlmostEqual(ground["distance"], 1.)
            self.assertIsNotNone(result)
            self.assertFalse(candidates)

            self.assertEqual(process(1, 1, 11., 1.), (None, None, ()))
            pipeline.reset(2)
            self.assertEqual(process(2, 2, 11.25, 0.), (None, None, ()))

            ground, _, candidates = process(3, 2, 12., .75)
            self.assertAlmostEqual(ground["distance"], 1.)
            self.assertFalse(candidates)
            _, _, candidates = process(4, 2, 12.5, 1.25)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].ground["units"], "m")
            self.assertEqual(detect.call_count, 3)

    def test_uncalibrated_pipeline_does_not_run_marker_guard(self):
        pipeline = lab.LabPipeline(OperationalConfig(1, CAMERA, (), ()),
                                   SimpleNamespace(width=WIDTH, height=HEIGHT, fps=4), infer_remotely=True)
        frame = Frame(0, 1, 10., None, np.zeros((HEIGHT, WIDTH, 3), np.uint8))
        with mock.patch.object(pattern_framing, "_detect") as detect:
            pipeline.reset(1)
            pipeline.process(frame, 0., detected=SimpleNamespace(person=(), forklift=()), inference_ms=1.)
            detect.assert_not_called()
        self.assertIsNone(pipeline.framing)
