"""Export named ABC/LEZ route maps using the existing project PyQGIS worker."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import shutil
import tempfile
import unicodedata


def export_maps(work, output=None):
    """Callable from an ordinary Python notebook; native cartography runs separately."""
    from .pipeline import kernel_spec
    work = Path(work).resolve()
    output = Path(output).resolve() if output else work / 'maps/routes'
    spec = kernel_spec()
    env = os.environ.copy(); env.update(spec.get('env', {}))
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    completed = subprocess.run([spec['argv'][0], str(Path(__file__).resolve()), '--work', str(work), '--output', str(output)], env=env, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError('Route map export failed: ' + completed.stderr[-4000:])
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _native_export(work, output):
    WORK, OUTPUT = Path(work).resolve(), Path(output).resolve()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(WORK / 'scripts'))
    from lez.common import cached_manifest, file_hash, input_path, now
    from lez.gis import initialize
    from qgis.core import (QgsVectorLayer, QgsGeometry, QgsRectangle, QgsLineSymbol, QgsFillSymbol,
                           QgsMapSettings, QgsMapRendererParallelJob, QgsCategorizedSymbolRenderer,
                           QgsRendererCategory)
    from qgis.PyQt.QtCore import QSize, QRectF, Qt
    from qgis.PyQt.QtGui import QColor, QImage, QPainter, QFont, QFontMetricsF

    profile = tempfile.TemporaryDirectory(prefix='abc-cartography-profile-')
    initialize(Path(profile.name))
    COLORS = {'inside': '#176cb1', 'outside': '#c45d17'}
    selection = json.loads((WORK / 'reports/selection/latest_selection_30.json').read_text())
    options = json.loads((WORK / 'config/selection_30.json').read_text())
    sampling_report_path = input_path(WORK, options['parent_report'])
    sampling = json.loads(sampling_report_path.read_text())
    selected_path = input_path(WORK, selection['paths']['geometry'])
    candidate_path = input_path(WORK, sampling['paths']['routes'])
    zones_path = input_path(WORK, sampling['paths']['zones'])
    network_path = (WORK / 'data/processed/network.gpkg').resolve()
    admin_path = (WORK / 'data/processed/admin_units.gpkg').resolve()
    protected = [selected_path, candidate_path, zones_path, network_path, admin_path,
                 WORK / 'reports/selection/latest_selection_30.json', sampling_report_path, WORK / 'config/selection_30.json']
    before_hashes = {str(p): file_hash(p) for p in protected}
    for path in (selected_path, candidate_path):
        manifest = json.loads((path.parent / 'manifest.json').read_text())
        if cached_manifest(path.parent, manifest['fingerprint']) is None:
            raise ValueError('Source cache is incomplete or has wrong hashes: ' + str(path))


    # OGR may persist feature-count metadata even when only viewing/subsetting a
    # GeoPackage. All native layers therefore open disposable copies; original
    # source hashes and manifest checks still refer to the immutable bundles.
    scratch = tempfile.TemporaryDirectory(prefix='abc-map-source-copies-')
    scratch_paths = {}
    for index, source_path in enumerate(protected):
        if source_path.suffix.lower() == '.gpkg':
            copy_path = Path(scratch.name) / (str(index) + '_' + source_path.name)
            shutil.copy2(source_path, copy_path)
            if file_hash(copy_path) != before_hashes[str(source_path)]:
                raise ValueError('GeoPackage copy differs from source: ' + str(source_path))
            scratch_paths[source_path.resolve()] = copy_path

    def layer(path, name):
        native_path = scratch_paths.get(Path(path).resolve())
        if native_path is None:
            raise ValueError('Native map layer must use a protected GeoPackage copy')
        value = QgsVectorLayer(str(native_path) + '|layername=' + name, name, 'ogr')
        if not value.isValid() or value.crs().authid() != 'EPSG:3405':
            raise ValueError('Invalid layer or CRS: ' + name)
        return value


    all_routes = layer(candidate_path, 'candidate_routes')
    assessment = layer(selected_path, 'candidate_assessment')
    selected = layer(selected_path, 'selected_routes')
    city = layer(zones_path, 'hanoi')
    inside = layer(zones_path, 'sampling_inside')
    outside = layer(zones_path, 'sampling_outside')
    reference = layer(zones_path, 'reference_lez_2030')
    abc = layer(zones_path, 'abc_zones')
    abc_geometry = {str(f['sampling_zone']): QgsGeometry(f.geometry()) for f in abc.getFeatures()}
    if set(abc_geometry) != {'A', 'B', 'C'}:
        raise ValueError('Missing ABC zone geometries')
    abc.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '0,0,0,0', 'outline_color': '#6553a5', 'outline_width': '0.30'}))
    admins = layer(admin_path, 'admin_units')
    roads = layer(network_path, 'segments')
    roads.setSubsetString("rc IN ('RC1','RC2') AND scope_length_m > 0")
    roads.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color': '#cfd6da', 'line_width': '0.12'}))
    city.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '#f6f7f5', 'outline_color': '#889397', 'outline_width': '0.4'}))
    admins.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '0,0,0,0', 'outline_color': '#e1e5e3', 'outline_width': '0.15'}))
    inside.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '#e0edf6', 'outline_color': '#809cac', 'outline_width': '0.25'}))
    reference.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '0,0,0,0', 'outline_color': '#9b6586',
                                                            'outline_width': '0.38', 'outline_style': 'dash'}))
    city_geometry = QgsGeometry.unaryUnion([f.geometry() for f in city.getFeatures()])
    inside_geometry = QgsGeometry.unaryUnion([f.geometry() for f in inside.getFeatures()])
    outside_geometry = QgsGeometry.unaryUnion([f.geometry() for f in outside.getFeatures()])
    info = {str(f['route_id']): f for f in assessment.getFeatures()}
    selected_ids = {str(f['route_id']) for f in selected.getFeatures()}
    assert selected_ids == set(selection['selected_route_ids']) and len(selected_ids) == 30


    def names(sequence):
        values = [unicodedata.normalize('NFC', s.strip()) for s in sequence.split('→')]
        known = [s for s in values if s and not s.startswith('(')]
        major = [s for s in known if not s.lower().startswith(('ngõ ', 'ngách ', 'hướng đi ', 'vòng xoay '))]
        unique = list(dict.fromkeys(major or known))
        compact = ' → '.join([unique[0], unique[-1]] if len(unique) > 1 else unique)
        first = unique[0] if unique else 'Chưa có tên OSM'
        for prefix in ('Đường ', 'Phố '):
            if first.startswith(prefix): first = first[len(prefix):]
        return compact or 'Chưa có tên đường trong OSM', first, unique


    records, source_geometries = [], {}
    for f in all_routes.getFeatures():
        rid = str(f['route_id']); original = info[rid]; geometry = f.geometry()
        if bytes(geometry.asWkb()) != bytes(original.geometry().asWkb()) or f['group'] != original['group']:
            raise ValueError('Current 60 differs from the source of the selected 30: ' + rid)
        if geometry.isEmpty() or not geometry.isGeosValid(): raise ValueError('Invalid route ' + rid)
        group = str(f['group']); zone = str(f['sampling_zone']); domain = inside_geometry if group == 'inside' else outside_geometry
        abc_outside_length = geometry.difference(abc_geometry[zone].buffer(0.001, 8)).length()
        if abc_outside_length > 0.02:
            raise ValueError('Route sampling zone disagrees with ABC polygons: ' + rid)
        outside_length = geometry.difference(domain.buffer(0.001, 8)).length()
        if outside_length > 0.02: raise ValueError('Route group disagrees with frozen research scope: ' + rid)
        if abs(geometry.length() - float(f['length_m'])) > 1e-5: raise ValueError('Length mismatch ' + rid)
        sequence = str(original['street_sequence']); short, first, unique = names(sequence)
        middle = geometry.interpolate(geometry.length() * 0.5).asPoint()
        record = {'route_id': rid, 'group': group, 'sampling_zone': zone, 'stratum_id': str(f['stratum_id']),
                  'lez2027_group': ('inside' if zone=='A' else 'outside'), 'lez2030_group': group, 'policy_version': str(original['policy_version']), 'survey_date': ('' if str(original['survey_date']) in ('NULL','None') else str(original['survey_date'])), 'lez_status_at_survey': ('' if str(original['lez_status_at_survey']) in ('NULL','None') else str(original['lez_status_at_survey'])),
                  'rc_target': str(f['rc_target']), 'length_km': geometry.length() / 1000,
                  'route_name': short, 'first_street': first, 'street_sequence': sequence,
                  'named_streets': unique, 'has_named_street': bool(unique), 'selected_30': rid in selected_ids,
                  'geometry_sha256': hashlib.sha256(bytes(geometry.asWkb())).hexdigest(),
                  'points_metric': [[p.x(), p.y()] for p in geometry.asPolyline()],
                  'mid_metric': [middle.x(), middle.y()]}
        source_geometries[rid] = QgsGeometry(geometry); records.append(record)
    records.sort(key=lambda r: r['route_id'])
    assert len(records) == 60 and {z: sum(r['sampling_zone'] == z for r in records) for z in 'ABC'} == {'A':20,'B':20,'C':20}


    def poly_path(geometry, transform):
        polygons = geometry.asMultiPolygon() if geometry.isMultipart() else [geometry.asPolygon()]
        commands = []
        for polygon in polygons:
            for ring in polygon:
                if not ring: continue
                points = [transform(p.x(), p.y()) for p in ring]
                commands.append('M' + 'L'.join(f'{x:.2f},{y:.2f}' for x, y in points) + 'Z')
        return ''.join(commands)


    def svg_data():
        extent = QgsRectangle(city.extent()); extent.scale(1.06)
        width, height = 1000, 1280
        scale = min(width / extent.width(), height / extent.height())
        dx, dy = (width - extent.width() * scale) / 2, (height - extent.height() * scale) / 2
        def transform(x, y): return (dx + (x - extent.xMinimum()) * scale, dy + (extent.yMaximum() - y) * scale)
        paths = {}
        for key, value in [('city', city), ('inside', inside), ('reference', reference), ('abc', abc)]:
            paths[key] = ''.join(poly_path(f.geometry().simplify(15), transform) for f in value.getFeatures())
        paths['admin'] = ''.join(poly_path(f.geometry().simplify(35), transform) for f in admins.getFeatures())
        road_paths = []
        for f in roads.getFeatures():
            geometry = f.geometry().simplify(25)
            lines = geometry.asMultiPolyline() if geometry.isMultipart() else [geometry.asPolyline()]
            for line in lines:
                points = [transform(p.x(), p.y()) for p in line]
                road_paths.append('M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in points))
        paths['roads'] = ''.join(road_paths)
        output = []
        for row in records:
            item = {k: v for k, v in row.items() if not k.endswith('_metric')}
            item['points'] = [[round(x, 2), round(y, 2)] for x, y in (transform(*p) for p in row['points_metric'])]
            item['mid'] = list(transform(*row['mid_metric']))
            output.append(item)
        inner = inside.extent(); x0, y0 = transform(inner.xMinimum(), inner.yMaximum()); x1, y1 = transform(inner.xMaximum(), inner.yMinimum())
        return {'width': width, 'height': height, 'paths': paths, 'routes': output,
                'inside_box': [x0 - 35, y0 - 35, x1 - x0 + 70, y1 - y0 + 70]}


    def draw_map(route_layer, extent, width, height):
        route_layer.setRenderer(QgsCategorizedSymbolRenderer('group', [
            QgsRendererCategory(group, QgsLineSymbol.createSimple({'line_color': color, 'line_width': '0.68'}), group)
            for group, color in COLORS.items()]))
        settings = QgsMapSettings(); settings.setLayers([route_layer, abc, reference, roads, admins, inside, city])
        settings.setDestinationCrs(city.crs()); settings.setOutputSize(QSize(width, height))
        extent = QgsRectangle(extent); extent.scale(1.07); settings.setExtent(extent)
        settings.setBackgroundColor(QColor('white'))
        job = QgsMapRendererParallelJob(settings); job.start(); job.waitForFinished()
        return job.renderedImage(), settings


    def annotate(painter, settings, rows, offset, size):
        xbase, ybase = offset; width, height = size; occupied = []; boxes = []
        painter.setFont(QFont('Arial', 17)); metrics = QFontMetricsF(painter.font())
        for row in rows:
            middle = source_geometries[row['route_id']].interpolate(source_geometries[row['route_id']].length() * .5).asPoint()
            pixel = settings.mapToPixel().transform(middle)
            x, y = pixel.x(), pixel.y(); text = row['first_street']
            boxw = min(360, max(160, metrics.horizontalAdvance(text) + 20)); boxh = 62
            best, score = None, float('inf')
            for radius in [25, 65, 105, 155, 220, 300, 410]:
                for angle in [-45, 45, 135, -135, 0, 90, 180, -90]:
                    radians = math.radians(angle)
                    xx = max(10, min(width - boxw - 10, x + radius * math.cos(radians) - boxw / 2))
                    yy = max(10, min(height - boxh - 10, y + radius * math.sin(radians) - boxh / 2))
                    rect = QRectF(xx, yy, boxw, boxh)
                    overlap = sum(rect.intersected(old).width() * rect.intersected(old).height() for old in occupied if rect.intersects(old))
                    cost = overlap * 10000 + math.hypot(xx + boxw / 2 - x, yy + boxh / 2 - y)
                    if cost < score: best, score = rect, cost
            occupied.append(best); boxes.append((row, x, y, best))
        for row, x, y, rect in boxes:
            painter.setPen(QColor(COLORS[row['group']]))
            painter.drawLine(int(xbase + x), int(ybase + y), int(xbase + rect.center().x()), int(ybase + rect.center().y()))
        for row, x, y, rect in boxes:
            color = QColor(COLORS[row['group']]); painter.setPen(color); painter.setBrush(color)
            painter.drawEllipse(QRectF(xbase + x - 5, ybase + y - 5, 10, 10))
            area = QRectF(xbase + rect.x(), ybase + rect.y(), rect.width(), rect.height())
            painter.fillRect(area, QColor(255, 255, 255, 236)); painter.setPen(color); painter.setFont(QFont('Arial', 18, QFont.Weight.Bold))
            painter.drawText(int(area.x() + 8), int(area.y() + 26), row['route_id'])
            painter.setFont(QFont('Arial', 17)); painter.setPen(QColor('#233843'))
            shortened = QFontMetricsF(painter.font()).elidedText(row['first_street'], Qt.TextElideMode.ElideRight, int(area.width() - 16))
            painter.drawText(int(area.x() + 8), int(area.y() + 53), shortened)


    def static_map(rows, total):
        value = selected if total == 30 else all_routes
        image = QImage(5600, 3800, QImage.Format.Format_ARGB32); image.fill(QColor('white'))
        p = QPainter(image); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor('#203746')); p.setFont(QFont('Arial', 43, QFont.Weight.Bold))
        p.drawText(65, 105, f'{total} TUYẾN ' + ('ĐƯỢC CHỌN' if total == 30 else 'TRONG BỘ ỨNG VIÊN') + ' · LEZ 2030')
        ni = sum(r['group'] == 'inside' for r in rows); no = total - ni
        p.setFont(QFont('Arial', 25)); p.drawText(65, 166, f"{ni} trong LEZ / {no} ngoài LEZ · A {sum(r['sampling_zone']=='A' for r in rows)} / B {sum(r['sampling_zone']=='B' for r in rows)} / C {sum(r['sampling_zone']=='C' for r in rows)} · OSM 01/10/2026")
        p.setFont(QFont('Arial', 26, QFont.Weight.Bold)); p.drawText(70, 240, 'Toàn Hà Nội — tên tuyến ngoài'); p.drawText(2070, 240, 'Phóng to nhóm trong'); p.drawText(3410, 240, 'Mã tuyến — tên đường rút gọn — km')
        main, settings = draw_map(value, city.extent(), 1940, 3190); p.drawImage(55, 265, main)
        annotate(p, settings, [r for r in rows if r['group'] == 'outside'], (55, 265), (1940, 3190))
        inset_extent = QgsRectangle()
        for row in rows:
            if row['group'] == 'inside': inset_extent.combineExtentWith(source_geometries[row['route_id']].boundingBox())
        value.setSubsetString("\"group\" = 'inside'")
        inset, inner_settings = draw_map(value, inset_extent, 1250, 2260); p.drawImage(2060, 265, inset)
        value.setSubsetString('')
        annotate(p, inner_settings, [r for r in rows if r['group'] == 'inside'], (2060, 265), (1250, 2260))
        rowheight = 49 if total == 60 else 98
        for i, row in enumerate(rows):
            y = 320 + i * rowheight
            p.setPen(QColor(COLORS[row['group']])); p.setFont(QFont('Arial', 23, QFont.Weight.Bold))
            p.drawText(3410, y, row['route_id'])
            p.setPen(QColor('#253944')); p.setFont(QFont('Arial', 21))
            text = row['route_name']; limit = 1850
            while QFontMetricsF(p.font()).horizontalAdvance(text) > limit and p.font().pointSize() > 16:
                p.setFont(QFont('Arial', p.font().pointSize() - 1))
            p.drawText(3520, y, text)
            p.setFont(QFont('Arial', 20)); p.drawText(5360, y, f"{row['length_km']:.2f}".replace('.', ','))
        p.setFont(QFont('Arial', 24, QFont.Weight.Bold)); p.setPen(QColor('#203746')); p.drawText(2070, 2660, 'Chú giải')
        for j, (color, text) in enumerate([(COLORS['inside'], f'{ni} tuyến trong phạm vi nghiên cứu'), (COLORS['outside'], f'{no} tuyến ngoài phạm vi nghiên cứu'), ('#e0edf6', 'Nền xanh nhạt: phạm vi lấy mẫu trong')]):
            y = 2730 + j * 76; p.fillRect(2070, y - 29, 50, 32, QColor(color)); p.setPen(QColor('#233843')); p.setFont(QFont('Arial', 22)); p.drawText(2140, y, text)
        p.setFont(QFont('Arial', 21)); p.drawText(2070, 2980, 'Nét đứt: đường bao đối chiếu LEZ 2030')
        p.drawText(2070, 3040, 'Nét tím liền: đường bao ba vùng A/B/C.')
        p.drawText(2070, 3100, 'A: thí điểm LEZ 2027; B: phần LEZ 2030 còn lại.')
        p.drawText(2070, 3160, 'C: ngoài phạm vi LEZ 2030 trong Hà Nội.')
        p.drawText(2070, 3220, 'Bản HTML có đầy đủ chuỗi đường của mỗi tuyến.')
        p.setFont(QFont('Arial', 24)); p.setPen(QColor('#233843'))
        p.drawText(65, 3600, 'A/B/C lấy LEZ làm mốc: A theo thí điểm 2027, B theo phạm vi 2030 trừ A, C ngoài LEZ 2030. Hình học đối chiếu OSM chưa xác minh là GIS chính thức.')
        p.setFont(QFont('Arial', 23)); p.drawText(65, 3660, 'Tên được lấy từ dữ liệu OSM, không tự đặt tên cho phần chưa có tên. Nguồn: OpenStreetMap contributors (ODbL). EPSG:3405.')
        missing = ', '.join(r['route_id'] for r in rows if not r['has_named_street'])
        p.drawText(65, 3720, 'Tuyến chưa có tên đường OSM: ' + (missing or 'không có') + ' · Hình học tuyến giữ nguyên từ bộ dữ liệu đã chọn.')
        p.end(); path = OUTPUT / f'{total}_tuyen_LEZ2030.png'
        if not image.save(str(path), 'PNG'): raise RuntimeError('Failed to save map ' + str(path))
        return path


    data = svg_data()
    template = (Path(__file__).parent / 'route_map_template.html').read_text()
    exports = []
    for total in [30, 60]:
        rows = [r for r in records if r['selected_30']] if total == 30 else records
        expected_zone = {'A':10,'B':8,'C':12} if total == 30 else {'A':20,'B':20,'C':20}
        actual_zone = {z: sum(row['sampling_zone'] == z for row in rows) for z in 'ABC'}
        assert actual_zone == expected_zone
        expected = (18,12) if total == 30 else (40,20)
        actual = (sum(r['group'] == 'inside' for r in rows), sum(r['group'] == 'outside' for r in rows))
        assert actual == expected and len(rows) == total
        payload = dict(data, routes=[r for r in data['routes'] if total == 60 or r['selected_30']], total=total,
                       counts={'inside': actual[0], 'outside': actual[1]}, zone_counts=actual_zone, zone_labels={'A':'A · thí điểm LEZ 2027','B':'B · LEZ 2030 trừ A','C':'C · ngoài LEZ 2030'}, title=f'{total} tuyến ' + ('được chọn' if total == 30 else 'trong bộ ứng viên'),
                       source_snapshot_utc=sampling.get('boundary', {}).get('snapshot_utc', selection['snapshot_utc']))
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
        page = template.replace('__DATA__', encoded).replace('__TITLE__', html.escape(payload['title']))
        html_path = OUTPUT / f'{total}_tuyen_LEZ2030.html'; html_path.write_text(page)
        image_path = static_map(rows, total)
        csv_path = OUTPUT / f'{total}_tuyen_danh_sach.csv'
        with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
            fields = ['route_id', 'sampling_zone', 'group', 'lez2027_group', 'lez2030_group', 'policy_version', 'survey_date', 'lez_status_at_survey', 'stratum_id', 'rc_target', 'length_km', 'route_name', 'street_sequence', 'has_named_street']
            writer = csv.DictWriter(stream, fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
        exports.append({'total': total, 'inside': actual[0], 'outside': actual[1], 'sampling_zone_counts':actual_zone, 'route_ids': [r['route_id'] for r in rows],
                        'routes_without_osm_names': [r['route_id'] for r in rows if not r['has_named_street']],
                        'files': {p.name: file_hash(p) for p in [html_path, image_path, csv_path]}})
    assert before_hashes == {str(p): file_hash(p) for p in protected}, 'Source files were modified'
    manifest = {'created_at': now(), 'source_snapshot_utc': selection['snapshot_utc'], 'crs': 'EPSG:3405',
                'scope': 'LEZ2027_A_LEZ2030_minus_A_B_outside_LEZ2030_C', 'official_gis_verified': False,
                'network_calls': 0, 'source_files_unchanged': True, 'source_hashes': before_hashes,
                'route_geometry_hashes': {r['route_id']: r['geometry_sha256'] for r in records}, 'exports': exports}
    (OUTPUT / 'route_maps_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (OUTPUT / 'README.md').write_text('# Bản đồ bộ tuyến ABC và LEZ 2030\n\n60 ứng viên: 20 A / 20 B / 20 C. Bộ 30: 10 A trong LEZ / 8 B trong LEZ / 12 C ngoài LEZ.\n\nA theo ba khu thí điểm LEZ 2027; B là phạm vi LEZ 2030 trừ A; C ngoài LEZ 2030 trong Hà Nội. Phạm vi toàn Vành đai 1 triển khai 2028–2029, không thay thế mốc 2027. Bản HTML có tên tuyến, đường đi qua, bộ lọc A/B/C và trong/ngoài LEZ; dữ liệu nhúng không gọi API. PNG và CSV cùng lấy hình học từ bộ mới.\n\nPhân loại A/B/C lấy LEZ làm mốc; A và B trong LEZ 2030, C ngoài LEZ 2030. Hình học đối chiếu OSM chưa được xác minh là GIS pháp lý. G1/G4/G5/G6 và C6 chờ khảo sát.\n', encoding='utf-8')
    result = {'status':'exported','maps':exports,'source_files_unchanged':True,'network_calls':0}
    (OUTPUT / 'export_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = _native_export(args.work, args.output)
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__': main()
