"""Independent M2/M3 objectives and verified saved M4/M5 on frozen GIS inputs.

Uses ordinary Python/NumPy. No QGIS startup, HTTP, new field observations,
baseline edits, or implicit C1-C7 objective in M2/M3. M1 remains unspecified.
"""
from __future__ import annotations

if __package__ in (None, ''):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'lez'

import argparse
import copy
import fcntl
import json
import math
import platform
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from . import selection_metrics as metrics
from . import selection_random as shared
from .common import (WORK, atomic_bytes, atomic_json, cached_manifest,
                     commit_manifest, digest, file_hash, input_path, now,
                     relative, write_csv)

METHODS = ('M2', 'M3', 'M4', 'M5')
VERSION = 'fixed_pool_objective_benchmarks_v1'


class NoCompleteStart(ValueError):
    def __init__(self, method, runs):
        super().__init__(f'{method}: không khởi đầu nào tìm được bộ đủ quota; không kết luận bài toán vô nghiệm.')
        self.seed_runs = runs


def _close(actual, expected, name='value'):
    """Compare recomputed/canonical structures without hiding changed fields."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError('Different fields: ' + name)
        for key in expected:
            _close(actual[key], expected[key], name + '.' + key)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError('Different sequence: ' + name)
        for i, value in enumerate(expected):
            _close(actual[i], value, f'{name}[{i}]')
    elif isinstance(expected, float):
        if (not isinstance(actual, (int, float)) or not math.isfinite(actual)
                or not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-10)):
            raise ValueError('Different metric: ' + name)
    elif actual != expected:
        raise ValueError('Different value: ' + name)


def _can_add(data, selected, candidate, options):
    if not metrics.feasible_add(data, selected, candidate, options['quota'],
                                set(options['required_strata']), options):
        return False
    return not selected or not np.any(
        data['corridors'][candidate, selected] >= options['max_corridor_overlap'])


def _validate_set(data, selected, options):
    target = sum(options['quota'].values())
    if len(selected) != target or len(set(selected)) != target:
        raise ValueError('The selected set is incomplete or contains duplicate routes')
    allowed = data.get('eligible_indices', set(range(len(data['features']))))
    if not set(selected).issubset(allowed):
        raise ValueError('Selected route is not eligible')
    counts = Counter(metrics.quota_bucket(data['features'][i], options) for i in selected)
    if any(counts[name] != b['count'] for name, b in metrics.quota_buckets(options).items()):
        raise ValueError('Exact zone x LEZ quota is not satisfied')
    reason = shared.rejection_reason(data, selected, options)
    if reason:
        raise ValueError('Common hard constraint failed: ' + reason)
    result = metrics.summary(data, selected, options['minimum_cell_fraction'])
    if result['D_combined'] is None or not math.isfinite(result['D_combined']):
        raise ValueError('RC traversal denominator must be positive')
    return result


def seed_pairs(data, options):
    """Same finite D-ranked start policy as M4/M5, with explicit overlap gating."""
    count = options['seed_count']
    if type(count) is not int or count < 1:
        raise ValueError('seed_count must be a positive integer')
    allowed = data.get('eligible_indices', set(range(len(data['features']))))
    inside = [i for i, f in enumerate(data['features']) if i in allowed and f['group'] == 'inside']
    outside = [i for i, f in enumerate(data['features']) if i in allowed and f['group'] == 'outside']
    candidates = []
    for i in inside:
        for j in outside:
            if not _can_add(data, [i], j, options):
                continue
            value = metrics.D(data['vectors'][[i, j]].sum(axis=0), data['q'])
            if value is not None and math.isfinite(value):
                candidates.append((value, data['features'][i]['route_id'],
                                   data['features'][j]['route_id'], i, j))
    return [(i, j) for _, _, _, i, j in sorted(candidates)[:count]]


def _rc_part_lengths(data):
    # Overlay lengths omit connectors; never substitute full part/traversal length.
    return {pid: float(sum(length for _, length in cells))
            for pid, cells in data['part_cells'].items()}


def greedy_objective(data, options, seed, method):
    """Complete one start. M2 minimizes new D; M3 maximizes unique RC gain."""
    if method not in ('M2', 'M3'):
        raise ValueError('Expected M2 or M3')
    selected, history = [], []
    target = sum(options['quota'].values())

    def fail(reason):
        return {'status': 'infeasible', 'selected_indices': selected.copy(),
                'history': history, 'reason': reason}

    for i in seed:
        if not 0 <= i < len(data['features']) or not _can_add(data, selected, i, options):
            return fail('invalid_or_incompatible_seed')
        selected.append(i)
    if not selected or len(selected) > target:
        return fail('invalid_seed_size')
    vector = data['vectors'][selected].sum(axis=0)
    if metrics.D(vector, data['q']) is None:
        return fail('seed_has_no_RC_length')
    covered = set().union(*(data['part_sets'][i] for i in selected))
    lengths = _rc_part_lengths(data) if method == 'M3' else {}
    ids = lambda indices: [data['features'][i]['route_id'] for i in indices]
    history.append({'round': len(selected), 'selected_after': ids(selected),
                    'seed': ids(selected), 'D': metrics.D(vector, data['q'])})
    while len(selected) < target:
        old_D = metrics.D(vector, data['q'])
        rows = []
        for i in range(len(data['features'])):
            if i in selected or not _can_add(data, selected, i, options):
                continue
            new_D = metrics.D(vector + data['vectors'][i], data['q'])
            gain = (sum(lengths.get(pid, 0.0) for pid in sorted(data['part_sets'][i] - covered))
                    if method == 'M3' else None)
            rows.append({'candidate_index': i, 'route_id': data['features'][i]['route_id'],
                         'D_after': new_D, 'delta_D': old_D - new_D,
                         'new_unique_RC_length_m': gain,
                         'objective_value': new_D if method == 'M2' else gain})
        if not rows:
            return fail('no_remaining_candidate_satisfies_common_constraints')
        best = (min if method == 'M2' else max)(r['objective_value'] for r in rows)
        tolerance = (options['tie_tolerance'] if method == 'M2'
                     else options.get('coverage_tie_tolerance_m', 1e-8))
        tied = [r for r in rows if abs(r['objective_value'] - best) <= tolerance]
        chosen = min(tied, key=lambda r: r['route_id'])
        i = chosen['candidate_index']
        previous = ids(selected)
        selected.append(i)
        vector = vector + data['vectors'][i]
        covered.update(data['part_sets'][i])
        history.append({'round': len(selected), 'selected_before': previous,
                        'selected_after': ids(selected), 'chosen': chosen['route_id'],
                        'D': chosen['D_after'], 'delta_D': chosen['delta_D'],
                        'new_unique_RC_length_m': chosen['new_unique_RC_length_m'],
                        'candidates': rows, 'tie_count': len(tied)})
    return {'status': 'completed', 'selected_indices': selected,
            'history': history, 'metrics': _validate_set(data, selected, options)}


def select_objective(data, options, method, progress=None):
    """Finite multiple starts; no swap, criterion weights, or hidden D tie for M3."""
    if method not in ('M2', 'M3'):
        raise ValueError('Expected M2 or M3')
    runs, completed = [], []
    for n, seed in enumerate(seed_pairs(data, options), 1):
        result = greedy_objective(data, options, seed, method)
        record = {k: v for k, v in result.items() if k != 'history'}
        record.update(start=n, seed=[data['features'][i]['route_id'] for i in seed],
                      selected_route_ids=[data['features'][i]['route_id']
                                          for i in result['selected_indices']])
        runs.append(record)
        if result['status'] == 'completed':
            completed.append((n, result))
        if progress:
            progress(f"{method}: khởi đầu {n}, {result['status']}")
    if not completed:
        raise NoCompleteStart(method, runs)
    key = 'D_combined' if method == 'M2' else 'unique_rc_length_m'
    best_value = (min if method == 'M2' else max)(r['metrics'][key] for _, r in completed)
    tolerance = (options['tie_tolerance'] if method == 'M2'
                 else options.get('coverage_tie_tolerance_m', 1e-8))
    tied = [(n, r) for n, r in completed if abs(r['metrics'][key] - best_value) <= tolerance]
    n, result = min(tied, key=lambda item: tuple(sorted(
        data['features'][i]['route_id'] for i in item[1]['selected_indices'])))
    return {**result, 'seed_runs': runs, 'chosen_start': n,
            'objective': key, 'objective_direction': 'min' if method == 'M2' else 'max'}


def _protocol(work, config_path=None, methods=None):
    path = (input_path(work, config_path) if config_path else
            Path(work) / 'config/selection_benchmarks.json')
    cfg = json.loads(path.read_text())
    fixed = {'schema_version': 1, 'method_version': VERSION,
             'seed_policy': 'shared_D_ranked_inside_outside_pairs_from_selection_config',
             'tie_breaker': 'route_ID_only',
             'M2_objective': 'minimum_RC_only_global_D_after_each_addition',
             'M3_objective': 'maximum_marginal_unique_RC_physical_length',
             'saved_methods_policy': 'verify_history_replay_swaps_recompute_metrics',
             'material_cell_count_is_filter': False, 'M2_M3_swaps': False}
    if any(cfg.get(k) != v for k, v in fixed.items()):
        raise ValueError('Unsupported benchmark protocol')
    for key in ('D_tie_tolerance', 'coverage_tie_tolerance_m'):
        value = cfg[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError('Expected a finite nonnegative tolerance: ' + key)
    if not 0 < cfg['secondary_length_window_fraction'] < 1:
        raise ValueError('Invalid descriptive length window')
    wanted = cfg['methods'] if methods is None else methods
    if (not isinstance(wanted, (list, tuple)) or not wanted or
            len(set(wanted)) != len(wanted) or set(wanted) - set(METHODS)):
        raise ValueError('Choose distinct M2/M3/M4/M5 methods; M1 allocation rule is not finalized')
    return cfg, [m for m in METHODS if m in wanted], path


def _prepare(work, config_path=None, methods=None):
    work = Path(work).resolve()
    cfg, wanted, cfg_path = _protocol(work, config_path, methods)
    # This shared preflight needs frozen inputs/gates, not any completed M0 run.
    check = shared.preflight_random(work)
    opts = copy.deepcopy(check['options'])
    if opts['tie_tolerance'] != cfg['D_tie_tolerance']:
        raise ValueError('D tolerance must match the shared selection configuration')
    opts['coverage_tie_tolerance_m'] = cfg['coverage_tie_tolerance_m']
    baseline = check['baseline']
    baseline_dir = input_path(work, baseline['paths']['directory'])
    canonical = json.loads((baseline_dir / 'manifest.json').read_text())['report']
    if input_path(work, canonical['source_bundle']) != input_path(work, check['parent']['paths']['directory']):
        raise ValueError('Baseline/gates belong to a different candidate bundle')
    if (canonical['policy_version'] != check['parent']['policy_version'] or
            canonical['scope'] != check['parent']['scope']):
        raise ValueError('Candidate and baseline policy/scope differ')
    if (canonical['scope'] != check['gates']['summary']['scope'] or
            canonical['snapshot_utc'] != check['gates']['summary']['snapshot_utc']):
        raise ValueError('Baseline scope/snapshot differs from cached geometry gates')
    for key in ('before_swaps', 'accepted_swaps', 'method_version', 'policy_version',
                'snapshot_utc', 'quota', 'intersection_quota', 'scope', 'source_bundle',
                'missing_cells_in_entire_pool', 'network_rc_denominator_m'):
        _close(baseline[key], canonical[key], 'baseline.' + key)
    hashes = dict(check['input_hashes'])
    hashes[relative(cfg_path, work)] = file_hash(cfg_path)
    if set(wanted) & {'M4', 'M5'}:
        for name in ('selection_history.json', 'swaps.csv', 'seed_runs.json', 'report.json'):
            path = baseline_dir / name
            hashes[relative(path, work)] = file_hash(path)
    names = ('selection_benchmarks.py', 'selection_random.py', 'selection_metrics.py',
             'selection_30.py', 'common.py', 'graph.py')
    code_paths = {name: Path(__file__).with_name(name) for name in names}
    code = {name: file_hash(path) for name, path in code_paths.items()}
    runtime = {'python': platform.python_version(), 'numpy': np.__version__}
    fingerprint = digest({'inputs': hashes, 'code': code, 'protocol': cfg,
                          'methods': wanted, 'runtime': runtime})
    return {'status': 'ready', 'fingerprint': fingerprint, 'protocol': cfg,
            'config_path': relative(cfg_path, work),
            'methods': wanted, 'runtime': runtime, 'input_hashes': hashes,
            'code_hashes': code, 'options': opts, 'baseline': baseline,
            'baseline_directory': baseline_dir, 'parent': check['parent'],
            'gates': check['gates'], '_code_paths': code_paths,
            'network_calls': 0, 'qgis_started': False}


def preflight_benchmarks(work=WORK, config_path=None, methods=None):
    check = _prepare(work, config_path, methods)
    return {**{k: check[k] for k in ('status', 'fingerprint', 'methods', 'runtime',
                                     'network_calls', 'qgis_started')},
            'candidate_pool': {'A': 20, 'B': 20, 'C': 20},
            'selected_quota': {'A': 10, 'B': 8, 'C': 12},
            'seed_count': check['options']['seed_count'],
            'M0_run_required': False, 'M1_status': 'allocation_rule_not_finalized',
            'baseline_modified': False}


def recover_saved_methods(data, options, baseline, directory):
    """Verify greedy history and positional swap replay; recompute every metric."""
    directory = Path(directory)
    history = json.loads((directory / 'selection_history.json').read_text())
    saved_seeds = json.loads((directory / 'seed_runs.json').read_text())
    swaps = metrics.rows(directory / 'swaps.csv')
    lookup = {r['route_id']: i for i, r in enumerate(data['features'])}
    expected_seeds = [[data['features'][i]['route_id'] for i in seed]
                      for seed in seed_pairs(data, options)]
    if [s['seed'] for s in saved_seeds] != expected_seeds:
        raise ValueError('Saved starts differ from the shared feasible seed policy')
    if not history or history[0].get('seed') not in expected_seeds:
        raise ValueError('Saved history has an unrecognized start')
    previous = []
    for n, entry in enumerate(history):
        ids = entry['selected_after']
        if n == 0:
            if ids != entry['seed'] or entry['round'] != 0:
                raise ValueError('Invalid saved seed entry')
            partial = []
            for rid in ids:
                i = lookup[rid]
                if not _can_add(data, partial, i, options):
                    raise ValueError('Saved start violates common constraints')
                partial.append(i)
        else:
            chosen = entry['chosen']
            if (entry['selected_before'] != previous or chosen in previous or
                    ids != previous + [chosen] or entry['round'] != len(ids)):
                raise ValueError('Invalid greedy history transition')
            if not _can_add(data, [lookup[r] for r in previous], lookup[chosen], options):
                raise ValueError('Saved greedy addition violates common constraints')
        actual = metrics.summary(data, [lookup[r] for r in ids], options['minimum_cell_fraction'])
        _close(actual, entry['set_metrics'], 'history metrics')
        previous = ids
    m4_ids = previous.copy()
    m4_indices = [lookup[r] for r in m4_ids]
    m4_metrics = _validate_set(data, m4_indices, options)
    _close(m4_metrics, baseline['before_swaps'], 'before_swaps')
    winning = next(row for row in saved_seeds if row['seed'] == history[0]['seed'])
    _close({k: v for k, v in winning.items() if k != 'seed'}, m4_metrics, 'winning saved start')
    if abs(min(r['D_combined'] for r in saved_seeds) - m4_metrics['D_combined']) > options['tie_tolerance']:
        raise ValueError('Saved M4 is not the best stored greedy start')
    current_ids, current = m4_ids.copy(), m4_metrics
    swap_history = []
    for n, row in enumerate(swaps, 1):
        if int(row['round']) != n or row['removed'] not in current_ids or row['added'] in current_ids:
            raise ValueError('Invalid saved swap transition')
        _close(current['D_combined'], float(row['D_before']), 'swap.D_before')
        trial = current_ids.copy()
        trial[trial.index(row['removed'])] = row['added']
        values = _validate_set(data, [lookup[r] for r in trial], options)
        _close(values['D_combined'], float(row['D_after']), 'swap.D_after')
        _close(current['D_combined'] - values['D_combined'], float(row['improvement']), 'swap.improvement')
        if values['D_combined'] >= current['D_combined'] - options['swap_min_improvement']:
            raise ValueError('Saved swap does not improve D')
        if (values['material_cells'] < current['material_cells'] or
                values['quantile_groups_covered'] < m4_metrics['quantile_groups_covered'] * options['minimum_quantile_diversity_retained'] or
                any(values['D_by_domain'][g] > m4_metrics['D_by_domain'][g] + options['max_domain_D_worsening']
                    for g in options['quota'])):
            raise ValueError('Saved swap violates M5-specific safeguards')
        swap_history.append({**row, 'selected_after': trial.copy(), 'metrics': values})
        current_ids, current = trial, values
    if len(swaps) != baseline['accepted_swaps'] or current_ids != baseline['selected_route_ids']:
        raise ValueError('Swap replay differs from the published M5 set')
    _close(current, baseline['metrics'], 'M5 metrics')
    provenance = {'source': 'verified_saved_selection_history',
                  'metrics_recomputed': True, 'weighted_algorithm_rerun': False}
    return {
        'M4': {'status': 'completed', 'selected_indices': m4_indices,
               'selected_route_ids': m4_ids, 'metrics': m4_metrics, 'history': history,
               'seed_runs': [], 'provenance': provenance, 'swaps': 0},
        'M5': {'status': 'completed', 'selected_indices': [lookup[r] for r in current_ids],
               'selected_route_ids': current_ids, 'metrics': current, 'history': swap_history,
               'seed_runs': [], 'provenance': provenance, 'swaps': len(swaps)},
    }


@contextmanager
def _output_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.selection_benchmarks.lock').open('a+') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another benchmark run is writing this output directory') from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _read_checkpoint(path, fingerprint, data, options, work):
    value = json.loads(Path(path).read_text())
    result = value['result']
    if value['fingerprint'] != fingerprint or value['result_hash'] != digest(result):
        raise ValueError('Checkpoint fingerprint/hash mismatch: ' + str(path))
    history_path = input_path(work, result['history_path'])
    if result['history_sha256'] != file_hash(history_path):
        raise ValueError('Checkpoint history hash mismatch: ' + str(path))
    lookup = {f['route_id']: i for i, f in enumerate(data['features'])}
    selected = [lookup[rid] for rid in result['selected_route_ids']]
    if result['status'] != 'completed' or selected != result['selected_indices']:
        raise ValueError('Checkpoint selected IDs/indices mismatch')
    _close(_validate_set(data, selected, options), result['metrics'], 'checkpoint.metrics')
    return result


def _recheck_inputs(work, check):
    for name, expected in check['input_hashes'].items():
        if file_hash(input_path(work, name)) != expected:
            raise ValueError('Input changed during the run: ' + name)
    for name, path in check['_code_paths'].items():
        if file_hash(path) != check['code_hashes'][name]:
            raise ValueError('Code changed during the run: ' + name)


def _comparison(results, baseline, protocol):
    rows = []
    base_length = baseline['metrics']['traversed_length_m']
    base_D = baseline['metrics']['D_combined']
    window = protocol['secondary_length_window_fraction']
    for method, result in results.items():
        row = {'method': method, 'status': result['status'],
               'source': result.get('provenance', {}).get('source', ''),
               'reason': result.get('reason', '')}
        if result['status'] == 'completed':
            m = result['metrics']
            row.update(D_combined=m['D_combined'], D_inside=m['D_by_domain']['inside'],
                       D_outside=m['D_by_domain']['outside'],
                       unique_rc_length_km=m['unique_rc_length_m'] / 1000,
                       unique_rc_coverage_pct=100 * m['unique_rc_coverage_fraction'],
                       traversed_length_km=m['traversed_length_m'] / 1000,
                       max_corridor_overlap_pct=100 * m['max_unique_corridor_overlap_fraction'],
                       quantile_groups_covered=m['quantile_groups_covered'],
                       material_cells=m['material_cells'],
                       A=m['sampling_zone_counts']['A'], B=m['sampling_zone_counts']['B'],
                       C=m['sampling_zone_counts']['C'], delta_D_vs_M5=m['D_combined'] - base_D,
                       length_within_baseline_window=abs(m['traversed_length_m'] / base_length - 1) <= window)
        rows.append(row)
    return rows


def _report_markdown(report, rows):
    lines = ['# Đối chứng lựa chọn 30 tuyến', '',
             'M là mã phương pháp; không phải trọng số hay thứ tự bắt buộc.', '',
             '| Phương pháp | D kết hợp | Km RC không trùng | Độ phủ RC (%) | Tổng km hành trình | Ô có đóng góp đáng kể |',
             '|---|---:|---:|---:|---:|---:|']
    for row in rows:
        if row['status'] == 'completed':
            lines.append(f"| {row['method']} | {row['D_combined']:.6f} | {row['unique_rc_length_km']:.3f} | "
                         f"{row['unique_rc_coverage_pct']:.4f} | {row['traversed_length_km']:.3f} | {row['material_cells']} |")
        else:
            lines.append(f"| {row['method']} | Chưa hoàn thành: {row['reason']} | | | | |")
    lines += ['', '- M2: tham lam theo D; M3: tham lam theo chiều dài RC mới không trùng. Không hoán đổi.',
              '- Dùng cùng các cặp khởi đầu xếp theo D; sau khởi đầu M3 chỉ dùng độ phủ và mã tuyến để phân xử hòa.',
              '- M4/M5: kiểm chứng lịch sử đã lưu, tính lại chỉ tiêu và phát lại hoán đổi. Không chạy lại thuật toán có trọng số.',
              '- Đúng A10/B8/C12, 18 trong và 12 ngoài LEZ; trùng hành lang <70%; giữ kiểm tra tiền khảo sát dùng chung.',
              '- D tính trên chiều dài RC theo lượt đi. Độ phủ tính hợp chiều dài RC không trùng. Đoạn nối không vào mẫu số RC.',
              '- Cột cửa sổ tổng km trong comparison.csv chỉ mô tả ±' +
              f"{report['protocol']['secondary_length_window_fraction'] * 100:g}% so với M5; không phải điều kiện lọc hoặc tối ưu.",
              '- Không ép đạt 11 ô. A × RC1 thiếu trong tập ứng viên vẫn được ghi nhận; không tự tạo bằng chứng bổ sung.',
              '- Đây là kết quả tiền khảo sát. Chưa xác minh thực địa, chưa có GPS, chưa chứng minh ranh giới pháp lý chính thức.',
              '- M1 chờ quy tắc phân bổ theo tỷ trọng mạng. M0 ở notebook 10, không là điều kiện để chạy các phương pháp này.',
              '- Các lượt khởi đầu hữu hạn không chứng minh tối ưu toàn cục. Giữ nguyên bộ 30 gốc.', '',
              f"Trạng thái: {report['status']}. Không gọi mạng, không khởi động QGIS.", '']
    return '\n'.join(lines)


def run_benchmarks(work=WORK, methods=None, config_path=None, output_root=None, progress=None):
    """Run independent objectives or reuse verified checkpoints; never edit baseline.

    An output_root override is for isolated review/QA and does not publish latest.
    Ctrl+C preserves completed methods. An unfinished method restarts its seeds.
    """
    work = Path(work).resolve()
    started, start_clock = now(), time.monotonic()
    check = _prepare(work, config_path, methods)
    fingerprint, wanted = check['fingerprint'], check['methods']
    root = (input_path(work, output_root) if output_root else work / 'data/processed/selection_benchmarks')
    directory = root / fingerprint[:20]
    options = check['options']
    tell = progress or (lambda message: None)
    with _output_lock(directory):
        manifest_path = directory / 'manifest.json'
        complete = cached_manifest(directory, fingerprint)
        if manifest_path.exists() and complete is None:
            raise ValueError('Completed bundle is inconsistent; preserve and inspect it before retrying: ' + str(directory))
        data = metrics.load_data(work, check['parent'], options)
        if {f['route_id'] for f in data['features']} != set(check['gates']['routes']):
            raise ValueError('Candidate IDs differ from cached geometry gate IDs')
        shared.sampling_buckets(data, options)
        shared.validate_baseline(data, options, check['baseline'])
        checkpoint_dir = directory / 'checkpoints'
        checkpoint_dir.mkdir(exist_ok=True)
        results, cached, newly_done = {}, [], []
        if complete and set(complete['report']['methods']) != set(wanted):
            raise ValueError('Completed manifest has different methods')
        progress_path = directory / 'progress.json'

        def save_progress(status):
            atomic_json(progress_path, {'status': status, 'fingerprint': fingerprint,
                                       'completed_methods': [m for m, r in results.items() if r['status'] == 'completed'],
                                       'updated_at': now()})

        try:
            recovered = None
            for method in wanted:
                checkpoint = checkpoint_dir / (method + '.json')
                if checkpoint.exists():
                    result = _read_checkpoint(checkpoint, fingerprint, data, options, work)
                    if result.get('method') != method:
                        raise ValueError('Checkpoint method mismatch')
                    cached.append(method)
                    tell(method + ': dùng lại kết quả đã kiểm tra hash và chỉ tiêu')
                else:
                    tell(method + ': bắt đầu')
                    try:
                        if method in ('M2', 'M3'):
                            result = select_objective(data, options, method, progress=tell)
                            result['selected_route_ids'] = [data['features'][i]['route_id']
                                                            for i in result['selected_indices']]
                            result['provenance'] = {'source': 'new_objective_greedy',
                                                    'metrics_recomputed': True,
                                                    'weighted_algorithm_rerun': False}
                        else:
                            if recovered is None:
                                recovered = recover_saved_methods(data, options, check['baseline'],
                                                                  check['baseline_directory'])
                            result = copy.deepcopy(recovered[method])
                    except NoCompleteStart as exc:
                        results[method] = {'method': method, 'status': 'failed',
                                           'reason': str(exc), 'seed_runs': exc.seed_runs,
                                           'selected_route_ids': []}
                        atomic_json(directory / ('failure_' + method + '.json'), results[method])
                        save_progress('partial')
                        continue
                    history_path = directory / 'history' / (method + '.json')
                    atomic_json(history_path, result.pop('history'))
                    result.update(method=method, history_path=relative(history_path, work),
                                  history_sha256=file_hash(history_path))
                    _recheck_inputs(work, check)
                    atomic_json(checkpoint, {'fingerprint': fingerprint,
                                             'result_hash': digest(result), 'result': result})
                    newly_done.append(method)
                results[method] = result
                save_progress('running')
            _recheck_inputs(work, check)
            if complete:
                for method in wanted:
                    _close(results[method], complete['report']['methods'][method], 'cached.' + method)
                report = copy.deepcopy(complete['report'])
                report['invocation'] = {'new_methods': [], 'cached_methods': cached,
                                        'elapsed_seconds': time.monotonic() - start_clock}
                if output_root is None:
                    atomic_json(work / 'reports/selection/latest_benchmarks.json', complete['report'])
                save_progress(complete['report']['status'])
                return report
            unresolved = [m for m in wanted if results[m]['status'] != 'completed']
            paths = {name: relative(directory / file, work) for name, file in
                     {'comparison': 'comparison.csv', 'method_results': 'method_results.json',
                      'report': 'REPORT.md', 'manifest': 'manifest.json'}.items()}
            paths['directory'] = relative(directory, work)
            report = {'status': 'partial' if unresolved else 'completed_pre_survey_benchmarks',
                      'fingerprint': fingerprint, 'method_version': VERSION,
                      'started_at': started, 'finished_at': now(),
                      'elapsed_seconds': time.monotonic() - start_clock,
                      'requested_methods': wanted, 'methods': results, 'unresolved': unresolved,
                      'new_methods': newly_done, 'cached_methods': cached,
                      'protocol': check['protocol'], 'runtime': check['runtime'],
                      'config_path': check['config_path'],
                      'quota': options['quota'], 'intersection_quota': options.get('intersection_quota'),
                      'snapshot_utc': check['baseline']['snapshot_utc'],
                      'baseline_selection_modified': False, 'network_calls': 0, 'qgis_started': False,
                      'measurement_verified': False, 'official_gis_verified': False,
                      'M1_status': 'allocation_rule_not_finalized',
                      'missing_cells_in_entire_pool': check['baseline']['missing_cells_in_entire_pool'],
                      'paths': paths}
            rows = _comparison(results, check['baseline'], check['protocol'])
            fields = ['method', 'status', 'source', 'reason', 'D_combined', 'D_inside', 'D_outside',
                      'unique_rc_length_km', 'unique_rc_coverage_pct', 'traversed_length_km',
                      'max_corridor_overlap_pct', 'quantile_groups_covered', 'material_cells',
                      'A', 'B', 'C', 'delta_D_vs_M5', 'length_within_baseline_window']
            write_csv(directory / 'comparison.csv', rows, fields)
            seed_rows = []
            for method, result in results.items():
                for seed in result.get('seed_runs', []):
                    seed_rows.append({'method': method, 'start': seed['start'],
                                      'seed': ' / '.join(seed['seed']), 'status': seed['status'],
                                      'reason': seed.get('reason', ''), **seed.get('metrics', {})})
            write_csv(directory / 'seed_results.csv', seed_rows,
                      ['method', 'start', 'seed', 'status', 'D_combined', 'unique_rc_length_m', 'reason'])
            atomic_json(directory / 'method_results.json', results)
            atomic_json(directory / 'report.json', report)
            atomic_json(directory / 'inputs.json', {'input_hashes': check['input_hashes'],
                                                    'code_hashes': check['code_hashes']})
            atomic_json(directory / 'protocol.json', check['protocol'])
            atomic_bytes(directory / 'REPORT.md', _report_markdown(report, rows).encode('utf-8'))
            if not unresolved:
                outputs = ['comparison.csv', 'seed_results.csv', 'method_results.json', 'report.json',
                           'inputs.json', 'protocol.json', 'REPORT.md']
                outputs += [p.relative_to(directory).as_posix()
                            for folder in ('checkpoints', 'history')
                            for p in sorted((directory / folder).glob('*.json'))]
                _recheck_inputs(work, check)
                commit_manifest(directory, fingerprint, report, outputs)
                if output_root is None:
                    atomic_json(work / 'reports/selection/latest_benchmarks.json', report)
            save_progress(report['status'])
            return report
        except KeyboardInterrupt:
            save_progress('interrupted')
            raise


def benchmark_status(work=WORK, config_path=None):
    path = Path(work) / 'reports/selection/latest_benchmarks.json'
    if not path.exists():
        return {'status': 'not_run', 'M1_status': 'allocation_rule_not_finalized'}
    report = json.loads(path.read_text())
    check = _prepare(work, config_path or report.get('config_path'), report['requested_methods'])
    directory = input_path(work, report['paths']['directory'])
    manifest = cached_manifest(directory, check['fingerprint'])
    if manifest is None or report != manifest['report']:
        raise ValueError('Latest benchmark pointer is stale or its bundle is inconsistent')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'run', 'status'))
    parser.add_argument('--work', type=Path, default=WORK)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--methods', nargs='+', choices=METHODS)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args(argv)
    if args.action == 'preflight':
        report = preflight_benchmarks(args.work, args.config, args.methods)
    elif args.action == 'run':
        report = run_benchmarks(args.work, args.methods, args.config, args.output_root, print)
    else:
        report = benchmark_status(args.work, args.config)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report['status'] != 'partial' else 1


if __name__ == '__main__':
    raise SystemExit(main())
