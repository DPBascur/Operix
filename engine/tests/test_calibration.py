import unittest
from dataclasses import replace

from operix_engine.calibration import calibration_snapshot, ground_measurement
from operix_engine.detection import BoundingBox
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.rules import RuleEngine
from operix_engine.tracking import Track


def calibration():
    return calibration_snapshot({"image_points":[[0,0],[1,0],[1,1],[0,1]],
        "ground_points_m":[[0,0],[10,0],[10,10],[0,10]], "source_sha256":"a"*64,
        "version":1,"status":"valid","units":"m","calibrated_at":"2026-11-09T00:00:00Z","zones_reviewed":True})


def skewed_calibration():
    image = [[.123, .214], [.811, .237], [.902, .879], [.198, .842]]
    return calibration_snapshot({
        **calibration(),
        "image_points": image,
        "ground_points_m": [[10 * x, 10 * y] for x, y in image],
    })


class CalibrationTests(unittest.TestCase):
    def test_metric_contact_on_skewed_boundary_and_just_outside(self):
        snapshot = skewed_calibration()
        equipment = BoundingBox(400, 300, 450, 371)
        contact_on_edge = BoundingBox(141.75, 300, 190, 371)
        measured = ground_measurement(snapshot, contact_on_edge, equipment, 1000, 1000)
        self.assertIsNotNone(measured)
        self.assertAlmostEqual(measured["distance"], 2.1, places=6)
        outside = BoundingBox(141.75 - 1e-6, 300, 190, 371)
        self.assertIsNone(ground_measurement(snapshot, outside, equipment, 1000, 1000))

    def test_parallel_rules_share_one_metric_label_and_keep_threshold_units(self):
        import cv2
        import numpy as np
        from unittest.mock import patch
        from operix_engine.visualization import OpenCvRenderer
        zone = Zone("z","Zone",((0,0),(1,0),(1,1),(0,1)))
        common = {"kind":"person_forklift_proximity","zone_id":"z","person_class":"person",
                  "forklift_class":"forklift","minimum_duration_seconds":0}
        rules = tuple(RuleConfig(name,1,True,{**common,"distance_unit":unit,"max_distance":maximum})
                      for name,unit,maximum in (("metric","m",3.1),("normal","normalized",.31)))
        engine = RuleEngine(OperationalConfig(1,"camera",(zone,),rules,calibration()))
        analyzer = SpatiotemporalAnalyzer(width=100,height=100,fps=10,zones=(zone,),calibration=calibration())
        state = analyzer.update(0,(Track(1,0,"person",.9,BoundingBox(0,10,10,20)),
                                  Track(1,1,"forklift",.9,BoundingBox(40,10,50,20))))
        renderer = OpenCvRenderer()
        with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as label, \
                patch("operix_engine.visualization.cv2.line", wraps=cv2.line) as line:
            renderer.render_proximity(np.zeros((100,100,3),dtype=np.uint8),state,engine.evaluate(state))
        labels = [call.args[1] for call in label.call_args_list]
        self.assertEqual(labels.count("P#1/F#1  ~3,00 m"), 1)
        self.assertTrue(any("max 3.1 m | metric" in text for text in labels))
        self.assertTrue(any("max 0.31 norm. | normal" in text for text in labels))
        self.assertEqual(line.call_args.args[1:3], ((10, 20), (40, 20)))
        line.assert_called_once()

    def test_metric_outside_calibration_draws_explicit_normalized_fallback(self):
        import cv2
        import numpy as np
        from unittest.mock import patch
        from operix_engine.visualization import OpenCvRenderer
        c = calibration_snapshot({**calibration(),"image_points":[[.2,.2],[.8,.2],[.8,.8],[.2,.8]]})
        zone = Zone("z","Zone",((0,0),(1,0),(1,1),(0,1)))
        rule = RuleConfig("metric",1,True,{"kind":"person_forklift_proximity","zone_id":"z",
            "person_class":"person","forklift_class":"forklift","max_distance":3.1,
            "minimum_duration_seconds":0,"distance_unit":"m"})
        analyzer = SpatiotemporalAnalyzer(width=100,height=100,fps=10,zones=(zone,),calibration=c)
        state = analyzer.update(0,(Track(1,0,"person",.9,BoundingBox(0,10,10,20)),
                                  Track(1,1,"forklift",.9,BoundingBox(40,10,50,20))))
        result = RuleEngine(OperationalConfig(1,"camera",(zone,),(rule,),c)).evaluate(state)
        self.assertFalse(result.candidates)
        self.assertEqual(result.evaluations[0].reason,"calibration_unavailable")
        renderer = OpenCvRenderer()
        with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as label, \
                patch("operix_engine.visualization.cv2.line", wraps=cv2.line) as line:
            renderer.render_proximity(np.zeros((100,100,3),dtype=np.uint8),state,result,metric_expected=True)
        line.assert_called_once()
        self.assertEqual(line.call_args.args[1:3], ((10, 20), (40, 20)))
        labels = [call.args[1] for call in label.call_args_list]
        self.assertIn("P#1/F#1  0,3 norm.", labels)
        self.assertTrue(any("Plano no aplicable" in text for text in labels))
        self.assertTrue(any("Umbral metrico suspendido" in text for text in labels))

    def test_centimeters_and_meters_across_profiles_with_the_same_geometry(self):
        import cv2
        import numpy as np
        from unittest.mock import patch
        from operix_engine.visualization import OpenCvRenderer

        zone = Zone("z", "Zone", ((0,0),(1,0),(1,1),(0,1)))
        snapshot = calibration()
        configs = (("m", .68), ("normalized", .15))
        rules = [RuleConfig(unit, i, True, {"kind": "person_forklift_proximity", "zone_id": "z",
                            "distance_unit": unit, "max_distance": threshold, "minimum_duration_seconds": 0})
                 for i, (unit, threshold) in enumerate(configs, 1)]
        renderer = OpenCvRenderer()
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        for physical, badge in ((.679, "~68 cm"), (.681, "~68 cm"), (1.42, "~1,42 m")):
            person = Track(1, 0, "person", .9, BoundingBox(200, 120, 240, 200))
            gap = 640 * physical / 10
            equipment = Track(1, 1, "forklift", .9, BoundingBox(240 + gap, 120, 340 + gap, 200))
            spatial = SpatiotemporalAnalyzer(width=640, height=360, fps=10, zones=(zone,), calibration=snapshot)
            state = spatial.update(0, (person, equipment))
            measured = state.proximities[0].ground["distance"]
            self.assertAlmostEqual(measured, physical, places=6)
            for active, emits in (((), False), ((rules[0],), physical <= .68), ((rules[1],), True)):
                with self.subTest(physical=physical, rules=active):
                    result = RuleEngine(OperationalConfig(1, "camera", (zone,), active, snapshot)).evaluate(state)
                    self.assertEqual(bool(result.candidates), emits)
                    with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as text:
                        renderer.render_proximity(frame, state, result)
                    self.assertIn(f"P#1/F#1  {badge}", [call.args[1] for call in text.call_args_list])

    def test_each_visible_pair_uses_its_own_calibrated_area_eligibility(self):
        import cv2
        import numpy as np
        from unittest.mock import patch
        from operix_engine.visualization import OpenCvRenderer

        snapshot = calibration_snapshot({**calibration(), "image_points": [[.2, .2], [.8, .2], [.8, .8], [.2, .8]]})
        tracks = (
            Track(1, 0, "person", .9, BoundingBox(200, 100, 240, 180)),
            Track(2, 0, "person", .9, BoundingBox(100, 100, 140, 180)),
            Track(1, 0, "forklift", .9, BoundingBox(300, 100, 350, 180)),
        )
        analyzer = SpatiotemporalAnalyzer(width=640, height=360, fps=10, zones=(), calibration=snapshot)
        state = analyzer.update(0, tracks)
        result = RuleEngine(OperationalConfig(1, "camera", (), (), snapshot)).evaluate(state)
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        with patch("operix_engine.visualization.cv2.putText", wraps=cv2.putText) as text:
            OpenCvRenderer().render_proximity(frame, state, result, metric_expected=True)
        labels = [call.args[1] for call in text.call_args_list]
        self.assertIn("P#1/F#1  ~1,56 m", labels)
        self.assertIn("P#2/F#1  0,25 norm.", labels)

    def test_projective_plane_known_distances_in_three_image_regions(self):
        # Plano virtual conocido, no GT físico de una cámara industrial.
        refs = [[.1,.1],[.9,.1],[.9,.9],[.1,.9]]
        ground = [[(14*x-1)/(1+.8*y), (12*y-1)/(1+.8*y)] for x,y in refs]
        snapshot = calibration_snapshot({**calibration(), "image_points":refs, "ground_points_m":ground})
        for y in (.2,.5,.8):
            for x in (.15,.35,.55):
                person = BoundingBox(x*1920,(y-.08)*1080,(x+.04)*1920,y*1080)
                equipment = BoundingBox((x+.16)*1920,(y-.08)*1080,(x+.20)*1920,y*1080)
                expected = 14*.12/(1+.8*y)
                measured = ground_measurement(snapshot,person,equipment,1920,1080)
                self.assertAlmostEqual(measured["distance"],expected,places=6)

    def test_no_extrapolation_and_no_disabled_zone_membership(self):
        c = calibration_snapshot({**calibration(), "image_points":[[.2,.2],[.8,.2],[.8,.8],[.2,.8]]})
        self.assertIsNone(ground_measurement(c,BoundingBox(0,0,10,10),BoundingBox(40,30,50,40),100,100))
        with self.assertRaises(ValueError):
            calibration_snapshot({**c,"source_sha256":"x"*64})
        zone=Zone("z","Zone",((0,0),(1,0),(1,1),(0,1)),enabled=False)
        analyzer=SpatiotemporalAnalyzer(width=100,height=100,fps=10,zones=(zone,))
        state=analyzer.update(0,(Track(1,0,"person",.9,BoundingBox(10,10,20,20)),))
        self.assertEqual(state.objects[0].zones,())

    def test_coexistence_requires_both_roles_and_resets(self):
        zone=Zone("z","Zone",((0,0),(1,0),(1,1),(0,1)))
        rule=RuleConfig("r",1,True,{"kind":"zone_coexistence","zone_id":"z","person_class":"person",
            "forklift_class":"forklift","max_distance":2**.5,"minimum_duration_seconds":.1})
        engine=RuleEngine(OperationalConfig(1,"camera",(zone,),(rule,)))
        analyzer=SpatiotemporalAnalyzer(width=100,height=100,fps=10,zones=(zone,))
        tracks=(Track(1,0,"person",.9,BoundingBox(10,10,20,20)),Track(1,1,"forklift",.9,BoundingBox(60,10,70,20)))
        self.assertFalse(engine.evaluate(analyzer.update(0,tracks)).candidates)
        result=engine.evaluate(analyzer.update(1,tracks))
        self.assertEqual(len(result.candidates),1)
        self.assertEqual(result.candidates[0].candidate_type,"zone_coexistence")
        self.assertFalse(engine.evaluate(analyzer.update(2,tracks)).candidates)
        self.assertFalse(engine.evaluate(analyzer.update(3,tracks[:1])).candidates)
        self.assertFalse(engine.evaluate(analyzer.update(4,tracks)).candidates)
        self.assertEqual(len(engine.evaluate(analyzer.update(5,tracks)).candidates),1)

    def test_known_distance_and_reproducible_snapshot(self):
        snapshot = calibration()
        self.assertEqual(snapshot, calibration_snapshot(snapshot))
        m = ground_measurement(snapshot, BoundingBox(0,10,10,20), BoundingBox(40,10,50,20), 100,100)
        self.assertAlmostEqual(m["distance"],3, places=7)
        self.assertAlmostEqual(m["person_anchor"][0],.1)

    def test_invalid_and_unreferenced_ground_never_returns_metres(self):
        c = calibration()
        bad = {**c,"image_points":[[0,0],[.1,.1],[.2,.2],[.3,.3]]}
        with self.assertRaises(ValueError): calibration_snapshot(bad)
        with self.assertRaises(ValueError): calibration_snapshot({**c,"ground_points_m":[[0,0]]*4})
        self.assertIsNone(ground_measurement({**c,"status":"invalid"},BoundingBox(0,0,10,10),BoundingBox(20,0,30,10),100,100))

    def test_metric_rules_require_calibration(self):
        zone=Zone("z","Zone",((0,0),(1,0),(1,1),(0,1)))
        rule=RuleConfig("r",1,True,{"kind":"person_forklift_proximity","zone_id":"z","person_class":"person",
            "forklift_class":"forklift","max_distance":3.1,"minimum_duration_seconds":0,"distance_unit":"m"})
        config=OperationalConfig(1,"camera",(zone,),(rule,))
        with self.assertRaises(ValueError): RuleEngine(config)
        engine=RuleEngine(replace(config,calibration=calibration()))
        analyzer=SpatiotemporalAnalyzer(width=100,height=100,fps=10,zones=(zone,),calibration=calibration())
        tracks=(Track(1,0,"person",.9,BoundingBox(0,10,10,20)),Track(1,1,"forklift",.9,BoundingBox(40,10,50,20)))
        state=analyzer.update(0,tracks)
        result=engine.evaluate(state)
        self.assertEqual(len(result.candidates),1)
        self.assertAlmostEqual(result.candidates[0].ground["distance"],3)
        import cv2
        import numpy as np
        from unittest.mock import patch
        from operix_engine.visualization import OpenCvRenderer
        with patch("operix_engine.visualization.cv2.line", wraps=cv2.line) as line:
            OpenCvRenderer().render_proximity(np.zeros((100,100,3),dtype=np.uint8),state,result)
        self.assertTrue(any(call.args[1:3] == ((10,20),(40,20)) for call in line.call_args_list))

    def test_entry_requires_observed_outside_then_inside_and_breaks_at_gap(self):
        zone=Zone("z","Zone",((.4,.4),(1,.4),(1,1),(.4,1)),purpose="restricted")
        rule=RuleConfig("r",1,True,{"kind":"zone_entry","zone_id":"z","class_name":"person","min_duration_s":0})
        engine=RuleEngine(OperationalConfig(1,"camera",(zone,),(rule,)))
        analyzer=SpatiotemporalAnalyzer(width=100,height=100,fps=10,zones=(zone,))
        def step(i,inside):
            box=BoundingBox(50,50,60,60) if inside else BoundingBox(0,0,10,10)
            return engine.evaluate(analyzer.update(i,(Track(1,0,"person",.9,box),)))
        self.assertFalse(step(0,True).candidates)
        self.assertFalse(step(1,False).candidates)
        self.assertEqual(len(step(2,True).candidates),1)
        self.assertFalse(step(3,True).candidates)
        self.assertFalse(step(4,False).candidates)
        self.assertFalse(step(6,True).candidates)
