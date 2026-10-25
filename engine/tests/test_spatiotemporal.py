# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas de variables OP-37 con tracks sintéticos, sin inferencia real."""

from __future__ import annotations

import math
import json
import unittest
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import Zone, load_operational_config
from operix_engine.spatiotemporal import ObjectIdentity, SpatiotemporalAnalyzer
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

    def test_explicit_video_timestamps_drive_dwell_and_trajectory(self):
        self.analyzer.update(0, (self.inside,), timestamp_s=0.)
        result = self.analyzer.update(1, (self.inside,), timestamp_s=.071)
        obj = result.objects[0]
        self.assertEqual(result.timestamp_s, .071)
        self.assertEqual(obj.zones[0].dwell_time_s, .071)
        self.assertEqual(obj.trajectory[-1].timestamp_s, .071)

    def test_bad_timestamp_does_not_mutate_analyzer(self):
        self.analyzer.update(0, (self.inside,), timestamp_s=.1)
        for timestamp in (0, .1, -1, float("nan"), float("inf"), True):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.analyzer.update(1, (self.inside,), timestamp_s=timestamp)
        self.assertEqual(self.analyzer.update(1, (self.inside,), timestamp_s=.2).timestamp_s, .2)

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

    def test_identity_is_class_scoped_hashable_and_immutable(self) -> None:
        person, forklift = ObjectIdentity("person", 1), ObjectIdentity("forklift", 1)
        self.assertNotEqual(person, forklift)
        self.assertEqual(len({person, forklift, ObjectIdentity("person", 1)}), 2)
        with self.assertRaises(FrozenInstanceError):
            person.track_id = 2
        for name, track_id in (("", 1), (0, 1), ("person", 0), ("person", True)):
            with self.subTest(name=name, track_id=track_id), self.assertRaises(ValueError):
                ObjectIdentity(name, track_id)

    def test_same_numeric_id_coexists_with_original_box_and_confidence(self) -> None:
        forklift = replace(make_track(1, 0.8, 0.7), class_name="forklift", confidence=0.8)
        result = self.analyzer.update(0, (self.inside, forklift))
        objects = {obj.identity: obj for obj in result.objects}
        self.assertEqual(len(objects), 2)
        for track in (self.inside, forklift):
            obj = objects[ObjectIdentity(track.class_name, track.track_id)]
            self.assertEqual((obj.class_name, obj.track_id), (track.class_name, track.track_id))
            self.assertEqual((obj.bounding_box, obj.confidence), (track.bounding_box, track.confidence))

    def test_multiclass_histories_dwell_and_loss_are_independent(self) -> None:
        forklift = replace(make_track(1, 0.5, 0.5), class_name="forklift")
        for frame in (0, 1):
            self.analyzer.update(frame, (self.inside, forklift))
        only_forklift = self.analyzer.update(2, (forklift,)).objects[0]
        self.assertEqual(only_forklift.zones[0].dwell_time_s, 2 / 30)
        recovered = self.analyzer.update(3, (self.inside, forklift))
        objects = {obj.class_name: obj for obj in recovered.objects}
        self.assertEqual(objects["person"].zones[0].dwell_time_s, 0)
        self.assertEqual(objects["forklift"].zones[0].dwell_time_s, 3 / 30)
        self.assertEqual(tuple(s.frame_index for s in objects["person"].trajectory), (3,))
        self.assertEqual(tuple(s.frame_index for s in objects["forklift"].trajectory), (0, 1, 2, 3))
        self.assertEqual(objects["person"].trajectory[-1].position, NormalizedPoint(0.4, 0.5))
        self.assertEqual(objects["forklift"].trajectory[-1].position, NormalizedPoint(0.5, 0.5))

    def test_zone_memberships_keep_class_and_independent_inside_state(self) -> None:
        forklift = replace(self.outside, class_name="forklift")
        result = self.analyzer.update(0, (self.inside, forklift))
        memberships = {obj.zones[0].identity: obj.zones[0] for obj in result.objects}
        self.assertTrue(memberships[ObjectIdentity("person", 1)].inside)
        self.assertFalse(memberships[ObjectIdentity("forklift", 1)].inside)

    def test_cross_class_proximity_is_symmetric_and_class_scoped(self) -> None:
        person = make_track(1, 0.7, 0.6)
        forklift = replace(make_track(1, 0.3, 0.3), class_name="forklift")
        pair = self.analyzer.update(0, (person, forklift)).proximities[0]
        self.assertEqual({pair.identity_a, pair.identity_b},
                         {ObjectIdentity("person", 1), ObjectIdentity("forklift", 1)})
        self.assertAlmostEqual(pair.normalized_distance, math.hypot(.3, .3))
        self.analyzer.reset()
        self.assertEqual(pair, self.analyzer.update(0, (forklift, person)).proximities[0])

    def test_same_class_proximities_work_for_person_and_forklift(self) -> None:
        for name in ("person", "forklift"):
            with self.subTest(class_name=name):
                self.analyzer.reset()
                tracks = tuple(replace(make_track(i, x, 0.5), class_name=name)
                               for i, x in ((1, 0.4), (2, 0.8)))
                pair = self.analyzer.update(0, tracks).proximities[0]
                self.assertEqual((pair.identity_a, pair.identity_b),
                                 (ObjectIdentity(name, 1), ObjectIdentity(name, 2)))
                self.assertAlmostEqual(pair.normalized_distance, 0.4)

    def test_duplicate_identity_rejected_without_advancing_multiclass_state(self) -> None:
        forklift = replace(self.inside, class_name="forklift")
        self.analyzer.update(0, (self.inside, forklift))
        with self.assertRaisesRegex(ValueError, "duplicado"):
            self.analyzer.update(1, (self.inside, forklift, forklift))
        result = self.analyzer.update(1, (self.inside, forklift))
        self.assertTrue(all(obj.zones[0].dwell_time_s == 1 / 30 for obj in result.objects))

    def test_changing_local_class_id_does_not_change_semantic_identity(self) -> None:
        self.analyzer.update(0, (self.inside,))
        obj = self.analyzer.update(1, (replace(self.inside, class_id=99),)).objects[0]
        self.assertEqual(obj.identity, ObjectIdentity("person", 1))
        self.assertEqual(obj.zones[0].dwell_time_s, 1 / 30)

    def test_multiclass_gap_and_reset_clear_both_histories(self) -> None:
        tracks = (self.inside, replace(self.inside, class_name="forklift"))
        self.analyzer.update(0, tracks)
        result = self.analyzer.update(2, tracks)
        self.assertTrue(all(len(obj.trajectory) == 1 and obj.zones[0].dwell_time_s == 0
                            for obj in result.objects))
        self.analyzer.reset()
        self.assertEqual(len(self.analyzer.update(0, tracks).objects), 2)

    def test_multiclass_state_serializes_structured_identities(self) -> None:
        result = self.analyzer.update(0, (self.inside, replace(self.inside, class_name="forklift")))
        payload = json.loads(json.dumps(asdict(result), allow_nan=False))
        identities = [obj["identity"] for obj in payload["objects"]]
        self.assertIn({"class_name": "person", "track_id": 1}, identities)
        self.assertIn({"class_name": "forklift", "track_id": 1}, identities)
        pair = payload["proximities"][0]
        self.assertNotEqual(pair["identity_a"], pair["identity_b"])
        self.assertEqual(pair["track_id_a"], pair["track_id_b"])


if __name__ == "__main__":
    unittest.main()
