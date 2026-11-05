"""RC-target apportionment M1 and a quota-controlled M2b on frozen inputs."""
from collections import Counter
import json
from pathlib import Path

import numpy as np

from . import selection_benchmarks as bench, selection_metrics as metrics
from .common import (WORK, atomic_json, cached_manifest, commit_manifest, digest,
                     file_hash, input_path, relative, write_csv)

ZONES = ('A', 'B', 'C')
VERSION = 'bounded_rc_target_slots_v1'


def bounded_quota(lengths, capacities, count):
    """Saturate constrained classes, then round remaining shares by largest remainder."""
    weights = np.asarray(lengths, dtype=float)
    caps = np.asarray(capacities)
    if (weights.shape != (4,) or caps.shape != (4,) or caps.dtype.kind not in 'iu'
            or type(count) is not int or count < 0 or np.any(caps < 0)
            or not np.isfinite(weights).all() or np.any(weights < 0)):
        raise ValueError('Expected four nonnegative RC lengths and integer capacities')
    slots = [0] * 4
    active = [i for i in range(4) if caps[i] > 0 and weights[i] > 0]
    if sum(int(caps[i]) for i in active) < count:
        raise ValueError('Insufficient candidates in positive-length RC classes')
    while count:
        ideal = {i: count * weights[i] / sum(weights[active]) for i in active}
        capped = [i for i in active if ideal[i] >= caps[i]]
        if capped:
            for i in capped:
                slots[i] = int(caps[i])
                count -= slots[i]
                active.remove(i)
            continue
        for i in active:
            slots[i] = int(ideal[i])
        remainder = count - sum(slots[i] for i in active)
        for i in sorted(active, key=lambda i: (-round(ideal[i] - slots[i], 12), i))[:remainder]:
            slots[i] += 1
        break
    return slots


def _zone(feature):
    return feature.get('sampling_zone', feature['stratum_id'])


def _cell(feature):
    return _zone(feature), feature['rc_target']


def _eligible(data):
    return sorted(data.get('eligible_indices', range(len(data['features']))))


def m1_targets(data, options):
    counts = {}
    group_by_zone = {}
    for bucket in metrics.quota_buckets(options).values():
        if bucket['count'] == 0:
            continue
        if bucket['zones'] is None or len(bucket['zones']) != 1 or bucket['zones'][0] in counts:
            raise ValueError('M1 requires one exact quota per ABC zone')
        zone = bucket['zones'][0]
        counts[zone], group_by_zone[zone] = bucket['count'], bucket['group']
    if set(counts) != set(ZONES):
        raise ValueError('M1 requires A/B/C quotas')
    keys = [(z, r) for z in ZONES for r in metrics.RC]
    if len(data['cells']) != len(keys) or set(data['cells']) != set(keys):
        raise ValueError('Expected 12 distinct ABC × RC cells')
    pool = [data['features'][i] for i in _eligible(data)]
    if any(_cell(f) not in keys or f['group'] != group_by_zone[_zone(f)] for f in pool):
        raise ValueError('Eligible route has inconsistent zone, LEZ or RC target')
    availability = Counter(map(_cell, pool))
    rows = []
    for zone in ZONES:
        cells = [(zone, rc) for rc in metrics.RC]
        lengths = np.asarray([data['network_lengths'][data['cells'].index(key)] for key in cells])
        if lengths.sum() <= 0:
            raise ValueError('Missing zone network denominator')
        shares = lengths / lengths.sum()
        available = [availability[key] for key in cells]
        quotas = bounded_quota(lengths, available, counts[zone])
        for rc, share, cap, slots in zip(metrics.RC, shares, available, quotas):
            rows.append(dict(zone=zone, rc=rc, network_share=float(share),
                             theoretical_slots=float(share * counts[zone]), available=cap, slots=slots))
    return rows


def _limits(targets):
    return {(r['zone'], r['rc']): r['slots'] for r in targets}


def _purity(data, i):
    j = data['cells'].index(_cell(data['features'][i]))
    length = float(data['walks'][i]['length_m'])
    value = float(data['vectors'][i, j]) / length if length > 0 else float('nan')
    if not 0 <= value <= 1 + 1e-10:
        raise ValueError('Invalid target-cell share of full traversal length')
    return value


def _complete(data, options, selected, targets=None):
    ids = [data['features'][i]['route_id'] for i in selected]
    counts = Counter(_cell(data['features'][i]) for i in selected)
    if targets is not None and counts != Counter(_limits(targets)):
        raise ValueError('Exact RC-target quotas not satisfied')
    values = bench._validate_set(data, selected, options)
    vector = data['vectors'][selected].sum(axis=0)
    values['D_by_zone'] = {}
    for zone in ZONES:
        cols = [j for j, cell in enumerate(data['cells']) if cell[0] == zone]
        network = data['network_lengths'][cols]
        values['D_by_zone'][zone] = metrics.D(vector[cols], network / network.sum())
    return {'status': 'completed', 'selected_indices': selected, 'selected_route_ids': ids,
            'metrics': values, 'target_purity_sum': sum(_purity(data, i) for i in selected)}


def select_m1(data, options, targets):
    """Attain the independent bucket upper bound if its exact maximizer passes all gates."""
    chosen = []
    for key, count in _limits(targets).items():
        ranked = sorted((i for i in _eligible(data) if _cell(data['features'][i]) == key),
                        key=lambda i: (-_purity(data, i), data['walks'][i]['length_m'],
                                       data['features'][i]['route_id']))
        chosen.extend(ranked[:count])
    try:
        result = _complete(data, options, chosen, targets)
    except ValueError as exc:
        raise ValueError('Independent M1 optimum violates a common gate or quota; '
                         'a constrained solver is required. This does not prove infeasibility.') from exc
    return {**result, 'objective': 'maximum_sum_target_cell_share_of_full_length',
            'optimality': 'independent_bucket_upper_bound_attained', 'seed_runs': []}


def greedy_m2b(data, options, seed, targets):
    """M2 addition and tie rule, with the same fixed RC-target slots as M1."""
    limits = _limits(targets)
    selected, history = [], []
    keys = [_cell(f) for f in data['features']]
    allowed = _eligible(data)

    def can_add(i):
        trial = selected + [i]
        taken = Counter(keys[j] for j in trial)
        if taken[keys[i]] > limits[keys[i]] or not bench._can_add(data, selected, i, options):
            return False
        remaining = Counter(keys[j] for j in allowed if j not in trial and
                            np.all(data['corridors'][j, trial] < options['max_corridor_overlap']))
        return all(remaining[k] >= size - taken[k] for k, size in limits.items())

    def fail(reason):
        return {'status': 'infeasible', 'reason': reason, 'selected_indices': selected.copy(),
                'history': history}

    for i in seed:
        if i not in allowed or not can_add(i):
            return fail('start_fails_common_or_RC_target_quota')
        selected.append(i)
    if not selected:
        return fail('empty_start')
    vector = data['vectors'][selected].sum(axis=0)
    ids = [f['route_id'] for f in data['features']]
    history.append({'round': len(selected), 'seed': [ids[i] for i in selected],
                    'D': metrics.D(vector, data['q'])})
    while len(selected) < sum(limits.values()):
        candidates = [(i, metrics.D(vector + data['vectors'][i], data['q']))
                      for i in allowed if i not in selected and can_add(i)]
        if not candidates:
            return fail('no_addition_under_RC_target_slots')
        best = min(d for _, d in candidates)
        i, d = min(((i, d) for i, d in candidates if abs(d - best) <= options['tie_tolerance']),
                   key=lambda item: ids[item[0]])
        selected.append(i)
        vector = vector + data['vectors'][i]
        history.append({'round': len(selected), 'chosen': ids[i], 'D': d,
                        'feasible_candidates': len(candidates)})
    return {**_complete(data, options, selected, targets), 'history': history}


def select_m2b(data, options, targets, progress=None):
    runs, complete = [], []
    ids = [f['route_id'] for f in data['features']]
    for n, seed in enumerate(bench.seed_pairs(data, options), 1):
        result = greedy_m2b(data, options, seed, targets)
        runs.append({**{k: v for k, v in result.items() if k != 'history'},
                     'start': n, 'seed': [ids[i] for i in seed]})
        if result['status'] == 'completed':
            complete.append((n, result))
        if progress:
            progress(f"M2b: khởi đầu {n}, {result['status']}")
    if not complete:
        raise bench.NoCompleteStart('M2b', runs)
    best = min(r['metrics']['D_combined'] for _, r in complete)
    n, result = min(((n, r) for n, r in complete if
                     abs(r['metrics']['D_combined'] - best) <= options['tie_tolerance']),
                    key=lambda item: tuple(sorted(item[1]['selected_route_ids'])))
    return {**result, 'chosen_start': n, 'seed_runs': runs}


def _saved_m2(work, check, data):
    """Validate the prior bundle using its runtime plus today's identical input/code hashes."""
    latest = work / 'reports/selection/latest_benchmarks.json'
    original = json.loads(latest.read_text())
    directory = input_path(work, original['paths']['directory'])
    manifest = cached_manifest(directory, original['fingerprint'])
    if not manifest or manifest['report'] != original:
        raise ValueError('Saved M2 bundle is incomplete or differs from its latest pointer')
    frozen = json.loads((directory / 'inputs.json').read_text())
    if (frozen['code_hashes'] != check['code_hashes'] or any(
            frozen['input_hashes'].get(k) != v for k, v in check['input_hashes'].items()) or
            original['protocol'] != check['protocol']):
        raise ValueError('Saved M2 was generated with different source, code or protocol')
    fp = digest({'inputs': frozen['input_hashes'], 'code': frozen['code_hashes'],
                 'protocol': original['protocol'], 'methods': original['requested_methods'],
                 'runtime': original['runtime']})
    if fp != original['fingerprint']:
        raise ValueError('Saved M2 provenance fingerprint differs')
    old = original['methods']['M2']
    options = check['options']
    expected_seeds = [[data['features'][i]['route_id'] for i in pair]
                      for pair in bench.seed_pairs(data, options)]
    if [x['seed'] for x in old['seed_runs']] != expected_seeds:
        raise ValueError('Saved M2 starts differ from the controlled comparison starts')
    by_id = {f['route_id']: i for i, f in enumerate(data['features'])}
    result = _complete(data, options, [by_id[r] for r in old['selected_route_ids']])
    bench._close({k: v for k, v in result['metrics'].items() if k != 'D_by_zone'},
                 old['metrics'], 'saved M2 metrics')
    return {**result, 'seed_runs': old['seed_runs'], 'provenance': 'verified_saved_M2_no_rerun',
            'source_fingerprint': fp}, {relative(p, work): file_hash(p) for p in
                                         (latest, directory / 'manifest.json')}


def run_m1_benchmark(work=WORK, progress=None, output_root=None):
    """Publish a separate M1/M2a/M2b comparison; preserve original M2 and production set."""
    work = Path(work).resolve()
    check = bench._prepare(work, methods=['M2'])
    options = check['options']
    data = metrics.load_data(work, check['parent'], options)
    bench.shared.sampling_buckets(data, options)
    bench.shared.validate_baseline(data, options, check['baseline'])
    if {f['route_id'] for f in data['features']} != set(check['gates']['routes']):
        raise ValueError('Candidate IDs differ from cached geometry gates')
    targets = m1_targets(data, options)
    m2a, saved_hashes = _saved_m2(work, check, data)
    source_hash = file_hash(Path(__file__))
    fp = digest({'version': VERSION, 'input_fingerprint': check['fingerprint'],
                 'module': source_hash, 'saved_M2': saved_hashes, 'targets': targets})
    directory = (Path(output_root).resolve() if output_root is not None else
                 work / 'data/processed/selection_m1') / fp[:20]
    latest = work / 'reports/selection/latest_m1_benchmark.json'
    with bench._output_lock(directory):
        cached = cached_manifest(directory, fp)
        if cached:
            if output_root is None:
                atomic_json(latest, cached['report'])
            return cached['report']
        if (directory / 'manifest.json').exists():
            raise ValueError('Existing M1 bundle failed verification; preserve it for inspection')
        m1 = select_m1(data, options, targets)
        m2b = select_m2b(data, options, targets, progress)
        results = {'M1': m1, 'M2a': m2a, 'M2b': m2b}
        cells, comparison = [], []
        for method, result in results.items():
            values = result['metrics']
            comparison.append(dict(method=method, D_combined=values['D_combined'],
                                   **{'D_' + z: d for z, d in values['D_by_zone'].items()},
                                   target_purity_sum=result['target_purity_sum'],
                                   traversed_km=values['traversed_length_m']/1000,
                                   rc_traversed_km=values['rc_traversed_length_m']/1000,
                                   unique_rc_km=values['unique_rc_length_m']/1000,
                                   material_cells=values['material_cells'],
                                   max_corridor_overlap_fraction=values['max_unique_corridor_overlap_fraction']))
            selected = result['selected_indices']
            taken = Counter(_cell(data['features'][i]) for i in selected)
            lengths = data['vectors'][selected].sum(axis=0)
            for row in targets:
                key = (row['zone'], row['rc'])
                j = data['cells'].index(key)
                cells.append(dict(method=method, **row, selected_target_slots=taken[key],
                                  selected_rc_traversed_m=float(lengths[j]),
                                  network_length_m=float(data['network_lengths'][j]),
                                  network_share_global=float(data['q'][j]),
                                  sample_share_global=float(lengths[j] / lengths.sum())))
        paths = {k: relative(directory / name, work) for k, name in
                 {'comparison': 'comparison.csv', 'cells': 'rc_cells.csv', 'history': 'm2b_history.json',
                  'seed_results': 'seed_results.json', 'manifest': 'manifest.json'}.items()}
        paths['directory'] = relative(directory, work)
        report = {**m1, 'method_version': VERSION, 'targets': targets, 'comparison': comparison,
                  'paths': paths, 'fingerprint': fp, 'snapshot_utc': check['baseline']['snapshot_utc'],
                  'methods': {k: {key: v for key, v in r.items() if key != 'history'}
                              for k, r in results.items()},
                  'source_hashes': {**check['input_hashes'], **saved_hashes},
                  'code_hashes': {**check['code_hashes'], 'selection_m1.py': source_hash},
                  'runtime': check['runtime'],
                  'start_policy': 'same_saved_M2_ten_D_ranked_pairs_and_route_ID_ties',
                  'measurement_verified': False, 'official_gis_verified': False}
        write_csv(directory / 'comparison.csv', comparison, list(comparison[0]))
        write_csv(directory / 'rc_cells.csv', cells, list(cells[0]))
        atomic_json(directory / 'm2b_history.json', m2b['history'])
        atomic_json(directory / 'seed_results.json', {'M2a': m2a['seed_runs'], 'M2b': m2b['seed_runs']})
        atomic_json(directory / 'report.json', report)
        bench._recheck_inputs(work, check)
        if file_hash(Path(__file__)) != source_hash or any(
                file_hash(input_path(work, k)) != v for k, v in saved_hashes.items()):
            raise ValueError('M1 module or saved M2 source changed during the run')
        commit_manifest(directory, fp, report,
                        ['comparison.csv', 'rc_cells.csv', 'm2b_history.json', 'seed_results.json', 'report.json'])
        if output_root is None:
            atomic_json(latest, report)
        return report
