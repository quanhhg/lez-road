"""T3: proposed survey schedules and coverage of real, versioned, QC'd trips.

Uses only the standard library. A planned row never becomes a measurement;
coverage is not a statistical stopping rule or certification of field access.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__:
    from . import trip_processing as trips
else:
    import trip_processing as trips

WORK = Path(__file__).resolve().parents[2]
VERSION = "survey_schedule_and_coverage_v1"
EXTRA_TRIP_FIELDS = ["plan_id", "device_id", "travel_direction", "day_type",
                     "calendar_checked", "calendar_note", "calendar_evidence_uri",
                     "weather", "weather_notes", "event_status", "event_notes",
                     "collection_stage"]
REPORT = "reports/field/latest_survey_coverage.json"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def configuration(project=WORK, config=None):
    cfg = json.loads(json.dumps(config)) if isinstance(config, dict) else read_json(
        trips.resolve(project, config or "config/field_workflow.json"))
    design = cfg["survey_design"]
    if design["status"] not in {"proposed", "approved"}:
        raise ValueError("Survey design status must be proposed or approved")
    if not design["version"]:
        raise ValueError("Missing survey design version")
    if cfg["timezone"] != "Asia/Ho_Chi_Minh":
        raise ValueError("Survey dates/time blocks require Hanoi local time")
    types = design["planned_day_types"]
    if not types or len(types) != len(set(types)) or not set(types) <= {"weekday", "weekend", "holiday"}:
        raise ValueError("Invalid or duplicate planned day types")
    blocks = cfg["time_blocks"]
    if not blocks or len({b["time_block"] for b in blocks}) != len(blocks):
        raise ValueError("Missing or duplicate time blocks")
    bounds = sorted((time.fromisoformat(b["local_start"]), time.fromisoformat(b["local_end"])) for b in blocks)
    if any(a >= b for a, b in bounds) or any(b > c for (_, b), (c, _) in zip(bounds, bounds[1:])):
        raise ValueError("Time blocks must be disjoint, increasing, within one day")
    repeat = cfg["repeat_schedule"]["proposed_repeat_count"]
    if isinstance(repeat, bool) or not isinstance(repeat, int) or repeat < 1:
        raise ValueError("Proposed repeat count must be a positive integer")
    targets = design["coverage_targets"]
    for key in ("minimum_valid_trips_per_cell", "minimum_distinct_dates_per_cell"):
        value = targets[key]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            raise ValueError("Coverage targets must be positive integers or null")
    if (targets["minimum_valid_trips_per_cell"] is None) != (targets["minimum_distinct_dates_per_cell"] is None):
        raise ValueError("Set both coverage targets, or leave both null")
    if design["status"] == "approved" and targets["minimum_valid_trips_per_cell"] is None:
        raise ValueError("Approved survey design requires explicit coverage targets")
    quality = design["quality_rules"]
    for key in ("minimum_speed_time_fraction", "minimum_gps_time_fraction",
                "minimum_matched_time_fraction", "minimum_route_length_fraction"):
        value = quality[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 1:
            raise ValueError("Quality fractions must be finite and in (0,1]")
    for key in ("weather_values", "event_values"):
        values = design[key]
        if not values or len(values) != len(set(values)) or "unknown" not in values:
            raise ValueError("Invalid survey vocabulary: " + key)
    overrides = design.get("calendar_overrides", {})
    for day, item in overrides.items():
        if date.fromisoformat(day).isoformat() != day or item["day_type"] not in {"weekday", "weekend", "holiday"} or not item.get("source"):
            raise ValueError("Calendar overrides need a date, valid day type and source")
    return cfg


def ensure_trip_template(path, base_fields):
    """Upgrade only empty/header-only templates. Never rewrite populated input."""
    path = Path(path)
    fields = list(dict.fromkeys([*base_fields, *EXTRA_TRIP_FIELDS]))
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            header = reader.fieldnames or []
            if len(header) != len(set(header)):
                raise ValueError("Duplicate CSV header; kept unchanged: " + str(path))
            missing = [f for f in fields if f not in header]
            if next(reader, None) is not None:
                return {"path": str(path), "action": "populated_file_preserved", "missing_columns": missing}
            fields = list(dict.fromkeys([*header, *fields]))
            if not missing:
                return {"path": str(path), "action": "unchanged", "missing_columns": []}
    path.parent.mkdir(parents=True, exist_ok=True)
    text = io.StringIO(newline="")
    csv.DictWriter(text, fields).writeheader()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", prefix=".template-", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text.getvalue())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": str(path), "action": "empty_template_upgraded", "missing_columns": []}


def schedule_rows(routes, cfg):
    """One proposed slot per route, block, day type and planning repetition."""
    rows = []
    for route in sorted(routes, key=lambda r: r["route_id"]):
        for block in cfg["time_blocks"]:
            for day_type in cfg["survey_design"]["planned_day_types"]:
                for repeat in range(1, cfg["repeat_schedule"]["proposed_repeat_count"] + 1):
                    identity = {"route_id": route["route_id"], "route_version": route["route_version"],
                        "block": block["time_block"], "day_type": day_type, "repeat": repeat,
                        "slot_schema": "T3_plan_slot_v1"}
                    row = {k: route[k] for k in ("route_id", "sampling_zone", "policy_version", "route_version", "source_bundle_sha256")}
                    row["lez2030_group"] = route.get("lez2030_group", route.get("group", ""))
                    row.update({k: "" for k in ("trip_id", "vehicle_id", "driver_id", "measurement_date", "started_at", "ended_at", "lez_status_at_measurement", *EXTRA_TRIP_FIELDS)})
                    row.update(plan_id="P-" + trips.digest(identity)[:16], day_type=day_type,
                        time_block=block["time_block"], travel_direction="as_planned", collection_stage="main",
                        proposed_local_start=block["local_start"], proposed_local_end=block["local_end"],
                        planned_repeat=repeat, status="schedule_template_not_measured",
                        survey_design_version=cfg["survey_design"]["version"], design_status=cfg["survey_design"]["status"])
                    rows.append(row)
    return rows


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def resource_conflicts(rows):
    """The same device, vehicle or driver cannot record overlapping trips."""
    resources = defaultdict(list)
    conflicts = defaultdict(set)
    for index, row in enumerate(rows):
        try:
            start, end = trips.parse_time(row.get("started_at")), trips.parse_time(row.get("ended_at"))
        except (ValueError, TypeError):
            continue
        if end <= start:
            continue
        for field in ("device_id", "vehicle_id", "driver_id"):
            if row.get(field):
                resources[(field, row[field])].append((start, end, index))
    for (field, _), intervals in resources.items():
        active = []
        for start, end, index in sorted(intervals):
            active = [(until, other) for until, other in active if until > start]
            for _, other in active:
                conflicts[index].add("overlapping_" + field)
                conflicts[other].add("overlapping_" + field)
            active.append((end, index))
    return conflicts


def evaluate(routes, trip_rows, metric_rows, cfg, *, qc_ready=True, now=None):
    """Pure evaluator; tests can use hand-checkable temporary synthetic records."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Assessment time needs a timezone")
    design = cfg["survey_design"]
    local_tz = ZoneInfo(cfg["timezone"])
    blocks = {b["time_block"]: b for b in cfg["time_blocks"]}
    route_map = {r["route_id"]: r for r in routes}
    if len(route_map) != len(routes):
        raise ValueError("Duplicate selected route IDs")
    planned = schedule_rows(routes, cfg)
    by_plan = {r["plan_id"]: r for r in planned}
    metrics = defaultdict(list)
    for row in metric_rows:
        metrics[row.get("trip_id")].append(row)
    counts = Counter(r.get("trip_id") for r in trip_rows)
    plan_counts = Counter(r.get("plan_id") for r in trip_rows if r.get("plan_id"))
    conflicts = resource_conflicts(trip_rows)
    audit = []
    for index, trip in enumerate(trip_rows):
        rid, tid = trip.get("route_id", ""), trip.get("trip_id", "")
        reasons = list(conflicts[index])
        if not qc_ready:
            reasons.append("trip_QC_required_or_stale")
        if counts[tid] != 1 or not tid:
            reasons.append("duplicate_or_missing_trip_id")
        if trip.get("valid") is not True:
            reasons.append("invalid_trip_metadata_in_QC")
        expected = route_map.get(rid)
        if expected is None:
            reasons.append("unknown_selected_route")
        else:
            for field in ("route_version", "source_bundle_sha256", "policy_version", "sampling_zone"):
                if trip.get(field) != expected.get(field):
                    reasons.append(field + "_mismatch")
        for field in ("vehicle_id", "driver_id", "device_id", "travel_direction", "day_type", "calendar_checked", "weather", "event_status", "collection_stage"):
            if not str(trip.get(field) or "").strip():
                reasons.append("missing:" + field)
        if trip.get("travel_direction") != "as_planned":
            reasons.append("direction_not_as_planned")
        if trip.get("calendar_checked") != "yes":
            reasons.append("calendar_not_checked")
        if trip.get("day_type") not in {"weekday", "weekend", "holiday"}:
            reasons.append("unknown_day_type")
        if trip.get("weather") not in design["weather_values"] or trip.get("weather") == "unknown":
            reasons.append("unknown_weather")
        if trip.get("weather") == "other" and not trip.get("weather_notes"):
            reasons.append("other_weather_needs_notes")
        if trip.get("event_status") not in design["event_values"] or trip.get("event_status") == "unknown":
            reasons.append("unknown_event_status")
        if trip.get("event_status") == "unusual_event" and not trip.get("event_notes"):
            reasons.append("unusual_event_needs_notes")
        if trip.get("collection_stage") not in {"main", "pilot"}:
            reasons.append("invalid_collection_stage")
        start = end = None
        try:
            start = trips.parse_time(trip.get("started_at")).astimezone(local_tz)
            end = trips.parse_time(trip.get("ended_at")).astimezone(local_tz)
            if end <= start or end > current:
                reasons.append("invalid_or_future_time_range")
            if start.date().isoformat() != trip.get("measurement_date") or end.date() != start.date():
                reasons.append("measurement_date_mismatch_or_cross_midnight")
            override = design.get("calendar_overrides", {}).get(start.date().isoformat())
            nominal_day = "weekend" if start.weekday() >= 5 else "weekday"
            if override:
                if trip.get("day_type") != override["day_type"]:
                    reasons.append("configured_calendar_mismatch")
            elif trip.get("day_type") in {"weekday", "weekend"} and trip["day_type"] != nominal_day:
                reasons.append("calendar_weekday_weekend_mismatch")
            if trip.get("day_type") == "holiday" and not override and not (trip.get("calendar_note") and trip.get("calendar_evidence_uri")):
                reasons.append("holiday_needs_calendar_reference")
            block = blocks.get(trip.get("time_block"))
            if block is None:
                reasons.append("unknown_time_block")
            elif not (time.fromisoformat(block["local_start"]) <= start.time() < time.fromisoformat(block["local_end"]) and end.time() <= time.fromisoformat(block["local_end"])):
                reasons.append("trip_outside_declared_time_block")
        except (ValueError, TypeError, AttributeError):
            reasons.append("invalid_trip_timestamps")
        plan = by_plan.get(trip.get("plan_id"))
        if trip.get("plan_id"):
            if plan is None or any(trip.get(k) != plan[k] for k in ("route_id", "route_version", "time_block", "day_type")):
                reasons.append("plan_slot_mismatch")
            if plan_counts[trip["plan_id"]] > 1:
                reasons.append("duplicate_plan_slot")
        found = metrics.get(tid, [])
        ratios = {"speed_time_fraction": None, "gps_time_fraction": None, "matched_time_fraction": None, "route_length_fraction": None}
        if len(found) != 1:
            reasons.append("missing_or_duplicate_QC_metrics")
        else:
            metric = found[0]
            if metric.get("metadata_valid") is not True or metric.get("route_id") != rid:
                reasons.append("QC_metrics_metadata_invalid")
            for field in ("route_version", "source_bundle_sha256", "policy_version", "sampling_zone"):
                if metric.get(field) != trip.get(field):
                    reasons.append("QC_metrics_" + field + "_mismatch")
            duration = _number(metric.get("declared_duration_s"))
            if start and end and (duration is None or abs((end - start).total_seconds() - duration) > 1e-6):
                reasons.append("QC_duration_mismatch")
            length = _number(expected.get("length_m")) if expected else None
            for output, numerator in (("speed_time_fraction", "speed_valid_duration_s"), ("gps_time_fraction", "gps_valid_duration_s"), ("matched_time_fraction", "matched_duration_s")):
                value = _number(metric.get(numerator))
                ratios[output] = value / duration if value is not None and duration and duration > 0 else None
                if ratios[output] is not None and ratios[output] > 1 + 1e-6:
                    reasons.append("QC_time_fraction_exceeds_one")
            distance = _number(metric.get("matched_distance_m"))
            ratios["route_length_fraction"] = distance / length if distance is not None and length and length > 0 else None
            for key, value in ratios.items():
                minimum = design["quality_rules"]["minimum_" + key]
                if value is None or value + 1e-9 < minimum:
                    reasons.append("insufficient_" + key)
            if metric.get("match_status_counts", {}).get("opposite_direction", 0):
                reasons.append("GPS_opposite_direction")
        reasons = sorted(set(reasons))
        quality_passed = not reasons
        in_design = trip.get("day_type") in design["planned_day_types"] and trip.get("time_block") in blocks and expected is not None
        eligible = quality_passed and in_design and trip.get("collection_stage") == "main"
        note = "eligible_under_configured_QC" if eligible else (
            "needs_correction" if reasons else "pilot_separate" if trip.get("collection_stage") == "pilot" else "outside_planned_day_types")
        audit.append({k: trip.get(k, "") for k in ("trip_id", "route_id", "time_block", "day_type", "measurement_date", "device_id", "vehicle_id", "driver_id", "travel_direction", "calendar_checked", "calendar_note", "calendar_evidence_uri", "weather", "weather_notes", "event_status", "event_notes", "collection_stage", "plan_id", "route_version", "source_bundle_sha256", "policy_version", "sampling_zone")} | {
            "quality_passed": quality_passed, "coverage_eligible": eligible, "status": note,
            "reasons": ";".join(reasons), **ratios})
    matrix = []
    targets = design["coverage_targets"]
    target, dates_target = targets["minimum_valid_trips_per_cell"], targets["minimum_distinct_dates_per_cell"]
    for route in sorted(routes, key=lambda r: r["route_id"]):
        for block in blocks:
            for day_type in design["planned_day_types"]:
                attempts = [r for r in audit if r["route_id"] == route["route_id"] and r["time_block"] == block and r["day_type"] == day_type and r["collection_stage"] != "pilot"]
                valid = [r for r in attempts if r["coverage_eligible"]]
                valid_dates = sorted({r["measurement_date"] for r in valid})
                met = len(valid) >= target and len(valid_dates) >= dates_target if target is not None else None
                status = "not_measured" if not attempts else "needs_correction" if not valid else (
                    "observed_target_unset" if met is None else "below_target" if not met else
                    "target_met" if design["status"] == "approved" else "provisional_target_met")
                matrix.append({"route_id": route["route_id"], "sampling_zone": route["sampling_zone"],
                    "lez2030_group": route.get("lez2030_group", route.get("group", "")),
                    "time_block": block, "day_type": day_type,
                    "proposed_slots": cfg["repeat_schedule"]["proposed_repeat_count"],
                    "attempted_trips": len(attempts), "valid_trips": len(valid),
                    "needs_correction_trips": len(attempts) - len(valid), "distinct_valid_dates": len(valid_dates),
                    "valid_dates": ";".join(valid_dates), "minimum_valid_trips": target,
                    "minimum_distinct_dates": dates_target,
                    "remaining_valid_trips": max(0, target - len(valid)) if target is not None else None,
                    "remaining_distinct_dates": max(0, dates_target - len(valid_dates)) if dates_target is not None else None,
                    "target_met": met, "status": status,
                    "unusual_event_valid_trips": sum(r["event_status"] == "unusual_event" for r in valid),
                    "weather_counts": json.dumps(dict(Counter(r["weather"] for r in valid)), sort_keys=True),
                    "route_version": route["route_version"], "source_bundle_sha256": route["source_bundle_sha256"]})
    eligible_count = sum(r["coverage_eligible"] for r in audit)
    if not trip_rows:
        overall = "awaiting_measurements"
    elif not eligible_count:
        overall = "needs_correction" if any(r["reasons"] for r in audit) else "awaiting_main_measurements"
    elif target is None or design["status"] != "approved":
        overall = "awaiting_design_confirmation"
    else:
        overall = "coverage_targets_met_pending_T6" if all(r["target_met"] for r in matrix) else "coverage_incomplete"
    summary = {"status": overall, "method_version": VERSION, "design_version": design["version"],
        "design_status": design["status"], "route_count": len(routes), "planned_slots": len(planned),
        "planned_cells": len(matrix), "observed_cells": sum(r["valid_trips"] > 0 for r in matrix),
        "not_measured_cells": sum(r["attempted_trips"] == 0 for r in matrix),
        "cells_needing_correction": sum(r["status"] == "needs_correction" for r in matrix),
        "cells_below_target": sum(r["status"] == "below_target" for r in matrix),
        "trip_rows": len(audit), "coverage_eligible_trips": eligible_count,
        "pilot_trips": sum(r["collection_stage"] == "pilot" for r in audit),
        "holiday_trips": sum(r["day_type"] == "holiday" for r in audit),
        "unusual_event_trips": sum(r["event_status"] == "unusual_event" for r in audit),
        "quality_rules": design["quality_rules"], "coverage_targets": targets,
        "reason_counts": dict(Counter(x for r in audit for x in r["reasons"].split(";") if x)),
        "cell_status_counts": dict(Counter(r["status"] for r in matrix)),
        "measurement_verified": False, "data_sufficiency_assessed": False,
        "field_gates_automatically_passed": False, "network_calls": 0}
    groups = defaultdict(list)
    for row in audit:
        groups[tuple(row[k] for k in ("day_type", "weather", "event_status", "collection_stage"))].append(row)
    conditions = [dict(zip(("day_type", "weather", "event_status", "collection_stage"), key)) |
        {"trip_rows": len(rows), "quality_passed_trips": sum(r["quality_passed"] for r in rows),
         "coverage_eligible_trips": sum(r["coverage_eligible"] for r in rows)} for key, rows in sorted(groups.items())]
    return summary, planned, matrix, audit, conditions


def _qc_inputs(project, src, trip_config, input_dir, trip_report):
    inventory = trips.input_inventory(project, trip_config, input_dir)
    raw_trips, errors = trips.read_table(inventory["trips"]["path"], trip_config["required_trip_fields"])
    raw_points, point_errors = trips.read_table(inventory["points"]["path"], trip_config["required_point_fields"])
    schema_errors = [e for e in errors + point_errors if not e.startswith("missing_file:")]
    report = trip_report if isinstance(trip_report, dict) else trips.status(project)
    if report.get("is_test_data"):
        raise ValueError("T3 real coverage cannot consume a demo/test report")
    if not raw_trips and not raw_points and not schema_errors:
        return [], [], True, inventory, {}, []
    expected_inputs = {k: v["sha256"] for k, v in inventory.items()}
    report_inputs = {k: v.get("sha256") for k, v in report.get("input_files", {}).items()}
    if schema_errors or report_inputs != expected_inputs or report.get("source_hashes") != src["hashes"] or report.get("config") != trip_config or not report.get("directory"):
        return raw_trips, [], False, inventory, {}, schema_errors or ["run_real_trip_QC_for_current_inputs_and_routes"]
    directory = trips.resolve(project, report["directory"])
    manifest = trips.cache_valid(directory, report.get("fingerprint"))
    if not manifest:
        raise ValueError("Real trip QC immutable bundle is missing or corrupt")
    stored = manifest["report"]
    if stored.get("is_test_data") or stored.get("source_hashes") != src["hashes"] or stored.get("config") != trip_config or {k: v.get("sha256") for k, v in stored.get("input_files", {}).items()} != expected_inputs:
        raise ValueError("Real QC provenance differs from current inputs or selected routes")
    raw_dir = trips.resolve(project, stored["raw_directory"])
    for label, item in inventory.items():
        archived = raw_dir / (label + ".csv")
        if not archived.is_file() or trips.file_hash(archived) != item["sha256"]:
            raise ValueError("Archived raw trip bytes failed integrity validation")
    if not stored.get("map_matching", {}).get("executed"):
        return read_json(directory / "trips_qc.json"), [], False, inventory, {}, ["directed_map_matching_required"]
    hashes = {str(directory / name): h for name, h in manifest["outputs"].items()}
    hashes[str(directory / "manifest.json")] = trips.file_hash(directory / "manifest.json")
    return read_json(directory / "trips_qc.json"), read_json(directory / "operating_metrics.json"), True, inventory, hashes, []


def run(project=WORK, *, config=None, selection_report=None, trip_config=None,
        input_dir=None, trip_report=None, output_root=None):
    project = Path(project).resolve()
    root = Path(output_root or project).resolve()
    cfg = configuration(project, config)
    tc = trips.load_config(project, trip_config)
    if selection_report is not None:
        tc["selection_report"] = str(selection_report)
    src = trips.route_sources(project, selection_report or tc.get("selection_report"))
    routes = list(src["routes"].values())
    actual = Counter(r["sampling_zone"] for r in routes)
    if actual != {"A": 10, "B": 8, "C": 12}:
        raise ValueError("T3 requires the current A10/B8/C12 selected set")
    with trips.lock(project, root):
        rows, metrics, ready, inventory, qc_hashes, input_issues = _qc_inputs(project, src, tc, input_dir, trip_report)
        summary, planned, matrix, audit, conditions = evaluate(routes, rows, metrics, cfg, qc_ready=ready)
        if input_issues:
            summary["status"] = "awaiting_trip_qc"
        source_hashes = {**src["hashes"], **qc_hashes}
        fingerprint = trips.digest({"version": VERSION, "code": trips.file_hash(__file__),
            "trip_code": trips.file_hash(trips.__file__), "config": cfg, "trip_config": tc,
            "sources": source_hashes, "inputs": inventory, "audit": audit, "input_issues": input_issues})
        destination = root / "data/processed/survey_coverage" / fingerprint[:20]
        destination.parent.mkdir(parents=True, exist_ok=True)
        cached = trips.cache_valid(destination, fingerprint)
        latest = root / REPORT
        if cached:
            result = {**cached["report"], "cache_hit": True, "checked_at": trips.now()}
            trips.atomic_json(latest, result)
            return result
        if destination.exists():
            raise ValueError("Corrupt immutable T3 bundle; preserve it for review")
        temporary = Path(tempfile.mkdtemp(prefix=".T3-", dir=destination.parent))
        try:
            files = ["trip_schedule_template.csv", "coverage_matrix.csv", "trip_coverage_audit.csv", "condition_summary.csv", "missing_or_incomplete_cells.csv", "summary.json"]
            for name, records, empty_fields in [
                (files[0], planned, ["plan_id", "route_id"]),
                (files[1], matrix, ["route_id", "time_block", "day_type"]),
                (files[2], audit, ["trip_id", "route_id", "status", "reasons", *EXTRA_TRIP_FIELDS]),
                (files[3], conditions, ["day_type", "weather", "event_status", "collection_stage", "trip_rows", "quality_passed_trips", "coverage_eligible_trips"]),
                (files[4], [r for r in matrix if r["status"] != "target_met"], list(matrix[0]))]:
                trips.write_csv(temporary / name, records, list(records[0]) if records else list(dict.fromkeys(empty_fields)))
            result = {**summary, "fingerprint": fingerprint, "recorded_at": trips.now(), "cache_hit": False,
                "input_issues": input_issues, "source_hashes": source_hashes, "input_files": inventory,
                "config": cfg, "paths": {"directory": str(destination), **{name[:-4]: str(destination / name) for name in files[:-1]}},
                "limitations": ["Proposed scheduling repetitions are not mandatory sample sizes.",
                    "QC thresholds are versioned research choices, not field-validated guarantees.",
                    "Coverage does not pass G1/G4/G5/G6/C6 or assess T6 data sufficiency.",
                    "Calendar references and declared weather/events are recorded, not independently verified.",
                    "Holidays and pilot trips remain separate unless explicitly included in the approved design."]}
            trips.atomic_json(temporary / "summary.json", result)
            for path, expected in source_hashes.items():
                if trips.file_hash(path) != expected:
                    raise ValueError("Source changed during T3 export: " + path)
            current = trips.input_inventory(project, tc, input_dir)
            if current != inventory:
                raise ValueError("Measurement inputs changed during T3 export")
            trips.publish_directory(temporary, destination, fingerprint, result, files)
            trips.atomic_json(latest, result)
            return result
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)


def status(project=WORK, output_root=None):
    path = Path(output_root or project) / REPORT
    return read_json(path) if path.is_file() else {"status": "not_run"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "run", "status"])
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--config")
    parser.add_argument("--selection-report")
    parser.add_argument("--input-dir")
    args = parser.parse_args()
    if args.command == "check":
        cfg = configuration(args.work, args.config)
        result = {"status": "ready", "design": cfg["survey_design"], "network_calls": 0}
    elif args.command == "status":
        result = status(args.work)
    else:
        result = run(args.work, config=args.config, selection_report=args.selection_report, input_dir=args.input_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
