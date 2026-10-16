# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas sintéticas del renderer y las trayectorias de OP-60."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import cv2
import numpy as np

from operix_engine.detection import BoundingBox, Detection
from operix_engine.operational_config import Zone
from operix_engine.tracking import Track
from operix_engine.visualization import (
    OpenCvRenderer,
    TrajectoryAccumulator,
    TrajectoryPoint,
    VisualizationConfig,
)
from operix_engine.zone_geometry import NormalizedPoint, point_in_zone


def detection(
    box: BoundingBox | None = None,
    *,
    confidence: float = 0.87,
) -> Detection:
    return Detection(0, "person", confidence, box or BoundingBox(20.0, 20.0, 60.0, 80.0))


def track(
    track_id: int = 1,
    box: BoundingBox | None = None,
    *,
    confidence: float = 0.87,
) -> Track:
    return Track(
        track_id,
        0,
        "person",
        confidence,
        box or BoundingBox(20.0, 20.0, 60.0, 80.0),
    )


class OpenCvRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = np.zeros((140, 180, 3), dtype=np.uint8)
        self.renderer = OpenCvRenderer()

    def test_preserves_shape_dtype_and_original_frame(self) -> None:
        original = self.frame.copy()
        annotated = self.renderer.render_detections(self.frame, (detection(),))

        self.assertEqual(annotated.shape, self.frame.shape)
        self.assertEqual(annotated.dtype, self.frame.dtype)
        self.assertFalse(np.shares_memory(annotated, self.frame))
        np.testing.assert_array_equal(self.frame, original)

    def test_empty_inputs_return_identical_copies(self) -> None:
        outputs = (
            self.renderer.render_detections(self.frame, ()),
            self.renderer.render_tracks(self.frame, ()),
        )
        for output in outputs:
            with self.subTest():
                np.testing.assert_array_equal(output, self.frame)
                self.assertFalse(np.shares_memory(output, self.frame))

    def test_detection_box_and_label_modify_frame(self) -> None:
        annotated = self.renderer.render_detections(self.frame, (detection(),))
        self.assertGreater(np.count_nonzero(annotated), 0)
        np.testing.assert_array_equal(annotated[80, 20], np.asarray([0, 255, 0]))

    def test_track_colors_are_deterministic_and_distinguishable(self) -> None:
        first = self.renderer.render_tracks(self.frame, (track(1),))
        repeated = self.renderer.render_tracks(self.frame, (track(1),))
        second = self.renderer.render_tracks(self.frame, (track(2),))

        np.testing.assert_array_equal(first, repeated)
        self.assertFalse(np.array_equal(first[80, 20], second[80, 20]))

    def test_draws_trajectory_with_consecutive_points(self) -> None:
        item = track(1, BoundingBox(120.0, 20.0, 150.0, 60.0))
        points = (
            TrajectoryPoint(0, 20.0, 110.0),
            TrajectoryPoint(1, 60.0, 110.0),
        )
        annotated = self.renderer.render_tracks(self.frame, (item,), {1: points})
        self.assertGreater(np.count_nonzero(annotated[110, 40]), 0)

    def test_does_not_join_trajectory_across_gap(self) -> None:
        item = track(1, BoundingBox(120.0, 20.0, 150.0, 60.0))
        points = (
            TrajectoryPoint(0, 20.0, 110.0),
            TrajectoryPoint(2, 60.0, 110.0),
        )
        annotated = self.renderer.render_tracks(self.frame, (item,), {1: points})
        np.testing.assert_array_equal(annotated[110, 40], np.zeros(3, dtype=np.uint8))

    def test_label_near_top_right_edge_remains_inside_frame(self) -> None:
        edge_detection = detection(BoundingBox(165.0, 0.0, 179.0, 40.0))
        annotated = self.renderer.render_detections(self.frame, (edge_detection,))
        self.assertGreater(np.count_nonzero(annotated[1:35, :165]), 0)

    def test_rejects_invalid_frames(self) -> None:
        invalid_frames = (
            np.zeros((20, 20), dtype=np.uint8),
            np.zeros((20, 20, 3), dtype=np.float32),
            np.zeros((0, 20, 3), dtype=np.uint8),
        )
        for invalid in invalid_frames:
            with self.subTest(shape=invalid.shape, dtype=invalid.dtype):
                with self.assertRaises(ValueError):
                    self.renderer.render_detections(invalid, ())

    def test_zone_uses_arbitrary_polygon_and_light_fill_without_mutating_frame(self) -> None:
        zone = Zone("aisle", "Pasillo", ((0.1, 0.2), (0.9, 0.2), (0.5, 0.9)))
        original = self.frame.copy()
        annotated = self.renderer.render_zone(self.frame, zone)
        np.testing.assert_array_equal(self.frame, original)
        np.testing.assert_array_equal(annotated[135, 5], original[135, 5])
        self.assertGreater(int(annotated[80, 90, 0]), 0)
        self.assertLess(int(annotated[80, 90, 0]), 30)
        np.testing.assert_array_equal(
            annotated[28, 90], self.renderer._ZONE_NORMAL_COLOR,
        )

    def test_event_zone_is_amber_and_uses_metadata_in_compact_label(self) -> None:
        zone = Zone("aisle", "Área tránsito", ((0.1, 0.2), (0.9, 0.2), (0.5, 0.9)))
        with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as put_text:
            annotated = self.renderer.render_zone(
                self.frame, zone, event=True, rule_kind="zone_dwell", frame_index=60,
            )
        np.testing.assert_array_equal(
            annotated[28, 90], self.renderer._ZONE_EVENT_COLOR,
        )
        labels = [call.args[1] for call in put_text.call_args_list]
        self.assertEqual(labels, ["Area transito", "Regla: zone_dwell", "Frame 60"])

    def test_eight_vertex_zone_uses_exact_logical_geometry_and_jpeg_preview(self) -> None:
        zone = Zone(
            "floor", "Pasillo central",
            ((0.2, 0.2), (0.5, 0.2), (0.7, 0.4), (0.9, 0.8),
             (0.8, 0.95), (0.1, 0.95), (0.05, 0.7), (0.1, 0.4)),
        )
        original_alpha = self.renderer._ZONE_FILL_ALPHA
        with patch("operix_engine.visualization.cv2.fillPoly", wraps=cv2.fillPoly) as fill:
            annotated = self.renderer.render_zone(self.frame, zone)
        expected = np.asarray(
            [(round(x * 179), round(y * 139)) for x, y in zone.polygon],
            dtype=np.int32,
        )
        np.testing.assert_array_equal(fill.call_args.args[1][0], expected)
        self.assertTrue(point_in_zone(NormalizedPoint(0.5, 0.7), zone))
        self.assertFalse(point_in_zone(NormalizedPoint(0.02, 0.02), zone))
        self.assertEqual(self.renderer._ZONE_FILL_ALPHA, original_alpha)
        self.assertEqual(annotated.shape, self.frame.shape)
        self.assertTrue(cv2.imencode(".jpg", annotated)[0])

    def test_zone_rejects_invalid_render_metadata(self) -> None:
        zone = Zone("aisle", "Pasillo", ((0.1, 0.2), (0.9, 0.2), (0.5, 0.9)))
        with self.assertRaises(TypeError):
            self.renderer.render_zone(self.frame, object())
        with self.assertRaises(ValueError):
            self.renderer.render_zone(self.frame, zone, frame_index=-1)


class TrajectoryAccumulatorTest(unittest.TestCase):
    def test_uses_box_center_and_returns_only_active_tracks(self) -> None:
        accumulator = TrajectoryAccumulator()
        trajectories = accumulator.update(
            0,
            (track(7, BoundingBox(10.0, 20.0, 30.0, 60.0)),),
        )
        self.assertEqual(trajectories, {7: (TrajectoryPoint(0, 20.0, 40.0),)})
        self.assertEqual(accumulator.update(1, ()), {})

    def test_maximum_length_removes_old_points(self) -> None:
        config = VisualizationConfig(max_trajectory_points=3)
        accumulator = TrajectoryAccumulator(config)
        trajectories = {}
        for frame_index in range(4):
            trajectories = accumulator.update(
                frame_index,
                (track(1, BoundingBox(frame_index, 10.0, frame_index + 10.0, 30.0)),),
            )
        self.assertEqual(
            [point.frame_index for point in trajectories[1]],
            [1, 2, 3],
        )

    def test_recovery_within_retention_preserves_history_and_gap(self) -> None:
        accumulator = TrajectoryAccumulator(VisualizationConfig(inactive_retention_frames=2))
        accumulator.update(0, (track(),))
        accumulator.update(1, ())
        trajectories = accumulator.update(2, (track(),))
        self.assertEqual([point.frame_index for point in trajectories[1]], [0, 2])

    def test_inactivity_beyond_retention_removes_history(self) -> None:
        accumulator = TrajectoryAccumulator(VisualizationConfig(inactive_retention_frames=2))
        accumulator.update(0, (track(),))
        accumulator.update(1, ())
        accumulator.update(2, ())
        accumulator.update(3, ())
        trajectories = accumulator.update(4, (track(),))
        self.assertEqual([point.frame_index for point in trajectories[1]], [4])

    def test_reset_clears_state_and_frame_sequence(self) -> None:
        accumulator = TrajectoryAccumulator()
        accumulator.update(10, (track(),))
        accumulator.reset()
        trajectories = accumulator.update(0, (track(),))
        self.assertEqual([point.frame_index for point in trajectories[1]], [0])

    def test_rejects_non_increasing_frame_index(self) -> None:
        accumulator = TrajectoryAccumulator()
        accumulator.update(2, ())
        with self.assertRaisesRegex(ValueError, "estrictamente creciente"):
            accumulator.update(2, ())

    def test_configuration_rejects_invalid_limits(self) -> None:
        with self.assertRaisesRegex(ValueError, "positivos"):
            VisualizationConfig(max_trajectory_points=0)
        with self.assertRaisesRegex(ValueError, "positivo"):
            VisualizationConfig(font_scale=0)


if __name__ == "__main__":
    unittest.main()
