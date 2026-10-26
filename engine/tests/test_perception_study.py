"""Regresiones de tooling de selección, sin pesos ni GPU."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from operix_engine.person_metrics import Prediction
from operix_engine.perception_study import checked_input, class_id, metrics, timing_summary, track_summary, validate_manifest


class PerceptionStudyTests(unittest.TestCase):
    def test_identity_and_checksum_are_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"fixture.txt";path.write_bytes(b'fixture')
            self.assertEqual(checked_input(str(path),hashlib.sha256(b'fixture').hexdigest()),path)
            with self.assertRaises(ValueError):checked_input(str(path),'0'*64)

    def test_protected_paths_are_rejected_before_open(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('no abrir')):
            for name in ('TEST2','REAL_HOLDOUT_V2','PERSON_FINAL_HOLDOUT_V2','person-independent-holdout-v2-2026'):
                with self.subTest(name=name),self.assertRaises(ValueError):checked_input(str(Path(name)/'frame.png'),'0'*64)

    def test_class_mapping_comes_from_names(self):
        self.assertEqual(class_id({4:'truck',8:'person'},'truck'),4)
        with self.assertRaises(ValueError):class_id({0:'person'},'truck')
        with self.assertRaises(ValueError):class_id({1:'truck',2:'truck'},'truck')

    def test_duplicate_prediction_is_false_positive_and_missed_gt_is_false_negative(self):
        samples=[{'id':'one','ground_truth':[(0,0,10,10),(20,20,30,30)]}, {'id':'negative','ground_truth':[]}]
        predictions={'one':(Prediction((0,0,10,10),.9),Prediction((0,0,10,10),.8)), 'negative':(Prediction((0,0,10,10),.3),)}
        value=metrics(samples,predictions)
        self.assertEqual((value['tp'],value['fp'],value['fn']),(1,2,1))
        self.assertAlmostEqual(value['f1'],.4)
        with self.assertRaises(ValueError):metrics(samples,{'one':()})

    def test_timing_uses_global_frames_divided_by_sum_not_instant_fps(self):
        value=timing_summary([.01,.03])
        self.assertEqual(value['fps'],50.)
        self.assertAlmostEqual(value['p95_ms'],29.)
        self.assertAlmostEqual(value['stdev_ms'],14.1421356237)
        for times in ([],[0.],[-1.],[float('nan')]):
            with self.assertRaises(ValueError):timing_summary(times)

    def test_tracking_statistics_do_not_claim_id_switches(self):
        value=track_summary({1:[0,1,4],2:[1,2]})
        self.assertEqual(value['internal_gap_episodes'],1)
        self.assertEqual(value['missing_track_frames'],2)
        self.assertNotIn('id_switches',value)

    def test_manifest_freezes_operating_point_and_development_identity(self):
        manifest={'study_id':'PERSON_MODEL_SELECTION_DEVELOPMENT','label':'DEVELOPMENT_SELECTION_METRICS',
                  'configuration':{'imgsz':640,'confidence':.1,'nms_iou':.7,'batch':1,'device':'cuda:0','match_iou':.5,
                                   'warmup':20,'repetitions':3,'pipeline_warmup_frames':20,'pipeline_repetitions':3},
                  'samples':[{'id':'development'}],'models':[{'id':'YOLO11N_COCO'}]}
        self.assertIs(validate_manifest(manifest),manifest['configuration'])
        for key,value in (('confidence',.45),('batch',2),('repetitions',0)):
            invalid=copy.deepcopy(manifest);invalid['configuration'][key]=value
            with self.assertRaises(ValueError):validate_manifest(invalid)
        manifest['study_id']='PERSON_EVALUATION_PROTOCOL_V1'
        with self.assertRaises(ValueError):validate_manifest(manifest)
