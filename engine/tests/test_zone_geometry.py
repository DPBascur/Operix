"""Pruebas de pertenencia de OP-36 sin inferencia ni tracking."""

from __future__ import annotations

import math
import unittest
from pathlib import Path

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import Zone, load_operational_config
from operix_engine.zone_geometry import (
    NormalizedPoint,
    bbox_in_zone,
    normalized_bottom_center,
    point_in_zone,
)


EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "examples" / "op30-zone-rule.json"


class ZoneGeometryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_operational_config(EXAMPLE)
        self.zone = self.config.zones[0]

    def test_recovers_saved_op30_zone(self) -> None:
        self.assertEqual(self.config.view_id, "ceiling_04")
        self.assertEqual(self.zone.zone_id, "zona_critica_01")
        self.assertEqual(self.zone.polygon, ((0.2, 0.2), (0.55, 0.2), (0.55, 0.7), (0.2, 0.7)))

    def test_interior_and_exterior(self) -> None:
        self.assertTrue(point_in_zone(NormalizedPoint(0.4, 0.4), self.zone))
        self.assertFalse(point_in_zone(NormalizedPoint(0.8, 0.4), self.zone))
        self.assertFalse(point_in_zone(NormalizedPoint(0.4, 0.8), self.zone))

    def test_every_edge_and_vertex_count_as_inside(self) -> None:
        for point in ((0.3, 0.2), (0.55, 0.4), (0.3, 0.7), (0.2, 0.4), *self.zone.polygon):
            with self.subTest(point=point):
                self.assertTrue(point_in_zone(NormalizedPoint(*point), self.zone))

    def test_outside_very_close_to_edge(self) -> None:
        self.assertFalse(point_in_zone(NormalizedPoint(0.55 + 1e-8, 0.4), self.zone))

    def test_bottom_center_normalization_and_membership(self) -> None:
        box = BoundingBox(600, 300, 800, 600)
        self.assertEqual(normalized_bottom_center(box, 1920, 1080), NormalizedPoint(700 / 1920, 600 / 1080))
        self.assertTrue(bbox_in_zone(box, self.zone, 1920, 1080))

    def test_partial_overlap_does_not_override_anchor_outside(self) -> None:
        box = BoundingBox(900, 400, 1200, 800)
        self.assertFalse(bbox_in_zone(box, self.zone, 1920, 1080))

    def test_same_normalized_anchor_at_different_resolutions(self) -> None:
        cases = ((BoundingBox(300, 100, 500, 300), 1000, 500),
                 (BoundingBox(600, 200, 1000, 600), 2000, 1000))
        for box, width, height in cases:
            with self.subTest(width=width):
                self.assertEqual(normalized_bottom_center(box, width, height), NormalizedPoint(0.4, 0.6))
                self.assertTrue(bbox_in_zone(box, self.zone, width, height))

    def test_invalid_dimensions(self) -> None:
        box = BoundingBox(1, 1, 2, 2)
        for width, height in ((0, 10), (10, 0), (-1, 10), (10, -1), (True, 10)):
            with self.subTest(width=width, height=height):
                with self.assertRaises(ValueError):
                    normalized_bottom_center(box, width, height)

    def test_out_of_frame_box_is_rejected(self) -> None:
        for box in (BoundingBox(1, 1, 11, 2), BoundingBox(1, 1, 2, 11)):
            with self.assertRaisesRegex(ValueError, "excede"):
                normalized_bottom_center(box, 10, 10)

    def test_nonfinite_and_invalid_boxes_are_rejected_by_existing_type(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                BoundingBox(0, 0, value, 10)
        with self.assertRaises(ValueError):
            BoundingBox(2, 0, 1, 1)

    def test_invalid_normalized_point(self) -> None:
        for coordinates in ((math.nan, 0.5), (math.inf, 0.5), (-0.1, 0.5), (1.1, 0.5), (True, 0.5)):
            with self.subTest(coordinates=coordinates), self.assertRaises(ValueError):
                NormalizedPoint(*coordinates)

    def test_fewer_than_three_vertices_rejected_by_existing_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "tres vértices"):
            Zone("bad", "bad", ((0.1, 0.1), (0.2, 0.2)))

    def test_zero_area_polygon_is_rejected(self) -> None:
        zone = Zone("line", "line", ((0.1, 0.1), (0.2, 0.2), (0.3, 0.3)))
        with self.assertRaisesRegex(ValueError, "área nula"):
            point_in_zone(NormalizedPoint(0.2, 0.2), zone)

    def test_self_intersection_is_rejected(self) -> None:
        zone = Zone("bowtie", "bowtie", ((0.1, 0.1), (0.8, 0.8), (0.1, 0.8), (0.8, 0.1)))
        with self.assertRaisesRegex(ValueError, "autointersectado"):
            point_in_zone(NormalizedPoint(0.4, 0.4), zone)

    def test_repeated_endpoint_and_adjacent_overlap_are_rejected(self) -> None:
        repeated = Zone("repeat", "repeat", ((0.1, 0.1), (0.8, 0.1), (0.8, 0.8), (0.1, 0.1)))
        with self.assertRaises(ValueError):
            point_in_zone(NormalizedPoint(0.4, 0.4), repeated)
        overlap = Zone("overlap", "overlap", ((0.1, 0.1), (0.8, 0.1), (0.4, 0.1), (0.4, 0.8), (0.1, 0.8)))
        with self.assertRaises(ValueError):
            point_in_zone(NormalizedPoint(0.3, 0.3), overlap)

    def test_concave_polygon_and_orientation(self) -> None:
        vertices = ((0.1, 0.1), (0.9, 0.1), (0.9, 0.3), (0.3, 0.3), (0.3, 0.9), (0.1, 0.9))
        for polygon in (vertices, tuple(reversed(vertices))):
            with self.subTest(polygon=polygon):
                zone = Zone("concave", "concave", polygon)
                self.assertTrue(point_in_zone(NormalizedPoint(0.2, 0.8), zone))
                self.assertFalse(point_in_zone(NormalizedPoint(0.8, 0.8), zone))


if __name__ == "__main__":
    unittest.main()
