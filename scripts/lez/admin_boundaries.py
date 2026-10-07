"""Build administrative polygons from the already archived OSM boundary response."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import unicodedata

from .common import (WORK, atomic_json, cached_manifest, code_hash, commit_manifest,
                     digest, event, file_hash, now, relative, write_csv)


def normalized_name(value):
    value = unicodedata.normalize('NFC', value).strip()
    for prefix in ('Phường ', 'Xã ', 'Thị trấn ', 'Huyện ', 'Quận ', 'Thị xã '):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return ' '.join(value.replace('–', '-').replace('—', '-').split())


def stitch_rings(ways):
    """Join by actual node IDs; never close a gap by proximity."""
    remaining = {int(key): list(refs) for key, refs in ways.items()}
    if any(len(refs) < 2 for refs in remaining.values()):
        raise ValueError('Boundary member way has fewer than two nodes')
    rings = []
    closed = [key for key, refs in remaining.items() if refs[0] == refs[-1]]
    for key in sorted(closed):
        rings.append(remaining.pop(key))
    endpoints = defaultdict(list)
    for key, refs in remaining.items():
        endpoints[refs[0]].append(key)
        endpoints[refs[-1]].append(key)
    if any(len(keys) != 2 for keys in endpoints.values()):
        raise ValueError('Open or ambiguous boundary endpoint; degree must equal two')
    while remaining:
        key = min(remaining)
        chain = remaining.pop(key)
        while chain[-1] != chain[0]:
            matches = [candidate for candidate in endpoints[chain[-1]] if candidate in remaining]
            if len(matches) != 1:
                raise ValueError('Boundary cannot be joined into an unambiguous ring')
            refs = remaining.pop(matches[0])
            if refs[0] != chain[-1]:
                refs.reverse()
            chain.extend(refs[1:])
        rings.append(chain)
    if any(len(ring) < 4 or len(set(ring[:-1])) < 3 for ring in rings):
        raise ValueError('Boundary ring needs at least three distinct vertices')
    return rings


def relation_rings(relation, ways, nodes):
    groups = {'outer': {}, 'inner': {}}
    seen = set()
    for member in relation.get('members', []):
        role, kind, ref = member.get('role', ''), member['type'], member['ref']
        if kind == 'node' and role in {'admin_centre', 'label'}:
            continue
        if kind != 'way' or role not in groups:
            raise ValueError(f'Unsupported boundary member: {kind}/{ref}, role={role!r}')
        if ref in seen:
            raise ValueError(f'Duplicate boundary way member: {ref}')
        seen.add(ref)
        if ref not in ways:
            raise ValueError(f'Missing boundary way: {ref}')
        refs = ways[ref].get('nodes', [])
        missing = [node for node in refs if node not in nodes]
        if missing:
            raise ValueError(f'Missing boundary node: {missing[0]}')
        groups[role][ref] = refs
    if not groups['outer']:
        raise ValueError('Relation has no outer way members')
    return {role: stitch_rings(members) for role, members in groups.items()}


def build_admin_units(work=WORK, force=False):
    from .gis import (QgsGeometry, QgsWkbTypes, initialize, read_polygon, sink,
                      check_layers, QgsCoordinateReferenceSystem, QgsCoordinateTransform)
    from qgis.core import QgsPointXY
    work = Path(work)
    raw_path = work / 'data/hanoi_tiles/data/raw/hanoi_osm_20261001.json'
    source_manifest = raw_path.with_name('boundary_manifest.json')
    source = json.loads(source_manifest.read_text())
    project = json.loads((work / 'data/hanoi_tiles/tile_project.json').read_text())
    if file_hash(raw_path) != source['response_sha256']:
        raise ValueError('Archived boundary response hash mismatch')
    if source.get('snapshot_utc') != project['snapshot_utc']:
        raise ValueError('Boundary snapshot differs from project snapshot')
    inputs = {'raw_sha256': file_hash(raw_path), 'manifest_sha256': file_hash(source_manifest),
              'snapshot_utc': project['snapshot_utc'], 'metric_crs': project['metric_crs']}
    fingerprint = digest({'inputs': inputs, 'code': code_hash(['common.py', 'gis.py', 'admin_boundaries.py'])})
    directory = work / 'data/processed/admin_boundaries' / fingerprint[:20]
    cached = None if force else cached_manifest(directory, fingerprint)
    if cached:
        atomic_json(work / 'reports/boundaries/admin_report.json', cached['report'])
        event('admin_boundaries', 'Đọc lớp địa bàn từ cache đã kiểm tra', units=cached['report']['units'])
        return directory, cached['report'], True
    raw = json.loads(raw_path.read_bytes())
    if raw.get('remark') or not isinstance(raw.get('elements'), list):
        raise ValueError('Boundary response has a remark or lacks elements')
    objects = raw['elements']
    if not objects or objects[-1].get('type') != 'count':
        raise ValueError('Boundary response lacks its final count record')
    for kind, label in [('node', 'nodes'), ('way', 'ways'), ('relation', 'relations')]:
        actual = sum(item['type'] == kind for item in objects)
        if actual != int(objects[-1]['tags'][label]):
            raise ValueError(f'Boundary {label} count mismatch')
    indexed = {kind: {item['id']: item for item in objects if item['type'] == kind}
               for kind in ('node', 'way', 'relation')}
    parent = indexed['relation'].get(int(source['relation_id']))
    if parent is None:
        raise ValueError('Parent Hanoi relation is missing')
    unit_ids = sorted(member['ref'] for member in parent['members']
                      if member['type'] == 'relation' and member.get('role') == 'subarea')
    if not unit_ids or len(unit_ids) != len(set(unit_ids)):
        raise ValueError('Parent relation has no unique subarea inventory')
    context = initialize(work)
    crs = project['metric_crs']
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'),
                                       QgsCoordinateReferenceSystem(crs), context)
    geometry_rows, rows, failures = [], [], []
    for relation_id in unit_ids:
        relation = indexed['relation'].get(relation_id)
        try:
            if relation is None or relation.get('tags', {}).get('boundary') != 'administrative':
                raise ValueError('Missing or non-administrative subarea relation')
            rings = relation_rings(relation, indexed['way'], indexed['node'])
            def ring_geometry(refs):
                return QgsGeometry.fromPolygonXY([[QgsPointXY(indexed['node'][ref]['lon'], indexed['node'][ref]['lat']) for ref in refs]])
            outers = [ring_geometry(refs) for refs in rings['outer']]
            inners = [ring_geometry(refs) for refs in rings['inner']]
            if any(not g.isGeosValid() for g in outers + inners):
                raise ValueError('Invalid original boundary ring; no silent geometry repair')
            geometry = QgsGeometry.unaryUnion(outers)
            if inners:
                holes = QgsGeometry.unaryUnion(inners)
                if not geometry.contains(holes):
                    raise ValueError('An inner boundary ring lies outside its outer rings')
                geometry = geometry.difference(holes)
            if not geometry.isGeosValid():
                raise ValueError('Invalid assembled multipolygon')
            geometry.transform(transform)
            geometry.convertToMultiType()
            if geometry.isEmpty() or geometry.area() <= 0 or not geometry.isGeosValid():
                raise ValueError('Invalid transformed administrative polygon')
            tags = relation['tags']
            name = tags.get('name', '')
            if not name:
                raise ValueError('Administrative relation has no name')
            row = {'osm_relation_id': str(relation_id), 'name': name,
                   'normalized_name': normalized_name(name), 'admin_level': tags.get('admin_level', ''),
                   'osm_version': relation.get('version'), 'snapshot_utc': project['snapshot_utc'],
                   'source_status': 'technical_osm', 'area_m2': geometry.area()}
            rows.append(row)
            geometry_rows.append((row, geometry))
        except (ValueError, KeyError, TypeError) as exc:
            failures.append({'osm_relation_id': str(relation_id), 'error': str(exc)})
    if failures:
        atomic_json(work / 'reports/boundaries/admin_geometry_errors.json', {'errors': failures, 'inputs': inputs})
        raise ValueError(f'{len(failures)} administrative polygons could not be reconstructed; see admin_geometry_errors.json')
    names = [row['normalized_name'] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError('Ambiguous duplicate administrative names; use explicit IDs')
    hanoi = read_polygon(work / 'maps/hanoi_tiles/hanoi_boundary.geojson', crs, context)
    union = QgsGeometry.unaryUnion([g for _, g in geometry_rows])
    missing = hanoi.difference(union)
    outside = union.difference(hanoi)
    pairwise_overlaps = []
    for i, (left_row, left) in enumerate(geometry_rows):
        for right_row, right in geometry_rows[i + 1:]:
            if left.boundingBox().intersects(right.boundingBox()):
                intersection = left.intersection(right)
                if not intersection.isEmpty() and intersection.area() > 0:
                    pairwise_overlaps.append((left_row['osm_relation_id'] + '/' + right_row['osm_relation_id'], intersection))
    qa = {'missing_area_m2': missing.area(),
          'outside_hanoi_area_m2': outside.area(),
          'overlap_area_m2': max(0., sum(g.area() for _, g in geometry_rows) - union.area())}
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / '.admin_units.building.gpkg'
    temp.unlink(missing_ok=True)
    fields = [(key, 'float' if key == 'area_m2' else 'int' if key == 'osm_version' else 'str') for key in rows[0]]
    with sink(temp, 'admin_units', fields, QgsWkbTypes.MultiPolygon, crs, context) as output:
        for row, geometry in geometry_rows:
            output.add(row, geometry)
    check_layers(temp, {'admin_units': len(rows)}, crs)
    temp.replace(directory / 'admin_units.gpkg')
    qa_path = directory / '.admin_qa.building.gpkg'
    qa_path.unlink(missing_ok=True)
    issues = []
    for issue_id, geometry in [('missing', missing), ('outside_hanoi', outside), *pairwise_overlaps]:
        if geometry.isEmpty() or geometry.area() <= 0:
            continue
        # Intersections can include lines/points alongside polygons.
        if geometry.type() != QgsWkbTypes.PolygonGeometry:
            polygons = [g for g in geometry.asGeometryCollection() if g.type() == QgsWkbTypes.PolygonGeometry]
            if not polygons:
                continue
            geometry = QgsGeometry.unaryUnion(polygons)
        geometry.convertToMultiType()
        issues.append((issue_id, geometry))
    with sink(qa_path, 'admin_qa_issues', [('issue_id', 'str'), ('area_m2', 'float')], QgsWkbTypes.MultiPolygon, crs, context) as output:
        for issue_id, geometry in issues:
            output.add({'issue_id': issue_id, 'area_m2': geometry.area()}, geometry)
    check_layers(qa_path, {'admin_qa_issues': len(issues)}, crs)
    qa_path.replace(directory / 'admin_qa.gpkg')
    write_csv(directory / 'admin_units.csv', rows, list(rows[0]))
    report = {'units': len(rows), 'expected_subareas': len(unit_ids), 'snapshot_utc': project['snapshot_utc'],
              'metric_crs': crs, 'source_status': 'technical_osm', 'qa': qa, 'input_hashes': inputs,
              'raw_osm_modified': False, 'network_calls': 0, 'recorded_at': now()}
    atomic_json(directory / 'admin_report.json', report)
    commit_manifest(directory, fingerprint, report, ['admin_units.gpkg', 'admin_units.csv', 'admin_qa.gpkg', 'admin_report.json'])
    atomic_json(work / 'reports/boundaries/admin_report.json', report)
    event('admin_boundaries', 'Đã dựng đa giác địa bàn từ dữ liệu gốc', units=len(rows), **qa)
    return directory, report, False
