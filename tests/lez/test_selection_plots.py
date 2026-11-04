"""Result integrity and statistical meaning of the M0 plot notebook."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from lez import selection_plots as plots
from lez.common import file_hash


WORK = Path(__file__).resolve().parents[2]


class SelectionPlotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.snapshot = self.work / plots.PUBLISHED
        shutil.copytree(WORK / plots.PUBLISHED, self.snapshot)

    def published(self):
        return plots.load_comparison(self.work, 'published')

    def make_latest(self):
        directory = self.work / 'data/processed/selection_random/test'
        directory.mkdir(parents=True)
        report = json.loads((self.snapshot / 'summary.json').read_text())
        report['fingerprint'] = report['source_run_fingerprint']
        report['paths'] = {'directory': 'work/data/processed/selection_random/test',
                           'sets': 'work/data/processed/selection_random/test/random_sets.csv',
                           'protocol': 'work/data/processed/selection_random/test/protocol.json'}
        for name in ('random_sets.csv', 'protocol.json'):
            shutil.copyfile(self.snapshot / name, directory / name)
        (directory / 'report.json').write_text(json.dumps(report))
        manifest = {'complete': True, 'fingerprint': report['fingerprint'], 'report': report,
                    'output_hashes': {n: file_hash(directory / n) for n in ('random_sets.csv', 'protocol.json', 'report.json')}}
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        pointer = self.work / 'reports/selection/latest_random_baseline.json'
        pointer.parent.mkdir(parents=True)
        pointer.write_text(json.dumps(report))
        return directory, pointer, report

    def test_verified_snapshot_works_without_gis_or_latest(self):
        data = plots.load_comparison(self.work)
        result = plots.describe_comparison(data)
        self.assertEqual(data.source, 'published')
        self.assertEqual(result['random_sets'], 1000)
        self.assertAlmostEqual(result['baseline_D'], 0.36518658692754424)
        self.assertEqual(result['no_higher_D_count'], 0)
        self.assertEqual(result['higher_D_count'], 1000)

    def test_auto_prefers_latest_but_does_not_hide_corruption(self):
        directory, _, _ = self.make_latest()
        self.assertEqual(plots.load_comparison(self.work).source, 'latest')
        with (directory / 'random_sets.csv').open('a') as f:
            f.write('\ncorrupt')
        with self.assertRaisesRegex(ValueError, 'hash'):
            plots.load_comparison(self.work)

    def test_snapshot_hash_tampering_is_rejected(self):
        (self.snapshot / 'random_sets.csv').write_text('wrong file')
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.published()

    def test_checksum_valid_but_wrong_quota_is_rejected(self):
        p = self.snapshot / 'random_sets.csv'
        p.write_text(p.read_text().replace('A01|A03|', 'A01|A01|', 1))
        sums = json.loads((self.snapshot / 'checksums.json').read_text())
        sums['files']['random_sets.csv'] = file_hash(p)
        (self.snapshot / 'checksums.json').write_text(json.dumps(sums))
        with self.assertRaisesRegex(ValueError, 'quota|lặp'):
            self.published()

    def test_changed_baseline_requires_new_m0(self):
        _, pointer, report = self.make_latest()
        baseline = {'selected_route_ids': list(reversed(report['baseline_selected_ids'])),
                    'metrics': report['baseline_metrics']}
        (pointer.parent / 'latest_selection_30.json').write_text(json.dumps(baseline))
        with self.assertRaisesRegex(ValueError, 'Bộ 30 hiện tại đã đổi'):
            plots.load_comparison(self.work)

    def test_interval_edges_and_percent_denominator(self):
        data = self.published()
        data.frame = data.frame.iloc[:4].copy()
        data.frame['D_combined'] = [0, 0.02, 0.04, 1]
        data.report = copy.deepcopy(data.report)
        data.report['baseline_metrics']['D_combined'] = 1
        bins = plots.d_interval_table(data, .02)
        self.assertEqual(bins['count'].sum(), 4)
        self.assertEqual(list(bins['count'].iloc[:3]), [1, 1, 1])
        self.assertEqual(bins['count'].iloc[-1], 1)
        self.assertEqual(bins['percent'].sum(), 100)
        self.assertTrue(bins['contains_baseline'].iloc[-1])
        self.assertEqual(bins['contains_baseline'].sum(), 1)

    def test_regression_uses_percent_units_and_excludes_baseline(self):
        data = self.published()
        data.frame = data.frame.iloc[:3].copy()
        data.frame['unique_rc_coverage_fraction'] = [.01, .02, .03]
        data.frame['D_combined'] = [.2, .4, .6]
        data.report = copy.deepcopy(data.report)
        data.report['baseline_metrics']['D_combined'] = .999
        result = plots.regression_summary(data)
        self.assertAlmostEqual(result['slope'], .2)
        self.assertAlmostEqual(result['intercept'], 0)
        self.assertAlmostEqual(result['r_squared'], 1)
        self.assertEqual(result['n'], 3)
        self.assertIsNone(result['confidence_interval'])

    def test_constant_x_does_not_invent_a_fit(self):
        data = self.published()
        data.frame['unique_rc_coverage_fraction'] = .01
        result = plots.regression_summary(data)
        self.assertEqual(result['status'], 'constant_or_insufficient_x')
        self.assertIsNone(result['slope'])
        self.assertIsNone(result['r_squared'])

    def test_invalid_parameters_fail_clearly(self):
        data = self.published()
        for width in (0, -1, float('nan'), 2):
            with self.assertRaises(ValueError):
                plots.d_interval_table(data, width)
        with self.assertRaises(ValueError):
            plots.regression_summary(data, 'sample_id')

    def test_export_preserves_sources_and_links_tables_to_plots(self):
        import matplotlib.pyplot as plt
        data = self.published()
        before = dict(data.input_hashes)
        histogram = plots.plot_d_histogram(data)
        relationship = plots.plot_d_relationship(data)
        try:
            directory, report = plots.export_comparison(data, histogram, relationship)
            manifest = json.loads((directory / 'manifest.json').read_text())
            self.assertEqual(report['comparison']['no_higher_D_count'], 0)
            self.assertEqual(report['regression']['fit_population'], 'random_sets_only')
            self.assertFalse(report['random_sampling_rerun'])
            self.assertTrue(manifest['complete'])
            self.assertEqual(len(manifest['output_hashes']), 6)
            self.assertTrue(all(file_hash(directory / n) == h for n, h in manifest['output_hashes'].items()))
            self.assertTrue(all(file_hash(self.work / Path(p).relative_to('work')) == h for p, h in before.items()))
            with self.assertRaisesRegex(ValueError, 'tham số|vẽ lại'):
                plots.export_comparison(data, histogram, relationship, bin_width=.05)
        finally:
            plt.close(histogram)
            plt.close(relationship)


if __name__ == '__main__':
    unittest.main()
