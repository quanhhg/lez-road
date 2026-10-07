"""Reproducible, resumable sensitivity analysis of the fixed ABC 30-route design.

Uses the exact published selection engine in an isolated namespace. Only
scenario scoring assumptions change; source geometry, gates and raw C6 stay
unchanged. Ordinary Python + NumPy; no QGIS import, HTTP or source-data writes.
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
import types
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
    path = Path(config_path) if config_path else Path(work) / 'config/selection_sensitivity.json'
    cfg = json.loads(path.read_text())
    if cfg['C6_zero_policy'] != 'exclude_candidate_in_simulated_availability_scenario':
        raise ValueError('C6=0 must exclude a simulated candidate, not just reduce its score')
    if cfg['normalization_fit_population'] != 'all_60_candidates_in_each_scenario' or cfg['zscore_ddof'] != 0:
        raise ValueError('Unsupported X fit population/ddof')
    if cfg['single_route_unavailability'] != 'each_of_the_30_baseline_routes':
        raise ValueError('Unsupported availability protocol')
    if cfg['C6_feasible_assumption_values'] != [1, 2, 3, 4, 5]:
        raise ValueError('Feasible C6 assumptions must be 1..5; zero is a separate exclusion scenario')
    for name in ('C6_random_runs_per_scaling', 'combined_random_runs', 'random_seed'):
        if not isinstance(cfg[name], int) or cfg[name] < 0:
            raise ValueError('Invalid '+name)
    if not 0 < cfg['weight_relative_change'] < 1 or any(not 0 < v < 1 for v in cfg['cell_thresholds']):
        raise ValueError('Invalid sensitivity ranges')
    for name in ('lane_model_bounds', 'speed_model_bounds_kmh'):
        if len(cfg[name]) != 2 or not 0 < cfg[name][0] < cfg[name][1]:
            raise ValueError('Invalid model bounds')
    return cfg


def preflight_sensitivity(work=WORK, config_path=None):
    """Verify cached GIS gates and frozen inputs without starting GIS or HTTP."""
    work = Path(work).resolve()
    cfg, opts = protocol(work, config_path), configuration(work)
    parent_path = input_path(work, opts['parent_report'])
    baseline_path = work / 'reports/selection/latest_selection_30.json'
    parent, baseline = [json.loads(p.read_text()) for p in (parent_path, baseline_path)]
    directories = [input_path(work, r['paths']['directory']) for r in (parent, baseline)]
    for directory, report in zip(directories, (parent, baseline)):
        manifest = json.loads((directory / 'manifest.json').read_text())
        if not cached_manifest(directory, manifest['fingerprint']):
            raise ValueError('Changed or incomplete frozen bundle: '+relative(directory, work))
        if directory == directories[1] and (manifest['report']['selected_route_ids'] != report['selected_route_ids']
                or manifest['report']['metrics'] != report['metrics']):
            raise ValueError('Latest baseline pointer differs from its immutable manifest')
    gates = json.loads((directories[1] / 'gate_checks.json').read_text())
    if not gates['summary']['G2_actual_graph_passed'] or not gates['summary']['G3_actual_geometry_passed']:
        raise ValueError('Cached mandatory GIS gates are not passed')
    if len(gates['routes']) != 60 or any(not v['pre_survey_admissible'] for v in gates['routes'].values()):
        raise ValueError('Expected 60 pre-survey admissible candidates')
    if len(baseline['selected_route_ids']) != 30 or len(set(baseline['selected_route_ids'])) != 30:
        raise ValueError('Invalid published 30-route baseline')
    sampling_path = input_path(work, opts['sampling_config'])
    sampling = json.loads(sampling_path.read_text())
    files = {parent_path, baseline_path, sampling_path, work/'config/selection_30.json',
             input_path(work, opts['policy_config']), input_path(work, opts['source_requirements']),
             input_path(work, sampling['graph_path']), input_path(work, sampling['network_path'])}
    files.update(input_path(work, p) for p in opts['sources'])
    for d in directories:
        files.add(d / 'manifest.json')
    files.update(directories[0] / p for p in ('candidate_walks.json', 'network_matrix.csv', 'network_parts.gpkg', 'route_overlap.csv'))
    files.update(directories[1] / p for p in ('gate_checks.json', 'route_variables.csv', 'selected_routes.csv'))
    hashes = {relative(p, work): file_hash(p) for p in sorted(files)}
    for name, expected in gates['summary']['input_hashes'].items():
        actual = hashes.get(name)
        if actual is None:
            actual = file_hash(input_path(work, name))
            hashes[name] = actual
        if actual != expected:
            raise ValueError('Input changed since mandatory GIS checks: '+name)
    engine_path = Path(metrics.__file__).resolve()
    code = {p.name:file_hash(p) for p in (Path(__file__), engine_path,
            engine_path.with_name('common.py'), engine_path.with_name('selection_30.py'), engine_path.with_name('graph.py'))}
    runtime = {'numpy':np.__version__, 'python':platform.python_version()}
    fingerprint = digest({'inputs':hashes, 'code':code, 'protocol':cfg, 'runtime':runtime})
    return {'status':'ready', 'fingerprint':fingerprint, 'protocol':cfg, 'options':opts,
            'input_hashes':hashes, 'code_hashes':code, 'runtime':runtime,
            'baseline':baseline, 'parent':parent, 'gates':gates,
            'network_calls':0, 'qgis_started':False}


def isolated_engine():
    """Execute verified engine source; never monkey-patch the normal notebook module."""
    path = Path(metrics.__file__).resolve()
    module = types.ModuleType('lez._sensitivity_engine')
    module.__file__, module.__package__ = str(path), 'lez'
    exec(compile(path.read_text(), str(path), 'exec'), module.__dict__)
    return module


def score_adapter(original, assumptions):
    """C6 remains raw None; heterogeneous assumptions affect only normalized scores."""
    def score(result, options):
        rows, normalization = original(result, options)
        weight = normalization['effective_weights']['C6']
        for row in rows:
            if row['raw']['C6'] is not None or not weight:
                continue
            value = float(assumptions[row['route_id']])
            if not math.isfinite(value) or not 1 <= value <= 5:
                raise ValueError('C6 score-only feasible assumption must be in [1,5]')
            previous = row['normalized']['C6'] or 0.0
            row['normalized']['C6'] = value / 5
            row['score'] += 100 * weight * (value / 5 - previous)
            row['score_lower_unknown_C6'] = row['score'] - 100 * weight * value / 5
            row['score_upper_unknown_C6'] = row['score_lower_unknown_C6'] + 100 * weight
            row['C6_assumed_for_scoring_only'] = value
            row['C6_score_is_assumption'] = True
        normalization['C6_assumed_for_scoring_only'] = None
        normalization['C6_assumption_scope'] = 'route_specific_scenario_values_not_observations'
        return rows, normalization
    return score


def shifted_model(feature, attribute, shift, bounds):
    """Perturb only the missing-length contribution; preserve observed OSM values."""
    model = float(feature[attribute+'_scoring_model'])
    missing = float(feature[attribute+'_imputed_length_fraction'])
    if missing <= 1e-12:
        return model
    observed = feature.get(attribute)
    observed_term = float(observed) * (1 - missing) if observed is not None else 0.0
    missing_mean = (model - observed_term) / missing
    shifted_missing_mean = min(bounds[1], max(bounds[0], missing_mean + shift))
    return observed_term + missing * shifted_missing_mean


def scenario_data(base, spec, cfg):
    """Share immutable geometry/lengths, rebuild only scenario X and eligibility."""
    data = dict(base)
    data['features'] = [dict(r) for r in base['features']]
    exclude = set(spec.get('exclude_features', []))
    names = [n for n in metrics.FEATURES if n not in exclude]
    for row in data['features']:
        for attribute, size_key, bounds_key in (
                ('lanes', 'lane_shift', 'lane_model_bounds'),
                ('maxspeed', 'speed_shift', 'speed_model_bounds_kmh')):
            shift = spec.get(size_key, 0.0)
            if isinstance(shift, dict):
                shift = shift[row['route_id']]
            if shift:
                row[attribute+'_scoring_model'] = shifted_model(row, attribute, float(shift), cfg[bounds_key])
    raw = np.array([[r[n+'_scoring_model'] if n in ('lanes','maxspeed') else r[n] for n in names]
                    for r in data['features']], dtype=float)
    if not np.isfinite(raw).all():
        raise ValueError('X contains nonfinite scenario values')
    low, high = raw.min(axis=0), raw.max(axis=0)
    varying = high-low > cfg['constant_X_tolerance']
    active = [n for n, flag in zip(names, varying) if flag]
    if not active:
        raise ValueError('All X features are constant')
    canonical = (raw[:,varying]-low[varying])/(high-low)[varying]
    scaling = spec.get('scaling','minmax')
    mean, std = raw.mean(axis=0), raw.std(axis=0, ddof=0)
    if scaling == 'minmax':
        X = canonical
    elif scaling == 'zscore':
        X = (raw[:,varying]-mean[varying])/std[varying]
    else:
        raise ValueError('Unsupported X scaling: '+scaling)
    thresholds = {n:sorted(set(float(v) for v in np.quantile(canonical[:,j], [.25,.5,.75])))
                  for j,n in enumerate(active)}
    bins = [{(n,int(np.searchsorted(thresholds[n],canonical[i,j],side='right')))
             for j,n in enumerate(active)} for i in range(len(raw))]
    # Unchanged data use the exact original rank groups, including numerical ties.
    if not spec.get('lane_shift') and not spec.get('speed_shift'):
        bins = [{b for b in row if b[0] in active} for row in base['bins']]
    data.update(X=X,feature_names=active,bins=bins,
                distances=np.sqrt(((X[:,None,:]-X[None,:,:])**2).sum(axis=2)))
    blocked = set(spec.get('excluded_routes', []))
    ids = {r['route_id'] for r in data['features']}
    if not blocked.issubset(ids):
        raise ValueError('Unknown simulated unavailable route')
    data['eligible_indices'] = {i for i,r in enumerate(data['features']) if r['route_id'] not in blocked}
    params = {'method':scaling, 'fit_count':len(raw), 'ddof':0,
              'active_features':active,'dropped_constant':[n for n,f in zip(names,varying) if not f],
              'excluded_features':sorted(exclude),'raw_min':dict(zip(names,low.tolist())),
              'raw_max':dict(zip(names,high.tolist())), 'mean':dict(zip(names,mean.tolist())),
              'std':dict(zip(names,std.tolist())), 'quartiles_canonical_minmax':thresholds,
              'C3_rank_groups_unchanged':bins==base['bins'], 'model_is_observation':False}
    return data, params


def scenarios(base_ids, baseline_ids, cfg):
    specs = [{'id':'baseline','family':'baseline'}]
    def add(name, family, **values):
        specs.append({'id':name,'family':family,**values})
    add('X_zscore','scaling',scaling='zscore')
    for targets in ([f'C{i}'] for i in range(1,8)):
        for sign, factor in (('minus',1-cfg['weight_relative_change']),('plus',1+cfg['weight_relative_change'])):
            add('weight_'+targets[0]+'_'+sign+'20','weights',weight_factors={c:factor for c in targets})
    for label, targets in (('C1_C2',['C1','C2']),('C4_C5',['C4','C5'])):
        for sign,factor in (('minus',1-cfg['weight_relative_change']),('plus',1+cfg['weight_relative_change'])):
            add('weights_'+label+'_'+sign+'20','weights',weight_factors={c:factor for c in targets})
    add('constant_criteria_drop_renormalize','constant_rule',constant_criterion_policy='drop_and_renormalize_weights')
    for threshold in cfg['cell_thresholds']:
        if abs(threshold-.3)>1e-12:
            add('cell_fraction_'+str(threshold),'cell_threshold',cell_threshold=threshold)
    for names in (['lanes'],['maxspeed'],['lanes','maxspeed']):
        add('omit_'+'_'.join(names),'missing_features',exclude_features=names)
    for sign,direction in (('low',-1),('high',1)):
        lane=direction*cfg['lane_missing_component_shift']
        speed=direction*cfg['speed_missing_component_shift_kmh']
        add('missing_lanes_'+sign,'imputation',lane_shift=lane)
        add('missing_speed_'+sign,'imputation',speed_shift=speed)
        add('missing_both_'+sign,'imputation',lane_shift=lane,speed_shift=speed)
    add('C6_drop_weight','C6_policy',C6_missing_policy='unknown_weight_zero_renormalize_other_criteria')
    baseline_set=set(baseline_ids)
    for name,favored in (('favor_reserves',False),('favor_baseline',True)):
        values={rid:5 if (rid in baseline_set)==favored else 1 for rid in base_ids}
        add('C6_'+name,'C6_adversarial',C6_assumptions=values)
    sequence=np.random.SeedSequence(cfg['random_seed'])
    children=sequence.spawn(2*cfg['C6_random_runs_per_scaling']+cfg['combined_random_runs'])
    child_index=0
    for scaling in ('minmax','zscore'):
        for n in range(cfg['C6_random_runs_per_scaling']):
            child=children[child_index];child_index+=1;rng=np.random.default_rng(child)
            values=dict(zip(base_ids,map(int,rng.choice(cfg['C6_feasible_assumption_values'],len(base_ids)))))
            add(f'C6_random_{scaling}_{n+1:02d}','C6_random',scaling=scaling,
                C6_assumptions=values,seed_spawn_key=list(child.spawn_key))
    for n in range(cfg['combined_random_runs']):
        child=children[child_index];child_index+=1;rng=np.random.default_rng(child)
        values=dict(zip(base_ids,map(int,rng.choice(cfg['C6_feasible_assumption_values'],len(base_ids)))))
        lane=dict(zip(base_ids,map(float,rng.uniform(-cfg['lane_missing_component_shift'],cfg['lane_missing_component_shift'],len(base_ids)))))
        speed=dict(zip(base_ids,map(float,rng.uniform(-cfg['speed_missing_component_shift_kmh'],cfg['speed_missing_component_shift_kmh'],len(base_ids)))))
        factors={f'C{i}':float(rng.uniform(1-cfg['weight_relative_change'],1+cfg['weight_relative_change'])) for i in range(1,8)}
        add(f'combined_random_{n+1:02d}','combined_random',scaling='zscore' if n%2 else 'minmax',
            C6_assumptions=values,lane_shift=lane,speed_shift=speed,weight_factors=factors,
            cell_threshold=float(rng.choice(cfg['cell_thresholds'])),seed_spawn_key=list(child.spawn_key))
    for rid in sorted(baseline_ids):
        add('unavailable_'+rid,'availability',excluded_routes=[rid],simulated_C6_zero_routes=[rid])
    if cfg.get('quota_infeasibility_diagnostic'):
        # Nine unavailable C candidates leave 11: cannot silently change quota 12.
        blocked=[rid for rid in base_ids if rid.startswith('C')][:9]
        add('infeasible_C_capacity_11','diagnostic',excluded_routes=blocked,
            simulated_C6_zero_routes=blocked,expected_infeasible=True)
    if len({s['id'] for s in specs})!=len(specs):
        raise ValueError('Duplicate scenario identifiers')
    return specs


def comparison(ids, baseline_ids):
    current, base = set(ids),set(baseline_ids)
    return {'retained':len(current&base),'jaccard':len(current&base)/len(current|base),
            'removed':sorted(base-current),'added':sorted(current-base)}


def run_scenario(engine, base, options, spec, cfg, baseline_ids, baseline_greedy_ids):
    timer=time.monotonic();data,params=scenario_data(base,spec,cfg)
    opts=copy.deepcopy(options)
    opts['weights']={c:w*spec.get('weight_factors',{}).get(c,1) for c,w in opts['weights'].items()}
    for key in ('constant_criterion_policy','C6_missing_policy'):
        if key in spec: opts[key]=spec[key]
    opts['minimum_cell_fraction']=spec.get('cell_threshold',opts['minimum_cell_fraction'])
    original=engine.normalize_scores
    if spec.get('C6_assumptions'):
        engine.normalize_scores=score_adapter(original,spec['C6_assumptions'])
    try:
        selected,history,swaps,seeds=engine.select(data,opts)
    except ValueError as exc:
        capacity=Counter(metrics.quota_bucket(data['features'][i],opts) for i in data['eligible_indices'])
        return {'id':spec['id'],'family':spec['family'],'status':'infeasible',
                'reason':str(exc),'available_by_quota_bucket':dict(capacity),
                'expected_infeasible':spec.get('expected_infeasible',False),'spec':spec,
                'normalization':params,'elapsed_seconds':time.monotonic()-timer}
    finally:
        engine.normalize_scores=original
    if spec.get('expected_infeasible'):
        raise RuntimeError('Infeasibility diagnostic unexpectedly selected 30')
    final=engine.summary(data,selected,opts['minimum_cell_fraction'])
    expected={'A_inside':10,'B_inside':8,'C_outside':12}
    if final['quota_bucket_counts']!=expected or len(set(selected))!=30 or (final['inside'],final['outside'])!=(18,12):
        raise RuntimeError('Scenario violated exact quota')
    if any(data['features'][i]['C6'] is not None for i in selected):
        raise RuntimeError('Sensitivity must not invent field observations')
    ids=[data['walks'][i]['route_id'] for i in selected]
    if set(ids)&set(spec.get('excluded_routes',[])):
        raise RuntimeError('Swap reintroduced a simulated unavailable route')
    greedy_ids=history[-1]['selected_after']
    index={r['route_id']:i for i,r in enumerate(data['walks'])}
    greedy=engine.summary(data,[index[rid] for rid in greedy_ids],opts['minimum_cell_fraction'])
    # Cross-scenario metrics also use the same baseline 9-feature groups and 30% threshold.
    common=engine.summary(base,selected,options['minimum_cell_fraction'])
    effective=history[-1]['normalization']['effective_weights']
    return {'id':spec['id'],'family':spec['family'],'status':'completed','spec':spec,
            'selected_route_ids':ids,'greedy_selected_route_ids':greedy_ids,
            'comparison':comparison(ids,baseline_ids),'greedy_comparison':comparison(greedy_ids,baseline_greedy_ids),
            'metrics':final,'metrics_common_basis':common,'before_swaps':greedy,
            'accepted_swaps':swaps,'seed_runs':seeds,'normalization':params,
            'effective_weights_final_round':effective,
            'cell_threshold':opts['minimum_cell_fraction'],'C6_observation_count':0,
            'elapsed_seconds':time.monotonic()-timer,
            'chosen_greedy_rounds':[{'round':r['round'],'chosen':r['chosen'],
                 'score':next(c['score'] for c in r['candidates'] if c['route_id']==r['chosen'])}
                 for r in history[1:]]}


def family_summary(results):
    rows=[]
    for name in sorted({r['family'] for r in results if r['family']!='baseline'}):
        group=[r for r in results if r['family']==name];done=[r for r in group if r['status']=='completed']
        rows.append({'family':name,'total':len(group),'completed':len(done),'infeasible':len(group)-len(done),
                     'unchanged':sum(r['comparison']['retained']==30 for r in done),
                     'min_retained':min((r['comparison']['retained'] for r in done),default=None),
                     'max_replaced':max((len(r['comparison']['removed']) for r in done),default=None),
                     'min_jaccard':min((r['comparison']['jaccard'] for r in done),default=None),
                     'max_D':max((r['metrics']['D_combined'] for r in done),default=None),
                     'min_D':min((r['metrics']['D_combined'] for r in done),default=None)})
    return rows


def frequency_rows(data, results, baseline_ids):
    rows=[]
    # Availability trials deliberately remove each baseline route: never mix with scoring stability.
    families=sorted({r['family'] for r in results}-{'baseline','availability','diagnostic'})
    sets=[('all_scoring_stress', [r for r in results if r['family'] in families and r['status']=='completed'])]
    sets += [(f,[r for r in results if r['family']==f and r['status']=='completed']) for f in families]
    for scope,group in sets:
        if not group:continue
        for feature in data['features']:
            rid=feature['route_id'];count=sum(rid in r['selected_route_ids'] for r in group)
            rows.append({'scope':scope,'route_id':rid,'sampling_zone':feature['sampling_zone'],
                         'rc_target':feature['rc_target'],'baseline_selected':rid in baseline_ids,
                         'selected_count':count,'scenario_count':len(group),'selection_fraction':count/len(group),
                         'lanes_known_length_fraction':feature['lanes_known_length_fraction'],
                         'maxspeed_known_length_fraction':feature['maxspeed_known_length_fraction'],
                         'C6_actual':None,'fraction_is_probability':False})
    return rows


def write_report(directory, report, results, features):
    base=next(r for r in results if r['id']=='baseline');fam=report['families']
    rows=[]
    for r in results:
        c=r.get('comparison',{});m=r.get('metrics',{});common=r.get('metrics_common_basis',{})
        rows.append({'scenario':r['id'],'family':r['family'],'status':r['status'],'reason':r.get('reason',''),
                     'retained':c.get('retained'),'replaced':len(c.get('removed',[])),'jaccard':c.get('jaccard'),
                     'removed':';'.join(c.get('removed',[])),'added':';'.join(c.get('added',[])),
                     'D':m.get('D_combined'),'D_inside':m.get('D_by_domain',{}).get('inside'),
                     'D_outside':m.get('D_by_domain',{}).get('outside'),
                     'unique_RC_coverage_fraction':m.get('unique_rc_coverage_fraction'),
                     'material_cells_scenario_threshold':m.get('material_cells'),
                     'material_cells_common_30pct':common.get('material_cells'),
                     'quantile_groups_scenario_X':m.get('quantile_groups_covered'),
                     'quantile_groups_common_9_features':common.get('quantile_groups_covered'),
                     'max_unique_corridor_overlap':m.get('max_unique_corridor_overlap_fraction'),
                     'greedy_retained':r.get('greedy_comparison',{}).get('retained'),
                     'swaps':len(r.get('accepted_swaps',[])),'quota_ok':r['status']=='completed',
                     'seconds':r['elapsed_seconds']})
    write_csv(directory/'scenario_summary.csv',rows,list(rows[0]))
    write_csv(directory/'families.csv',fam,list(fam[0]))
    frequency=report.pop('_frequency_rows')
    write_csv(directory/'route_frequency.csv',frequency,list(frequency[0]))
    write_csv(directory/'input_completeness.csv',features,list(features[0]))
    zero=[r for r in results if r['family']=='availability']
    availability=[{'excluded':r['spec']['excluded_routes'][0],'status':r['status'],
                  'added':';'.join(r.get('comparison',{}).get('added',[])),
                  'also_removed':';'.join(set(r.get('comparison',{}).get('removed',[]))-set(r['spec']['excluded_routes'])),
                  'D':r.get('metrics',{}).get('D_combined'),'reason':r.get('reason','')}
                 for r in zero]
    write_csv(directory/'simulated_replacements.csv',availability,list(availability[0]))
    atomic_json(directory/'results.json',results)
    text=['# Kiểm tra độ nhạy bộ 30 trước khảo sát','',
          '**Đã chạy lại thuật toán chọn tuyến**, không suy từ khoảng cách láng giềng. Giữ A10/B8/C12 = 18 trong/12 ngoài, 10 seed và swap như cấu hình gốc. Bộ 30 công bố được giữ nguyên.','',
          f"Đầu vào: `{report['baseline_directory']}`; snapshot {report['snapshot_utc']}. Baseline tái lập đúng thứ tự; D={base['metrics']['D_combined']:.8f}.", '',
          f"Hoàn tất {report['completed_scenarios']}/{report['total_scenarios']} lượt chọn; {report['expected_infeasible_scenarios']} ca không đủ quota có chủ đích, {report['unexpected_infeasible_scenarios']} ca không giải quyết. Ba ngưỡng cờ overlap được đánh giá riêng, không tính là ba lượt chọn.", '',
          '| Nhóm thử | Hoàn tất | Giữ nguyên bộ 30 | Giữ ít nhất | Jaccard nhỏ nhất | D nhỏ nhất–lớn nhất |',
          '|---|---:|---:|---:|---:|---|']
    labels={'scaling':'Chuẩn hóa X','weights':'Trọng số ±20%','constant_rule':'Tiêu chí hằng',
            'cell_threshold':'P_ô 25–40%','missing_features':'Bỏ mô hình làn/tốc độ',
            'imputation':'Đổi giá trị cho phần chiều dài thiếu','C6_policy':'Bỏ trọng số C6',
            'C6_adversarial':'C6 1/5 đối nghịch','C6_random':'C6 khác nhau, giả lập có seed',
            'combined_random':'Giả lập kết hợp','availability':'Giả lập một tuyến C6=0','diagnostic':'Thiếu khả năng đạt quota'}
    for f in fam:
        rng=f"{f['min_D']:.6f}–{f['max_D']:.6f}" if f['completed'] else '—'
        text.append(f"| {labels.get(f['family'],f['family'])} | {f['completed']}/{f['total']} | {f['unchanged']} | {f['min_retained'] if f['completed'] else '—'} | {f['min_jaccard']:.4f} | {rng} |" if f['completed'] else f"| {labels.get(f['family'],f['family'])} | 0/{f['total']} | — | — | — | — |")
    z=next(r for r in results if r['id']=='X_zscore')
    text += ['',f"Min–max → z-score: giữ {z['comparison']['retained']}/30, J={z['comparison']['jaccard']:.4f}; bỏ {', '.join(z['comparison']['removed']) or 'không có'}, thêm {', '.join(z['comparison']['added']) or 'không có'}. Trước swap giữ {z['greedy_comparison']['retained']}/30 so với greedy cơ sở.", '',
             f"Lõi chung trong {report['scoring_stress_scenarios']} kịch bản chấm điểm: {len(report['scoring_common_core'])} tuyến: {', '.join(report['scoring_common_core']) or 'không có'}. Không đưa các ca cố ý loại tuyến vào mẫu số độ ổn định.", '',
             'Tần suất trong `route_frequency.csv` là tỷ lệ trong tập kịch bản đã thiết kế, **không phải xác suất được chọn hoặc khoảng tin cậy**. Xem riêng từng nhóm; không dùng tần suất gộp để tự thay bộ 30.', '',
             'Làn/tốc độ: bỏ lần lượt và đồng thời; dịch phần chiều dài thiếu ±1 làn/±10 km/h; giữ phần quan sát. Đây là biên thử do người phân tích đặt, không phải thông số thực địa. Chuẩn hóa lại X trên đủ 60 ở mỗi kịch bản, z-score ddof=0. C1–C5 vẫn min–max mỗi vòng; quartile không đổi chỉ do thay scale.', '',
             'C6: đối nghịch 1/5 và giả lập từng tuyến 1–5 khi giả định còn khả thi. C6=0 chỉ thử bằng loại khỏi khả dụng; swap không được đưa lại tuyến đó. Tất cả C6 thật vẫn NULL, G1/G4/G5/G6 vẫn chờ khảo sát. Thay C6 đồng loạt cho mọi tuyến không đủ thử thay đổi thứ hạng.', '',
             'Độ phủ RC là chiều dài phần đường vật lý được bộ tuyến chạm tới (đếm một lần) chia chiều dài mạng RC mục tiêu. D dùng cơ cấu chiều dài lượt đi RC; D thấp hơn không chứng minh đạt thực địa hay tối ưu toàn cục. Cột `*_common_basis` dùng cùng 9 biến và ngưỡng ô 30% để so sánh khi bỏ biến/đổi ngưỡng.', '',
             'Ma trận giữ đủ 12 ô; A×RC1 vẫn không có ứng viên đủ điều kiện. Không thay ranh giới, quota, graph, OSM, cổng kiểm tra hay sinh chu trình lái.', '',
             'Ưu tiên xác minh các tuyến thay đổi giữa kịch bản, làn/tốc độ còn thiếu và C6 có khả năng đổi lựa chọn. `simulated_replacements.csv` chỉ gợi ý thay thế khi giả lập một tuyến không khả thi; chưa xác nhận tuyến dự phòng thực tế.', '',
             'Chạy/tiếp tục ở notebook 06, hoặc:', '',
             '```bash','python3 work/scripts/lez/selection_sensitivity.py preflight',
             'python3 work/scripts/lez/selection_sensitivity.py run',
             'python3 work/scripts/lez/selection_sensitivity.py status','```', '',
             '`force=False` dùng cache đã xác minh hash của từng kịch bản. Ctrl+C giữ kịch bản đã xong; chạy lại cùng cấu hình để tiếp tục. Đổi cấu hình/đầu vào/mã tạo bundle mới. Đây là nghiên cứu trước khảo sát, không phải nghiệm thu bộ tuyến.','']
    atomic_bytes(directory/'REPORT.md','\n'.join(text).encode())


@contextmanager
def output_lock(root):
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.sensitivity.lock').open('a+') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise RuntimeError('Another sensitivity run uses this output root') from exc
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)


def sensitivity_status(work=WORK):
    path=Path(work)/'reports/selection/latest_sensitivity.json'
    return json.loads(path.read_text()) if path.exists() else {'status':'not_run'}


def run_sensitivity(work=WORK, force=False, progress=print, config_path=None, output_root=None):
    work=Path(work).resolve();check=preflight_sensitivity(work,config_path)
    cfg,opts,baseline=check['protocol'],check['options'],check['baseline']
    root=Path(output_root).resolve() if output_root else work/'data/processed/selection_sensitivity'
    directory=root/check['fingerprint'][:20]
    with output_lock(root):
        cache=None if force else cached_manifest(directory,check['fingerprint'])
        if cache:
            result=dict(cache['report'],cache_hit=True)
            if output_root is None:atomic_json(work/'reports/selection/latest_sensitivity.json',result)
            return result
        started,timer=now(),time.monotonic();directory.mkdir(parents=True,exist_ok=True)
        atomic_json(directory/'inputs.json',{k:v for k,v in check.items() if k not in ('baseline','parent','gates')})
        if progress:progress('Đọc dữ liệu đã kiểm tra; tái lập baseline trước khi thử độ nhạy.',flush=True) if progress is print else progress('Đọc dữ liệu đã kiểm tra; tái lập baseline trước khi thử độ nhạy.')
        base=metrics.load_data(work,check['parent'],opts)
        ids=[r['route_id'] for r in base['walks']]
        for f in base['features']:
            gate=check['gates']['routes'][f['route_id']]
            f.update(G3=gate['G3'],pre_survey_admissible=gate['pre_survey_admissible'])
        engine=isolated_engine()
        specs=scenarios(ids,baseline['selected_route_ids'],cfg)
        atomic_json(directory/'protocol.json',{'config':cfg,'scenarios':specs})
        baseline_dir=input_path(work,baseline['paths']['directory'])
        baseline_history=json.loads((baseline_dir/'selection_history.json').read_text())
        greedy_ids=baseline_history[-1]['selected_after']
        results=[];new_count=cache_count=0
        output_names=['inputs.json','protocol.json']
        for n,spec in enumerate(specs,1):
            name='scenarios/'+spec['id']+'.json';path=directory/name
            scenario_fingerprint=digest({'run':check['fingerprint'],'spec':spec})
            cached=None
            if path.exists() and not force:
                try:
                    value=json.loads(path.read_text());content=value['result']
                    if (value['fingerprint']==scenario_fingerprint and value['result_hash']==digest(content)
                            and content['spec']==spec and content['status'] in ('completed','infeasible')):
                        cached=content
                except (ValueError,KeyError,TypeError,OSError):pass
            if cached is None:
                result=run_scenario(engine,base,opts,spec,cfg,baseline['selected_route_ids'],greedy_ids)
                atomic_json(path,{'fingerprint':scenario_fingerprint,'result_hash':digest(result),'result':result})
                new_count+=1
            else:result=cached;cache_count+=1
            if spec['id']=='baseline':
                if result['status']!='completed' or result['selected_route_ids']!=baseline['selected_route_ids']:
                    raise RuntimeError('Full baseline rerun did not reproduce published route order')
                if abs(result['metrics']['D_combined']-baseline['metrics']['D_combined'])>1e-12:
                    raise RuntimeError('Baseline D differs from published result')
            results.append(result);output_names.append(name)
            if progress:
                message=f"[{n}/{len(specs)}] {spec['id']}: {result['status']}"
                if result['status']=='completed':message+=f"; giữ {result['comparison']['retained']}/30; D={result['metrics']['D_combined']:.6f}"
                progress(message,flush=True) if progress is print else progress(message)
            atomic_json(directory/'progress.json',{'status':'running','completed_scenarios':n,
                'total_scenarios':len(specs),'last_scenario':spec['id'],'updated_at':now(),
                'new_scenarios':new_count,'cached_scenarios':cache_count})
        completed=[r for r in results if r['status']=='completed']
        expected=[r for r in results if r['status']=='infeasible' and r.get('expected_infeasible')]
        unexpected=[r for r in results if r['status']=='infeasible' and not r.get('expected_infeasible')]
        scoring=[r for r in completed if r['family'] not in ('baseline','availability','diagnostic')]
        core=sorted(set.intersection(*(set(r['selected_route_ids']) for r in scoring))) if scoring else []
        flags=[]
        selected_indices=[ids.index(rid) for rid in baseline['selected_route_ids']]
        for threshold in cfg['overlap_review_thresholds']:
            pairs=[{'left':ids[i],'right':ids[j],'traversed_overlap':float(base['overlaps'][i,j]),
                    'unique_corridor_overlap':float(base['corridors'][i,j])}
                   for p,i in enumerate(selected_indices) for j in selected_indices[p+1:]
                   if base['overlaps'][i,j]>=threshold]
            flags.append({'threshold':threshold,'flagged_pairs':len(pairs),'pairs':pairs,
                          'changes_selection':False,'hard_corridor_cap':opts['max_corridor_overlap']})
        atomic_json(directory/'overlap_review_only.json',flags)
        frequency=frequency_rows(base,results,set(baseline['selected_route_ids']))
        features=[{k:r.get(k) for k in ('route_id','sampling_zone','rc_target','lanes','maxspeed',
            'lanes_known_length_fraction','maxspeed_known_length_fraction','lanes_scoring_model','maxspeed_scoring_model','C6','G1','G4','G5','G6')}
            for r in base['features']]
        report={'status':'completed_with_unresolved_scenarios' if unexpected else 'completed_pre_survey_sensitivity',
                'fingerprint':check['fingerprint'],'started_at':started,'finished_at':now(),
                'elapsed_seconds':time.monotonic()-timer,'cache_hit':False,'network_calls':0,'qgis_started':False,
                'new_scenarios':new_count,'cached_scenarios':cache_count,'total_scenarios':len(specs),
                'completed_scenarios':len(completed),'expected_infeasible_scenarios':len(expected),
                'unexpected_infeasible_scenarios':len(unexpected),'unresolved':[{'id':r['id'],'reason':r['reason']} for r in unexpected],
                'quota':opts['quota'],'intersection_quota':opts['intersection_quota'],
                'baseline_reproduced_exactly':True,'baseline_directory':relative(baseline_dir,work),
                'baseline_selected_ids':baseline['selected_route_ids'],'baseline_metrics':baseline['metrics'],
                'snapshot_utc':baseline['snapshot_utc'],'policy_version':baseline['policy_version'],
                'baseline_selection_modified':False,'raw_OSM_modified':False,'field_observations_created':0,
                'scoring_stress_scenarios':len(scoring),'scoring_common_core':core,
                'families':family_summary(results),'overlap_review_flag_counts':[{k:r[k] for k in ('threshold','flagged_pairs','changes_selection')} for r in flags],
                'missing_pool_cells':baseline['missing_cells_in_entire_pool'],'_frequency_rows':frequency,
                'paths':{k:relative(directory/name,work) for k,name in (
                    ('directory','.'),('report','REPORT.md'),('summary','scenario_summary.csv'),
                    ('frequency','route_frequency.csv'),('replacements','simulated_replacements.csv'),
                    ('results','results.json'),('inputs','inputs.json'),('protocol','protocol.json'))},
                'limitations':['Scenario frequencies are not probabilities or confidence intervals.',
                  'C6 and survey gates remain unknown; simulated values do not certify field feasibility.',
                  'Frozen candidate pool and research geometry only; no boundary uncertainty or global optimum proof.',
                  'Overlapping/linked X variables are retained as in the original design; scaling does not remove dependence.']}
        write_report(directory,report,results,features)
        atomic_json(directory/'report.json',report)
        output_names+=['results.json','report.json','REPORT.md','families.csv','scenario_summary.csv',
                       'route_frequency.csv','input_completeness.csv','simulated_replacements.csv','overlap_review_only.json']
        # A long run must not be published as current if source bytes changed during it.
        for name,expected_hash in check['input_hashes'].items():
            if file_hash(input_path(work,name))!=expected_hash:
                raise RuntimeError('Input changed during sensitivity run: '+name)
        commit_manifest(directory,check['fingerprint'],report,output_names)
        atomic_json(directory/'progress.json',{'status':report['status'],'processed_scenarios':len(specs),
                    'total_scenarios':len(specs),'updated_at':now()})
        if output_root is None:atomic_json(work/'reports/selection/latest_sensitivity.json',report)
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['preflight','run','status'])
    parser.add_argument('--work',type=Path,default=WORK)
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--config',type=Path)
    parser.add_argument('--output-root',type=Path)
    args=parser.parse_args()
    if args.command=='run':result=run_sensitivity(args.work,args.force,config_path=args.config,output_root=args.output_root)
    elif args.command=='status':result=sensitivity_status(args.work)
    else:
        check=preflight_sensitivity(args.work,args.config)
        result={k:check[k] for k in ('status','fingerprint','network_calls','qgis_started','runtime')}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
