"""Synthetic checks for the corrected quota/purity M1 and quota-controlled M2b."""
from collections import Counter
import unittest
from unittest.mock import patch

import numpy as np

from lez import selection_benchmarks as benchmarks
from lez import selection_m1 as m1
from lez import selection_metrics as metrics

from test_selection_benchmarks import fixture


def problem(routes, reference, counts=None):
    """Create genuine ABC-pure route vectors and independent reference lengths.

    Each route is (ID, zone, LEZ group, target RC, four RC lengths[, connector]).
    """
    walks, parts = [], {}
    for rid, zone, group, _, lengths, *extra in routes:
        ids = []
        for k, length in enumerate(lengths):
            if length:
                pid = f'{rid}/RC{k + 1}'
                parts[pid] = (length, [('ABC'.index(zone) * 4 + k, length)])
                ids.append(pid)
        if extra and extra[0]:
            pid = f'{rid}/connector'
            parts[pid] = (extra[0], [])
            ids.append(pid)
        walks.append((rid, zone, group, ids))
    reference = np.asarray(reference, dtype=float).reshape(-1)
    data, options = fixture(walks, parts, counts, reference / reference.sum())
    for feature, walk, spec in zip(data['features'], data['walks'], routes):
        feature['rc_target'] = walk['rc_target'] = spec[3]
    data['network_lengths'] = reference
    data['domain_lengths'] = {g: reference / 2 for g in data['domain_lengths']}
    return data, options


def route_ids(data, result):
    return {data['features'][i]['route_id'] for i in result['selected_indices']}


class M1QuotaTests(unittest.TestCase):
    def test_integer_allotment_matches_the_unbounded_largest_remainders(self):
        self.assertEqual(list(m1.bounded_quota([46, 25, 24, 5], [10] * 4, 10)),
                         [5, 3, 2, 0])

    def test_capacity_shortfall_redistributes_without_inventing_candidates(self):
        result = list(m1.bounded_quota([40, 30, 20, 10], [0, 3, 10, 10], 10))
        # RC1 has no candidates and RC2 saturates after rescaling. Allocate
        # the seven remaining slots to RC3:RC4 in the original 2:1 proportion.
        self.assertEqual(result, [0, 3, 5, 2])
        self.assertEqual(sum(result), 10)
        self.assertTrue(all(0 <= n <= cap for n, cap in zip(result, [0, 3, 10, 10])))
        self.assertTrue(all(n >= floor for n, floor in zip(result[2:], [2, 1])))
        with self.assertRaises(ValueError):
            m1.bounded_quota([40, 30, 20, 10], [0, 3, 2, 1], 10)

    def test_missing_A_RC1_stays_in_network_reference_and_eligibility_is_respected(self):
        data, options = problem([
            ('A01', 'A', 'inside', 'RC2', (0, 100, 0, 0)),
            ('A02', 'A', 'inside', 'RC2', (0, 150, 0, 0)),
            ('A03', 'A', 'inside', 'RC1', (100, 0, 0, 0)),
            ('A99', 'A', 'outside', 'RC1', (100, 0, 0, 0)),
            ('B01', 'B', 'inside', 'RC2', (0, 100, 0, 0)),
            ('C01', 'C', 'outside', 'RC1', (100, 0, 0, 0))],
            [[600, 400, 0, 0], [0, 100, 0, 0], [100, 0, 0, 0]],
            counts={'A': 2, 'B': 1, 'C': 1})
        data['eligible_indices'] = {0, 1, 3, 4, 5}
        with self.assertRaisesRegex(ValueError, 'inconsistent zone, LEZ or RC target'):
            m1.m1_targets(data, options)
        data['eligible_indices'].remove(3)  # A99 is outside; cannot count toward A inside.
        targets = {(r['zone'], r['rc']): r for r in m1.m1_targets(data, options)}
        self.assertEqual(len(targets), 12)
        rc1, rc2 = targets['A', 'RC1'], targets['A', 'RC2']
        self.assertAlmostEqual(rc1['network_share'], .6)
        self.assertAlmostEqual(rc1['theoretical_slots'], 1.2)
        self.assertEqual((rc1['available'], rc1['slots']), (0, 0))
        self.assertAlmostEqual(rc2['network_share'], .4)
        self.assertEqual((rc2['available'], rc2['slots']), (2, 2))
        result = m1.select_m1(data, options, list(targets.values()))
        self.assertEqual(route_ids(data, result), {'A01', 'A02', 'B01', 'C01'})


class M1PurityTests(unittest.TestCase):
    def distinction_problem(self):
        return problem([
            ('A01', 'A', 'inside', 'RC1', (100, 0, 0, 0)),
            ('C01', 'C', 'outside', 'RC1', (100, 0, 0, 0)),
            ('B01', 'B', 'inside', 'RC1', (80, 0, 0, 0), 40),
            ('B02', 'B', 'inside', 'RC1', (70, 30, 0, 0))],
            [[1000, 0, 0, 0], [800, 30, 0, 0], [1000, 0, 0, 0]])

    def test_purity_uses_full_route_length_even_when_global_D_prefers_other_route(self):
        data, options = self.distinction_problem()
        targets = m1.m1_targets(data, options)
        result_D = benchmarks.greedy_objective(data, options, (0, 1), 'M2')
        with patch.object(metrics, 'criteria', side_effect=AssertionError('weighted criteria used')), \
             patch.object(metrics, 'select', side_effect=AssertionError('M5 selector used')):
            result = m1.select_m1(data, options, targets)
        self.assertEqual(result['status'], 'completed')
        # B02 purity = 70/100, higher than B01 80/(80+40); B01 gives smaller D.
        self.assertEqual(route_ids(data, result), {'A01', 'C01', 'B02'})
        self.assertAlmostEqual(result['target_purity_sum'], 2.7)
        self.assertEqual(route_ids(data, result_D), {'A01', 'C01', 'B01'})
        self.assertGreater(result['metrics']['D_combined'], result_D['metrics']['D_combined'])

    def test_equal_purity_prefers_shorter_full_route_then_ID(self):
        data, options = problem([
            ('A01', 'A', 'inside', 'RC1', (100, 0, 0, 0)),
            ('C01', 'C', 'outside', 'RC1', (100, 0, 0, 0)),
            ('B01', 'B', 'inside', 'RC1', (96, 0, 0, 0), 24),
            ('B03', 'B', 'inside', 'RC1', (64, 16, 0, 0)),
            ('B02', 'B', 'inside', 'RC1', (64, 16, 0, 0))],
            [[100, 0, 0, 0], [300, 40, 0, 0], [100, 0, 0, 0]])
        result = m1.select_m1(data, options, m1.m1_targets(data, options))
        self.assertIn('B02', route_ids(data, result))
        self.assertAlmostEqual(result['target_purity_sum'], 2.8)

    def test_top_purity_set_conflict_at_cap_is_not_silently_repaired(self):
        data, options = self.distinction_problem()
        data['corridors'][0, 3] = data['corridors'][3, 0] = .7
        targets = m1.m1_targets(data, options)
        with self.assertRaises(ValueError):
            m1.select_m1(data, options, targets)


class M2bQuotaControlTests(unittest.TestCase):
    def controlled_problem(self):
        return problem([
            ('A01', 'A', 'inside', 'RC2', (0, 20, 0, 0)),
            ('C01', 'C', 'outside', 'RC1', (100, 0, 0, 0)),
            ('A02', 'A', 'inside', 'RC2', (0, 55, 45, 0)),
            ('A03', 'A', 'inside', 'RC3', (0, 0, 10, 0)),
            ('B01', 'B', 'inside', 'RC1', (100, 0, 0, 0))],
            [[0, 100, 100, 0], [100, 0, 0, 0], [100, 0, 0, 0]],
            counts={'A': 2, 'B': 1, 'C': 1})

    def test_M2b_keeps_the_same_RC_slots_even_when_uncontrolled_D_is_lower(self):
        data, options = self.controlled_problem()
        targets = m1.m1_targets(data, options)
        ordinary = benchmarks.greedy_objective(data, options, (0, 1), 'M2')
        result = m1.greedy_m2b(data, options, (0, 1), targets)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(route_ids(data, ordinary), {'A01', 'A02', 'B01', 'C01'})
        self.assertEqual(route_ids(data, result), {'A01', 'A03', 'B01', 'C01'})
        self.assertGreater(result['metrics']['D_combined'], ordinary['metrics']['D_combined'])
        actual = Counter((data['features'][i]['sampling_zone'], data['features'][i]['rc_target'])
                         for i in result['selected_indices'])
        self.assertEqual(actual, {(row['zone'], row['rc']): row['slots']
                                  for row in targets if row['slots']})


if __name__ == '__main__':
    unittest.main()
