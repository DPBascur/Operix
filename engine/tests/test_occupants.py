import math
import unittest

from operix_engine.detection import BoundingBox
from operix_engine.motion import MotionConfig
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track


def truck(offset, identity=1):
    return Track(identity, 1, "forklift", .8, BoundingBox(100 + offset, 200, 220 + offset, 320))


def rider(offset, identity=1, partial=False):
    bottom = 248 if partial else 267
    return Track(identity, 0, "person", .8, BoundingBox(142 + offset, 221, 175 + offset, bottom))


class PossibleOccupantTest(unittest.TestCase):
    def setUp(self):
        zone = Zone("floor", "Floor", ((0, 0), (1, 0), (1, 1), (0, 1)))
        rules = (
            RuleConfig("pedestrians", 1, True, {
                "kind": "person_forklift_proximity", "zone_id": "floor", "max_distance": .8,
                "minimum_duration_seconds": 1., "exclude_possible_occupant": True,
            }),
            RuleConfig("coexistence", 1, True, {
                "kind": "zone_coexistence", "zone_id": "floor", "max_distance": math.sqrt(2),
                "minimum_duration_seconds": 1.,
            }),
        )
        motion = MotionConfig("normalized", .3, 4, .2, .01, .04, .015, True, .2)
        config = OperationalConfig(1, "test", (zone,), rules, motion=motion)
        self.analyzer = SpatiotemporalAnalyzer(width=1000, height=600, fps=10, zones=config.zones,
                                              motion=config.motion, observe_occupants=config.observe_occupants)
        self.engine = RuleEngine(config)

    def step(self, frame, tracks, **kwargs):
        spatial = self.analyzer.update(frame, tracks, **kwargs)
        return spatial, self.engine.evaluate(spatial)

    def test_only_own_vehicle_excluded_and_coexistence_unchanged(self):
        candidates = []
        for index in range(12):
            x = index * 7
            pedestrian = Track(2, 0, "person", .8, BoundingBox(280, 260, 300, 350))
            frame, result = self.step(index, (truck(x), rider(x), truck(x + 180, 2), pedestrian))
            candidates.extend(result.candidates)
        observed = {(item.rule_id, item.interaction.person.track_id, item.interaction.forklift.track_id): item
                    for item in result.evaluations}
        own_pair = observed["pedestrians", 1, 1]
        self.assertEqual(own_pair.reason, "possible_occupant")
        self.assertEqual(own_pair.occupant_association.state, "POSSIBLE_OCCUPANT")
        self.assertEqual(len(frame.objects), 4)
        emitted = {(item.rule_id, item.interaction.person.track_id, item.interaction.forklift.track_id)
                   for item in candidates}
        self.assertNotIn(("pedestrians", 1, 1), emitted)
        self.assertIn(("coexistence", 1, 1), emitted)
        self.assertIn(("pedestrians", 1, 2), emitted)
        self.assertIn(("pedestrians", 2, 1), emitted)

    def test_stationary_and_projected_overlap_without_co_motion_stay_evaluable(self):
        for scene in ("stopped", "crossing", "foreground", "behind", "camera_unverified"):
            with self.subTest(scene=scene):
                self.setUp()
                emitted = []
                for index in range(12):
                    x = 0 if scene == "stopped" else index * 7
                    person = rider(x - index * 2 if scene == "crossing" else x)
                    if scene in ("foreground", "behind"):
                        y = 275 if scene == "foreground" else 178
                        person = Track(1, 0, "person", .8, BoundingBox(151+x, y, 174+x, y+50))
                    frame, result = self.step(index, (truck(x), person), image_only=scene == "camera_unverified")
                    if scene == "camera_unverified":
                        self.assertFalse(frame.occupant_associations)
                    else:
                        evaluation = result.evaluations[0]
                        self.assertNotEqual(evaluation.reason, "possible_occupant")
                    emitted.extend(item.rule_id for item in result.candidates)
                if scene == "camera_unverified":
                    self.assertNotIn("pedestrians", emitted)
                else:
                    self.assertIn("pedestrians", emitted)

    def test_partial_rider_confirmed_only_until_occluded_and_ambiguity_fails_open(self):
        for index in range(11):
            frame, _ = self.step(index, (truck(index*7), rider(index*7, partial=True)))
        self.assertEqual(next(iter(frame.occupant_associations.values())).state, "POSSIBLE_OCCUPANT")
        frame, _ = self.step(11, (truck(77),))
        self.assertFalse(frame.occupant_associations)
        frame, _ = self.step(12, (truck(84), rider(84, partial=True)))
        self.assertEqual(next(iter(frame.occupant_associations.values())).state, "UNCERTAIN")
        frame, _ = self.step(13, (truck(91), truck(93, 2), rider(91, partial=True)))
        self.assertTrue(all(item.reason == "ambiguous_cabin_overlap"
                            for item in frame.occupant_associations.values()))

    def test_similar_overlaps_with_two_people_do_not_claim_operator(self):
        for index in range(12):
            x = index * 7
            frame, result = self.step(index, (truck(x), rider(x), rider(x + 5, identity=2)))
            self.assertEqual(len(frame.occupant_associations), 2)
            self.assertTrue(all(item.state == "UNCERTAIN" for item in frame.occupant_associations.values()))
            self.assertTrue(all(item.reason != "possible_occupant" for item in result.evaluations))
