import unittest
import tempfile
import json
from scripts.benchmark_layout import choose_threshold, metrics, freeze_sources
from scripts.layout_fixtures import fixtures, reference_fixtures, overlap_regression_fixtures
from pathlib import Path


class BenchmarkTests(unittest.TestCase):
    def test_metrics_count_false_negatives_and_false_alarms(self):
        result=metrics([(True,.9),(True,.2),(False,.8),(False,.1)],.7)
        self.assertEqual((result['tp'],result['fp'],result['fn'],result['tn']),(1,1,1,1))
        self.assertEqual(result['precision'],.5)
        self.assertEqual(result['recall'],.5)
        self.assertAlmostEqual(result['brier'],(.01+.64+.64+.01)/4)

    def test_threshold_ties_preserve_existing_default(self):
        self.assertEqual(choose_threshold([(False,.01),(True,.99)]),.7)
        self.assertEqual(choose_threshold([(False,.1),(True,.6)]),.6)

    def test_template_and_source_groups_never_cross_splits(self):
        rows=fixtures()+reference_fixtures(Path('/tmp/data'))
        groups={}
        for row in rows:
            groups.setdefault(row['group'],set()).add(row['split'])
        self.assertTrue(all(len(splits)==1 for splits in groups.values()))
        self.assertEqual(len(rows),48)
        for split in ('calibration','heldout'):
            self.assertEqual(sum(row['split']==split for row in rows),24)
        sources={split:{row[key] for row in rows if row['split']==split for key in ('image','reference') if key in row} for split in ('calibration','heldout')}
        self.assertFalse(sources['calibration'] & sources['heldout'])

    def test_ambiguous_cross_labels_are_excluded_before_inference(self):
        for row in fixtures():
            if 'low-contrast' in row['id'] or 'tiny-text' in row['id']:
                self.assertIsNone(row['labels']['requirements'])
            if 'overlap' in row['id'] or 'clipped-heading' in row['id']:
                self.assertIsNone(row['labels']['readability'])

    def test_frozen_source_and_manifest_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'manifest.json').write_text(json.dumps({'cases':[]}))
            original=freeze_sources(root)
            self.assertEqual(freeze_sources(root),original)
            (root/'modules'/'layout.js').write_text('changed source')
            with self.assertRaisesRegex(ValueError,'changed'):freeze_sources(root)

    def test_mixed_regressions_keep_clipping_and_overlap_as_independent_labels(self):
        rows=overlap_regression_fixtures()
        self.assertEqual(len(rows),24)
        for row in rows:
            if 'clipping-with-' in row['id']:
                self.assertTrue(row['labels']['clipping'])
                self.assertTrue(row['labels']['overlap'])
            if 'heading-crop' in row['id']:
                self.assertTrue(row['labels']['clipping'])
                self.assertFalse(row['labels']['overlap'])
