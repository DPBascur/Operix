import unittest
from dataclasses import replace

from operix_engine.motion import MotionConfig, MotionEstimator
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.rules import RuleEngine
from operix_engine.detection import BoundingBox
from operix_engine.tracking import Track
from test_calibration import calibration, skewed_calibration


def config(**kw):
    # Parámetros de un ensayo sintético; no umbrales operacionales promovidos.
    return MotionConfig(**(dict(unit="normalized", window_seconds=1., min_observations=3,
        max_gap_seconds=.6, stationary_speed=.01, moving_speed=.05,
        max_position_residual=.01, camera_fixed_confirmed=True) | kw))


def track(role, identity, x=.2):
    return Track(identity,0 if role=="person" else 1,role,.9,BoundingBox(x*100,30,(x+.04)*100,50))


class MotionTests(unittest.TestCase):
    def test_metric_motion_on_skewed_boundary_then_outside(self):
        cfg = config(unit="m", stationary_speed=.1, moving_speed=.5, max_position_residual=.1)
        estimator = MotionEstimator(cfg)
        snapshot = skewed_calibration()
        for frame in range(3):
            fraction = (frame + 1) / 4
            point = (.123 + .075 * fraction, .214 + .628 * fraction)
            measured = estimator.update(1, frame, frame * .5, point, calibration=snapshot)
        self.assertEqual(measured.state, "MOVING")
        self.assertAlmostEqual(measured.speed, 5 * (.075**2 + .628**2)**.5, places=6)
        outside = (.198 - 1e-9, .842)
        rejected = estimator.update(1, 3, 1.5, outside, calibration=snapshot)
        self.assertEqual(rejected.state, "UNKNOWN")
        self.assertEqual(rejected.reason, "outside_calibrated_area")

    def series(self, positions, cfg=None, **kw):
        estimator=MotionEstimator(cfg or config())
        return [estimator.update(("forklift",1),i,i*.5,(x,.5),**kw) for i,x in enumerate(positions)]

    def test_moving_stationary_and_insufficient_are_distinct(self):
        moving=self.series([.2,.25,.3])
        self.assertEqual([m.state for m in moving],["UNKNOWN","UNKNOWN","MOVING"])
        self.assertAlmostEqual(moving[-1].speed,.1)
        self.assertEqual(moving[-1].unit,"normalized_image_per_s")
        self.assertEqual(self.series([.2,.2,.2])[-1].state,"STATIONARY")
        self.assertEqual(self.series([.2,.2,.2],config(stationary_speed=0,moving_speed=1e-15))[-1].state,"STATIONARY")
        self.assertEqual(self.series([.2,.21,.22])[-1].state,"UNKNOWN")

    def test_jitter_and_large_residual_never_imply_confirmed_movement(self):
        self.assertEqual(self.series([.2,.201,.2])[-1].state,"STATIONARY")
        noisy=self.series([.2,.28,.2])[-1]
        self.assertEqual(noisy.state,"UNKNOWN")
        self.assertEqual(noisy.reason,"noisy_observation")
        self.assertIsNone(noisy.speed)

    def test_metres_require_valid_fixed_calibration_and_referenced_area(self):
        cfg=config(unit="m",stationary_speed=.1,moving_speed=.5,max_position_residual=.1)
        measured=self.series([.2,.25,.3],cfg,calibration=calibration())[-1]
        self.assertEqual(measured.state,"MOVING")
        self.assertAlmostEqual(measured.speed,1.)
        self.assertEqual(measured.unit,"m_per_s")
        self.assertEqual(measured.calibration_sha256,calibration()["sha256"])
        self.assertEqual(self.series([.2,.25,.3],cfg)[-1].state,"UNKNOWN")
        self.assertEqual(self.series([.2,.25,.3],config(camera_fixed_confirmed=False))[-1].state,"UNKNOWN")
        self.assertEqual(self.series([.2,.25,.3],cfg,calibration={**calibration(),"status":"invalid"})[-1].state,"UNKNOWN")

    def test_absence_time_gap_and_calibration_revision_reset_window(self):
        estimator=MotionEstimator(config())
        for i in range(3):observation=estimator.update(1,i,i*.5,(.2+i*.05,.5))
        self.assertEqual(observation.state,"MOVING")
        estimator.retain(set())
        self.assertEqual(estimator.update(1,3,1.5,(.35,.5)).state,"UNKNOWN")
        self.assertEqual(estimator.update(1,4,3.,(.4,.5)).sample_count,1)
        estimator=MotionEstimator(config(unit="m",moving_speed=.5,stationary_speed=.1,max_position_residual=.1))
        for i in range(3):estimator.update(1,i,i*.5,(.2+i*.05,.5),calibration=calibration())
        self.assertEqual(estimator.update(1,3,1.5,(.35,.5),calibration={**calibration(),"sha256":"b"*64}).state,"UNKNOWN")

    def test_configuration_rejects_ambiguous_thresholds_and_bad_windows(self):
        for kw in ({"moving_speed":.01},{"max_gap_seconds":2},{"min_observations":2},
                   {"window_seconds":float("nan")},{"unit":"km/h"},{"camera_fixed_confirmed":1}):
            with self.assertRaises(ValueError):config(**kw)

    def test_pair_rules_read_motion_without_recalculating_and_keep_any_mode(self):
        zone=Zone("z","Zone",((0,0),(1,0),(1,1),(0,1)))
        params=dict(kind="person_forklift_proximity",zone_id="z",person_class="person",
                    forklift_class="forklift",max_distance=1.,minimum_duration_seconds=.5)
        rules=(RuleConfig("moving",1,True,{**params,"motion_condition":"moving"}),
               RuleConfig("any",1,True,params))
        analyzer=SpatiotemporalAnalyzer(width=100,height=100,fps=2,zones=(zone,),motion=config())
        engine=RuleEngine(OperationalConfig(1,"camera",(zone,),rules,motion=config()))
        emitted=[]
        for i in range(4):
            state=analyzer.update(i,(track("person",1,.1),track("forklift",1,.3+i*.05)))
            result=engine.evaluate(state)
            emitted += [(candidate.rule_id,candidate.frame_index) for candidate in result.candidates]
        self.assertEqual(emitted,[("any",1),("moving",3)])
        candidate=next(c for c in result.candidates if c.rule_id=="moving")
        self.assertEqual(candidate.equipment_motion["state"],"MOVING")
        self.assertEqual(candidate.equipment_motion["epoch"],state.epoch)
        self.assertEqual(candidate.interaction.person.track_id,candidate.interaction.forklift.track_id)

    def test_new_epoch_reuses_ids_but_not_motion_or_episode_state(self):
        zone=Zone("z","Zone",((0,0),(1,0),(1,1),(0,1)))
        rule=RuleConfig("r",1,True,dict(kind="person_forklift_proximity",zone_id="z",
            person_class="person",forklift_class="forklift",max_distance=1.,minimum_duration_seconds=.5))
        analyzer=SpatiotemporalAnalyzer(width=100,height=100,fps=2,zones=(zone,),motion=config())
        engine=RuleEngine(OperationalConfig(1,"camera",(zone,),(rule,),motion=config()))
        for i in range(3):previous=analyzer.update(i,(track("person",1),track("forklift",1,.4)))
        engine.evaluate(previous)
        analyzer.reset(epoch=7)
        first=analyzer.update(0,(track("person",1),track("forklift",1,.4)))
        self.assertEqual(first.epoch,7)
        self.assertEqual(first.objects[0].motion.state,"UNKNOWN")
        self.assertFalse(engine.evaluate(first).candidates)
        with self.assertRaises(ValueError):engine.evaluate(replace(first,epoch=0))

class MultipleRelationsTests(unittest.TestCase):
    def setup_pair(self, persons, forklifts):
        zone=Zone("z","Controlled",((0,0),(1,0),(1,1),(0,1)))
        rule=RuleConfig("pairs",1,True,dict(kind="person_forklift_proximity",zone_id="z",max_distance=1.4,minimum_duration_seconds=.5))
        analyzer=SpatiotemporalAnalyzer(width=100,height=100,fps=2,zones=(zone,),motion=config())
        engine=RuleEngine(OperationalConfig(1,"controlled",(zone,),(rule,),motion=config()))
        objects=tuple(track("person",i+1,.1+i*.05) for i in range(persons))+tuple(track("forklift",i+1,.5+i*.05) for i in range(forklifts))
        return analyzer,engine,objects

    def test_cartesian_pairs_emit_independently_once(self):
        for people,equipment in ((1,2),(3,1),(2,2)):
            with self.subTest(people=people,equipment=equipment):
                analyzer,engine,objects=self.setup_pair(people,equipment)
                engine.evaluate(analyzer.update(0,objects))
                emitted=engine.evaluate(analyzer.update(1,objects))
                self.assertEqual(len(emitted.candidates),people*equipment)
                self.assertEqual(len({c.interaction for c in emitted.candidates}),people*equipment)
                self.assertFalse(engine.evaluate(analyzer.update(2,objects)).candidates)
                self.assertTrue(all(c.equipment_motion["state"]=="UNKNOWN" for c in emitted.candidates))

    def test_loss_of_one_partner_does_not_rearm_others(self):
        analyzer,engine,objects=self.setup_pair(2,2)
        engine.evaluate(analyzer.update(0,objects))
        self.assertEqual(len(engine.evaluate(analyzer.update(1,objects)).candidates),4)
        engine.evaluate(analyzer.update(2,objects[:-1]))
        self.assertFalse(engine.evaluate(analyzer.update(3,objects)).candidates)
        emitted=engine.evaluate(analyzer.update(4,objects))
        self.assertEqual(len(emitted.candidates),2)
        self.assertTrue(all(c.interaction.forklift.track_id==2 for c in emitted.candidates))

    def test_visual_limit_never_filters_calculations_or_events(self):
        import numpy as np
        from unittest.mock import patch
        from operix_engine.visualization import OpenCvRenderer,VisualizationConfig
        from operix_engine.operational_config import RelationDisplayConfig
        analyzer,engine,objects=self.setup_pair(2,2)
        engine.evaluate(analyzer.update(0,objects))
        spatial=analyzer.update(1,objects)
        result=engine.evaluate(spatial)
        renderer=OpenCvRenderer(VisualizationConfig(relations=RelationDisplayConfig(1,"all",.2)))
        with patch("operix_engine.visualization.cv2.line") as lines:
            renderer.render_proximity(np.zeros((100,100,3),dtype=np.uint8),spatial,result)
        self.assertEqual(lines.call_count,1)
        self.assertEqual(len(result.candidates),4)
        doubled=replace(result,evaluations=result.evaluations+tuple(replace(e,rule_id="other") for e in result.evaluations))
        with patch.object(renderer,"_draw_label") as labels:
            renderer.render_proximity(np.zeros((100,100,3),dtype=np.uint8),spatial,doubled)
        self.assertTrue(any(c.args[1]=="Relaciones visibles: 1/4" for c in labels.call_args_list))
        with self.assertRaises(ValueError):renderer.render_proximity(np.zeros((100,100,3),dtype=np.uint8),replace(spatial,epoch=1),result)

    def test_stationary_and_unknown_never_emit_moving_only(self):
        analyzer,engine,objects=self.setup_pair(1,1)
        zone=analyzer.zones
        rule=RuleConfig("moving",1,True,dict(kind="person_forklift_proximity",zone_id="z",max_distance=1.4,minimum_duration_seconds=.5,motion_condition="moving"))
        engine=RuleEngine(OperationalConfig(1,"controlled",tuple(zone),(rule,),motion=config()))
        for i in range(5):self.assertFalse(engine.evaluate(analyzer.update(i,objects)).candidates)

    def test_metric_point_outside_calibration_is_unknown(self):
        cal=calibration()
        cal={**cal,"image_points":[[.3,.3],[.7,.3],[.7,.7],[.3,.7]]}
        last=MotionTests().series([.1,.12,.15],config(unit="m"),calibration=cal)[-1]
        self.assertEqual(last.state,"UNKNOWN")
        self.assertEqual(last.reason,"outside_calibrated_area")

    def test_crossing_changes_geometry_without_restarting_identity_or_duplicating_event(self):
        analyzer,engine,objects=self.setup_pair(1,1)
        engine.evaluate(analyzer.update(0,objects))
        emitted=engine.evaluate(analyzer.update(1,objects))
        crossed=(track("person",1,.5),track("forklift",1,.1))
        result=engine.evaluate(analyzer.update(2,crossed))
        self.assertEqual(result.evaluations[0].interaction,emitted.candidates[0].interaction)
        self.assertFalse(result.candidates)
        self.assertEqual(result.evaluations[0].started_frame_index,0)

    def test_any_mode_can_emit_for_stationary_equipment_but_unconfirmed_cannot_emit_moving(self):
        zone=Zone("z","Controlled",((0,0),(1,0),(1,1),(0,1)))
        params=dict(kind="person_forklift_proximity",zone_id="z",max_distance=1.,minimum_duration_seconds=2.)
        for confirmed in (True,False):
            cfg=config(camera_fixed_confirmed=confirmed)
            analyzer=SpatiotemporalAnalyzer(width=100,height=100,fps=2,zones=(zone,),motion=cfg)
            engine=RuleEngine(OperationalConfig(1,"controlled",(zone,),(
                RuleConfig("any",1,True,params),RuleConfig("moving",1,True,{**params,"motion_condition":"moving"})),motion=cfg))
            emitted=[]
            for i in range(6):emitted.extend(engine.evaluate(analyzer.update(i,(track("person",1,.1),track("forklift",1,.5)))).candidates)
            self.assertEqual([c.rule_id for c in emitted],["any"])
            self.assertEqual(emitted[0].equipment_motion["state"],"STATIONARY" if confirmed else "UNKNOWN")
