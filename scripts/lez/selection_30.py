"""Select 18/12 proposed routes from the 20A/20B/20C pool before field survey."""
from __future__ import annotations

if __package__ in (None, ''):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'lez'

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import time

from .common import (WORK, atomic_json, cached_manifest, code_hash, commit_manifest,
                     digest, file_hash, input_path, now, processing_lock, publish_link, relative, write_csv)


def configuration(work):
    options = json.loads((Path(work) / 'config/selection_30.json').read_text())
    if options['quota'] != {'inside': 18, 'outside': 12}:
        raise ValueError('Baseline quota must be the user-selected 18 inside / 12 outside')
    if options.get('pool_quota') != {'A': 20, 'B': 20, 'C': 20} or options['required_strata'] != ['A', 'B', 'C']:
        raise ValueError('Candidate design must contain 20 routes in each of A/B/C')
    from .selection_metrics import quota_buckets
    buckets = quota_buckets(options)
    if buckets.get('A_inside', {}).get('count') != 10 or buckets.get('B_inside', {}).get('count') != 8 or buckets.get('C_outside', {}).get('count') != 12 or buckets['inside_remaining']['count'] != 0 or buckets['outside_remaining']['count'] != 0:
        raise ValueError('Joint quota must retain 10 A-inside, 8 B-inside and 12 C-outside routes')
    if options['field_data_required_before_selection'] is not False:
        raise ValueError('Pre-survey selection cannot require prior field observations')
    if set(options['weights']) != {f'C{i}' for i in range(1,8)} or sum(options['weights'].values()) != 100:
        raise ValueError('Invalid source criterion weights')
    if options['C6_missing_policy'] != 'neutral_assumption_with_score_interval' or options.get('C6_neutral_assumption')!=2.5:
        raise ValueError('Baseline must retain raw C6 unknown and declare a separate neutral scoring assumption')
    if options.get('constant_criterion_policy')!='all_one_preserve_weights':
        raise ValueError('Baseline constant criteria must preserve nominal document weights')
    return options


def preflight_selection(work=WORK):
    work = Path(work).resolve()
    options = configuration(work)
    path = input_path(work, options.get('parent_report', 'reports/sampling/latest_sampling_2030.json'))
    report = json.loads(path.read_text())
    if options.get('zone_basis') == 'LEZ_first' and report.get('policy_version') != options.get('policy_version'):
        raise ValueError('Candidate and selection policy versions differ')
    directory = input_path(work, report['paths']['directory'])
    manifest = json.loads((directory / 'manifest.json').read_text())
    if not cached_manifest(directory, manifest['fingerprint']):
        raise ValueError('The parent 60-route bundle is incomplete or has changed')
    candidates = json.loads((directory / 'candidate_walks.json').read_text())
    ids = [r['route_id'] for r in candidates]
    counts = {g: sum(r['group'] == g for r in candidates) for g in options['quota']}
    zone_counts = {zone: sum(r.get('sampling_zone') == zone for r in candidates) for zone in options['pool_quota']}
    if len(ids) != 60 or len(set(ids)) != 60 or zone_counts != options['pool_quota']:
        raise ValueError('Expected an immutable, distinct 20A/20B/20C pool of 60 routes')
    if any(r.get('sampling_zone') != r['stratum_id'] or r['group'] not in options['quota'] for r in candidates):
        raise ValueError('ABC sampling zone and explicit LEZ group are required on every route')
    from .selection_metrics import quota_bucket, quota_buckets
    available = {name: sum(quota_bucket(r, options) == name for r in candidates) for name in quota_buckets(options)}
    if any(available[name] < bucket['count'] for name, bucket in quota_buckets(options).items()):
        raise ValueError('Candidate pool cannot satisfy exact ABC × LEZ quotas')
    if not set(options['required_strata']).issubset({r['stratum_id'] for r in candidates}):
        raise ValueError('Required spatial strata are absent from candidate pool')
    sampling_path = input_path(work, options.get('sampling_config', 'config/sampling_2030.json'))
    sampling = json.loads(sampling_path.read_text())
    from .pipeline import kernel_spec
    kernel_spec()
    required = [work / 'config/selection_30.json', directory / 'manifest.json',
                input_path(work, sampling['network_path']), input_path(work,sampling['graph_path']),
                sampling_path,work/'config/boundary_project.json',work/'data/hanoi_tiles/tile_project.json']
    required += [input_path(work, v) for v in options['sources'] + [options['source_requirements']]]
    for p in required:
        if not p.is_file():
            raise ValueError('Missing immutable selection input: ' + str(p))
    requirements=json.loads(input_path(work,options['source_requirements']).read_text())
    for source in requirements['sources'].values():
        if file_hash(work/'data/raw/research'/source['filename'])!=source['sha256']:
            raise ValueError('Research source hash differs from extracted requirements: '+source['filename'])
    fingerprint = digest({'inputs': {relative(p, work):file_hash(p) for p in required},
                          'code':code_hash(['common.py','selection_30.py','selection_metrics.py','selection_gates.py','graph.py','gis.py'])})
    return {'status':'ready_for_pre_survey_selection', 'network_calls':0,
            'source_bundle':relative(directory, work), 'pool':counts, 'pool_by_sampling_zone':zone_counts,
            'quota':options['quota'], 'intersection_quota':options['intersection_quota'],
            'fingerprint':fingerprint, 'field_data_required':False,
            'research_scope_only':True, 'snapshot_utc':sampling['source_snapshot_utc']}


def selection_status(work=WORK):
    p = Path(work) / 'reports/selection/latest_selection_30.json'
    return json.loads(p.read_text()) if p.exists() else {'status':'not_run'}


def native_export(work, directory, command='export'):
    from .pipeline import kernel_spec
    spec = kernel_spec()
    env = os.environ.copy()
    env.update(spec.get('env', {}))
    process = subprocess.run([spec['argv'][0], str(Path(__file__).resolve()), command,
                              '--work', str(work), '--directory', str(directory)],
                             env=env, capture_output=True, text=True)
    (directory / ('gis_'+command+'.log')).write_text(process.stdout + process.stderr)
    if process.returncode:
        raise RuntimeError('Native GIS export failed: ' + process.stderr[-2500:])


def run_selection(work=WORK, force=False, progress=print):
    import numpy as np
    from .selection_metrics import criteria, load_data, normalize_scores, rows, select, summary
    work = Path(work).resolve()
    check = preflight_selection(work)
    options = configuration(work)
    parent = json.loads(input_path(work, options.get('parent_report', 'reports/sampling/latest_sampling_2030.json')).read_text())
    fingerprint = check['fingerprint']
    directory = work / 'data/processed/selection_30' / fingerprint[:20]
    with processing_lock(work):
        cached = None if force else cached_manifest(directory, fingerprint)
        if cached:
            result = dict(cached['report'], cache_hit=True)
        else:
            started, timer = now(), time.monotonic()
            directory.mkdir(parents=True, exist_ok=True)
            if progress:
                progress('Đang phân loại 60 tuyến từ dữ liệu GIS/OSM; chưa yêu cầu dữ liệu thực địa.')
            data = load_data(work, parent, options)
            native_export(work,directory,'precompute')
            gates=json.loads((directory/'gate_checks.json').read_text())
            for row in data['features']:
                evidence=gates['routes'][row['route_id']]
                if not evidence['pre_survey_admissible']:
                    raise ValueError('Candidate fails mandatory GIS/OSM gate: '+row['route_id'])
                row.update(G3='passed_QGIS_research_scope',pre_survey_admissible=True)
            if progress:
                progress('Đang chọn 18 trong / 12 ngoài; giữ 10 A trong, 8 B trong và 12 C ngoài bằng C1–C7, nhiều khởi đầu và hoán đổi.')
            selected, history, swaps, seeds = select(data, options)
            final = summary(data, selected, options['minimum_cell_fraction'])
            from .selection_metrics import quota_buckets
            exact_buckets = {name: bucket['count'] for name, bucket in quota_buckets(options).items()}
            achieved_buckets = {name: final['quota_bucket_counts'].get(name, 0) for name in exact_buckets}
            if (final['inside'], final['outside']) != (18,12) or achieved_buckets != exact_buckets or len(set(selected)) != 30 or set(final['represented_primary_strata']) != set(options['required_strata']):
                raise RuntimeError('Selection failed mandatory quota/strata/uniqueness checks')
            ids = [data['walks'][i]['route_id'] for i in selected]
            baseline = summary(data, list(range(60)), options['minimum_cell_fraction'])
            greedy_set = [next(i for i,r in enumerate(data['walks']) if r['route_id']==rid)
                          for rid in history[-1]['selected_after']]
            greedy_metrics = summary(data, greedy_set, options['minimum_cell_fraction'])
            # Final context assesses leave-one-out contribution for selected routes,
            # and addition to the final set for reserves. It is not the dynamic selection score.
            raw_assessments = []
            for i in range(60):
                reference = [j for j in selected if j != i]
                record = criteria(data, reference, [i], options)[0][0]
                raw_assessments.append({'candidate_index':i,'route_id':data['walks'][i]['route_id'],'raw':record['raw']})
            assessments, final_normalization = normalize_scores(raw_assessments, options)
            chosen_at = {r['chosen']:(r['round'],next(c['score'] for c in r['candidates'] if c['route_id']==r['chosen'])) for r in history[1:]}
            feature_rows = []
            for record in assessments:
                i = record['candidate_index']
                row = dict(data['features'][i])
                row.update(selected=i in selected, status='proposed_for_survey' if i in selected else 'reserve_candidate',
                           selection_order=selected.index(i)+1 if i in selected else None,
                           assessment_context='leave_one_out_readdition' if i in selected else 'addition_to_final_set',
                           final_context_score=record['score'],
                           final_context_score_lower_C6=record['score_lower_unknown_C6'],
                           final_context_score_upper_C6=record['score_upper_unknown_C6'],
                           C6_scoring_assumption=options['C6_neutral_assumption'],
                           C6_score_is_assumption=True,
                           greedy_round=chosen_at.get(row['route_id'],(None,None))[0],
                           score_at_greedy_selection=chosen_at.get(row['route_id'],(None,None))[1],
                           selection_method='swap' if any(s['added']==row['route_id'] for s in swaps) else ('weighted_greedy' if row['route_id'] in chosen_at else ('seed' if i in selected else 'reserve')))
                row.update({f'{c}_final_context':v for c,v in record['raw'].items()})
                row.update({f'{c}_normalized_final':v for c,v in record['normalized'].items()})
                feature_rows.append(row)
            write_csv(directory/'candidate_classification.csv', feature_rows, list(feature_rows[0]))
            chosen_rows = [next(r for r in feature_rows if r['route_id']==rid) for rid in ids]
            write_csv(directory/'selected_routes.csv', chosen_rows, list(feature_rows[0]))
            reserve = []
            selected_vector = data['vectors'][selected].sum(axis=0)
            from .selection_metrics import D, feasible_add
            for i in range(60):
                if i in selected:
                    continue
                replacements = []
                for old in selected:
                    others = [j for j in selected if j != old]
                    if data['features'][old]['group'] != data['features'][i]['group'] or not feasible_add(data, others, i, options['quota'],set(options['required_strata']), options):
                        continue
                    if data['corridors'][i,others].max()>=options['max_corridor_overlap']:
                        continue
                    value = D(selected_vector-data['vectors'][old]+data['vectors'][i],data['q'])
                    replacements.append((value,data['features'][old]['route_id']))
                value, replace_id = min(replacements) if replacements else (None,None)
                reserve.append(dict(next(r for r in feature_rows if r['route_id']==data['features'][i]['route_id']),
                                    suggested_replace=replace_id, D_if_replaced=value,
                                    reserve_method='minimum_RC_only_D_same_quota_and_primary_strata_not_field_verified'))
            reserve.sort(key=lambda r:(r['group'],r['D_if_replaced'] if r['D_if_replaced'] is not None else float('inf'),r['route_id']))
            write_csv(directory/'reserve_routes.csv',reserve,list(reserve[0]))
            vector = data['vectors'][selected].sum(axis=0)
            coverage = np.zeros(len(data['cells']))
            for pid in set().union(*(data['part_sets'][i] for i in selected)):
                for cell,length in data['part_cells'][pid]:
                    coverage[cell]+=length
            matrix = []
            for j,(stratum,rc) in enumerate(data['cells']):
                matrix.append({'stratum_id':stratum,'sampling_zone':stratum,'rc':rc,'network_length_m':float(data['network_lengths'][j]),
                               'network_fraction':float(data['q'][j]),'sample_traversed_length_m':float(vector[j]),
                               'sample_fraction':float(vector[j]/vector.sum()),'gap_fraction':float(data['q'][j]-vector[j]/vector.sum()),
                               **{key: value for group in ('inside','outside') for key,value in [
                                   ('network_'+group+'_length_m', float(data['domain_lengths'][group][j])),
                                   ('network_'+group+'_fraction_domain', float(data['domain_lengths'][group][j]/data['domain_lengths'][group].sum()) if data['domain_lengths'][group].sum() else None),
                                   ('sample_'+group+'_traversed_length_m', float(data['domain_vectors'][group][selected,j].sum())),
                                   ('sample_'+group+'_fraction_domain', float(data['domain_vectors'][group][selected,j].sum()/data['domain_vectors'][group][selected].sum()) if data['domain_vectors'][group][selected].sum() else None)]},
                               'sample_unique_length_m':float(coverage[j]),
                               'unique_coverage_fraction':float(coverage[j]/data['network_lengths'][j]) if data['network_lengths'][j] else None,
                               'materially_represented':bool(np.any(data['P'][selected,j]>=options['minimum_cell_fraction'])),
                               'reachable_in_60':bool(np.any(data['vectors'][:,j]>0))})
            write_csv(directory/'network_sample_matrix.csv',matrix,list(matrix[0]))
            history_rows=[]
            for h in history[1:]:
                for r in h['candidates']:
                    history_rows.append({'round':h['round'],'candidate':r['route_id'],'chosen':r['route_id']==h['chosen'],
                                         'score':r['score'],'score_lower_C6':r['score_lower_unknown_C6'],
                                         'score_upper_C6':r['score_upper_unknown_C6'],**r['raw'],
                                         **{c+'_weight':v for c,v in h['normalization']['effective_weights'].items()}})
            write_csv(directory/'selection_history.csv',history_rows,list(history_rows[0]))
            atomic_json(directory/'selection_history.json',history)
            steps = {len(h['selected_after']):h['set_metrics']['D_combined'] for h in history}
            saturation = []
            for n in sorted(steps):
                if n-2 not in steps:
                    continue
                before, after = steps[n-2], steps[n]
                improve = (before-after)/before if before else None
                saturation.append({'route_count':n,'delta_n':2,'D_before':before,'D_after':after,
                                   'relative_improvement':improve,
                                   'diagnostic':'worsening' if improve is not None and improve < 0 else 'improvement',
                                   'below_2_percent':improve is not None and 0 <= improve < 0.02,
                                   'used_to_stop_before_30':False})
            write_csv(directory/'saturation.csv',saturation,list(saturation[0]))
            write_csv(directory/'swaps.csv',swaps,['round','removed','added','D_before','D_after','improvement'])
            atomic_json(directory/'seed_runs.json',seeds)
            atomic_json(directory/'feature_normalization.json',data['normalization'])
            atomic_json(directory/'final_context_normalization.json',final_normalization)
            atomic_json(directory/'selected_walks.json',[data['walks'][i] for i in selected])
            parent_dir=input_path(work,parent['paths']['directory'])
            anchors=[r for r in rows(parent_dir/'anchors.csv') if r['route_id'] in ids]
            write_csv(directory/'selected_anchors.csv',anchors,list(anchors[0]))
            arcs=[r for r in rows(parent_dir/'route_arcs.csv') if r['route_id'] in ids]
            write_csv(directory/'selected_route_arcs.csv',arcs,list(arcs[0]))
            checklist=[]
            for row in chosen_rows:
                checklist.append({'route_id':row['route_id'],'group':row['group'],'stratum_id':row['stratum_id'],'sampling_zone':row['sampling_zone'],
                                  'lez2027_group':row.get('lez2027_group','unknown'),'lez2030_group':row['group'],'policy_version':row['policy_version'],
                                  'survey_date':row['survey_date'],'lez_status_at_survey':row['lez_status_at_survey'],
                                  'length_km':float(row['length_m'])/1000,'G1_motorcycle_permission':'survey_required',
                                  'G2_continuity_direction_turns':'passed_on_source_graph_verify_changes',
                                  'G3_scope':'passed_research_scope_check_reference_legal_geography',
                                  'G4_temporary_works':'survey_required','G5_repeatability':'survey_required',
                                  'G6_safe_start_end':'survey_required','C6_field_feasibility_0_to_5':None,
                                  'lanes_to_verify':True,'maxspeed_to_verify':True,'speed_time_measured':False,
                                  'date':'','observer':'','evidence':'','decision':'','notes':''})
            write_csv(directory/'field_checklist.csv',checklist,list(checklist[0]))
            sensitivities=[]
            scenarios=[]
            for name,criteria_ids in [('weights_C1_C2_120_percent',['C1','C2']),('weights_C4_C5_120_percent',['C4','C5'])]:
                trial=copy.deepcopy(options)
                for c in criteria_ids:trial['weights'][c]*=options['sensitivity']['weight_factor']
                scenarios.append((name,trial))
            for value in options['sensitivity']['cell_thresholds']:
                if value!=options['minimum_cell_fraction']:
                    trial=copy.deepcopy(options);trial['minimum_cell_fraction']=value
                    scenarios.append(('cell_fraction_'+str(value),trial))
            for quota in options['sensitivity']['quota_neighbors']:
                trial=copy.deepcopy(options);trial['quota']=quota
                scenarios.append(('quota_'+str(quota['inside'])+'_'+str(quota['outside']),trial))
            trial=copy.deepcopy(options);trial['C6_missing_policy']='unknown_weight_zero_renormalize_other_criteria'
            scenarios.append(('unknown_C6_drop_renormalize',trial))
            for name,trial in scenarios:
                if progress:progress('Kiểm tra độ nhạy: '+name)
                s,_,_,_=select(data,trial)
                common=set(s)&set(selected)
                sensitivities.append({'scenario':name,'quota':trial['quota'],
                    'weights':trial['weights'],'minimum_cell_fraction':trial['minimum_cell_fraction'],
                    'review_threshold':trial['overlap_review_fraction'],'jaccard':len(common)/len(set(s)|set(selected)),
                    'route_ids':[data['walks'][i]['route_id'] for i in s],**summary(data,s,trial['minimum_cell_fraction'])})
            if progress:progress('Kiểm tra độ nhạy: 7 biến có dữ liệu đầy đủ so với mô hình 9 biến.')
            trial=copy.deepcopy(options);trial['feature_policy']='seven_complete_features'
            complete_data=load_data(work,parent,trial)
            s,_,_,_=select(complete_data,trial)
            common=set(s)&set(selected)
            sensitivities.append({'scenario':'seven_complete_features_no_lane_speed_models','quota':trial['quota'],
                'weights':trial['weights'],'minimum_cell_fraction':trial['minimum_cell_fraction'],
                'review_threshold':trial['overlap_review_fraction'],'jaccard':len(common)/len(set(s)|set(selected)),
                'route_ids':[data['walks'][i]['route_id'] for i in s],**summary(complete_data,s,trial['minimum_cell_fraction'])})
            substantive_scenario_count=len(sensitivities)
            for threshold in options['sensitivity']['review_thresholds']:
                sensitivities.append({'scenario':'overlap_review_'+str(threshold),'quota':options['quota'],
                    'weights':options['weights'],'minimum_cell_fraction':options['minimum_cell_fraction'],
                    'review_threshold':threshold,'jaccard':1.0,'route_ids':ids,
                    'review_pairs':int(sum(data['overlaps'][i,j]>=threshold for k,i in enumerate(selected) for j in selected[k+1:])),
                    'review_is_flag_only_selection_unchanged':True,**final})
            atomic_json(directory/'sensitivity.json',sensitivities)
            sensitivity_fields=['scenario','inside','outside','D_combined','D_domain_mean','jaccard','unique_rc_coverage_fraction',
                                'minimum_cell_fraction','review_threshold','review_pairs','route_ids','weights']
            write_csv(directory/'sensitivity.csv',[{**r,'route_ids':';'.join(r['route_ids']),'weights':json.dumps(r['weights'],sort_keys=True)} for r in sensitivities],sensitivity_fields)
            frequency={rid:sum(rid in r['route_ids'] for r in sensitivities[:substantive_scenario_count])+int(rid in ids) for rid in [r['route_id'] for r in data['features']]}
            write_csv(directory/'selection_frequency.csv',[{'route_id':rid,'times_selected':n,'scenario_count':substantive_scenario_count+1} for rid,n in frequency.items()],['route_id','times_selected','scenario_count'])
            review=[{'left':data['walks'][i]['route_id'],'right':data['walks'][j]['route_id'],
                     'overlap_fraction':float(data['overlaps'][i,j])} for k,i in enumerate(selected) for j in selected[k+1:] if data['overlaps'][i,j]>=options['overlap_review_fraction']]
            atomic_json(directory/'overlap_review.json',review)
            payload={'parent_directory':relative(parent_dir,work),'selected_ids':ids,'features':feature_rows}
            atomic_json(directory/'selection_payload.json',payload)
            native_export(work,directory)
            result={'status':'proposed_for_survey','started_at':started,'finished_at':now(),
                    'elapsed_seconds':time.monotonic()-timer,'cache_hit':False,'network_calls':0,
                    'method_version':options['method_version'],'policy_version':options.get('policy_version'),
                    'scope':options.get('scope'),'zone_basis':options.get('zone_basis'),'quota_achieved':True,'quota':options['quota'],
                    'intersection_quota':options['intersection_quota'],'candidate_pool_quota':options['pool_quota'],'selected_route_ids':ids,
                    'metrics':final,'baseline_60':baseline,'before_swaps':greedy_metrics,'accepted_swaps':len(swaps),
                    'source_bundle':relative(parent_dir,work),'snapshot_utc':check['snapshot_utc'],
                    'measurement_verified':False,'field_data_required_before_selection':False,
                    'survey_required_routes':30,'official_gis_verified':False,'raw_osm_modified':False,
                    'criteria':{'document_weights':options['weights'],'C6':'raw_unknown_neutral_assumption_2.5_for_provisional_scoring_only_interval_0_to_5',
                                'C3_C5':'9_features_with_separate_lane_speed_models_raw_NULL_preserved_and_7_feature_sensitivity',
                                'C7':'explicit_research_spatial_novelty_rubric_0_to_5',
                                'constant_criterion':'all_one_preserve_weights','final_context_score_is_not_selection_score':True},
                    'mandatory_gates':gates['summary'],
                    'C6_ranking_uncertainty_rounds':sum(h.get('C6_can_change_ranking',False) for h in history[1:]),
                    'network_rc_denominator_m':float(data['network_lengths'].sum()),
                    'normalization':data['normalization'],
                    'missing_cells_in_entire_pool':[r['stratum_id']+'×'+r['rc'] for r in matrix if not r['reachable_in_60']],
                    'sensitivity_scenarios':len(sensitivities),
                    'limitations':['Selection precedes field survey; G1/G4/G5/G6 and C6 remain unknown.',
                                   'Frozen research scope is not independently verified government GIS.',
                                   'Lanes/maxspeed raw partial observations are separate from RC-median scoring estimates; verify in survey.',
                                   'C6 is unknown; neutral provisional assumption does not discriminate routes; heterogeneous field values can change rankings within a 10-point nominal interval.',
                                   'Junctions/signals are mapped topology proxies, not complete observed counts.',
                                   'ABC bands and LEZ membership are independent; classification uses both geometry overlays.',
                                   'Weighted greedy plus finite swaps is not a proof of global optimum or representativeness.'],
                    'paths':{'directory':relative(directory,work),'selected_routes':relative(directory/'selected_routes.csv',work),
                             'geometry':relative(directory/'selected_routes.gpkg',work),'classification':relative(directory/'candidate_classification.csv',work),
                             'matrix':relative(directory/'network_sample_matrix.csv',work),'reserves':relative(directory/'reserve_routes.csv',work),
                             'field_checklist':relative(directory/'field_checklist.csv',work),'map':relative(directory/'selected_routes_map.png',work)}}
            result['paths'].update(variables_geometry=relative(directory/'route_variables.gpkg',work),
                variables=relative(directory/'route_variables.csv',work),gates=relative(directory/'gate_checks.json',work),
                standardized_X=relative(directory/'X_standardized.csv',work))
            atomic_json(directory/'report.json',result)
            commit_manifest(directory,fingerprint,result,[p.name for p in directory.iterdir() if p.is_file() and p.name!='manifest.json'])
        publish_link(work,'selected_routes_30.gpkg',directory/'selected_routes.gpkg')
        atomic_json(work/'reports/selection/latest_selection_30.json',result)
    return result


def export_geometry(work,directory):
    from .gis import initialize,sink,check_layers
    from qgis.core import (QgsVectorLayer,QgsWkbTypes,QgsMapSettings,QgsMapRendererParallelJob,
                           QgsFillSymbol,QgsLineSymbol,QgsRendererCategory,QgsCategorizedSymbolRenderer)
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor,QImage,QPainter,QFont
    context=initialize(work)
    payload=json.loads((directory/'selection_payload.json').read_text())
    parent=input_path(work,payload['parent_directory'])
    selected=set(payload['selected_ids'])
    info={r['route_id']:r for r in payload['features']}
    source=QgsVectorLayer(str(parent/'candidate_routes.gpkg')+'|layername=candidate_routes','source','ogr')
    if not source.isValid():raise ValueError('Invalid source route geometry')
    path=directory/'selected_routes.gpkg'
    temporary=directory/'.selected_routes.export.gpkg'
    temporary.unlink(missing_ok=True)
    fields=[('route_id','str'),('group','str'),('stratum_id','str'),('rc_target','str'),('length_m','float'),
            ('selected','bool'),('status','str'),('final_context_score','float'),('C6_status','str')]
    for key in payload['features'][0]:
        if key in {name for name,kind in fields}:
            continue
        values=[row[key] for row in payload['features'] if row[key] is not None]
        exemplar=values[0] if values else None
        kind='bool' if isinstance(exemplar,bool) else 'str' if isinstance(exemplar,str) else 'float'
        fields.append((key,kind))
    with sink(temporary,'candidate_assessment',fields,QgsWkbTypes.LineString,'EPSG:3405',context) as all_routes:
        for feature in source.getFeatures():
            rid=str(feature['route_id']);row=info[rid]
            if not feature.geometry().isGeosValid():raise ValueError('Invalid source route '+rid)
            all_routes.add(row,feature.geometry())
    for layer_name,flag in [('selected_routes',True),('reserve_routes',False)]:
        with sink(temporary,layer_name,fields,QgsWkbTypes.LineString,'EPSG:3405',context) as target:
            for feature in source.getFeatures():
                rid=str(feature['route_id'])
                if (rid in selected)==flag:target.add(info[rid],feature.geometry())
    anchors=QgsVectorLayer(str(parent/'candidate_routes.gpkg')+'|layername=anchors','anchors','ogr')
    with sink(temporary,'selected_anchors',[('route_id','str'),('order','int'),('node_id','str'),('safe_stop_verified','bool')],QgsWkbTypes.Point,'EPSG:3405',context) as target:
        for feature in anchors.getFeatures():
            if str(feature['route_id']) in selected:
                target.add({'route_id':str(feature['route_id']),'order':int(feature['order']),
                            'node_id':str(feature['node_id']),'safe_stop_verified':False},feature.geometry())
    check_layers(temporary,{'candidate_assessment':60,'selected_routes':30,'reserve_routes':30,'selected_anchors':90},'EPSG:3405')
    temporary.replace(path)
    hanoi=QgsVectorLayer(str(parent/'sampling_zones.gpkg')+'|layername=hanoi','hanoi','ogr')
    inside=QgsVectorLayer(str(parent/'sampling_zones.gpkg')+'|layername=sampling_inside','research_scope','ogr')
    hanoi.renderer().setSymbol(QgsFillSymbol.createSimple({'color':'#f7f8f5','outline_color':'#88929b','outline_width':'0.3'}))
    inside.renderer().setSymbol(QgsFillSymbol.createSimple({'color':'#dbeaf3','outline_color':'#699ebc','outline_width':'0.2'}))
    source.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':'#c5c9c9','line_width':'0.25'}))
    target=QgsVectorLayer(str(path)+'|layername=selected_routes','selected','ogr')
    target.setRenderer(QgsCategorizedSymbolRenderer('group',[
        QgsRendererCategory('inside',QgsLineSymbol.createSimple({'line_color':'#166ea7','line_width':'0.8'}),'18 trong'),
        QgsRendererCategory('outside',QgsLineSymbol.createSimple({'line_color':'#188160','line_width':'0.75'}),'12 ngoài')]))
    settings=QgsMapSettings();settings.setLayers([target,source,inside,hanoi]);settings.setDestinationCrs(hanoi.crs())
    extent=hanoi.extent();extent.scale(1.06);settings.setExtent(extent);settings.setOutputSize(QSize(1330,820));settings.setBackgroundColor(QColor('white'))
    job=QgsMapRendererParallelJob(settings);job.start();job.waitForFinished()
    image=QImage(1400,1060,QImage.Format.Format_ARGB32);image.fill(QColor('white'));painter=QPainter(image)
    painter.setPen(QColor('#203e55'));painter.setFont(QFont('Arial',22,QFont.Weight.Bold));painter.drawText(40,50,'30 TUYẾN DỰ KIẾN ĐI KHẢO SÁT · LEZ 2030')
    painter.setFont(QFont('Arial',12));painter.drawText(40,86,'18 trong LEZ (10 A + 8 B) / 12 ngoài LEZ · 60 ứng viên: 20 A + 20 B + 20 C · chưa đo thực địa')
    painter.drawImage(35,115,job.renderedImage());painter.setFont(QFont('Arial',12))
    painter.fillRect(45,953,25,15,QColor('#166ea7'));painter.drawText(85,966,'18 tuyến trong (10 A + 8 B)')
    painter.fillRect(330,953,25,15,QColor('#188160'));painter.drawText(370,966,'12 tuyến ngoài')
    painter.fillRect(650,953,25,15,QColor('#c5c9c9'));painter.drawText(690,966,'30 tuyến dự phòng / chưa chọn')
    painter.setFont(QFont('Arial',10));painter.drawText(40,1010,'Phạm vi nghiên cứu đã cố định; lớp đối chiếu OSM chưa được xác minh là GIS pháp lý. C6/quyền đi/điểm dừng chờ khảo sát.')
    painter.drawText(40,1040,'Nguồn hình học: OpenStreetMap contributors (ODbL). Chỉ chọn và sao chép hình học có sẵn; không sửa tuyến hoặc OSM gốc.')
    painter.end();temp_map=directory/'.selected_routes_map.tmp.png'
    if not image.save(str(temp_map),'PNG'):raise RuntimeError('Map export failed')
    temp_map.replace(directory/'selected_routes_map.png')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['preflight','run','status','export','precompute'])
    parser.add_argument('--work',type=Path,default=WORK)
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    if args.command=='export':export_geometry(args.work,args.directory);return
    if args.command=='precompute':
        from .selection_metrics import load_data
        from .selection_gates import verify_gates, export_variables
        options=configuration(args.work)
        parent=json.loads(input_path(args.work, options.get('parent_report', 'reports/sampling/latest_sampling_2030.json')).read_text())
        data=load_data(args.work,parent,options)
        gates=verify_gates(args.work,parent,data)
        atomic_json(args.directory/'gate_checks.json',gates)
        export_variables(args.work,parent,data,args.directory)
        return
    result=preflight_selection(args.work) if args.command=='preflight' else selection_status(args.work) if args.command=='status' else run_selection(args.work,args.force)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
