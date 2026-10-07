"""Build physical segments, clipped scope parts, directed arcs and turn rules."""
from __future__ import annotations

import csv
import gzip
import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .access import classify_way, directional_decision, directions, node_decision, restriction_spec
from .common import (WORK, atomic_json, cached_manifest, canonical, code_hash, commit_manifest,
                     digest, event, file_hash, relative)
from .osm_index import open_index


def split_ranges(refs, cut_nodes):
    cuts = [0] + [i for i in range(1, len(refs)-1) if refs[i] in cut_nodes] + [len(refs)-1]
    return list(zip(cuts, cuts[1:]))


def resolve_turn_pairs(spec, incoming, outgoing):
    if not incoming or not outgoing:
        return [], "missing_in_scope_from_or_to_arc"
    value = spec["value"]
    pairs = [(a, b) for a in incoming for b in outgoing]
    same_way = len(spec["from_ways"]) == len(spec["to_ways"]) == 1 and spec["from_ways"] == spec["to_ways"]
    if same_way and value in {"no_u_turn", "only_u_turn"}:
        pairs = [(a, b) for a, b in pairs if a["part_id"] == b["part_id"] and a["from_node"] == b["to_node"]]
    elif same_way and value in {"no_straight_on", "only_straight_on"}:
        pairs = [(a, b) for a, b in pairs if a["part_id"] != b["part_id"]]
    elif any(v > 1 for v in Counter(a["way_id"] for a in incoming).values()) or any(v > 1 for v in Counter(a["way_id"] for a in outgoing).values()):
        return [], "turn_orientation_ambiguous"
    if not pairs:
        return [], "no_matching_turn_pair"
    return pairs, None


def build_network(work, index_dir, index_report, boundary_dir, force=False):
    from .gis import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry,
                      QgsWkbTypes, initialize, read_polygon, sink, check_layers)
    from qgis.core import QgsPointXY
    work = Path(work)
    rules_path = work / "config/access_rules.json"
    rules = json.loads(rules_path.read_text())
    sources = {"index": file_hash(Path(index_dir) / "osm_index.sqlite"), "rules": file_hash(rules_path),
               "index_scope": digest({k:index_report.get(k) for k in ("snapshot_utc", "metric_crs", "selected_tiles", "is_full_scope", "tiles")}),
               "zones": file_hash(Path(boundary_dir) / "zones.gpkg"), "code": code_hash(["common.py", "gis.py", "access.py", "network.py", "graph.py"])}
    fp = digest(sources)
    directory = work / "data/processed/network" / fp[:20]
    cached = None if force else cached_manifest(directory, fp)
    if cached:
        event("network", "Đọc mạng đã kiểm tra", segments=cached["report"]["segments"], routable_arcs=cached["report"]["routable_arcs"])
        return directory, cached["report"], True
    directory.mkdir(parents=True, exist_ok=True)
    context = initialize(work)
    crs = index_report["metric_crs"]
    hanoi = read_polygon(Path(boundary_dir) / "zones.gpkg", crs, context, "hanoi")
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), QgsCoordinateReferenceSystem(crs), context)
    reverse = QgsCoordinateTransform(QgsCoordinateReferenceSystem(crs), QgsCoordinateReferenceSystem("EPSG:4326"), context)
    original = open_index(index_dir)
    coords, node_tags = {}, {}
    for _, payload in original.execute("SELECT id,payload FROM objects WHERE type='node'"):
        obj = json.loads(payload)
        p = transform.transform(QgsPointXY(obj["lon"], obj["lat"]))
        coords[obj["id"]] = (p.x(), p.y(), obj["lon"], obj["lat"])
        if obj.get("tags"):
            node_tags[obj["id"]] = obj["tags"]
    ways, usage, levels = [], Counter(), defaultdict(set)
    for _, payload in original.execute("SELECT id,payload FROM objects WHERE type='way' ORDER BY id"):
        way = json.loads(payload)
        tags = way.get("tags", {})
        if "highway" not in tags:
            continue
        ways.append(way)
        usage.update(way["nodes"])
        for n in way["nodes"][1:-1]:
            levels[n].add((tags.get("layer", "0"), tags.get("bridge", "no"), tags.get("tunnel", "no")))
    controls = {n for n, tags in node_tags.items() if tags.get("barrier") or set(tags.get("highway", "").split(";")) & {"traffic_signals", "stop", "give_way", "crossing"}
                or any(k in tags for k in ("access", "motorcycle", "motor_vehicle", "vehicle")) or any("conditional" in k for k in tags)}
    cut_nodes = {n for n, count in usage.items() if count > 1} | controls
    level_conflicts = {n for n, values in levels.items() if len(values) > 1}
    # A shared interior node with contradictory levels needs evidence before routing.
    level_conflict_ways = {w["id"] for w in ways if any(n in level_conflicts for n in w["nodes"][1:-1])}
    specs = [restriction_spec(json.loads(payload)) for (payload,) in original.execute("SELECT payload FROM objects WHERE type='relation' ORDER BY id") if json.loads(payload).get("tags", {}).get("type") == "restriction"]
    affected = defaultdict(list)
    for spec in specs:
        if spec["status"] == "review_required":
            for member in spec["members"]:
                if member["type"] == "way":
                    affected[member["ref"]].append(f"restriction/{spec['restriction_id']}:{spec['reason']}")
    provenance = dict(original.execute("SELECT id,GROUP_CONCAT(tile_id) FROM object_tiles WHERE type='way' GROUP BY id"))
    original.close()
    tempdb = directory / ".network_tables.building.sqlite"
    tempdb.unlink(missing_ok=True)
    db = sqlite3.connect(tempdb)
    db.row_factory = sqlite3.Row
    db.executescript("""
      CREATE TABLE nodes(node_id TEXT PRIMARY KEY,osm_node_id INTEGER,x REAL,y REAL,lon REAL,lat REAL,artificial INTEGER,tags_json TEXT);
      CREATE TABLE segments(segment_id TEXT PRIMARY KEY,way_id INTEGER,start_index INTEGER,end_index INTEGER,from_node TEXT,to_node TEXT,length_m REAL,scope_length_m REAL,access_status TEXT,rc TEXT,reason TEXT,tags_json TEXT,tile_ids TEXT,wkb BLOB);
      CREATE TABLE scope_parts(part_id TEXT PRIMARY KEY,segment_id TEXT,from_node TEXT,to_node TEXT,length_m REAL,from_measure_m REAL,to_measure_m REAL,access_status TEXT,wkb BLOB);
      CREATE TABLE arcs(arc_id TEXT PRIMARY KEY,part_id TEXT,segment_id TEXT,way_id INTEGER,from_node TEXT,to_node TEXT,direction TEXT,length_m REAL,access_status TEXT,routable INTEGER,reason TEXT,rc TEXT);
      CREATE TABLE restrictions(restriction_id INTEGER PRIMARY KEY,status TEXT,value TEXT,reason TEXT,members_json TEXT,tags_json TEXT);
      CREATE TABLE turn_rules(restriction_id INTEGER,from_arc TEXT,to_arc TEXT,kind TEXT,via_node TEXT,PRIMARY KEY(restriction_id,from_arc,to_arc));
      CREATE TABLE issues(kind TEXT,object_id TEXT,detail TEXT);
      CREATE TABLE controls(control_id INTEGER PRIMARY KEY,x REAL,y REAL,lon REAL,lat REAL,control_type TEXT,access_status TEXT,reason TEXT,on_way INTEGER,tags_json TEXT);
      CREATE INDEX arc_way_to ON arcs(way_id,to_node);
      CREATE INDEX arc_way_from ON arcs(way_id,from_node);
      CREATE INDEX part_segment ON scope_parts(segment_id);
    """)
    def add_node(node_id, p, osm_id=None):
        lonlat = reverse.transform(p)
        db.execute("INSERT OR IGNORE INTO nodes VALUES (?,?,?,?,?,?,?,?)", (node_id, osm_id, p.x(), p.y(), lonlat.x(), lonlat.y(), int(osm_id is None), canonical(node_tags.get(osm_id, {}))))
    def clipped_parts(geom, segment_id, refs):
        length = geom.length()
        if hanoi.contains(geom):
            return [(QgsGeometry(geom), 0.0, length)]
        intersection = geom.intersection(hanoi)
        if intersection.isNull():
            raise ValueError("Scope intersection failed: " + segment_id)
        if intersection.isEmpty():
            return []
        pieces = intersection.asGeometryCollection() if intersection.isMultipart() or intersection.type() == QgsWkbTypes.UnknownGeometry else [intersection]
        result = []
        for piece in pieces:
            if piece.type() != QgsWkbTypes.LineGeometry or piece.length() <= 1e-6:
                continue
            points = piece.asPolyline()
            if not points:
                raise ValueError("Cannot read clipped linestring: " + segment_id)
            start = geom.lineLocatePoint(QgsGeometry.fromPointXY(points[0]))
            end = geom.lineLocatePoint(QgsGeometry.fromPointXY(points[-1]))
            if end < start:
                piece = QgsGeometry.fromPolylineXY(list(reversed(points)))
                start, end = end, start
            if start < 0 or end <= start or abs((end-start)-piece.length()) > max(0.01, piece.length()*1e-6):
                db.execute("INSERT INTO issues VALUES (?,?,?)", ("ambiguous_clip_measure", segment_id, "Scope fragment cannot be mapped unambiguously to the source segment"))
                result.append((piece, None, None))
                continue
            result.append((piece, start, end))
        return sorted(result, key=lambda x: x[1] if x[1] is not None else float("inf"))
    try:
        for n in sorted(controls):
            x,y,lon,lat = coords[n]
            if not hanoi.intersects(QgsGeometry.fromPointXY(QgsPointXY(x,y))):
                continue
            status, reason = node_decision(node_tags[n])
            tags = node_tags[n]
            db.execute("INSERT INTO controls VALUES (?,?,?,?,?,?,?,?,?,?)", (n,x,y,lon,lat,tags.get("barrier") or tags.get("highway", "access"),status,reason,int(n in usage),canonical(tags)))
        for i, way in enumerate(ways, 1):
            tags, way_id = way.get("tags", {}), way["id"]
            base = classify_way(tags, rules)
            allowed_dirs, errors = directions(tags)
            if errors and base["policy_status"] != "excluded":
                base.update(status="review_required", reasons=base["reasons"]+errors,
                            policy_status="review_required", policy_reasons=base["policy_reasons"]+errors)
            if affected[way_id] and base["policy_status"] != "excluded":
                base.update(status="review_required", reasons=base["reasons"]+affected[way_id],
                            policy_status="review_required", policy_reasons=base["policy_reasons"]+affected[way_id])
            if way_id in level_conflict_ways and base["policy_status"] != "excluded":
                base.update(status="review_required", reasons=base["reasons"]+["shared_interior_node_has_conflicting_levels"],
                            policy_status="review_required", policy_reasons=base["policy_reasons"]+["shared_interior_node_has_conflicting_levels"])
            if tags.get("area") == "yes" and base["policy_status"] != "excluded":
                base.update(status="review_required", reasons=base["reasons"]+["area_highway_requires_linear_network_review"],
                            policy_status="review_required", policy_reasons=base["policy_reasons"]+["area_highway_requires_linear_network_review"])
            refs = way["nodes"]
            for start, end in split_ranges(refs, cut_nodes):
                segment_id = f"w{way_id}:{start}:{end}"
                segment_refs = refs[start:end+1]
                points = [QgsPointXY(*coords[n][:2]) for n in segment_refs]
                geom = QgsGeometry.fromPolylineXY(points)
                length = geom.length()
                if length <= 1e-6:
                    db.execute("INSERT INTO issues VALUES (?,?,?)", ("zero_length_segment", segment_id, canonical(segment_refs)))
                    continue
                decision = dict(base, reasons=list(base["reasons"]), policy_reasons=list(base["policy_reasons"]))
                for n in segment_refs:
                    status, reason = node_decision(node_tags.get(n, {}))
                    if status == "excluded" or status == "review_required" and decision["policy_status"] != "excluded":
                        decision.update(status=status)
                        decision["reasons"].append(f"node/{n}:{reason}")
                        decision["policy_status"] = status
                        decision["policy_reasons"].append(f"node/{n}:{reason}")
                decisions = {direction: directional_decision(tags, direction, decision) for direction in allowed_dirs}
                statuses = [d["status"] for d in decisions.values()]
                effective = "provisionally_allowed" if "provisionally_allowed" in statuses else "review_required" if "review_required" in statuses or not statuses else "excluded"
                if decision["policy_status"] == "excluded":
                    effective = "excluded"
                parts = clipped_parts(geom, segment_id, segment_refs)
                if any(a is None for _, a, _ in parts) and effective != "excluded":
                    effective = "review_required"
                    decision["reasons"].append("ambiguous_scope_clip_measure")
                    for access in decisions.values():
                        if access["status"] != "excluded":
                            access.update(status="review_required")
                            access["reasons"].append("ambiguous_scope_clip_measure")
                scope_length = sum(g.length() for g, _, _ in parts)
                db.execute("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (segment_id, way_id, start, end, f"osm/{refs[start]}", f"osm/{refs[end]}", length, scope_length,
                           effective, base["rc"], ";".join(sorted({reason for access in decisions.values() for reason in access["reasons"]} or set(decision["reasons"]))), canonical(tags), provenance.get(way_id, ""), bytes(geom.asWkb())))
                for j, (g, a, b) in enumerate(parts):
                    part_id = segment_id + f":p{j}"
                    endpoints = []
                    for endpoint, (measure, point, osm_id) in enumerate(((a, g.asPolyline()[0], refs[start] if a is not None and abs(a) <= 1e-6 else None),
                                                    (b, g.asPolyline()[-1], refs[end] if b is not None and abs(b-length) <= 1e-6 else None))):
                        nid = f"osm/{osm_id}" if osm_id is not None else f"clip/{segment_id}/{measure:.6f}" if measure is not None else f"clip/{part_id}/endpoint{endpoint}"
                        add_node(nid, point, osm_id)
                        endpoints.append(nid)
                    db.execute("INSERT INTO scope_parts VALUES (?,?,?,?,?,?,?,?,?)", (part_id, segment_id, *endpoints, g.length(), a, b, effective, bytes(g.asWkb())))
                    for direction, access in decisions.items():
                        frm, to = endpoints if direction == "forward" else list(reversed(endpoints))
                        arc_id = part_id + (":F" if direction == "forward" else ":B")
                        db.execute("INSERT INTO arcs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (arc_id, part_id, segment_id, way_id, frm, to, direction, g.length(), access["status"], int(access["status"] == "provisionally_allowed"), ";".join(access["reasons"]), base["rc"]))
            if i % 10000 == 0 or i == len(ways):
                db.commit()
                event("network", "Dựng đoạn và cung có hướng", completed_ways=i, total_ways=len(ways))
        for spec in specs:
            if spec["status"] == "candidate":
                incoming = [dict(r) for way_id in spec["from_ways"] for r in db.execute("SELECT * FROM arcs WHERE way_id=? AND to_node=?", (way_id, f"osm/{spec['via_node']}"))]
                outgoing = [dict(r) for way_id in spec["to_ways"] for r in db.execute("SELECT * FROM arcs WHERE way_id=? AND from_node=?", (way_id, f"osm/{spec['via_node']}"))]
                pairs, error = resolve_turn_pairs(spec, incoming, outgoing)
                if error:
                    spec.update(status="review_required", reason=error)
                else:
                    spec.update(status="resolved", reason="via_node_transition_rules")
                    kind = "only" if spec["value"].startswith("only_") else "no"
                    db.executemany("INSERT INTO turn_rules VALUES (?,?,?,?,?)", [(spec["restriction_id"], a["arc_id"], b["arc_id"], kind, f"osm/{spec['via_node']}") for a, b in pairs])
            if spec["status"] == "review_required":
                for m in spec["members"]:
                    if m["type"] != "way":
                        continue
                    reason = f";restriction/{spec['restriction_id']}:{spec['reason']}"
                    db.execute("UPDATE arcs SET access_status='review_required',routable=0,reason=reason||? WHERE way_id=? AND access_status='provisionally_allowed'", (reason, m["ref"]))
                    db.execute("UPDATE segments SET access_status='review_required',reason=reason||? WHERE way_id=? AND access_status='provisionally_allowed'", (reason, m["ref"]))
                    db.execute("UPDATE scope_parts SET access_status='review_required' WHERE segment_id IN (SELECT segment_id FROM segments WHERE way_id=?) AND access_status='provisionally_allowed'", (m["ref"],))
            db.execute("INSERT INTO restrictions VALUES (?,?,?,?,?,?)", (spec["restriction_id"], spec["status"], spec.get("value", ""), spec["reason"], canonical(spec["members"]), canonical(spec["tags"])))
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Network database integrity failed")
        dangling = db.execute("SELECT COUNT(*) FROM arcs a LEFT JOIN nodes n ON a.from_node=n.node_id LEFT JOIN nodes n2 ON a.to_node=n2.node_id WHERE n.node_id IS NULL OR n2.node_id IS NULL").fetchone()[0]
        bad_turns = db.execute("SELECT COUNT(*) FROM turn_rules t JOIN arcs a ON t.from_arc=a.arc_id JOIN arcs b ON t.to_arc=b.arc_id WHERE a.to_node != b.from_node OR a.to_node != t.via_node").fetchone()[0]
        lengths = db.execute("SELECT COUNT(*) FROM segments WHERE scope_length_m>length_m+0.02 OR length_m<=0").fetchone()[0]
        if dangling or bad_turns or lengths:
            raise RuntimeError(f"Network QA failed: dangling={dangling}, turns={bad_turns}, lengths={lengths}")
        gpkgtemp = directory / ".network.building.gpkg"
        gpkgtemp.unlink(missing_ok=True)
        counts = {}
        kinds = {"segment_id": "str", "part_id": "str", "node_id": "str", "arc_id": "str", "from_arc": "str", "to_arc": "str", "via_node": "str", "segment_id": "str", "from_node": "str", "to_node": "str",
                 "way_id": "int", "osm_node_id": "int", "control_id": "int", "on_way": "bool", "start_index": "int", "end_index": "int", "artificial": "bool", "routable": "bool", "restriction_id": "int"}
        float_fields = {"x", "y", "lon", "lat", "length_m", "scope_length_m", "from_measure_m", "to_measure_m"}
        for table, geometry_type in (("nodes", QgsWkbTypes.Point), ("controls", QgsWkbTypes.Point), ("segments", QgsWkbTypes.LineString), ("scope_parts", QgsWkbTypes.LineString), ("arcs", QgsWkbTypes.NoGeometry), ("restrictions", QgsWkbTypes.NoGeometry), ("turn_rules", QgsWkbTypes.NoGeometry)):
            event("network", "Xuất và kiểm tra lớp mạng", layer=table)
            names = [r[1] for r in db.execute("PRAGMA table_info(" + table + ")") if r[1] != "wkb"]
            columns = [(name, "float" if name in float_fields else kinds.get(name, "str")) for name in names]
            with sink(gpkgtemp, table, columns, geometry_type, crs, context) as output:
                with (directory / (table + ".csv")).open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=names)
                    writer.writeheader()
                    for record in db.execute("SELECT * FROM " + table):
                        row = dict(record)
                        blob = row.pop("wkb", None)
                        if table in {"nodes", "controls"}:
                            g = QgsGeometry.fromPointXY(QgsPointXY(row["x"], row["y"]))
                        elif blob is not None:
                            g = QgsGeometry(); g.fromWkb(blob)
                        else:
                            g = None
                        output.add(row, g)
                        writer.writerow(row)
                counts[table] = output.count
        check_layers(gpkgtemp, counts, crs)
        gpkgtemp.replace(directory / "network.gpkg")
        with (directory / "network_issues.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream);writer.writerow(["kind", "object_id", "detail"])
            writer.writerows(db.execute("SELECT * FROM issues"))
        from .graph import export_graph
        graph_stats = export_graph(db, directory / "motorcycle_graph.json.gz", index_report["snapshot_utc"])
        statuses = dict(db.execute("SELECT access_status,COUNT(*) FROM segments GROUP BY access_status"))
        restrictions = dict(db.execute("SELECT status,COUNT(*) FROM restrictions GROUP BY status"))
        road_stats = [dict(r) for r in db.execute("SELECT access_status,rc,COUNT(*) segment_count,SUM(scope_length_m) scope_length_m FROM segments GROUP BY access_status,rc")]
        report = {"snapshot_utc": index_report["snapshot_utc"], "metric_crs": crs, "selected_tiles": index_report["selected_tiles"],
                  "is_full_scope": index_report["is_full_scope"], "unique_osm_counts": index_report["counts"], "highway_ways": len(ways),
                  **counts, "segment_statuses": statuses, "restriction_statuses": restrictions, "length_by_access_rc": road_stats,
                  "routable_arcs": graph_stats["arcs"], "graph": graph_stats, "dangling_arc_endpoints": dangling,
                  "invalid_turn_rules": bad_turns, "length_failures": lengths,
                  "zero_or_ambiguous_geometry_issues": db.execute("SELECT COUNT(*) FROM issues").fetchone()[0],
                  "interior_node_level_conflicts": len(level_conflicts), "input_hashes": sources,
                  "verified_allowed_segments": 0, "network_status": "provisional_osm_motorcycle_network",
                  "final_legal_network_ready": False, "raw_osm_modified": False,
                  "turn_aware_graph_required": True,
                  "note": "Review-required ways and unresolved turn dependencies are excluded from the exported routing graph. Empty motorcycle tags are not legal verification."}
        db.close()
        tempdb.replace(directory / "network_tables.sqlite")
        atomic_json(directory / "network_report.json", report)
        atomic_json(work / "reports/network/latest_network_report.json", report)
        outputs = ["network.gpkg", "network_tables.sqlite", "motorcycle_graph.json.gz", "network_report.json", "network_issues.csv"] + [name + ".csv" for name in counts]
        commit_manifest(directory, fp, report, outputs)
        event("network", "Đã dựng và kiểm tra mạng xe máy tạm thời", segments=counts["segments"], routable_arcs=graph_stats["arcs"], restrictions=restrictions)
        return directory, report, False
    except BaseException:
        db.close()
        raise
