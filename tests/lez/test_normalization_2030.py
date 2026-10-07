"""Offline regression checks for RC composition and connector denominators."""
from collections import Counter
import importlib.util
from pathlib import Path
import sys
import unittest

WORK = Path('/Users/quanh.hg/python/work')
sys.path.insert(0, str(WORK / 'scripts'))
staged = Path(__file__).resolve().parents[1] / 'sampling_2030.py'
source = staged if staged.exists() else WORK / 'scripts/lez/sampling_2030.py'
spec = importlib.util.spec_from_file_location('lez.normalization_2030_under_test', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
rc_composition = module.rc_composition


class CompositionRegressionTests(unittest.TestCase):
    def base(self):
        return Counter({('V1', 'RC1'): 10, ('V1', 'RC2'): 30, ('N1', 'RC1'): 60}), Counter({('V1', 'RC1'): 20, ('V1', 'RC2'): 20, ('N1', 'RC1'): 10})

    def test_huge_connector_lengths_cannot_change_rc_fractions_or_D(self):
        network, sample = self.base()
        baseline = rc_composition(network, sample)
        network.update({('V1', 'connector'): 1_000_000_000, ('N1', 'connector'): 2_000_000_000})
        sample.update({('V1', 'connector'): 3_000_000_000, ('N1', 'connector'): 4_000_000_000})
        rows, sampled, connectors, metrics = rc_composition(network, sample)
        self.assertEqual(rows, baseline[0])
        self.assertEqual(sampled, baseline[1])
        self.assertEqual(len(rows), 60)
        self.assertEqual(len(sampled), 60)
        self.assertTrue(all(r['rc'] in module.RC_CLASSES for r in rows + sampled))
        self.assertAlmostEqual(metrics['D_combined'], .4)
        self.assertAlmostEqual(metrics['D_by_domain']['inside'], .25)
        self.assertAlmostEqual(metrics['D_by_domain']['outside'], 0)
        self.assertEqual(metrics['network_rc_m'], 100)
        self.assertEqual(metrics['sample_rc_m'], 50)
        self.assertEqual(metrics['network_all_m'], 3_000_000_100)
        self.assertEqual(metrics['sample_all_m'], 7_000_000_050)
        self.assertTrue(all(r['included_in_rc_composition'] is False for r in connectors))
        self.assertTrue(all('network_fraction' not in r and 'gap_fraction' not in r for r in connectors))
        self.assertAlmostEqual(sum(r['network_fraction_all_rc'] for r in rows), 1)
        self.assertAlmostEqual(sum(r['sample_fraction'] for r in sampled), 1)
        for group in ['inside', 'outside']:
            self.assertAlmostEqual(sum(r['network_fraction_domain_rc'] for r in rows if r['group'] == group), 1)

    def test_sample_with_only_connectors_has_undefined_RC_composition(self):
        network, _ = self.base()
        rows, sampled, connectors, metrics = rc_composition(network, {('V1', 'connector'): 200})
        self.assertIsNone(metrics['D_combined'])
        self.assertIsNone(metrics['D_by_domain']['inside'])
        self.assertIsNone(metrics['D_by_domain']['outside'])
        self.assertIsNone(metrics['sample_fraction_sum'])
        self.assertEqual(metrics['sample_rc_m'], 0)
        self.assertEqual(metrics['sample_all_m'], 200)
        self.assertTrue(all(r['sample_fraction'] is None and r['gap_fraction'] is None for r in sampled))
        self.assertAlmostEqual(sum(r['network_fraction_all_rc'] for r in rows), 1)

    def test_empty_network_and_sample_keep_null_denominators(self):
        rows, sampled, connectors, metrics = rc_composition({}, {})
        self.assertEqual((len(rows), len(sampled), connectors), (60, 60, []))
        self.assertIsNone(metrics['D_combined'])
        self.assertIsNone(metrics['network_fraction_sum'])
        self.assertTrue(all(r['network_fraction'] is None and r['sample_fraction'] is None and r['gap_fraction'] is None for r in sampled))
        self.assertTrue(all(r['network_fraction_domain_rc'] is None for r in rows))

    def test_empty_domain_is_null_even_if_other_domain_has_data(self):
        _, _, _, metrics = rc_composition({('V1', 'RC1'): 10}, {('V1', 'RC1'): 20})
        self.assertEqual(metrics['D_by_domain']['inside'], 0)
        self.assertIsNone(metrics['D_by_domain']['outside'])

    def test_helper_does_not_mutate_source_counts(self):
        network, sample = self.base()
        before = dict(network), dict(sample)
        rc_composition(network, sample)
        self.assertEqual((dict(network), dict(sample)), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
