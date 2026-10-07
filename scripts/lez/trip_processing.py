"""Immutable trip import, QC, route-constrained GPS matching and operating metrics.

Ordinary Python controls CSV/provenance/metrics. Only geometry extraction and CRS
transformation run in the registered PyQGIS worker. No driving-cycle methods.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = "route_constrained_trip_qc_v1"
WORK = Path(__file__).resolve().parents[2] if Path(__file__).parent.name == "lez" else Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def resolve(project, value):
    path = Path(value)
    if path.parts[:1] == ("work",):
        path = Path(*path.parts[1:])
    return path.resolve() if path.is_absolute() else (Path(project) / path).resolve()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
        f.flush(); os.fsync(f.fileno())


def load_config(project=WORK, config=None):
    if isinstance(config, dict):
        cfg = json.loads(json.dumps(config))
    else:
        candidates = [resolve(project, config)] if config else [Path(project) / "config/trip_processing.json", Path(__file__).parent / "config/trip_processing.json"]
        path = next((p for p in candidates if p.is_file()), None)
        if path is None:
            raise ValueError("Missing config/trip_processing.json")
        cfg = json.loads(path.read_text(encoding="utf-8"))
    positive = ["max_gap_s", "max_gps_accuracy_m", "max_speed_kmh", "max_gps_jump_speed_kmh", "max_abs_acceleration_m_s2"]
    for name in positive:
        if not isinstance(cfg.get(name), (int, float)) or not math.isfinite(cfg[name]) or cfg[name] <= 0:
            raise ValueError("Config must be positive and finite: " + name)
    for name in ["idle_speed_kmh", "acceleration_threshold_m_s2", "cruise_abs_acceleration_max_m_s2"]:
        if not isinstance(cfg.get(name), (int, float)) or not math.isfinite(cfg[name]) or cfg[name] < 0:
            raise ValueError("Config must be nonnegative and finite: " + name)
    if cfg["acceleration_threshold_m_s2"] != cfg["cruise_abs_acceleration_max_m_s2"]:
        raise ValueError("Acceleration threshold and cruise bound must be equal for exhaustive states")
    m = cfg["map_matching"]
    for name in ["candidate_radius_m", "grid_cell_size_m", "max_candidates", "continuity_slack_m"]:
        if not isinstance(m.get(name), (int, float)) or m[name] <= 0 or not math.isfinite(m[name]):
            raise ValueError("Invalid map-matching configuration: " + name)
    for name in ["ambiguity_distance_margin_m", "ambiguity_progress_separation_m", "heading_min_displacement_m", "backward_tolerance_m"]:
        if not isinstance(m.get(name), (int, float)) or m[name] < 0 or not math.isfinite(m[name]):
            raise ValueError("Invalid map-matching configuration: " + name)
    if not isinstance(m["max_candidates"], int) or isinstance(m["max_candidates"], bool): raise ValueError("max_candidates must be an integer")
    if not -1 <= m["minimum_heading_cosine"] <= 1: raise ValueError("minimum_heading_cosine must be in [-1,1]")
    for key, value in cfg["accepted_speed_units"].items():
        if not isinstance(value, (int, float)) or value <= 0 or not math.isfinite(value): raise ValueError("Invalid speed-unit factor: " + key)
    if m["metric_crs"] != "EPSG:3405":
        raise ValueError("Current source network requires EPSG:3405")
    ZoneInfo(cfg["measurement_timezone"])
    return cfg


def project_module(project, name):
    """Reuse current project runtime and processing lock without local installs."""
    scripts = str(Path(project) / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module("lez." + name)


@contextmanager
def lock(project, output_root):
    # At deployment output_root == project. Staged checks lock only staged state.
    with project_module(project, "common").processing_lock(output_root):
        yield


def route_sources(project, selection_report=None):
    project = Path(project).resolve()
    latest = resolve(project, selection_report or "reports/selection/latest_selection_30.json")
    selection = json.loads(latest.read_text(encoding="utf-8"))
    directory = resolve(project, selection["paths"]["directory"])
    manifest_path = directory / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        if not manifest.get("complete") or any(file_hash(directory/name) != expected for name,expected in manifest.get("output_hashes",{}).items()):
            raise ValueError("Selected route snapshot failed immutable integrity validation")
    network_report = project / "reports/lez/latest_pipeline.json"
    network = json.loads(network_report.read_text(encoding="utf-8"))
    selected_csv = resolve(project, selection["paths"]["selected_routes"])
    walks = directory / "selected_walks.json"
    # Selection stores the exact graph/network provenance: prefer those paths
    # over a newer unrelated latest pipeline report.
    gated = selection.get("mandatory_gates", {}).get("input_hashes", {})
    graph_names = [p for p in gated if p.endswith("motorcycle_graph.json.gz")]
    network_names = [p for p in gated if p.endswith("/network.gpkg")]
    graph = resolve(project, graph_names[0] if graph_names else network["paths"]["graph"])
    gpkg = resolve(project, network_names[0] if network_names else network["paths"]["network"])
    immutable_report = directory / ("report.json" if (directory / "report.json").is_file() else "qa.json")
    files = [immutable_report if immutable_report.is_file() else latest, selected_csv, walks, graph, gpkg]
    hashes = {str(p): file_hash(p) for p in files}
    for name in graph_names + network_names:
        if hashes[str(resolve(project, name))] != gated[name]:
            raise ValueError("Selection source provenance hash mismatch: " + name)
    rows = read_table(selected_csv, ["route_id", "sampling_zone", "policy_version"])[0]
    metadata = {r["route_id"]: r for r in rows}
    if len(metadata) != len(rows):
        raise ValueError("Duplicate route identifiers in selected route snapshot")
    walk_rows = json.loads(walks.read_text())
    bundle_walk_hash = hashes[str(walks)]
    origin = selection.get("origin_selection_report")
    if origin:
        original = json.loads(resolve(project, origin).read_text())
        origin_walks = resolve(project, original["paths"]["directory"]) / "selected_walks.json"
        origin_gates = original.get("mandatory_gates", {}).get("input_hashes", {})
        for name in graph_names + network_names:
            if origin_gates.get(name) != gated[name]:
                raise ValueError("Field revision changed campaign graph/network provenance")
        bundle_walk_hash = file_hash(origin_walks)
        hashes[str(origin_walks)] = bundle_walk_hash
    bundle = digest({"walks": bundle_walk_hash, "graph": hashes[str(graph)], "network": hashes[str(gpkg)]})
    for walk in walk_rows:
        rid = walk["route_id"]
        if rid not in metadata: raise ValueError("Walk absent from selected metadata: " + rid)
        metadata[rid]["route_version"] = digest({"route_id": rid, "arc_ids": walk["arc_ids"],
            "graph_sha256": hashes[str(graph)], "network_sha256": hashes[str(gpkg)],
            "sampling_zone": metadata[rid]["sampling_zone"], "policy_version": metadata[rid]["policy_version"]})
        metadata[rid]["source_bundle_sha256"] = bundle
    if len(walk_rows) != len(metadata): raise ValueError("Selected walks and metadata count differ")
    return {"selection": str(latest), "walks": str(walks), "graph": str(graph), "network": str(gpkg),
            "selected_routes": str(selected_csv), "hashes": hashes, "routes": metadata,
            "source_bundle_sha256": bundle, "selection_status": selection.get("status"), "snapshot_utc": selection.get("snapshot_utc")}


def read_table(path, required):
    if not Path(path).is_file():
        return [], ["missing_file:" + str(path)]
    try:
        text = Path(path).read_bytes().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        fields = reader.fieldnames or []
        issues = []
        if len(set(fields)) != len(fields):
            issues.append("duplicate_header")
        missing = [f for f in required if f not in fields]
        issues.extend("missing_column:" + f for f in missing)
        rows = []
        for i, row in enumerate(reader, 2):
            overflow = row.pop(None, None)
            row["source_row"] = i
            row["_csv_flags"] = ["extra_csv_fields"] if overflow is not None else []
            if any(v is None for k, v in row.items() if k not in {"source_row", "_csv_flags"}):
                row["_csv_flags"].append("short_csv_row")
            row["_overflow_fields"] = overflow
            rows.append(row)
        return rows, issues
    except (UnicodeDecodeError, csv.Error) as exc:
        return [], ["invalid_csv:" + str(exc)]


def input_inventory(project, cfg, input_dir=None):
    folder = resolve(project, input_dir or cfg["input_directory"])
    files = {"trips": folder / cfg["trips_filename"], "points": folder / cfg["points_filename"]}
    return {k: {"path": str(p), "exists": p.is_file(), "sha256": file_hash(p) if p.is_file() else None} for k, p in files.items()}


def preflight(project=WORK, config=None, input_dir=None):
    cfg = load_config(project, config)
    src = route_sources(project, cfg.get("selection_report"))
    inv = input_inventory(project, cfg, input_dir)
    tr, ti = read_table(inv["trips"]["path"], cfg["required_trip_fields"])
    pt, pi = read_table(inv["points"]["path"], cfg["required_point_fields"])
    schema_errors = [e for e in ti + pi if not e.startswith("missing_file:")]
    return {"status": "schema_errors" if schema_errors else ("awaiting_measurements" if not tr and not pt else "ready_to_import"),
            "method_version": VERSION, "route_count": len(src["routes"]), "routes": sorted(src["routes"]),
            "input_files": inv, "trip_rows": len(tr), "point_rows": len(pt), "schema_errors": schema_errors,
            "missing_input_files": [v["path"] for v in inv.values() if not v["exists"]],
            "config_sha256": digest(cfg), "source_snapshot_utc": src["snapshot_utc"],
            "source_bundle_sha256": src["source_bundle_sha256"],
            "route_contracts": {rid: {k: row[k] for k in ["sampling_zone", "policy_version", "route_version", "source_bundle_sha256"]} for rid, row in src["routes"].items()},
            "measurement_verified": False, "network_calls": 0, "driving_cycle_constructed": False}


def cache_valid(directory, fingerprint):
    try:
        manifest = json.loads((Path(directory) / "manifest.json").read_text())
        return manifest if manifest["complete"] and manifest["fingerprint"] == fingerprint and all(file_hash(Path(directory) / n) == h for n, h in manifest["outputs"].items()) else None
    except (OSError, KeyError, ValueError, TypeError):
        return None


def publish_directory(temporary, destination, fingerprint, report, files):
    """Commit complete new version; never overwrite a corrupted immutable version."""
    temporary, destination = Path(temporary), Path(destination)
    atomic_json(temporary / "manifest.json", {"complete": True, "fingerprint": fingerprint, "finished_at": now(),
        "outputs": {n: file_hash(temporary / n) for n in files}, "report": report})
    if destination.exists():
        raise RuntimeError("Existing immutable version failed integrity validation: " + str(destination))
    os.replace(temporary, destination)


def qgis_call(project, payload):
    spec = project_module(project, "pipeline").kernel_spec()
    env = os.environ.copy(); env.update(spec.get("env", {})); env["PYTHONUNBUFFERED"] = "1"
    path = Path(payload["result"]).parent / ".worker_payload.json"
    atomic_json(path, payload)
    r = subprocess.run([spec["argv"][0], str(Path(__file__).resolve()), "geometry-worker", "--payload", str(path)],
                       env=env, capture_output=True, text=True, timeout=180)
    if r.returncode:
        raise RuntimeError("PyQGIS trip worker failed: " + (r.stderr + r.stdout)[-3500:])
    if not Path(payload["result"]).is_file():
        raise RuntimeError("Trip geometry worker did not write its result")
    return json.loads(Path(payload["result"]).read_text())


def prepare(project=WORK, config=None, output_root=None, force=False):
    """Cache geometry for current selected directed walks, with source hashes."""
    cfg = load_config(project, config); src = route_sources(project, cfg.get("selection_report"))
    root = Path(output_root or project).resolve()
    fingerprint = digest({"code": file_hash(__file__), "sources": src["hashes"], "metric_crs": cfg["map_matching"]["metric_crs"]})
    destination = root / "data/processed/trip_corridors" / fingerprint[:20]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with lock(project, root):
        cached = cache_valid(destination, fingerprint)
        if cached and not force:
            return {**cached["report"], "cache_hit": True, "directory": str(destination), "fingerprint": fingerprint}
        if destination.exists():
            if cached and force:
                return {**cached["report"], "cache_hit": True, "directory": str(destination), "fingerprint": fingerprint}
            raise RuntimeError("Corrupted immutable corridor cache: " + str(destination))
        temporary = Path(tempfile.mkdtemp(prefix=".corridors-", dir=destination.parent))
        try:
            qgis_call(project, {"action": "corridors", "project": str(Path(project).resolve()), "sources": src,
                       "result": str(temporary / "corridors.json"), "metric_crs": cfg["map_matching"]["metric_crs"]})
            corridors = json.loads((temporary / "corridors.json").read_text())
            report = {"status": "prepared", "method_version": VERSION, "route_count": len(corridors["routes"]),
                "directed_arc_count": sum(len(r["arcs"]) for r in corridors["routes"].values()),
                "source_hashes": src["hashes"], "source_snapshot_utc": src["snapshot_utc"], "metric_crs": cfg["map_matching"]["metric_crs"],
                "direction_and_turns_validated": True, "measurement_verified": False, "network_calls": 0}
            atomic_json(temporary / "qa.json", report)
            (temporary / ".worker_payload.json").unlink(missing_ok=True)
            publish_directory(temporary, destination, fingerprint, report, ["corridors.json", "qa.json"])
        finally:
            if temporary.exists(): shutil.rmtree(temporary)
    return {**report, "directory": str(destination), "cache_hit": False, "fingerprint": fingerprint}


def parse_time(text):
    t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("Timestamp must contain UTC offset")
    return t.astimezone(timezone.utc)


def finite_number(value):
    n = float(value)
    if not math.isfinite(n): raise ValueError("Nonfinite number")
    return n


def haversine(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dl = lat2 - lat1; dn = math.radians(b[1] - a[1])
    s = math.sin(dl / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dn / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, s)))


def validate(trips, points, cfg, routes):
    """Keep every source row; errors become flags and validity fields."""
    counts = Counter(r.get("trip_id") for r in trips)
    metadata, trip_rows, point_rows = {}, [], []
    for r in trips:
        flags = list(r.get("_csv_flags", []))
        for f in cfg["required_trip_fields"]:
            if r.get(f) in {None, ""}: flags.append("missing:" + f)
        tid, rid = r.get("trip_id"), r.get("route_id")
        if counts[tid] != 1: flags.append("duplicate_trip_id")
        if rid not in routes: flags.append("unknown_route_id")
        start = end = None
        for key in ["started_at", "ended_at"]:
            try:
                t = parse_time(r.get(key)); start = t if key == "started_at" else start; end = t if key == "ended_at" else end
            except (ValueError, TypeError): flags.append("invalid_" + key)
        if start and end and end <= start: flags.append("invalid_trip_time_range")
        try:
            date = datetime.strptime(str(r.get("measurement_date")), "%Y-%m-%d").date()
            if start and start.astimezone(ZoneInfo(cfg["measurement_timezone"])).date() != date:
                flags.append("measurement_date_mismatch")
        except (ValueError, TypeError): flags.append("invalid_measurement_date")
        if rid in routes:
            expected = routes[rid]
            if r.get("sampling_zone") != expected.get("sampling_zone"): flags.append("sampling_zone_mismatch")
            for field in ["policy_version", "route_version", "source_bundle_sha256"]:
                if r.get(field) != expected.get(field): flags.append(field + "_mismatch")
        if r.get("lez_status_at_measurement") not in cfg["valid_lez_statuses"]: flags.append("invalid_lez_status")
        q = {**r, "_start": start, "_end": end, "flags": sorted(set(flags)), "valid": not flags}
        trip_rows.append(q)
        if tid not in metadata: metadata[tid] = q
    previous, seen_times = {}, defaultdict(set)
    for r in points:
        flags = list(r.get("_csv_flags", [])); tid = r.get("trip_id")
        for f in cfg["required_point_fields"]:
            if r.get(f) in {None, ""}: flags.append("missing:" + f)
        trip = metadata.get(tid)
        if trip is None: flags.append("unknown_trip_id")
        elif not trip["valid"]: flags.append("invalid_trip_metadata")
        t = None; lat = lon = speed = accuracy = None
        try:
            t = parse_time(r.get("timestamp"))
            if t in seen_times[tid]: flags.append("duplicate_timestamp")
            seen_times[tid].add(t)
            if trip and trip["_start"] and trip["_end"] and not trip["_start"] <= t <= trip["_end"]:
                flags.append("outside_trip_time_range")
        except (ValueError, TypeError): flags.append("invalid_timestamp")
        try:
            lat, lon = finite_number(r.get("latitude")), finite_number(r.get("longitude"))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                flags.append("invalid_coordinate"); lat = lon = None
        except (ValueError, TypeError): flags.append("invalid_coordinate")
        unit = str(r.get("speed_unit", "")).strip().lower()
        if unit not in cfg["accepted_speed_units"]: flags.append("invalid_speed_unit")
        try:
            rawspeed = finite_number(r.get("speed"))
            if rawspeed < 0: flags.append("negative_speed")
            if unit in cfg["accepted_speed_units"]:
                speed = rawspeed * cfg["accepted_speed_units"][unit]
                if speed > cfg["max_speed_kmh"]: flags.append("speed_outlier")
        except (ValueError, TypeError): flags.append("invalid_speed")
        if r.get("gps_accuracy_m") not in {None, ""}:
            try:
                accuracy = finite_number(r["gps_accuracy_m"])
                if accuracy < 0: flags.append("invalid_gps_accuracy")
                elif accuracy > cfg["max_gps_accuracy_m"]: flags.append("poor_gps_accuracy")
            except (ValueError, TypeError): flags.append("invalid_gps_accuracy")
        prev = previous.get(tid); dt = distance = acceleration = None
        if t and prev and prev["_time"]:
            dt = (t - prev["_time"]).total_seconds()
            if dt <= 0: flags.append("nonmonotonic_time")
            elif dt > cfg["max_gap_s"]: flags.append("sampling_gap")
            if dt > 0 and lat is not None and lon is not None and prev["_lat"] is not None and prev["_lon"] is not None:
                distance = haversine((prev["_lat"], prev["_lon"]), (lat, lon))
                if distance / dt * 3.6 > cfg["max_gps_jump_speed_kmh"]: flags.append("gps_jump")
            if dt > 0 and speed is not None and prev["speed_kmh"] is not None:
                acceleration = (speed - prev["speed_kmh"]) / 3.6 / dt
                if abs(acceleration) > cfg["max_abs_acceleration_m_s2"]: flags.append("acceleration_outlier")
        hard_gps = {"invalid_coordinate", "poor_gps_accuracy", "invalid_gps_accuracy", "invalid_timestamp", "duplicate_timestamp", "nonmonotonic_time", "gps_jump", "outside_trip_time_range", "unknown_trip_id", "invalid_trip_metadata", "extra_csv_fields", "short_csv_row"}
        hard_speed = {"negative_speed", "speed_outlier", "invalid_speed", "invalid_speed_unit", "invalid_timestamp", "duplicate_timestamp", "nonmonotonic_time", "outside_trip_time_range", "unknown_trip_id", "invalid_trip_metadata", "extra_csv_fields", "short_csv_row"}
        q = {**r, "flags": sorted(set(flags)), "valid": not flags, "_time": t, "_lat": lat, "_lon": lon,
             "speed_kmh": speed, "gps_accuracy_m_normalized": accuracy,
             "gps_valid": not hard_gps.intersection(flags), "speed_valid": not hard_speed.intersection(flags),
             "interval_s": dt, "gps_interval_distance_m": distance, "acceleration_m_s2": acceleration,
             "gps_interval_valid": bool(prev and dt is not None and 0 < dt <= cfg["max_gap_s"] and prev["gps_valid"] and not hard_gps.intersection(flags)),
             "speed_interval_valid": bool(prev and dt is not None and 0 < dt <= cfg["max_gap_s"] and prev["speed_valid"] and not hard_speed.intersection(flags) and "acceleration_outlier" not in flags)}
        # Gap is an interval-level error: its endpoint can start a fresh valid interval.
        point_rows.append(q); previous[tid] = q
    return trip_rows, point_rows


class CorridorIndex:
    """Bounded route segments in directed traversal order, never an OSM layer guess."""
    def __init__(self, corridor, cfg):
        self.cfg = cfg; self.grid = defaultdict(list); self.segments = []
        cell = cfg["grid_cell_size_m"]
        for arc in corridor["arcs"]:
            progress = arc["start_m"]
            for a, b in zip(arc["coordinates"], arc["coordinates"][1:]):
                length = math.dist(a, b)
                if length <= 0: continue
                i = len(self.segments)
                self.segments.append({"a": a, "b": b, "length": length, "start_m": progress,
                    "arc_id": arc["arc_id"], "arc_order": arc["order"]})
                for x in range(math.floor(min(a[0], b[0]) / cell), math.floor(max(a[0], b[0]) / cell) + 1):
                    for y in range(math.floor(min(a[1], b[1]) / cell), math.floor(max(a[1], b[1]) / cell) + 1):
                        self.grid[x, y].append(i)
                progress += length

    def candidates(self, p):
        radius = self.cfg["candidate_radius_m"]; cell = self.cfg["grid_cell_size_m"]
        ids = set()
        for x in range(math.floor((p[0] - radius) / cell), math.floor((p[0] + radius) / cell) + 1):
            for y in range(math.floor((p[1] - radius) / cell), math.floor((p[1] + radius) / cell) + 1):
                ids.update(self.grid.get((x, y), []))
        values = []
        for i in ids:
            s = self.segments[i]; a, b = s["a"], s["b"]
            vx, vy = b[0] - a[0], b[1] - a[1]
            f = max(0, min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / s["length"] ** 2))
            residual = math.hypot(p[0] - a[0] - f * vx, p[1] - a[1] - f * vy)
            if residual <= radius:
                values.append({**s, "residual_m": residual, "progress_m": s["start_m"] + f * s["length"],
                               "dx": vx / s["length"], "dy": vy / s["length"]})
        values.sort(key=lambda x: (x["residual_m"], x["progress_m"], x["arc_id"]))
        # Retain the cap count before slicing so ambiguity cannot vanish silently.
        return values[:int(self.cfg["max_candidates"])], len(values) > int(self.cfg["max_candidates"])


def match_points(points, trips, corridors, cfg):
    settings = cfg["map_matching"]
    trip_routes = {t["trip_id"]: t.get("route_id") for t in trips}
    indices = {r: CorridorIndex(c, settings) for r, c in corridors["routes"].items()}
    previous_gps, previous_match = {}, {}
    output = []
    for p in points:
        tid = p.get("trip_id"); rid = trip_routes.get(tid)
        result = {"match_status": "unknown_bad_gps", "match_arc_id": None, "match_arc_order": None,
            "match_progress_m": None, "route_deviation_m": None, "match_confidence": None, "match_flags": []}
        xy = p.get("_xy")
        if p["gps_valid"] and xy is not None:
            if rid not in indices:
                result["match_status"] = "unknown_route"
            else:
                candidates, capped = indices[rid].candidates(xy)
                if capped: result["match_flags"].append("candidate_limit_reached")
                prior_gps = previous_gps.get(tid); heading = None
                if prior_gps and p["gps_interval_valid"]:
                    hx, hy = xy[0] - prior_gps["xy"][0], xy[1] - prior_gps["xy"][1]
                    movement = math.hypot(hx, hy)
                    if movement >= settings["heading_min_displacement_m"]: heading = hx / movement, hy / movement
                if not candidates:
                    result["match_status"] = "off_route"
                    result["match_flags"].append("beyond_candidate_radius")
                else:
                    result["route_deviation_m"] = candidates[0]["residual_m"]
                    directed = [c for c in candidates if heading is None or c["dx"] * heading[0] + c["dy"] * heading[1] >= settings["minimum_heading_cosine"]]
                    prior_match = previous_match.get(tid) if p["gps_interval_valid"] else None
                    if not directed:
                        result["match_status"] = "opposite_direction"
                    else:
                        possible = directed
                        if prior_match:
                            upper = cfg["max_speed_kmh"] / 3.6 * p["interval_s"] + settings["continuity_slack_m"]
                            possible = [c for c in directed if -settings["backward_tolerance_m"] <= c["progress_m"] - prior_match["progress_m"] <= upper]
                        if not possible:
                            result["match_status"] = "continuity_unresolved"
                        else:
                            chosen = min(possible, key=lambda c: c["residual_m"] + (0.05 * abs(c["progress_m"] - prior_match["progress_m"] - p.get("gps_interval_distance_m", 0)) if prior_match else 0))
                            ambiguous = capped or any(c["residual_m"] <= chosen["residual_m"] + settings["ambiguity_distance_margin_m"] and abs(c["progress_m"] - chosen["progress_m"]) >= settings["ambiguity_progress_separation_m"] for c in possible)
                            result.update(match_status="ambiguous" if ambiguous else "matched", match_arc_id=chosen["arc_id"],
                                match_arc_order=chosen["arc_order"], match_progress_m=chosen["progress_m"], route_deviation_m=chosen["residual_m"],
                                match_confidence=0.0 if ambiguous else max(0, 1 - chosen["residual_m"] / settings["candidate_radius_m"]))
                            if heading is None: result["match_flags"].append("heading_unknown")
                            if ambiguous: result["match_flags"].append("multiple_corridor_locations")
                            if result["match_status"] == "matched": previous_match[tid] = chosen
                previous_gps[tid] = {"xy": xy}
        if result["match_status"] != "matched": previous_match.pop(tid, None)
        if not p["gps_valid"]: previous_gps.pop(tid, None)
        output.append({**p, **result})
    return output


def operating_metrics(trips, points, cfg):
    """Interval integrals exclude gaps/errors; denominators explicitly exported."""
    grouped = defaultdict(list)
    for p in points: grouped[p.get("trip_id")].append(p)
    results = []
    for t in trips:
        rows = grouped.get(t.get("trip_id"), []); previous = None
        gps_distance = speed_distance = gps_time = speed_time = idle = moving = accel = decel = cruise = matched_distance = matched_time = 0.0
        accelerations, speeds, deviations = [], [], []
        interval_count = 0
        for p in rows:
            dt = p["interval_s"]
            if p["speed_valid"] and p["speed_kmh"] is not None: speeds.append(p["speed_kmh"])
            if p.get("route_deviation_m") is not None: deviations.append(p["route_deviation_m"])
            if p["gps_interval_valid"] and p["gps_interval_distance_m"] is not None:
                gps_distance += p["gps_interval_distance_m"]; gps_time += dt
            if p["speed_interval_valid"] and previous:
                speed_time += dt; interval_count += 1
                v = (previous["speed_kmh"] + p["speed_kmh"]) / 2
                speed_distance += v / 3.6 * dt
                # State uses interval mean speed; half-idle transitions remain moving.
                if v <= cfg["idle_speed_kmh"]: idle += dt
                else:
                    moving += dt
                    a = p["acceleration_m_s2"]
                    if a > cfg["acceleration_threshold_m_s2"]: accel += dt
                    elif a < -cfg["acceleration_threshold_m_s2"]: decel += dt
                    else: cruise += dt
                accelerations.append(p["acceleration_m_s2"])
            if previous and p["gps_interval_valid"] and p.get("match_status") == "matched" and previous.get("match_status") == "matched":
                delta = p["match_progress_m"] - previous["match_progress_m"]
                if delta >= 0: matched_distance += delta; matched_time += dt
            previous = p
        duration = (t["_end"] - t["_start"]).total_seconds() if t["_start"] and t["_end"] and t["_end"] > t["_start"] else None
        observed_span = (rows[-1]["_time"] - rows[0]["_time"]).total_seconds() if rows and rows[-1]["_time"] and rows[0]["_time"] and rows[-1]["_time"] >= rows[0]["_time"] else None
        result = {"trip_id": t.get("trip_id"), "route_id": t.get("route_id"), "metadata_valid": t["valid"],
            "sampling_zone": t.get("sampling_zone"), "policy_version": t.get("policy_version"), "measurement_date": t.get("measurement_date"),
            "time_block": t.get("time_block"), "lez_status_at_measurement": t.get("lez_status_at_measurement"),
            "route_version": t.get("route_version"), "source_bundle_sha256": t.get("source_bundle_sha256"),
            "point_count": len(rows), "valid_speed_point_count": len(speeds), "valid_gps_point_count": sum(p["gps_valid"] for p in rows),
            "declared_duration_s": duration, "observed_span_s": observed_span,
            "speed_valid_duration_s": speed_time, "gps_valid_duration_s": gps_time, "valid_speed_interval_count": interval_count,
            "speed_duration_coverage_fraction": speed_time / duration if duration else None,
            "gps_duration_coverage_fraction": gps_time / duration if duration else None,
            "gps_distance_m": gps_distance if gps_time else None, "speed_integrated_distance_m": speed_distance if speed_time else None,
            "time_weighted_mean_speed_kmh": speed_distance / speed_time * 3.6 if speed_time else None,
            "mean_moving_speed_kmh": speed_distance / moving * 3.6 if moving else None,
            "maximum_valid_speed_kmh": max(speeds) if speeds else None,
            "idle_time_s": idle, "moving_time_s": moving, "idle_fraction_valid_speed_time": idle / speed_time if speed_time else None,
            "acceleration_time_s": accel, "deceleration_time_s": decel, "cruise_time_s": cruise,
            "mean_acceleration_m_s2": sum(a for a in accelerations if a > cfg["acceleration_threshold_m_s2"]) / sum(a > cfg["acceleration_threshold_m_s2"] for a in accelerations) if any(a > cfg["acceleration_threshold_m_s2"] for a in accelerations) else None,
            "mean_deceleration_m_s2": sum(a for a in accelerations if a < -cfg["acceleration_threshold_m_s2"]) / sum(a < -cfg["acceleration_threshold_m_s2"] for a in accelerations) if any(a < -cfg["acceleration_threshold_m_s2"] for a in accelerations) else None,
            "maximum_abs_acceleration_m_s2": max(map(abs, accelerations)) if accelerations else None,
            "matched_distance_m": matched_distance if matched_time else None, "matched_duration_s": matched_time,
            "match_status_counts": dict(Counter(p.get("match_status", "not_requested") for p in rows)),
            "maximum_candidate_deviation_m": max(deviations) if deviations else None,
            "flagged_point_count": sum(bool(p["flags"]) for p in rows)}
        # Moving mean excludes the speed-integral contribution of idle intervals.
        idle_distance = 0.0
        for a, b in zip(rows, rows[1:]):
            if b["speed_interval_valid"] and (a["speed_kmh"] + b["speed_kmh"]) / 2 <= cfg["idle_speed_kmh"]:
                idle_distance += (a["speed_kmh"] + b["speed_kmh"]) / 2 / 3.6 * b["interval_s"]
        result["mean_moving_speed_kmh"] = (speed_distance - idle_distance) / moving * 3.6 if moving else None
        results.append(result)
    return results


def operating_summary(metrics):
    """Descriptive time-weighted totals; no city-wide sampling inference."""
    buckets = defaultdict(list)
    for row in metrics:
        buckets[("route", row.get("route_id"), "")].append(row)
        buckets[("zone", row.get("sampling_zone"), "")].append(row)
        buckets[("zone_time_block", row.get("sampling_zone"), row.get("time_block"))].append(row)
    result = []
    for (kind, group, block), records in sorted(buckets.items(), key=lambda x:str(x[0])):
        valid = [r for r in records if r["metadata_valid"]]
        def total(name): return sum(float(r.get(name) or 0) for r in valid)
        speed_time, declared = total("speed_valid_duration_s"), total("declared_duration_s")
        distance = total("speed_integrated_distance_m")
        result.append({"aggregation":kind,"group":group,"time_block":block,
            "trip_rows":len(records),"metadata_valid_trips":len(valid),
            "trips_with_valid_speed_intervals":sum(r["speed_valid_duration_s"]>0 for r in valid),
            "excluded_metadata_trips":len(records)-len(valid),
            "declared_duration_s":declared,"speed_valid_duration_s":speed_time,
            "speed_duration_coverage_fraction":speed_time/declared if declared else None,
            "speed_integrated_distance_m":distance if speed_time else None,
            "time_weighted_mean_speed_kmh":distance/speed_time*3.6 if speed_time else None,
            "idle_fraction_valid_speed_time":total("idle_time_s")/speed_time if speed_time else None,
            "acceleration_fraction_valid_speed_time":total("acceleration_time_s")/speed_time if speed_time else None,
            "deceleration_fraction_valid_speed_time":total("deceleration_time_s")/speed_time if speed_time else None,
            "cruise_fraction_valid_speed_time":total("cruise_time_s")/speed_time if speed_time else None,
            "gps_distance_m":total("gps_distance_m") if total("gps_valid_duration_s") else None,
            "matched_distance_m":total("matched_distance_m") if total("matched_duration_s") else None,
            "declared_duration_denominator":"metadata_valid_trips_only; all declared time including gaps",
            "interpretation":"descriptive_valid_intervals_only; not representative city mean"})
    return result


def public_record(record):
    return {k: v for k, v in record.items() if not k.startswith("_")}


def status(project=WORK, output_root=None, demo=False):
    mode = "demo" if demo else "real"
    path = Path(output_root or project) / f"reports/trips/latest_{mode}.json"
    return json.loads(path.read_text()) if path.is_file() else {"status": "not_run", "is_test_data": demo}


def run(project=WORK, config=None, input_dir=None, output_root=None, demo=False):
    cfg = load_config(project, config); src = route_sources(project, cfg.get("selection_report"))
    root = Path(output_root or project).resolve(); mode = "demo" if demo else "real"
    inv = input_inventory(project, cfg, input_dir)
    trips, trip_errors = read_table(inv["trips"]["path"], cfg["required_trip_fields"])
    points, point_errors = read_table(inv["points"]["path"], cfg["required_point_fields"])
    report_path = root / f"reports/trips/latest_{mode}.json"
    if not trips and not points and not [e for e in trip_errors + point_errors if not e.startswith("missing_file:")]:
        report = {"status": "awaiting_measurements", "is_test_data": demo, "measurement_verified": False,
            "trip_count": 0, "point_count": 0, "route_count": len(src["routes"]), "input_files": inv,
            "source_hashes": src["hashes"], "config": cfg, "recorded_at": now(), "network_calls": 0,
            "driving_cycle_constructed": False}
        with lock(project, root): atomic_json(report_path, report)
        return report
    fixture_provenance = Path(inv["trips"]["path"]).parent / "fixture_provenance.json"
    is_fixture = any(any(part in {"fixtures", "demo"} or part.endswith("_demo") for part in Path(v["path"]).parts) for v in inv.values())
    if fixture_provenance.is_file():
        is_fixture = is_fixture or json.loads(fixture_provenance.read_text()).get("is_test_data", False)
    is_fixture = is_fixture or any(str(r.get("is_test_data", "")).lower() in {"true", "1"} for r in trips + points)
    if not demo and is_fixture:
        raise ValueError("Fixture/demo data require --demo; cannot enter real measurement storage")
    fingerprint = digest({"code": file_hash(__file__), "inputs": inv, "config": cfg, "sources": src["hashes"], "is_test_data": demo})
    destination = root / f"data/processed/trip_processing/{mode}" / fingerprint[:20]
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Raw provenance is independent of processed version/config.
    rawfingerprint = digest({"inputs": inv, "is_test_data": demo})
    rawdirectory = root / f"data/raw/measurements/{mode}" / rawfingerprint[:20]
    with lock(project, root):
        cached = cache_valid(destination, fingerprint)
        if cached:
            if not cache_valid(rawdirectory, rawfingerprint):
                raise RuntimeError("Immutable raw copy failed integrity validation")
            atomic_json(report_path, {**cached["report"], "cache_hit": True})
            return {**cached["report"], "cache_hit": True}
        if destination.exists(): raise RuntimeError("Corrupted immutable processed version: " + str(destination))
        if not rawdirectory.exists():
            rawdirectory.parent.mkdir(parents=True, exist_ok=True)
            temporary_raw = Path(tempfile.mkdtemp(prefix=".raw-", dir=rawdirectory.parent))
            try:
                files = []
                for label, item in inv.items():
                    if item["exists"]:
                        name = label + ".csv"; shutil.copyfile(item["path"], temporary_raw / name); files.append(name)
                        if file_hash(temporary_raw / name) != item["sha256"]: raise RuntimeError("Input changed during import: " + item["path"])
                atomic_json(temporary_raw / "provenance.json", {"is_test_data": demo, "source_files": inv, "imported_at": now()})
                files.append("provenance.json")
                publish_directory(temporary_raw, rawdirectory, rawfingerprint, {"is_test_data": demo}, files)
            finally:
                if temporary_raw.exists(): shutil.rmtree(temporary_raw)
        elif not cache_valid(rawdirectory, rawfingerprint):
            raise RuntimeError("Immutable raw copy failed integrity validation")
        # Parse only the archived byte-identical copy. Later edits in incoming
        # cannot change the records associated with this immutable version.
        trips, trip_errors = read_table(rawdirectory / "trips.csv", cfg["required_trip_fields"])
        points, point_errors = read_table(rawdirectory / "points.csv", cfg["required_point_fields"])
    # Geometry prepares under its own common processing lock.
    corridors = None; prepared = None
    if points and cfg["map_matching"]["enabled"] and not trip_errors and not point_errors:
        prepared = prepare(project, config, root)
        corridors = json.loads((Path(prepared["directory"]) / "corridors.json").read_text())
    with lock(project, root):
        # Another run may have completed while geometry was preparing.
        cached = cache_valid(destination, fingerprint)
        if cached:
            if not cache_valid(rawdirectory, rawfingerprint): raise RuntimeError("Immutable raw copy failed integrity validation")
            return {**cached["report"], "cache_hit": True}
        temporary = Path(tempfile.mkdtemp(prefix=".trip-import-", dir=destination.parent))
        try:
            validated_trips, validated_points = validate(trips, points, cfg, src["routes"])
            if trip_errors:
                for t in validated_trips:
                    t["flags"] = sorted(set(t["flags"] + ["invalid_trip_schema"])); t["valid"] = False
            if trip_errors or point_errors:
                for p in validated_points:
                    p["flags"] = sorted(set(p["flags"] + ["invalid_source_schema"]))
                    p.update(valid=False, gps_valid=False, speed_valid=False, gps_interval_valid=False, speed_interval_valid=False)
            if corridors is not None:
                geo = [{"source_row": p["source_row"], "latitude": p["_lat"], "longitude": p["_lon"]} for p in validated_points if p["gps_valid"]]
                if geo:
                    transformed = qgis_call(project, {"action": "transform", "points": geo, "metric_crs": cfg["map_matching"]["metric_crs"], "result": str(temporary / ".transformed.json")})
                    coordinates = {p["source_row"]: p["xy"] for p in transformed}
                    for p in validated_points: p["_xy"] = coordinates.get(p["source_row"])
                validated_points = match_points(validated_points, validated_trips, corridors, cfg)
            metrics = operating_metrics(validated_trips, validated_points, cfg)
            aggregated = operating_summary(metrics)
            flags = Counter(f for p in validated_points for f in p["flags"])
            schema = {"trips": trip_errors, "points": point_errors}
            report = {"status": "imported_with_qc_flags" if flags or any(t["flags"] for t in validated_trips) or trip_errors or point_errors else "processed",
                "is_test_data": demo, "measurement_verified": False, "method_version": VERSION,
                "trip_count": len(trips), "point_count": len(points), "processed_point_count": len(validated_points),
                "all_parseable_source_rows_preserved": len(points) == len(validated_points) and len(trips) == len(validated_trips),
                "raw_source_bytes_preserved": True,
                "valid_trip_count": sum(t["valid"] for t in validated_trips), "trips_with_valid_speed_intervals":sum(m["metadata_valid"] and m["speed_valid_duration_s"]>0 for m in metrics),
                "operating_summary_rows":len(aggregated), "point_flag_counts": dict(flags),
                "trip_flag_counts": dict(Counter(f for t in validated_trips for f in t["flags"])), "schema_errors": schema,
                "map_matching": {"enabled": cfg["map_matching"]["enabled"], "executed": corridors is not None,
                    "statuses": dict(Counter(p.get("match_status", "not_requested") for p in validated_points)),
                    "confidence_is_calibrated_probability": False, "corridors": prepared},
                "config": cfg, "input_files": inv, "source_hashes": src["hashes"], "raw_directory": str(rawdirectory),
                "directory": str(destination), "fingerprint": fingerprint, "finished_at": now(), "cache_hit": False,
                "network_calls": 0, "driving_cycle_constructed": False,
                "limitations": ["Map matching is bounded to the planned route; it cannot discover an unplanned alternate path.",
                    "Direction is inferred from successive usable GPS displacement; stationary points have unknown heading.",
                    "Ambiguous points, errors and long sampling gaps do not contribute matched-distance intervals.",
                    "Geometric proximity does not verify motorcycle permission, enforcement, safe stops or field conditions.",
                    "Coverage and denominator fields must accompany operating metrics; no missing interval is filled."]}
            atomic_json(temporary / "trips_qc.json", [public_record(t) for t in validated_trips])
            atomic_json(temporary / "points_qc.json", [public_record(p) for p in validated_points])
            atomic_json(temporary / "operating_metrics.json", metrics)
            atomic_json(temporary / "operating_summary.json", aggregated)
            write_csv(temporary / "operating_summary.csv", aggregated, list(aggregated[0]) if aggregated else ["aggregation", "group", "time_block"])
            fields = list(metrics[0]) if metrics else ["trip_id", "route_id"]
            write_csv(temporary / "operating_metrics.csv", [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in m.items()} for m in metrics], fields)
            atomic_json(temporary / "qa.json", report)
            (temporary / ".transformed.json").unlink(missing_ok=True); (temporary / ".worker_payload.json").unlink(missing_ok=True)
            publish_directory(temporary, destination, fingerprint, report, ["trips_qc.json", "points_qc.json", "operating_metrics.json", "operating_metrics.csv", "operating_summary.json", "operating_summary.csv", "qa.json"])
            atomic_json(report_path, report)
        finally:
            if temporary.exists(): shutil.rmtree(temporary)
    return report


def geometry_worker(payload):
    from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest, QgsPointXY, QgsProject, QgsVectorLayer
    app = QgsApplication([], False); app.initQgis()
    try:
        target = QgsCoordinateReferenceSystem(payload["metric_crs"])
        if payload["action"] in {"transform", "inverse_transform"}:
            inverse = payload["action"] == "inverse_transform"
            source, destination = (target, QgsCoordinateReferenceSystem("EPSG:4326")) if inverse else (QgsCoordinateReferenceSystem("EPSG:4326"), target)
            transform = QgsCoordinateTransform(source, destination, QgsProject.instance())
            values = []
            for p in payload["points"]:
                xy = transform.transform(QgsPointXY(*p["xy"]) if inverse else QgsPointXY(p["longitude"], p["latitude"]))
                if not math.isfinite(xy.x()) or not math.isfinite(xy.y()): raise ValueError("Coordinate transform returned nonfinite result")
                values.append({"source_row": p["source_row"], **({"latitude": xy.y(), "longitude": xy.x()} if inverse else {"xy": [xy.x(), xy.y()]})})
            atomic_json(payload["result"], values)
            return
        src = payload["sources"]; project = Path(payload["project"])
        from_graph = project_module(project, "graph").MotorcycleNetwork.load(src["graph"])
        graph_nodes = {n["node_id"]: (n["x"], n["y"]) for n in from_graph.data["nodes"]}
        walks = json.loads(Path(src["walks"]).read_text()); wanted = {from_graph.arcs[a]["part_id"] for w in walks for a in w["arc_ids"]}
        with tempfile.TemporaryDirectory(prefix="trip-gpkg-", dir=Path(payload["result"]).parent) as folder:
            copy = Path(folder) / "network.gpkg"; shutil.copyfile(src["network"], copy)
            layer = QgsVectorLayer(str(copy) + "|layername=scope_parts", "source_parts", "ogr")
            if not layer.isValid() or layer.crs() != target: raise ValueError("Wrong source layer or CRS for trip corridors")
            request = QgsFeatureRequest().setFilterExpression("\"part_id\" IN (" + ",".join("'" + p.replace("'", "''") + "'" for p in sorted(wanted)) + ")")
            shapes = {}
            for f in layer.getFeatures(request):
                geometry = f.geometry()
                line = geometry.asPolyline()
                if not line or geometry.isMultipart(): raise ValueError("Invalid source part geometry")
                shapes[str(f["part_id"])] = [[p.x(), p.y()] for p in line]
            result = {"metric_crs": payload["metric_crs"], "source_hashes": src["hashes"], "routes": {}}
            for w in walks:
                valid, reason = from_graph.validate_walk(w["arc_ids"])
                if not valid: raise ValueError("Source directed walk invalid: " + w["route_id"] + ": " + str(reason))
                progress = 0; arcs = []
                for order, arc_id in enumerate(w["arc_ids"]):
                    arc = from_graph.arcs[arc_id]; coords = shapes[arc["part_id"]]
                    if arc["direction"] == "backward": coords = list(reversed(coords))
                    if math.dist(coords[0], graph_nodes[arc["from_node"]]) > 0.02 or math.dist(coords[-1], graph_nodes[arc["to_node"]]) > 0.02:
                        raise ValueError("Source arc/geometry endpoint mismatch: " + arc_id)
                    length = sum(math.dist(a, b) for a, b in zip(coords, coords[1:]))
                    if abs(length - arc["length_m"]) > 0.02: raise ValueError("Source arc/geometry length mismatch: " + arc_id)
                    arcs.append({"arc_id": arc_id, "order": order, "from_node": arc["from_node"], "to_node": arc["to_node"], "direction": arc["direction"], "coordinates": coords, "length_m": length, "start_m": progress})
                    progress += length
                result["routes"][w["route_id"]] = {"arcs": arcs, "length_m": progress, "sampling_zone": w.get("sampling_zone"), "policy_version": w.get("policy_version")}
            del layer
            for name, expected in src["hashes"].items():
                if file_hash(name) != expected: raise RuntimeError("Source changed during corridor extraction: " + name)
            atomic_json(payload["result"], result)
    finally:
        app.exitQgis()


def generate_demo(project=WORK, config=None, output_root=None, demo_directory=None):
    """Create explicitly synthetic points on the current corridor for a smoke test.

    It does not model traffic or a driving cycle. Always call run(..., demo=True).
    """
    from datetime import timedelta
    cfg = load_config(project, config); src = route_sources(project, cfg.get("selection_report"))
    prepared = prepare(project, config, output_root)
    corridors = json.loads((Path(prepared["directory"]) / "corridors.json").read_text())
    destination = Path(demo_directory or (Path(output_root or project) / "tests/fixtures/trip_processing_demo"))
    if not any(part in {"fixtures", "demo"} or part.endswith("_demo") for part in destination.parts):
        raise ValueError("Synthetic fixture output must be in an explicit fixtures/demo folder")
    destination.mkdir(parents=True, exist_ok=True)
    rid = sorted(corridors["routes"])[0]; route = corridors["routes"][rid]; contract = src["routes"][rid]
    # Fixed 10 m/s positions over 30 s verify coordinates, units and matching.
    # The value is an arbitrary test input, never an observation of Hanoi speed.
    geometry_points = []
    for second in range(31):
        target = second * 10.0 + 10.0; coordinate = None
        for arc in route["arcs"]:
            progress = arc["start_m"]
            for a, b in zip(arc["coordinates"], arc["coordinates"][1:]):
                length = math.dist(a, b)
                if progress <= target <= progress + length and length:
                    f = (target - progress) / length
                    coordinate = [a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])]; break
                progress += length
            if coordinate is not None: break
        if coordinate is None: raise ValueError("Current selected route too short for bounded fixture")
        geometry_points.append({"source_row": second + 2, "xy": coordinate})
    with tempfile.TemporaryDirectory(prefix=".fixture-transform-", dir=destination) as folder:
        converted = qgis_call(project, {"action": "inverse_transform", "points": geometry_points,
            "metric_crs": cfg["map_matching"]["metric_crs"], "result": str(Path(folder) / "coordinates.json")})
    start = datetime(2026, 10, 6, 8, 0, 0, tzinfo=ZoneInfo(cfg["measurement_timezone"]))
    tid = "SYNTHETIC_DEMO_T001"
    metadata = {"trip_id": tid, "route_id": rid, "vehicle_id": "TEST_VEHICLE", "driver_id": "TEST_DRIVER",
        "started_at": start.isoformat(), "ended_at": (start + timedelta(seconds=30)).isoformat(), "time_block": "synthetic_test",
        "measurement_date": start.date().isoformat(), "sampling_zone": contract["sampling_zone"], "lez_status_at_measurement": "unknown",
        "policy_version": contract["policy_version"], "route_version": contract["route_version"], "source_bundle_sha256": contract["source_bundle_sha256"]}
    points = [{"trip_id": tid, "timestamp": (start + timedelta(seconds=i)).isoformat(), "latitude": p["latitude"],
        "longitude": p["longitude"], "speed": 10, "speed_unit": "m/s", "gps_accuracy_m": 3} for i, p in enumerate(converted)]
    write_csv(destination / cfg["trips_filename"], [metadata], cfg["required_trip_fields"])
    write_csv(destination / cfg["points_filename"], points, cfg["required_point_fields"] + ["gps_accuracy_m"])
    provenance = {"is_test_data": True, "source_bundle_sha256": src["source_bundle_sha256"], "route_version": contract["route_version"],
        "point_count": len(points), "route_id": rid, "speed_is_arbitrary_test_input": True, "driving_cycle_constructed": False,
        "created_at": now(), "purpose": "CSV ingestion/CRS/directed-route matching smoke test only"}
    atomic_json(destination / "fixture_provenance.json", provenance)
    return {**provenance, "directory": str(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "preflight", "run", "status", "generate-demo", "geometry-worker"])
    parser.add_argument("--project", "--work", default=str(WORK)); parser.add_argument("--config")
    parser.add_argument("--input-dir"); parser.add_argument("--output-root"); parser.add_argument("--demo", action="store_true")
    parser.add_argument("--payload")
    parser.add_argument("--demo-directory")
    args = parser.parse_args()
    if args.command == "geometry-worker":
        geometry_worker(json.loads(Path(args.payload).read_text())); return
    if args.command == "prepare": value = prepare(args.project, args.config, args.output_root)
    elif args.command == "generate-demo": value = generate_demo(args.project, args.config, args.output_root, args.demo_directory)
    elif args.command == "preflight": value = preflight(args.project, args.config, args.input_dir)
    elif args.command == "status": value = status(args.project, args.output_root, args.demo)
    else: value = run(args.project, args.config, args.input_dir, args.output_root, args.demo)
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__": main()
