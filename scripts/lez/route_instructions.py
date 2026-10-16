"""T2: offline, versioned survey instructions for the selected directed routes.

The controller and exports use the Python standard library. Existing PyQGIS
workers read source geometry and transform coordinates; QGIS is never imported
into the notebook controller. No routing service or measured trip is created.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "lez"

from . import trip_processing as tp
from .common import WORK, atomic_json, digest, file_hash, processing_lock

VERSION = "directed_route_instructions_v1"
REPORT = "reports/routes/latest_route_instructions.json"
GPX_NS = "http://www.topografix.com/GPX/1/1"
NOTICE = ("Lộ trình dự kiến từ OSM; chỉ dẫn chuyển hướng suy ra từ hình học. "
          "Chưa xác minh biển báo, quyền xe máy lưu thông hoặc điểm dừng an toàn. "
          "GPX không phải dữ liệu của chuyến đã đo.")
REASONS = {
    "unnamed_road": "Đoạn chưa có tên OSM; đối chiếu tọa độ và mã đoạn.",
    "junction_review": "Nút có nhiều cung ra trong mạng; kiểm tra nhánh đi và biển báo.",
    "roundabout_review": "Vòng xuyến; đi theo nhánh được đánh dấu, chưa xác nhận số thứ tự lối ra.",
    "uturn_review": "Đổi hướng gần 180 độ; kiểm tra chỗ quay đầu và quyền lưu thông.",
    "sharp_turn_review": "Chuyển hướng gấp; kiểm tra hình học và cách đi tại hiện trường.",
    "start_unverified": "Điểm đầu theo tuyến nguồn; chưa xác minh chỗ dừng an toàn.",
    "end_unverified": "Điểm cuối theo tuyến nguồn; chưa xác minh chỗ dừng an toàn.",
}


def portable(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    return "work/" + path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def configuration(project=WORK, config=None):
    if isinstance(config, dict):
        cfg = json.loads(json.dumps(config))
    else:
        p = tp.resolve(project, config or "config/route_instructions.json")
        cfg = json.loads(p.read_text(encoding="utf-8"))
    if cfg.get("method_version") != VERSION or cfg.get("metric_crs") != "EPSG:3405":
        raise ValueError("Unsupported route-instructions version or source CRS")
    n = cfg.get("expected_route_count")
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise ValueError("expected_route_count must be a positive integer")
    keys = ["bearing_distance_m", "endpoint_tolerance_m", "length_tolerance_m", "coordinate_tolerance_m",
            "straight_angle_deg", "slight_angle_deg", "sharp_angle_deg", "uturn_angle_deg"]
    for k in keys:
        if isinstance(cfg.get(k), bool) or not isinstance(cfg.get(k), (int, float)) or not math.isfinite(cfg[k]) or cfg[k] <= 0:
            raise ValueError("Configuration must be positive and finite: " + k)
    angles = [cfg[k] for k in keys[-4:]]
    if angles != sorted(set(angles)) or angles[-1] >= 180:
        raise ValueError("Turn angle thresholds must be strictly increasing below 180")
    return cfg


def source_inputs(project, cfg, selection_report=None):
    src = tp.route_sources(project, selection_report or cfg["selection_report"])
    walks = json.loads(Path(src["walks"]).read_text(encoding="utf-8"))
    ids = [w["route_id"] for w in walks]
    if (len(ids) != cfg["expected_route_count"] or len(set(ids)) != len(ids)
            or set(ids) != set(src["routes"])):
        raise ValueError("Selected route identifiers are missing, duplicated, or inconsistent")
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", rid) for rid in ids):
        raise ValueError("Route identifiers cannot be used safely as filenames")
    if any(not w.get("arc_ids") for w in walks):
        raise ValueError("An empty selected walk cannot produce survey instructions")
    arc_csv = Path(src["walks"]).parent / "selected_route_arcs.csv"
    if not arc_csv.is_file():
        raise ValueError("Missing ordered source table selected_route_arcs.csv")
    with arc_csv.open(encoding="utf-8-sig", newline="") as f:
        records = list(csv.DictReader(f))
    grouped = defaultdict(list)
    for row in records:
        grouped[row["route_id"]].append(row)
    if set(grouped) != set(ids):
        raise ValueError("Ordered arc table does not cover exactly the selected routes")
    for walk in walks:
        rows = sorted(grouped[walk["route_id"]], key=lambda r: int(r["order"]))
        if ([int(r["order"]) for r in rows] != list(range(len(rows)))
                or [r["arc_id"] for r in rows] != walk["arc_ids"]):
            raise ValueError("Ordered arc table disagrees with walk: " + walk["route_id"])
    src["arc_table"] = str(arc_csv)
    src["hashes"][str(arc_csv)] = file_hash(arc_csv)
    src["ordered_arcs"] = grouped
    src["walk_rows"] = walks
    return src


def preflight(project=WORK, config=None, selection_report=None):
    cfg = configuration(project, config)
    src = source_inputs(project, cfg, selection_report)
    return {"status": "ready", "route_count": len(src["routes"]),
            "directed_arc_occurrences": sum(len(w["arc_ids"]) for w in src["walk_rows"]),
            "routes": sorted(src["routes"]), "snapshot_utc": src["snapshot_utc"],
            "config_sha256": digest(cfg), "network_calls": 0, "source_modified": False}


def road_identity(tags, way_id):
    name = str(tags.get("name:vi") or tags.get("name") or "").strip()
    name = unicodedata.normalize("NFC", re.sub(r"\s+", " ", name))
    ref = unicodedata.normalize("NFC", str(tags.get("ref") or "").strip())
    if name:
        return "name:" + name.casefold(), name, False
    if ref:
        return "ref:" + ref.casefold(), "Đường mang mã " + ref, False
    return "unnamed:" + str(way_id), "Đoạn chưa có tên OSM (way " + str(way_id) + ")", True


def source_attributes(src):
    """Read attributes/topological choices without opening a writable GIS layer."""
    segment_ids = set()
    arc_ids = {aid for w in src["walk_rows"] for aid in w["arc_ids"]}
    db = sqlite3.connect(Path(src["network"]).as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        arcs = {}
        for batch in chunks(sorted(arc_ids)):
            sql = "SELECT arc_id,segment_id,part_id,from_node,to_node,direction,length_m,way_id FROM arcs WHERE arc_id IN (" + ",".join("?" for _ in batch) + ")"
            for row in db.execute(sql, batch):
                arcs[row["arc_id"]] = dict(row); segment_ids.add(row["segment_id"])
        if set(arcs) != arc_ids:
            raise ValueError("Source GeoPackage is missing selected directed arcs")
        tags = {}
        for batch in chunks(sorted(segment_ids)):
            for row in db.execute("SELECT segment_id,tags_json FROM segments WHERE segment_id IN (" + ",".join("?" for _ in batch) + ")", batch):
                tags[row["segment_id"]] = json.loads(row["tags_json"] or "{}")
        wanted_nodes = {a[k] for a in arcs.values() for k in ("from_node", "to_node")}
        outgoing, nodes = defaultdict(list), {}
        for batch in chunks(sorted(wanted_nodes)):
            marks = ",".join("?" for _ in batch)
            for row in db.execute("SELECT arc_id,from_node,to_node FROM arcs WHERE routable=1 AND from_node IN (" + marks + ")", batch):
                outgoing[row["from_node"]].append(dict(row))
            for row in db.execute("SELECT node_id,lon,lat FROM nodes WHERE node_id IN (" + marks + ")", batch):
                nodes[row["node_id"]] = [row["lon"], row["lat"]]
        return arcs, tags, outgoing, nodes
    finally:
        db.close()


def chunks(values, size=400):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def path_length(coords):
    return sum(math.dist(a, b) for a, b in zip(coords, coords[1:]))


def tangent(coords, distance, incoming=False):
    """Look a fixed distance along geometry; ignore repeated zero-length points."""
    points = list(reversed(coords)) if incoming else coords
    origin = points[0]
    remaining = distance
    previous = origin
    for current in points[1:]:
        length = math.dist(previous, current)
        if length == 0:
            continue
        if remaining <= length:
            t = remaining / length
            endpoint = [previous[i] + t * (current[i] - previous[i]) for i in (0, 1)]
            vector = [endpoint[i] - origin[i] for i in (0, 1)]
            break
        remaining -= length; previous = current
    else:
        vector = [points[-1][i] - origin[i] for i in (0, 1)]
    if math.hypot(*vector) < 1e-8:
        # Closed/retraced short geometry can have a zero chord.
        pair = next((p for p in points[1:] if math.dist(p, origin) > 1e-8), None)
        if pair is None:
            raise ValueError("Cannot infer direction from a zero-length geometry")
        vector = [pair[i] - origin[i] for i in (0, 1)]
    return [-v for v in vector] if incoming else vector


def turn_angle(before, after, distance):
    a, b = tangent(before, distance, True), tangent(after, distance)
    return math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))


def maneuver(angle, cfg):
    absolute = abs(angle)
    side = "left" if angle > 0 else "right"
    if absolute <= cfg["straight_angle_deg"]: return "straight"
    if absolute <= cfg["slight_angle_deg"]: return "slight_" + side
    if absolute < cfg["sharp_angle_deg"]: return side
    if absolute < cfg["uturn_angle_deg"]: return "sharp_" + side
    return "uturn"


def compass(coords, distance):
    x, y = tangent(coords, distance)
    bearing = math.degrees(math.atan2(x, y)) % 360
    return ["Bắc", "Đông Bắc", "Đông", "Đông Nam", "Nam", "Tây Nam", "Tây", "Tây Bắc"][int((bearing + 22.5) // 45) % 8]


def instruction(kind, name, heading=None):
    labels = {"straight": "Đi tiếp theo hướng tuyến vào ", "slight_left": "Chếch trái vào ",
              "slight_right": "Chếch phải vào ", "left": "Rẽ trái vào ", "right": "Rẽ phải vào ",
              "sharp_left": "Chuyển hướng gấp sang trái vào ", "sharp_right": "Chuyển hướng gấp sang phải vào ",
              "uturn": "Đổi hướng gần 180 độ theo tuyến vào ",
              "roundabout_enter": "Vào vòng xuyến, theo nhánh tuyến được đánh dấu: ",
              "roundabout_exit": "Ra khỏi vòng xuyến theo nhánh tuyến vào ",
              "roundabout_continue": "Tiếp tục trong vòng xuyến theo "}
    if kind == "start": return "Bắt đầu tại điểm đánh dấu, đi hướng " + heading + " theo " + name + "."
    if kind == "arrive": return "Đến điểm cuối của tuyến dự kiến; vị trí dừng an toàn chưa được xác minh."
    return labels[kind] + name + "."


def build_route(walk, metadata, corridor, attributes, cfg):
    """Partition every source arc occurrence exactly once into ordered steps."""
    arc_meta, tags, outgoing, nodes = attributes
    arcs = []
    expected = walk["arc_ids"]
    if [a["arc_id"] for a in corridor["arcs"]] != expected:
        raise ValueError("Cached geometry has a different directed walk: " + walk["route_id"])
    progress, previous = 0.0, None
    for order, a in enumerate(corridor["arcs"]):
        source = arc_meta[a["arc_id"]]
        coords = a["coordinates"]
        if len(coords) < 2 or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in coords):
            raise ValueError("Invalid coordinates on " + a["arc_id"])
        length = path_length(coords)
        if length <= 0 or abs(length - float(source["length_m"])) > cfg["length_tolerance_m"]:
            raise ValueError("Source arc length mismatch: " + a["arc_id"])
        if (a["from_node"] != source["from_node"] or a["to_node"] != source["to_node"]
                or a["direction"] != source["direction"]):
            raise ValueError("Source arc direction mismatch: " + a["arc_id"])
        if previous and (previous["to_node"] != a["from_node"]
                         or math.dist(previous["coordinates"][-1], coords[0]) > cfg["endpoint_tolerance_m"]):
            raise ValueError("Disconnected source route: " + walk["route_id"])
        road_tags = tags[source["segment_id"]]
        key, name, unnamed = road_identity(road_tags, source["way_id"])
        row = {**a, "order": order, "part_id": source["part_id"], "way_id": source["way_id"],
               "road_key": key, "road_name": name, "unnamed": unnamed, "length_m": length,
               "start_m": progress, "roundabout": road_tags.get("junction") in {"roundabout", "circular"}}
        arcs.append(row); progress += length; previous = row
    if abs(progress - float(metadata["length_m"])) > cfg["length_tolerance_m"]:
        raise ValueError("Route length differs from selected source: " + walk["route_id"])
    steps = []
    for i, arc in enumerate(arcs):
        previous = arcs[i-1] if i else None
        angle = turn_angle(previous["coordinates"], arc["coordinates"], cfg["bearing_distance_m"]) if previous else None
        # Counts are topology candidates, not a claim that every outgoing turn is legal.
        choices = [v for v in outgoing.get(arc["from_node"], [])
                   if not previous or v["to_node"] != previous["from_node"]]
        is_junction = previous is not None and len(choices) > 1
        round_change = previous is not None and previous["roundabout"] != arc["roundabout"]
        split = (not previous or arc["road_key"] != previous["road_key"] or is_junction or round_change
                 or abs(angle) >= cfg["slight_angle_deg"])
        if split:
            flags = []
            if arc["unnamed"]: flags.append("unnamed_road")
            if not previous:
                kind = "start"; flags.append("start_unverified")
            elif arc["roundabout"] or previous["roundabout"]:
                kind = ("roundabout_enter" if not previous["roundabout"] else
                        "roundabout_exit" if not arc["roundabout"] else "roundabout_continue")
                flags.append("roundabout_review")
            else:
                kind = maneuver(angle, cfg)
            if is_junction: flags.append("junction_review")
            if kind == "uturn": flags.append("uturn_review")
            if kind.startswith("sharp_"): flags.append("sharp_turn_review")
            steps.append({"route_id": walk["route_id"], "step_no": len(steps)+1,
                          "maneuver": kind, "instruction": instruction(kind, arc["road_name"],
                          compass(arc["coordinates"], cfg["bearing_distance_m"])),
                          "road_name": arc["road_name"], "start_m": arc["start_m"], "length_m": 0.0,
                          "turn_angle_deg": angle, "start_xy": arc["coordinates"][0],
                          "end_xy": arc["coordinates"][-1], "arc_order_start": i, "arc_order_end": i,
                          "arc_ids": [], "review_flags": flags, "geometry_only": True})
        step = steps[-1]
        step["length_m"] += arc["length_m"]; step["arc_ids"].append(arc["arc_id"])
        step["arc_order_end"] = i; step["end_xy"] = arc["coordinates"][-1]
    steps.append({"route_id": walk["route_id"], "step_no": len(steps)+1, "maneuver": "arrive",
                  "instruction": instruction("arrive", ""), "road_name": arcs[-1]["road_name"],
                  "start_m": progress, "length_m": 0.0, "turn_angle_deg": None,
                  "start_xy": arcs[-1]["coordinates"][-1], "end_xy": arcs[-1]["coordinates"][-1],
                  "arc_order_start": len(arcs), "arc_order_end": len(arcs), "arc_ids": [],
                  "review_flags": ["end_unverified"], "geometry_only": True})
    assert [aid for s in steps for aid in s["arc_ids"]] == expected
    coords = []
    for arc in arcs:
        coords.extend(arc["coordinates"] if not coords else arc["coordinates"][1:])
    return {"route_id": walk["route_id"], "sampling_zone": metadata["sampling_zone"],
            "group": metadata.get("group", walk.get("group")), "policy_version": metadata["policy_version"],
            "route_version": metadata["route_version"], "source_bundle_sha256": metadata["source_bundle_sha256"],
            "length_m": progress, "arcs": arcs, "steps": steps, "coordinates": coords,
            "notice": NOTICE, "field_verified": False}


def add_wgs84(routes, project, temporary, cfg):
    unique = dict.fromkeys(tuple(p) for r in routes for p in r["coordinates"])
    points = [{"source_row": i, "xy": list(p)} for i, p in enumerate(unique)]
    result = tp.qgis_call(project, {"action": "inverse_transform", "metric_crs": cfg["metric_crs"],
                          "points": points, "result": str(temporary / ".wgs84.json")})
    if len(result) != len(points) or [p["source_row"] for p in result] != list(range(len(points))):
        raise ValueError("Coordinate transformation dropped or reordered points")
    mapped = {}
    for p, v in zip(points, result):
        lat, lon = v["latitude"], v["longitude"]
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon < 180:
            raise ValueError("Invalid WGS84 coordinates")
        mapped[tuple(p["xy"])] = [lon, lat]
    for route in routes:
        route["coordinates_wgs84"] = [mapped[tuple(p)] for p in route["coordinates"]]
        for arc in route["arcs"]:
            arc["coordinates_wgs84"] = [mapped[tuple(p)] for p in arc["coordinates"]]
        for step in route["steps"]:
            step["start_wgs84"] = mapped[tuple(step["start_xy"])]
            step["end_wgs84"] = mapped[tuple(step["end_xy"])]
    (temporary / ".wgs84.json").unlink()
    (temporary / ".worker_payload.json").unlink(missing_ok=True)
    return mapped


def check_wgs84_endpoints(routes, source_nodes, cfg):
    maximum = 0.0
    for r in routes:
        for a in r["arcs"]:
            for node, coord in [(a["from_node"], a["coordinates_wgs84"][0]),
                                (a["to_node"], a["coordinates_wgs84"][-1])]:
                known = source_nodes[node]
                delta = tp.haversine((known[1], known[0]), (coord[1], coord[0]))
                maximum = max(maximum, delta)
    if maximum > cfg["coordinate_tolerance_m"]:
        raise ValueError("WGS84 transformation disagrees with source OSM coordinates")
    return maximum


def export_gpx(route, path):
    ET.register_namespace("", GPX_NS)
    def sub(parent, tag, text=None, **attrs):
        e = ET.SubElement(parent, "{" + GPX_NS + "}" + tag, attrs)
        if text is not None: e.text = str(text)
        return e
    root = ET.Element("{" + GPX_NS + "}gpx", version="1.1", creator="work T2 " + VERSION)
    meta = sub(root, "metadata")
    sub(meta, "name", route["route_id"] + " - tuyến khảo sát dự kiến")
    sub(meta, "desc", NOTICE + " Phiên bản tuyến: " + route["route_version"])
    for step in route["steps"]:
        lon, lat = step["start_wgs84"]
        point = sub(root, "wpt", lat=f"{lat:.9f}", lon=f"{lon:.9f}")
        sub(point, "name", route["route_id"] + " - bước " + str(step["step_no"]))
        sub(point, "desc", step["instruction"] + " " + " ".join(REASONS[f] for f in step["review_flags"]))
        sub(point, "type", "planned_survey_instruction")
    track = sub(root, "trk")
    sub(track, "name", route["route_id"])
    sub(track, "desc", NOTICE)
    sub(track, "type", "planned_survey_route")
    segment = sub(track, "trkseg")
    for lon, lat in route["coordinates_wgs84"]:
        sub(segment, "trkpt", lat=f"{lat:.9f}", lon=f"{lon:.9f}")
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def route_svg(route):
    points = route["coordinates"]
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    scale = min(850 / max(xmax-xmin, 1), 500 / max(ymax-ymin, 1))
    def xy(p): return (70 + (p[0]-xmin)*scale, 45 + (ymax-p[1])*scale)
    path = "M" + "L".join(f"{x:.3f},{y:.3f}" for x,y in map(xy,points))
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 620" role="img" aria-label="Sơ đồ lộ trình có hướng">',
             '<style>.map-step text{display:none}.map-step.overview-label text,.map-step.selected text{display:block}</style>',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#087e8b"/></marker></defs>',
             '<rect width="1000" height="620" fill="#f2f6f8"/>',
             '<text x="70" y="28" font-size="18" font-weight="bold">'+html.escape(route["route_id"])+' · Lộ trình dự kiến</text>',
             '<text x="942" y="35" font-size="17">Bắc ↑</text>',
             '<path d="' + path + '" fill="none" stroke="#087e8b" stroke-width="3" stroke-linejoin="round"/>']
    label_every = max(1, math.ceil(len(route["steps"])/18))
    for step in route["steps"]:
        selected = [p for a in route["arcs"][step["arc_order_start"]:step["arc_order_end"]+1]
                    for p in a["coordinates"]] if step["arc_ids"] else []
        if selected:
            shape = "M" + "L".join(f"{x:.3f},{y:.3f}" for x,y in map(xy,selected))
            parts.append(f'<path class="step-path" data-step="{step["step_no"]}" d="{shape}" fill="none" stroke="transparent" stroke-width="6" stroke-linejoin="round"/>')
    # Arrows sampled by travelled distance, preserving a retraced direction.
    every = max(route["length_m"]/20, 100)
    next_arrow, progress = every / 2, 0.0
    for a,b in zip(points,points[1:]):
        length = math.dist(a,b)
        while length and progress + length >= next_arrow:
            t = (next_arrow-progress)/length
            p=[a[i]+t*(b[i]-a[i]) for i in (0,1)]
            half=min(length/2, 9/scale)
            u=[(b[i]-a[i])/length for i in (0,1)]
            x0,y0=xy([p[i]-half*u[i] for i in (0,1)])
            x1,y1=xy([p[i]+half*u[i] for i in (0,1)])
            parts.append(f'<path d="M{x0:.2f},{y0:.2f}L{x1:.2f},{y1:.2f}" stroke="#087e8b" stroke-width="2.5" marker-end="url(#arrow)"/>')
            next_arrow += every
        progress += length
    # Every step is locatable, even when labels at the same junction overlap.
    for step in route["steps"]:
        x,y=xy(step["start_xy"])
        first,last=step["step_no"]==1,step["step_no"]==len(route["steps"])
        label=html.escape(("Đầu " if first else "Cuối " if last else "")+str(step["step_no"]))
        desc=html.escape(step["instruction"])
        color="#147853" if first else "#7b2f9b" if last else "#a44a14" if step["review_flags"] else "#153c50"
        overview = " overview-label" if step["step_no"] in (1,len(route["steps"])) or (step["step_no"]-1)%label_every==0 else ""
        dy=15 if last else -6
        radius=6 if first or last else 4
        parts.append(f'<g class="map-step{overview}" data-step="{step["step_no"]}" tabindex="0"><title>Bước {label}: {desc}</title><circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" fill="{color}" stroke="white"/><text x="{x+7:.2f}" y="{y+dy:.2f}" font-size="11" fill="#153c50">{label}</text></g>')
    # A scale bar in source metric CRS.
    distance = 10 ** math.floor(math.log10(max((xmax-xmin)/5, 1)))
    if distance*5*scale <= 170: distance*=5
    elif distance*2*scale <= 170: distance*=2
    width=distance*scale
    parts.append(f'<path d="M70 575v8m0 -4h{width:.3f}m0 -4v8" fill="none" stroke="#153c50" stroke-width="2"/><text x="70" y="602" font-size="14">{distance:g} m</text>')
    parts.append(f'<text x="380" y="596" font-size="13">{route["length_m"]/1000:.3f} km · Điểm đầu xanh / điểm cuối tím</text>')
    parts.append('<text x="380" y="614" font-size="10">© OpenStreetMap contributors · ODbL · Chưa xác minh thực địa</text>')
    parts.append('</svg>')
    return "".join(parts)


def csv_export(path, rows, fields):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {k: (json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v) for k,v in row.items()}
            # Preserve untrusted OSM text in JSON; spreadsheet exports must not execute it.
            for k,v in flat.items():
                if isinstance(v,str) and v.startswith(("=", "+", "-", "@", "\t", "\r")):
                    flat[k] = "'" + v
            writer.writerow(flat)


def render_exports(routes, destination, source, cfg):
    template = Path(__file__).with_name("route_instructions_template.html").read_text()
    folders = {name: destination/name for name in ["routes", "gpx", "maps"]}
    for p in folders.values(): p.mkdir()
    steps, arc_rows, summaries, reviews = [], [], [], []
    for route in routes:
        rid=route["route_id"]
        svg=route_svg(route); (folders["maps"]/(rid+".svg")).write_text(svg,encoding="utf-8")
        export_gpx(route,folders["gpx"]/(rid+".gpx"))
        route_rows=[]
        for step in route["steps"]:
            lon,lat=step["start_wgs84"]; end_lon,end_lat=step["end_wgs84"]
            row={**step,"longitude":lon,"latitude":lat,"end_longitude":end_lon,"end_latitude":end_lat,
                 "end_m":step["start_m"]+step["length_m"],"review_reasons":[REASONS[f] for f in step["review_flags"]]}
            steps.append(row)
            for flag in step["review_flags"]:
                reviews.append({"route_id":rid,"step_no":step["step_no"],"start_m":step["start_m"],"latitude":lat,"longitude":lon,"flag":flag,"reason":REASONS[flag]})
            note=" ".join(row["review_reasons"])
            route_rows.append('<tr id="step-'+str(step["step_no"])+'" data-step="'+str(step["step_no"])+'"><td>'+str(step["step_no"])+'</td><td><b>'+html.escape(step["instruction"])+'</b><small>'+html.escape(note)+'</small></td><td>'+f'{step["length_m"]:.1f} m<br/><small>Từ {step["start_m"]:.1f} m</small></td><td>'+f'{lat:.7f}<br/>{lon:.7f}'+'</td></tr>')
        start=route["coordinates_wgs84"][0]; end=route["coordinates_wgs84"][-1]
        summary={"route_id":rid,"sampling_zone":route["sampling_zone"],"group":route["group"],
                 "length_m":route["length_m"],"arc_occurrences":len(route["arcs"]),"instruction_count":len(route["steps"]),
                 "review_steps":sum(bool(s["review_flags"]) for s in route["steps"]),
                 "unnamed_length_m":sum(a["length_m"] for a in route["arcs"] if a["unnamed"]),
                 "start_latitude":start[1],"start_longitude":start[0],"end_latitude":end[1],"end_longitude":end[0],
                 "route_version":route["route_version"],"source_bundle_sha256":route["source_bundle_sha256"],"field_verified":False}
        summaries.append(summary)
        for arc in route["arcs"]:
            p,q=arc["coordinates_wgs84"][0],arc["coordinates_wgs84"][-1]
            arc_rows.append({"route_id":rid,**arc,"start_longitude":p[0],"start_latitude":p[1],"end_longitude":q[0],"end_latitude":q[1]})
        replacements={"TITLE":html.escape(rid+" - Hướng dẫn khảo sát"),"ROUTE_ID":rid,"ZONE":html.escape(route["sampling_zone"]),
                      "LENGTH":f'{route["length_m"]/1000:.3f}',"NOTICE":html.escape(NOTICE),"MAP":svg,
                      "ROWS":"".join(route_rows),"COUNT":str(len(route["steps"])),
                      "REVIEW":str(summary["review_steps"]),"VERSION":route["route_version"][:16],
                      "SNAPSHOT":html.escape(source["snapshot_utc"] or "chưa rõ")}
        page=template
        for key,value in replacements.items():page=page.replace("@@"+key+"@@",value)
        (folders["routes"]/(rid+".html")).write_text(page,encoding="utf-8")
    csv_export(destination/"route_summary.csv",summaries,list(summaries[0]))
    csv_export(destination/"route_steps.csv",steps,["route_id","step_no","maneuver","instruction","road_name","start_m","length_m","end_m","turn_angle_deg","latitude","longitude","end_latitude","end_longitude","arc_order_start","arc_order_end","arc_ids","review_flags","review_reasons","geometry_only"])
    csv_export(destination/"route_arcs.csv",arc_rows,["route_id","order","arc_id","part_id","way_id","from_node","to_node","direction","road_name","length_m","start_m","start_latitude","start_longitude","end_latitude","end_longitude","unnamed"])
    csv_export(destination/"review_points.csv",reviews,["route_id","step_no","start_m","latitude","longitude","flag","reason"])
    cards=[]
    for r in summaries:
        rid=r["route_id"]
        cards.append(f'<article data-zone="{r["sampling_zone"]}"><h2><a href="routes/{rid}.html">{rid}</a> <span>Vùng {r["sampling_zone"]}</span></h2><p>{r["length_m"]/1000:.3f} km · {r["instruction_count"]} bước · {r["review_steps"]} bước cần rà soát</p><a href="routes/{rid}.html">Mở hướng dẫn</a> · <a href="gpx/{rid}.gpx" download>GPX</a> · <a href="maps/{rid}.svg">Sơ đồ có hướng</a></article>')
    index='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hướng dẫn 30 tuyến khảo sát Hà Nội</title><style>
body{font:16px/1.6 system-ui,sans-serif;color:#233b48;background:#f2f6f8;margin:0}main{max-width:1150px;margin:auto;padding:30px}h1{color:#153c50}article{background:white;border:1px solid #d2e0e5;border-radius:12px;padding:18px}h2{margin:0}h2 span{font-size:14px;color:#607580}a{color:#087e8b}.notice{background:#fff3d8;padding:15px;border-radius:10px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:15px}nav{margin:22px 0}button{font:inherit;margin:4px;padding:6px 16px;border:1px solid #087e8b;border-radius:6px;background:white;cursor:pointer}button.active{background:#087e8b;color:white}.stats{font-size:20px}small{color:#586d79}</style><main><h1>Hướng dẫn 30 tuyến khảo sát Hà Nội</h1><p class="stats">A10 · B8 · C12 | 18 trong / 12 ngoài LEZ theo thiết kế nghiên cứu</p><p class="notice">'''+html.escape(NOTICE)+'''</p><p><a href="route_summary.csv">Tổng hợp tuyến</a> · <a href="route_steps.csv">Chi tiết các bước</a> · <a href="route_arcs.csv">Chuỗi đoạn đầy đủ</a> · <a href="review_points.csv">Điểm cần rà soát</a> · <a href="gpx_30_routes.zip" download>30 tệp GPX</a></p><nav aria-label="Lọc vùng"><button class="active" data-filter="all">Tất cả</button><button data-filter="A">Vùng A</button><button data-filter="B">Vùng B</button><button data-filter="C">Vùng C</button></nav><div class="grid">'''+''.join(cards)+'''</div><p><small>© OpenStreetMap contributors. Nguồn dữ liệu OSM theo giấy phép ODbL. Các tệp GPX là tuyến dự kiến, không có thời gian đo tại từng điểm.</small></p></main><script>document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('article').forEach(a=>a.hidden=b.dataset.filter!=='all'&&a.dataset.zone!==b.dataset.filter);document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));}));</script></html>'''
    (destination/"index.html").write_text(index,encoding="utf-8")
    with zipfile.ZipFile(destination/"gpx_30_routes.zip","w",zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folders["gpx"].glob("*.gpx")):z.write(p,p.name)
    # Coordinates remain available for independent round-trip validation.
    atomic_json(destination/"route_instructions.json",{"method_version":VERSION,"routes":routes})
    return summaries,steps,reviews


def _validate_bundle(routes, src, summaries, steps, reviews, endpoint_error, directory):
    expected={w["route_id"]:w for w in src["walk_rows"]}
    maximum=0.0
    for r in routes:
        flat=[a for s in r["steps"] for a in s["arc_ids"]]
        if flat!=expected[r["route_id"]]["arc_ids"]:raise ValueError("Export lost source arc occurrences")
        delta=abs(sum(s["length_m"] for s in r["steps"])-r["length_m"]);maximum=max(maximum,delta)
        if delta>1e-6:raise ValueError("Step partition changed route length")
        xml=ET.parse(directory/"gpx"/(r["route_id"]+".gpx")).getroot()
        ns={"g":GPX_NS}
        if xml.tag!="{"+GPX_NS+"}gpx" or xml.get("version")!="1.1":
            raise ValueError("Wrong GPX version or namespace")
        track=xml.findall("g:trk/g:trkseg/g:trkpt",ns)
        if len(track)!=len(r["coordinates_wgs84"]):
            raise ValueError("GPX changed the number of source geometry points")
        for p,(lon,lat) in zip(track,r["coordinates_wgs84"]):
            if max(abs(float(p.get("lon"))-lon),abs(float(p.get("lat"))-lat))>1e-9:
                raise ValueError("GPX coordinates were changed or reordered")
        if xml.findall(".//g:time",ns) or len(xml.findall("g:wpt",ns))!=len(r["steps"]):
            raise ValueError("GPX has measured timestamps or missing instruction points")
    with (directory/"route_arcs.csv").open(encoding="utf-8-sig",newline="") as f:
        emitted=defaultdict(list)
        for row in csv.DictReader(f):emitted[row["route_id"]].append(row["arc_id"])
    if dict(emitted)!={rid:w["arc_ids"] for rid,w in expected.items()}:
        raise ValueError("CSV export changed source arc occurrences")
    with zipfile.ZipFile(directory/"gpx_30_routes.zip") as z:
        if z.testzip() or set(z.namelist())!={r["route_id"]+".gpx" for r in routes}:
            raise ValueError("GPX archive is incomplete or corrupted")
    return {"status":"passed","route_count":len(routes),"arc_occurrences":sum(len(r["arcs"]) for r in routes),
            "instruction_count":len(steps),"review_flag_counts":dict(Counter(r["flag"] for r in reviews)),
            "max_step_length_error_m":maximum,"max_wgs84_endpoint_error_m":endpoint_error,
            "ordered_source_arcs_preserved":True,"source_direction_and_turns_validated":True,
            "gpx_route_count":len(routes),"gpx_xml_validated":True,"gpx_points_match_source_geometry":True,
            "csv_arc_order_validated":True,"zip_crc_validated":True,"no_measured_track_timestamps":True,
            "field_verified":False,"network_calls":0}


def run(project=WORK, *, config=None, output_root=None, selection_report=None, force=False, progress=print):
    project=Path(project).resolve();root=Path(output_root or project).resolve()
    cfg=configuration(project,config);src=source_inputs(project,cfg,selection_report)
    template=Path(__file__).with_name("route_instructions_template.html")
    fingerprint=digest({"version":VERSION,"config":cfg,"sources":src["hashes"],
                        "code":file_hash(__file__),"template":file_hash(template),
                        "geometry_code":file_hash(tp.__file__)})
    destination=root/"data/processed/route_instructions"/fingerprint[:20]
    destination.parent.mkdir(parents=True,exist_ok=True)
    cached=tp.cache_valid(destination,fingerprint)
    if cached:
        report={**cached["report"],"cache_hit":True}
        with processing_lock(root):
            publish_latest(root,destination,report)
        return report
    if destination.exists():raise RuntimeError("Corrupt immutable T2 bundle; preserve it for review: "+str(destination))
    if progress:progress("T2: kiểm chuỗi cung, chiều đi và hình học nguồn.")
    trip_cfg=tp.load_config(project)
    trip_cfg["selection_report"]=selection_report or cfg["selection_report"]
    prepared=tp.prepare(project,config=trip_cfg,output_root=root)
    if not prepared.get("direction_and_turns_validated"):raise ValueError("Source turn validation missing")
    corridors=json.loads((Path(prepared["directory"])/"corridors.json").read_text())
    attributes=source_attributes(src)
    for rows in src["ordered_arcs"].values():
        for row in rows:
            arc=attributes[0][row["arc_id"]]
            if (row["part_id"]!=arc["part_id"] or row["direction"]!=arc["direction"]
                    or abs(float(row["length_m"])-float(arc["length_m"]))>cfg["length_tolerance_m"]):
                raise ValueError("Ordered source table has inconsistent attributes: "+row["arc_id"])
    routes=[build_route(w,src["routes"][w["route_id"]],corridors["routes"][w["route_id"]],attributes,cfg)
            for w in sorted(src["walk_rows"],key=lambda w:w["route_id"])]
    with processing_lock(root):
        # A second controller may have finished while geometry was preparing.
        cached=tp.cache_valid(destination,fingerprint)
        if cached:
            report={**cached["report"],"cache_hit":True};publish_latest(root,destination,report);return report
        temporary=Path(tempfile.mkdtemp(prefix=".t2-",dir=destination.parent))
        try:
            if progress:progress("T2: đổi tọa độ, lập chỉ dẫn và xuất 30 GPX / sơ đồ.")
            add_wgs84(routes,project,temporary,cfg)
            endpoint_error=check_wgs84_endpoints(routes,attributes[3],cfg)
            summaries,steps,reviews=render_exports(routes,temporary,src,cfg)
            qa=_validate_bundle(routes,src,summaries,steps,reviews,endpoint_error,temporary)
            for p,h in src["hashes"].items():
                if file_hash(p)!=h:raise RuntimeError("Source changed during T2 export: "+p)
            atomic_json(temporary/"qa.json",qa)
            paths={"directory":portable(destination,root),"index":portable(destination/"index.html",root),
                   "summary":portable(destination/"route_summary.csv",root),"steps":portable(destination/"route_steps.csv",root),
                   "arcs":portable(destination/"route_arcs.csv",root),"review_points":portable(destination/"review_points.csv",root),
                   "gpx_zip":portable(destination/"gpx_30_routes.zip",root),
                   "sheets":portable(destination/"routes",root),"gpx":portable(destination/"gpx",root),
                   "maps":portable(destination/"maps",root),"qa":portable(destination/"qa.json",root)}
            report={"status":"exported_pending_field_review","method_version":VERSION,"route_count":len(routes),
                    "sampling_zone_counts":dict(Counter(r["sampling_zone"] for r in routes)),
                    "arc_occurrences":qa["arc_occurrences"],"instruction_count":len(steps),
                    "review_step_count":sum(bool(s["review_flags"]) for s in steps),
                    "review_flag_counts":qa["review_flag_counts"],"snapshot_utc":src["snapshot_utc"],
                    "source_bundle_sha256":src["source_bundle_sha256"],
                    "source_selection_report":portable(src["selection"],project),
                    "source_hashes":{portable(p,project):h for p,h in src["hashes"].items()},
                    "structural_validation":"passed","field_verified":False,"source_selection_modified":False,
                    "network_calls":0,"cache_hit":False,"paths":paths}
            atomic_json(temporary/"report.json",report)
            files=[p.relative_to(temporary).as_posix() for p in sorted(temporary.rglob("*")) if p.is_file()]
            tp.publish_directory(temporary,destination,fingerprint,report,files)
            publish_latest(root,destination,report)
        finally:
            if temporary.exists():shutil.rmtree(temporary)
    if progress:progress("T2: đã xuất đủ "+str(len(routes))+" tuyến; xem các điểm cần rà soát trong báo cáo.")
    return report


def publish_latest(root,destination,report):
    # A portable relative symlink lets the whole work directory be moved intact.
    link=root/"maps/route_instructions"
    link.parent.mkdir(parents=True,exist_ok=True)
    if link.exists() and not link.is_symlink():
        raise RuntimeError("Refuse to replace a non-symlink map directory: "+str(link))
    tmp=link.with_name(".route_instructions-"+str(os.getpid()))
    tmp.unlink(missing_ok=True)
    try:
        tmp.symlink_to(os.path.relpath(destination,link.parent),target_is_directory=True)
        os.replace(tmp,link)
    finally:
        tmp.unlink(missing_ok=True)
    atomic_json(root/REPORT,report)


def status(project=WORK, output_root=None):
    root=Path(output_root or project).resolve();path=root/REPORT
    if not path.is_file():return {"status":"not_run"}
    report=json.loads(path.read_text())
    directory=tp.resolve(root,report["paths"]["directory"])
    try:
        manifest=json.loads((directory/"manifest.json").read_text())
        valid=tp.cache_valid(directory,manifest["fingerprint"])
    except (OSError,ValueError,KeyError):valid=None
    return {**report,"cache_valid":bool(valid),"status":report["status"] if valid else "cache_invalid"}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=["check","run","status"])
    p.add_argument("--project",type=Path,default=WORK)
    p.add_argument("--config",type=Path)
    p.add_argument("--output-root",type=Path)
    p.add_argument("--selection-report",type=Path)
    p.add_argument("--force",action="store_true")
    a=p.parse_args()
    if a.command=="check":result=preflight(a.project,a.config,a.selection_report)
    elif a.command=="status":result=status(a.project,a.output_root)
    else:result=run(a.project,config=a.config,output_root=a.output_root,selection_report=a.selection_report,force=a.force)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
