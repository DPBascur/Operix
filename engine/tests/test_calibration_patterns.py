import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np

from operix_engine.calibration import calibration_snapshot, contacts_in_calibrated_area, project
from operix_engine.calibration_patterns import (
    detect_marker_corners, evaluate_control_distances, propose_calibration,
)


WIDTH, HEIGHT = 960, 600
VIEW = np.array([[128., 7., 130.], [5., 110., 75.], [.025, .035, 1.]])
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "propose_calibration.py"


def image_points(ground, view=VIEW):
    return cv2.perspectiveTransform(np.asarray([ground], dtype=float), view)[0]


def layout(dictionary="DICT_4X4_50", count=5):
    locations = ((0, 0), (5, .45), (4.8, 3), (.3, 3.3), (2, 1.4))
    quad = .55 * np.array([[0, 0], [1, 0], [1, 1], [0, 1]])
    return {"dictionary": dictionary, "ground_plane_confirmed": True, "markers": [
        {"id": marker, "corners_m": (np.roll(quad, marker % 4, axis=0) + origin).tolist()}
        for marker, origin in enumerate(locations[:count])
    ]}


def render(pattern, sample=0, *, missing=(), shift=(0, 0), misplaced=None, occluded=None, view=VIEW):
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(getattr(aruco, pattern["dictionary"]))
    frame = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    source = np.float32([[0, 0], [119, 0], [119, 119], [0, 119]])
    for marker in pattern["markers"]:
        marker_id = marker["id"]
        if marker_id in missing:
            continue
        target = image_points(marker["corners_m"], view) + shift
        if marker_id == misplaced:
            target += [45, -32]
        tag = aruco.generateImageMarker(dictionary, marker_id, 120)
        if marker_id == occluded:
            tag[:, :60] = 255
        matrix = cv2.getPerspectiveTransform(source, target.astype(np.float32))
        np.minimum(frame, cv2.warpPerspective(tag, matrix, (WIDTH, HEIGHT), borderValue=255), out=frame)
    frame[20:60, 20:60] = 180 + sample  # Distinct samples without changing camera framing.
    return frame


def canonical(proposal):
    return calibration_snapshot(dict(proposal, status="valid", units="m", source_sha256="b" * 64,
                                     version=1, calibrated_at="2026-11-21T00:00:00Z", zones_reviewed=True))


def cli(request, env=None):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), "propose"], input=json.dumps(request),
                          text=True, capture_output=True, timeout=15, env=env)


class CalibrationPatternTests(unittest.TestCase):
    def test_synthetic_ground_grid(self):
        pattern = layout()
        oblique = np.array([[145., 10., 145.], [5., 130., 120.], [.105, .055, 1.]])
        segments = {
            "short": ((.65, .7), (1.4, .7)),
            "interior": ((2., 1.), (3.7, 1.7)),
            "far_row": ((1.1, 3.), (3.9, 3.)),
            "near_side_boundary": ((4.7, 1.6), (4.7, 2.8)),
            "long_diagonal": ((.6, .35), (4.6, 3.13)),
        }
        for name, view in (("mild", VIEW), ("oblique", oblique)):
            for occlusion in (False, True):
                with self.subTest(view=name, occlusion=occlusion):
                    frames = [render(pattern, i, view=view,
                                     occluded=1 if occlusion and i == 0 else None)
                              for i in range(4)]
                    proposal = propose_calibration(frames, pattern)
                    self.assertEqual(proposal["status"], "candidate", proposal)
                    self.assertEqual(proposal["quality"]["observations_by_marker"]["1"], 3 if occlusion else 4)
                    self.assertTrue(proposal["grid"])
                    controls = [
                        {"image_points": (image_points(pair, view) / [WIDTH, HEIGHT]).tolist(),
                         "distance_m": float(np.linalg.norm(np.subtract(*pair))),
                         "tolerance_m": .03}
                        for pair in segments.values()
                    ]
                    outside = dict(controls[0], image_points=[[0., 0.], controls[0]["image_points"][1]])
                    checks = evaluate_control_distances(
                        canonical(proposal), [*controls, outside], dimensions=(WIDTH, HEIGHT))
                    self.assertEqual(checks[-1]["status"], "outside_footprint")
                    self.assertTrue(all(check["status"] == "pass" for check in checks[:-1]), checks)
                    errors = [check["absolute_error_m"] for check in checks[:-1]]
                    relative = [check["relative_error"] for check in checks[:-1]]
                    print(json.dumps(dict(
                        view=name, partial_occlusion=occlusion, image_coverage=proposal["coverage"],
                        absolute_error_m=dict(zip(segments, errors)),
                        relative_error=dict(zip(segments, relative)),
                        mean_absolute_error_m=float(np.mean(errors)),
                        max_absolute_error_m=max(errors),
                        p50_absolute_error_m=float(np.percentile(errors, 50)),
                        p95_absolute_error_m=float(np.percentile(errors, 95)),
                    )))

    def test_aruco_and_apriltag_recover_metric_scale_with_canonical_fit(self):
        for dictionary in ("DICT_4X4_50", "DICT_APRILTAG_36h11"):
            with self.subTest(dictionary=dictionary):
                pattern = layout(dictionary)
                frames = [render(pattern, i) for i in range(3)]
                result = propose_calibration(iter(frames), pattern)
                self.assertEqual(result["status"], "candidate", result)
                self.assertEqual(result["dictionary"], dictionary)
                self.assertEqual(result["quality"]["inlier_marker_ids"], list(range(5)))
                self.assertEqual(result["quality"]["supporting_frames"], 3)
                self.assertEqual(len(result["image_points"]), 16)
                self.assertEqual(len(result["reference_marker_corners"]), 4)
                self.assertEqual([p for quad in result["reference_marker_corners"].values() for p in quad],
                                 result["image_points"])
                selected = [pattern["markers"][int(i)] for i in result["reference_marker_corners"]]
                self.assertEqual(result["ground_points_m"], [p for tag in selected for p in tag["corners_m"]])
                preview = detect_marker_corners(frames[result["preview_frame_index"]], dictionary)
                self.assertEqual(result["marker_corners"], {str(i): points for i, points in preview.items()})
                snapshot = canonical(result)
                self.assertEqual(snapshot["homography"], result["homography"])
                self.assertGreater(result["coverage"], .15)
                for line in result["grid"]:
                    # Allow numerical roundoff at the footprint boundary.
                    center = np.mean(line, axis=0)
                    self.assertTrue(contacts_in_calibrated_area(snapshot, .99999 * np.asarray(line) + .00001 * center))
                pairs = image_points([[1, 1], [3, 2]]) / (WIDTH, HEIGHT)
                measured = np.linalg.norm(project(snapshot, pairs[0]) - project(snapshot, pairs[1]))
                self.assertAlmostEqual(measured, 5**.5, delta=.02)
                json.dumps(result, allow_nan=False)

    def test_partial_visibility_can_pass_with_temporal_and_spatial_support(self):
        pattern = layout()
        frames = [render(pattern, 0, occluded=1), render(pattern, 1, missing=(3,)), render(pattern, 2), render(pattern, 3)]
        result = propose_calibration(frames, pattern)
        self.assertEqual(result["status"], "candidate", result)
        self.assertEqual(result["quality"]["observations_by_marker"]["1"], 3)
        self.assertIn(result["preview_frame_index"], (2, 3))
        self.assertTrue(result["reference_marker_corners"].keys() <= result["marker_corners"].keys())

    def test_alternating_occlusions_cannot_confirm_a_never_visible_pattern(self):
        pattern = layout(count=4)
        frames = [render(pattern, i, missing=(2 + i % 2,)) for i in range(4)]
        result = propose_calibration(frames, pattern)
        self.assertEqual(result["status"], "requires_review")
        self.assertIn("insufficient_temporal_support", result["reasons"])
        self.assertEqual(result["quality"]["supporting_frames"], 0)

    def test_both_dictionaries_on_same_dimmed_and_blurred_perspective(self):
        endpoints = (image_points([[1, 1], [3, 2]]) / [WIDTH, HEIGHT]).tolist()
        control = {"image_points": endpoints, "distance_m": 5**.5}
        for dictionary in ("DICT_4X4_50", "DICT_APRILTAG_36h11"):
            with self.subTest(dictionary=dictionary):
                pattern = layout(dictionary)
                frames = [(cv2.GaussianBlur(render(pattern, i), (5, 5), 1.) * .48 + 14).astype(np.uint8)
                          for i in range(3)]
                result = propose_calibration(frames, pattern, [control])
                self.assertEqual(result["status"], "candidate", result)
                self.assertLess(result["quality"]["max_reprojection_error_px"], 1.)
                self.assertLess(result["control_distances"][0]["absolute_error_m"], .01)

    def test_ransac_excludes_a_misplaced_tag_and_requires_review(self):
        pattern = layout()
        result = propose_calibration([render(pattern, i, misplaced=4) for i in range(3)], pattern)
        self.assertEqual(result["status"], "requires_review", result)
        self.assertIn("marker_layout_disagreement", result["reasons"])
        self.assertEqual(result["quality"]["rejected_marker_ids"], [4])
        self.assertNotIn("4", result["reference_marker_corners"])
        self.assertIn("4", result["marker_corners"])
        self.assertEqual(result["homography"], canonical(result)["homography"])

    def test_single_tag_collinear_layout_and_replayed_frames_cannot_pass(self):
        single = layout(count=1)
        self.assertEqual(propose_calibration([render(single, i) for i in range(3)], single)["status"], "invalid")
        pattern = layout(count=3)
        for marker, x in zip(pattern["markers"], (0., 2., 4.)):
            points = np.array(marker["corners_m"])
            marker["corners_m"] = (points - points.min(axis=0) + [x, 1.]).tolist()
        result = propose_calibration([render(pattern, i) for i in range(3)], pattern)
        self.assertEqual(result["status"], "requires_review")
        self.assertIn("insufficient_distribution", result["reasons"])
        pattern = layout()
        image = render(pattern)
        result = propose_calibration([image] * 3, pattern)
        self.assertEqual(result["status"], "requires_review")
        self.assertIn("insufficient_temporal_support", result["reasons"])

    def test_moving_frame_cannot_create_a_candidate(self):
        pattern = layout()
        result = propose_calibration([render(pattern), render(pattern, 1, shift=(18., -11.)), render(pattern, 2)], pattern)
        self.assertNotEqual(result["status"], "candidate")
        self.assertGreater(result["quality"]["max_marker_deviation_px"], 15.)
        self.assertTrue(result["quality"]["unstable_marker_ids"])

    def test_two_shifted_views_cannot_pass_by_averaging_their_corners(self):
        pattern = layout()
        result = propose_calibration([render(pattern), render(pattern, 1, shift=(5., 0.))], pattern)
        self.assertLess(result["quality"]["max_marker_deviation_px"], 3.)
        self.assertGreater(result["quality"]["max_marker_span_px"], 4.)
        self.assertEqual(result["status"], "invalid")

    def test_control_pass_fail_outside_and_reused_references(self):
        pattern = layout()
        frames = [render(pattern, i) for i in range(3)]
        endpoints = (image_points([[1, 1], [3, 1]]) / [WIDTH, HEIGHT]).tolist()
        good = {"image_points": endpoints, "distance_m": 2.}
        wrong = dict(good, distance_m=3.)
        result = propose_calibration(frames, pattern, [good])
        self.assertEqual(result["status"], "candidate")
        self.assertEqual(result["control_distances"][0]["status"], "pass")
        result = propose_calibration(frames, pattern, [wrong])
        self.assertEqual(result["status"], "requires_review")
        self.assertIn("control_distance_failed", result["reasons"])
        outside = dict(good, image_points=[[0., 0.], endpoints[1]])
        reused = dict(good, image_points=[result["image_points"][0], endpoints[1]])
        checks = evaluate_control_distances(canonical(result), [good, wrong, outside, reused], dimensions=(WIDTH, HEIGHT))
        self.assertEqual([check["status"] for check in checks],
                         ["pass", "fail", "outside_footprint", "uses_fit_references"])
        self.assertAlmostEqual(checks[0]["estimated_distance_m"], 2., delta=.02)

    def test_rejects_unconfirmed_irregular_and_mixed_size_inputs(self):
        pattern = layout()
        with self.assertRaises(ValueError):
            propose_calibration([], dict(pattern, ground_plane_confirmed=False))
        image = render(pattern)
        with self.assertRaises(ValueError):
            propose_calibration([image, image[:, :-1]], pattern)
        pattern["markers"][0]["corners_m"][0][0] += .25
        with self.assertRaises(ValueError):
            propose_calibration([], pattern)

    def test_cli_samples_local_video_and_returns_one_tied_preview(self):
        pattern = layout()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "fixture.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 12, (WIDTH, HEIGHT))
            self.assertTrue(writer.isOpened())
            try:
                for i in range(10):
                    writer.write(cv2.cvtColor(render(pattern, i * 2), cv2.COLOR_GRAY2BGR))
            finally:
                writer.release()
            response = cli(dict(layout=pattern, video_path=str(path), width=WIDTH, height=HEIGHT))
            self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
            self.assertEqual(response.stderr, "")
            result = json.loads(response.stdout)
            self.assertEqual(result["status"], "candidate", result["quality"])
            self.assertEqual((result["width"], result["height"]), (WIDTH, HEIGHT))
            self.assertEqual(result["quality"]["frames_sampled"], 5)
            pixels = np.frombuffer(base64.b64decode(result["preview_jpeg"], validate=True), dtype=np.uint8)
            jpeg = cv2.imdecode(pixels, cv2.IMREAD_GRAYSCALE)
            self.assertEqual(jpeg.shape, (HEIGHT, WIDTH))
            decoded = detect_marker_corners(jpeg, pattern["dictionary"])
            for marker, corners in result["marker_corners"].items():
                np.testing.assert_allclose(decoded[int(marker)], corners, atol=.002)
            mismatch = cli(dict(layout=pattern, video_path=str(path), width=WIDTH + 1))
            self.assertEqual(mismatch.returncode, 2)
            self.assertEqual(json.loads(mismatch.stdout)["reasons"], ["invalid_request"])

    def test_cli_rejects_unpinned_rtsp_without_exposing_credentials(self):
        env = dict(os.environ, OPERIX_RTSP_URL="rtsp://user:secret@127.0.0.2/test", OPERIX_RTSP_ALLOWED_IP="127.0.0.1")
        response = cli(dict(layout=layout()), env)
        self.assertEqual(response.returncode, 2)
        self.assertEqual(json.loads(response.stdout)["status"], "invalid")
        self.assertEqual(response.stderr, "")
        self.assertNotIn("secret", response.stdout)

    def test_cli_corrupt_media_returns_only_generic_json_error(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "fixture.mp4"
            path.write_bytes(b"corrupt video")
            response = cli(dict(layout=layout(), video_path=str(path)))
        self.assertEqual(response.returncode, 2)
        self.assertEqual(json.loads(response.stdout)["reasons"], ["capture_failed"])
        self.assertEqual(response.stderr, "")
        self.assertNotIn("fixture.mp4", response.stdout)

    def test_large_preview_fits_the_backend_response_budget(self):
        frame = np.random.default_rng(0).integers(0, 256, (1080, 1920, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "noisy.png"
            self.assertTrue(cv2.imwrite(str(path), frame))
            response = cli(dict(layout=layout(), frame_paths=[str(path)]))
        self.assertEqual(response.returncode, 0, response.stdout[:1000] + response.stderr)
        self.assertEqual(response.stderr, "")
        result = json.loads(response.stdout)
        self.assertEqual((result["width"], result["height"]), (1920, 1080))
        self.assertLessEqual(len(result["preview_jpeg"]), 720_000)
        self.assertLessEqual(len(response.stdout), 768_000)
