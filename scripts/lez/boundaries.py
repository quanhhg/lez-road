"""Prepare research polygons from explicit inputs and report unresolved definitions."""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from .common import (WORK, atomic_bytes, atomic_json, cached_manifest, code_hash,
                     commit_manifest, digest, event, file_hash, input_path, now, relative)


def capture_sources(work=WORK, refresh=False):
    import requests
    work = Path(work)
    registry = json.loads((work / "config/boundary_sources.json").read_text())
    folder = work / "data/raw/legal"
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    with requests.Session() as session:
        session.headers["User-Agent"] = "Hanoi-LEZ-research/0.3 (source archive; sequential)"
        for entry in registry["sources"]:
            destination = folder / (entry["source_id"] + ".html")
            meta = destination.with_suffix(".manifest.json")
            if not refresh and destination.exists() and meta.exists():
                previous = json.loads(meta.read_text())
                if previous.get("sha256") == file_hash(destination) and previous.get("requested_url") == entry["url"]:
                    records.append(previous)
                    continue
            record = dict(entry, requested_url=entry["url"], captured_at=now(), geometry_available=False)
            for attempt in range(2):
                try:
                    response = session.get(entry["url"], timeout=(10, 40))
                    response.raise_for_status()
                    if len(response.content) > 20 * 1024 * 1024:
                        raise ValueError("Source page exceeds the configured 20 MiB limit")
                    atomic_bytes(destination, response.content)
                    record.update(status="captured", final_url=response.url, http_status=response.status_code,
                                  sha256=file_hash(destination), local_file=relative(destination, work))
                    break
                except (requests.RequestException, ValueError) as exc:
                    record.update(status="fetch_failed", error=str(exc))
                    if attempt == 0:
                        time.sleep(2)
            atomic_json(meta, record)
            records.append(record)
            event("sources", "Lưu nguồn ranh giới", source_id=entry["source_id"], status=record["status"])
            time.sleep(1)
    atomic_json(work / "reports/boundaries/source_capture.json", {"sources": records, "recorded_at": now()})
    return records


def prepare(work=WORK, force=False, config_path=None, publish_report=True):
    from .gis import QgsGeometry, QgsWkbTypes, initialize, read_polygon, sink, check_layers
    work = Path(work)
    config_path = input_path(work, config_path) if config_path else work / "config/boundary_project.json"
    config = json.loads(config_path.read_text())
    mapping_path = input_path(work, config["strata_mapping"])
    with mapping_path.open(newline="", encoding="utf-8-sig") as stream:
        mappings = list(csv.DictReader(stream))
    expected = ["V" + str(i) for i in range(1, 6)] + ["N" + str(i) for i in range(1, 11)]
    if len(mappings) != 15 or sorted(r["stratum_id"] for r in mappings) != sorted(expected):
        raise ValueError("The strata table must contain each of V1–V5 and N1–N10 exactly once")
    if any(row.get("domain") != ("inside" if row["stratum_id"].startswith("V") else "outside") for row in mappings):
        raise ValueError("V strata must use the inside domain and N strata the outside domain")
    project = json.loads((work / "data/hanoi_tiles/tile_project.json").read_text())
    crs = project["metric_crs"]
    inputs = {"config": file_hash(config_path), "mapping": file_hash(mapping_path), "crs": crs, "snapshot_utc": project["snapshot_utc"]}
    for definition in [config["hanoi_source"], config["lez_source"], *mappings]:
        p = input_path(work, definition.get("path") or definition.get("geometry_path"))
        if p:
            inputs[relative(p, work)] = file_hash(p) if p.exists() else "missing"
    grid_path = work / "maps/hanoi_tiles/hanoi_download_grid.gpkg"
    inputs[relative(grid_path, work)] = file_hash(grid_path)
    raw = work / "data/hanoi_tiles/data/raw/hanoi_osm_20261001.json"
    manifest_path = work / "data/hanoi_tiles/data/raw/boundary_manifest.json"
    raw_manifest = json.loads(manifest_path.read_text())
    if file_hash(raw) != raw_manifest["response_sha256"]:
        raise ValueError("Original Hanoi boundary hash mismatch")
    inputs[relative(manifest_path, work)] = file_hash(manifest_path)
    fp = digest({"inputs": inputs, "code": code_hash(["common.py", "gis.py", "boundaries.py"])})
    directory = work / "data/processed/boundaries" / fp[:20]
    cached = None if force else cached_manifest(directory, fp)
    if cached:
        if publish_report:
            atomic_json(work / "reports/boundaries/latest_boundary_report.json", cached["report"])
        event("boundaries", "Đọc kết quả ranh giới đã kiểm tra", stage_a_complete=cached["report"]["stage_a_complete"])
        return directory, cached["report"], True
    directory.mkdir(parents=True, exist_ok=True)
    context = initialize(work)
    tolerance = float(config.get("area_tolerance_m2", 1.0))
    hdef = config["hanoi_source"]
    hanoi = read_polygon(input_path(work, hdef["path"]), crs, context, hdef.get("layer"))
    coverage = read_polygon(grid_path, crs, context, "download_tiles")
    uncovered = hanoi.difference(coverage).area()
    problems = []
    if not hdef.get("scope_confirmed"):
        problems.append({"component": "hanoi", "reason": "technical_osm_scope_not_confirmed_for_research"})
    if uncovered > tolerance:
        problems.append({"component": "download_coverage", "reason": "chosen_hanoi_scope_exceeds_download_grid", "uncovered_area_m2": uncovered})
    geometry = {"hanoi": [("hanoi", hanoi, hdef.get("status", "technical_osm"))]}
    lezdef = config["lez_source"]
    lezpath = input_path(work, lezdef.get("path"))
    lez = inside = outside = None
    if not lezpath or not lezpath.exists():
        problems.append({"component": "lez_2030", "reason": "missing_polygon_source_and_research_scope_decision"})
    else:
        try:
            lez = read_polygon(lezpath, crs, context, lezdef.get("layer"))
            inside = hanoi.intersection(lez)
            outside = hanoi.difference(lez)
            if inside.isEmpty() or inside.isNull() or outside.isNull():
                raise ValueError("LEZ has no valid overlap with the Hanoi scope")
            if any(not g.isGeosValid() for g in (inside, outside)):
                raise ValueError("Invalid inside/outside overlay")
            geometry.update(lez_2030=[("lez_2030", lez, lezdef.get("status", "draft"))],
                            inside_lez=[("inside", inside, lezdef.get("status", "draft"))])
            if not outside.isEmpty():
                geometry["outside_lez"] = [("outside", outside, lezdef.get("status", "draft"))]
            if lezdef.get("status") not in {"official", "research_confirmed"} or not lezdef.get("source_id"):
                problems.append({"component": "lez_2030", "reason": "polygon_source_or_methodology_not_confirmed"})
        except ValueError as exc:
            problems.append({"component": "lez_2030", "reason": "invalid_source", "detail": str(exc)})
            inside = outside = None
    strata = []
    for row in mappings:
        code = row["stratum_id"]
        path = input_path(work, row.get("geometry_path"))
        if not path or not path.exists():
            problems.append({"component": code, "reason": "missing_explicit_polygon_definition"})
            continue
        if inside is None:
            problems.append({"component": code, "reason": "waiting_for_lez_polygon"})
            continue
        try:
            values = json.loads(row["selector_values"]) if row.get("selector_values") else None
            g = read_polygon(path, crs, context, row.get("layer") or None, row.get("selector_field") or None, values)
            domain = inside if code.startswith("V") else outside
            g = g.intersection(domain)
            if g.isNull() or g.isEmpty() or g.area() <= tolerance or not g.isGeosValid():
                raise ValueError("The selected stratum has no valid positive area in its domain")
            strata.append((code, g, row.get("status", "draft")))
            if row.get("status") not in {"official", "research_confirmed"} or not row.get("source_id"):
                problems.append({"component": code, "reason": "stratum_definition_not_confirmed"})
        except (ValueError, TypeError) as exc:
            problems.append({"component": code, "reason": "invalid_definition", "detail": str(exc)})
    geometry["strata"] = strata
    qa = {}
    for prefix, domain in (("V", inside), ("N", outside)):
        group = [g for code, g, _ in strata if code.startswith(prefix)]
        if domain is None:
            qa[prefix] = {"available": False}
            continue
        union = QgsGeometry.unaryUnion(group) if group else QgsGeometry()
        missing = domain.difference(union) if group else QgsGeometry(domain)
        overlap = max(0.0, sum(g.area() for g in group) - (union.area() if group else 0.0))
        qa[prefix] = {"available": True, "strata_count": len(group), "missing_area_m2": missing.area(), "overlap_area_m2": overlap}
        if missing.area() > tolerance or overlap > tolerance:
            problems.append({"component": prefix, "reason": "strata_coverage_or_overlap_failed", **qa[prefix]})
        if not missing.isEmpty():
            geometry.setdefault("unassigned_scope", []).append((prefix + "_unassigned", missing, "unresolved"))
    if inside is None:
        geometry["unassigned_scope"] = [("hanoi_unassigned", hanoi, "waiting_for_lez_and_strata")]
    temp = directory / ".zones.building.gpkg"
    temp.unlink(missing_ok=True)
    counts = {}
    columns = [("zone_id", "str"), ("status", "str"), ("area_m2", "float")]
    for layer_name, features in geometry.items():
        with sink(temp, layer_name, columns, QgsWkbTypes.MultiPolygon, crs, context) as output:
            for code, g, status in features:
                g = QgsGeometry(g)
                g.convertToMultiType()
                output.add({"zone_id": code, "status": status, "area_m2": g.area()}, g)
            counts[layer_name] = output.count
    check_layers(temp, counts, crs)
    temp.replace(directory / "zones.gpkg")
    report = {"stage_a_complete": not problems, "snapshot_utc": project["snapshot_utc"], "metric_crs": crs,
              "hanoi_area_m2": hanoi.area(), "hanoi_source_status": hdef.get("status"),
              "grid_uncovered_area_m2": uncovered, "layers": counts, "strata_qa": qa,
              "needs_input": problems, "input_hashes": inputs, "invented_lez_or_strata": False}
    atomic_json(directory / "boundary_report.json", report)
    if publish_report:
        atomic_json(work / "reports/boundaries/latest_boundary_report.json", report)
    commit_manifest(directory, fp, report, ["zones.gpkg", "boundary_report.json"])
    event("boundaries", "Đã kiểm tra ranh giới và liệt kê đầu vào còn thiếu", stage_a_complete=report["stage_a_complete"], unresolved=len(problems))
    return directory, report, False
