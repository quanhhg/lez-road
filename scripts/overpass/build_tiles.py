"""Chuẩn bị ô tải Overpass; chạy bằng kernel PyQGIS, không gửi request tải đường."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path

from download_tiles import (
    locked_project_operation, merge_download_progress, persist_tile_state,
)

from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsProject, QgsRectangle,
    QgsVectorFileWriter, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from project_paths import DATA_ROOT, project_file

ROOT = DATA_ROOT
METRIC_CRS = "EPSG:3405"
SIDE_M = 5000
MIN_SIDE_M = 1250
APP = None
CSV_FIELDS = [
    "tile_id", "parent_id", "row", "col", "depth", "side_m", "status",
    "xmin_m", "ymin_m", "xmax_m", "ymax_m", "south", "west", "north", "east",
    "scope_area_km2", "scope_fraction", "snapshot_utc", "query_file", "response_dir",
]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def initialize(root=ROOT):
    global APP
    if QgsApplication.instance() is None:
        QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
        profile = Path(root) / "data" / "qgis_profile"
        profile.mkdir(parents=True, exist_ok=True)
        APP = QgsApplication([], False, str(profile))
        APP.initQgis()
    return QgsProject.instance().transformContext()


def load_boundary(root=ROOT):
    """Ghép bằng OSM node ID; chỉ đọc thành viên outer/inner của ranh thành phố."""
    root = Path(root)
    context = initialize(root)
    manifest = json.loads((root / "data/raw/boundary_manifest.json").read_text())
    raw = root / "data/raw/hanoi_osm_20261001.json"
    if hashlib.sha256(raw.read_bytes()).hexdigest() != manifest["response_sha256"]:
        raise ValueError("SHA-256 của dữ liệu ranh không khớp manifest.")
    payload = json.loads(raw.read_text())
    objects = {(e["type"], e["id"]): e for e in payload["elements"] if "id" in e}
    relation = objects[("relation", manifest["relation_id"])]
    if relation.get("tags", {}).get("wikidata") != "Q1858":
        raise ValueError("Relation không nhận diện là Hà Nội.")

    def assemble(role):
        members = [m for m in relation["members"] if m.get("role") == role]
        if any(m["type"] != "way" for m in members):
            raise ValueError(f"Có thành viên {role} dạng relation; cần xử lý riêng.")
        chains = {m["ref"]: objects[("way", m["ref"])]["nodes"] for m in members}
        if len(chains) != len(members):
            raise ValueError("Có thành viên ranh bị lặp.")
        endpoints = defaultdict(set)
        for way_id, chain in chains.items():
            if len(chain) < 2:
                raise ValueError(f"Way ranh quá ngắn: {way_id}")
            for node_id in (chain[0], chain[-1]):
                endpoints[node_id].add(way_id)
        unused = set(chains)
        rings = []
        while unused:
            first = min(unused)
            ring = list(chains[first])
            unused.remove(first)
            while ring[-1] != ring[0]:
                choices = endpoints[ring[-1]] & unused
                if len(choices) != 1:
                    raise ValueError(f"Ranh hở hoặc nhánh mơ hồ tại node {ring[-1]}: {choices}")
                way_id = choices.pop()
                chain = chains[way_id]
                if chain[0] != ring[-1]:
                    chain = list(reversed(chain))
                ring.extend(chain[1:])
                unused.remove(way_id)
            if len(ring) < 4:
                raise ValueError("Vòng ranh không đủ điểm.")
            rings.append([QgsPointXY(objects[("node", n)]["lon"], objects[("node", n)]["lat"]) for n in ring])
        return rings

    outers, inners = assemble("outer"), assemble("inner")
    if not outers:
        raise ValueError("Không có vòng ranh outer.")
    polygons = [[ring] for ring in outers]
    outer_geoms = [QgsGeometry.fromPolygonXY([ring]) for ring in outers]
    for hole in inners:
        hole_geom = QgsGeometry.fromPolygonXY([hole])
        containers = [i for i, geom in enumerate(outer_geoms) if geom.contains(hole_geom)]
        if not containers:
            raise ValueError("Vòng inner không nằm trong outer.")
        polygons[min(containers, key=lambda i: outer_geoms[i].area())].append(hole)
    geographic = QgsGeometry.fromMultiPolygonXY(polygons)
    if not geographic.isGeosValid():
        raise ValueError("Ranh OSM ghép được nhưng hình học không hợp lệ; không tự sửa ranh.")
    metric = QgsGeometry(geographic)
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                                       QgsCoordinateReferenceSystem(METRIC_CRS), context)
    metric.transform(transform)
    if not metric.isGeosValid():
        raise ValueError("Ranh sau chiếu không hợp lệ.")
    info = dict(manifest)
    info.update(outer_rings=len(outers), inner_rings=len(inners),
                boundary_area_km2=metric.area() / 1e6,
                coordinate_operation=transform.coordinateOperation())
    return geographic, metric, info


def tile_geometry(tile):
    return QgsGeometry.fromRect(QgsRectangle(tile["xmin_m"], tile["ymin_m"],
                                            tile["xmax_m"], tile["ymax_m"]))


def geographic_tile(tile):
    # Densify để bao cả cạnh cong sau biến đổi hệ tọa độ.
    geom = tile_geometry(tile).densifyByDistance(100)
    geom.transform(QgsCoordinateTransform(QgsCoordinateReferenceSystem(METRIC_CRS),
                                         QgsCoordinateReferenceSystem("EPSG:4326"),
                                         QgsProject.instance().transformContext()))
    return geom


def make_tile(tile_id, x, y, side, boundary, snapshot, row, col, parent="", depth=0):
    tile = dict(tile_id=tile_id, parent_id=parent, row=row, col=col, depth=depth,
                side_m=side, status="pending", xmin_m=x, ymin_m=y,
                xmax_m=x + side, ymax_m=y + side, snapshot_utc=snapshot)
    intersection = tile_geometry(tile).intersection(boundary)
    if intersection.isNull():
        raise ValueError(f"Không tính được giao ranh: {tile_id}")
    if intersection.area() <= 1e-6:
        return None
    tile["scope_area_km2"] = intersection.area() / 1e6
    tile["scope_fraction"] = intersection.area() / (side * side)
    bbox = geographic_tile(tile).boundingBox()
    # Làm tròn ra ngoài và thêm ~0.1m: tránh mất điểm do làm tròn số.
    tile.update(south=math.floor(bbox.yMinimum() * 1e6) / 1e6 - 1e-6,
                west=math.floor(bbox.xMinimum() * 1e6) / 1e6 - 1e-6,
                north=math.ceil(bbox.yMaximum() * 1e6) / 1e6 + 1e-6,
                east=math.ceil(bbox.xMaximum() * 1e6) / 1e6 + 1e-6,
                query_file=f"queries/{tile_id}.ql", response_dir=f"data/road_tiles/{tile_id}")
    for key in ("south", "west", "north", "east"):
        tile[key] = round(tile[key], 6)
    return tile


def query_for_tile(tile):
    bbox = ",".join(f"{tile[k]:.6f}" for k in ("south", "west", "north", "east"))
    return f'''[out:json][timeout:180][date:"{tile["snapshot_utc"]}"];
way["highway"]({bbox})->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"]({bbox});
  node["barrier"]({bbox});
);
(._; >>;);
out meta;
out count;
'''


def validate_grid(tiles, boundary):
    active = [t for t in tiles if t["status"] != "split"]
    if not active or len({t["tile_id"] for t in tiles}) != len(tiles):
        raise ValueError("Không có ô hoặc mã ô bị trùng.")
    geometries = [tile_geometry(t) for t in active]
    union = QgsGeometry.unaryUnion(geometries)
    missing = boundary.difference(union)
    if union.isNull() or missing.isNull():
        raise ValueError("Phép union/difference thất bại.")
    missing_area = missing.area()
    overlap = abs(sum(g.area() for g in geometries) - union.area())
    area_error = abs(sum(t["scope_area_km2"] * 1e6 for t in active) - boundary.area())
    bbox_failures = []
    for tile, geom in zip(active, geometries):
        if not geom.isGeosValid() or abs(geom.area() - tile["side_m"] ** 2) > .001:
            raise ValueError(f"Ô không phải hình vuông hợp lệ: {tile['tile_id']}")
        b = geographic_tile(tile).boundingBox()
        if not (tile["west"] <= b.xMinimum() and tile["east"] >= b.xMaximum()
                and tile["south"] <= b.yMinimum() and tile["north"] >= b.yMaximum()):
            bbox_failures.append(tile["tile_id"])
    report = dict(passed=missing_area < .01 and overlap < .01 and area_error < .01 and not bbox_failures,
                  active_tile_count=len(active), history_tile_count=len(tiles),
                  boundary_area_km2=boundary.area() / 1e6,
                  download_squares_area_km2=union.area() / 1e6,
                  uncovered_scope_area_m2=missing_area, projected_square_overlap_area_m2=overlap,
                  scope_area_sum_error_m2=area_error, bbox_containment_failures=bbox_failures,
                  scope_geometry_valid=boundary.isGeosValid(),
                  tolerance_m2=.01,
                  note="Ô tải là hình vuông; bbox WGS84 có thể chồng nhau. Dedupe bằng (type,id).")
    if not report["passed"]:
        raise ValueError(f"Grid QA thất bại: {report}")
    return report


def geojson_feature(geometry, properties):
    return dict(type="Feature", geometry=json.loads(geometry.asJson(12)), properties=properties)


def write_gpkg(root, boundary, active):
    fields = [QgsField("tile_id", QVariant.String), QgsField("parent_id", QVariant.String),
              QgsField("side_m", QVariant.Int), QgsField("status", QVariant.String),
              QgsField("scope_km2", QVariant.Double), QgsField("south", QVariant.Double),
              QgsField("west", QVariant.Double), QgsField("north", QVariant.Double),
              QgsField("east", QVariant.Double), QgsField("snapshot", QVariant.String)]
    layers = []
    for name in ("hanoi_boundary", "download_tiles", "scope_in_tiles"):
        layer = QgsVectorLayer(f"MultiPolygon?crs={METRIC_CRS}", name, "memory")
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        features = []
        records = [None] if name == "hanoi_boundary" else active
        for tile in records:
            geom = QgsGeometry(boundary) if tile is None else tile_geometry(tile)
            if name == "scope_in_tiles":
                geom = geom.intersection(boundary)
            geom.convertToMultiType()
            feature = QgsFeature(layer.fields())
            feature.setGeometry(geom)
            feature.setAttributes(["HANOI", "", 0, "scope", boundary.area()/1e6, None, None, None, None,
                                   active[0]["snapshot_utc"]] if tile is None else
                                  [tile["tile_id"], tile["parent_id"], tile["side_m"], tile["status"],
                                   tile["scope_area_km2"], tile["south"], tile["west"], tile["north"],
                                   tile["east"], tile["snapshot_utc"]])
            features.append(feature)
        ok, _ = layer.dataProvider().addFeatures(features)
        if not ok:
            raise ValueError(f"Không tạo được layer {name}")
        layers.append(layer)
    temp = project_file(root, "hanoi_download_grid.tmp.gpkg")
    temp.unlink(missing_ok=True)
    for i, layer in enumerate(layers):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer.name()
        options.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteFile if i == 0
                                        else QgsVectorFileWriter.CreateOrOverwriteLayer)
        result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(temp),
                                                           QgsProject.instance().transformContext(), options)
        if result[0] != QgsVectorFileWriter.NoError:
            raise ValueError(f"Ghi GPKG thất bại: {result}")
    counts = {}
    for name, expected in (("hanoi_boundary", 1), ("download_tiles", len(active)), ("scope_in_tiles", len(active))):
        check = QgsVectorLayer(f"{temp}|layername={name}", name, "ogr")
        if not check.isValid() or check.featureCount() != expected or check.crs().authid() != METRIC_CRS:
            raise ValueError(f"Đọc lại GPKG không khớp: {name}")
        counts[name] = check.featureCount()
        del check
    temp.replace(project_file(root, "hanoi_download_grid.gpkg"))
    return counts


@locked_project_operation
def export_project(root, geographic, boundary, source, config, tiles):
    root = Path(root)
    tiles = merge_download_progress(root, tiles)
    report = validate_grid(tiles, boundary)
    active = sorted((t for t in tiles if t["status"] != "split"), key=lambda t: t["tile_id"])
    queries = root / "queries"
    queries.mkdir(parents=True, exist_ok=True)
    # Chỉ giữ truy vấn của các ô lá để tránh tải đồng thời cả cha và con.
    active_files = {t["tile_id"] + ".ql" for t in active}
    for path in queries.glob("*.ql"):
        if path.name not in active_files:
            path.unlink()
    for tile in active:
        (root / tile["query_file"]).write_text(query_for_tile(tile), encoding="utf-8")
    persist_tile_state(root, tiles, CSV_FIELDS)
    write_json(root / "tile_project.json", dict(config, boundary_source=source))
    source_props = dict(name="Hà Nội", osm_relation=source["relation_id"], snapshot=config["snapshot_utc"],
                        boundary_status=source["boundary_status"], attribution="© OpenStreetMap contributors")
    write_json(project_file(root, "hanoi_boundary.geojson"), dict(type="FeatureCollection",
               features=[geojson_feature(geographic, source_props)]))
    write_json(project_file(root, "download_tiles.geojson"), dict(type="FeatureCollection",
               features=[geojson_feature(geographic_tile(t), t) for t in active]))
    report["gpkg_readback_counts"] = write_gpkg(root, boundary, active)
    with (root / "tiles.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(active) or len(list(queries.glob("*.ql"))) != len(active):
        raise ValueError("Số dòng CSV hoặc file query không khớp.")
    report["csv_rows"] = len(rows)
    report["query_files"] = len(active)
    report["road_requests_sent"] = 0
    write_json(project_file(root, "qa_report.json"), report)
    # Tọa độ mét thuần JSON để vẽ bản đồ mà không cần QGIS trong tiến trình vẽ.
    write_json(project_file(root, "data/map_geometry.json"), dict(
        crs=METRIC_CRS, boundary=json.loads(boundary.asJson(6)),
        tiles=[dict(tile_id=t["tile_id"], rectangle=[t[k] for k in ("xmin_m", "ymin_m", "xmax_m", "ymax_m")]) for t in active]))
    return report


@locked_project_operation
def build(root=ROOT, side_m=SIDE_M):
    root = Path(root)
    if (root / "tiles_history.json").exists():
        raise FileExistsError("Grid đã có. Dùng verify/split; không ghi đè lịch sử tải.")
    if side_m != SIDE_M:
        raise ValueError("Kế hoạch hiện tại dùng ô gốc 5000m.")
    geographic, boundary, source = load_boundary(root)
    extent = boundary.boundingBox()
    x0 = math.floor(extent.xMinimum() / side_m) * side_m
    y0 = math.floor(extent.yMinimum() / side_m) * side_m
    cols = math.ceil((extent.xMaximum() - x0) / side_m)
    rows = math.ceil((extent.yMaximum() - y0) / side_m)
    config = dict(snapshot_utc=source["snapshot_utc"], metric_crs=METRIC_CRS,
                  root_side_m=side_m, minimum_side_m=MIN_SIDE_M, origin_m=[x0, y0],
                  extent_rows=rows, extent_cols=cols, bbox_order=["south", "west", "north", "east"],
                  endpoint=source["endpoint"], scope="Hanoi technical OSM administrative boundary",
                  selection="positive area intersection with city boundary",
                  grid_is_sampling_strata=False, tile_status_values=["pending", "done", "failed", "heavy", "split"])
    tiles = []
    for row in range(rows):
        for col in range(cols):
            tile = make_tile(f"HN_R{row:03d}_C{col:03d}", x0+col*side_m, y0+row*side_m,
                             side_m, boundary, source["snapshot_utc"], row, col)
            if tile is not None:
                tiles.append(tile)
    return export_project(root, geographic, boundary, source, config, tiles)


@locked_project_operation
def split_tile(tile_id, root=ROOT):
    """Chia một ô chưa tải thành 4 phần; giữ các phần có diện tích trong Hà Nội."""
    root = Path(root)
    tiles = json.loads((root / "tiles_history.json").read_text())
    matches = [t for t in tiles if t["tile_id"] == tile_id]
    if len(matches) != 1:
        raise ValueError(f"Không tìm thấy mã ô duy nhất: {tile_id}")
    parent = matches[0]
    if parent["status"] not in ("pending", "failed", "heavy"):
        raise ValueError(f"Chỉ chia ô pending/failed/heavy; trạng thái hiện tại {parent['status']}")
    half = parent["side_m"] // 2
    if half < MIN_SIDE_M:
        raise ValueError("Đã đạt ô tối thiểu 1250m; xem lại query/server thay vì chia tiếp.")
    geographic, boundary, source = load_boundary(root)
    children = []
    for suffix, dx, dy in (("SW", 0, 0), ("SE", half, 0), ("NW", 0, half), ("NE", half, half)):
        child = make_tile(tile_id + "_" + suffix, parent["xmin_m"]+dx, parent["ymin_m"]+dy,
                          half, boundary, parent["snapshot_utc"], parent["row"], parent["col"],
                          parent=tile_id, depth=parent["depth"]+1)
        if child is not None:
            children.append(child)
    parent["status"] = "split"
    tiles.extend(children)
    config = json.loads((root / "tile_project.json").read_text())
    config.pop("boundary_source", None)
    report = export_project(root, geographic, boundary, source, config, tiles)
    return dict(parent=tile_id, children=[t["tile_id"] for t in children], qa=report)


@locked_project_operation
def verify(root=ROOT):
    root = Path(root)
    _, boundary, _ = load_boundary(root)
    tiles = json.loads((root / "tiles_history.json").read_text())
    return validate_grid(tiles, boundary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "verify", "split"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--tile", help="Mã ô cần chia, ví dụ HN_R010_C010")
    args = parser.parse_args()
    if args.action == "split" and not args.tile:
        parser.error("split cần --tile")
    result = (build(args.root) if args.action == "build" else
              verify(args.root) if args.action == "verify" else split_tile(args.tile, args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
