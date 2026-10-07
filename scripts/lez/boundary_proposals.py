"""Resolve declared research rules to OSM IDs and produce inspectable draft layers."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .admin_boundaries import normalized_name
from .common import (WORK, atomic_json, cached_manifest, code_hash, commit_manifest,
                     digest, event, file_hash, input_path, relative, write_csv)


def validate_rules(rules):
    expected = {f'V{i}' for i in range(1, 6)} | {f'N{i}' for i in range(1, 11)}
    rows = rules.get('strata', [])
    codes = [row.get('stratum_id') for row in rows]
    if len(codes) != 15 or set(codes) != expected:
        raise ValueError('Automation rules must define each V1–V5/N1–N10 exactly once')
    if rules.get('automatic_activation') is not False:
        raise ValueError('Draft automation must not activate research definitions automatically')
    names = [normalized_name(name) for name in rules['legal_scope']['names']]
    if len(names) != 36 or len(set(names)) != 36:
        raise ValueError('The verified legal-scope declaration needs 36 unique unit names')
    inside_names = [normalized_name(name) for row in rows if row['stratum_id'].startswith('V') for name in row.get('names', [])]
    if len(set(inside_names)) != len(inside_names) or set(inside_names) != set(names):
        raise ValueError('V research assignments must partition the declared legal name list')
    outside_names = [normalized_name(name) for row in rows if row['stratum_id'].startswith('N') for name in row.get('names', [])]
    if len(outside_names) != len(set(outside_names)) or set(outside_names) & set(names):
        raise ValueError('N assignments must be unique and outside the declared LEZ units')
    if any(not row.get('names') or not row.get('rationale') for row in rows):
        raise ValueError('Each research stratum needs explicit names and a rationale')
    if rules.get('unassigned_policy') != 'report_only':
        raise ValueError('Unassigned units must be reported; no implicit residual stratum')
    return rows


def resolve_names(names, inventory):
    by_name = {}
    for row in inventory:
        key = normalized_name(row['name'])
        if key in by_name:
            raise ValueError('Ambiguous administrative name: ' + key)
        by_name[key] = row
    resolved = []
    for name in names:
        key = normalized_name(name)
        if key not in by_name:
            raise ValueError('Administrative unit not found in snapshot: ' + name)
        resolved.append(by_name[key])
    return resolved


def render_preview(zones, destination, snapshot_utc):
    from qgis.core import (QgsVectorLayer, QgsCategorizedSymbolRenderer, QgsRendererCategory,
                           QgsFillSymbol, QgsMapSettings, QgsMapRendererParallelJob)
    from qgis.PyQt.QtCore import QSize, Qt
    from qgis.PyQt.QtGui import QColor, QPainter, QFont, QImage
    layers = []
    unassigned = QgsVectorLayer(str(zones) + '|layername=unassigned_scope', 'Chưa phân tầng', 'ogr')
    if unassigned.isValid() and unassigned.featureCount():
        unassigned.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '230,0,170,120', 'outline_color': '160,0,120,255', 'outline_width': '0.2'}))
        layers.append(unassigned)
    strata = QgsVectorLayer(str(zones) + '|layername=strata', 'Tầng nghiên cứu dự thảo', 'ogr')
    codes = [f'V{i}' for i in range(1, 6)] + [f'N{i}' for i in range(1, 11)]
    colors = ['#246dba','#3d9acb','#71c5d6','#9ccdd6','#c2e1dc','#b2cc66','#7dae5c','#4c9b68','#3c7b5e','#efcb66','#e7a44d','#d78354','#c46a62','#9f7095','#746da5']
    categories = [QgsRendererCategory(code, QgsFillSymbol.createSimple({'color': color, 'outline_color': '#4c5560', 'outline_width': '0.15'}), code) for code, color in zip(codes, colors)]
    strata.setRenderer(QgsCategorizedSymbolRenderer('zone_id', categories))
    layers.append(strata)
    hanoi = QgsVectorLayer(str(zones) + '|layername=hanoi', 'Hà Nội', 'ogr')
    hanoi.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '#fafafa', 'outline_color': '#24313e', 'outline_width': '0.4'}))
    layers.append(hanoi)
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setDestinationCrs(hanoi.crs())
    settings.setBackgroundColor(QColor('white'))
    extent = hanoi.extent()
    extent.scale(1.12)
    settings.setExtent(extent)
    settings.setOutputSize(QSize(1400, 1250))
    job = QgsMapRendererParallelJob(settings)
    job.start(); job.waitForFinished()
    map_image = job.renderedImage()
    image = QImage(1880, 1300, QImage.Format.Format_ARGB32)
    image.fill(QColor('white'))
    painter = QPainter(image)
    painter.drawImage(470,25,map_image)
    painter.setFont(QFont('Arial', 14))
    painter.setPen(QColor('#24313e'))
    painter.drawText(35, 48, 'PHÂN TẦNG DỰ THẢO — CHƯA KHÓA')
    painter.setFont(QFont('Arial', 11))
    for index, (code, color) in enumerate(zip(codes, colors)):
        y = 82 + index * 24
        painter.fillRect(35, y - 13, 20, 15, QColor(color))
        painter.drawText(65, y, code)
    painter.fillRect(35, 448, 20, 15, QColor('#e600aa'))
    painter.drawText(65, 461, 'Chưa phân tầng / cần quyết định')
    painter.drawText(35, 491, f'OSM {snapshot_utc[:10]} · {hanoi.crs().authid()} · mét')
    painter.drawText(35, 525, 'Nguồn hình học: OSM, chưa xác minh pháp lý')
    painter.end()
    if not image.save(str(destination), 'PNG'):
        raise RuntimeError('Cannot save boundary preview PNG')


def build_proposal(work, admin_dir, force=False):
    from .gis import initialize, read_polygon, sink, QgsWkbTypes
    from .boundaries import prepare
    work, admin_dir = Path(work), Path(admin_dir)
    rules_path = work / 'config/boundary_automation.json'
    rules = json.loads(rules_path.read_text())
    definitions = validate_rules(rules)
    legal = rules['legal_scope']
    legal_file = input_path(work, legal['source_file'])
    if not legal_file or not legal_file.exists() or file_hash(legal_file) != legal['verified_sha256']:
        raise ValueError('Legal PDF is missing or has changed; re-check the declared clause/name list before using it')
    if legal.get('name_list_verified_against_pdf') is not True:
        raise ValueError('Legal name list has not been verified against the cited PDF')
    with (admin_dir / 'admin_units.csv').open(newline='', encoding='utf-8-sig') as stream:
        inventory = list(csv.DictReader(stream))
    lez_units = resolve_names(legal['names'], inventory)
    resolved = {row['stratum_id']: resolve_names(row['names'], inventory) for row in definitions}
    original_mapping = work / 'config/strata_mapping.csv'
    with original_mapping.open(newline='', encoding='utf-8-sig') as stream:
        originals = {row['stratum_id']: row for row in csv.DictReader(stream)}
    inputs = {'rules': file_hash(rules_path), 'admin_manifest': file_hash(admin_dir / 'manifest.json'),
              'legal_pdf': file_hash(legal_file), 'active_config': file_hash(work / 'config/boundary_project.json'),
              'active_mapping': file_hash(original_mapping)}
    fingerprint = digest({'inputs': inputs, 'code': code_hash(['common.py', 'gis.py', 'boundaries.py', 'boundary_proposals.py'])})
    directory = work / 'data/processed/boundary_proposals' / fingerprint[:20]
    cached = None if force else cached_manifest(directory, fingerprint)
    if cached:
        output = cached['report']
        config_path = directory / 'boundary_project.draft.json'
        zones_dir, qa, _ = prepare(work, config_path=config_path, publish_report=False)
        if relative(zones_dir / 'zones.gpkg', work) != output['zones']:
            raise ValueError('Cached proposal refers to a different boundary result')
        return directory, output, True
    directory.mkdir(parents=True, exist_ok=True)
    crs = json.loads((work / 'data/hanoi_tiles/tile_project.json').read_text())['metric_crs']
    context = initialize(work)
    admin_path = admin_dir / 'admin_units.gpkg'
    geometry = read_polygon(admin_path, crs, context, 'admin_units', 'osm_relation_id', [row['osm_relation_id'] for row in lez_units])
    geometry.convertToMultiType()
    proxy = directory / '.lez_admin_proxy.building.gpkg'
    proxy.unlink(missing_ok=True)
    with sink(proxy, 'lez_admin_proxy', [('status','str'),('source_id','str'),('area_m2','float')], QgsWkbTypes.MultiPolygon, crs, context) as output:
        output.add({'status':'draft_admin_extent_proxy','source_id':legal['source_id'],'area_m2':geometry.area()}, geometry)
    proxy.replace(directory / 'lez_admin_proxy.gpkg')
    mapping_rows, trace = [], []
    for definition in definitions:
        code = definition['stratum_id']
        ids = [row['osm_relation_id'] for row in resolved[code]]
        mapping_rows.append({'stratum_id':code,'domain':'inside' if code.startswith('V') else 'outside',
                             'definition':originals[code]['definition'], 'geometry_path':relative(admin_path,work),
                             'layer':'admin_units','selector_field':'osm_relation_id',
                             'selector_values':json.dumps(ids), 'source_id':rules['method_id'] + '/' + code,'status':'draft'})
        for unit in resolved[code]:
            trace.append({'stratum_id':code,'osm_relation_id':unit['osm_relation_id'],'name':unit['name'],
                          'status':'draft','rationale':definition['rationale']})
    mapping_path = directory / 'strata_mapping.draft.csv'
    write_csv(mapping_path, mapping_rows, list(mapping_rows[0]))
    write_csv(directory / 'assignment_trace.csv', trace, list(trace[0]))
    assigned = {row['osm_relation_id'] for row in trace}
    unassigned = [row for row in inventory if row['osm_relation_id'] not in assigned]
    write_csv(directory / 'unassigned_admin_units.csv', unassigned, list(inventory[0]))
    config = json.loads((work / 'config/boundary_project.json').read_text())
    config['lez_source'] = {'path':relative(directory / 'lez_admin_proxy.gpkg',work), 'layer':'lez_admin_proxy',
                            'status':'draft','source_id':legal['source_id'],
                            'research_scope_note':'Research administrative extent proxy, not a verified official GIS boundary.'}
    config['strata_mapping'] = relative(mapping_path, work)
    config_path = directory / 'boundary_project.draft.json'
    atomic_json(config_path, config)
    zones_dir, qa, _ = prepare(work, config_path=config_path, publish_report=False)
    render_preview(zones_dir / 'zones.gpkg', directory / 'preview.png', qa['snapshot_utc'])
    report = {'profile_status':'draft', 'automatic_activation':False, 'legal_units':len(lez_units),
              'strata_count':15, 'assigned_admin_units':len(assigned), 'unassigned_admin_units':len(unassigned),
              'unassigned_names':[row['normalized_name'] for row in unassigned],
              'config':relative(config_path,work), 'mapping':relative(mapping_path,work),
              'zones':relative(zones_dir / 'zones.gpkg',work), 'preview':relative(directory / 'preview.png',work),
              'boundary_qa':qa, 'input_hashes':inputs,
              'legal_provenance':{key:legal[key] for key in ['source_id','verified_sha256','verified_pages','clause_refs']}}
    atomic_json(directory / 'proposal_report.json', report)
    commit_manifest(directory, fingerprint, report, ['lez_admin_proxy.gpkg','boundary_project.draft.json','strata_mapping.draft.csv',
                                                    'assignment_trace.csv','unassigned_admin_units.csv','proposal_report.json','preview.png'])
    event('boundary_proposals','Đã tạo bản phân tầng dự thảo và danh sách chưa gán', strata=15, unassigned_units=len(unassigned))
    return directory, report, False
