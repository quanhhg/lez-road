"""Evidence-preserving preparation and import for Hanoi route surveys.

Runs with ordinary Python. It prepares proposed surveys, never creates field
measurements, alters source OSM or changes a candidate's geometry.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import importlib.util
import json
import math
import os
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote
from zoneinfo import ZoneInfo

WORK = Path(__file__).resolve().parents[2]
OBS_FIELDS = ["observation_id", "route_id", "segment_id", "part_id", "trip_id",
              "observed_at", "survey_date", "observer", "evidence_uri",
              "evidence_type", "evidence_source", "field", "value", "unit",
              "status", "coverage", "time_block", "sampling_zone",
              "lez2030_group", "policy_version", "route_version", "source_bundle_sha256", "lez_status_at_survey",
              "policy_evidence_uri", "rubric_version", "notes"]
TRIP_FIELDS = ["trip_id", "route_id", "vehicle_id", "driver_id", "started_at",
               "ended_at", "time_block", "measurement_date", "sampling_zone",
               "lez_status_at_measurement", "policy_version", "route_version", "source_bundle_sha256"]
POINT_FIELDS = ["trip_id", "timestamp", "latitude", "longitude", "speed",
                "speed_unit", "gps_accuracy_m"]
NUMERIC_FIELDS = {"lanes", "maxspeed", "junction_count", "signal_count", "C6"}
GATE_FIELDS = {"G1", "G4", "G5", "G6_start", "G6_end"}
OTHER_FIELDS = {"lanes", "maxspeed", "junction_count", "signal_count", "oneway",
                "temporary_works", "direction_change", "turn_restriction",
                "start_point", "end_point", "gps_issue", "geometry_issue", "policy_status"}


def resolve(work, value):
    p = Path(value)
    if p.parts[:1] == ("work",):
        p = Path(*p.parts[1:])
    return p.resolve() if p.is_absolute() else (Path(work) / p).resolve()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames or []
        if not fields or len(fields) != len(set(fields)):
            raise ValueError("Missing or duplicate CSV header: " + str(path))
        result = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in result):
            raise ValueError("CSV row width differs from header: " + str(path))
        return result


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, data):
    atomic(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def write_csv(path, records, fields=None):
    import io
    records = list(records)
    fields = fields or (list(records[0]) if records else [])
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
    writer.writeheader()
    writer.writerows(records)
    atomic(path, stream.getvalue())


def config(work, path=None):
    return read_json(resolve(work, path or "config/field_workflow.json"))


def source_bundle(work, cfg):
    report_path = resolve(work, cfg["selection_report"])
    report = read_json(report_path)
    directory = resolve(work, report["paths"]["directory"])
    selected_manifest = read_json(directory / "manifest.json")
    if not selected_manifest.get("complete") or any(sha(directory / name) != expected for name, expected in selected_manifest.get("output_hashes", {}).items()):
        raise ValueError("Selection snapshot failed immutable integrity validation")
    report_path = directory / "report.json"  # immutable snapshot, not volatile latest/cache metadata
    if not report_path.is_file():
        raise ValueError("Missing immutable selection report")
    classification = directory / "candidate_classification.csv"
    candidates = read_csv(classification)
    ids = [r["route_id"] for r in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate candidate route IDs")
    selected_ids = report["selected_route_ids"]
    if len(selected_ids) != 30 or len(set(selected_ids)) != 30 or not set(selected_ids) <= set(ids):
        raise ValueError("Selection must contain 30 distinct real candidate routes")
    actual = Counter(r["sampling_zone"] + "_" + r["lez2030_group"]
                     for r in candidates if r["route_id"] in selected_ids)
    if dict(actual) != cfg["quota"]:
        raise ValueError("Selection does not preserve A_inside10/B_inside8/C_outside12")
    payload = read_json(directory / "selection_payload.json")
    parent_dir = resolve(work, payload["parent_directory"])
    walk_path = parent_dir / "candidate_walks.json"
    walks = read_json(walk_path)
    if {r["route_id"] for r in walks} != set(ids):
        raise ValueError("Candidate walk IDs differ from classification")
    fingerprint = hashlib.sha256(json.dumps({"report": sha(report_path),
        "classification": sha(classification), "walks": sha(walk_path),
        "config": cfg, "workflow_code": sha(__file__)}, sort_keys=True).encode()).hexdigest()[:20]
    return {"report": report, "report_path": report_path, "directory": directory,
            "candidates": candidates, "selected_ids": selected_ids,
            "walks": walks, "parent_dir": parent_dir, "fingerprint": fingerprint}


def route_contracts(work, bundle):
    """Use the trip module's shared hashes; extend the same contract to reserves."""
    location = Path(work) / "scripts/lez/trip_processing.py"
    if not location.exists():
        staged = Path(__file__).resolve().parents[3] / "trips/trip_processing.py"
        location = staged if staged.exists() else location
    if not location.exists():
        raise ValueError("Install scripts/lez/trip_processing.py before preparing shared route contracts")
    spec = importlib.util.spec_from_file_location("_field_shared_trip_processing", location)
    trip_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = trip_module
    spec.loader.exec_module(trip_module)
    source = trip_module.route_sources(work)
    graph_hash = source["hashes"][source["graph"]]
    network_hash = source["hashes"][source["network"]]
    contracts = {}
    rows = {r["route_id"]: r for r in bundle["candidates"]}
    for walk in bundle["walks"]:
        rid, row = walk["route_id"], rows[walk["route_id"]]
        contracts[rid] = {"route_version": trip_module.digest({"route_id": rid, "arc_ids": walk["arc_ids"],
            "graph_sha256": graph_hash, "network_sha256": network_hash,
            "sampling_zone": row["sampling_zone"], "policy_version": row["policy_version"]}),
            "source_bundle_sha256": source["source_bundle_sha256"]}
        if rid in source["routes"] and any(contracts[rid][k] != source["routes"][rid][k] for k in contracts[rid]):
            raise ValueError("Candidate/selected walk contracts differ: " + rid)
    return contracts, source["hashes"]


def route_parts(work, cfg, bundle):
    """Resolve actual immutable part/segment IDs without importing QGIS."""
    options = read_json(resolve(work, cfg["selection_config"]))
    sampling = read_json(resolve(work, options.get("sampling_config", "config/sampling_abc.json")))
    network_path = resolve(work, sampling["network_path"])
    parts = {}
    db = sqlite3.connect("file:" + str(network_path) + "?mode=ro", uri=True)
    try:
        for pid, sid in db.execute("SELECT part_id,segment_id FROM scope_parts"):
            parts[str(pid)] = str(sid)
    finally:
        db.close()
    output = []
    for walk in bundle["walks"]:
        if len(walk["part_ids"]) != len(walk["arc_ids"]):
            raise ValueError("Part and arc orders differ: " + walk["route_id"])
        for order, (pid, aid) in enumerate(zip(walk["part_ids"], walk["arc_ids"]), 1):
            if str(pid) not in parts:
                raise ValueError("Missing immutable network part: " + str(pid))
            output.append({"route_id": walk["route_id"], "part_id": str(pid),
                           "segment_id": parts[str(pid)], "arc_id": str(aid),
                           "walk_order": order})
    return output


def optional_rows(path):
    return read_csv(path) if Path(path).exists() else []


def desk_priorities(bundle, cfg):
    frequencies = {r["route_id"]: r for r in optional_rows(bundle["directory"] / "selection_frequency.csv")}
    out = []
    for row in bundle["candidates"]:
        lane_missing = 1 - float(row.get("lanes_known_length_fraction") or 0)
        speed_missing = 1 - float(row.get("maxspeed_known_length_fraction") or 0)
        frequency = frequencies.get(row["route_id"], {})
        scenarios = int(frequency.get("scenario_count") or 0)
        rate = int(frequency.get("times_selected") or 0) / scenarios if scenarios else None
        # For selected routes, low frequency means fragile membership. For a reserve,
        # high frequency means the choice between reserve and selected merits review.
        selected = row["route_id"] in bundle["selected_ids"]
        instability = (1 - rate if selected else rate) if rate is not None else 1
        lower, upper = row.get("final_context_score_lower_C6"), row.get("final_context_score_upper_C6")
        width = float(upper) - float(lower) if lower and upper else 10
        priority = (lane_missing + speed_missing) / 2 + instability + width / 10
        out.append({"route_id": row["route_id"], "sampling_zone": row["sampling_zone"],
                    "lez2030_group": row["lez2030_group"], "selected": selected,
                    "lanes_missing_fraction": lane_missing, "maxspeed_missing_fraction": speed_missing,
                    "selection_frequency": rate, "sensitivity_scenario_count": scenarios,
                    "selection_instability": instability, "C6_observed": "",
                    "C6_score_interval_width": width, "priority_score": priority,
                    "method_version": cfg["method_version"],
                    "priority_purpose": "desk_review_and_field_verification_only"})
    return sorted(out, key=lambda r: (-r["priority_score"], r["route_id"]))


def prepare(work=WORK, output=None, config_path=None):
    work = Path(work).resolve()
    cfg = config(work, config_path)
    bundle = source_bundle(work, cfg)
    output = Path(output).resolve() if output else resolve(work, cfg["output_directory"]) / bundle["fingerprint"]
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        previous = read_json(output / "manifest.json")
        existing = optional_rows(output / "field_observations.csv")
        if existing and previous["fingerprint"] != bundle["fingerprint"]:
            raise ValueError("Filled observations belong to an older source; prepare into a new version directory")
    contracts, source_hashes = route_contracts(work, bundle)
    candidates = bundle["candidates"]
    registry = []
    for r in candidates:
        selected = r["route_id"] in bundle["selected_ids"]
        registry.append({"route_id": r["route_id"], "sampling_zone": r["sampling_zone"],
            "lez2030_group": r["lez2030_group"], "policy_version": r["policy_version"],
            "survey_date": "", "measurement_date": "", "lez_status_at_measurement": "",
            "lez_status_at_survey": "", "selected": selected,
            "decision_status": "proposed_for_survey" if selected else "reserve_candidate",
            "length_m": r["length_m"], "rc_target": r["rc_target"],
            "street_sequence": r.get("street_sequence", ""),
            "source_selection_fingerprint": bundle["fingerprint"],
            **contracts[r["route_id"]],
            "legal_geometry_verified": bundle["report"].get("official_gis_verified", False)})
    write_csv(output / "route_registry.csv", registry)
    write_csv(output / "route_part_registry.csv", route_parts(work, cfg, bundle))
    osm, models = [], []
    for r in candidates:
        for field in ("lanes", "maxspeed", "junctions_per_km", "signals_per_km", "P_oneway"):
            unit = {"lanes": "count", "maxspeed": "km/h", "junctions_per_km": "count/km",
                    "signals_per_km": "count/km", "P_oneway": "fraction"}[field]
            osm.append({"route_id": r["route_id"], "field": field, "value": r.get(field, ""),
                        "unit": unit, "source": "osm_snapshot",
                        "snapshot_utc": bundle["report"].get("snapshot_utc", ""),
                        "known_length_fraction": r.get(field + "_known_length_fraction", ""),
                        "definition": "mean_of_known_OSM_length_only" if field in ("lanes", "maxspeed") else "OSM_topology_proxy",
                        "is_field_observation": False})
        for field in ("lanes", "maxspeed"):
            models.append({"route_id": r["route_id"], "field": field,
                "value": r.get(field + "_scoring_model", ""),
                "unit": cfg["field_units"][field], "model": "RC_median_scoring_model",
                "imputed_length_fraction": r.get(field + "_imputed_length_fraction", ""),
                "is_field_observation": False})
        models.append({"route_id": r["route_id"], "field": "C6", "value": r.get("C6_scoring_assumption", 2.5),
            "unit": "score_0_to_5", "model": "neutral_provisional_assumption",
            "imputed_length_fraction": "", "is_field_observation": False})
    write_csv(output / "attributes_osm.csv", osm)
    write_csv(output / "attributes_models.csv", models)
    for name, fields in (("field_observations.csv", OBS_FIELDS), ("trip_registry.csv", TRIP_FIELDS), ("gps_points.csv", POINT_FIELDS)):
        # Re-running preparation must never erase actual observations or trips.
        if not (output / name).exists():
            write_csv(output / name, [], fields)
    incoming = resolve(work, cfg["measurement_incoming"])
    # With an explicit staging output, all writes remain beneath that output.
    incoming = output / "measurement_incoming" if output.is_relative_to(work) is False else incoming
    for name, fields in (("trips.csv", TRIP_FIELDS), ("gps_points.csv", POINT_FIELDS)):
        if not (incoming / name).exists():
            write_csv(incoming / name, [], fields)
    selected = [r for r in registry if r["selected"]]
    checklist = []
    questions = []
    for r in selected:
        checklist.append({"route_id": r["route_id"], "sampling_zone": r["sampling_zone"],
            "lez2030_group": r["lez2030_group"], "policy_version": r["policy_version"],
            "survey_date": "", "observer": "", "lez_status_at_survey": "",
            "route_version": r["route_version"], "source_bundle_sha256": r["source_bundle_sha256"],
            "G1": "unknown", "G4": "unknown", "G5": "unknown", "G6": "unknown",
            "C6": "", "C6_rubric_version": cfg["c6"]["rubric_version"],
            "lanes_observed": "", "maxspeed_observed": "", "evidence_uri": "",
            "decision": "pending_field_verification"})
        for gate, rule in cfg["gates"].items():
            for field in rule["fields"]:
                questions.append({"route_id": r["route_id"], "field": field,
                    "question": rule["question"], "required_evidence": "dated_field_evidence",
                    "minimum_distinct_dates": rule["minimum_distinct_dates"],
                    "answer": "", "observed_at": "", "evidence_uri": ""})
        for field in cfg["c6"]["supporting_fields"]:
            questions.append({"route_id": r["route_id"], "field": field,
                "question": "Đánh giá thành phần " + field + "; dùng no_limitation/minor/moderate/multiple/severe/infeasible và ghi lý do.",
                "required_evidence": "dated_field_evidence", "minimum_distinct_dates": 1,
                "answer": "", "observed_at": "", "evidence_uri": ""})
        for field in ("lanes", "maxspeed", "junction_count", "signal_count", "oneway", "geometry_issue", "policy_status"):
            questions.append({"route_id": r["route_id"], "field": field,
                "question": "Kiểm tra " + field + " theo đúng đoạn/chiều, ngày và khung giờ; dùng part_id/segment_id khi thuộc tính thay đổi.",
                "required_evidence": "source_and_date_required", "minimum_distinct_dates": 1,
                "answer": "", "observed_at": "", "evidence_uri": ""})
    write_csv(output / "survey_checklist.csv", checklist)
    write_csv(output / "evidence_questionnaires.csv", questions)
    schedule = []
    for r in selected:
        for block in cfg["time_blocks"]:
            for repeat in range(1, cfg["repeat_schedule"]["proposed_repeat_count"] + 1):
                schedule.append({"route_id": r["route_id"], "sampling_zone": r["sampling_zone"],
                    "lez2030_group": r["lez2030_group"], "policy_version": r["policy_version"],
                    "trip_id": "", "vehicle_id": "", "driver_id": "", "measurement_date": "",
                    "lez_status_at_measurement": "", "time_block": block["time_block"],
                    "route_version": r["route_version"], "source_bundle_sha256": r["source_bundle_sha256"],
                    "proposed_local_start": block["local_start"], "proposed_local_end": block["local_end"],
                    "planned_repeat": repeat, "status": "schedule_template_not_measured"})
    write_csv(output / "trip_schedule_template.csv", schedule)
    write_csv(output / "desk_review_priority.csv", desk_priorities(bundle, cfg))
    write_json(output / "C6_rubric.json", cfg["c6"])
    manifest = {"status": "prepared_awaiting_field_observations", "method_version": cfg["method_version"],
        "fingerprint": bundle["fingerprint"], "created_at": (read_json(output / "manifest.json").get("created_at") if (output / "manifest.json").exists() else datetime.now(timezone.utc).isoformat()),
        "work": str(work), "directory": str(output), "candidate_routes": len(registry),
        "selected_routes": len(selected), "quota": cfg["quota"], "measured_trips_created": 0,
        "field_observations_created": 0, "measurement_verified": False, "surveyed_set_locked": False,
        "incoming_directory": str(incoming), "source_selection_report": str(bundle["report_path"]),
        "source_selection_report_sha256": sha(bundle["report_path"]),
        "source_classification_sha256": sha(bundle["directory"] / "candidate_classification.csv"),
        "source_file_hashes": {**source_hashes,
            str(bundle["directory"] / "candidate_classification.csv"): sha(bundle["directory"] / "candidate_classification.csv"),
            str(bundle["parent_dir"] / "candidate_walks.json"): sha(bundle["parent_dir"] / "candidate_walks.json")},
        "source_directory": str(bundle["directory"]), "config": cfg,
        "raw_osm_modified": False, "candidate_geometry_modified": False,
        "paths": {name[:-4]: str(output / name) for name in ("route_registry.csv", "route_part_registry.csv",
            "field_observations.csv", "survey_checklist.csv", "evidence_questionnaires.csv",
            "desk_review_priority.csv", "trip_schedule_template.csv", "trip_registry.csv", "gps_points.csv")}}
    write_json(output / "manifest.json", manifest)
    result = status(output)
    write_json(output / "status.json", result)
    if output.is_relative_to(resolve(work, cfg["output_directory"])):
        write_json(work / "reports/field/latest_field_workflow.json", manifest)
    return manifest


def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timestamp requires explicit timezone offset")
    return dt


def evidence_uri_error(value):
    if not value:
        return "missing evidence URI"
    parsed = urlparse(value)
    if parsed.scheme in ("https", "http"):
        return None if parsed.netloc else "invalid evidence URL"
    if parsed.scheme == "file":
        p = Path(unquote(parsed.path))
    elif not parsed.scheme:
        p = Path(value)
        if not p.is_absolute():
            return "local evidence path must be absolute"
    else:
        return "unsupported evidence URI scheme"
    return None if p.is_file() else "local evidence file does not exist"


def validate_observations(directory, observations, *, existing=None, now=None):
    directory = Path(directory)
    manifest = read_json(directory / "manifest.json")
    cfg = manifest["config"]
    try:
        assert_current_source(directory)
    except (ValueError, OSError) as e:
        return {"status": "failed", "valid": False, "row_count": len(observations),
                "accepted_count": 0, "idempotent_ignored_count": 0, "ignored_ids": [],
                "errors": [{"errors": [str(e)]}], "accepted": [],
                "evidence_validation": "stale_source_snapshot_rejected"}
    registry = {r["route_id"]: r for r in read_csv(directory / "route_registry.csv")}
    trip_rows = optional_rows(directory / "trip_registry.csv")
    incoming = manifest.get("incoming_directory")
    if incoming:
        trip_rows += optional_rows(Path(incoming) / "trips.csv")
    trips = {r["trip_id"]: r for r in trip_rows}
    part_rows = read_csv(directory / "route_part_registry.csv")
    links = defaultdict(lambda: {"parts": set(), "segments": set(), "pairs": set()})
    for r in part_rows:
        links[r["route_id"]]["parts"].add(r["part_id"])
        links[r["route_id"]]["segments"].add(r["segment_id"])
        links[r["route_id"]]["pairs"].add((r["part_id"], r["segment_id"]))
    now = now or datetime.now(timezone.utc)
    existing_by_id = {r["observation_id"]: r for r in (existing or [])}
    seen = set()
    errors, accepted, ignored = [], [], []
    allowed = GATE_FIELDS | OTHER_FIELDS | set(cfg["c6"]["supporting_fields"]) | {"C6"}
    for line, raw in enumerate(observations, 2):
        r = {key: str(raw.get(key) or "").strip() for key in OBS_FIELDS}
        issue = []
        oid, rid, field = r["observation_id"], r["route_id"], r["field"]
        if not oid:
            issue.append("missing observation_id")
        if oid in seen:
            issue.append("duplicate observation_id in import")
        seen.add(oid)
        if oid in existing_by_id:
            same = all(str(existing_by_id[oid].get(k) or "") == r[k] for k in OBS_FIELDS)
            if same:
                ignored.append(oid)
                continue
            issue.append("observation_id conflicts with stored record; use a new ID for correction")
        route = registry.get(rid)
        if route is None:
            issue.append("unknown route_id")
        else:
            for key in ("sampling_zone", "lez2030_group", "policy_version", "route_version", "source_bundle_sha256"):
                if r[key] != route[key]:
                    issue.append(key + " differs from current route registry")
            pid, sid = r["part_id"], r["segment_id"]
            if pid and pid not in links[rid]["parts"]:
                issue.append("part_id is not on route")
            if sid and sid not in links[rid]["segments"]:
                issue.append("segment_id is not on route")
            if pid and sid and (pid, sid) not in links[rid]["pairs"]:
                issue.append("part/segment linkage differs from source network")
            if r["trip_id"] and (r["trip_id"] not in trips or trips[r["trip_id"]].get("route_id") != rid):
                issue.append("trip_id is not a registered trip for this route")
        if field not in allowed:
            issue.append("unsupported field")
        if r["status"] not in cfg["observation_statuses"]:
            issue.append("unsupported observation status")
        if r["evidence_source"] not in cfg["evidence_sources"]:
            issue.append("evidence_source must be field or desk")
        if r["coverage"] not in ("whole_route", "part", "segment", "point", ""):
            issue.append("unsupported evidence coverage")
        if r["coverage"] == "part" and not r["part_id"]:
            issue.append("part coverage requires part_id")
        if r["coverage"] == "segment" and not r["segment_id"]:
            issue.append("segment coverage requires segment_id")
        if r["status"] in ("unknown", "pending"):
            if r["value"]:
                issue.append("unknown/pending observation must have blank value")
        else:
            try:
                observed = timestamp(r["observed_at"])
                if observed > now:
                    issue.append("observed_at is in the future")
                if date.fromisoformat(r["survey_date"]) != observed.astimezone(ZoneInfo(cfg["timezone"])).date():
                    issue.append("survey_date differs from observed_at in Hanoi timezone")
            except (ValueError, TypeError):
                issue.append("invalid observed_at/survey_date (ISO dates and timezone required)")
            if not r["observer"]:
                issue.append("missing observer")
            if not r["value"]:
                issue.append("observed status requires a value")
            uri_error = evidence_uri_error(r["evidence_uri"])
            if uri_error:
                issue.append(uri_error)
            if r["evidence_type"] not in cfg["evidence_types"]:
                issue.append("unsupported evidence_type")
            if r["evidence_source"] == "field" and r["evidence_type"] not in cfg["field_evidence_types"]:
                issue.append("field evidence requires a field capture or device log")
            if r["lez_status_at_survey"] not in cfg["policy_status_values"]:
                issue.append("record policy status at actual survey date; use unknown if unresolved")
            if r["lez_status_at_survey"] in ("inside", "outside") or (field == "policy_status" and r["value"] in ("inside", "outside")):
                policy_error = evidence_uri_error(r["policy_evidence_uri"])
                if policy_error:
                    issue.append("actual-date policy status: " + policy_error)
            if field in GATE_FIELDS:
                if r["value"] not in ("passed", "failed"):
                    issue.append("gate value must be passed or failed")
                if r["coverage"] != "whole_route":
                    issue.append("gate assessment must explicitly cover whole_route")
                if r["unit"]:
                    issue.append("gate unit must be blank")
            if field in NUMERIC_FIELDS:
                try:
                    n = float(r["value"])
                    if not math.isfinite(n) or n < 0:
                        issue.append("invalid numeric value")
                    if field in ("lanes", "junction_count", "signal_count", "C6") and not n.is_integer():
                        issue.append("count/score must be an integer")
                    if field in ("lanes", "maxspeed") and n <= 0:
                        issue.append("lanes/maxspeed must be positive")
                    if field == "C6" and not 0 <= n <= 5:
                        issue.append("C6 must be in [0,5]")
                except ValueError:
                    issue.append("numeric field is not numeric")
                if r["unit"] != cfg["field_units"][field]:
                    issue.append("wrong unit; expected " + cfg["field_units"][field])
            if field == "oneway" and (r["value"] not in ("true", "false") or r["unit"] != "boolean"):
                issue.append("oneway requires true/false and unit boolean")
            if field == "policy_status" and r["value"] not in cfg["policy_status_values"]:
                issue.append("invalid actual-date policy_status value")
            if field in set(cfg["c6"]["supporting_fields"]):
                if r["value"] not in cfg["c6"]["support_values"]:
                    issue.append("invalid C6 supporting assessment")
            if field == "C6" or field in cfg["c6"]["supporting_fields"]:
                if r["rubric_version"] != cfg["c6"]["rubric_version"]:
                    issue.append("wrong or missing C6 rubric version")
                if r["coverage"] != "whole_route":
                    issue.append("C6 requires whole_route assessment")
        if issue:
            errors.append({"line": line, "observation_id": oid, "route_id": rid, "errors": issue})
        else:
            accepted.append(r)
    combined = list(existing or []) + accepted
    group = defaultdict(list)
    for r in combined:
        if r.get("status") == "observed":
            group[(r["route_id"], r["field"], r.get("part_id", ""), r.get("segment_id", ""), r["observed_at"])].append(r)
    for key, records in group.items():
        if len({(r["value"], r["unit"]) for r in records}) > 1:
            errors.append({"route_id": key[0], "errors": ["conflicting simultaneous values for the same route/field/part"]})
    return {"status": "passed" if not errors else "failed", "valid": not errors,
            "row_count": len(observations), "accepted_count": len(accepted),
            "idempotent_ignored_count": len(ignored), "ignored_ids": ignored,
            "errors": errors, "accepted": accepted,
            "evidence_validation": "URI syntax and local existence; remote content not independently verified"}


def assert_current_source(directory):
    manifest = read_json(Path(directory) / "manifest.json")
    report = Path(manifest["source_selection_report"])
    if manifest.get("work"):
        latest = read_json(resolve(Path(manifest["work"]), manifest["config"]["selection_report"]))
        if resolve(Path(manifest["work"]), latest["paths"]["directory"]) != Path(manifest["source_directory"]):
            raise ValueError("Selection changed after preparation; prepare a new workflow version before importing")
    if sha(report) != manifest["source_selection_report_sha256"]:
        raise ValueError("Selection changed after preparation; prepare a new workflow version before importing")
    for path, expected in manifest.get("source_file_hashes", {}).items():
        if sha(path) != expected:
            raise ValueError("Source geometry/network snapshot changed after preparation: " + path)


def import_observations(directory, source):
    directory = Path(directory)
    assert_current_source(directory)
    existing = read_csv(directory / "field_observations.csv")
    rows = read_csv(source)
    result = validate_observations(directory, rows, existing=existing)
    write_json(directory / "last_import_validation.json", {k: v for k, v in result.items() if k != "accepted"})
    if not result["valid"]:
        return {k: v for k, v in result.items() if k != "accepted"}
    write_csv(directory / "field_observations.csv", existing + result["accepted"], OBS_FIELDS)
    archive = directory / "imports" / (sha(source)[:20] + ".csv")
    if not archive.exists():
        atomic(archive, Path(source).read_bytes())
    updated = status(directory)
    write_json(directory / "status.json", updated)
    return {**{k: v for k, v in result.items() if k != "accepted"}, "workflow_status": updated["status"]}


def assess_routes(registry, observations, cfg):
    by_route = defaultdict(list)
    for r in observations:
        if r["status"] == "observed" and r["evidence_source"] == "field":
            by_route[r["route_id"]].append(r)
    output = []
    for route in registry:
        evidence = by_route[route["route_id"]]
        record = {k: route[k] for k in ("route_id", "sampling_zone", "lez2030_group", "policy_version", "selected")}
        states = {}
        for gate, rule in cfg["gates"].items():
            field_states = []
            for field in rule["fields"]:
                rows = [r for r in evidence if r["field"] == field and r["coverage"] == "whole_route"]
                if not rows:
                    field_states.append("unknown")
                    continue
                latest_date = max(r["survey_date"] for r in rows)
                latest = [r for r in rows if r["survey_date"] == latest_date]
                if any(r["value"] == "failed" for r in latest):
                    field_states.append("failed")
                elif len({r["survey_date"] for r in rows if r["value"] == "passed"
                          and r["survey_date"] > max((q["survey_date"] for q in rows if q["value"] == "failed"), default="")}) >= rule["minimum_distinct_dates"]:
                    field_states.append("passed")
                else:
                    field_states.append("unknown")
            states[gate] = "failed" if "failed" in field_states else ("passed" if all(s == "passed" for s in field_states) else "unknown")
        record.update(states)
        scores = sorted((r for r in evidence if r["field"] == "C6"), key=lambda r: timestamp(r["observed_at"]))
        score_date = scores[-1]["survey_date"] if scores else ""
        supports = {r["field"] for r in evidence if r["field"] in cfg["c6"]["supporting_fields"] and r["survey_date"] == score_date}
        gates_pass = all(s == "passed" for s in states.values())
        last_failure = max((timestamp(r["observed_at"]) for r in evidence if r["field"] in GATE_FIELDS and r["value"] == "failed"), default=None)
        complete_C6 = bool(scores) and supports == set(cfg["c6"]["supporting_fields"]) and gates_pass and (last_failure is None or timestamp(scores[-1]["observed_at"]) > last_failure)
        record["C6"] = scores[-1]["value"] if complete_C6 else ""
        record["C6_status"] = "observed_after_gates" if complete_C6 else "unknown_until_valid_field_evidence"
        record["C6_rubric_version"] = cfg["c6"]["rubric_version"]
        latest_date = max((r["survey_date"] for r in evidence), default="")
        policy_values = {r["value"] if r["field"] == "policy_status" else r["lez_status_at_survey"]
                         for r in evidence if r["survey_date"] == latest_date and r["coverage"] == "whole_route"
                         and r.get("policy_evidence_uri") and
                         ((r["field"] == "policy_status" and r["value"] != "unknown") or
                          (r["field"] != "policy_status" and r["lez_status_at_survey"] != "unknown"))}
        policy_known = len(policy_values) == 1
        record["lez_status_at_latest_survey"] = next(iter(policy_values)) if policy_known else "unknown"
        record["actual_date_policy_review"] = "evidence_recorded" if policy_known else "pending"
        record["valid_field_observation_count"] = len(evidence)
        record["survey_date"] = max((r["survey_date"] for r in evidence), default="")
        if "failed" in states.values():
            decision = "proposed_replace_or_repair"
        elif complete_C6 and float(record["C6"]) == 0:
            decision = "proposed_replace"
        elif gates_pass and complete_C6 and policy_known:
            decision = "eligible_for_manual_surveyed_set_review"
        else:
            decision = "pending_field_verification"
        record["decision_status"] = decision
        record["surveyed_set_locked"] = False
        output.append(record)
    return output


def status(directory):
    directory = Path(directory)
    manifest = read_json(directory / "manifest.json")
    cfg = manifest["config"]
    registry = read_csv(directory / "route_registry.csv")
    observations = read_csv(directory / "field_observations.csv")
    validation = validate_observations(directory, observations)
    # Corrupt/imported-by-hand rows never activate a gate.
    decisions = assess_routes(registry, validation["accepted"] if validation["valid"] else [], cfg)
    write_csv(directory / "proposed_decisions.csv", decisions)
    selected = [r for r in decisions if str(r["selected"]).lower() == "true"]
    completed = sum(r["decision_status"] == "eligible_for_manual_surveyed_set_review" for r in selected)
    return {"status": "awaiting_field_observations" if not observations else
            ("observations_require_correction" if not validation["valid"] else "field_review_in_progress"),
            "candidate_routes": len(registry), "selected_routes": len(selected),
            "stored_observation_rows": len(observations), "valid_observations": validation["accepted_count"] if validation["valid"] else 0,
            "selected_routes_eligible_for_manual_review": completed,
            "selected_routes_pending": len(selected) - completed,
            "G1_G4_G5_G6_unknown_counts": {g: sum(r[g] == "unknown" for r in selected) for g in cfg["gates"]},
            "C6_unknown_count": sum(not r["C6"] for r in selected),
            "measurement_verified": False, "surveyed_set_locked": False,
            "source_selection_fingerprint": manifest["fingerprint"],
            "validation_errors": validation["errors"]}


def replacement_dry_runs(work, cfg, selected_ids, candidates):
    """Recompute the full set with the existing selection metric implementation."""
    sys.path.insert(0, str(work)) if str(work) not in sys.path else None
    metrics = importlib.import_module("scripts.lez.selection_metrics")
    options = read_json(resolve(work, cfg["selection_config"]))
    parent = read_json(resolve(work, options.get("parent_report", cfg["sampling_report"])))
    data = metrics.load_data(work, parent, options)
    index = {r["route_id"]: i for i, r in enumerate(data["features"])}
    selected = [index[r] for r in selected_ids]
    baseline = metrics.summary(data, selected, options["minimum_cell_fraction"])
    output = []
    for candidate in candidates:
        rid = candidate["route_id"]
        if rid in selected_ids:
            continue
        new = index[rid]
        trials = []
        for old in selected:
            old_feature = data["features"][old]
            if (old_feature["sampling_zone"], old_feature["group"]) != (candidate["sampling_zone"], candidate["lez2030_group"]):
                continue
            others = [i for i in selected if i != old]
            if not metrics.feasible_add(data, others, new, options["quota"], set(options["required_strata"]), options):
                continue
            summary = metrics.summary(data, others + [new], options["minimum_cell_fraction"])
            counts = {k: summary["quota_bucket_counts"].get(k, 0) for k in cfg["quota"]}
            if counts != cfg["quota"] or summary["route_count"] != 30:
                continue
            if summary["max_unique_corridor_overlap_fraction"] >= options["max_corridor_overlap"]:
                continue
            if summary["material_cells"] < baseline["material_cells"]:
                continue
            if summary["quantile_groups_covered"] < baseline["quantile_groups_covered"] * options["minimum_quantile_diversity_retained"]:
                continue
            if any(summary["D_by_domain"][g] > baseline["D_by_domain"][g] + options["max_domain_D_worsening"] for g in ("inside", "outside")):
                continue
            trials.append((summary["D_combined"], old_feature["route_id"], summary))
        best = min(trials, key=lambda x: (x[0], x[1])) if trials else None
        output.append({"reserve_route_id": rid, "sampling_zone": candidate["sampling_zone"],
            "lez2030_group": candidate["lez2030_group"], "replace_route_id": best[1] if best else "",
            "status": "feasible_proposed_dry_run" if best else "no_feasible_single_swap",
            "quota_preserved": bool(best), "D_before": baseline["D_combined"],
            "D_after": best[0] if best else "", "delta_D": best[0] - baseline["D_combined"] if best else "",
            "unique_rc_coverage_fraction": best[2]["unique_rc_coverage_fraction"] if best else "",
            "material_cells": best[2]["material_cells"] if best else "",
            "quantile_groups_covered": best[2]["quantile_groups_covered"] if best else "",
            "max_corridor_overlap": best[2]["max_unique_corridor_overlap_fraction"] if best else "",
            "field_verified": False, "source_modified": False,
            "all_set_metrics_json": json.dumps(best[2], sort_keys=True) if best else ""})
    return baseline, output


def build_update_plan(directory, *, evaluate_reserves=True):
    directory = Path(directory)
    assert_current_source(directory)
    manifest = read_json(directory / "manifest.json")
    cfg, work = manifest["config"], Path(manifest["work"])
    current = status(directory)
    observations = read_csv(directory / "field_observations.csv")
    validation = validate_observations(directory, observations)
    valid = validation["accepted"] if validation["valid"] else []
    changes = []
    for r in valid:
        if r["field"] in ("lanes", "maxspeed", "junction_count", "signal_count", "oneway", "temporary_works", "direction_change", "turn_restriction", "geometry_issue", "start_point", "end_point", "policy_status"):
            changes.append({"observation_id": r["observation_id"], "route_id": r["route_id"],
                "part_id": r["part_id"], "segment_id": r["segment_id"], "field": r["field"],
                "proposed_observed_value": r["value"], "unit": r["unit"], "observed_at": r["observed_at"],
                "evidence_uri": r["evidence_uri"], "action": "review_observed_overlay" if r["field"] in NUMERIC_FIELDS else "review_rebuild_graph_and_route_if_needed",
                "source_geometry_modified": False, "raw_osm_modified": False})
    fields = ["observation_id", "route_id", "part_id", "segment_id", "field", "proposed_observed_value", "unit", "observed_at", "evidence_uri", "action", "source_geometry_modified", "raw_osm_modified"]
    write_csv(directory / "observation_update_plan.csv", changes, fields)
    observed = [{"observation_id": r["observation_id"], "route_id": r["route_id"],
                 "part_id": r["part_id"], "segment_id": r["segment_id"], "field": r["field"],
                 "value": r["value"], "unit": r["unit"], "observed_at": r["observed_at"],
                 "observer": r["observer"], "evidence_uri": r["evidence_uri"],
                 "coverage": r["coverage"], "source": "dated_field_observation",
                 "route_version": r["route_version"], "source_bundle_sha256": r["source_bundle_sha256"],
                 "aggregation": "none; one evidence assessment per row"}
                for r in valid if r["status"] == "observed" and r["evidence_source"] == "field"
                and r["field"] in NUMERIC_FIELDS | {"oneway"}]
    observed_fields = ["observation_id", "route_id", "part_id", "segment_id", "field", "value", "unit", "observed_at",
                       "observer", "evidence_uri", "coverage", "source", "route_version", "source_bundle_sha256", "aggregation"]
    write_csv(directory / "attributes_observed.csv", observed, observed_fields)
    baseline, reserves, metric_status = None, [], "not_requested"
    if evaluate_reserves:
        bundle = source_bundle(work, cfg)
        try:
            baseline, reserves = replacement_dry_runs(work, cfg, bundle["selected_ids"], bundle["candidates"])
            write_csv(directory / "reserve_replacement_dry_run.csv", reserves)
            metric_status = "recomputed_all_set_metrics"
        except (ImportError, KeyError, ValueError, OSError) as e:
            # A unavailable optional metric runtime cannot become a false passed plan.
            metric_status = "pending_metric_recalculation: " + str(e)
    plan = {"status": "proposed_update_plan", "workflow_status": current,
        "observed_updates_proposed": len(changes), "reserve_evaluation": metric_status,
        "reserve_candidates": len(reserves), "baseline_set_metrics": baseline,
        "quota": cfg["quota"], "source_modified": False, "surveyed_set_locked": False,
        "mandatory_next_after_geometry_change": ["rebuild_directed_graph_walk", "recalculate_metric_lengths",
            "recheck_G2_G3_and_access", "recompute_full_network_sample_matrix", "recompute_D_and_overlap_and_diversity",
            "rerun_exact_quota_selection", "review_dated_field_gates"],
        "driving_cycle_construction": "excluded_by_user"}
    write_json(directory / "update_plan.json", plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "status", "validate_observations", "import_observations", "build_update_plan"])
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--config")
    parser.add_argument("--output", type=Path, help="Prepared workflow directory; stage here when outside canonical project")
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--skip-reserve-metrics", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.work, args.output, args.config)
    else:
        directory = args.output
        if directory is None:
            directory = Path(read_json(args.work / "reports/field/latest_field_workflow.json")["directory"])
        if args.command == "status":
            result = status(directory)
        elif args.command in ("validate_observations", "import_observations"):
            if args.observations is None:
                parser.error("--observations is required")
            if args.command == "validate_observations":
                result = validate_observations(directory, read_csv(args.observations))
                result.pop("accepted", None)
            else:
                result = import_observations(directory, args.observations)
        else:
            result = build_update_plan(directory, evaluate_reserves=not args.skip_reserve_metrics)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if result.get("valid") is False:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
