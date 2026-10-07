"""Regression checks for exact ABC × LEZ quotas and independent overlays."""
import copy
from collections import Counter
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

# When installed, imports the project module normally. Staging can override it.
import lez.selection_metrics as metrics


def toy_abc():
    cells = [(zone, rc) for zone in 'ABC' for rc in metrics.RC]
    features, walks, vectors, domains, parts, part_sets, part_cells = [], [], [], {'inside': [], 'outside': []}, {}, [], {}
    for zone in 'ABC':
        for n in range(20):
            group = 'inside' if zone == 'A' or zone == 'B' and n < 14 else 'outside'
            rc = metrics.RC[n % 4]
            index = cells.index((zone, rc)); vector = np.zeros(12); vector[index] = 100. + n
            rid = f'{zone}{n + 1:02d}'; pid = f'part/{rid}'
            features.append({'route_id': rid, 'sampling_zone': zone, 'stratum_id': zone, 'group': group, 'rc_target': rc})
            walks.append({'route_id': rid, 'length_m': float(vector.sum())})
            vectors.append(vector); parts[pid] = {'length_m': float(vector.sum())}; part_sets.append({pid}); part_cells[pid] = [(index, float(vector.sum()))]
            for g in domains: domains[g].append(vector if g == group else np.zeros(12))
    vectors = np.array(vectors); X = np.linspace(0, 1, 60)[:, None]
    lengths = np.array([1000. + i * 10 for i in range(12)])
    dl = {'inside': np.array([v if cell[0] in 'AB' else 0. for cell, v in zip(cells, lengths)]), 'outside': np.array([v if cell[0] == 'C' else 0. for cell, v in zip(cells, lengths)])}
    # B has both groups: the denominator must follow explicit overlay, too.
    dl['outside'][4:8] = lengths[4:8] * .3; dl['inside'][4:8] = lengths[4:8] * .7
    return {'cells': cells, 'features': features, 'walks': walks, 'vectors': vectors, 'q': lengths/lengths.sum(), 'network_lengths': lengths,
            'P': vectors/vectors.sum(axis=1)[:, None], 'X': X, 'distances': np.abs(X-X.T), 'bins': [{('feature', i//15)} for i in range(60)],
            'overlaps': np.eye(60), 'corridors': np.eye(60), 'parts': parts, 'part_sets': part_sets, 'part_cells': part_cells,
            'domain_vectors': {g: np.array(v) for g,v in domains.items()}, 'domain_lengths': dl}


def options():
    return {'quota': {'inside': 18, 'outside': 12}, 'required_strata': ['A', 'B', 'C'],
            'intersection_quota': [{'name': 'A_inside', 'group': 'inside', 'sampling_zones': ['A'], 'count': 10}, {'name': 'B_inside', 'group': 'inside', 'sampling_zones': ['B'], 'count': 8}, {'name': 'C_outside', 'group': 'outside', 'sampling_zones': ['C'], 'count': 12}],
            'weights': {'C1': 25, 'C2': 15, 'C3': 15, 'C4': 15, 'C5': 10, 'C6': 10, 'C7': 10},
            'minimum_cell_fraction': .3, 'tie_tolerance': 1e-10, 'seed_count': 4, 'max_corridor_overlap': .7,
            'max_swap_rounds': 10, 'swap_min_improvement': 1e-9, 'minimum_quantile_diversity_retained': .9, 'max_domain_D_worsening': .02}


class ABCSelectionTests(unittest.TestCase):
    def test_greedy_and_swaps_preserve_joint_quotas(self):
        data, config = toy_abc(), options()
        selected, history, swaps, seeds = metrics.select(data, config)
        result = metrics.summary(data, selected)
        self.assertEqual((result['inside'], result['outside']), (18, 12))
        self.assertEqual(result['zone_group_counts']['A']['inside'], 10)
        self.assertEqual(result['zone_group_counts']['B']['inside'], 8)
        self.assertEqual(result['zone_group_counts']['C']['outside'], 12)
        self.assertEqual(set(result['represented_primary_strata']), {'A', 'B', 'C'})
        self.assertEqual(len(set(selected)), 30)
        self.assertEqual(selected, metrics.select(data, config)[0])
        for step in history:
            features = {r['route_id']:r for r in data['features']}
            count = Counter(metrics.quota_bucket(features[rid], config) for rid in step['selected_after'])
            self.assertLessEqual(count['A_inside'], 10); self.assertLessEqual(count['B_inside'], 8); self.assertLessEqual(count['C_outside'], 12); self.assertEqual(count['outside_remaining'], 0)
        self.assertTrue(all(s['D_after'] < s['D_before'] for s in swaps))

    def test_cross_zone_same_LEZ_replacement_is_rejected(self):
        data, config = toy_abc(), options(); selected = metrics.select(data, config)[0]
        old = next(i for i in selected if data['features'][i]['sampling_zone'] == 'A')
        others = [i for i in selected if i != old]
        b = next(i for i,r in enumerate(data['features']) if i not in selected and r['sampling_zone']=='B' and r['group']=='inside')
        self.assertFalse(metrics.feasible_add(data, others, b, config['quota'], set(config['required_strata']), config))
        a = next(i for i,r in enumerate(data['features']) if i not in selected and r['sampling_zone']=='A' and r['group']=='inside')
        self.assertTrue(metrics.feasible_add(data, others, a, config['quota'], set(config['required_strata']), config))

    def test_explicit_LEZ_domain_not_inferred_from_ABC(self):
        data, config = toy_abc(), options(); selected = metrics.select(data, config)[0]
        outside_B = next(i for i,r in enumerate(data['features']) if r['sampling_zone']=='B' and r['group']=='outside')
        vector, denominator = metrics.domain_arrays(data, [outside_B], 'outside')
        self.assertGreater(vector.sum(), 0); self.assertGreater(denominator[4:8].sum(), 0)
        vector_inside, _ = metrics.domain_arrays(data, [outside_B], 'inside')
        self.assertEqual(vector_inside.sum(), 0)
        summary = metrics.summary(data, selected)
        expected = metrics.D(data['domain_vectors']['outside'][selected].sum(axis=0), denominator/denominator.sum())
        self.assertAlmostEqual(summary['D_by_domain']['outside'], expected)

    def test_missing_stratum_cannot_be_filled_after_slots_exhausted(self):
        data, config = toy_abc(), options()
        # Fill outside slots with B routes in a synthetic pool; C must still appear.
        for i in range(20,40): data['features'][i]['group'] = 'outside'
        selected = list(range(10)) + list(range(20,31))
        self.assertFalse(metrics.feasible_add(data, selected, 31, config['quota'], {'A','B','C'}, config))

    def test_AB_outside_candidates_cannot_use_C_outside_slots(self):
        data, config = toy_abc(), options()
        b_outside = next(i for i,r in enumerate(data['features']) if r['sampling_zone']=='B' and r['group']=='outside')
        self.assertFalse(metrics.feasible_add(data, [0], b_outside, config['quota'], set(config['required_strata']), config))

    def test_overlapping_intersection_quotas_are_invalid(self):
        config = options(); config['intersection_quota'][1]['sampling_zones'] = ['A','B']
        with self.assertRaisesRegex(ValueError, 'disjoint'): metrics.quota_buckets(config)

    def test_no_feasible_seed_is_reported(self):
        data, config = toy_abc(), options(); config['intersection_quota'][1]['count'] = 19
        with self.assertRaises(ValueError): metrics.select(data, config)


if __name__ == '__main__': unittest.main()
