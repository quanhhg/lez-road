"""Versioned field overlays and re-selection with the existing C1-C7 engine.

Never edit source OSM, the graph, or the original pre-survey selection. An
observed direction/geometry conflict blocks that route until a new graph exists.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path
import sqlite3

from .common import WORK, atomic_json, cached_manifest, commit_manifest, digest, file_hash, input_path, now, processing_lock, relative, write_csv
from . import field_workflow as fw
from . import selection_metrics as sm

VERSION = 'dated_field_revision_C1_C7_v1'
REPORT = 'reports/field/latest_survey_revision.json'
SAFE_NO_CHANGE = {'none', 'no', 'false', 'no_issue', 'unchanged', 'no_change'}


def fixed_feature_space(data, options):
    """Refit the documented min/max and quartiles on all 60 updated candidates."""
    import numpy as np
    names = sm.FEATURES if options.get('feature_policy') != 'seven_complete_features' else [n for n in sm.FEATURES if n not in ('lanes', 'maxspeed')]
    raw = np.array([[r[n+'_scoring_model'] if n in ('lanes','maxspeed') else r[n] for n in names] for r in data['features']], dtype=float)
    if not np.all(np.isfinite(raw)):
        raise ValueError('Field overlay introduced a nonfinite scoring feature')
    low, high = raw.min(axis=0), raw.max(axis=0)
    varying = high - low > 1e-12
    active = [n for n, flag in zip(names, varying) if flag]
    X = (raw[:, varying] - low[varying]) / (high[varying] - low[varying])
    cuts = {n: sorted(set(float(v) for v in np.quantile(X[:, j], [.25,.5,.75]))) for j,n in enumerate(active)}
    data.update(X=X, feature_names=active,
        bins=[{(n, int(np.searchsorted(cuts[n], X[i,j], side='right'))) for j,n in enumerate(active)} for i in range(len(raw))],
        distances=np.sqrt(((X[:, None, :] - X[None, :, :])**2).sum(axis=2)))
    data['normalization'] = dict(data['normalization'], field_revision=True,
        raw_min=dict(zip(names, low.tolist())), raw_max=dict(zip(names, high.tolist())),
        active_features=active, quartile_thresholds_in_normalized_space=cuts,
        model_is_observation=False)


def numeric_overlay(data, observations, part_registry, graph, decisions):
    """Length-weight field values on actual traversed parts; no point extrapolation."""
    observations = [r for r in observations if r['status']=='observed' and r['evidence_source']=='field']
    grouped = defaultdict(list)
    for row in observations:
        grouped[row['route_id']].append(row)
    segment_by_part = {r['part_id']:r['segment_id'] for r in part_registry}
    decisions = {r['route_id']:r for r in decisions}
    directions = defaultdict(set)
    for arc in graph.arcs.values(): directions[arc['part_id']].add(arc['direction'])
    blocked = {}
    audit = []
    for feature, walk in zip(data['features'], data['walks']):
        rid = feature['route_id']; evidence = grouped[rid]; reasons = []
        decision = decisions[rid]
        for gate in ('G1','G4','G5','G6'):
            feature[gate] = decision[gate]
            if decision[gate]=='failed': reasons.append('failed_'+gate)
        feature['C6'] = float(decision['C6']) if decision['C6'] else None
        feature['C6_status'] = decision['C6_status']
        feature['G3'] = 'passed_QGIS_research_scope_from_same_immutable_source'
        if feature['C6']==0: reasons.append('observed_C6_zero')
        # Only the latest assessment of a scope activates a geometry warning.
        scoped = defaultdict(list)
        for row in evidence:
            if row['field'] in {'direction_change','turn_restriction','geometry_issue','oneway'}:
                scoped[(row['field'],row['coverage'],row['part_id'],row['segment_id'])].append(row)
        for (field, coverage, pid, sid), records in scoped.items():
            row = max(records, key=lambda r: fw.timestamp(r['observed_at']))
            if field!='oneway':
                if row['value'].strip().lower() not in SAFE_NO_CHANGE:
                    reasons.append('graph_rebuild_required_'+field)
            else:
                covered = [p for p in walk['part_ids'] if coverage=='whole_route' or (coverage=='part' and p==pid) or (coverage=='segment' and segment_by_part[p]==sid)]
                if coverage=='point': continue
                expected = row['value']=='true'
                if any((len(directions[p])==1)!=expected for p in set(covered)):
                    reasons.append('graph_rebuild_required_oneway')
        for attribute in ('lanes','maxspeed'):
            feature[attribute+'_osm'] = feature[attribute]
            total = float(feature['length_m']); measured_sum = measured_length = hybrid_sum = 0.0
            for pid, aid in zip(walk['part_ids'], walk['arc_ids']):
                part = data['parts'][pid]; length = float(part['length_m']); tags = json.loads(part['tags_json'])
                arc = graph.arcs[aid]
                candidates = [r for r in evidence if r['field']==attribute and
                    (r['coverage']=='whole_route' or (r['coverage']=='part' and r['part_id']==pid) or
                     (r['coverage']=='segment' and r['segment_id']==segment_by_part[pid]))]
                chosen = max(candidates, key=lambda r:(fw.timestamp(r['observed_at']), {'whole_route':0,'segment':1,'part':2}[r['coverage']]), default=None)
                key = 'maxspeed:'+arc['direction'] if attribute=='maxspeed' else attribute
                raw = sm.number(tags.get(key, tags.get(attribute)), speed=attribute=='maxspeed')
                fallback = raw if raw is not None else data['normalization']['model_medians'][attribute][arc['rc']]
                if chosen:
                    value = float(chosen['value']); measured_sum += value*length; measured_length += length
                    audit.append({'route_id':rid,'arc_id':aid,'part_id':pid,'field':attribute,'value':value,
                        'length_weight_m':length,'observation_id':chosen['observation_id'], 'evidence_uri':chosen['evidence_uri']})
                else: value = fallback
                hybrid_sum += value*length
            feature[attribute+'_observed'] = measured_sum/measured_length if measured_length else None
            feature[attribute+'_observed_length_fraction'] = min(1.0, measured_length/total)
            feature[attribute+'_scoring_model'] = hybrid_sum/total
            feature[attribute+'_scoring_source'] = 'dated_field_on_covered_parts_plus_OSM_and_model_elsewhere'
        for field, variable in (('junction_count','junctions_per_km'),('signal_count','signals_per_km')):
            whole = [r for r in evidence if r['field']==field and r['coverage']=='whole_route']
            feature[variable+'_osm'] = feature[variable]
            if whole:
                row = max(whole, key=lambda r:fw.timestamp(r['observed_at']))
                feature[variable] = float(row['value'])/(float(feature['length_m'])/1000)
                feature[variable+'_source'] = row['observation_id']
            else: feature[variable+'_source'] = 'OSM_proxy; partial_or_point_counts_not_extrapolated'
        if reasons: blocked[rid] = sorted(set(reasons))
    data['eligible_indices'] = {i for i,r in enumerate(data['features']) if r['route_id'] not in blocked}
    return blocked, audit


def run(directory, work=WORK):
    directory, work = Path(directory).resolve(), Path(work).resolve()
    fw.assert_current_source(directory)
    manifest = fw.read_json(directory/'manifest.json'); cfg = manifest['config']
    observations = fw.read_csv(directory/'field_observations.csv')
    validation = fw.validate_observations(directory, observations)
    report = dict(status='awaiting_field_observations', method_version=VERSION, finished_at=now(),
        source_campaign=relative(directory,work), valid_observations=validation['accepted_count'] if validation['valid'] else 0,
        geometry_modified=False, raw_osm_modified=False, driving_cycle_constructed=False, surveyed_set_locked=False)
    if not validation['valid']:
        report.update(status='observations_require_correction', errors=validation['errors'])
        atomic_json(work/REPORT, report); return report
    if not any(r['status']=='observed' and r['evidence_source']=='field' for r in observations):
        atomic_json(work/REPORT, report); return report
    options = fw.read_json(work/'config/selection_30.json')
    parent = fw.read_json(input_path(work, options['parent_report']))
    fingerprint = digest({'version':VERSION, 'code':file_hash(__file__), 'metrics':file_hash(sm.__file__),
        'field':file_hash(fw.__file__), 'campaign':file_hash(directory/'manifest.json'),
        'observations':file_hash(directory/'field_observations.csv'), 'options':options})
    target = work/'data/processed/survey_revision'/fingerprint[:20]
    with processing_lock(work):
        cached = cached_manifest(target,fingerprint)
        if cached:
            report = dict(cached['report'],cache_hit=True)
            atomic_json(work/REPORT,report); return report
        target.mkdir(parents=True, exist_ok=True)
        data = sm.load_data(work,parent,options)
        sampling = fw.read_json(work/options['sampling_config'])
        from .graph import MotorcycleNetwork
        graph = MotorcycleNetwork.load(input_path(work,sampling['graph_path']))
        decisions = fw.assess_routes(fw.read_csv(directory/'route_registry.csv'), observations, cfg)
        blocked, audit = numeric_overlay(data,observations,fw.read_csv(directory/'route_part_registry.csv'),graph,decisions)
        fixed_feature_space(data,options)
        write_csv(target/'field_feature_overlay.csv',data['features'],list(data['features'][0]))
        write_csv(target/'applied_part_evidence.csv',audit,list(audit[0]) if audit else ['route_id','arc_id','part_id','field','value','length_weight_m','observation_id','evidence_uri'])
        write_csv(target/'blocked_routes.csv',[{'route_id':rid,'reasons':';'.join(reasons)} for rid,reasons in sorted(blocked.items())],['route_id','reasons'])
        try: selected, history, swaps, seeds = sm.select(data,options)
        except ValueError as exc:
            report.update(status='quota_infeasible_after_field_evidence',error=str(exc),blocked_routes=blocked,
                remaining_by_bucket=dict(Counter(data['features'][i]['quota_bucket'] for i in data['eligible_indices'])),
                paths={'directory':relative(target,work)})
            atomic_json(target/'qa.json',report)
            commit_manifest(target,fingerprint,report,['field_feature_overlay.csv','applied_part_evidence.csv','blocked_routes.csv','qa.json'])
            atomic_json(work/REPORT,report); return report
        ids = [data['features'][i]['route_id'] for i in selected]
        summary = sm.summary(data,selected,options['minimum_cell_fraction'])
        wanted = {name:bucket['count'] for name,bucket in sm.quota_buckets(options).items()}
        if summary['route_count']!=30 or {k:summary['quota_bucket_counts'].get(k,0) for k in wanted}!=wanted:
            raise RuntimeError('Field revision violated exact quota')
        rows = []
        for i in selected:
            raw = sm.criteria(data,[j for j in selected if j!=i],[i],options)[0][0]['raw']
            rows.append({'candidate_index':i,'route_id':data['features'][i]['route_id'],'raw':raw})
        scored, normal = sm.normalize_scores(rows,options)
        chosen = []
        for score in scored:
            feature = copy.deepcopy(data['features'][score['candidate_index']])
            feature.update(selected=True,final_context_score=score['score'],C6_score_is_assumption=score['C6_score_is_assumption'],
                final_context_score_lower_C6=score['score_lower_unknown_C6'],final_context_score_upper_C6=score['score_upper_unknown_C6'])
            chosen.append(feature)
        eligible = {r['route_id'] for r in decisions if r['decision_status']=='eligible_for_manual_surveyed_set_review'}
        ready = set(ids)<=eligible
        write_csv(target/'selected_routes.csv',chosen,list(chosen[0]))
        atomic_json(target/'selected_walks.json',[data['walks'][i] for i in selected])
        atomic_json(target/'decision_history.json',{'greedy':history,'swaps':swaps,'seeds':seeds,'normalization':normal})
        original = fw.read_json(work/cfg['selection_report'])
        report.update(status='surveyed_technical_set_frozen' if ready else 'reselected_awaiting_field_evidence',
            cache_hit=False, fingerprint=fingerprint, selected_route_ids=ids, summary=summary, blocked_routes=blocked,
            changed_routes={'removed':sorted(set(original['selected_route_ids'])-set(ids)), 'added':sorted(set(ids)-set(original['selected_route_ids']))},
            pending_selected_routes=sorted(set(ids)-eligible), surveyed_set_locked=ready,
            official_gis_verified=False, policy_version=options['policy_version'], source_bundle=relative(directory,work),
            origin_selection_report=cfg['selection_report'], mandatory_gates=original['mandatory_gates'],
            snapshot_utc=original.get('snapshot_utc'), measurement_verified=False,
            paths={'directory':relative(target,work),'selected_routes':relative(target/'selected_routes.csv',work)})
        atomic_json(target/'qa.json',report)
        commit_manifest(target,fingerprint,report,['field_feature_overlay.csv','applied_part_evidence.csv','blocked_routes.csv',
            'selected_routes.csv','selected_walks.json','decision_history.json','qa.json'])
    atomic_json(work/REPORT,report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('directory',type=Path);p.add_argument('--work',type=Path,default=WORK)
    a=p.parse_args(); print(json.dumps(run(a.directory,a.work),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
