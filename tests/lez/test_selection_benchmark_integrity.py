"""Tampering and protocol checks for independent benchmark publication."""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from lez import selection_benchmarks as benchmarks
from lez import selection_metrics as metrics

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_selection_benchmarks import fixture


def protocol():
    return {'schema_version': 1, 'method_version': benchmarks.VERSION,
            'methods': ['M2', 'M3', 'M4', 'M5'],
            'seed_policy': 'shared_D_ranked_inside_outside_pairs_from_selection_config',
            'D_tie_tolerance': 1e-10, 'coverage_tie_tolerance_m': 1e-8,
            'tie_breaker': 'route_ID_only',
            'M2_objective': 'minimum_RC_only_global_D_after_each_addition',
            'M3_objective': 'maximum_marginal_unique_RC_physical_length',
            'saved_methods_policy': 'verify_history_replay_swaps_recompute_metrics',
            'secondary_length_window_fraction': .1,
            'material_cell_count_is_filter': False, 'M2_M3_swaps': False,
            'M1_status': 'allocation_rule_not_finalized'}


def saved_bundle(root):
    """A genuine feasible M4 set and one improving positional swap into M5."""
    data, options = fixture([
        ('A01', 'A', 'inside', (8, 0)), ('C01', 'C', 'outside', (0, 2)),
        ('B01', 'B', 'inside', (6, 4)), ('B02', 'B', 'inside', (0, 2))],
        q=[.6, .4] + [0.] * 10)
    options.update(seed_count=1, swap_min_improvement=1e-9,
                   minimum_quantile_diversity_retained=.9,
                   max_domain_D_worsening=.1)
    seed = list(benchmarks.seed_pairs(data, options)[0])
    assert set(seed) == {1, 2}
    ids = lambda selected: [data['features'][i]['route_id'] for i in selected]
    selected = seed + [0]
    before = metrics.summary(data, selected, options['minimum_cell_fraction'])
    after_indices = [3 if i == 2 else i for i in selected]
    after = metrics.summary(data, after_indices, options['minimum_cell_fraction'])
    history = [{'round': 0, 'seed': ids(seed), 'selected_after': ids(seed),
                'set_metrics': metrics.summary(data, seed, options['minimum_cell_fraction'])},
               {'round': 3, 'chosen': 'A01', 'selected_before': ids(seed),
                'selected_after': ids(selected), 'set_metrics': before}]
    baseline = {'before_swaps': before, 'metrics': after, 'accepted_swaps': 1,
                'selected_route_ids': ids(after_indices)}
    seeds = [{'seed': ids(seed), **before}]
    swaps = [{'round': 1, 'removed': 'B01', 'added': 'B02',
              'D_before': before['D_combined'], 'D_after': after['D_combined'],
              'improvement': before['D_combined'] - after['D_combined']}]
    write_bundle(root, history, seeds, swaps)
    return data, options, baseline, history, seeds, swaps


def write_bundle(root, history, seeds, swaps):
    root = Path(root)
    (root / 'selection_history.json').write_text(json.dumps(history))
    (root / 'seed_runs.json').write_text(json.dumps(seeds))
    with (root / 'swaps.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['round', 'removed', 'added',
                                                     'D_before', 'D_after', 'improvement'])
        writer.writeheader()
        writer.writerows(swaps)


class BenchmarkProtocolTests(unittest.TestCase):
    def test_independent_method_subset_has_canonical_output_order(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'protocol.json'
            path.write_text(json.dumps(protocol()))
            _, wanted, _ = benchmarks._protocol(root, 'protocol.json', ['M5', 'M2'])
            self.assertEqual(wanted, ['M2', 'M5'])
            _, wanted, _ = benchmarks._protocol(root, 'protocol.json', ['M3'])
            self.assertEqual(wanted, ['M3'])

    def test_unsupported_methods_and_protocol_changes_are_rejected(self):
        cases = [('schema_version', 2), ('seed_policy', 'pick_new_seeds_each_run'),
                 ('M2_objective', 'weighted_C1_C7'), ('M2_M3_swaps', True),
                 ('material_cell_count_is_filter', True),
                 ('D_tie_tolerance', -1), ('D_tie_tolerance', float('nan')),
                 ('coverage_tie_tolerance_m', True),
                 ('coverage_tie_tolerance_m', float('inf')),
                 ('secondary_length_window_fraction', 0),
                 ('secondary_length_window_fraction', 1),
                 ('methods', ['M1']), ('methods', ['M2', 'M2']), ('methods', [])]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'protocol.json'
            for key, value in cases:
                with self.subTest(key=key, value=value):
                    cfg = protocol()
                    cfg[key] = value
                    path.write_text(json.dumps(cfg))
                    with self.assertRaises(ValueError):
                        benchmarks._protocol(root, 'protocol.json')


class SavedMethodIntegrityTests(unittest.TestCase):
    def test_recovers_M4_and_replays_M5_with_recomputed_metrics(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, baseline, *_ = saved_bundle(root)
            original = copy.deepcopy(baseline)
            result = benchmarks.recover_saved_methods(data, options, baseline, root)
            self.assertEqual(result['M4']['metrics'], baseline['before_swaps'])
            self.assertEqual(result['M5']['metrics'], baseline['metrics'])
            self.assertEqual(result['M5']['selected_route_ids'], baseline['selected_route_ids'])
            self.assertEqual(result['M4']['swaps'], 0)
            self.assertEqual(result['M5']['swaps'], 1)
            self.assertFalse(result['M5']['provenance']['weighted_algorithm_rerun'])
            self.assertTrue(result['M5']['provenance']['metrics_recomputed'])
            self.assertEqual(baseline, original)

    def test_tampered_history_metric_or_transition_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, baseline, history, seeds, swaps = saved_bundle(root)
            corruptions = []
            bad = copy.deepcopy(history)
            bad[-1]['set_metrics']['D_combined'] += .001
            corruptions.append(bad)
            bad = copy.deepcopy(history)
            bad[-1]['selected_before'] = list(reversed(bad[-1]['selected_before']))
            corruptions.append(bad)
            bad = copy.deepcopy(history)
            bad[-1]['chosen'] = 'B02'
            corruptions.append(bad)
            bad = copy.deepcopy(history)
            bad[0]['round'] = 2
            corruptions.append(bad)
            for number, bad in enumerate(corruptions):
                with self.subTest(corruption=number):
                    write_bundle(root, bad, seeds, swaps)
                    with self.assertRaises(ValueError):
                        benchmarks.recover_saved_methods(data, options, baseline, root)

    def test_changed_saved_start_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, baseline, history, seeds, swaps = saved_bundle(root)
            seeds[0]['seed'].reverse()
            write_bundle(root, history, seeds, swaps)
            with self.assertRaisesRegex(ValueError, 'starts'):
                benchmarks.recover_saved_methods(data, options, baseline, root)

    def test_saved_winner_start_metrics_must_match_reconstructed_M4(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, baseline, history, seeds, swaps = saved_bundle(root)
            # Matching D alone does not authenticate the other stored fields.
            seeds[0]['unique_rc_length_m'] += 1
            write_bundle(root, history, seeds, swaps)
            with self.assertRaises(ValueError):
                benchmarks.recover_saved_methods(data, options, baseline, root)

    def test_tampered_swap_transition_metric_or_improvement_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, baseline, history, seeds, swaps = saved_bundle(root)
            for field, value in [('round', 2), ('removed', 'not-selected'),
                                 ('added', 'A01'), ('D_before', 0),
                                 ('D_after', 0), ('improvement', 1)]:
                with self.subTest(field=field):
                    changed = copy.deepcopy(swaps)
                    changed[0][field] = value
                    write_bundle(root, history, seeds, changed)
                    with self.assertRaises(ValueError):
                        benchmarks.recover_saved_methods(data, options, baseline, root)

    def test_tampered_baseline_metrics_count_or_final_order_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, baseline, *_ = saved_bundle(root)
            corruptions = []
            bad = copy.deepcopy(baseline)
            bad['before_swaps']['unique_rc_length_m'] += 1
            corruptions.append(bad)
            bad = copy.deepcopy(baseline)
            bad['metrics']['D_combined'] += .001
            corruptions.append(bad)
            bad = copy.deepcopy(baseline)
            bad['accepted_swaps'] = 0
            corruptions.append(bad)
            bad = copy.deepcopy(baseline)
            bad['selected_route_ids'].reverse()
            corruptions.append(bad)
            for number, bad in enumerate(corruptions):
                with self.subTest(corruption=number):
                    with self.assertRaises(ValueError):
                        benchmarks.recover_saved_methods(data, options, bad, root)

    def test_saved_M5_swap_must_retain_original_domain_safeguard(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, baseline, *_ = saved_bundle(root)
            # This swap lowers global D but worsens inside-domain D slightly.
            options['max_domain_D_worsening'] = 0
            with self.assertRaisesRegex(ValueError, 'M5-specific safeguards'):
                benchmarks.recover_saved_methods(data, options, baseline, root)


class CheckpointIntegrityTests(unittest.TestCase):
    def checkpoint(self, root):
        data, options = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('B01', 'B', 'inside', (1, 1))])
        result = benchmarks.greedy_objective(data, options, (0, 1), 'M2')
        history = result.pop('history')
        history_path = Path(root) / 'history.json'
        history_path.write_text(json.dumps(history))
        result.update(method='M2', history_path='work/history.json',
                      selected_route_ids=[data['features'][i]['route_id']
                                          for i in result['selected_indices']],
                      history_sha256=benchmarks.file_hash(history_path))
        record = {'fingerprint': 'a' * 64, 'result_hash': benchmarks.digest(result),
                  'result': result}
        path = Path(root) / 'checkpoint.json'
        path.write_text(json.dumps(record))
        return data, options, result, record, path

    def test_valid_checkpoint_recomputes_metrics_and_returns_result(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, result, _, path = self.checkpoint(root)
            loaded = benchmarks._read_checkpoint(path, 'a' * 64, data, options, root)
            self.assertEqual(loaded, result)

    def test_wrong_fingerprint_or_unresigned_result_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, _, record, path = self.checkpoint(root)
            with self.assertRaises(ValueError):
                benchmarks._read_checkpoint(path, 'b' * 64, data, options, root)
            record['result']['metrics']['D_combined'] += .001
            path.write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                benchmarks._read_checkpoint(path, 'a' * 64, data, options, root)

    def test_resigned_but_invalid_metrics_or_ID_alignment_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, _, record, path = self.checkpoint(root)
            corruptions = []
            changed = copy.deepcopy(record)
            changed['result']['metrics']['unique_rc_length_m'] += 1
            corruptions.append(changed)
            changed = copy.deepcopy(record)
            changed['result']['selected_indices'].reverse()
            corruptions.append(changed)
            changed = copy.deepcopy(record)
            changed['result']['status'] = 'failed'
            corruptions.append(changed)
            for number, changed in enumerate(corruptions):
                with self.subTest(corruption=number):
                    changed['result_hash'] = benchmarks.digest(changed['result'])
                    path.write_text(json.dumps(changed))
                    with self.assertRaises(ValueError):
                        benchmarks._read_checkpoint(path, 'a' * 64, data, options, root)

    def test_changed_or_missing_history_file_is_not_a_valid_cache(self):
        with tempfile.TemporaryDirectory() as root:
            data, options, _, _, path = self.checkpoint(root)
            history = Path(root) / 'history.json'
            history.write_text('[]')
            with self.assertRaises(ValueError):
                benchmarks._read_checkpoint(path, 'a' * 64, data, options, root)
            history.unlink()
            with self.assertRaises((ValueError, OSError)):
                benchmarks._read_checkpoint(path, 'a' * 64, data, options, root)


class BenchmarkOrchestrationTests(unittest.TestCase):
    def problem(self, root):
        data, options = fixture([
            ('A01', 'A', 'inside', (5, 0)), ('C01', 'C', 'outside', (0, 5)),
            ('B01', 'B', 'inside', (1, 1)), ('B02', 'B', 'inside', (20, 0))])
        baseline = {'selected_route_ids': ['A01', 'C01', 'B01'],
                    'metrics': metrics.summary(data, [0, 1, 2]),
                    'snapshot_utc': '2026-10-01T00:00:00Z',
                    'missing_cells_in_entire_pool': [['A', 'RC1']]}
        check = {'fingerprint': 'a' * 64, 'methods': ['M2', 'M3'],
                 'options': options, 'baseline': baseline, 'parent': {},
                 'config_path': 'work/config/selection_benchmarks.json',
                 'protocol': protocol(), 'runtime': {'python': 'test', 'numpy': 'test'},
                 'input_hashes': {}, '_code_paths': {}, 'code_hashes': {},
                 'gates': {'routes': {f['route_id']: {'pre_survey_admissible': True}
                                      for f in data['features']}}}
        # A marker representing the existing chosen routes must remain exact.
        marker = Path(root) / 'reports/selection/latest_selection_30.json'
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps(baseline))
        return data, check, marker

    def test_completed_bundle_reuses_cache_without_optimizing_again(self):
        with tempfile.TemporaryDirectory() as root:
            data, check, marker = self.problem(root)
            original = marker.read_bytes()
            with patch.object(benchmarks, '_prepare', return_value=check), \
                 patch.object(metrics, 'load_data', return_value=data):
                report = benchmarks.run_benchmarks(root, output_root='isolated')
                self.assertEqual(report['new_methods'], ['M2', 'M3'])
                with patch.object(benchmarks, 'select_objective', side_effect=AssertionError('cache optimized again')):
                    cached = benchmarks.run_benchmarks(root, output_root='isolated')
            self.assertEqual(cached['invocation']['new_methods'], [])
            self.assertEqual(cached['invocation']['cached_methods'], ['M2', 'M3'])
            self.assertEqual(marker.read_bytes(), original)
            self.assertFalse((Path(root) / 'reports/selection/latest_benchmarks.json').exists())
            self.assertTrue((Path(root) / 'isolated' / ('a' * 20) / 'manifest.json').exists())
            progress = Path(root) / 'isolated' / ('a' * 20) / 'progress.json'
            self.assertEqual(json.loads(progress.read_text())['status'], cached['status'])

    def test_custom_config_is_persisted_and_used_by_status(self):
        with tempfile.TemporaryDirectory() as root:
            data, check, _ = self.problem(root)
            check['config_path'] = 'work/config/custom_benchmarks.json'
            with patch.object(benchmarks, '_prepare', return_value=check) as prepare, \
                 patch.object(metrics, 'load_data', return_value=data):
                report = benchmarks.run_benchmarks(root, config_path=check['config_path'])
                self.assertEqual(report['config_path'], check['config_path'])
                prepare.reset_mock()
                current = benchmarks.benchmark_status(root)
                self.assertEqual(current, report)
                self.assertEqual(prepare.call_args.args[1], check['config_path'])

    def test_corrupt_completed_output_is_rejected_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as root:
            data, check, _ = self.problem(root)
            with patch.object(benchmarks, '_prepare', return_value=check), \
                 patch.object(metrics, 'load_data', return_value=data):
                benchmarks.run_benchmarks(root, output_root='isolated')
                history = Path(root) / 'isolated' / ('a' * 20) / 'history/M2.json'
                history.write_text('corrupted cached output')
                with self.assertRaisesRegex(ValueError, 'inconsistent'):
                    benchmarks.run_benchmarks(root, output_root='isolated')
                self.assertEqual(history.read_text(), 'corrupted cached output')

    def test_interrupt_preserves_completed_method_and_resume_runs_only_unfinished_one(self):
        with tempfile.TemporaryDirectory() as root:
            data, check, marker = self.problem(root)
            original = marker.read_bytes()
            real_selector = benchmarks.select_objective
            calls = []
            def stop_at_M3(data, options, method, progress=None):
                calls.append(method)
                if method == 'M3':
                    raise KeyboardInterrupt()
                return real_selector(data, options, method, progress)
            with patch.object(benchmarks, '_prepare', return_value=check), \
                 patch.object(metrics, 'load_data', return_value=data):
                with patch.object(benchmarks, 'select_objective', side_effect=stop_at_M3):
                    with self.assertRaises(KeyboardInterrupt):
                        benchmarks.run_benchmarks(root)
                directory = Path(root) / 'data/processed/selection_benchmarks' / ('a' * 20)
                self.assertTrue((directory / 'checkpoints/M2.json').exists())
                self.assertFalse((directory / 'checkpoints/M3.json').exists())
                self.assertFalse((directory / 'manifest.json').exists())
                self.assertFalse((Path(root) / 'reports/selection/latest_benchmarks.json').exists())
                self.assertEqual(json.loads((directory / 'progress.json').read_text())['status'], 'interrupted')
                with patch.object(benchmarks, 'select_objective', wraps=real_selector) as selector:
                    resumed = benchmarks.run_benchmarks(root)
                self.assertEqual([call.args[2] for call in selector.call_args_list], ['M3'])
            self.assertEqual(resumed['cached_methods'], ['M2'])
            self.assertEqual(resumed['new_methods'], ['M3'])
            self.assertTrue((directory / 'manifest.json').exists())
            self.assertEqual(marker.read_bytes(), original)

    def test_failed_method_keeps_other_result_without_publishing_complete_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            data, check, _ = self.problem(root)
            real_selector = benchmarks.select_objective
            def fail_M2(data, options, method, progress=None):
                if method == 'M2':
                    raise benchmarks.NoCompleteStart(method, [{
                        'start': 1, 'seed': ['A01', 'C01'], 'status': 'infeasible',
                        'reason': 'synthetic_dead_end'}])
                return real_selector(data, options, method, progress)
            with patch.object(benchmarks, '_prepare', return_value=check), \
                 patch.object(metrics, 'load_data', return_value=data), \
                 patch.object(benchmarks, 'select_objective', side_effect=fail_M2):
                report = benchmarks.run_benchmarks(root)
            directory = Path(root) / 'data/processed/selection_benchmarks' / ('a' * 20)
            self.assertEqual(report['status'], 'partial')
            self.assertEqual(report['unresolved'], ['M2'])
            self.assertEqual(report['methods']['M3']['status'], 'completed')
            self.assertTrue((directory / 'checkpoints/M3.json').exists())
            self.assertFalse((directory / 'manifest.json').exists())
            self.assertFalse((Path(root) / 'reports/selection/latest_benchmarks.json').exists())

    def test_input_change_before_checkpoint_prevents_publication(self):
        with tempfile.TemporaryDirectory() as root:
            data, check, _ = self.problem(root)
            with patch.object(benchmarks, '_prepare', return_value=check), \
                 patch.object(metrics, 'load_data', return_value=data), \
                 patch.object(benchmarks, '_recheck_inputs', side_effect=ValueError('Input changed during run')):
                with self.assertRaisesRegex(ValueError, 'Input changed'):
                    benchmarks.run_benchmarks(root)
            directory = Path(root) / 'data/processed/selection_benchmarks' / ('a' * 20)
            self.assertFalse((directory / 'manifest.json').exists())
            self.assertFalse((directory / 'checkpoints/M2.json').exists())
            self.assertFalse((Path(root) / 'reports/selection/latest_benchmarks.json').exists())


if __name__ == '__main__':
    unittest.main()
