"""T5 interval mathematics: SI RPA/PKE, time-weighted SAFD and pooled totals.

No GIS, HTTP, smoothing, inferred measurements or driving-cycle construction.
The linear-speed assumption applies only within already valid adjacent samples.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys

VERSION = "T5_linear_interval_SI_v1"
GROUP_FIELDS = ["aggregation", "group", "time_block", "day_type", "collection_stage"]


def finite(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def protocol(cfg):
    opts = cfg.get("operating_metrics")
    if not isinstance(opts, dict) or opts.get("version") != VERSION:
        raise ValueError("Missing/unsupported T5 operating_metrics protocol")
    if opts.get("status") not in {"proposed", "approved"}:
        raise ValueError("T5 protocol status must be proposed or approved")
    for field in ("positive_acceleration_threshold_m_s2", "distance_epsilon_m"):
        value = finite(opts.get(field))
        if not isinstance(opts.get(field), (int, float)) or value is None or value < 0 or (field == "distance_epsilon_m" and value == 0):
            raise ValueError("Invalid T5 numeric rule: " + field)
    if opts["positive_acceleration_threshold_m_s2"] >= cfg["max_abs_acceleration_m_s2"]:
        raise ValueError("RPA threshold must be below the QC acceleration limit")
    for field in ("speed_edges_kmh", "acceleration_edges_m_s2"):
        edges = opts.get(field)
        if not isinstance(edges, list) or len(edges) < 2 or any(not isinstance(x, (int, float)) or finite(x) is None for x in edges) or any(a >= b for a, b in zip(edges, edges[1:])):
            raise ValueError("SAFD edges must be finite and strictly increasing: " + field)
    if opts["speed_edges_kmh"][0] < 0:
        raise ValueError("SAFD speed grid must be nonnegative")
    if (len(opts["speed_edges_kmh"]) - 1) * (len(opts["acceleration_edges_m_s2"]) - 1) > 1000000:
        raise ValueError("SAFD grid is too large")
    if opts.get("interval_model") != "linear_speed_constant_acceleration" or opts.get("pke_definition") != "positive_delta_speed_squared_no_half":
        raise ValueError("Changing the T5 formula requires an explicit new implementation version")
    return opts


def bin_index(value, edges):
    """Half-open bins, with the last upper boundary included."""
    if value < edges[0] or value > edges[-1]:
        return None
    if value == edges[-1]:
        return len(edges) - 2
    return bisect_right(edges, value) - 1


def safd_allocation(v0_kmh, v1_kmh, acceleration, duration, opts):
    """Split valid interval time exactly at crossed speed-bin boundaries."""
    ai = bin_index(acceleration, opts["acceleration_edges_m_s2"])
    if ai is None:
        return {}, duration
    cuts = [0.0, 1.0]
    if v1_kmh != v0_kmh:
        cuts += [(edge - v0_kmh) / (v1_kmh - v0_kmh) for edge in opts["speed_edges_kmh"]
                 if 0 < (edge - v0_kmh) / (v1_kmh - v0_kmh) < 1]
    cuts = sorted(set(cuts))
    cells = defaultdict(float)
    outside = 0.0
    for begin, end in zip(cuts, cuts[1:]):
        midpoint_speed = v0_kmh + (v1_kmh - v0_kmh) * (begin + end) / 2
        si = bin_index(midpoint_speed, opts["speed_edges_kmh"])
        seconds = (end - begin) * duration
        if si is None:
            outside += seconds
        else:
            cells[(si, ai)] += seconds
    return dict(cells), outside


def compute(rows, cfg):
    """Return additive numerators, denominators, sparse histogram and audit."""
    opts = protocol(cfg)
    histogram = defaultdict(float)
    audit, used = [], {}
    speed_time = distance = rpa_n = pke_n = outside = 0.0
    pos_time = neg_time = pos_integral = neg_integral = a_integral = a2_integral = 0.0
    for index in range(1, len(rows)):
        before, after = rows[index - 1], rows[index]
        dt = finite(after.get("interval_s"))
        s0, s1 = finite(before.get("speed_kmh")), finite(after.get("speed_kmh"))
        stated_a = finite(after.get("acceleration_m_s2"))
        reasons = []
        if not after.get("speed_interval_valid"):
            reasons.append("QC_speed_interval_invalid")
        if not before.get("speed_valid") or not after.get("speed_valid"):
            reasons.append("QC_speed_endpoint_invalid")
        if dt is None or not 0 < dt <= cfg["max_gap_s"]:
            reasons.append("invalid_or_gap_interval")
        if s0 is None or s1 is None or min(s0, s1) < 0 or max(s0, s1) > cfg["max_speed_kmh"]:
            reasons.append("invalid_speed_endpoints")
        v0, v1 = s0 / 3.6 if s0 is not None else None, s1 / 3.6 if s1 is not None else None
        acceleration = (v1 - v0) / dt if v0 is not None and v1 is not None and dt and dt > 0 else None
        if acceleration is None or abs(acceleration) > cfg["max_abs_acceleration_m_s2"] + 1e-12:
            reasons.append("invalid_or_outlier_acceleration")
        elif stated_a is None or not math.isclose(acceleration, stated_a, rel_tol=1e-9, abs_tol=1e-9):
            reasons.append("inconsistent_interval_acceleration")
        item = {"interval_order": index, "start_source_row": before.get("source_row"),
            "end_source_row": after.get("source_row"), "duration_s": dt,
            "start_speed_m_s": v0, "end_speed_m_s": v1, "acceleration_m_s2": acceleration,
            "status": "excluded" if reasons else "used", "reasons": ";".join(sorted(set(reasons))),
            "start_QC_flags": ";".join(before.get("flags", [])), "end_QC_flags": ";".join(after.get("flags", [])),
            "distance_m": None, "rpa_numerator_m2_s2": None, "pke_numerator_m2_s2": None,
            "safd_in_grid_s": None, "safd_outside_grid_s": None}
        if not reasons:
            mean_speed = (v0 + v1) / 2
            d = mean_speed * dt
            rn = mean_speed * acceleration * dt if acceleration > opts["positive_acceleration_threshold_m_s2"] else 0.0
            pn = max((v1 - v0) * (v1 + v0), 0.0)
            allocation, out = safd_allocation(s0, s1, acceleration, dt, opts)
            for key, seconds in allocation.items():
                histogram[key] += seconds
            speed_time += dt; distance += d; rpa_n += rn; pke_n += pn; outside += out
            a_integral += acceleration * dt; a2_integral += acceleration ** 2 * dt
            if acceleration > cfg["acceleration_threshold_m_s2"]:
                pos_time += dt; pos_integral += acceleration * dt
            if acceleration < -cfg["acceleration_threshold_m_s2"]:
                neg_time += dt; neg_integral += acceleration * dt
            item.update(distance_m=d, rpa_numerator_m2_s2=rn, pke_numerator_m2_s2=pn,
                safd_in_grid_s=sum(allocation.values()), safd_outside_grid_s=out)
            used[index] = {"duration_s": dt, "mean_speed_kmh": mean_speed * 3.6,
                "acceleration_m_s2": acceleration, "distance_m": d}
        audit.append(item)
    has_distance = distance > opts["distance_epsilon_m"]
    in_grid = sum(histogram.values())
    if not math.isclose(in_grid + outside, speed_time, abs_tol=1e-8, rel_tol=1e-10):
        raise ValueError("SAFD time accounting does not equal valid interval duration")
    metrics = {"operating_method_version": VERSION, "distance_epsilon_m": opts["distance_epsilon_m"],
        "kinematic_status": "no_valid_intervals" if not speed_time else "computed_on_valid_intervals",
        "kinematic_valid_interval_count": len(used), "kinematic_excluded_interval_count": len(audit) - len(used),
        "kinematic_valid_duration_s": speed_time, "kinematic_distance_m": distance if speed_time else None,
        "rpa_numerator_m2_s2": rpa_n if speed_time else None, "pke_numerator_m2_s2": pke_n if speed_time else None,
        "rpa_m_s2": rpa_n / distance if has_distance else None, "pke_m_s2": pke_n / distance if has_distance else None,
        "distance_metric_status": "no_valid_intervals" if not speed_time else "defined" if has_distance else "zero_or_near_zero_distance",
        "positive_acceleration_duration_s": pos_time, "negative_acceleration_duration_s": neg_time,
        "positive_acceleration_integral_m_s": pos_integral, "negative_acceleration_integral_m_s": neg_integral,
        "acceleration_integral_m_s": a_integral, "acceleration_squared_integral_m2_s3": a2_integral,
        "mean_acceleration_m_s2": pos_integral / pos_time if pos_time else None,
        "mean_deceleration_m_s2": neg_integral / neg_time if neg_time else None,
        "time_weighted_signed_acceleration_m_s2": a_integral / speed_time if speed_time else None,
        "rms_acceleration_m_s2": math.sqrt(a2_integral / speed_time) if speed_time else None,
        "safd_in_grid_duration_s": in_grid, "safd_outside_grid_duration_s": outside,
        "safd_valid_time_denominator_s": speed_time,
        "safd_in_grid_fraction": in_grid / speed_time if speed_time else None,
        "safd_status": "no_valid_intervals" if not speed_time else "outside_grid_present" if outside > 1e-9 else "computed",
        "smoothing_applied": False}
    return {"metrics": metrics, "histogram": dict(histogram), "interval_audit": audit, "used_intervals": used}


def group_keys(row):
    """Always separate pilot/main/unknown collection stage in pooled results."""
    rid, zone, block = row.get("route_id"), row.get("sampling_zone"), row.get("time_block")
    day, stage = row.get("day_type") or "unknown", row.get("collection_stage") or "unknown"
    return [("overall", "all", "", "all", stage), ("route", rid, "", "all", stage),
        ("zone", zone, "", "all", stage), ("time_block", block, block, "all", stage),
        ("zone_time_block", zone, block, "all", stage),
        ("zone_time_block_day_type", zone, block, day, stage),
        ("route_time_block_day_type", rid, block, day, stage)]


def pooled_metrics(records):
    """Pool raw sums and denominators, never average per-trip ratios."""
    def total(key):
        return sum(r.get(key) or 0.0 for r in records)
    distance, duration = total("kinematic_distance_m"), total("kinematic_valid_duration_s")
    rn, pn = total("rpa_numerator_m2_s2"), total("pke_numerator_m2_s2")
    # Individual near-zero rows have no defined distance ratio, but their
    # nonnegative integrals remain explicitly pooled under one group rule.
    epsilon = max((r.get("distance_epsilon_m", 1e-9) for r in records), default=1e-9)
    positive, negative = total("positive_acceleration_duration_s"), total("negative_acceleration_duration_s")
    return {"kinematic_valid_duration_s": duration, "kinematic_distance_m": distance if duration else None,
        "rpa_numerator_m2_s2": rn if duration else None, "pke_numerator_m2_s2": pn if duration else None,
        "rpa_m_s2": rn / distance if distance > epsilon else None,
        "pke_m_s2": pn / distance if distance > epsilon else None,
        "positive_acceleration_duration_s": positive, "negative_acceleration_duration_s": negative,
        "mean_acceleration_m_s2": total("positive_acceleration_integral_m_s") / positive if positive else None,
        "mean_deceleration_m_s2": total("negative_acceleration_integral_m_s") / negative if negative else None,
        "time_weighted_signed_acceleration_m_s2": total("acceleration_integral_m_s") / duration if duration else None,
        "rms_acceleration_m_s2": math.sqrt(total("acceleration_squared_integral_m2_s3") / duration) if duration else None,
        "safd_valid_time_denominator_s": total("safd_valid_time_denominator_s"),
        "safd_in_grid_duration_s": total("safd_in_grid_duration_s"),
        "safd_outside_grid_duration_s": total("safd_outside_grid_duration_s"),
        "operating_method_version": VERSION}


SAFD_FIELDS = ["speed_bin", "acceleration_bin", "speed_lower_kmh", "speed_upper_kmh",
    "acceleration_lower_m_s2", "acceleration_upper_m_s2", "duration_s", "valid_time_denominator_s", "fraction_of_valid_time"]


def histogram_rows(histogram, denominator, opts):
    for (si, ai), duration in sorted(histogram.items()):
        if duration <= 0:
            continue
        yield {"speed_bin": si, "acceleration_bin": ai,
            "speed_lower_kmh": opts["speed_edges_kmh"][si], "speed_upper_kmh": opts["speed_edges_kmh"][si + 1],
            "acceleration_lower_m_s2": opts["acceleration_edges_m_s2"][ai], "acceleration_upper_m_s2": opts["acceleration_edges_m_s2"][ai + 1],
            "duration_s": duration, "valid_time_denominator_s": denominator,
            "fraction_of_valid_time": duration / denominator if denominator else None}


def export_tables(metrics, details, cfg):
    opts = protocol(cfg)
    if len(metrics) != len(details):
        raise ValueError("T5 trip metrics and interval details must align")
    by_trip, audit = [], []
    grouped, denominators = defaultdict(lambda: defaultdict(float)), defaultdict(float)
    for row, detail in zip(metrics, details):
        identity = {k: row.get(k) for k in ("trip_id", "route_id", "trip_source_row", "sampling_zone", "time_block", "day_type", "collection_stage", "route_version", "source_bundle_sha256")}
        by_trip += [dict(identity, metadata_valid=row["metadata_valid"], **r) for r in histogram_rows(detail["histogram"], row["kinematic_valid_duration_s"], opts)]
        audit += [dict(identity, metadata_valid=row["metadata_valid"], **r) for r in detail["interval_audit"]]
        if not row["metadata_valid"]:
            continue
        for key in group_keys(row):
            denominators[key] += row["kinematic_valid_duration_s"]
            for cell, seconds in detail["histogram"].items():
                grouped[key][cell] += seconds
    by_group = []
    for key in sorted(grouped, key=str):
        by_group += [dict(zip(GROUP_FIELDS, key)) | r for r in histogram_rows(grouped[key], denominators[key], opts)]
    return by_trip, by_group, audit


def protocol_record(cfg):
    opts = protocol(cfg)
    return {**opts, "internal_speed_unit": "m/s", "acceleration_unit": "m/s2", "distance_unit": "m", "time_unit": "s",
        "rpa_formula": "sum(mean(v0,v1)*a*dt where a>positive_threshold) / valid_speed_distance",
        "pke_formula": "sum(max(v1^2-v0^2,0)) / valid_speed_distance; no factor 1/2",
        "distance_formula": "sum(mean(v0,v1)*dt) on the same valid intervals",
        "safd_formula": "time in speed-acceleration bin / all valid speed interval time",
        "zero_distance_policy": "RPA/PKE null; keep valid stationary SAFD time",
        "bin_boundary_rule": "[lower,upper), last upper boundary included",
        "out_of_grid_policy": "report outside seconds; never clip or silently renormalize",
        "sparse_table_rule": "omitted cells mean zero only when the valid-time denominator is positive",
        "rpa_pke_dependence": "with zero positive threshold and this interval model PKE=2*RPA; not independent evidence",
        "smoothing_applied": False, "fills_sampling_gaps": False, "data_sufficiency_assessed": False}


def self_check(cfg):
    """Hand-calculated examples independent of source routes and real storage."""
    if __package__:
        from . import trip_processing as tp
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from lez import trip_processing as tp
    opts = protocol(cfg)
    if opts["positive_acceleration_threshold_m_s2"] != 0:
        raise ValueError("Hand-check suite expects the zero-threshold T5 default")
    cases = [
        ("stationary", [0, 1, 3], [0, 0, 0], 3, 0, None, None),
        ("constant_speed", [0, 1, 3], [2, 2, 2], 3, 6, 0, 0),
        ("accelerate_cruise_brake", [0, 2, 4, 6], [0, 2, 2, 0], 6, 8, 0.25, 0.5),
        ("unequal_steps", [0, 1, 3], [0, 1, 3], 3, 4.5, 1, 2),
        ("gap_then_recover", [0, 10, 11], [0, 2, 2], 1, 2, 0, 0)]
    results = []
    for label, seconds, speeds, expected_t, expected_d, expected_rpa, expected_pke in cases:
        from datetime import datetime, timedelta, timezone
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        metadata = {"trip_id": "TEST_ONLY_" + label, "route_id": "TEST_ONLY_route", "vehicle_id": "TEST_ONLY_vehicle", "driver_id": "TEST_ONLY_driver",
            "started_at": start.isoformat(), "ended_at": (start + timedelta(seconds=seconds[-1])).isoformat(), "measurement_date": "2020-01-01",
            "time_block": "TEST_ONLY", "sampling_zone": "A", "lez_status_at_measurement": "unknown", "policy_version": "TEST_ONLY_policy", "route_version": "TEST_ONLY_route", "source_bundle_sha256": "TEST_ONLY_source"}
        point_rows = [{"trip_id": metadata["trip_id"], "timestamp": (start + timedelta(seconds=s)).isoformat(),
            "latitude": 21, "longitude": 105.8, "speed": v, "speed_unit": "m/s", "source_row": i + 2} for i, (s, v) in enumerate(zip(seconds, speeds))]
        validated, points = tp.validate([metadata], point_rows, cfg, {"TEST_ONLY_route": metadata})
        actual = tp.operating_metrics(validated, points, cfg)[0]
        expected = {"kinematic_valid_duration_s": expected_t, "kinematic_distance_m": expected_d, "rpa_m_s2": expected_rpa, "pke_m_s2": expected_pke}
        checks = {k: actual[k] is None if v is None else math.isclose(actual[k], v, abs_tol=1e-9) for k, v in expected.items()}
        results.append({"case": label, "expected": expected, "actual": {k: actual[k] for k in expected}, "passed": all(checks.values())})
    return {"status": "passed" if all(r["passed"] for r in results) else "failed", "is_test_data": True,
        "cases": results, "real_measurements_created": 0, "protocol": protocol_record(cfg), "network_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["self-check"])
    parser.add_argument("--work", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if str(Path(__file__).resolve().parents[1]) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lez import trip_processing as tp
    result = self_check(tp.load_config(args.work))
    if args.report:
        tp.atomic_json(args.report, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
