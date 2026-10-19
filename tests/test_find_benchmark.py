"""Benchmark integrity tests; no live judgments."""
import json
from pathlib import Path
import tempfile
import unittest
from scripts.benchmark_find import attempt_usage, paired_bootstrap, snapshot, digest, analyze
from contextlib import redirect_stdout
import io

class FindBenchmarkTests(unittest.TestCase):
    def test_failed_unknown_usage_is_not_free_and_output_tokens_are_preserved(self):
        totals=attempt_usage([
            {'ok':True,'body':{'usage':{'input_tokens':100,'output_tokens':20}}},
            {'ok':False,'body':{'usage':{'input_tokens':40,'output_tokens':3}}},
            {'ok':False,'body':None},
            {'ok':True,'body':{'usage':{'input_tokens':True}}},
        ])
        self.assertEqual(totals,{'inputTokens':140,'outputTokens':23,'unknownCostAttempts':2})

    def test_bootstrap_resamples_source_groups_with_repeats_kept_together(self):
        rows=[]
        for group,counts in [('scene-a',(1,0)),('scene-b',(0,1))]:
            for repeat in range(1,4):
                for v,tp in zip(['v5','v2'],counts):
                    rows.append({'case':group,'groupId':group,'run':repeat,'version':v,'iou50':{'tp':tp,'fp':1-tp,'fn':1-tp}})
        report=paired_bootstrap(rows,'v5','v2',samples=100,seed=7)
        self.assertEqual(report['groups'],2)
        self.assertEqual(report['recall']['difference'],0)
        self.assertEqual(report['recall']['ci95'],[-1,1])
        self.assertEqual(report,paired_bootstrap(rows,'v5','v2',samples=100,seed=7))
        with self.assertRaises(ValueError):paired_bootstrap(rows[:-1],'v5','v2')

    def test_snapshot_verifies_inputs_freezes_dependencies_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source';out=Path(directory)/'experiment'
            source.mkdir();(source/'photo.jpg').write_bytes(b'fixture')
            manifest={'cases':[{'id':'fixture','path':'photo.jpg','sha256':digest(b'fixture')}],
                      'model':'jev-1.14.0','annotation':{'independent':True}}
            (source/'manifest.json').write_text(json.dumps(manifest))
            snapshot(out,source,['v4','v5','v6'],3,{'maxRegions':21},{'minBoxConfidence':.8})
            result=json.loads((out/'manifest.json').read_text())
            self.assertIn('tools/find/v5.js',result['moduleHashes'])
            self.assertIn('tools/find/v6/combined.js',result['moduleHashes'])
            self.assertEqual(result['versions'],['v4','v5','v6'])
            self.assertEqual(result['repeats'],3)
            self.assertEqual(result['v5Config'],{'maxRegions':21})
            self.assertEqual(result['v6Config'],{'minBoxConfidence':.8})
            with self.assertRaises(ValueError):snapshot(out,source,['v5'])
            (source/'photo.jpg').write_bytes(b'changed')
            with self.assertRaises(ValueError):snapshot(Path(directory)/'new',source,['v5'])
            self.assertFalse((Path(directory)/'new').exists())


    def test_hard_failures_remain_in_quality_and_unknown_cost_report(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            box={'left':0,'top':0,'right':1,'bottom':1}
            manifest={'versions':['v5'],'repeats':1,'cases':[{'id':'fixture','target':'cats','stratum':'single','groundTruth':[box]}],
                      'model':'jev-1.14.0','price':{'usdPerMillionInputTokens':.042}}
            (out/'manifest.json').write_text(json.dumps(manifest))
            (out/'fixture-v5-1.json').write_text(json.dumps({'case':'fixture','version':'v5','run':1,'seconds':1,
                'error':'browser failure','pageErrors':[],'result':None,'exchanges':[{}],
                'attempts':[{'ok':False,'body':None}]}))
            with redirect_stdout(io.StringIO()):analyze(out)
            report=json.loads((out/'summary.json').read_text());totals=report['versions']['v5']
            self.assertEqual(totals['iou50']['fn'],1)
            self.assertEqual(totals['hardFailureRuns'],1)
            self.assertEqual(totals['unknownCostAttempts'],1)
            self.assertFalse(totals['costComplete'])
            self.assertEqual(report['gates']['minimumCoverage'],'fail')

    def test_preflight_refuses_unavailable_or_unconfigured_endpoint(self):
        from unittest.mock import patch
        from scripts.benchmark_find import preflight_endpoint
        with patch('scripts.benchmark_find.urlopen',side_effect=ConnectionRefusedError):
            with self.assertRaisesRegex(RuntimeError,'no live jobs'):preflight_endpoint('http://unavailable.test')
        with patch('scripts.benchmark_find.urlopen') as opened:
            opened.return_value.__enter__.return_value=io.StringIO('{"apiKeyConfigured":false}')
            with self.assertRaisesRegex(RuntimeError,'no live jobs'):preflight_endpoint('http://unconfigured.test')
        with patch('scripts.benchmark_find.urlopen') as opened:
            opened.return_value.__enter__.return_value=io.StringIO('{"apiKeyConfigured":true}')
            preflight_endpoint('http://ready.test')

    def test_v6_config_is_validated_and_result_mismatches_are_rejected(self):
        from scripts.benchmark_find import validate_v6_overrides,check_v6_result_config,V6_SETTING_KEYS
        for invalid in [[],None,False,{'minBoxConfidence':True},{'duplicateBoxIou':1.1},{'maxRegions':100},{'minChoiceConfidence':float('nan')}]:
            with self.assertRaises(ValueError):validate_v6_overrides(invalid)
        config={key:.5 for key in V6_SETTING_KEYS}
        check_v6_result_config(config,{'minBoxConfidence':.5})
        with self.assertRaisesRegex(ValueError,'disagree'):check_v6_result_config(config,{'minBoxConfidence':.8})
        with self.assertRaisesRegex(ValueError,'Missing'):check_v6_result_config(None,{})
