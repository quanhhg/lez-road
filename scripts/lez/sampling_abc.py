"""LEZ-first ABC candidates: 2027 pilot, 2030 remainder, and outside 2030."""
from __future__ import annotations
import argparse
from collections import Counter, deque
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'lez'
from .common import (WORK, atomic_json, cached_manifest, code_hash, commit_manifest, digest,
                     event, file_hash, input_path, now, processing_lock, publish_link, relative, write_csv)
RC_CLASSES = ('RC1','RC2','RC3','RC4')
ZONES = ('A','B','C')


def configuration(work=WORK):
    work=Path(work)
    options=json.loads((work/'config/sampling_abc.json').read_text())
    targets=options['targets']
    if len({t['route_id'] for t in targets}) != 60 or Counter(t['sampling_zone'] for t in targets) != options['candidate_quota']:
        raise ValueError('Expected 60 unique candidates, 20 in each A/B/C')
    if options['candidate_quota'] != dict(A=20,B=20,C=20):
        raise ValueError('Current user design requires 20 A / 20 B / 20 C')
    for t in targets:
        if t['stratum_id'] != t['sampling_zone'] or t['rc_target'] not in RC_CLASSES or t['group'] != ('outside' if t['sampling_zone']=='C' else 'inside'):
            raise ValueError('ABC target must carry an explicit compatible 2030 group')
    snapshot=json.loads((work/'data/hanoi_tiles/tile_project.json').read_text())['snapshot_utc']
    if options['source_snapshot_utc'] != snapshot:
        raise ValueError('Snapshot mismatch')
    return options


def _normalization(work,options):
    report=json.loads(input_path(work,options['normalization_report']).read_text())
    directory=input_path(work,report['paths']['directory'])
    manifest=json.loads((directory/'manifest.json').read_text())
    if not cached_manifest(directory,manifest['fingerprint']):
        raise ValueError('Frozen normalization cache is missing or corrupt; run normalization first')
    return report,directory


def preflight(work=WORK):
    """Validate configuration and immutable inputs; no HTTP request."""
    work=Path(work).resolve();options=configuration(work)
    report,directory=_normalization(work,options)
    from .pipeline import kernel_spec
    for k in ['network_path','graph_path','source_document','ring_config','policy_config']:
        if not input_path(work,options[k]).is_file(): raise ValueError('Missing '+k)
    return {'status':'ready','candidate_quota':options['candidate_quota'],
            'selection_quota':options['selection_quota'],'matrix_cells':12,
            'snapshot_utc':options['source_snapshot_utc'],'network_calls':0,
            'normalization_directory':relative(directory,work),'qgis_runtime':kernel_spec()['argv'][0],
            'zone_basis':'LEZ2027_pilot_and_LEZ2030_policy_first',
            'legacy_normalization_role':'Hanoi_source_and_supplemental_audit_only',
            'target_reallocation':options.get('target_reallocation'),
            'routing_unavailable_cells':options.get('routing_unavailable_cells',[])}


def composition(matrix,sample=None,unique=None,domain_matrix=None):
    sample=sample or {};unique=unique or {};domain_matrix=domain_matrix or {}
    cells=[(z,rc) for z in ZONES for rc in RC_CLASSES]
    for values in (matrix,sample,unique):
        if any(h not in ZONES or not math.isfinite(v) or v<0 for (h,k),v in values.items()):
            raise ValueError('Invalid ABC composition lengths')
    nd=sum(matrix.get(c,0) for c in cells);sd=sum(sample.get(c,0) for c in cells)
    domains={g:sum(v for (h,k,group),v in domain_matrix.items() if group==g and k in RC_CLASSES) for g in ('inside','outside')}
    network=[];rows=[]
    for z,rc in cells:
        n=matrix.get((z,rc),0);v=sample.get((z,rc),0)
        network.append({'stratum_id':z,'sampling_zone':z,'rc':rc,'network_length_m':n,
                        'network_fraction_all_rc':n/nd if nd else None,
                        'network_inside_length_m':domain_matrix.get((z,rc,'inside'),0),
                        'network_outside_length_m':domain_matrix.get((z,rc,'outside'),0)})
        rows.append({'stratum_id':z,'rc':rc,'network_length_m':n,'sample_traversed_length_m':v,
                     'sample_unique_length_m':unique.get((z,rc),0),'network_fraction':n/nd if nd else None,
                     'sample_fraction':v/sd if sd else None,'gap_fraction':n/nd-v/sd if nd and sd else None,
                     'unique_coverage_fraction':unique.get((z,rc),0)/n if n else None})
    others=sorted({c for x in (matrix,sample,unique) for c in x if c[1] not in RC_CLASSES},key=lambda c:(c[0],str(c[1])))
    connectors=[{'stratum_id':z,'group':'mixed_by_LEZ_overlay','rc':rc or 'unclassified','network_length_m':matrix.get((z,rc),0),
                 'sample_traversed_length_m':sample.get((z,rc),0),'sample_unique_length_m':unique.get((z,rc),0),'included_in_rc_composition':False} for z,rc in others]
    return network,rows,connectors,{'network_rc_m':nd,'sample_rc_m':sd,'network_all_m':sum(matrix.values()),
             'sample_all_m':sum(sample.values()),'network_connector_m':sum(r['network_length_m'] for r in connectors),
             'sample_connector_m':sum(r['sample_traversed_length_m'] for r in connectors),
             'network_rc_domain_m':domains,'D_combined':0.5*sum(abs(r['gap_fraction']) for r in rows) if nd and sd else None,
             'network_fraction_sum':sum(r['network_fraction'] for r in rows) if nd else None,
             'sample_fraction_sum':sum(r['sample_fraction'] for r in rows) if sd else None}


def overlay_network(work,directory,options,context,crs,zones,inside,reference):
    from .gis import sink,QgsWkbTypes
    from .graph import MotorcycleNetwork
    from .sampling_2030 import _engine,_line
    from qgis.core import QgsGeometry,QgsVectorLayer
    network=MotorcycleNetwork.load(input_path(work,options['graph_path']))
    if network.data['snapshot_utc']!=options['source_snapshot_utc']:raise ValueError('Graph snapshot differs')
    lengths={a['part_id']:a['length_m'] for a in network.arcs.values()}
    rc_by_part={a['part_id']:a['rc'] for a in network.arcs.values()}
    layer=QgsVectorLayer(str(input_path(work,options['network_path']))+'|layername=scope_parts','parts','ogr')
    if not layer.isValid() or layer.crs().authid()!=crs:raise ValueError('Invalid network layer or CRS')
    zone_engines={z:_engine(g) for z,g in zones.items()};inside_engine=_engine(inside);ref_engine=_engine(reference)
    shapes={};meta={};matrix=Counter();domains=Counter();max_error=0.;pieces=0
    building=directory/'.network_parts.building.gpkg';building.unlink(missing_ok=True)
    fields=[('part_id','str'),('segment_id','str'),('stratum_id','str'),('sampling_zone','str'),('group','str'),('rc','str'),('length_m','float')]
    with sink(building,'network_parts',fields,QgsWkbTypes.MultiLineString,crs,context) as out:
        for index,f in enumerate(layer.getFeatures()):
            pid=str(f['part_id'])
            if pid not in lengths:continue
            g=QgsGeometry(f.geometry());length=g.length();rc=rc_by_part[pid]
            if abs(length-lengths[pid])>.01:raise ValueError('Source length mismatch '+pid)
            shapes[pid]=g
            li=length if inside_engine.contains(g.constGet()) else g.intersection(inside).length() if inside_engine.intersects(g.constGet()) else 0.
            lr=length if ref_engine.contains(g.constGet()) else g.intersection(reference).length() if ref_engine.intersects(g.constGet()) else 0.
            group='inside' if abs(li-length)<=1e-5 else 'outside' if li<=1e-5 else None
            cells=[];zone_lengths=Counter();remaining=QgsGeometry(g);assigned=0.
            for z,region in zones.items():
                engine=zone_engines[z]
                if remaining.isEmpty() or not g.boundingBox().intersects(region.boundingBox()) or not engine.intersects(remaining.constGet()):continue
                piece=_line(QgsGeometry(remaining) if engine.contains(remaining.constGet()) else remaining.intersection(region))
                if piece.isEmpty() or piece.length()<1e-7:continue
                size=piece.length();cells.append((z,rc,size));matrix[(z,rc)]+=size;zone_lengths[z]+=size;assigned+=size
                # Partition every physical length once, independently by ABC and LEZ.
                if group:
                    bits=[(group,piece)]
                else:
                    bit=_line(piece.intersection(inside));other=_line(piece.difference(inside));bits=[('inside',bit),('outside',other)]
                for domain,bit in bits:
                    if bit.isEmpty() or bit.length()<1e-7:continue
                    bit.convertToMultiType();d=bit.length();domains[(z,rc,domain)]+=d;pieces+=1
                    out.add({'part_id':pid,'segment_id':str(f['segment_id']),'stratum_id':z,'sampling_zone':z,'group':domain,'rc':rc,'length_m':d},bit)
                remaining=_line(remaining.difference(piece))
            error=abs(assigned-length);max_error=max(max_error,error)
            if error>.02:raise ValueError('ABC overlay lost/duplicated length '+pid+': '+str(error))
            pure_zone=next((z for z,v in zone_lengths.items() if abs(v-length)<=1e-5),None)
            meta[pid]={'pure_group':group,'pure_zone':pure_zone,'cells':cells,'reference_inside_m':lr,'length_m':length}
            if index%50000==0:event('abc_overlay','Đang cắt mạng theo ABC và LEZ',source_index=index)
    building.replace(directory/'network_parts.gpkg')
    if set(meta)!=set(lengths):raise ValueError('Missing graph parts')
    domain_partition_error=max((abs(v-domains.get((h,k,'inside'),0)-domains.get((h,k,'outside'),0)) for (h,k),v in matrix.items()),default=0.)
    if domain_partition_error>.02:raise ValueError('LEZ domains do not partition ABC cells')
    rows,_,_,comp=composition(matrix,domain_matrix=domains)
    write_csv(directory/'network_matrix.csv',rows,list(rows[0]))
    report={'physical_routable_parts':len(meta),'normalized_pieces':pieces,'network_length_m':sum(lengths.values()),
            'rc1_rc4_network_length_m':comp['network_rc_m'],'connector_network_length_m':comp['network_connector_m'],
            'statistical_cells':12,'max_domain_cell_partition_error_m':domain_partition_error,'max_part_length_error_m':max_error,'aggregate_length_error_m':abs(sum(matrix.values())-sum(lengths.values())),
            'cross_ABC_boundary_parts_excluded_from_candidate_routing':sum(not p['pure_zone'] for p in meta.values()),
            'cross_LEZ_boundary_parts_excluded_from_candidate_routing':sum(not p['pure_group'] for p in meta.values()),
            'rc1_rc4_domain_lengths_m':comp['network_rc_domain_m'],'rc_network_fraction_sum':comp['network_fraction_sum'],
            'status':'provisional_access_network_not_field_verified'}
    atomic_json(directory/'overlay_report.json',report)
    coordinates={n['node_id']:(n['x'],n['y']) for n in network.data['nodes']}
    return network,meta,shapes,coordinates,matrix,report,domains


def build_candidates(work,directory,options,context,crs,overlay):
    from .gis import sink,QgsWkbTypes,check_layers
    from .routing import generate
    from qgis.core import QgsGeometry,QgsPointXY
    network,meta,geometry,coords,matrix,overlay_report,domain_matrix=overlay
    def progress(route_id,count,accepted,reasons):event('routes','Đã xét ứng viên',route_id=route_id,created=count,accepted=accepted,reasons=reasons)
    routes,failed,pairs=generate(network,meta,coords,options['targets'],options['route_design'],progress)
    building=directory/'.candidate_routes.building.gpkg';building.unlink(missing_ok=True)
    fields=[('route_id','str'),('group','str'),('stratum_id','str'),('sampling_zone','str'),('lez2027_group','str'),('lez2030_group','str'),('policy_version','str'),('survey_date','str'),('lez_status_at_survey','str'),('rc_target','str'),('length_m','float'),('target_cell_fraction','float'),('reference_inside_length_fraction','float'),('status','str')]
    anchor_rows=[];sample=Counter();unique_sample=Counter();walk_rows=[];used=set()
    with sink(building,'candidate_routes',fields,QgsWkbTypes.LineString,crs,context) as output:
        for route in routes:
            points=[];length=0.0
            for order,aid in enumerate(route['arc_ids']):
                arc=network.arcs[aid];pid=arc['part_id'];poly=geometry[pid].asPolyline()
                if arc['direction']=='backward':poly=list(reversed(poly))
                if points and math.dist((points[-1].x(),points[-1].y()),(poly[0].x(),poly[0].y()))>0.001:raise ValueError('Reconstructed candidate geometry is disconnected')
                points.extend(poly if not points else poly[1:]);length+=geometry[pid].length()
                walk_rows.append({'route_id':route['route_id'],'order':order,'arc_id':aid,'part_id':pid,'direction':arc['direction'],'length_m':arc['length_m']})
                for h,k,l in meta[pid]['cells']:
                    sample[(h,k)]+=l
                    if pid not in used:unique_sample[(h,k)]+=l
                used.add(pid)
            geom=QgsGeometry.fromPolylineXY(points)
            if abs(geom.length()-route['length_m'])>0.02:raise ValueError('Reconstructed candidate length mismatch')
            output.add(route,geom)
            for order,node in enumerate(route['anchors']):anchor_rows.append({'route_id':route['route_id'],'order':order,'node_id':node,'x':coords[node][0],'y':coords[node][1],'safe_stop_verified':False})
    with sink(building,'anchors', [('route_id','str'),('order','int'),('node_id','str'),('safe_stop_verified','bool')],QgsWkbTypes.Point,crs,context) as output:
        for anchor in anchor_rows:output.add(anchor,QgsGeometry.fromPointXY(QgsPointXY(anchor['x'],anchor['y'])))
    building.replace(directory/'candidate_routes.gpkg')
    check_layers(directory/'candidate_routes.gpkg',{'candidate_routes':len(routes),'anchors':len(anchor_rows)},crs)
    atomic_json(directory/'candidate_walks.json',routes)
    atomic_json(directory/'failed_targets.json',failed)
    atomic_json(directory/'overlap_review.json',pairs)
    route_rows=[{k:v for k,v in r.items() if k not in ['arc_ids','part_ids','anchors']} for r in routes]
    route_fields=list(route_rows[0]) if route_rows else [k for k in options['targets'][0]]+['group','length_m','target_cell_fraction','reference_inside_length_fraction','status']
    write_csv(directory/'candidate_routes.csv',route_rows,route_fields)
    write_csv(directory/'route_arcs.csv',walk_rows,['route_id','order','arc_id','part_id','direction','length_m'])
    write_csv(directory/'anchors.csv',anchor_rows,['route_id','order','node_id','x','y','safe_stop_verified'])
    _,coverage,connectors,composition_result=composition(matrix,sample,unique_sample,domain_matrix)
    denom=composition_result['network_rc_m'];sample_denom=composition_result['sample_rc_m']
    write_csv(directory/'sample_matrix.csv',coverage,list(coverage[0]))
    write_csv(directory/'connector_summary.csv',connectors,
              ['stratum_id','group','rc','network_length_m','sample_traversed_length_m','sample_unique_length_m','included_in_rc_composition'])
    overlaps=[]
    for index,left in enumerate(routes):
        for right in routes[index+1:]:
            common=sum(meta[p]['length_m'] for p in set(left['part_ids']) & set(right['part_ids']))
            unique_min=min(sum(meta[p]['length_m'] for p in set(left['part_ids'])),sum(meta[p]['length_m'] for p in set(right['part_ids'])))
            overlaps.append({'left':left['route_id'],'right':right['route_id'],'common_length_m':common,
                             'traversed_overlap_fraction':common/min(left['length_m'],right['length_m']),
                             'unique_corridor_overlap_fraction':common/unique_min})
    write_csv(directory/'route_overlap.csv',overlaps,['left','right','common_length_m','traversed_overlap_fraction','unique_corridor_overlap_fraction'])
    D_by_domain={}
    for domain in ['inside','outside']:
        network_domain=sum(v for (h,k,g),v in domain_matrix.items() if g==domain and k in RC_CLASSES)
        domain_sample=Counter()
        for route in routes:
            if route['group']==domain:
                for pid in route['part_ids']:
                    for h,k,length in meta[pid]['cells']:
                        if k in RC_CLASSES:domain_sample[(h,k)]+=length
        sample_domain=sum(domain_sample.values())
        D_by_domain[domain]=.5*sum(abs(domain_matrix.get((h,k,domain),0)/network_domain-domain_sample[(h,k)]/sample_domain) for h in ZONES for k in RC_CLASSES) if network_domain and sample_domain else None
    composition_result['sample_rc_domain_m']={g:sum(l for r in routes if r['group']==g for pid in r['part_ids'] for h,k,l in meta[pid]['cells'] if k in RC_CLASSES) for g in ['inside','outside']}
    zone_counts=Counter(r['sampling_zone'] for r in routes)
    counts=Counter(r['group'] for r in routes)
    report={'created_routes':len(routes),'inside':counts['inside'],'outside':counts['outside'],'requested_inside':40,'requested_outside':20,'sampling_zone_counts':dict(zone_counts),'requested_zone_counts':options['candidate_quota'],
            'geometry_quota_achieved':dict(zone_counts)==options['candidate_quota'] and counts['inside']==40 and counts['outside']==20,'verified_measurement_quota_achieved':False,
            'all_walks_direction_continuity_turn_checked':True,'all_routes_pure_in_frozen_sampling_scope':True,
            'all_targets_cell_fraction_at_least':options['route_design']['target_cell_min_fraction'],
            'duplicate_corridor_sets':len(routes)-len({frozenset(r['part_ids']) for r in routes}),
            'overlap_pairs_to_review':len(pairs),'failed_targets':failed,'pending_field_check_routes':len(routes),
            'D_combined':composition_result['D_combined'],
            'D_by_domain':D_by_domain,'overlap_pairs_calculated':len(overlaps),
            'network_denominator_m':denom,'sample_denominator_m':sample_denom,
            'all_network_length_m':composition_result['network_all_m'],'all_sample_traversed_length_m':composition_result['sample_all_m'],
            'connector_network_length_m':composition_result['network_connector_m'],'connector_sample_traversed_length_m':composition_result['sample_connector_m'],
            'network_rc_domain_lengths_m':composition_result['network_rc_domain_m'],'sample_rc_domain_lengths_m':composition_result['sample_rc_domain_m'],
            'network_fraction_sum':composition_result['network_fraction_sum'],'sample_fraction_sum':composition_result['sample_fraction_sum'],
            'statistical_cells':len(coverage),'composition_classes':list(RC_CLASSES),'connectors_in_composition':False,
            'sample_composition_counts_shared_parts_for_each_traversal':True,'unique_coverage_counts_physical_parts_once':True,
            'route_design':options['route_design'],'final_30_selection_performed':False}
    atomic_json(directory/'candidate_report.json',report)
    return report



def fine_matrix(directory,normalization_directory,zones,context,crs):
    """Diagnostic old V/N strata × ABC × RC, never a quota constraint."""
    from .sampling_2030 import _engine
    from qgis.core import QgsGeometry,QgsVectorLayer
    layer=QgsVectorLayer(str(normalization_directory/'network_parts.gpkg')+'|layername=network_parts','legacy_parts','ogr')
    if not layer.isValid():raise ValueError('Missing frozen fine overlay')
    engines={z:_engine(g) for z,g in zones.items()};counts=Counter()
    for f in layer.getFeatures():
        geom=QgsGeometry(f.geometry());remaining=QgsGeometry(geom)
        for z,region in zones.items():
            if remaining.isEmpty() or not geom.boundingBox().intersects(region.boundingBox()) or not engines[z].intersects(remaining.constGet()):continue
            part=QgsGeometry(remaining) if engines[z].contains(remaining.constGet()) else remaining.intersection(region)
            length=part.length()
            if length>1e-7:
                counts[(z,str(f['stratum_id']),str(f['group']),str(f['rc']) if f['rc'] else '')]+=length
                remaining=remaining.difference(part)
    rows=[{'sampling_zone':z,'legacy_stratum_id':h,'legacy_adjusted_group':g,'rc':rc,'network_length_m':v} for (z,h,g,rc),v in sorted(counts.items())]
    write_csv(directory/'fine_network_matrix.csv',rows,list(rows[0]))
    return {'fine_matrix_cells':len(rows),'fine_matrix_length_m':sum(counts.values())}


def execute(work=WORK,force=False):
    from .gis import initialize,read_polygon,sink,QgsWkbTypes,check_layers
    from .policy_boundaries import build as build_policy_regions
    from .sampling_2030 import _engine
    work=Path(work).resolve();options=configuration(work);preflight(work)
    normalization,source=_normalization(work,options)
    source_paths=[input_path(work,options[k]) for k in ['network_path','graph_path','source_document','ring_config','policy_config']]
    ring_options=json.loads(input_path(work,options['ring_config']).read_text())
    source_paths.append(input_path(work,ring_options['source_network']))
    source_paths.extend(input_path(work,v['file']) for v in ring_options.get('sources',[]) if v.get('file'))
    policy_options=json.loads(input_path(work,options['policy_config']).read_text())
    source_paths.extend(input_path(work,v['file']) for v in policy_options.get('sources',[]) if v.get('file'))
    source_paths.extend([work/'config/sampling_abc.json',source/'manifest.json',source/'sampling_zones.gpkg',source/'network_parts.gpkg'])
    fingerprint=digest({'stage':options['method_version'],'inputs':{relative(p,work):file_hash(p) for p in source_paths},
                        'code':code_hash(['common.py','gis.py','graph.py','routing.py','sampling_2030.py','sampling_abc.py','abc_boundaries.py','policy_boundaries.py'])})
    directory=work/'data/processed/sampling_abc'/fingerprint[:20]
    with processing_lock(work):
        cached=None if force else cached_manifest(directory,fingerprint)
        if cached:
            result=dict(cached['report'],cache_hit=True)
        else:
            directory.mkdir(parents=True,exist_ok=True);started=now();timer=time.monotonic()
            context=initialize(work);crs=json.loads((work/'data/hanoi_tiles/tile_project.json').read_text())['metric_crs']
            hanoi=read_polygon(source/'sampling_zones.gpkg',crs,context,'hanoi')
            event('abc','Đang dựng A theo LEZ 2027, B theo LEZ 2030 trừ A, C ngoài LEZ 2030')
            policy=build_policy_regions(work,hanoi,context,output_dir=directory,options=policy_options)
            zones=policy['groups'];inside=policy['lez2030'];reference=policy['lez2030']
            boundary=policy['report'];uncertainty=policy['exclusion_geometry']
            # Publish fresh policy scopes; legacy population/activity adjustments
            # are never copied into the current LEZ-first classification layers.
            scope_path=directory/'sampling_zones.gpkg'
            scope_path.unlink(missing_ok=True)
            scopes={'hanoi':hanoi,'sampling_inside':inside,'sampling_outside':zones['C'],
                    'reference_lez_2030':inside,'lez2027':policy['lez2027'],'lez2030':inside}
            for layer_name,geometry in scopes.items():
                with sink(scope_path,layer_name,[('scope','str'),('policy_version','str'),('official_gis_verified','bool')],QgsWkbTypes.MultiPolygon,crs,context) as out:
                    shape=type(geometry)(geometry);shape.convertToMultiType()
                    out.add({'scope':layer_name,'policy_version':options['policy_version'],'official_gis_verified':False},shape)
            with sink(scope_path,'abc_zones',[('sampling_zone','str'),('stratum_id','str'),('area_m2','float'),('status','str')],QgsWkbTypes.MultiPolygon,crs,context) as out:
                for z,geom in zones.items():
                    shape=type(geom)(geom);shape.convertToMultiType()
                    out.add({'sampling_zone':z,'stratum_id':z,'area_m2':shape.area(),'status':'policy_first_technical_geometry'},shape)
            check_layers(directory/'sampling_zones.gpkg',{'abc_zones':3,'sampling_inside':1,'sampling_outside':1},crs)
            overlay=overlay_network(work,directory,options,context,crs,zones,inside,reference)
            if uncertainty and not uncertainty.isEmpty():
                engine=_engine(uncertainty);excluded=0
                for pid,g in overlay[2].items():
                    if g.boundingBox().intersects(uncertainty.boundingBox()) and engine.intersects(g.constGet()):
                        overlay[1][pid]['pure_zone']=None;excluded+=1
                overlay[5]['uncertain_ring_alignment_parts_excluded_from_routing']=excluded
                atomic_json(directory/'overlay_report.json',overlay[5])
            eligible=Counter()
            rc_by_part={a['part_id']:a['rc'] for a in overlay[0].arcs.values()}
            for pid,meta in overlay[1].items():
                if meta['pure_zone'] and meta['pure_group'] and rc_by_part[pid] in RC_CLASSES:
                    eligible[(meta['pure_zone'],rc_by_part[pid])]+=meta['length_m']
            eligible_rows=[{'sampling_zone':z,'rc':rc,'eligible_full_part_length_m':eligible[(z,rc)],
                            'network_overlay_length_m':overlay[4][(z,rc)],
                            'routing_status':'available' if eligible[(z,rc)] else 'unavailable'}
                           for z in ZONES for rc in RC_CLASSES]
            write_csv(directory/'routing_network_matrix.csv',eligible_rows,list(eligible_rows[0]))
            unavailable={(z,rc) for z in ZONES for rc in RC_CLASSES if not eligible[(z,rc)]}
            incompatible=[t['route_id'] for t in options['targets'] if (t['sampling_zone'],t['rc_target']) in unavailable]
            if incompatible:raise ValueError('Targets require unavailable routing cells: '+str(incompatible))
            overlay[5]['routing_unavailable_cells']=[{'sampling_zone':z,'rc':rc} for z,rc in sorted(unavailable)]
            overlay[5]['target_reallocation']=options.get('target_reallocation')
            atomic_json(directory/'overlay_report.json',overlay[5])
            fine=fine_matrix(directory,source,zones,context,crs)
            if abs(fine['fine_matrix_length_m']-overlay[5]['network_length_m'])>.1:raise ValueError('Fine and ABC matrix length totals disagree')
            candidates=build_candidates(work,directory,options,context,crs,overlay)
            boundary.update(official_gis_verified=False,lez_boundary_unchanged=False,
                            previous_adjusted_LEZ_scope_used_for_route_classification=False,
                            legacy_strata_count=15,legacy_strata_role='supplemental_audit_only',abc_strata_count=3,**fine)
            result={'status':'geometry_quota_achieved_pending_validation' if candidates['geometry_quota_achieved'] else 'candidate_quota_incomplete',
                    'method_version':options['method_version'],'policy_version':options['policy_version'],
                    'scope':'LEZ2027_A_LEZ2030_minus_A_B_outside_LEZ2030_C',
                    'started_at':started,'finished_at':now(),'elapsed_seconds':time.monotonic()-timer,
                    'boundary':boundary,'overlay':overlay[5],'candidates':candidates,'raw_osm_modified':False,'network_calls':0,'cache_hit':False,
                    'paths':{'directory':relative(directory,work),'zones':relative(directory/'sampling_zones.gpkg',work),
                             'sampling_zones':relative(directory/'sampling_zones.gpkg',work),'parts':relative(directory/'network_parts.gpkg',work),
                             'network_parts':relative(directory/'network_parts.gpkg',work),'routes':relative(directory/'candidate_routes.gpkg',work),
                             'route_csv':relative(directory/'candidate_routes.csv',work),'network_matrix':relative(directory/'network_matrix.csv',work),
                             'sample_matrix':relative(directory/'sample_matrix.csv',work),'fine_matrix':relative(directory/'fine_network_matrix.csv',work)}}
            atomic_json(directory/'report.json',result)
            # Incomplete pools remain inspectable, but cannot become reusable completed cache.
            if candidates['geometry_quota_achieved']:
                outputs=[p.name for p in directory.iterdir() if p.is_file() and not p.name.startswith('.') and p.name!='manifest.json']
                commit_manifest(directory,fingerprint,result,outputs)
        for name,target in [('sampling_abc.gpkg','sampling_zones.gpkg'),('network_parts_abc.gpkg','network_parts.gpkg'),('candidate_routes_abc.gpkg','candidate_routes.gpkg')]:
            publish_link(work,name,directory/target)
        atomic_json(work/'reports/sampling/latest_sampling_abc.json',result)
    return result


def status(work=WORK):
    path=Path(work)/'reports/sampling/latest_sampling_abc.json'
    return json.loads(path.read_text()) if path.exists() else {'status':'not_run'}


def run_sampling(work=WORK,force=False,progress=print):
    """Controller uses normal Python; geometry worker uses registered PyQGIS."""
    from .pipeline import kernel_spec
    work=Path(work).resolve();preflight(work);spec=kernel_spec();env=os.environ.copy();env.update(spec.get('env',{}));env['PYTHONUNBUFFERED']='1'
    args=[spec['argv'][0],str(Path(__file__).resolve()),'build','--worker','--work',str(work)]
    if force:args.append('--force')
    process=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    recent=deque(maxlen=30);result=None
    try:
        for line in process.stdout:
            recent.append(line.strip())
            try:message=json.loads(line)
            except ValueError:
                if progress:progress(line.strip())
                continue
            if message.get('event')=='result':result=message['result']
            elif progress:progress(message)
        if process.wait() or result is None:raise RuntimeError('ABC worker failed:\n'+'\n'.join(recent))
        return result
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
        if progress:progress('Đã dừng. Cache hoàn chỉnh và các phiên bản trước được giữ nguyên.')
        return status(work)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['check','build','run','status']);parser.add_argument('--work',type=Path,default=WORK);parser.add_argument('--force',action='store_true');parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    if args.command=='check':result=preflight(args.work)
    elif args.command=='status':result=status(args.work)
    elif args.command=='build' or args.worker:result=execute(args.work,args.force)
    else:result=run_sampling(args.work,args.force)
    print(json.dumps({'event':'result','result':result},ensure_ascii=False))
if __name__=='__main__':main()
