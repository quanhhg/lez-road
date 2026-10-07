"""Build the 2030 research sampling scope, normalized overlay and 20/40 candidates."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import signal
import subprocess
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'lez'

from .common import (WORK, atomic_json, cached_manifest, code_hash, commit_manifest, digest,
                     event, file_hash, input_path, now, processing_lock, publish_link, relative, write_csv)

RC_CLASSES = ('RC1', 'RC2', 'RC3', 'RC4')
STRATA_CODES = tuple([f'V{i}' for i in range(1, 6)] + [f'N{i}' for i in range(1, 11)])


def rc_composition(matrix, sample=None, unique_sample=None):
    """RC-only composition; connector lengths remain separate diagnostics.

    Matrix counts unique physical network length; sample counts traversals and
    unique_sample counts each sampled physical part once. Empty denominators
    produce None, never an invented zero composition or discrepancy.
    """
    sample = {} if sample is None else sample
    unique_sample = {} if unique_sample is None else unique_sample
    for values in [matrix, sample, unique_sample]:
        if any(h not in STRATA_CODES or not math.isfinite(v) or v < 0 for (h, k), v in values.items()):
            raise ValueError('Composition requires valid strata and finite non-negative lengths')
    rc_cells = [(h, k) for h in STRATA_CODES for k in RC_CLASSES]
    network_total = sum(matrix.get(cell, 0.0) for cell in rc_cells)
    sample_total = sum(sample.get(cell, 0.0) for cell in rc_cells)
    network_domain = {group: sum(matrix.get((h, k), 0.0) for h, k in rc_cells if h.startswith(prefix))
                      for group, prefix in [('inside', 'V'), ('outside', 'N')]}
    sample_domain = {group: sum(sample.get((h, k), 0.0) for h, k in rc_cells if h.startswith(prefix))
                     for group, prefix in [('inside', 'V'), ('outside', 'N')]}
    network_rows, sample_rows = [], []
    for h, k in rc_cells:
        group = 'inside' if h.startswith('V') else 'outside'
        length, traversed, unique = (values.get((h, k), 0.0) for values in [matrix, sample, unique_sample])
        q = length / network_total if network_total else None
        q_sample = traversed / sample_total if sample_total else None
        network_rows.append({'stratum_id': h, 'group': group, 'rc': k, 'network_length_m': length,
                             'network_fraction_all_rc': q,
                             'network_fraction_domain_rc': length / network_domain[group] if network_domain[group] else None})
        sample_rows.append({'stratum_id': h, 'rc': k, 'network_length_m': length,
                            'sample_traversed_length_m': traversed, 'sample_unique_length_m': unique,
                            'network_fraction': q, 'sample_fraction': q_sample,
                            'gap_fraction': q - q_sample if q is not None and q_sample is not None else None,
                            'unique_coverage_fraction': unique / length if length else None})
    non_rc_cells = sorted({cell for values in [matrix, sample, unique_sample] for cell in values if cell[1] not in RC_CLASSES},
                          key=lambda cell: (cell[0], str(cell[1])))
    connector_rows = [{'stratum_id': h, 'group': 'inside' if h.startswith('V') else 'outside',
                       'rc': k or 'unclassified', 'network_length_m': matrix.get((h, k), 0.0),
                       'sample_traversed_length_m': sample.get((h, k), 0.0),
                       'sample_unique_length_m': unique_sample.get((h, k), 0.0),
                       'included_in_rc_composition': False} for h, k in non_rc_cells]
    domain_d = {}
    for group, prefix in [('inside', 'V'), ('outside', 'N')]:
        nd, sd = network_domain[group], sample_domain[group]
        domain_d[group] = 0.5 * sum(abs(matrix.get((h, k), 0.0) / nd - sample.get((h, k), 0.0) / sd)
                                  for h, k in rc_cells if h.startswith(prefix)) if nd and sd else None
    metrics = {'network_rc_m': network_total, 'sample_rc_m': sample_total,
               'network_all_m': sum(matrix.values()), 'sample_all_m': sum(sample.values()),
               'network_connector_m': sum(r['network_length_m'] for r in connector_rows),
               'sample_connector_m': sum(r['sample_traversed_length_m'] for r in connector_rows),
               'network_rc_domain_m': network_domain, 'sample_rc_domain_m': sample_domain,
               'D_combined': 0.5 * sum(abs(r['gap_fraction']) for r in sample_rows) if network_total and sample_total else None,
               'D_by_domain': domain_d,
               'network_fraction_sum': sum(r['network_fraction'] for r in sample_rows) if network_total else None,
               'sample_fraction_sum': sum(r['sample_fraction'] for r in sample_rows) if sample_total else None}
    return network_rows, sample_rows, connector_rows, metrics


def config(work):
    work = Path(work)
    options = json.loads((work/'config/sampling_2030.json').read_text())
    policy = json.loads(input_path(work,options['policy']).read_text())
    if policy['legal_reference']['scope_selection_status'] != 'user_selected_2030':
        raise ValueError('2030 must be explicitly selected in the sampling policy')
    ref = policy['legal_reference']
    if file_hash(input_path(work,ref['source_file'])) != ref['source_sha256']:
        raise ValueError('Legal reference PDF has changed')
    project=json.loads((work/'data/hanoi_tiles/tile_project.json').read_text())
    if project['snapshot_utc'] != options['source_snapshot_utc']:
        raise ValueError('Sampling and OSM project snapshots disagree')
    targets = options['targets']
    ids = [t['route_id'] for t in targets]
    if len(ids) != len(set(ids)) or Counter(i[0] for i in ids) != {'L':20,'O':40}:
        raise ValueError('Expected 20 unique L targets and 40 unique O targets')
    if options['boundary_band_m'] != policy['sampling_scope']['boundary_band']['distance_m']:
        raise ValueError('Boundary band disagrees between config and policy')
    if options['classification_weights'] != policy['sampling_scope']['weights'] or options['score_threshold'] != policy['sampling_scope']['classification']['inside_score_at_least']:
        raise ValueError('Classification weights/threshold disagree between config and policy')
    if any(options['classification_weights'][k] < 0 for k in ['population_density','activity_density']) or abs(sum(options['classification_weights'].values())-1) > 1e-9:
        raise ValueError('Classification weights must be non-negative and sum to one')
    if options['classification_weights'] != policy['sampling_scope']['weights'] or options['score_threshold'] != policy['sampling_scope']['classification']['inside_score_at_least']:
        raise ValueError('Classification weights/threshold disagree with declared sampling policy')
    if not 0 <= options['score_threshold'] <= 1 or options['boundary_band_m'] <= 0:
        raise ValueError('Invalid band or threshold')
    return options, policy


def _load_geometries(work):
    from .gis import initialize, read_polygon
    from qgis.core import QgsGeometry, QgsVectorLayer
    options, policy = config(work)
    context = initialize(work)
    crs = json.loads((Path(work)/'data/hanoi_tiles/tile_project.json').read_text())['metric_crs']
    layer = QgsVectorLayer(str(input_path(work,options['boundary_admin_path']))+'|layername=admin_units','admin','ogr')
    if not layer.isValid() or layer.crs().authid() != crs or layer.featureCount() != 126:
        raise ValueError('Expected 126 valid administrative geometries in the project metric CRS')
    admins = {}
    for feature in layer.getFeatures():
        geometry = QgsGeometry(feature.geometry())
        if geometry.isEmpty() or not geometry.isGeosValid():
            raise ValueError('Invalid administrative geometry')
        admins[str(feature['osm_relation_id'])] = {'name':str(feature['name']),'geometry':geometry}
    boundary = json.loads((Path(work)/'config/boundary_project.json').read_text())
    hanoi = read_polygon(input_path(work,boundary['hanoi_source']['path']),crs,context)
    ref = policy['legal_reference']
    reference = read_polygon(input_path(work,ref['geometry_path']),crs,context,ref['geometry_layer']).intersection(hanoi)
    width = options['boundary_band_m']
    band = reference.buffer(width,12).difference(reference.buffer(-width,12)).intersection(hanoi)
    return options, policy, context, crs, admins, hanoi, reference, band


def prepare_inputs(work=WORK):
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsRectangle
    work = Path(work)
    options,policy,context,crs,admins,hanoi,reference,band = _load_geometries(work)
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(crs),QgsCoordinateReferenceSystem('EPSG:4326'),context)
    tasks = []
    for admin_id, row in sorted(admins.items()):
        if not row['geometry'].boundingBox().intersects(band.boundingBox()) or row['geometry'].intersection(band).area() <= 100:
            continue
        polygon = row['geometry'].simplify(5)
        if not polygon.isGeosValid():
            polygon = QgsGeometry(row['geometry'])
        parts = polygon.asMultiPolygon() if polygon.isMultipart() else [polygon.asPolygon()]
        for index, rings in enumerate(parts):
            part = QgsGeometry.fromPolygonXY(rings)
            if part.area() < 100:
                continue
            area = part.area()
            part.transform(transform)
            body = {'geojson':json.loads(part.asJson()),'year':2025,'resolution':'1km'}
            tasks.append({'task_key':admin_id+'_'+str(index),'admin_id':admin_id,'name':row['name'],
                          'area_m2':area,'body':body})
    project = json.loads((work/'data/hanoi_tiles/tile_project.json').read_text())
    with (work/'data/hanoi_tiles/tiles.csv').open(encoding='utf-8-sig',newline='') as stream:
        tiles = [t for t in csv.DictReader(stream) if t['status']!='split']
    # Reuse the existing tile envelopes, snapshot and endpoint, with new activity predicates.
    south=min(float(t['south']) for t in tiles);west=min(float(t['west']) for t in tiles)
    north=max(float(t['north']) for t in tiles);east=max(float(t['east']) for t in tiles)
    bbox=','.join(str(v) for v in [south,west,north,east])
    predicates = {'trade_services':['[shop]','[amenity~"^(marketplace|bank|restaurant|cafe|fast_food)$"]'],
                  'offices':['[office]'], 'education':['[amenity~"^(school|kindergarten|college|university)$"]']}
    queries=[]
    for name,filters in predicates.items():
        query=f'[out:json][timeout:180][date:"{project["snapshot_utc"]}"];\n('+''.join('nwr'+f+'('+bbox+');' for f in filters)+');\nout meta center;\nout count;\n'
        queries.append({'name':name,'query':query})
    prepared={'prepared_at':now(),'snapshot_utc':project['snapshot_utc'],'endpoint':project['endpoint'],
              'population_tasks':tasks,'population_geometry_simplification_m':5,'activity_queries':queries,
              'boundary_admin_sha256':file_hash(input_path(work,options['boundary_admin_path'])),
              'policy_sha256':file_hash(work/'config/sampling_boundary_policy.json'),
              'config_sha256':file_hash(work/'config/sampling_2030.json')}
    atomic_json(work/'data/interim/sampling/requests.json',prepared)
    event('sampling','Đã chuẩn bị đầu vào HTTP',population_tasks=len(tasks),activity_queries=len(queries))
    return {'population_tasks':len(tasks),'activity_queries':len(queries),'boundary_band_m':options['boundary_band_m']}


def _engine(geometry):
    from qgis.core import QgsGeometry
    engine=QgsGeometry.createGeometryEngine(geometry.constGet());engine.prepareGeometry()
    return engine


def _dimension_only(geometry,kind):
    """GEOS intersections can contain polygon/line/point collections; keep the requested dimension."""
    from qgis.core import QgsGeometry,QgsWkbTypes
    empty='MULTIPOLYGON EMPTY' if kind==QgsWkbTypes.PolygonGeometry else 'MULTILINESTRING EMPTY'
    def collect(item):
        if item.isNull() or item.isEmpty():return []
        if item.type()==kind:return [QgsGeometry(item)]
        if item.wkbType() in {QgsWkbTypes.GeometryCollection,QgsWkbTypes.GeometryCollectionZ,QgsWkbTypes.GeometryCollectionM,QgsWkbTypes.GeometryCollectionZM}:
            return [part for child in item.asGeometryCollection() for part in collect(child)]
        return []
    pieces=collect(geometry)
    result=QgsGeometry.unaryUnion(pieces) if pieces else QgsGeometry.fromWkt(empty)
    result.convertToMultiType()
    return result


def _polygon(geometry):
    from qgis.core import QgsWkbTypes
    return _dimension_only(geometry,QgsWkbTypes.PolygonGeometry)


def _line(geometry):
    from qgis.core import QgsWkbTypes
    return _dimension_only(geometry,QgsWkbTypes.LineGeometry)


def _nearest_stratum(geometry, codes, base):
    # Spatial overlap, proximity, then centroid/code provide deterministic regional affinity.
    def rank(code):
        shared=geometry.intersection(base[code]).area()
        distance=geometry.distance(base[code])
        return (-shared,distance,geometry.centroid().distance(base[code].centroid()),code)
    return min(codes,key=rank)


def build_scope(work, directory, loaded):
    from .gis import sink, QgsWkbTypes, check_layers
    from .admin_boundaries import normalized_name
    from .routing import classify, midrank
    from qgis.core import QgsGeometry, QgsPointXY, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsVectorLayer
    options,policy,context,crs,admins,hanoi,reference,band=loaded
    population=json.loads(input_path(work,options['population_input']).read_text())
    activity=json.loads(input_path(work,options['activity_input']).read_text())
    if activity['snapshot_utc']!=options['source_snapshot_utc']:
        raise ValueError('Activity input belongs to a different OSM snapshot')
    if population['year']!=2025:
        raise ValueError('Population input year differs from configured model year')
    tasks=population['expected_tasks'];expected=Counter(t['admin_id'] for t in tasks)
    counts=Counter(p['admin_id'] for p in population['parts'])
    pops=defaultdict(float);areas=defaultdict(float)
    for part in population['parts']:
        pops[part['admin_id']]+=part['population'];areas[part['admin_id']]+=part['area_m2']
    density={i:pops[i]/areas[i]*1e6 for i in pops if counts[i]==expected[i] and areas[i]>0}
    pop_rank=midrank(list(density.values())) if density else {}
    transform=QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'),QgsCoordinateReferenceSystem(crs),context)
    features=[]
    seen=set()
    for item in activity['features']:
        key=(item['osm_key'],item['category'])
        if key in seen:continue
        seen.add(key)
        point=QgsGeometry.fromPointXY(transform.transform(QgsPointXY(item['lon'],item['lat'])))
        if hanoi.intersects(point):features.append((item,point))
    units=[];claimed=QgsGeometry.fromWkt('MULTIPOLYGON EMPTY')
    outside_reference=hanoi.difference(reference)
    for admin_id,admin in sorted(admins.items()):
        full=_polygon(admin['geometry'].intersection(band))
        if not claimed.isEmpty():full=_polygon(full.difference(claimed))
        if full.isEmpty():continue
        claimed=QgsGeometry.unaryUnion([claimed,full])
        for group,side in [('inside',reference),('outside',outside_reference)]:
            geom=_polygon(full.intersection(side))
            if geom.area()<=100:continue
            engine=_engine(geom);categories=Counter()
            for item,point in features:
                if engine.intersects(point.constGet()):categories[item['category']]+=1
            area_km2=geom.area()/1e6
            units.append({'unit_id':admin_id+'/'+group,'admin_id':admin_id,'name':admin['name'],
                          'reference_group':group,'population_density':density.get(admin_id),
                          'population_year':2025,'population_source':'WorldPop R2025A 2025 1km (modeled)',
                          'activity_density':sum(categories.values())/area_km2 if activity['complete'] else None,
                          'trade_services':categories['trade_services'],'offices':categories['offices'],'education':categories['education'],
                          'area_m2':geom.area(),'geometry':geom})
    activity_rank=midrank([u['activity_density'] for u in units if u['activity_density'] is not None])
    sampling=QgsGeometry(reference)
    for unit in units:
        p=pop_rank.get(unit['population_density']);a=activity_rank.get(unit['activity_density'])
        group,score,reason=classify(p,a,options['classification_weights'],unit['reference_group'],options['score_threshold'])
        unit.update(sampling_group=group,score=score,population_percentile=p,activity_percentile=a,
                    reason=reason,changed=group!=unit['reference_group'])
        if unit['changed']:
            sampling=_polygon(QgsGeometry.unaryUnion([sampling,unit['geometry']]) if group=='inside' else sampling.difference(unit['geometry']))
    sampling=_polygon(sampling.intersection(hanoi));outside=_polygon(hanoi.difference(sampling))
    if not sampling.isGeosValid() or not outside.isGeosValid():raise ValueError('Invalid derived sampling polygon')
    added=_polygon(sampling.difference(reference));removed=_polygon(reference.difference(sampling))
    beyond=QgsGeometry.unaryUnion([added,removed]).difference(band).area()
    if beyond>0.01:raise ValueError('Adjustment extends outside declared boundary band')
    rules=json.loads((Path(work)/'config/boundary_automation.json').read_text())
    by_name={normalized_name(v['name']):i for i,v in admins.items()}
    assignment={};base={}
    for row in rules['strata']:
        code=row['stratum_id'];ids=[by_name[normalized_name(n)] for n in row['names']]
        for i in ids:assignment[i]=code
        base[code]=QgsGeometry.unaryUnion([admins[i]['geometry'] for i in ids])
    explicit=[]
    for name,code in options['remaining_admin_assignments'].items():
        i=by_name[normalized_name(name)]
        if i in assignment:raise ValueError('Remaining unit already assigned')
        assignment[i]=code
        explicit.append({'admin_id':i,'name':admins[i]['name'],'stratum_id':code,
                         'reason':'explicit research regional assignment; then clipped to frozen sampling domain'})
    strata=defaultdict(list);trace=[];claimed=QgsGeometry.fromWkt('MULTIPOLYGON EMPTY')
    for admin_id,admin in sorted(admins.items()):
        full=_polygon(admin['geometry'].intersection(hanoi))
        if not claimed.isEmpty():full=_polygon(full.difference(claimed))
        if full.isEmpty():continue
        claimed=QgsGeometry.unaryUnion([claimed,full])
        old=assignment[admin_id]
        for group,scope,prefix in [('inside',sampling,'V'),('outside',outside,'N')]:
            geom=_polygon(full.intersection(scope))
            if geom.area()<=0.00001:continue
            code=old if old.startswith(prefix) else _nearest_stratum(geom,[c for c in base if c.startswith(prefix)],base)
            strata[code].append(geom)
            trace.append({'admin_id':admin_id,'name':admin['name'],'reference_stratum':old,'sampling_stratum':code,
                          'group':group,'area_m2':geom.area(),'reason':'original regional assignment' if old==code else 'sampling domain changed; spatial affinity to matching V/N stratum'})
    residual=_polygon(hanoi.difference(claimed))
    if residual.area()>1000:raise ValueError('Administrative gap is too large for declared technical gap repair')
    for group,scope,prefix in [('inside',sampling,'V'),('outside',outside,'N')]:
        geometry=_polygon(residual.intersection(scope))
        if geometry.area()<=0.00001:continue
        pieces=geometry.asGeometryCollection() if geometry.isMultipart() else [geometry]
        for piece in pieces:
            code=_nearest_stratum(piece,[c for c in base if c.startswith(prefix)],base)
            strata[code].append(piece)
            trace.append({'admin_id':'technical_gap','name':'OSM administrative residual','reference_stratum':None,
                          'sampling_stratum':code,'group':group,'area_m2':piece.area(),'reason':'derived research gap repair <=1000 m2; raw geometry unchanged'})
    result={c:_polygon(QgsGeometry.unaryUnion(g)) for c,g in strata.items()}
    coverage=QgsGeometry.unaryUnion(list(result.values()))
    gap=hanoi.difference(coverage).area()
    overlap=sum(g.area() for g in result.values())-coverage.area()
    if gap>0.1 or overlap>0.1 or len(result)!=15:raise ValueError('Sampling strata do not partition Hanoi: '+str((gap,overlap,len(result))))
    building=directory/'.sampling_zones.building.gpkg';building.unlink(missing_ok=True)
    columns=[('zone_id','str'),('status','str'),('area_m2','float')]
    with sink(building,'reference_lez_2030',columns,QgsWkbTypes.MultiPolygon,crs,context) as out:
        geometry=QgsGeometry(reference);geometry.convertToMultiType()
        out.add({'zone_id':'LEZ2030_reference','status':policy['legal_reference']['geometry_status'],'area_m2':geometry.area()},geometry)
    for name,geometry in [('hanoi',hanoi),('sampling_inside',sampling),('sampling_outside',outside),('adjustment_band',band),('added_inside',added),('removed_inside',removed)]:
        with sink(building,name,columns,QgsWkbTypes.MultiPolygon,crs,context) as out:
            if not geometry.isEmpty():
                geometry=QgsGeometry(geometry);geometry.convertToMultiType()
                out.add({'zone_id':name,'status':'provisional_research_scope','area_m2':geometry.area()},geometry)
    with sink(building,'strata',columns,QgsWkbTypes.MultiPolygon,crs,context) as out:
        for code,geometry in sorted(result.items()):
            geometry.convertToMultiType();out.add({'zone_id':code,'status':'research_2030_sampling','area_m2':geometry.area()},geometry)
    fields=[(k,'str' if k in ['unit_id','admin_id','name','reference_group','sampling_group','reason','population_source'] else 'bool' if k=='changed' else 'float') for k in units[0] if k!='geometry']
    with sink(building,'boundary_units',fields,QgsWkbTypes.MultiPolygon,crs,context) as out:
        for unit in units:
            geometry=QgsGeometry(unit['geometry']);geometry.convertToMultiType();out.add(unit,geometry)
    building.replace(directory/'sampling_zones.gpkg')
    check_layers(directory/'sampling_zones.gpkg',{'strata':15,'boundary_units':len(units),'sampling_inside':1,'sampling_outside':1},crs)
    serial=[{k:v for k,v in u.items() if k!='geometry'} for u in units]
    write_csv(directory/'boundary_decisions.csv',serial,list(serial[0]))
    write_csv(directory/'strata_assignment_trace.csv',trace,list(trace[0]))
    write_csv(directory/'remaining_admin_assignments.csv',explicit,list(explicit[0]))
    report={'scope':'LEZ2030 research sampling','reference_status':policy['legal_reference']['geometry_status'],
            'official_gis_verified':False,'research_scope_active':True,'boundary_band_m':options['boundary_band_m'],
            'population_year':2025,'population_is_modeled':True,'population_admin_units_with_data':len(density),
            'activity_complete':activity['complete'],'activity_features_in_hanoi':len(features),
            'boundary_units':len(units),'adjusted_units':sum(u['changed'] for u in units),
            'pending_evidence_units':sum(u['reason'].startswith('pending') for u in units),
            'reference_area_km2':reference.area()/1e6,'sampling_inside_area_km2':sampling.area()/1e6,
            'added_inside_area_km2':added.area()/1e6,'removed_inside_area_km2':removed.area()/1e6,
            'adjustment_outside_band_m2':beyond,'strata':15,'previous_unassigned_admin_units_assigned':len(explicit),
            'technical_gap_repaired_m2':residual.area(),'strata_gap_m2':gap,'strata_overlap_m2':overlap,
            'limitations':['OSM 36-unit union is a technical proxy for statutory geography, not verified government GIS.',
                           'Population is modeled at 1km; density is aggregated to admin units and reused for their band parts.',
                           'OSM feature counts are mapping-dependent activity proxies; zero is not proof of absent economic activity.',
                           'Band, weights, threshold, regional assignment and route lengths remain research parameters for sensitivity checks.']}
    atomic_json(directory/'boundary_report.json',report)
    return sampling,outside,reference,result,report


def overlay_network(work,directory,loaded,scope):
    from .gis import sink,QgsWkbTypes
    from .graph import MotorcycleNetwork
    from qgis.core import QgsGeometry,QgsVectorLayer
    options,policy,context,crs,*_=loaded
    sampling,outside,reference,strata,_=scope
    network=MotorcycleNetwork.load(input_path(work,options['graph_path']))
    if network.data.get('snapshot_utc')!=options['source_snapshot_utc']:
        raise ValueError('Routing graph belongs to a different OSM snapshot')
    eligible={a['part_id'] for a in network.arcs.values()}
    graph_lengths={a['part_id']:a['length_m'] for a in network.arcs.values()}
    layers=QgsVectorLayer(str(input_path(work,options['network_path']))+'|layername=scope_parts','parts','ogr')
    if not layers.isValid():raise ValueError('Cannot load network scope parts')
    rc_by_part={a['part_id']:a['rc'] for a in network.arcs.values()}
    engines={c:_engine(g) for c,g in strata.items()};inside_engine=_engine(sampling);ref_engine=_engine(reference)
    geometries={};part_meta={};matrix=Counter();group_total=Counter();total=0.0;max_error=0.0;piece_count=0
    building=directory/'.network_parts.building.gpkg';building.unlink(missing_ok=True)
    fields=[('part_id','str'),('segment_id','str'),('stratum_id','str'),('group','str'),('rc','str'),('length_m','float')]
    with sink(building,'network_parts',fields,QgsWkbTypes.MultiLineString,crs,context) as output:
        for index,feature in enumerate(layers.getFeatures()):
            pid=str(feature['part_id'])
            if pid not in eligible:continue
            geometry=QgsGeometry(feature.geometry());length=geometry.length();rc=rc_by_part[pid]
            if abs(length-float(feature['length_m']))>0.01 or abs(length-graph_lengths[pid])>0.01:
                raise ValueError('Graph/source part length disagrees with geometry')
            total+=length;geometries[pid]=geometry
            if inside_engine.contains(geometry.constGet()):inside_length=length
            elif inside_engine.intersects(geometry.constGet()):inside_length=geometry.intersection(sampling).length()
            else:inside_length=0.0
            if ref_engine.contains(geometry.constGet()):reference_length=length
            elif ref_engine.intersects(geometry.constGet()):reference_length=geometry.intersection(reference).length()
            else:reference_length=0.0
            pure='inside' if abs(inside_length-length)<=1e-5 else 'outside' if inside_length<=1e-5 else None
            cells=[];remaining=QgsGeometry(geometry);assigned=0.0
            for code,region in sorted(strata.items()):
                if remaining.isEmpty():break
                if not geometry.boundingBox().intersects(region.boundingBox()):continue
                engine=engines[code]
                if not engine.intersects(remaining.constGet()):continue
                piece=_line(QgsGeometry(remaining) if engine.contains(remaining.constGet()) else remaining.intersection(region))
                size=piece.length()
                if size<=1e-7:continue
                piece.convertToMultiType()
                # Intersections touching only a point add no length; shared line boundaries are assigned once.
                if piece.isEmpty():continue
                size=piece.length();group='inside' if code.startswith('V') else 'outside'
                output.add({'part_id':pid,'segment_id':str(feature['segment_id']),'stratum_id':code,'group':group,'rc':rc,'length_m':size},piece)
                assigned+=size;piece_count+=1;cells.append((code,rc,size));group_total[group]+=size
                # Keep all physical lengths for diagnostics; rc_composition alone
                # decides whether a class belongs to the statistical denominator.
                matrix[(code,rc)]+=size
                remaining=_line(remaining.difference(piece))
            error=abs(assigned-length);max_error=max(error,max_error)
            if error>0.02:raise ValueError('Overlay lost or duplicated length: '+pid+' '+str(error))
            part_meta[pid]={'pure_group':pure,'cells':cells,'reference_inside_m':reference_length,'length_m':length}
            if index%50000==0:event('overlay','Đang cắt mạng theo tầng nghiên cứu',source_index=index,eligible_parts=len(part_meta))
    building.replace(directory/'network_parts.gpkg')
    if len(part_meta)!=len(eligible):raise ValueError('Graph refers to absent physical parts')
    rows,_,_,composition=rc_composition(matrix)
    rc_total=composition['network_rc_m']
    write_csv(directory/'network_matrix.csv',rows,list(rows[0]))
    report={'physical_routable_parts':len(part_meta),'normalized_pieces':piece_count,'network_length_m':total,
            'rc1_rc4_network_length_m':rc_total,'connector_network_length_m':composition['network_connector_m'],
            'rc1_rc4_physical_routable_parts':sum(rc_by_part[p] in RC_CLASSES for p in part_meta),
            'connector_physical_routable_parts':sum(rc_by_part[p] not in RC_CLASSES for p in part_meta),
            'domain_lengths_m':dict(group_total),'rc1_rc4_domain_lengths_m':composition['network_rc_domain_m'],
            'rc_network_fraction_sum':composition['network_fraction_sum'],'max_part_length_error_m':max_error,
            'aggregate_length_error_m':abs(sum(group_total.values())-total),'statistical_cells':len(rows),
            'cross_sampling_boundary_parts_excluded_from_candidate_routing':sum(not p['pure_group'] for p in part_meta.values()),
            'length_denominator':'unique physical routable OSM parts in Hanoi, excluding review/excluded arcs; two directions counted once',
            'composition_denominator':'only RC1-RC4 physical parts; connector lengths excluded from global and domain fractions',
            'status':'provisional_access_network_not_field_verified'}
    atomic_json(directory/'overlay_report.json',report)
    coordinates={n['node_id']:(n['x'],n['y']) for n in network.data['nodes']}
    return network,part_meta,geometries,coordinates,matrix,report


def build_candidates(work,directory,loaded,scope,overlay):
    from .gis import sink,QgsWkbTypes,check_layers
    from .routing import generate
    from qgis.core import QgsGeometry,QgsPointXY
    options,policy,context,crs,*_=loaded
    network,meta,geometry,coords,matrix,overlay_report=overlay
    def progress(route_id,count,accepted,reasons):event('routes','Đã xét ứng viên',route_id=route_id,created=count,accepted=accepted,reasons=reasons)
    routes,failed,pairs=generate(network,meta,coords,options['targets'],options['route_design'],progress)
    building=directory/'.candidate_routes.building.gpkg';building.unlink(missing_ok=True)
    fields=[('route_id','str'),('group','str'),('stratum_id','str'),('rc_target','str'),('length_m','float'),('target_cell_fraction','float'),('reference_inside_length_fraction','float'),('status','str')]
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
    _,coverage,connectors,composition=rc_composition(matrix,sample,unique_sample)
    denom=composition['network_rc_m'];sample_denom=composition['sample_rc_m']
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
    D_by_domain=composition['D_by_domain']
    counts=Counter(r['group'] for r in routes)
    report={'created_routes':len(routes),'inside':counts['inside'],'outside':counts['outside'],'requested_inside':20,'requested_outside':40,
            'geometry_quota_achieved':counts['inside']==20 and counts['outside']==40,'verified_measurement_quota_achieved':False,
            'all_walks_direction_continuity_turn_checked':True,'all_routes_pure_in_frozen_sampling_scope':True,
            'all_targets_cell_fraction_at_least':options['route_design']['target_cell_min_fraction'],
            'duplicate_corridor_sets':len(routes)-len({frozenset(r['part_ids']) for r in routes}),
            'overlap_pairs_to_review':len(pairs),'failed_targets':failed,'pending_field_check_routes':len(routes),
            'D_combined':composition['D_combined'],
            'D_by_domain':D_by_domain,'overlap_pairs_calculated':len(overlaps),
            'network_denominator_m':denom,'sample_denominator_m':sample_denom,
            'all_network_length_m':composition['network_all_m'],'all_sample_traversed_length_m':composition['sample_all_m'],
            'connector_network_length_m':composition['network_connector_m'],'connector_sample_traversed_length_m':composition['sample_connector_m'],
            'network_rc_domain_lengths_m':composition['network_rc_domain_m'],'sample_rc_domain_lengths_m':composition['sample_rc_domain_m'],
            'network_fraction_sum':composition['network_fraction_sum'],'sample_fraction_sum':composition['sample_fraction_sum'],
            'statistical_cells':len(coverage),'composition_classes':list(RC_CLASSES),'connectors_in_composition':False,
            'sample_composition_counts_shared_parts_for_each_traversal':True,'unique_coverage_counts_physical_parts_once':True,
            'route_design':options['route_design'],'final_30_selection_performed':False}
    atomic_json(directory/'candidate_report.json',report)
    return report


def execute_legacy(work=WORK,force=False):
    work=Path(work);options,policy=config(work);started=now();timer=time.monotonic()
    boundary=json.loads((work/'config/boundary_project.json').read_text())
    required=[work/'config/sampling_2030.json',work/'config/sampling_boundary_policy.json',work/'config/boundary_automation.json',
              work/'config/boundary_project.json',input_path(work,boundary['hanoi_source']['path']),
              input_path(work,policy['legal_reference']['geometry_path']),input_path(work,policy['legal_reference']['source_file']),
              input_path(work,options['boundary_admin_path']),input_path(work,options['network_path']),
              input_path(work,options['graph_path']),input_path(work,options['population_input']),input_path(work,options['activity_input'])]
    fingerprint=digest({'inputs':{relative(p,work):file_hash(p) for p in required},
                        'code':code_hash(['common.py','gis.py','graph.py','routing.py','sampling_2030.py'])})
    directory=work/'data/processed/sampling_2030'/fingerprint[:20]
    with processing_lock(work):
        cached=None if force else cached_manifest(directory,fingerprint)
        if cached:
            result=dict(cached['report'],cache_hit=True)
        else:
            directory.mkdir(parents=True,exist_ok=True)
            loaded=_load_geometries(work)
            event('sampling','Đang chấm điểm và cố định phạm vi lấy mẫu')
            scope=build_scope(work,directory,loaded)
            event('sampling','Đang chuẩn hóa mạng theo phạm vi 2030')
            overlay=overlay_network(work,directory,loaded,scope)
            candidate=build_candidates(work,directory,loaded,scope,overlay)
            result={'started_at':started,'status':'geometry_quota_achieved_pending_validation' if candidate['geometry_quota_achieved'] else 'candidate_quota_incomplete',
                    'scope':'user_selected_LEZ2030','boundary':scope[-1],'overlay':overlay[-1],'candidates':candidate,
                    'raw_osm_modified':False,'cache_hit':False,'finished_at':now(),'elapsed_seconds':time.monotonic()-timer,
                    'paths':{'directory':relative(directory,work),'zones':relative(directory/'sampling_zones.gpkg',work),
                             'parts':relative(directory/'network_parts.gpkg',work),'routes':relative(directory/'candidate_routes.gpkg',work),
                             'route_csv':relative(directory/'candidate_routes.csv',work),'network_matrix':relative(directory/'network_matrix.csv',work),
                             'sample_matrix':relative(directory/'sample_matrix.csv',work),'connector_summary':relative(directory/'connector_summary.csv',work),
                             'boundary_decisions':relative(directory/'boundary_decisions.csv',work)}}
            atomic_json(directory/'report.json',result)
            outputs=[p.name for p in directory.iterdir() if p.is_file() and not p.name.startswith('.') and p.name!='manifest.json']
            commit_manifest(directory,fingerprint,result,outputs)
        for name,target in [('sampling_2030.gpkg','sampling_zones.gpkg'),('network_parts_2030.gpkg','network_parts.gpkg'),('candidate_routes_2030.gpkg','candidate_routes.gpkg')]:
            publish_link(work,name,directory/target)
        atomic_json(work/'reports/sampling/latest_sampling_2030.json',result)
    return result


def execute(work=WORK, force=False):
    """Compatibility entry point: new projects use the current ABC design."""
    if (Path(work)/'config/sampling_abc.json').is_file():
        from .sampling_abc import execute as build_abc
        return build_abc(work, force)
    return execute_legacy(work, force)


def status(work=WORK):
    if (Path(work)/'config/sampling_abc.json').is_file():
        from .sampling_abc import status as abc_status
        return abc_status(work)
    path=Path(work)/'reports/sampling/latest_sampling_2030.json'
    return json.loads(path.read_text()) if path.exists() else {'status':'not_run'}


def run_normalization(work=WORK,fetch=False,force=False,progress=print):
    """Run strata/overlay only, separately from generating or selecting routes."""
    from .normalization_2030 import run_normalization as normalize
    return normalize(work,fetch=fetch,force=force,progress=progress)


def normalization_status(work=WORK):
    from .normalization_2030 import normalization_status as read_status
    return read_status(work)


def preflight_sampling(work=WORK,progress=print):
    """Check inputs and geometry in the registered runtime; sends no HTTP request."""
    work=Path(work).resolve();options,policy=config(work)
    from .pipeline import kernel_spec
    spec=kernel_spec()
    for key in ['boundary_admin_path','network_path','graph_path','draft_zones_path']:
        if not input_path(work,options[key]).is_file():raise ValueError('Missing input '+options[key])
    prepared=_worker(work,'prepare',progress=progress)
    project=json.loads((work/'data/hanoi_tiles/tile_project.json').read_text())
    if project['snapshot_utc']!=options['source_snapshot_utc']:raise ValueError('Network/source snapshot differs from sampling config')
    return dict(prepared,scope_selection='2030',snapshot_utc=project['snapshot_utc'],endpoint=project['endpoint'],
                qgis_runtime=spec['argv'][0],network_calls=0,raw_osm_modified=False,
                reference_gis_verified=False,research_scope_only=True)


def _worker(work,command,force=False,progress=print):
    from .pipeline import kernel_spec
    spec=kernel_spec();env=os.environ.copy();env.update(spec.get('env',{}));env['PYTHONUNBUFFERED']='1'
    args=[spec['argv'][0],str(Path(__file__).resolve()),command,'--worker','--work',str(work)]
    if force:args.append('--force')
    process=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    recent=deque(maxlen=20);result=None
    try:
        for line in process.stdout:
            recent.append(line.strip())
            try:message=json.loads(line)
            except ValueError:
                if progress:progress(line.strip())
                continue
            if message.get('event')=='result':result=message['result']
            elif progress:progress(message)
        if process.wait() or result is None:raise RuntimeError('Sampling worker failed:\n'+'\n'.join(recent))
        return result
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
        raise


def run_sampling(work=WORK,fetch=True,force=False,progress=print):
    work=Path(work).resolve()
    if (work/'config/sampling_abc.json').is_file():
        from .sampling_abc import run_sampling as build_abc
        return build_abc(work,force=force,progress=progress)
    config(work)
    try:
        if fetch:
            _worker(work,'prepare',progress=progress)
            from .sampling_data import fetch_inputs
            fetch_inputs(work,progress)
        return _worker(work,'build',force,progress)
    except KeyboardInterrupt:
        if progress:progress('Đã dừng; dữ liệu HTTP và manifest hoàn chỉnh được giữ để tiếp tục.')
        return status(work)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','fetch','build','run','status'])
    parser.add_argument('--work',default=str(WORK));parser.add_argument('--worker',action='store_true');parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    if args.worker:result=prepare_inputs(args.work) if args.command=='prepare' else execute(args.work,args.force)
    elif args.command=='status':result=status(args.work)
    elif args.command in {'prepare','build'}:result=_worker(args.work,args.command,args.force)
    elif args.command=='fetch':
        from .sampling_data import fetch_inputs
        result=fetch_inputs(args.work)
    else:result=run_sampling(args.work,True,args.force)
    print(json.dumps({'event':'result','result':result},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
