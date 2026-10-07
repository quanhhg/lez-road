"""Automate strata and RC normalization independently of route generation or selection."""
from __future__ import annotations

if __package__ in (None, ''):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'lez'

import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

from .common import (WORK, atomic_json, cached_manifest, code_hash, commit_manifest,
                     digest, file_hash, input_path, now, processing_lock, publish_link, relative, write_csv)


def validate_cached_inputs(work, options):
    """Verify exact raw hashes, request identity and derived values, without HTTP."""
    from .sampling_data import _cached_response, validate_activity
    work = Path(work)
    prepared = json.loads((work / 'data/interim/sampling/requests.json').read_text())
    activity = json.loads(input_path(work, options['activity_input']).read_text())
    population = json.loads(input_path(work, options['population_input']).read_text())
    if prepared['snapshot_utc'] != options['source_snapshot_utc'] or activity['snapshot_utc'] != prepared['snapshot_utc']:
        raise ValueError('Normalization inputs have inconsistent OSM snapshots')
    if activity['endpoint'] != prepared['endpoint'] or not activity['complete'] or not population['complete']:
        raise ValueError('Population/activity inputs are incomplete or have different source configuration')
    if population['year'] != 2025:
        raise ValueError('Expected modeled population year 2025')
    folder = work / 'data/raw/sampling'
    expected_features = []
    raw_paths = []
    for task in prepared['activity_queries']:
        name = task['name']
        raw = folder / ('activity_' + name + '.json')
        identity = digest({'query':task['query'], 'endpoint':prepared['endpoint'], 'snapshot':prepared['snapshot_utc']})
        payload = _cached_response(raw, raw.with_suffix('.manifest.json'), identity)
        if payload is None or file_hash(raw) != activity['source_hashes'].get(name):
            raise ValueError('Activity cache hash/request mismatch: ' + name)
        validate_activity(payload, prepared['snapshot_utc'])
        for item in payload['elements'][:-1]:
            point = item if item['type'] == 'node' else item['center']
            expected_features.append({'osm_key':item['type'] + '/' + str(item['id']), 'category':name,
                                      'lon':point['lon'], 'lat':point['lat'], 'tags':item.get('tags', {})})
        raw_paths.append(raw)
    if digest(expected_features) != digest(activity['features']):
        raise ValueError('Derived activity features do not match immutable raw responses')
    tasks = prepared['population_tasks']
    expected = {task['task_key']: task for task in tasks}
    actual = {part['task_key']: part for part in population['parts']}
    if len(expected) != len(tasks) or len(actual) != len(population['parts']) or set(actual) != set(expected):
        raise ValueError('Population task identifiers are duplicated or incomplete')
    if digest(population['expected_tasks']) != digest(tasks):
        raise ValueError('Population geometry requests have changed; refresh missing inputs first')
    for key, part in actual.items():
        task = expected[key]
        raw = folder / ('population_' + key + '.json')
        identity = digest({'url':population['api'], 'body':task['body']})
        payload = _cached_response(raw, raw.with_suffix('.manifest.json'), identity)
        if payload is None or file_hash(raw) != part['response_sha256']:
            raise ValueError('Population cache hash/request mismatch: ' + key)
        result = payload.get('result', {})
        if payload.get('status') != 'success' or result.get('data_year') != part['year'] or part['year'] != 2025:
            raise ValueError('Population response status/year mismatch: ' + key)
        if part['population'] != result.get('total_population') or part['source'] != result.get('data_source'):
            raise ValueError('Derived population value/source does not match raw response: ' + key)
        if part['admin_id'] != task['admin_id'] or part['area_m2'] != task['area_m2']:
            raise ValueError('Population unit/area does not match requested geometry: ' + key)
        if not math.isfinite(part['population']) or part['population'] < 0 or not math.isfinite(part['area_m2']) or part['area_m2'] <= 0:
            raise ValueError('Invalid population value/area: ' + key)
        raw_paths.append(raw)
    return {'status':'validated_against_raw_cache', 'population_parts':len(actual),
            'activity_queries':len(prepared['activity_queries']), 'activity_records':len(expected_features),
            'network_calls':0, 'raw_hashes':{relative(p,work):file_hash(p) for p in raw_paths}}


def normalization_status(work=WORK):
    path = Path(work) / 'reports/sampling/latest_normalization_2030.json'
    return json.loads(path.read_text()) if path.exists() else {'status':'not_run'}


def execute_normalization(work=WORK, force=False):
    from .sampling_2030 import _load_geometries, build_scope, config, overlay_network, rc_composition
    work = Path(work)
    options, policy = config(work)
    validation = validate_cached_inputs(work, options)
    boundary = json.loads((work / 'config/boundary_project.json').read_text())
    inputs = [work/'config/sampling_2030.json', work/'config/sampling_boundary_policy.json',
              work/'config/boundary_automation.json',work/'config/boundary_project.json',
              input_path(work,boundary['hanoi_source']['path']),
              input_path(work,policy['legal_reference']['geometry_path']),
              input_path(work,policy['legal_reference']['source_file'])]
    inputs += [input_path(work,options[k]) for k in ['boundary_admin_path','network_path','graph_path','population_input','activity_input']]
    fingerprint = digest({'stage':'strata_and_network_normalization_without_route_generation',
                          'inputs':{relative(p,work):file_hash(p) for p in inputs},
                          'raw_cache':validation['raw_hashes'],
                          'code':code_hash(['common.py','gis.py','graph.py','routing.py','sampling_2030.py','normalization_2030.py'])})
    directory = work / 'data/processed/normalization_2030' / fingerprint[:20]
    with processing_lock(work):
        cached = None if force else cached_manifest(directory, fingerprint)
        if cached:
            result = dict(cached['report'], cache_hit=True)
        else:
            started, timer = now(), time.monotonic()
            directory.mkdir(parents=True, exist_ok=True)
            loaded = _load_geometries(work)
            scope = build_scope(work,directory,loaded)
            overlay = overlay_network(work,directory,loaded,scope)
            _, _, connectors, metrics = rc_composition(overlay[-2])
            write_csv(directory/'connector_summary.csv',connectors,
                      ['stratum_id','group','rc','network_length_m','included_in_rc_composition'])
            # Explicit table for the changed polygon parts, not entire communes/wards.
            import csv
            with (directory/'boundary_decisions.csv').open(encoding='utf-8',newline='') as stream:
                decisions=list(csv.DictReader(stream))
            changed=[r for r in decisions if r['changed'].lower() in ('true','1')]
            write_csv(directory/'adjusted_boundary_parts.csv',changed,list(decisions[0]))
            checks = {'input_raw_cache_verified':True, 'strata_count':scope[-1]['strata'],
                      'pending_evidence_parts':scope[-1]['pending_evidence_units'],
                      'changed_parts':len(changed),
                      'outside_to_inside':sum(r['reference_group']=='outside' for r in changed),
                      'inside_to_outside':sum(r['reference_group']=='inside' for r in changed),
                      'network_fraction_sum':metrics['network_fraction_sum'],
                      'network_domain_fraction_sums':{g:sum(r['network_fraction_domain_rc'] for r in rc_composition(overlay[-2])[0] if r['group']==g) for g in ('inside','outside')},
                      'max_part_length_error_m':overlay[-1]['max_part_length_error_m'],
                      'aggregate_length_error_m':overlay[-1]['aggregate_length_error_m'],
                      'changes_outside_band_m2':scope[-1]['adjustment_outside_band_m2']}
            if abs(checks['network_fraction_sum']-1)>1e-10 or any(abs(v-1)>1e-10 for v in checks['network_domain_fraction_sums'].values()):
                raise ValueError('RC proportions fail global/domain normalization')
            atomic_json(directory/'normalization_checks.json', checks)
            result = {'status':'normalized_research_scope_ready_for_pre_survey_selection',
                      'started_at':started,'finished_at':now(),'elapsed_seconds':time.monotonic()-timer,
                      'cache_hit':False,'scope':'user_selected_LEZ2030','boundary':scope[-1],
                      'overlay':overlay[-1],'checks':checks,'input_validation':validation,
                      'network_calls':0,'raw_osm_modified':False,'route_generation_performed':False,
                      'selection_30_performed':False,'official_gis_verified':False,
                      'paths':{'directory':relative(directory,work),
                               'zones':relative(directory/'sampling_zones.gpkg',work),
                               'parts':relative(directory/'network_parts.gpkg',work),
                               'network_matrix':relative(directory/'network_matrix.csv',work),
                               'connector_summary':relative(directory/'connector_summary.csv',work),
                               'boundary_decisions':relative(directory/'boundary_decisions.csv',work),
                               'adjusted_boundary_parts':relative(directory/'adjusted_boundary_parts.csv',work),
                               'assignment_trace':relative(directory/'strata_assignment_trace.csv',work)}}
            atomic_json(directory/'report.json',result)
            outputs=[p.name for p in directory.iterdir() if p.is_file() and not p.name.startswith('.') and p.name!='manifest.json']
            commit_manifest(directory,fingerprint,result,outputs)
        for name,target in [('sampling_2030.gpkg','sampling_zones.gpkg'),('network_parts_2030.gpkg','network_parts.gpkg')]:
            publish_link(work,name,directory/target)
        atomic_json(work/'reports/sampling/latest_normalization_2030.json',result)
    return result


def run_normalization(work=WORK, fetch=False, force=False, progress=print):
    """Ordinary Python controller; fetch=False ensures no HTTP requests."""
    from .sampling_2030 import config, preflight_sampling
    from .pipeline import kernel_spec
    work = Path(work).resolve()
    preflight_sampling(work,progress=progress)
    if fetch:
        from .sampling_data import fetch_inputs
        fetch_inputs(work,progress)
    options,_ = config(work)
    validation=validate_cached_inputs(work,options)
    atomic_json(work/'reports/sampling/normalization_input_validation.json',validation)
    spec=kernel_spec();env=os.environ.copy();env.update(spec.get('env',{}))
    args=[spec['argv'][0],str(Path(__file__).resolve()),'build','--work',str(work)]
    if force:args.append('--force')
    process=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    result=None;recent=[]
    try:
        for line in process.stdout:
            recent.append(line.strip());recent=recent[-20:]
            try:message=json.loads(line)
            except ValueError:
                if progress:progress(line.strip())
                continue
            if message.get('event')=='result':result=message['result']
            elif progress:progress(message)
        if process.wait() or result is None:raise RuntimeError('Normalization worker failed:\n'+'\n'.join(recent))
        return result
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
        if progress:progress('Đã dừng; phiên bản hoàn chỉnh được giữ, chạy lại cùng cấu hình để tiếp tục.')
        return normalization_status(work)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','build','status'])
    parser.add_argument('--work',type=Path,default=WORK)
    parser.add_argument('--fetch',action='store_true')
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    result=execute_normalization(args.work,args.force) if args.command=='build' else normalization_status(args.work) if args.command=='status' else run_normalization(args.work,args.fetch,args.force)
    print(json.dumps({'event':'result','result':result},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
