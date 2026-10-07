"""Native, read-only source gates and the full variable layer for all 60 routes.

Controller API:
    checks = verify_gates(work, parent_sampling_report, data)
    export = export_variables(work, parent_sampling_report, data, output_directory)

`data` is the output of selection_metrics.load_data. These calls need no qgis
import in the calling notebook. Legal permission, safe stops and field C6 remain
unknown; only identifiable source-OSM conflicts and GIS geometry are checked.
"""
from __future__ import annotations

if __package__ in (None, ''):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if '--payload' in sys.argv:
        import json
        payload_file = Path(sys.argv[sys.argv.index('--payload') + 1])
        sys.path.insert(0, str(Path(json.loads(payload_file.read_text())['work']) / 'scripts'))
    __package__ = 'lez'

import argparse
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

from .common import WORK, atomic_json, file_hash, input_path, now, relative, write_csv

FEATURE_NAMES = ['P_RC1', 'P_RC2', 'P_RC3', 'P_RC4', 'lanes', 'maxspeed',
                 'junctions_per_km', 'signals_per_km', 'P_oneway']


def _payload(work, report, data):
    X = data.get('X')
    return {'work': str(Path(work).resolve()), 'parent_report': report,
            'walks': data['walks'], 'features': data['features'],
            'feature_names': data.get('feature_names', []),
            'X': X.tolist() if hasattr(X, 'tolist') else X,
            'normalization': data.get('normalization', {})}


def _native_call(command, payload, directory=None):
    from .pipeline import kernel_spec
    spec = kernel_spec()
    env = os.environ.copy(); env.update(spec.get('env', {}))
    with tempfile.TemporaryDirectory(prefix='lez-gates-call-') as folder:
        path = Path(folder) / 'payload.json'
        atomic_json(path, payload)
        args = [spec['argv'][0], str(Path(__file__).resolve()), command, '--payload', str(path)]
        if directory is not None:
            args += ['--directory', str(Path(directory).resolve())]
        completed = subprocess.run(args, env=env, capture_output=True, text=True)
        if completed.returncode:
            raise RuntimeError('Mandatory GIS source checks failed: ' + completed.stderr[-4000:])
        try:
            return json.loads(completed.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise RuntimeError('Native source check returned no valid JSON: ' + completed.stdout[-1000:]) from exc


def verify_gates(work, report, data):
    """Fail before selecting when any actual source-OSM/G2/G3 gate fails."""
    result = _native_call('verify', _payload(work, report, data))
    for row in data['features']:
        evidence = result['routes'][row['route_id']]
        row.update(G1_OSM=evidence['G1_OSM'], G2=evidence['G2'], G3=evidence['G3'],
                   pre_survey_admissible=evidence['pre_survey_admissible'])
    return result


def export_variables(work, report, data, directory):
    """Recheck inputs and write route_variables.gpkg + gate_checks.json."""
    return _native_call('export', _payload(work, report, data), directory)


def _native_checks(payload):
    from .graph import MotorcycleNetwork
    from qgis.core import QgsFeatureRequest, QgsGeometry, QgsVectorLayer, QgsWkbTypes
    work = Path(payload['work'])
    parent = input_path(work, payload['parent_report']['paths']['directory'])
    options = json.loads((work / 'config/selection_30.json').read_text())
    sampling_path = input_path(work, options.get('sampling_config', 'config/sampling_2030.json'))
    sampling = json.loads(sampling_path.read_text())
    project = json.loads((work / 'data/hanoi_tiles/tile_project.json').read_text())
    crs = project['metric_crs']
    graph_path = input_path(work, sampling['graph_path'])
    network_path = input_path(work, sampling['network_path'])
    graph = MotorcycleNetwork.load(graph_path)
    if graph.data.get('snapshot_utc') != sampling['source_snapshot_utc'] or project['snapshot_utc'] != sampling['source_snapshot_utc']:
        raise ValueError('Source graph/config/project snapshot mismatch')
    walks = payload['walks']
    identifiers = [r['route_id'] for r in walks]
    if len(walks) != 60 or len(set(identifiers)) != 60:
        raise ValueError('Expected 60 unique source routes')
    counts = {g: sum(r['group'] == g for r in walks) for g in ['inside', 'outside']}
    zone_counts = {zone: sum(r.get('sampling_zone') == zone for r in walks) for zone in options['pool_quota']}
    if zone_counts != options['pool_quota'] or any(r.get('sampling_zone') != r['stratum_id'] or r['group'] not in ('inside', 'outside') for r in walks):
        raise ValueError('Source pool must contain 20 A / 20 B / 20 C with independent LEZ membership')
    source_walks = {r['route_id']: r for r in json.loads((parent / 'candidate_walks.json').read_text())}
    wanted_parts = {pid for r in walks for pid in r['part_ids']}
    wanted_arcs = {aid for r in walks for aid in r['arc_ids']}
    with sqlite3.connect(network_path.as_uri() + '?mode=ro', uri=True) as db:
        parts = {r[0]: r[1:] for r in db.execute('SELECT part_id,length_m,from_node,to_node FROM scope_parts') if r[0] in wanted_parts}
        arcs = {r[0]: r[1:] for r in db.execute('SELECT arc_id,routable,access_status,part_id,from_node,to_node,length_m,direction FROM arcs') if r[0] in wanted_arcs}
    if set(parts) != wanted_parts or set(arcs) != wanted_arcs:
        raise ValueError('Route source parts/arcs are absent from source network')
    bad_access = [a for a, row in arcs.items() if row[:2] != (1, 'provisionally_allowed')]
    if bad_access:
        raise ValueError('G1_OSM unresolved/excluded/non-routable arcs: ' + ','.join(bad_access[:8]))
    source_part_layer = QgsVectorLayer(str(network_path) + '|layername=scope_parts', 'source_parts', 'ogr')
    if not source_part_layer.isValid() or source_part_layer.crs().authid() != crs:
        raise ValueError('Invalid source part geometry layer/CRS')
    expression = '"part_id" IN (' + ','.join("'" + p.replace("'", "''") + "'" for p in sorted(wanted_parts)) + ')'
    source_part_shapes = {str(f['part_id']): QgsGeometry(f.geometry())
                          for f in source_part_layer.getFeatures(QgsFeatureRequest().setFilterExpression(expression))}
    if set(source_part_shapes) != wanted_parts:
        raise ValueError('Source physical part geometries are absent')
    route_layer = QgsVectorLayer(str(parent / 'candidate_routes.gpkg') + '|layername=candidate_routes', 'routes', 'ogr')
    if not route_layer.isValid() or route_layer.crs().authid() != crs:
        raise ValueError('Invalid route source layer or CRS')
    shapes = {str(f['route_id']): QgsGeometry(f.geometry()) for f in route_layer.getFeatures()}
    if set(shapes) != set(identifiers):
        raise ValueError('Walk/geometry route IDs do not agree')
    scopes = {}
    for group, layer_name in [('inside', 'sampling_inside'), ('outside', 'sampling_outside')]:
        src = QgsVectorLayer(str(parent / 'sampling_zones.gpkg') + '|layername=' + layer_name, group, 'ogr')
        if not src.isValid() or src.crs().authid() != crs:
            raise ValueError('Invalid sampling scope layer/CRS')
        polygons = [QgsGeometry(f.geometry()) for f in src.getFeatures()]
        if not polygons or any(g.type() != QgsWkbTypes.PolygonGeometry or not g.isGeosValid() or g.isEmpty() for g in polygons):
            raise ValueError('Invalid/non-polygon sampling scope')
        scopes[group] = QgsGeometry.unaryUnion(polygons).buffer(0.001, 12)
    abc_layer = QgsVectorLayer(str(parent / 'sampling_zones.gpkg') + '|layername=abc_zones', 'ABC', 'ogr')
    if not abc_layer.isValid() or abc_layer.crs().authid() != crs:
        raise ValueError('Invalid ABC sampling polygons/CRS')
    abc_parts = {}
    for feature in abc_layer.getFeatures():
        zone = str(feature['sampling_zone'])
        shape = QgsGeometry(feature.geometry())
        if zone not in options['pool_quota'] or shape.isEmpty() or not shape.isGeosValid() or shape.type() != QgsWkbTypes.PolygonGeometry:
            raise ValueError('Invalid/non-polygon ABC sampling zone')
        abc_parts.setdefault(zone, []).append(shape)
    if set(abc_parts) != set(options['pool_quota']):
        raise ValueError('Missing ABC sampling zone geometry')
    abc_scopes = {zone: QgsGeometry.unaryUnion(shapes).buffer(0.001, 12) for zone, shapes in abc_parts.items()}
    uncertain_layer = QgsVectorLayer(str(parent / 'abc_boundaries.gpkg') + '|layername=routing_exclusion', 'uncertain_alignment', 'ogr')
    if not uncertain_layer.isValid() or uncertain_layer.crs().authid() != crs:
        raise ValueError('Missing uncertain ring-alignment exclusion geometry')
    uncertain_shapes = [QgsGeometry(f.geometry()) for f in uncertain_layer.getFeatures()]
    if not uncertain_shapes or any(g.isEmpty() or not g.isGeosValid() for g in uncertain_shapes):
        raise ValueError('Invalid uncertain ring-alignment exclusion geometry')
    uncertain = QgsGeometry.unaryUnion(uncertain_shapes)
    checks, max_length_error, max_outside, max_outside_abc = {}, 0.0, 0.0, 0.0
    for route in walks:
        rid, length = route['route_id'], float(route['length_m'])
        if rid not in source_walks or route['arc_ids'] != source_walks[rid]['arc_ids'] or route['part_ids'] != source_walks[rid]['part_ids']:
            raise ValueError('Source walk changed: ' + rid)
        if len(route['arc_ids']) != len(route['part_ids']):
            raise ValueError('Arc/part sequence size mismatch: ' + rid)
        valid, reason = graph.validate_walk(route['arc_ids'])
        if not valid:
            raise ValueError('G2 direction/continuity/turn violation for ' + rid + ': ' + str(reason))
        source_length = 0.0
        ordered_points = []
        for aid, pid in zip(route['arc_ids'], route['part_ids']):
            if aid not in graph.arcs or graph.arcs[aid]['part_id'] != pid:
                raise ValueError('Graph arc/physical part identity mismatch: ' + rid)
            g = graph.arcs[aid]
            source_part_length, from_node, to_node = parts[pid]
            source_length += source_part_length
            expected_ends = (from_node, to_node) if g['direction'] == 'forward' else (to_node, from_node)
            if (g['from_node'], g['to_node']) != expected_ends or g['direction'] not in ['forward', 'backward']:
                raise ValueError('Graph/source direction/endpoints mismatch: ' + aid)
            sql = arcs[aid]
            if (sql[2], sql[3], sql[4], sql[6]) != (pid, g['from_node'], g['to_node'], g['direction']) or abs(sql[5] - g['length_m']) > 0.01 or abs(g['length_m'] - source_part_length) > 0.01:
                raise ValueError('Graph/source arc or length mismatch: ' + aid)
            part_shape = source_part_shapes[pid]
            if not part_shape.isGeosValid() or QgsWkbTypes.flatType(part_shape.wkbType()) != QgsWkbTypes.LineString or abs(part_shape.length() - source_part_length) > 0.01:
                raise ValueError('Invalid source physical part geometry/length: ' + pid)
            points = part_shape.asPolyline()
            if g['direction'] == 'backward':
                points.reverse()
            if not points or ordered_points and math.dist((ordered_points[-1].x(), ordered_points[-1].y()), (points[0].x(), points[0].y())) > 0.001:
                raise ValueError('G2 source physical geometries are disconnected: ' + rid)
            ordered_points.extend(points if not ordered_points else points[1:])
        shape = shapes[rid]
        if shape.isEmpty() or not shape.isGeosValid() or QgsWkbTypes.flatType(shape.wkbType()) != QgsWkbTypes.LineString:
            raise ValueError('G2 invalid/non-linestring route geometry: ' + rid)
        reconstructed = QgsGeometry.fromPolylineXY(ordered_points)
        if not shape.equals(reconstructed):
            raise ValueError('G2 route geometry differs from ordered source arc geometry: ' + rid)
        error = max(abs(shape.length() - length), abs(source_length - length))
        max_length_error = max(max_length_error, error)
        if error > 0.02 or length <= 0 or not math.isfinite(length):
            raise ValueError('G2 source/graph/geometry length mismatch: ' + rid)
        remaining = shape.difference(scopes[route['group']])
        outside = 0.0 if remaining.isEmpty() else remaining.length()
        max_outside = max(max_outside, outside)
        if outside > 0.02:
            raise ValueError('G3 route extends outside frozen research group: ' + rid)
        abc_remaining = shape.difference(abc_scopes[route['sampling_zone']])
        abc_outside = 0.0 if abc_remaining.isEmpty() else abc_remaining.length()
        max_outside_abc = max(max_outside_abc, abc_outside)
        if abc_outside > 0.02:
            raise ValueError('G3 route extends outside declared ABC sampling zone: ' + rid)
        if shape.intersects(uncertain):
            raise ValueError('Route touches an uncertain ring-alignment exclusion band: ' + rid)
        checks[rid] = {'uncertain_ring_alignment_avoided': True, 'route_id': rid, 'sampling_zone': route['sampling_zone'], 'group': route['group'], 'lez2027_group': route.get('lez2027_group'), 'policy_version': route.get('policy_version'), 'G1_OSM': 'passed_no_identified_source_graph_access_conflict',
                       'G1': 'survey_required', 'G2': 'passed_on_source_graph',
                       'G3': 'passed_in_frozen_research_scope', 'G4': 'survey_required',
                       'G5': 'survey_required', 'G6': 'survey_required',
                       'C6': None, 'C6_status': 'unknown_until_survey',
                       'source_graph_geometry_length_error_m': error,
                       'outside_group_length_m_after_1mm_buffer': outside,
                       'outside_sampling_zone_length_m_after_1mm_buffer': abc_outside,
                       'arc_count': len(route['arc_ids']), 'actual_checks_passed': True,
                       'pre_survey_admissible': True}
    checked_inputs = [graph_path, network_path, parent / 'candidate_routes.gpkg', parent / 'candidate_walks.json',
                      parent / 'sampling_zones.gpkg', parent / 'abc_boundaries.gpkg', sampling_path, work / 'config/selection_30.json']
    output = {'summary': {'status': 'passed', 'checked_at': now(), 'routes_checked': len(checks),
                         'inside': counts['inside'], 'outside': counts['outside'], 'sampling_zone_counts': zone_counts,
                         'unique_source_arcs_checked': len(wanted_arcs), 'unique_source_parts_checked': len(wanted_parts),
                         'G1_OSM_passed': True, 'G2_actual_graph_passed': True, 'G3_actual_geometry_passed': True, 'uncertain_ring_alignment_avoided_on_all_routes': True,
                         'legal_motorcycle_permission_verified': False, 'field_gates_verified': False,
                         'official_gis_verified': False, 'scope': 'LEZ2027_A_LEZ2030_minus_A_B_outside_LEZ2030_C',
                         'snapshot_utc': graph.data['snapshot_utc'], 'metric_crs': crs,
                         'polygon_buffer_tolerance_m': 0.001, 'maximum_allowed_outside_length_m': 0.02,
                         'max_source_graph_geometry_length_error_m': max_length_error,
                         'max_outside_group_length_m': max_outside, 'max_outside_sampling_zone_length_m': max_outside_abc, 'network_calls': 0,
                         'input_hashes': {relative(p, work): file_hash(p) for p in checked_inputs}},
              'routes': checks}
    return output, shapes, crs


def _native_export(payload, directory, checks, shapes, crs):
    from .gis import sink, check_layers
    from qgis.core import QgsProject, QgsWkbTypes
    directory.mkdir(parents=True, exist_ok=True)
    context = QgsProject.instance().transformContext()
    feature_rows = payload['features']
    ids = [r['route_id'] for r in feature_rows]
    if len(ids) != 60 or set(ids) != set(shapes):
        raise ValueError('Variable rows do not agree with source geometries')
    active = payload['feature_names']
    X = payload['X']
    if X is None or len(X) != 60 or any(len(row) != len(active) for row in X):
        raise ValueError('Invalid normalized X matrix dimensions')
    raw_fields = ['length_m', 'rc_length_m', 'connector_length_m', 'target_cell_fraction', 'reference_inside_length_fraction'] + FEATURE_NAMES
    raw_fields += ['P_' + rc + '_conditional_RC' for rc in ['RC1', 'RC2', 'RC3', 'RC4']]
    model_fields = ['lanes_scoring_model', 'maxspeed_scoring_model', 'lanes_known_length_fraction',
                    'maxspeed_known_length_fraction', 'lanes_imputed_length_fraction', 'maxspeed_imputed_length_fraction', 'P_osm_oneway']
    columns = [(k, 'str') for k in ['route_id', 'group', 'sampling_zone', 'lez2027_group', 'lez2030_group', 'policy_version', 'survey_date', 'lez_status_at_survey', 'stratum_id', 'rc_target', 'status', 'C6_status', 'G1_OSM', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6']]
    columns += [('pre_survey_admissible', 'bool')]
    columns += [(k, 'float') for k in raw_fields + model_fields + ['C6'] + ['X_' + name for name in FEATURE_NAMES]]
    temporary = directory / '.route_variables.building.gpkg'
    temporary.unlink(missing_ok=True)
    exported_rows, X_rows = [], []
    with sink(temporary, 'route_variables', columns, QgsWkbTypes.LineString, crs, context) as target:
        for row, xrow in zip(feature_rows, X):
            values = dict(row)
            values.update(checks['routes'][row['route_id']])
            values.update({'X_' + name: float(value) for name, value in zip(active, xrow)})
            if any(not math.isfinite(float(v)) for v in xrow):
                raise ValueError('Non-finite normalized variables: ' + row['route_id'])
            target.add(values, shapes[row['route_id']])
            exported_rows.append({k: values.get(k) for k, kind in columns})
            X_rows.append({'route_id': row['route_id'], **{'X_' + name: values.get('X_' + name) for name in FEATURE_NAMES}})
    check_layers(temporary, {'route_variables': 60}, crs)
    final = directory / 'route_variables.gpkg'
    temporary.replace(final)
    write_csv(directory / 'route_variables.csv', exported_rows, [k for k, kind in columns])
    write_csv(directory / 'X_standardized.csv', X_rows, ['route_id'] + ['X_' + name for name in FEATURE_NAMES])
    atomic_json(directory / 'gate_checks.json', checks)
    units = {'length_m': 'm; full route including connector traversals',
             'rc_length_m': 'm; only RC1-RC4 traversals', 'connector_length_m': 'm; remaining traversals',
             'P_RC1..P_RC4': 'dimensionless; RC length / full route length including connectors; sum may be below one',
             'P_RC*_conditional_RC': 'dimensionless; RC1-RC4-only denominator, sum=1',
             'lanes': 'lanes; length-weighted observed total-road OSM lanes, NULL if absent',
             'maxspeed': 'km/h; length-weighted observed posted OSM tag, not measured driving speed',
             'lanes_scoring_model': 'lanes; observed/imputed model over full route',
             'maxspeed_scoring_model': 'km/h; observed/imputed model over full route',
             '*_known_length_fraction': 'dimensionless; observed tag length / full route length',
             '*_imputed_length_fraction': 'dimensionless; complementary model-estimated fraction',
             'junctions_per_km': 'distinct mapped graph junction nodes per full route km',
             'signals_per_km': 'distinct mapped signal nodes per full route km; OSM proxy',
             'P_oneway': 'dimensionless; length on parts with one effective source-graph motorcycle direction / full route length',
             'X_*': 'dimensionless [0,1]; fixed minmax fit on all 60; lanes/maxspeed use explicit scoring models',
             'target_cell_fraction': 'dimensionless; target RC/stratum length / full route length',
             'reference_inside_length_fraction': 'dimensionless; reference proxy-inside length / full route length; not verified legal GIS',
             'C6': 'unknown until field survey; no observed score supplied'}
    atomic_json(directory / 'variable_units.json', {'units': units, 'normalization': payload['normalization'],
                                                  'active_X_features': active, 'raw_and_model_separate': True,
                                                  'geometry_copied_from_source': True})
    return {'path': str(final), 'features': 60, 'layers': ['route_variables'], 'gate_checks': checks,
            'sha256': file_hash(final), 'raw_osm_modified': False, 'network_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify', 'export'])
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text())
    from qgis.core import QgsApplication
    with tempfile.TemporaryDirectory(prefix='lez-gates-qgis-') as profile:
        app = QgsApplication([], False, profile)
        app.initQgis()
        checks, shapes, crs = _native_checks(payload)
        result = checks if args.command == 'verify' else _native_export(payload, args.directory, checks, shapes, crs)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        app.exitQgis()


if __name__ == '__main__':
    main()
