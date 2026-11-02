"""M0: independent uniform stratified draws, conditional on common hard gates.

Uses frozen GIS inputs and the published metric definitions. No optimization,
QGIS startup, HTTP requests, field observations or changes to the baseline.
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
import importlib.metadata
import json
import math
import os
import platform
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from . import selection_metrics as metrics
from .common import (WORK, atomic_bytes, atomic_json, cached_manifest,
                     commit_manifest, digest, file_hash, input_path, now,
                     relative, write_csv)
from .selection_30 import configuration


def protocol(work, config_path=None):
    path = Path(config_path) if config_path else Path(work) / 'config/selection_random.json'
    cfg = json.loads(path.read_text())
    if cfg['schema_version'] != 1 or cfg['method_version'] != 'M0_uniform_stratified_rejection_v1':
        raise ValueError('Unsupported M0 protocol')
    for key in ('valid_samples', 'max_attempts', 'checkpoint_every'):
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError('Expected a positive integer: ' + key)
    if type(cfg['random_seed']) is not int or cfg['random_seed'] < 0:
        raise ValueError('Expected a nonnegative integer seed')
    if cfg['max_attempts'] < cfg['valid_samples']:
        raise ValueError('max_attempts must allow the requested valid sample count')
    if (cfg['replacement_within_set'] is not False or cfg['independent_sets_may_repeat'] is not True
            or cfg['material_cell_count_is_filter'] is not False):
        raise ValueError('M0 requires independent sets, no replacement within a set, no cell-count filter')
    if not 0 <= cfg['comparison_tolerance'] <= 1e-8:
        raise ValueError('Invalid comparison tolerance')
    if not 0 < cfg['secondary_length_window_fraction'] < 1:
        raise ValueError('Invalid descriptive length window')
    if type(cfg['render_plot']) is not bool:
        raise ValueError('render_plot must be boolean')
    return cfg


def preflight_random(work=WORK, config_path=None):
    """Verify frozen bundles and the cached GIS gates without requiring PyQGIS."""
    work = Path(work).resolve()
    cfg, opts = protocol(work, config_path), configuration(work)
    if opts.get('required_material_cells') or opts.get('mandatory_cells'):
        raise ValueError('This M0 protocol treats material cell coverage as an outcome, not a filter')
    parent_path = input_path(work, opts['parent_report'])
    baseline_path = work / 'reports/selection/latest_selection_30.json'
    parent, baseline = [json.loads(p.read_text()) for p in (parent_path, baseline_path)]
    directories = [input_path(work, r['paths']['directory']) for r in (parent, baseline)]
    for directory, report in zip(directories, (parent, baseline)):
        manifest = json.loads((directory / 'manifest.json').read_text())
        if not cached_manifest(directory, manifest['fingerprint']):
            raise ValueError('Changed or incomplete frozen bundle: ' + relative(directory, work))
        for key in ('selected_route_ids', 'metrics'):
            if key in report and manifest['report'].get(key) != report[key]:
                raise ValueError('Latest pointer differs from its immutable bundle: ' + key)
    gates = json.loads((directories[1] / 'gate_checks.json').read_text())
    if not gates['summary']['G2_actual_graph_passed'] or not gates['summary']['G3_actual_geometry_passed']:
        raise ValueError('Cached mandatory graph/geometry gates are not passed')
    if len(gates['routes']) != 60 or any(not r['pre_survey_admissible'] for r in gates['routes'].values()):
        raise ValueError('Expected 60 pre-survey admissible candidates')
    ids = baseline['selected_route_ids']
    if len(ids) != 30 or len(set(ids)) != 30:
        raise ValueError('Invalid published baseline')
    sampling_path = input_path(work, opts['sampling_config'])
    sampling = json.loads(sampling_path.read_text())
    files = {parent_path, baseline_path, sampling_path, work / 'config/selection_30.json',
             input_path(work, opts['policy_config']), input_path(work, opts['source_requirements']),
             input_path(work, sampling['graph_path']), input_path(work, sampling['network_path'])}
    files.update(input_path(work, p) for p in opts['sources'])
    files.update(d / 'manifest.json' for d in directories)
    files.update(directories[0] / p for p in ('candidate_walks.json', 'network_matrix.csv', 'network_parts.gpkg', 'route_overlap.csv'))
    files.update(directories[1] / p for p in ('gate_checks.json', 'route_variables.csv', 'selected_routes.csv'))
    hashes = {relative(p, work): file_hash(p) for p in sorted(files)}
    for name, expected in gates['summary']['input_hashes'].items():
        actual = hashes.get(name)
        if actual is None:
            actual = file_hash(input_path(work, name))
            hashes[name] = actual
        if actual != expected:
            raise ValueError('Input changed since mandatory GIS checks: ' + name)
    engine = Path(metrics.__file__).resolve()
    code = {p.name: file_hash(p) for p in (Path(__file__), engine, engine.with_name('common.py'),
            engine.with_name('selection_30.py'), engine.with_name('graph.py'))}
    runtime = {'numpy': np.__version__, 'python': platform.python_version()}
    if cfg['render_plot']:
        runtime['matplotlib'] = importlib.metadata.version('matplotlib')
    fingerprint = digest({'inputs': hashes, 'code': code, 'protocol': cfg, 'runtime': runtime})
    return {'status': 'ready', 'fingerprint': fingerprint, 'protocol': cfg, 'options': opts,
            'input_hashes': hashes, 'code_hashes': code, 'runtime': runtime,
            'baseline': baseline, 'parent': parent, 'gates': gates,
            'network_calls': 0, 'qgis_started': False}


def sampling_buckets(data, options):
    ids = [r['route_id'] for r in data['features']]
    if len(ids) != len(set(ids)) or ids != [r['route_id'] for r in data['walks']]:
        raise ValueError('Candidate IDs must be unique and aligned with walks')
    matrix = np.asarray(data['corridors'])
    if (matrix.shape != (len(ids), len(ids)) or not np.isfinite(matrix).all()
            or not np.allclose(matrix, matrix.T, atol=1e-12, rtol=0)
            or np.any(matrix < 0) or np.any(matrix > 1)):
        raise ValueError('Invalid physical corridor overlap matrix')
    if not 0 < options['max_corridor_overlap'] <= 1:
        raise ValueError('Invalid corridor overlap cap')
    allowed = data.get('eligible_indices', set(range(len(ids))))
    result = []
    for name, bucket in metrics.quota_buckets(options).items():
        members = [i for i, r in enumerate(data['features'])
                   if i in allowed and metrics.quota_bucket(r, options) == name]
        if len(members) < bucket['count']:
            raise ValueError('Insufficient candidates in quota bucket: ' + name)
        if bucket['count']:
            result.append((name, members, bucket['count']))
    return result


def draw_indices(rng, buckets):
    """Each full quota-conforming set has the same proposal probability."""
    return sorted(int(i) for _, members, count in buckets
                  for i in rng.choice(members, size=count, replace=False))


def rejection_reason(data, indices, options):
    # Reject the whole proposal; never repair or optimize a random set.
    if set(options['required_strata']) - {data['features'][i]['stratum_id'] for i in indices}:
        return 'required_strata'
    pairs = np.triu_indices(len(indices), 1)
    if np.any(data['corridors'][np.ix_(indices, indices)][pairs] >= options['max_corridor_overlap']):
        return 'overlap'
    return None


def generate_samples(data, options, cfg, state=None, checkpoint=None):
    """Continue exactly from RNG state; max_attempts counts rejected draws too."""
    buckets = sampling_buckets(data, options)
    rng = np.random.Generator(np.random.PCG64(cfg['random_seed']))
    state = copy.deepcopy(state) if state is not None else {
        'attempts': 0, 'rejections': {'overlap': 0, 'required_strata': 0}, 'samples': [],
        'rng_state': rng.bit_generator.state}
    if state['attempts'] != len(state['samples']) + sum(state['rejections'].values()):
        raise ValueError('Invalid checkpoint attempt accounting')
    if len(state['samples']) > cfg['valid_samples'] or state['attempts'] > cfg['max_attempts']:
        raise ValueError('Checkpoint exceeds configured run limits')
    rng.bit_generator.state = state['rng_state']
    last_checkpoint_attempt = None
    while len(state['samples']) < cfg['valid_samples'] and state['attempts'] < cfg['max_attempts']:
        # A committed state represents a whole draw. An interrupted metric
        # calculation is retried with the previous RNG state on resume.
        indices = draw_indices(rng, buckets)
        reason = rejection_reason(data, indices, options)
        sample = None
        if reason is None:
            sample = {'sample_id': len(state['samples']) + 1, 'attempt': state['attempts'] + 1,
                      'route_ids': [data['features'][i]['route_id'] for i in indices],
                      'metrics': metrics.summary(data, indices, options['minimum_cell_fraction'])}
        if sample is not None:
            state['samples'].append(sample)
        else:
            state['rejections'][reason] += 1
        state['attempts'] += 1
        state['rng_state'] = rng.bit_generator.state
        if checkpoint and ((sample is not None and len(state['samples']) % cfg['checkpoint_every'] == 0)
                           or state['attempts'] % 10000 == 0):
            checkpoint(state)
            last_checkpoint_attempt = state['attempts']
    if checkpoint and state['attempts'] != last_checkpoint_attempt:
        checkpoint(state)
    return state


def distribution(values):
    array = np.asarray(values, dtype=float)
    if not len(array):
        return None
    if not np.isfinite(array).all():
        raise ValueError('Nonfinite benchmark metric')
    q = np.quantile(array, [.025, .25, .5, .75, .975])
    return {'count': len(array), 'mean': float(array.mean()),
            'std': float(array.std(ddof=1)) if len(array) > 1 else None,
            'min': float(array.min()), 'q025': float(q[0]), 'q25': float(q[1]),
            'median': float(q[2]), 'q75': float(q[3]), 'q975': float(q[4]), 'max': float(array.max())}


def comparison(samples, baseline_metrics, tolerance):
    values = [r['metrics']['D_combined'] for r in samples]
    baseline_D = baseline_metrics['D_combined']
    strict = sum(v < baseline_D - tolerance for v in values)
    tied = sum(abs(v - baseline_D) <= tolerance for v in values)
    count = len(values)
    return {'n': count, 'baseline_D': baseline_D, 'D_distribution': distribution(values),
            'strictly_lower_D_count': strict, 'tied_D_count': tied,
            'no_higher_D_count': strict + tied,
            'no_higher_D_fraction': (strict + tied) / count if count else None,
            'empirical_resolution': 1 / count if count else None,
            'interpretation': 'Descriptive random-set benchmark; not a conventional p-value or a population confidence interval.'}


def flat_metrics(values):
    return {**{k: v for k, v in values.items() if type(v) in (int, float)},
            **{'D_' + group: value for group, value in values['D_by_domain'].items()}}


def validate_baseline(data, options, baseline):
    ids = [r['route_id'] for r in data['walks']]
    selected = [ids.index(rid) for rid in baseline['selected_route_ids']]
    counts = Counter(metrics.quota_bucket(data['features'][i], options) for i in selected)
    if any(counts[name] != bucket['count'] for name, bucket in metrics.quota_buckets(options).items()):
        raise ValueError('Baseline does not meet the same quotas')
    if rejection_reason(data, selected, options):
        raise ValueError('Baseline does not pass the common hard constraints')
    actual = metrics.summary(data, selected, options['minimum_cell_fraction'])
    def equal(a, b):
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
        if isinstance(a, float):
            return isinstance(b, (int, float)) and math.isclose(a, b, abs_tol=1e-10, rel_tol=1e-12)
        return a == b
    if not equal(actual, baseline['metrics']):
        raise ValueError('Recomputed baseline metrics differ from the published baseline')
    return actual


def write_plot(directory, samples, baseline_metrics):
    os.environ.setdefault('MPLCONFIGDIR', str(directory / '.matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    ds = [r['metrics']['D_combined'] for r in samples]
    lengths = [r['metrics']['traversed_length_m'] / 1000 for r in samples]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
    axes[0].hist(ds, bins=30, color='#287d8e', alpha=.85, edgecolor='white')
    axes[0].axvline(baseline_metrics['D_combined'], color='#c44e32', lw=2, label='Fixed selected 30')
    axes[0].set(xlabel='D (lower is better)', ylabel='Number of valid random sets',
                title=f'M0: {len(samples):,} valid stratified sets')
    axes[0].legend()
    axes[1].scatter(lengths, ds, s=12, alpha=.35, color='#287d8e', label='Random sets')
    axes[1].scatter([baseline_metrics['traversed_length_m'] / 1000], [baseline_metrics['D_combined']],
                    marker='*', s=170, color='#c44e32', label='Fixed selected 30', zorder=5)
    axes[1].set(xlabel='Total route traversal (km)', ylabel='D', title='Length and D on the fixed candidate pool')
    axes[1].legend()
    fig.savefig(directory / 'D_distribution.png', dpi=180)
    plt.close(fig)


def write_outputs(directory, state, check, baseline_metrics):
    samples, cfg = state['samples'], check['protocol']
    baseline_flat = flat_metrics(baseline_metrics)
    flat = [{'sample_id': s['sample_id'], 'attempt': s['attempt'], 'route_ids': '|'.join(s['route_ids']),
             **flat_metrics(s['metrics'])} for s in samples]
    write_csv(directory / 'random_sets.csv', flat, list(flat[0]))
    summaries = []
    for key, value in baseline_flat.items():
        stats = distribution([flat_metrics(s['metrics'])[key] for s in samples])
        summaries.append({'metric': key, 'baseline': value, **stats})
    write_csv(directory / 'metric_summary.csv', summaries, list(summaries[0]))
    frequencies = Counter(rid for sample in samples for rid in sample['route_ids'])
    baseline_ids = set(check['baseline']['selected_route_ids'])
    frequency_rows = [{'route_id': rid, 'selected_count': frequencies[rid],
                       'selected_fraction': frequencies[rid] / len(samples), 'in_baseline': rid in baseline_ids}
                      for rid in sorted(check['gates']['routes'])]
    write_csv(directory / 'route_frequency.csv', frequency_rows, list(frequency_rows[0]))
    atomic_json(directory / 'random_sets.json', samples)
    length = baseline_metrics['traversed_length_m']
    window = cfg['secondary_length_window_fraction']
    matched = [s for s in samples if abs(s['metrics']['traversed_length_m'] / length - 1) <= window]
    result = {'comparison': comparison(samples, baseline_metrics, cfg['comparison_tolerance']),
              'secondary_length_matched_comparison': {'length_window_fraction': window,
                  'selection_filter': False, **comparison(matched, baseline_metrics, cfg['comparison_tolerance'])},
              'unique_sampled_sets': len({tuple(s['route_ids']) for s in samples})}
    if cfg['render_plot']:
        write_plot(directory, samples, baseline_metrics)
    return result


@contextmanager
def output_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.random_baseline.lock').open('a+') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another M0 run uses this output root') from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def run_random(work=WORK, config_path=None, output_root=None, progress=print):
    work = Path(work).resolve()
    check = preflight_random(work, config_path)
    cfg, opts, baseline = check['protocol'], check['options'], check['baseline']
    root = Path(output_root).resolve() if output_root else work / 'data/processed/selection_random'
    directory = root / check['fingerprint'][:20]
    latest = work / 'reports/selection/latest_random_baseline.json'
    def tell(message):
        if progress is print:
            print(message, flush=True)
        elif progress:
            progress(message)
    with output_lock(root):
        cached = cached_manifest(directory, check['fingerprint'])
        if cached:
            report = dict(cached['report'], cache_hit=True)
            if output_root is None:
                atomic_json(latest, report)
            return report
        if (directory / 'manifest.json').exists():
            raise RuntimeError('Existing completed M0 bundle failed integrity checks; preserve it for inspection')
        started, timer = now(), time.monotonic()
        directory.mkdir(parents=True, exist_ok=True)
        state_path = directory / 'checkpoint.json'
        state = None
        if state_path.exists():
            saved = json.loads(state_path.read_text())
            if saved['fingerprint'] != check['fingerprint'] or saved['state_hash'] != digest(saved['state']):
                raise ValueError('Checkpoint integrity mismatch')
            state = saved['state']
        tell('M0: đọc dữ liệu cố định và đối chiếu lại toàn bộ chỉ tiêu của bộ 30.')
        data = metrics.load_data(work, check['parent'], opts)
        if set(r['route_id'] for r in data['walks']) != set(check['gates']['routes']):
            raise ValueError('Candidate pool differs from the gated pool')
        baseline_metrics = validate_baseline(data, opts, baseline)
        atomic_json(directory / 'inputs.json', {k: v for k, v in check.items() if k not in ('parent', 'baseline', 'gates')})
        atomic_json(directory / 'protocol.json', {'config': cfg, 'quota': opts['quota'],
            'intersection_quota': opts['intersection_quota'], 'max_corridor_overlap': opts['max_corridor_overlap'],
            'proposal': 'uniform independent full-set draw within disjoint quota buckets',
            'acceptance': 'reject entire set if common hard constraints fail; no repair or optimization',
            'repeated_sets': 'allowed across independent draws; never within one set',
            'baseline_selected_ids': baseline['selected_route_ids'],
            'D_formula': '0.5 * sum(abs(network_RC_length / total_network_RC_length - sample_RC_traversal / total_sample_RC_traversal))',
            'coverage_denominator': 'full eligible RC1-RC4 network length, each physical part counted once',
            'material_cells': 'diagnostic outcome only; fixed full-route fraction threshold from selection_30 config'})
        def checkpoint(current):
            atomic_json(state_path, {'fingerprint': check['fingerprint'], 'state_hash': digest(current), 'state': current})
            atomic_json(directory / 'progress.json', {'status': 'sampling', 'accepted': len(current['samples']),
                'target': cfg['valid_samples'], 'attempts': current['attempts'], 'rejections': current['rejections'], 'updated_at': now()})
            tell(f"M0: {len(current['samples'])}/{cfg['valid_samples']} bộ hợp lệ; {current['attempts']} lần bốc.")
        state = generate_samples(data, opts, cfg, state=state, checkpoint=checkpoint)
        if len(state['samples']) != cfg['valid_samples']:
            atomic_json(directory / 'progress.json', {'status': 'max_attempts_reached', 'accepted': len(state['samples']),
                'target': cfg['valid_samples'], 'attempts': state['attempts'], 'updated_at': now()})
            raise RuntimeError('M0 reached max_attempts before obtaining all valid sets; no complete report published')
        results = write_outputs(directory, state, check, baseline_metrics)
        report = {'status': 'completed_pre_survey_random_baseline', 'fingerprint': check['fingerprint'],
            'started_at': started, 'finished_at': now(), 'elapsed_seconds': time.monotonic() - timer,
            'cache_hit': False, 'valid_samples': len(state['samples']), 'attempts': state['attempts'],
            'rejections': state['rejections'], 'acceptance_fraction': len(state['samples']) / state['attempts'],
            'random_seed': cfg['random_seed'], 'quota': opts['quota'], 'intersection_quota': opts['intersection_quota'],
            'baseline_metrics': baseline_metrics, 'baseline_selected_ids': baseline['selected_route_ids'],
            'baseline_reproduced': True, 'baseline_selection_modified': False,
            'measurement_verified': False, 'official_gis_verified': False, 'field_observations_created': 0,
            'network_calls': 0, 'qgis_started': False, 'missing_pool_cells': baseline['missing_cells_in_entire_pool'],
            **results, 'paths': {k: relative(directory / value, work) for k, value in (
                ('directory', '.'), ('report', 'REPORT.md'), ('sets', 'random_sets.csv'),
                ('summary', 'metric_summary.csv'), ('frequency', 'route_frequency.csv'),
                ('protocol', 'protocol.json'), ('inputs', 'inputs.json'))},
            'limitations': ['Conditional on the fixed 60-candidate pool and cached research geometry/gates.',
                'D measures length-composition mismatch, not field measurement coverage.',
                'Finite simulation of random sets compared with an optimized baseline; no conventional p-value or global optimality proof.',
                'Zero observed random sets at least as good does not mean zero probability.',
                'Length-matched comparison is descriptive on a subset; all valid draws remain in the primary result.']}
        if cfg['render_plot']:
            report['paths']['plot'] = relative(directory / 'D_distribution.png', work)
        c = report['comparison']; d = c['D_distribution']
        text = (f"# M0 — đối chứng ngẫu nhiên phân tầng\n\n"
            f"Đã bốc {report['attempts']:,} lần, nhận {report['valid_samples']:,} bộ hợp lệ; "
            f"quota A10/B8/C12, 18 trong/12 ngoài LEZ. Seed: {cfg['random_seed']}.\n\n"
            f"D bộ 30 cố định: **{c['baseline_D']:.6f}**. D ngẫu nhiên trung bình: **{d['mean']:.6f}**; "
            f"trung vị {d['median']:.6f}; nhỏ nhất {d['min']:.6f}; lớn nhất {d['max']:.6f}.\n\n"
            f"Có **{c['no_higher_D_count']}/{c['n']}** bộ ngẫu nhiên có D không lớn hơn bộ 30 "
            f"(dung sai {cfg['comparison_tolerance']}). Đây là tỷ lệ thực nghiệm mô tả, không phải p-value. "
            f"Không suy ra xác suất bằng 0 nếu không thấy trường hợp nào trong {c['n']} lần hợp lệ.\n\n"
            "Mọi bộ giữ đúng quota và có trùng hành lang vật lý dưới ngưỡng hiện hành. "
            "Không lọc theo D, số ô RC, độ đa dạng hay chiều dài. Bộ trùng giữa các lần độc lập được giữ lại.\n\n"
            "`random_sets.csv/json` giữ danh sách 30 ID và chỉ tiêu của từng bộ; `metric_summary.csv` tổng hợp "
            "phân phối; `route_frequency.csv` ghi tần suất từng tuyến. `protocol.json` và `inputs.json` giữ quy tắc và hash.\n\n"
            "D dùng tỷ trọng chiều dài RC1–RC4, tính theo lượt đi và loại connector khỏi mẫu số. "
            "Độ phủ duy nhất đếm mỗi phần đường vật lý một lần, chia cho tổng chiều dài mạng RC1–RC4 đủ điều kiện. "
            f"Đối chiếu phụ giới hạn ±{cfg['secondary_length_window_fraction'] * 100:g}% chiều dài bộ gốc "
            "chỉ là mô tả, không phải điều kiện nhận bộ.\n\n"
            "Bộ 30 gốc được đối chiếu lại, không bị sửa. Đây là kết quả tiền khảo sát trên pool cố định; "
            "A×RC1 và các xác minh thực địa còn thiếu vẫn giữ nguyên.\n")
        atomic_bytes(directory / 'REPORT.md', text.encode())
        atomic_json(directory / 'report.json', report)
        for name, expected in check['input_hashes'].items():
            if file_hash(input_path(work, name)) != expected:
                raise RuntimeError('Input changed during M0 run: ' + name)
        outputs = ['inputs.json', 'protocol.json', 'random_sets.csv', 'random_sets.json', 'metric_summary.csv',
                   'route_frequency.csv', 'REPORT.md', 'report.json', 'checkpoint.json']
        if cfg['render_plot']:
            outputs.append('D_distribution.png')
        commit_manifest(directory, check['fingerprint'], report, outputs)
        atomic_json(directory / 'progress.json', {'status': report['status'], 'accepted': len(state['samples']),
            'attempts': state['attempts'], 'updated_at': now()})
        if output_root is None:
            atomic_json(latest, report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['preflight', 'run', 'status'])
    parser.add_argument('--work', type=Path, default=WORK)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    if args.command == 'run':
        result = run_random(args.work, config_path=args.config, output_root=args.output_root)
    elif args.command == 'preflight':
        check = preflight_random(args.work, args.config)
        result = {key: check[key] for key in ('status', 'fingerprint', 'network_calls', 'qgis_started', 'runtime')}
    else:
        path = args.work / 'reports/selection/latest_random_baseline.json'
        result = json.loads(path.read_text()) if path.exists() else {'status': 'not_run'}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
