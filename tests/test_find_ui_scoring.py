"""Reference-relative UI scoring must preserve provenance and uncertainty scope."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.score_find_ui import score_directory

B={'left':.2,'top':.2,'right':.8,'bottom':.8}


class FindUIScoringTests(unittest.TestCase):
    def fixture(self,root):
        (root/'inputs').mkdir();data=b'frozen original';(root/'inputs'/'photo.jpg').write_bytes(data)
        cases=[{'id':name,'image':{'name':'photo.jpg'},'sha256':hashlib.sha256(data).hexdigest(),'groundTruth':truth} for name,truth in [('positive',[B]),('negative',[])]]
        manifest={'annotation':{'independent':False,'referenceKind':'agent-visual','independentOfDetectorOutputs':True,'humanAudited':False},'cases':cases,'versions':['v4','v5'],'repeats':1,'model':'jev-1.14.0'}
        (root/'manifest.json').write_text(json.dumps(manifest))
        for c in cases:
            for v in manifest['versions']:
                run={'case':c['id'],'version':v,'run':1,'error':False,'pageErrors':[],'seconds':1,
                  'boxes':[B] if v=='v4' else [],'reviewBoxes':[B] if v=='v5' and c['id']=='positive' else [],
                  'exchanges':[{'status':200,'response':{'model':'jev-1.14.0','usage':{'input_tokens':10}}}]}
                (root/f"{c['id']}-{v}-1.json").write_text(json.dumps(run))

    def test_agent_references_require_explicit_opt_in(self):
        with TemporaryDirectory() as d:
            p=Path(d);self.fixture(p)
            with self.assertRaisesRegex(ValueError,'explicitly'):score_directory(p,p/'scores.json')
            r=score_directory(p,p/'scores.json',True)
            self.assertFalse(r['annotation']['independent']);self.assertFalse(r['annotation']['humanAudited'])
            self.assertIn('not independently',r['scope'])

    def test_negative_false_positives_count_and_review_outlines_do_not(self):
        with TemporaryDirectory() as d:
            p=Path(d);self.fixture(p);r=score_directory(p,p/'scores.json',True)
            a,b=[r['versions'][v]['iou50'] for v in ['v4','v5']]
            self.assertEqual((a['tp'],a['fp'],a['fn']),(1,1,0))
            self.assertEqual((b['tp'],b['fp'],b['fn']),(0,0,1))
            self.assertEqual(next(row for row in r['runs'] if row['version']=='v5' and row['case']=='positive')['reviewIou50']['tp'],1)

    def test_v6_compares_paired_sources_without_replacing_v5_reports(self):
        with TemporaryDirectory() as d:
            p=Path(d);self.fixture(p)
            manifest=json.loads((p/'manifest.json').read_text())
            manifest['versions'].append('v6')
            (p/'manifest.json').write_text(json.dumps(manifest))
            for case in manifest['cases']:
                record=json.loads((p/f"{case['id']}-v4-1.json").read_text())
                record['version']='v6'
                (p/f"{case['id']}-v6-1.json").write_text(json.dumps(record))
            report=score_directory(p,p/'scores.json',True)
            self.assertEqual(report['v6PairedDifferences']['v4']['recall']['difference'],0)
            self.assertIn('v4',report['pairedDifferences'])

    def test_failed_runs_and_changed_sources_are_not_silently_dropped(self):
        with TemporaryDirectory() as d:
            p=Path(d);self.fixture(p)
            f=p/'positive-v5-1.json';r=json.loads(f.read_text());r['pageErrors']=['broken UI'];f.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'Failed UI'):score_directory(p,p/'scores.json',True)
            (p/'inputs'/'photo.jpg').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'source image mismatch'):score_directory(p,p/'scores.json',True)

    def test_network_failures_without_response_records_are_unknown_cost_attempts(self):
        with TemporaryDirectory() as d:
            p=Path(d);self.fixture(p);f=p/'positive-v5-1.json';r=json.loads(f.read_text())
            r['exchanges']=[];r['evidence']={'budget':{'httpAttempts':1,'stopped':'service-failure'}};f.write_text(json.dumps(r))
            report=score_directory(p,p/'scores.json',True);row=next(x for x in report['runs'] if x['case']=='positive' and x['version']=='v5')
            self.assertEqual((row['httpAttempts'],row['failedAttempts'],row['unknownUsageAttempts']),(1,1,1))
            self.assertEqual(row['iou50']['fn'],1)
