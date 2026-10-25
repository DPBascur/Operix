"""Comparación geométrica de desarrollo; ningún modelo ni threshold se ajusta."""
import math
import unittest

from operix_engine.detection import BoundingBox
from operix_engine.proximity_geometry import PROXIMITY_GEOMETRY_VERSION, nearest_ground_edges
from operix_engine.zone_geometry import NormalizedPoint


class GroundEdgeGeometryTests(unittest.TestCase):
    def measure(self, person, equipment=(300, 250, 800, 450)):
        return nearest_ground_edges(BoundingBox(*person), BoundingBox(*equipment), 1000, 600)

    def test_horizontal_overlap_preserves_vertical_separation(self):
        observed = self.measure((530, 460, 570, 560))
        self.assertEqual(observed.person_anchor, NormalizedPoint(.55, 560/600))
        self.assertEqual(observed.equipment_target, NormalizedPoint(.55, .75))
        self.assertAlmostEqual(observed.normalized_distance, 110/600)

    def test_left_and_right_nearest_corners(self):
        left = self.measure((100, 200, 140, 450))
        right = self.measure((860, 200, 900, 450))
        self.assertEqual(left.equipment_target, NormalizedPoint(.3, .75))
        self.assertEqual(right.equipment_target, NormalizedPoint(.8, .75))
        self.assertEqual(left.person_anchor, NormalizedPoint(.14, .75))
        self.assertEqual(right.person_anchor, NormalizedPoint(.86, .75))
        self.assertAlmostEqual(left.normalized_distance, .16)
        self.assertAlmostEqual(right.normalized_distance, .06)

    def test_partial_overlap_uses_midpoint_of_intersection_deterministically(self):
        observed = self.measure((270,380,330,500))
        self.assertEqual(observed.person_anchor, NormalizedPoint(.315, 500/600))
        self.assertEqual(observed.equipment_target, NormalizedPoint(.315, .75))
        self.assertEqual(observed, self.measure((270,380,330,500)))

    def test_touching_bottom_segments_have_zero_distance(self):
        observed = self.measure((260,300,300,450))
        self.assertEqual(observed.person_anchor, observed.equipment_target)
        self.assertEqual(observed.normalized_distance, 0.)

    def test_reversing_boxes_keeps_segment_distance(self):
        person, equipment = BoundingBox(100,200,140,450), BoundingBox(300,250,800,450)
        direct = nearest_ground_edges(person,equipment,1000,600)
        reverse = nearest_ground_edges(equipment,person,1000,600)
        self.assertEqual(direct.normalized_distance, reverse.normalized_distance)
        self.assertEqual(direct.person_anchor, reverse.equipment_target)

    def test_development_fixtures(self):
        cases = (("partial_front", (270,380,330,500), 50/600),
                 ("perspective_overlap", (350,100,400,330), .2),
                 ("contained", (500,280,550,400), 50/600),
                 ("vertical", (530,30,570,150), .5),
                 ("same_bottom", (420,300,460,450), 0.),
                 ("multiple_left", (170,300,210,450), .09),
                 ("multiple_center", (480,300,520,450), 0.),
                 ("multiple_right", (870,300,910,450), .07))
        for name, box, expected in cases:
            with self.subTest(name=name):
                self.assertAlmostEqual(self.measure(box).normalized_distance, expected)

    def test_very_different_sizes_and_image_edge(self):
        self.assertAlmostEqual(self.measure((250,390,270,430), (280,100,980,450)).normalized_distance,
                               math.hypot(.01, 20/600))
        self.assertEqual(self.measure((0,280,20,420), (20,200,400,420)).normalized_distance, 0.)

    def test_normalization_invariant_under_frame_resize(self):
        original = self.measure((100,200,140,450))
        resized = nearest_ground_edges(BoundingBox(200,400,280,900),
                    BoundingBox(600,500,1600,900),2000,1200)
        self.assertEqual(original, resized)

    def test_width_change_inside_footprint_does_not_invent_horizontal_separation(self):
        person = (530,460,570,560)
        self.assertEqual(self.measure(person), self.measure(person,(100,250,900,450)))

    def test_invalid_boxes_or_frame_rejected(self):
        for width, height in ((0,600),(1000,0)):
            with self.assertRaises(ValueError):
                nearest_ground_edges(BoundingBox(1,1,2,2),BoundingBox(1,1,3,3),width,height)
        with self.assertRaises(ValueError):
            self.measure((990,200,1010,450))

    def test_contract_is_explicit_not_a_configurable_geometry_switch(self):
        self.assertEqual(PROXIMITY_GEOMETRY_VERSION, "person_equipment_nearest_ground_edges_v1")


if __name__ == "__main__":
    unittest.main()
