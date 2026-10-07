"""Offline LEZ-first workflow up to measurement QC; no driving-cycle creation."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'lez'
from .common import WORK, atomic_json, file_hash, input_path, now, relative
VERSION='LEZ_FIRST_AUTOMATION_v2_sensitivity'
REPORT='reports/automation/latest_project_automation.json'


def preflight(work=WORK):
    """Check inputs/configuration only; no network call, no new geometry."""
    from .sampling_abc import preflight as sampling_preflight, configuration
    from .selection_30 import configuration as selection_configuration
    from .trip_processing import load_config
    from .field_workflow import config as field_config
    from .selection_sensitivity import protocol as sensitivity_protocol
    work=Path(work).resolve()
    sampling=configuration(work);selection=selection_configuration(work)
    policy=json.loads((work/'config/lez_policy.json').read_text())
    if policy.get('classification_basis')!='dated_LEZ2027_pilot_and_LEZ2030_planned_ring3':
        raise ValueError('Unexpected LEZ-first boundary configuration')
    if len({v['policy_version'] for v in (sampling,selection,policy)})!=1:
        raise ValueError('Policy versions differ; refuse mixed LEZ scopes')
    if not sampling.get('method_version','').startswith('ABC_LEZ_FIRST_') or selection.get('zone_basis')!='LEZ_first':
        raise ValueError('Current design must use LEZ-first zones')
    if policy.get('allow_population_activity_boundary_adjustments') is not False:
        raise ValueError('Policy boundaries must not be moved for quotas')
    requirements=json.loads((work/'data/raw/research/source_requirements.json').read_text())
    if requirements['current_request'].get('driving_cycle_construction_requested'):
        raise ValueError('Current automation excludes driving-cycle construction')
    for item in policy['sources']:
        if file_hash(input_path(work,item['file']))!=item['sha256']:
            raise ValueError('Official source hash mismatch: '+item['file'])
    audit=json.loads((work/'reports/overpass/completion_audit.json').read_text())
    with (work/'data/hanoi_tiles/tiles.csv').open() as stream:
        import csv
        states=Counter(r['status'] for r in csv.DictReader(stream) if r['status']!='split')
    if set(states)!={'done'}:raise ValueError('OSM source tiles are not all completed: '+str(states))
    result=sampling_preflight(work)
    load_config(work);field_config(work)
    sensitivity=sensitivity_protocol(work)
    return dict(result,status='ready',method_version=VERSION,source_tile_states=dict(states),
                policy_version=policy['policy_version'],raw_source_audit=relative(work/'reports/overpass/completion_audit.json',work),
                raw_osm_modified=False,driving_cycle_constructed=False,
                sensitivity_method_version=sensitivity['method_version'],
                sensitivity_config=relative(work/'config/selection_sensitivity.json',work))


def status(work=WORK):
    path=Path(work)/REPORT
    return json.loads(path.read_text()) if path.is_file() else {'status':'not_run'}


def maps_cached(work):
    """Reuse maps only when every source and export hash still matches."""
    path=work/'maps/routes/route_maps_manifest.json'
    try:
        m=json.loads(path.read_text())
        if m.get('scope')!='LEZ2027_A_LEZ2030_minus_A_B_outside_LEZ2030_C':return False
        if any(not Path(p).is_file() or file_hash(p)!=h for p,h in m['source_hashes'].items()):return False
        return all((path.parent/n).is_file() and file_hash(path.parent/n)==h
                   for e in m['exports'] for n,h in e['files'].items())
    except (OSError,ValueError,KeyError):return False


def validate_sensitivity(sensitivity, selected, work):
    """Do not mark orchestration complete with unresolved or stale sensitivity."""
    unresolved=sensitivity.get('unexpected_infeasible_scenarios',0)
    if unresolved or sensitivity.get('status')!='completed_pre_survey_sensitivity':
        raise ValueError('Sensitivity has unresolved scenarios: '+str(sensitivity.get('unresolved',[])))
    if (not sensitivity.get('baseline_reproduced_exactly') or
            sensitivity.get('baseline_selected_ids')!=selected['selected_route_ids'] or
            sensitivity.get('policy_version')!=selected['policy_version'] or
            input_path(work,sensitivity['baseline_directory'])!=input_path(work,selected['paths']['directory'])):
        raise ValueError('Sensitivity baseline does not match the selected 30-route bundle')
    completed=sensitivity['completed_scenarios'];expected=sensitivity['expected_infeasible_scenarios']
    total=sensitivity['total_scenarios']
    if (any(not isinstance(n,int) or n<0 for n in (completed,expected,total)) or
            not total or completed+expected!=total):
        raise ValueError('Sensitivity scenario counts are incomplete')
    if sensitivity.get('network_calls')!=0 or sensitivity.get('baseline_selection_modified') is not False:
        raise ValueError('Sensitivity must remain offline and preserve the published selection')


def run(work=WORK, *, force=False, progress=print, observations=None, input_dir=None):
    """Resume independent verified caches; preserve completed steps on interruption."""
    from .sampling_abc import run_sampling
    from .selection_30 import run_selection
    from .selection_sensitivity import run_sensitivity
    from .export_route_maps import export_maps
    from .field_workflow import prepare, status as field_status, import_observations, build_update_plan
    from .trip_processing import prepare as prepare_trips, run as process_trips, load_config
    from .survey_revision import run as revise_survey
    work=Path(work).resolve();check=preflight(work);timer=time.monotonic()
    report={'status':'running','method_version':VERSION,'started_at':now(),'policy_version':check['policy_version'],
            'steps':{},'step_seconds':{},'network_calls':0,'raw_osm_modified':False,'driving_cycle_constructed':False,
            'measurement_verified':False,'preflight':check}
    def step(name,fn):
        report['active_step']=name;atomic_json(work/REPORT,report)
        if progress:progress('Đang xử lý: '+name)
        step_timer=time.monotonic()
        value=fn();report['steps'][name]=value
        report['step_seconds'][name]=time.monotonic()-step_timer
        report['elapsed_seconds']=time.monotonic()-timer;atomic_json(work/REPORT,report)
        return value
    try:
        pool=step('sampling_60',lambda:run_sampling(work,force=force,progress=progress))
        if not pool['candidates']['geometry_quota_achieved']:
            raise ValueError('Candidate quota incomplete; inspect failed_targets before selection')
        selected=step('selection_30',lambda:run_selection(work,force=force,progress=progress))
        sensitivity=step('selection_sensitivity',lambda:run_sensitivity(work,force=force,progress=progress))
        validate_sensitivity(sensitivity,selected,work)
        step('named_maps',lambda:({'status':'cached','cache_hit':True,'network_calls':0} if not force and maps_cached(work) else export_maps(work)))
        field=step('field_templates',lambda:prepare(work));directory=Path(field['directory'])
        if observations:step('observation_import',lambda:import_observations(directory,observations))
        step('field_status',lambda:field_status(directory))
        step('update_and_reserve_plan',lambda:build_update_plan(directory,evaluate_reserves=True))
        revision=step('observed_features_and_reselection',lambda:revise_survey(directory,work))
        trip_config=load_config(work)
        if revision.get('surveyed_set_locked'):
            trip_config['selection_report']='reports/field/latest_survey_revision.json'
        step('directed_trip_corridors',lambda:prepare_trips(work,config=trip_config))
        trips=step('real_trip_qc',lambda:process_trips(work,config=trip_config,input_dir=input_dir))
        report.update(status='automated_pre_survey_complete_awaiting_field_evidence',finished_at=now(),
                      active_step=None,elapsed_seconds=time.monotonic()-timer,
                      candidate_routes=pool['candidates']['created_routes'],selected_routes=len(selected['selected_route_ids']),
                      measured_trips=trips.get('trip_count',0),
                      sensitivity_scenarios=sensitivity['total_scenarios'],
                      sensitivity_completed_scenarios=sensitivity['completed_scenarios'],
                      sensitivity_expected_infeasible_scenarios=sensitivity['expected_infeasible_scenarios'],
                      pending=['official_GIS_boundary_review','dated_G1_G4_G5_G6_and_C6_evidence','real_GPS_speed_time_measurements'])
        report['pending']=['official_GIS_boundary_review']
        if not revision.get('surveyed_set_locked'): report['pending'].append('dated_G1_G4_G5_G6_and_C6_evidence')
        if not trips.get('trips_with_valid_speed_intervals',0): report['pending'].append('real_GPS_speed_time_measurements')
        elif trips.get('status')!='processed': report['pending'].append('measurement_QC_flags_review')
        if revision.get('surveyed_set_locked') and trips.get('trips_with_valid_speed_intervals',0)>0:
            report['status']='automated_processing_complete_pending_evidence_QA_review'
        atomic_json(work/REPORT,report);return report
    except BaseException as exc:
        report.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc),
                      finished_at=now(),elapsed_seconds=time.monotonic()-timer)
        atomic_json(work/REPORT,report);raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['check','run','status']);p.add_argument('--work',type=Path,default=WORK)
    p.add_argument('--force',action='store_true');p.add_argument('--observations',type=Path);p.add_argument('--input-dir',type=Path)
    a=p.parse_args()
    value=preflight(a.work) if a.command=='check' else status(a.work) if a.command=='status' else run(a.work,force=a.force,observations=a.observations,input_dir=a.input_dir)
    print(json.dumps(value,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
