"""Scientific protocol checks for the fixed-pool M0 random benchmark."""
import copy
import itertools
import json
from collections import Counter
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from lez import selection_random as random
from lez import selection_metrics as metrics

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_selection_abc import options, toy_abc


def config(n=30):
    return {'valid_samples': n, 'random_seed': 20261102, 'max_attempts': max(n * 20, 100),
            'checkpoint_every': 5}


def small_problem():
    data, opts = toy_abc(), options()
    data['eligible_indices'] = {0, 1, 20, 21, 40, 41}
    opts['quota'] = {'inside': 2, 'outside': 1}
    for bucket in opts['intersection_quota']:
        bucket['count'] = 1
    data['corridors'][0, 20] = data['corridors'][20, 0] = opts['max_corridor_overlap']
    return data, opts


class RandomBaselineTests(unittest.TestCase):
    def test_exact_intersection_quotas_and_no_replacement(self):
        data, opts = toy_abc(), options()
        result = random.generate_samples(data, opts, config())
        for sample in result['samples']:
            self.assertEqual(len(sample['route_ids']), 30)
            self.assertEqual(len(set(sample['route_ids'])), 30)
            self.assertEqual(Counter(r[0] for r in sample['route_ids']), {'A': 10, 'B': 8, 'C': 12})
            ids = [r['route_id'] for r in data['features']]
            self.assertFalse(any(34 <= ids.index(rid) < 40 for rid in sample['route_ids']))
            self.assertEqual(sample['metrics']['inside'], 18)
            self.assertEqual(sample['metrics']['outside'], 12)

    def test_repeated_sets_allowed_and_conditional_uniformity(self):
        data, opts = small_problem()
        result = random.generate_samples(data, opts, config(6000))
        counts = Counter(tuple(sample['route_ids']) for sample in result['samples'])
        allowed = {tuple(data['features'][i]['route_id'] for i in indices)
                   for indices in itertools.product((0, 1), (20, 21), (40, 41))
                   if not random.rejection_reason(data, list(indices), opts)}
        self.assertEqual(set(counts), allowed)
        self.assertEqual(len(allowed), 6)
        self.assertTrue(all(850 < count < 1150 for count in counts.values()))
        self.assertGreater(result['rejections']['overlap'], 0)
        self.assertEqual(result['attempts'], len(result['samples']) + sum(result['rejections'].values()))

    def test_overlap_at_cap_rejected_and_just_below_accepted(self):
        data, opts = small_problem()
        self.assertEqual(random.rejection_reason(data, [0, 20, 40], opts), 'overlap')
        data['corridors'][0, 20] = data['corridors'][20, 0] = np.nextafter(.7, 0)
        self.assertIsNone(random.rejection_reason(data, [0, 20, 40], opts))

    def test_low_material_coverage_is_kept(self):
        data, opts = toy_abc(), options()
        data['P'][:] = 0
        result = random.generate_samples(data, opts, config(2))
        self.assertEqual(len(result['samples']), 2)
        self.assertEqual(result['rejections'], {'overlap': 0, 'required_strata': 0})
        self.assertTrue(all(r['metrics']['material_cells'] == 0 for r in result['samples']))

    def test_seed_repeats_and_different_seed_changes_draws(self):
        data, opts = toy_abc(), options()
        cfg = config()
        first = random.generate_samples(data, opts, cfg)
        self.assertEqual(first, random.generate_samples(data, opts, cfg))
        cfg['random_seed'] += 1
        self.assertNotEqual(first['samples'], random.generate_samples(data, opts, cfg)['samples'])

    def test_json_checkpoint_resume_matches_uninterrupted_run(self):
        data, opts = small_problem()
        cfg, captured = config(), []
        class Interrupted(Exception):
            pass
        def stop(state):
            captured.append(json.loads(json.dumps(state)))
            raise Interrupted()
        with self.assertRaises(Interrupted):
            random.generate_samples(data, opts, cfg, checkpoint=stop)
        resumed = random.generate_samples(data, opts, cfg, state=captured[-1])
        self.assertEqual(resumed, random.generate_samples(data, opts, cfg))

    def test_infeasible_overlap_stops_at_attempt_limit(self):
        data, opts = toy_abc(), options()
        data['corridors'][:] = 1
        cfg = config(2); cfg['max_attempts'] = 7
        state = random.generate_samples(data, opts, cfg)
        self.assertEqual(state['samples'], [])
        self.assertEqual(state['attempts'], 7)
        self.assertEqual(state['rejections']['overlap'], 7)

    def test_insufficient_quota_fails_before_drawing(self):
        data, opts = toy_abc(), options()
        data['eligible_indices'] = set(range(30))
        with self.assertRaisesRegex(ValueError, 'Insufficient candidates'):
            random.generate_samples(data, opts, config())

    def test_asymmetric_overlap_fails(self):
        data, opts = toy_abc(), options()
        data['corridors'][0, 1] = .5
        with self.assertRaisesRegex(ValueError, 'overlap matrix'):
            random.generate_samples(data, opts, config())

    def test_rng_does_not_call_optimizer_or_modify_source_arrays(self):
        data, opts = toy_abc(), options()
        before = {k: v.copy() for k, v in data.items() if isinstance(v, np.ndarray)}
        original_features = copy.deepcopy(data['features'])
        with patch.object(metrics, 'select', side_effect=AssertionError('M0 must not optimize')):
            random.generate_samples(data, opts, config(5))
        for key, value in before.items():
            np.testing.assert_array_equal(value, data[key])
        self.assertEqual(original_features, data['features'])

    def test_metrics_exactly_reuse_published_definitions(self):
        data, opts = toy_abc(), options()
        sample = random.generate_samples(data, opts, config(1))['samples'][0]
        ids = [r['route_id'] for r in data['features']]
        expected = metrics.summary(data, [ids.index(rid) for rid in sample['route_ids']], opts['minimum_cell_fraction'])
        self.assertEqual(sample['metrics'], expected)
        random.validate_baseline(data, opts, {'selected_route_ids': sample['route_ids'], 'metrics': expected})
        changed = copy.deepcopy(expected); changed['unique_rc_length_m'] += 1
        with self.assertRaisesRegex(ValueError, 'baseline metrics'):
            random.validate_baseline(data, opts, {'selected_route_ids': sample['route_ids'], 'metrics': changed})

    def test_tail_counts_handle_ties_zero_and_empty_subset(self):
        samples = [{'metrics': {'D_combined': value}} for value in (.1, .2, .2, .4)]
        result = random.comparison(samples, {'D_combined': .2}, 1e-12)
        self.assertEqual((result['strictly_lower_D_count'], result['tied_D_count']), (1, 2))
        self.assertEqual(result['no_higher_D_fraction'], .75)
        result = random.comparison(samples, {'D_combined': .05}, 1e-12)
        self.assertEqual(result['no_higher_D_count'], 0)
        self.assertEqual(result['empirical_resolution'], .25)
        empty = random.comparison([], {'D_combined': .2}, 1e-12)
        self.assertIsNone(empty['no_higher_D_fraction'])
        self.assertIsNone(empty['D_distribution'])

    def test_complete_1000_is_enforced_before_report_publication(self):
        # A failed run may save a checkpoint, but must not publish latest/manifest.
        data, opts = toy_abc(), options()
        data['corridors'][:] = 1
        check = {'fingerprint': 'a' * 64, 'protocol': config(2), 'options': opts,
                 'baseline': {'selected_route_ids': [], 'metrics': {}}, 'parent': {},
                 'gates': {'routes': {r['route_id']: {} for r in data['walks']}}}
        check['protocol']['max_attempts'] = 3
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(random, 'preflight_random', return_value=check), \
                 patch.object(metrics, 'load_data', return_value=data), \
                 patch.object(random, 'validate_baseline', return_value={}):
                with self.assertRaisesRegex(RuntimeError, 'max_attempts'):
                    random.run_random(tmp, progress=None)
            root = Path(tmp) / 'data/processed/selection_random' / ('a' * 20)
            self.assertTrue((root / 'checkpoint.json').exists())
            self.assertEqual(json.loads((root / 'progress.json').read_text())['status'], 'max_attempts_reached')
            self.assertFalse((root / 'manifest.json').exists())
            self.assertFalse((Path(tmp) / 'reports/selection/latest_random_baseline.json').exists())


if __name__ == '__main__':
    unittest.main()
