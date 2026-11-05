"""Independent synthetic protocol checks for the M2/M3 greedy benchmarks.

The fixtures retain the production ABC×RC shape, quota buckets, traversal
vectors and distinct physical-part coverage. No GIS runtime or real downloads
are necessary to distinguish the two scientific objectives.
"""
import copy
from collections import Counter
import unittest
from unittest.mock import patch

import numpy as np

from lez import selection_benchmarks as benchmarks
from lez import selection_metrics as metrics


def fixture(routes, physical_parts=None, zone_counts=None, q=None):
    """Build aligned production-shaped data from small, explicit route walks.

    A route is (ID, zone, group, vector-in-first-two-cells) unless its fourth
    item is a list of named physical parts. Part specifications are
    (physical length, [(RC cell index, RC length), ...]); [] marks a connector.
    Repeated part IDs contribute repeatedly to traversal, once to coverage.
    """
    cells = [(zone, rc) for zone in 'ABC' for rc in metrics.RC]
    parts, part_cells = {}, {}
    for pid, (length, contributions) in (physical_parts or {}).items():
        parts[pid] = {'length_m': float(length)}
        part_cells[pid] = list(contributions)
    walks, features, vectors, part_sets = [], [], [], []
    for index, (rid, zone, group, description) in enumerate(routes):
        if isinstance(description, tuple):
            path = []
            for cell, length in enumerate(description):
                if length:
                    pid = f'{rid}/cell{cell}'
                    parts[pid] = {'length_m': float(length)}
                    part_cells[pid] = [(cell, float(length))]
                    path.append(pid)
        else:
            path = list(description)
        vector = np.zeros(12)
        for pid in path:
            for cell, length in part_cells[pid]:
                vector[cell] += length
        length = sum(parts[pid]['length_m'] for pid in path)
        walks.append({'route_id': rid, 'length_m': length, 'part_ids': path})
        features.append({'route_id': rid, 'stratum_id': zone,
                         'sampling_zone': zone, 'group': group,
                         'rc_target': 'RC1', 'C6': index * 1000.0})
        vectors.append(vector)
        part_sets.append(set(path))
    vectors = np.asarray(vectors)
    q = np.asarray(q if q is not None else [.5, .5] + [0.] * 10)
    network_lengths = q * 10000
    n = len(routes)
    domains = {group: np.asarray([v if feature['group'] == group else np.zeros(12)
                                  for v, feature in zip(vectors, features)])
               for group in ('inside', 'outside')}
    data = {'cells': cells, 'features': features, 'walks': walks,
            'vectors': vectors, 'q': q, 'network_lengths': network_lengths,
            'P': vectors / np.asarray([r['length_m'] for r in walks])[:, None],
            'parts': parts, 'part_cells': part_cells, 'part_sets': part_sets,
            'corridors': np.eye(n), 'overlaps': np.eye(n),
            'bins': [{('arbitrary-feature', i)} for i in range(n)],
            'distances': np.abs(np.arange(n)[:, None] - np.arange(n)[None, :]),
            'X': np.arange(n)[:, None].astype(float),
            'domain_vectors': domains,
            'domain_lengths': {g: network_lengths / 2 for g in domains}}
    counts = zone_counts or {'A': 1, 'B': 1, 'C': 1}
    opts = {'quota': {'inside': counts['A'] + counts['B'], 'outside': counts['C']},
            'intersection_quota': [
                {'name': f'{zone}_{group}', 'group': group,
                 'sampling_zones': [zone], 'count': counts[zone]}
                for zone, group in (('A', 'inside'), ('B', 'inside'), ('C', 'outside'))],
            'required_strata': ['A', 'B', 'C'], 'minimum_cell_fraction': .3,
            'max_corridor_overlap': .7, 'seed_count': 10,
            'tie_tolerance': 1e-10,
            'weights': {'C1': 0, 'C2': 0, 'C3': 0, 'C4': 0,
                        'C5': 0, 'C6': 100, 'C7': 0}}
    return data, opts


def selected_ids(data, result):
    return {data['features'][i]['route_id'] for i in result['selected_indices']}


class ObjectiveBenchmarkTests(unittest.TestCase):
    def test_M2_recomputes_aggregate_D_and_dynamic_denominator(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (8, 0)),
            ('C01', 'C', 'outside', (0, 2)),
            ('B01', 'B', 'inside', (0, 2)),
            ('B02', 'B', 'inside', (6, 4))], q=[.6, .4] + [0.] * 10)
        # B02 alone perfectly matches q; nevertheless B01 better balances
        # the existing (8,2). Ranking routes once by their own D is incorrect.
        self.assertEqual(metrics.D(data['vectors'][3], data['q']), 0.)
        result = benchmarks.greedy_objective(data, opts, (0, 1), 'M2')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(selected_ids(data, result), {'A01', 'C01', 'B01'})
        vector = data['vectors'][result['selected_indices']].sum(axis=0)
        self.assertAlmostEqual(metrics.D(vector, data['q']), 1 / 15)

    def test_M2_never_calls_weighted_criteria_or_swap_selection(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (8, 0)), ('C01', 'C', 'outside', (0, 2)),
            ('B01', 'B', 'inside', (0, 2)), ('B02', 'B', 'inside', (6, 4))],
            q=[.6, .4] + [0.] * 10)
        with patch.object(metrics, 'criteria', side_effect=AssertionError('weighted criteria used')), \
             patch.object(metrics, 'select', side_effect=AssertionError('M5 selector used')):
            first = benchmarks.greedy_objective(data, opts, (0, 1), 'M2')
            opts['weights'] = {'C1': 100000, 'C7': -100000}
            data['bins'] = [set(), set(), set(), {('strong distractor', 999)}]
            second = benchmarks.greedy_objective(data, opts, (0, 1), 'M2')
        self.assertEqual(first['selected_indices'], second['selected_indices'])

    def test_M2_can_complete_when_every_addition_increases_D(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('B01', 'B', 'inside', (10, 0)), ('B02', 'B', 'inside', (20, 0))])
        self.assertEqual(metrics.D(data['vectors'][[0, 1]].sum(axis=0), data['q']), 0.)
        result = benchmarks.greedy_objective(data, opts, (0, 1), 'M2')
        self.assertEqual(result['status'], 'completed')
        self.assertIn(2, result['selected_indices'])
        self.assertAlmostEqual(metrics.D(data['vectors'][result['selected_indices']].sum(axis=0), data['q']), .25)

    def test_M2_tolerance_ties_use_route_ID_instead_of_index_or_secondary_score(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('BZ', 'B', 'inside', (1, 1)),
            ('BA', 'B', 'inside', (1 + 1e-8, 1))])
        opts['tie_tolerance'] = 1e-8
        result = benchmarks.greedy_objective(data, opts, (0, 1), 'M2')
        self.assertIn(3, result['selected_indices'])
        self.assertNotIn(2, result['selected_indices'])
        opts['tie_tolerance'] = 1e-12
        result = benchmarks.greedy_objective(data, opts, (0, 1), 'M2')
        self.assertIn(2, result['selected_indices'])

    def test_M3_counts_unique_RC_parts_not_traversals_or_connectors(self):
        parts = {'a': (10, [(0, 10)]), 'c': (10, [(1, 10)]),
                 'small': (1, [(0, 1)]), 'big': (20, [(0, 20)]),
                 'connector': (500, [])}
        data, opts = fixture([
            ('A01', 'A', 'inside', ['a']), ('C01', 'C', 'outside', ['c']),
            ('B01', 'B', 'inside', ['a'] * 8 + ['small', 'connector']),
            ('B02', 'B', 'inside', ['big'])], parts)
        self.assertGreater(data['walks'][2]['length_m'], data['walks'][3]['length_m'])
        result = benchmarks.greedy_objective(data, opts, (0, 1), 'M3')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(selected_ids(data, result), {'A01', 'C01', 'B02'})
        self.assertEqual(metrics.summary(data, result['selected_indices'])['unique_rc_length_m'], 40.)

    def test_M3_recomputes_union_after_each_addition(self):
        parts = {'a': (10, [(0, 10)]), 'c': (10, [(1, 10)]),
                 'x': (10, [(0, 10)]), 'y': (9, [(1, 9)]),
                 'z': (8, [(0, 8)])}
        data, opts = fixture([
            ('A01', 'A', 'inside', ['a']), ('C01', 'C', 'outside', ['c']),
            ('B01', 'B', 'inside', ['x', 'y']),
            ('B02', 'B', 'inside', ['x']),
            ('B03', 'B', 'inside', ['z'])], parts,
            zone_counts={'A': 1, 'B': 2, 'C': 1})
        result = benchmarks.greedy_objective(data, opts, (0, 1), 'M3')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(selected_ids(data, result), {'A01', 'C01', 'B01', 'B03'})
        self.assertEqual(metrics.summary(data, result['selected_indices'])['unique_rc_length_m'], 47.)

    def test_M3_maximizes_coverage_even_when_D_is_worse(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (10, 0)), ('C01', 'C', 'outside', (0, 10)),
            ('B01', 'B', 'inside', (.5, .5)), ('B02', 'B', 'inside', (90, 0))])
        with patch.object(metrics, 'criteria', side_effect=AssertionError('weighted criteria used')):
            result = benchmarks.greedy_objective(data, opts, (0, 1), 'M3')
        self.assertIn(3, result['selected_indices'])
        self.assertGreater(metrics.D(data['vectors'][result['selected_indices']].sum(axis=0), data['q']), 0.)

    def test_M3_equal_gain_uses_ID_without_D_as_hidden_secondary_objective(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('BZ', 'B', 'inside', (1, 1)), ('BA', 'B', 'inside', (2, 0))])
        opts['coverage_tie_tolerance_m'] = 1e-8
        result = benchmarks.greedy_objective(data, opts, (0, 1), 'M3')
        # Both add exactly 2m, so BA wins lexically despite its larger D.
        self.assertIn(3, result['selected_indices'])
        self.assertNotIn(2, result['selected_indices'])

    def test_ineligible_candidate_cannot_win_either_objective(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('B01', 'B', 'inside', (100, 100)), ('B02', 'B', 'inside', (1, 0))])
        data['eligible_indices'] = {0, 1, 3}
        for method in ('M2', 'M3'):
            result = benchmarks.greedy_objective(data, opts, (0, 1), method)
            self.assertEqual(result['status'], 'completed')
            self.assertIn(3, result['selected_indices'])
            self.assertNotIn(2, result['selected_indices'])

    def test_overlap_at_cap_is_rejected_and_nextafter_below_is_allowed(self):
        for method in ('M2', 'M3'):
            with self.subTest(method=method):
                data, opts = fixture([
                    ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
                    ('B01', 'B', 'inside', (10, 10)), ('B02', 'B', 'inside', (1, 0))])
                data['corridors'][0, 2] = data['corridors'][2, 0] = .7
                result = benchmarks.greedy_objective(data, opts, (0, 1), method)
                self.assertIn(3, result['selected_indices'])
                self.assertNotIn(2, result['selected_indices'])
                data['corridors'][0, 2] = data['corridors'][2, 0] = np.nextafter(.7, 0)
                result = benchmarks.greedy_objective(data, opts, (0, 1), method)
                self.assertIn(2, result['selected_indices'])

    def test_remaining_slots_reserve_missing_required_strata(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('A02', 'A', 'inside', (10, 10)), ('B01', 'B', 'inside', (1, 0))])
        opts['intersection_quota'] = []
        for method in ('M2', 'M3'):
            result = benchmarks.greedy_objective(data, opts, (0, 1), method)
            self.assertEqual(result['status'], 'completed')
            self.assertIn(3, result['selected_indices'])
            self.assertNotIn(2, result['selected_indices'])

    def test_material_cell_count_is_an_outcome_not_an_implicit_filter(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('B01', 'B', 'inside', (1, 1))])
        data['P'][:] = 0
        for method in ('M2', 'M3'):
            result = benchmarks.greedy_objective(data, opts, (0, 1), method)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['metrics']['material_cells'], 0)

    def test_quota_completion_uses_real_feasibility_gate_and_does_not_mutate_inputs(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('A02', 'A', 'inside', (1, 1)), ('B01', 'B', 'inside', (2, 2)),
            ('B02', 'B', 'outside', (20, 20)), ('C02', 'C', 'outside', (20, 20))],
            zone_counts={'A': 2, 'B': 1, 'C': 1})
        before = copy.deepcopy(data)
        for method in ('M2', 'M3'):
            with patch.object(metrics, 'feasible_add', wraps=metrics.feasible_add) as gate:
                result = benchmarks.greedy_objective(data, opts, (0, 1), method)
            self.assertTrue(gate.called)
            self.assertEqual(result['status'], 'completed')
            indices = result['selected_indices']
            self.assertEqual(len(indices), len(set(indices)))
            self.assertEqual(Counter(metrics.quota_bucket(data['features'][i], opts) for i in indices),
                             {'A_inside': 2, 'B_inside': 1, 'C_outside': 1})
        for key in ('vectors', 'P', 'corridors', 'overlaps', 'q'):
            np.testing.assert_array_equal(data[key], before[key])
        for key in ('features', 'walks', 'part_sets', 'parts', 'part_cells'):
            self.assertEqual(data[key], before[key])

    def test_overlap_dead_end_is_reported_not_a_partial_completed_set(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('B01', 'B', 'inside', (1, 1)), ('B02', 'B', 'inside', (2, 2))])
        data['corridors'][0, 2:] = .7
        data['corridors'][2:, 0] = .7
        for method in ('M2', 'M3'):
            result = benchmarks.greedy_objective(data, opts, (0, 1), method)
            self.assertEqual(result['status'], 'infeasible')
            self.assertEqual(set(result['selected_indices']), {0, 1})
            self.assertTrue(result.get('reason'))

    def test_seed_pairs_use_common_finite_D_and_ID_order_with_eligibility(self):
        data, opts = fixture([
            ('AZ', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('B01', 'B', 'inside', (2, 2)), ('AA', 'A', 'inside', (4, 0)),
            ('C02', 'C', 'outside', (0, 4))])
        data['eligible_indices'] = {0, 1, 2, 3}
        opts['seed_count'] = 2
        expected = []
        for i in sorted(data['eligible_indices']):
            if data['features'][i]['group'] != 'inside':
                continue
            for j in sorted(data['eligible_indices']):
                if data['features'][j]['group'] != 'outside':
                    continue
                if metrics.feasible_add(data, [i], j, opts['quota'], set(opts['required_strata']), opts):
                    expected.append((metrics.D(data['vectors'][[i, j]].sum(axis=0), data['q']),
                                     data['features'][i]['route_id'], data['features'][j]['route_id'], i, j))
        expected = [(r[-2], r[-1]) for r in sorted(expected)[:2]]
        self.assertEqual([tuple(pair) for pair in benchmarks.seed_pairs(data, opts)], expected)

    def test_all_dead_end_starts_raise_without_returning_a_partial_success(self):
        data, opts = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('B01', 'B', 'inside', (1, 1))])
        data['corridors'][0, 2] = data['corridors'][2, 0] = .7
        for method in ('M2', 'M3'):
            with self.assertRaises(ValueError) as failure:
                benchmarks.select_objective(data, opts, method)
            self.assertTrue(str(failure.exception))
            runs = getattr(failure.exception, 'seed_runs', None)
            self.assertTrue(runs)
            self.assertTrue(all(run['status'] == 'infeasible' for run in runs))

    def test_best_seed_run_is_selected_by_its_own_method_objective(self):
        parts = {'a': (10, [(0, 10)]), 'c': (10, [(1, 10)]),
                 'balanced': (2, [(0, 1), (1, 1)]), 'large': (90, [(0, 90)])}
        data, opts = fixture([
            ('A01', 'A', 'inside', ['a']), ('C01', 'C', 'outside', ['c']),
            ('B01', 'B', 'inside', ['balanced']),
            ('B02', 'B', 'inside', ['large']), ('A02', 'A', 'inside', ['a'])], parts)
        data['corridors'][0, 3] = data['corridors'][3, 0] = .7
        data['corridors'][4, 2] = data['corridors'][2, 4] = .7
        with patch.object(benchmarks, 'seed_pairs', return_value=[(0, 1), (4, 1)]):
            result_D = benchmarks.select_objective(data, opts, 'M2')
            result_coverage = benchmarks.select_objective(data, opts, 'M3')
        self.assertEqual(selected_ids(data, result_D), {'A01', 'C01', 'B01'})
        self.assertEqual(selected_ids(data, result_coverage), {'A02', 'C01', 'B02'})
        self.assertEqual(len(result_D['seed_runs']), 2)
        self.assertEqual(len(result_coverage['seed_runs']), 2)

    def test_equal_final_objectives_use_sorted_route_IDs_not_seed_index(self):
        parts = {'a': (10, [(0, 10)]), 'c': (10, [(1, 10)]),
                 'b': (2, [(0, 1), (1, 1)])}
        data, opts = fixture([
            ('A10', 'A', 'inside', ['a']), ('C01', 'C', 'outside', ['c']),
            ('B10', 'B', 'inside', ['b']), ('B20', 'B', 'inside', ['b']),
            ('A00', 'A', 'inside', ['a'])], parts)
        data['corridors'][0, 3] = data['corridors'][3, 0] = .7
        data['corridors'][4, 2] = data['corridors'][2, 4] = .7
        for method in ('M2', 'M3'):
            with patch.object(benchmarks, 'seed_pairs', return_value=[(0, 1), (4, 1)]):
                result = benchmarks.select_objective(data, opts, method)
            self.assertEqual(selected_ids(data, result), {'A00', 'C01', 'B20'})


if __name__ == '__main__':
    unittest.main()
