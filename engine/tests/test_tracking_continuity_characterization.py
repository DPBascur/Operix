"""Caracterización de episodios observados; no implementa gracia ni ReID."""
import unittest

from operix_engine.byte_tracker import ByteTracker
from operix_engine.detection import BoundingBox, Detection
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track


def characterize(cause, fps=30, gap_frames=1):
    """Fixture con condición sostenida a ambos lados de una interrupción conocida."""
    zone = Zone("fixture", "Fixture", ((0,0),(1,0),(1,1),(0,1)))
    config = OperationalConfig(1,"fixture",(zone,),(RuleConfig("TEST_DATA_PAIR",1,True,{
        "kind":"person_forklift_proximity", "zone_id":"fixture", "max_distance":.25,
        "minimum_duration_seconds":1.}),))
    analyzer = SpatiotemporalAnalyzer(width=1000,height=600,fps=fps,zones=(zone,))
    rules = RuleEngine(config)
    start = fps + 3
    recovery = start if cause == "TRACK_ID_CHANGE" else start + gap_frames
    frames, candidates = [], []
    for index in range(recovery + fps + 3):
        person = Track(2 if cause == "TRACK_ID_CHANGE" and index >= start else 1,
                       0,"person",.9,BoundingBox(400,250,430,400))
        forklift = Track(1,0,"forklift",.9,BoundingBox(450,200,650,400))
        objects = (person,forklift)
        if start <= index < start + gap_frames:
            if cause in {"TRACK_LOSS", "DETECTION_GAP", "OBJECT_DISAPPEARANCE"}:
                objects = (forklift,)
            elif cause == "FORKLIFT_LOSS":
                objects = (person,)
            elif cause == "RULE_EXIT":
                objects = (person,Track(1,0,"forklift",.9,BoundingBox(800,200,1000,400)))
        result = rules.evaluate(analyzer.update(index,objects))
        candidates.extend(result.candidates)
        frames.append({"frame":index,"timestamp_s":index/fps,
            "person_detection_present": not (start <= index < start+gap_frames and cause in {"DETECTION_GAP","OBJECT_DISAPPEARANCE"}),
            "forklift_detection_present": not (start <= index < start+gap_frames and cause == "FORKLIFT_LOSS"),
            "objects":tuple((obj.class_name,obj.track_id) for obj in objects),
            "reason":result.evaluations[0].reason if result.evaluations else "PAIR_UNOBSERVED",
            "duration_s":result.evaluations[0].observed_duration_s if result.evaluations else None,
            "candidate_count":len(result.candidates)})
    return frames, candidates, start, recovery


class TrackingContinuityCharacterizationTests(unittest.TestCase):
    def test_continuous_pair_emits_once_not_once_per_frame(self):
        for fps in (10,30,60):
            rows,events,_,_ = characterize("NO_GAP",fps)
            self.assertEqual([event.frame_index for event in events], [fps])

    def test_single_and_multiframe_losses_reset_even_when_same_id_returns(self):
        for fps in (10,30,60):
            for gap in (1,3):
                for cause in ("TRACK_LOSS","DETECTION_GAP","FORKLIFT_LOSS","OBJECT_DISAPPEARANCE"):
                    with self.subTest(fps=fps,gap=gap,cause=cause):
                        rows,events,start,recovery = characterize(cause,fps,gap)
                        self.assertEqual(len(events),2)
                        self.assertEqual([event.frame_index for event in events],[fps,recovery+fps])
                        self.assertEqual(rows[recovery]["duration_s"],0.)
                        self.assertTrue(all(row["reason"]=="PAIR_UNOBSERVED" for row in rows[start:recovery]))
                        self.assertEqual(events[0].interaction,events[1].interaction)
                        self.assertNotEqual(events[0].episode_key,events[1].episode_key)

    def test_known_rule_exit_rearms_a_legitimate_episode(self):
        rows,events,start,recovery = characterize("RULE_EXIT")
        self.assertEqual(rows[start]["reason"],"outside_distance")
        self.assertEqual(len(events),2)
        self.assertEqual(events[1].started_frame_index,recovery)

    def test_changed_id_is_not_merged_by_same_location(self):
        rows,events,start,recovery = characterize("TRACK_ID_CHANGE")
        self.assertEqual(len(events),2)
        self.assertEqual(events[0].interaction.person.track_id,1)
        self.assertEqual(events[1].interaction.person.track_id,2)
        self.assertEqual(events[1].started_frame_index,start)

    def test_missing_observations_do_not_reveal_the_physical_cause(self):
        # Una oclusión y una salida real pueden producir exactamente el mismo input.
        loss = characterize("DETECTION_GAP")[0]
        disappearance = characterize("OBJECT_DISAPPEARANCE")[0]
        self.assertEqual(loss,disappearance)

    def test_two_nearby_people_remain_independent_during_loss(self):
        zone = Zone("fixture","Fixture",((0,0),(1,0),(1,1),(0,1)))
        config = OperationalConfig(1,"fixture",(zone,),(RuleConfig("TEST_DATA_PAIR",1,True,{
            "kind":"person_forklift_proximity","zone_id":"fixture","max_distance":.25,
            "minimum_duration_seconds":1.}),))
        analyzer = SpatiotemporalAnalyzer(width=1000,height=600,fps=1,zones=(zone,))
        engine = RuleEngine(config)
        p1 = Track(1,0,"person",.9,BoundingBox(400,250,430,400))
        p2 = Track(2,0,"person",.9,BoundingBox(405,250,435,400))
        fork = Track(1,0,"forklift",.9,BoundingBox(450,200,650,400))
        emitted = []
        for frame,objects in enumerate(((p1,p2,fork),(p1,p2,fork),(p2,fork),(p1,p2,fork),(p1,p2,fork))):
            emitted.extend(engine.evaluate(analyzer.update(frame,objects)).candidates)
        self.assertEqual([(event.frame_index,event.interaction.person.track_id) for event in emitted],[(1,1),(1,2),(4,1)])

    def test_real_bytetrack_recovers_short_gaps_but_exposes_no_observed_track_in_gap(self):
        for gap in (1,3):
            tracker = ByteTracker()
            detection = Detection(0,"person",.9,BoundingBox(30,30,50,70))
            original = tracker.update((detection,))[0].track_id
            for _ in range(gap):
                self.assertEqual(tracker.update(()),())
            self.assertEqual(tracker.update((detection,))[0].track_id,original)

    def test_real_bytetrack_reconfirmation_after_expiry_does_not_resurrect_id(self):
        tracker = ByteTracker()
        detection = Detection(0,"person",.9,BoundingBox(30,30,50,70))
        original = tracker.update((detection,))[0].track_id
        for _ in range(35):
            self.assertEqual(tracker.update(()),())
        recovered = tracker.update((detection,))
        if not recovered:
            recovered = tracker.update((detection,))
        self.assertTrue(recovered)
        self.assertNotEqual(recovered[0].track_id,original)


if __name__ == "__main__":
    unittest.main()
