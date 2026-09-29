# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas de variables OP-37 con tracks sintéticos, sin inferencia real."""

from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import Zone, load_operational_config
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track
from operix_engine.zone_geometry import NormalizedPoint


EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "examples" / "op30-zone-rule.json"


def make_track(track_id: int, x: float, y: float) -> Track:
    """Construye una caja en 100×100 con centro inferior normalizado (x,y)."""
    center_x = x * 100
    bottom_y = y * 100
    return Track(track_id, 0, "person", 0.9, BoundingBox(
        center_x - 5, bottom_y - 10, center_x + 5, bottom_y,
    ))


class SpatiotemporalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.zone = load_operational_config(EXAMPLE).zones[0]
        self.analyzer = SpatiotemporalAnalyzer(width=100, height=100, fps=30, zones=(self.zone,))
        self.inside = make_track(1, 0.4, 0.5)
        self.outside = make_track(1, 0.8, 0.5)

    def test_timestamp_uses_video_fps_not_wall_clock(self) -> None:
        result = self.analyzer.update(3, (self.inside,))
        self.assertAlmostEqual(result.timestamp_s, 0.1)
        self.assertEqual(result.objects[0].frame_index, 3)
        self.assertAlmostEqual(result.objects[0].timestamp_s, 0.1)

    def test_position_and_zone_reuse_existing_geometry(self) -> None:
        obj = self.analyzer.update(0, (self.inside,)).objects[0]
        self.assertEqual(obj.position, NormalizedPoint(0.4, 0.5))
        membership = obj.zones[0]
        self.assertEqual((membership.track_id, membership.zone_id, membership.frame_index),
                         (1, "zona_critica_01", 0))
        self.assertTrue(membership.inside)
        self.assertEqual(membership.dwell_time_s, 0)

    def test_entry_and_consecutive_dwell_elapsed_seconds(self) -> None:
        durations = [self.analyzer.update(frame, (self.inside,)).objects[0].zones[0].dwell_time_s
                     for frame in (0, 1, 2)]
        self.assertEqual(durations, [0, 1 / 30, 2 / 30])

    def test_exit_and_reentry_start_new_interval(self) -> None:
        self.analyzer.update(0, (self.inside,))
        self.analyzer.update(1, (self.inside,))
        exit_state = self.analyzer.update(2, (self.outside,)).objects[0].zones[0]
        reentry = self.analyzer.update(3, (self.inside,)).objects[0].zones[0]
        self.assertFalse(exit_state.inside)
        self.assertEqual(exit_state.dwell_time_s, 0)
        self.assertTrue(reentry.inside)
        self.assertEqual(reentry.dwell_time_s, 0)

    def test_absent_track_breaks_dwell_and_trajectory(self) -> None:
        self.analyzer.update(0, (self.inside,))
        self.analyzer.update(1, (self.inside,))
        empty = self.analyzer.update(2, ())
        recovered = self.analyzer.update(3, (self.inside,)).objects[0]
        self.assertEqual(empty.objects, ())
        self.assertEqual(recovered.zones[0].dwell_time_s, 0)
        self.assertEqual(tuple(item.frame_index for item in recovered.trajectory), (3,))

    def test_skipped_frame_breaks_continuity_without_interpolation(self) -> None:
        self.analyzer.update(0, (self.inside,))
        recovered = self.analyzer.update(2, (self.inside,)).objects[0]
        self.assertEqual(recovered.zones[0].dwell_time_s, 0)
        self.assertEqual(tuple(item.frame_index for item in recovered.trajectory), (2,))

    def test_recent_trajectory_has_normalized_position_and_time(self) -> None:
        analyzer = SpatiotemporalAnalyzer(width=100, height=100, fps=10,
                                         zones=(self.zone,), max_trajectory_points=2)
        for frame, x in enumerate((0.4, 0.41, 0.42)):
            result = analyzer.update(frame, (make_track(1, x, 0.5),))
        samples = result.objects[0].trajectory
        self.assertEqual(tuple(item.frame_index for item in samples), (1, 2))
        self.assertEqual(tuple(item.timestamp_s for item in samples), (0.1, 0.2))
        self.assertAlmostEqual(samples[-1].position.x, 0.42)

    def test_pairwise_distance_is_normalized_and_order_independent(self) -> None:
        a, b = make_track(2, 0.3, 0.3), make_track(1, 0.7, 0.6)
        first = self.analyzer.update(0, (a, b)).proximities[0]
        self.analyzer.reset()
        second = self.analyzer.update(0, (b, a)).proximities[0]
        self.assertEqual((first.track_id_a, first.track_id_b), (1, 2))
        self.assertAlmostEqual(first.normalized_distance, 0.5)
        self.assertEqual(first.normalized_distance, second.normalized_distance)

    def test_coincident_tracks_have_zero_distance(self) -> None:
        proximity = self.analyzer.update(0, (self.inside, make_track(2, 0.4, 0.5))).proximities[0]
        self.assertEqual(proximity.normalized_distance, 0)

    def test_multiple_tracks_and_zones(self) -> None:
        second = Zone("other", "other", ((0.35, 0.35), (0.85, 0.35), (0.85, 0.85), (0.35, 0.85)))
        analyzer = SpatiotemporalAnalyzer(width=100, height=100, fps=30,
                                         zones=(self.zone, second))
        result = analyzer.update(0, (make_track(2, 0.8, 0.5), self.inside))
        self.assertEqual(tuple(obj.track_id for obj in result.objects), (1, 2))
        self.assertEqual(tuple(z.inside for z in result.objects[0].zones), (True, True))
        self.assertEqual(tuple(z.inside for z in result.objects[1].zones), (False, True))
        self.assertEqual(len(result.proximities), 1)

    def test_no_zones_still_produces_position_and_proximity(self) -> None:
        analyzer = SpatiotemporalAnalyzer(width=100, height=100, fps=30, zones=())
        result = analyzer.update(0, (self.inside, make_track(2, 0.5, 0.5)))
        self.assertEqual(result.objects[0].zones, ())
        self.assertEqual(len(result.proximities), 1)

    def test_invalid_fps_and_dimensions(self) -> None:
        for fps in (0, -1, math.inf, math.nan, True, "30"):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                SpatiotemporalAnalyzer(width=100, height=100, fps=fps, zones=())
        for width, height in ((0, 100), (100, 0), (True, 100)):
            with self.subTest(width=width, height=height), self.assertRaises(ValueError):
                SpatiotemporalAnalyzer(width=width, height=height, fps=30, zones=())

    def test_invalid_track_tuple_frame_index_and_duplicates(self) -> None:
        for frame in (-1, True, 1.0):
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                self.analyzer.update(frame, ())
        with self.assertRaises(TypeError):
            self.analyzer.update(0, [self.inside])  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "duplicado"):
            self.analyzer.update(0, (self.inside, self.inside))

    def test_nonmonotonic_frame_and_reset(self) -> None:
        self.analyzer.update(2, (self.inside,))
        with self.assertRaises(ValueError):
            self.analyzer.update(2, ())
        self.analyzer.reset()
        self.assertEqual(self.analyzer.update(0, (self.inside,)).objects[0].zones[0].dwell_time_s, 0)

    def test_invalid_box_does_not_advance_state(self) -> None:
        self.analyzer.update(0, (self.inside,))
        bad = Track(2, 0, "person", 0.9, BoundingBox(90, 20, 110, 40))
        with self.assertRaises(ValueError):
            self.analyzer.update(1, (self.inside, bad))
        result = self.analyzer.update(1, (self.inside,))
        self.assertEqual(result.objects[0].zones[0].dwell_time_s, 1 / 30)

    def test_result_objects_are_immutable(self) -> None:
        result = self.analyzer.update(0, (self.inside,))
        with self.assertRaises(FrozenInstanceError):
            result.objects[0].position = NormalizedPoint(0.3, 0.4)  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
