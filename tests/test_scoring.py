import unittest
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from scripts.score_boxes import score
from scripts.benchmark_find import aggregate

class ScoringTests(unittest.TestCase):
    def test_duplicates_and_missing_objects(self):
        box={'left':0,'top':0,'right':0.4,'bottom':0.4}
        other={'left':0.6,'top':0.6,'right':1,'bottom':1}
        result=score([box,other],[box,box],0.5)
        self.assertEqual((result['tp'],result['fp'],result['fn'],result['duplicateCandidates']),(1,1,1,1))
    def test_maximum_matching_beats_greedy(self):
        box=lambda l,r:{'left':l,'top':0,'right':r,'bottom':1}
        result=score([box(0,.5),box(.4,.9)],[box(.2,.7),box(0,.3)],.3)
        self.assertEqual(result['tp'],2)
    def test_invalid_box(self):
        with self.assertRaises(ValueError):score([], [{'left':0,'right':2,'top':0,'bottom':1}],.5)

    def test_micro_aggregation_includes_negatives_and_localization_failures(self):
        box={'left':0,'top':0,'right':.4,'bottom':.4}
        wrong={'left':.6,'top':.6,'right':1,'bottom':1}
        rows=[]
        for truth,predictions in [([box],[box,box]),([],[wrong]),([box],[])]:
            rows.append({'iou50':score(truth,predictions,.5),'iou30':score(truth,predictions,.3),
                         'truth':len(truth),'predictions':len(predictions),'seconds':1,'unresolved':0,
                         'apiRequests':1,'httpAttempts':2,'failedAttempts':1,'inputTokens':100,
                         'usdEstimate':.0000042,'clusters':2})
        result=aggregate(rows)
        self.assertEqual((result['iou50']['tp'],result['iou50']['fp'],result['iou50']['fn']),(1,2,1))
        self.assertAlmostEqual(result['iou50']['precision'],1/3)
        self.assertEqual(result['iou50']['recall'],.5)
        self.assertEqual(result['iou50']['duplicateCandidates'],1)
        self.assertEqual(result['falseCompleteRuns'],1)
        self.assertEqual(result['httpAttempts'],6)
        self.assertAlmostEqual(result['usdEstimate'],.0000126)

    def test_cli_requires_three_runs_for_v4_too(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'input.json'
            runs=[{'version':v,'run':r,'boxes':[]} for v in ['v1','v2','v3'] for r in [1,2,3]]
            def evaluate():
                path.write_text(json.dumps({'annotation':{'independent':True},'groundTruth':[],'runs':runs}))
                return json.loads(subprocess.check_output([sys.executable,'-m','scripts.score_boxes',str(path)]))
            self.assertFalse(evaluate()['hasThreeRunsEach'])
            runs.extend({'version':'v4','run':r,'boxes':[]} for r in [1,2,3])
            self.assertTrue(evaluate()['hasThreeRunsEach'])

class CohortSummaryTests(unittest.TestCase):
    def test_repeated_negatives_are_one_source_and_macro_weights_categories(self):
        from scripts.benchmark_find import cohort_summary
        rows=[{'case':'negative','groupId':'n','target':'ants','truth':0,'predictions':p,'iou50':score([],[],.5)} for p in [0,0,1]]
        rows += [{'case':'crowd','groupId':'c','target':'ants','truth':9,'predictions':9,'iou50':{'tp':9,'fp':0,'fn':0}},
                 {'case':'single','groupId':'s','target':'dogs','truth':1,'predictions':0,'iou50':{'tp':0,'fp':0,'fn':1}}]
        result=cohort_summary(rows)
        self.assertEqual(result['independentSourceGroups'],3)
        self.assertEqual(result['negativeSourceGroups'],1)
        self.assertEqual(result['negativeGroupsWithAnyFalsePositive'],1)
        self.assertEqual(result['macroCategoryIou50']['recall'],.5)
        self.assertLess(result['negativeAnyRepeatFalsePositiveWilson95'][0],1)
