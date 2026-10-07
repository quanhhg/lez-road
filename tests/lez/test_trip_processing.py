"""Adverse-case contracts, interval denominators and immutable import checks."""
import copy
import csv
import importlib.util
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "trip_processing.py"
if not MODULE.is_file():
    MODULE = Path(__file__).resolve().parents[2] / "scripts/lez/trip_processing.py"
spec = importlib.util.spec_from_file_location("trip_processing", MODULE)
tp = importlib.util.module_from_spec(spec); spec.loader.exec_module(tp)
CFG = tp.load_config(MODULE.parents[2] if MODULE.parent.name == "lez" else MODULE.parent)
ROUTES = {"A01": {"sampling_zone": "A", "policy_version": "LEZ2027_2030_LEZ_FIRST_v1", "route_version": "route-v1", "source_bundle_sha256": "bundle-v1"}}


def trip(**extra):
    return {"trip_id": "T001", "route_id": "A01", "vehicle_id": "V001", "driver_id": "D001",
        "started_at": "2026-10-06T08:00:00+07:00", "ended_at": "2026-10-06T08:01:00+07:00", "time_block": "morning",
        "measurement_date": "2026-10-06", "sampling_zone": "A", "lez_status_at_measurement": "unknown",
        "policy_version": ROUTES["A01"]["policy_version"], "route_version": "route-v1", "source_bundle_sha256": "bundle-v1", "source_row": 2, **extra}


def point(second=0, **extra):
    return {"trip_id": "T001", "timestamp": f"2026-10-06T08:00:{second:02d}+07:00", "latitude": "21.0",
        "longitude": "105.8", "speed": "36", "speed_unit": "km/h", "gps_accuracy_m": "3", "source_row": second + 2, **extra}


def corridor(arcs=None):
    return {"metric_crs": "EPSG:3405", "routes": {"A01": {"arcs": arcs or [
        {"arc_id": "e1:F", "order": 0, "coordinates": [[0, 0], [100, 0]], "start_m": 0, "length_m": 100},
        {"arc_id": "e2:F", "order": 1, "coordinates": [[100, 0], [200, 0]], "start_m": 100, "length_m": 100}]}}}


class ValidationTests(unittest.TestCase):
    def validate(self, rows, metadata=None):
        return tp.validate(metadata or [trip()], rows, CFG, ROUTES)

    def test_group_summary_uses_time_denominator_and_excludes_bad_metadata(self):
        tr, pts = self.validate([point(0), point(1)])
        first = tp.operating_metrics(tr, pts, CFG)[0]
        invalid = dict(first, metadata_valid=False, speed_integrated_distance_m=99999)
        summary = tp.operating_summary([first, invalid])
        zone = next(r for r in summary if r["aggregation"] == "zone")
        self.assertEqual(zone["excluded_metadata_trips"], 1)
        self.assertEqual(zone["declared_duration_s"], 60)
        self.assertAlmostEqual(zone["speed_duration_coverage_fraction"], 1/60)
        self.assertAlmostEqual(zone["time_weighted_mean_speed_kmh"], 36)

    def test_inline_config_is_validated_and_copied(self):
        cfg = tp.load_config(config=CFG)
        self.assertEqual(cfg, CFG)
        self.assertIsNot(cfg, CFG)
        broken = copy.deepcopy(CFG)
        broken["max_gap_s"] = -1
        with self.assertRaises(ValueError): tp.load_config(config=broken)

    def test_speed_units_equivalent_and_invalid_preserved(self):
        tr, pts = self.validate([point(0, speed="10", speed_unit="m/s"), point(1), point(2, speed_unit="mph")])
        self.assertEqual(len(pts), 3)
        self.assertEqual([p["speed_kmh"] for p in pts[:2]], [36, 36])
        self.assertIn("invalid_speed_unit", pts[2]["flags"])
        self.assertFalse(pts[2]["speed_valid"])
        self.assertTrue(pts[2]["gps_valid"])

    def test_duplicate_and_nonmonotonic_time_not_silently_sorted(self):
        _, pts = self.validate([point(1), point(1), point(0)])
        self.assertIn("duplicate_timestamp", pts[1]["flags"])
        self.assertIn("nonmonotonic_time", pts[2]["flags"])
        self.assertEqual([p["source_row"] for p in pts], [3, 3, 2])

    def test_timestamp_offset_mandatory(self):
        _, pts = self.validate([point(timestamp="2026-10-06T08:00:00")])
        self.assertIn("invalid_timestamp", pts[0]["flags"])

    def test_gap_endpoint_can_restart_without_filling_missing_seconds(self):
        tr, pts = self.validate([point(0), point(10), point(11)])
        self.assertIn("sampling_gap", pts[1]["flags"])
        self.assertFalse(pts[1]["speed_interval_valid"])
        self.assertTrue(pts[2]["speed_interval_valid"])
        m = tp.operating_metrics(tr, pts, CFG)[0]
        self.assertEqual(m["speed_valid_duration_s"], 1)
        self.assertAlmostEqual(m["speed_integrated_distance_m"], 10)
        self.assertAlmostEqual(m["speed_duration_coverage_fraction"], 1 / 60)

    def test_jump_invalidates_gps_but_keeps_independent_speed_channel(self):
        _, pts = self.validate([point(0), point(1, latitude="22.0")])
        self.assertIn("gps_jump", pts[1]["flags"])
        self.assertFalse(pts[1]["gps_interval_valid"])
        self.assertTrue(pts[1]["speed_interval_valid"])

    def test_nonfinite_negative_outlier_and_bad_accuracy(self):
        _, pts = self.validate([point(0, speed="NaN", latitude="inf"), point(1, speed="-1"),
            point(2, speed="999"), point(3, gps_accuracy_m="200")])
        self.assertIn("invalid_speed", pts[0]["flags"])
        self.assertIn("invalid_coordinate", pts[0]["flags"])
        self.assertIn("negative_speed", pts[1]["flags"])
        self.assertIn("speed_outlier", pts[2]["flags"])
        self.assertIn("poor_gps_accuracy", pts[3]["flags"])

    def test_acceleration_outlier_excluded_from_interval_metrics(self):
        tr, pts = self.validate([point(0, speed="0"), point(1, speed="100")])
        self.assertIn("acceleration_outlier", pts[1]["flags"])
        self.assertEqual(tp.operating_metrics(tr, pts, CFG)[0]["speed_valid_duration_s"], 0)

    def test_date_uses_hanoi_timezone(self):
        t = trip(started_at="2026-10-05T18:00:00Z", ended_at="2026-10-05T18:01:00Z")
        tr, _ = self.validate([], [t])
        self.assertTrue(tr[0]["valid"])

    def test_stale_route_bundle_policy_and_zone_invalidate_metadata(self):
        for key, value in [("route_version", "old"), ("source_bundle_sha256", "old"), ("policy_version", "old"), ("sampling_zone", "B")]:
            with self.subTest(key=key):
                tr, pts = self.validate([point()], [trip(**{key: value})])
                self.assertFalse(tr[0]["valid"])
                self.assertIn(key + "_mismatch", tr[0]["flags"])
                self.assertFalse(pts[0]["gps_valid"])
                self.assertFalse(pts[0]["speed_valid"])

    def test_time_weighted_metrics_with_idle_accel_cruise_decel(self):
        tr, pts = self.validate([point(0, speed="0"), point(1, speed="0"), point(3, speed="7.2"), point(5, speed="7.2"), point(7, speed="0")])
        m = tp.operating_metrics(tr, pts, CFG)[0]
        self.assertEqual(m["speed_valid_duration_s"], 7)
        self.assertEqual(m["idle_time_s"], 1)
        self.assertEqual(m["moving_time_s"], 6)
        self.assertEqual((m["acceleration_time_s"], m["cruise_time_s"], m["deceleration_time_s"]), (2, 2, 2))
        self.assertAlmostEqual(m["speed_integrated_distance_m"], 8)
        self.assertAlmostEqual(m["time_weighted_mean_speed_kmh"], 8 / 7 * 3.6)
        self.assertAlmostEqual(m["mean_moving_speed_kmh"], 4.8)

    def test_duplicate_trip_id_rejected_for_both_rows(self):
        tr, pts = self.validate([point()], [trip(), trip(source_row=3)])
        self.assertTrue(all("duplicate_trip_id" in t["flags"] for t in tr))
        self.assertIn("invalid_trip_metadata", pts[0]["flags"])


class MatchingTests(unittest.TestCase):
    def match(self, xy, shape=None, extra=None):
        tr, pts = tp.validate([trip()], [point(i, **(extra[i] if extra else {})) for i in range(len(xy))], CFG, ROUTES)
        for p, coordinate in zip(pts, xy): p["_xy"] = coordinate
        return tr, tp.match_points(pts, tr, shape or corridor(), CFG)

    def test_forward_match_and_matched_distance(self):
        tr, pts = self.match([[10, 1], [20, 1], [30, 1]])
        self.assertTrue(all(p["match_status"] == "matched" for p in pts))
        self.assertIn("heading_unknown", pts[0]["match_flags"])
        m = tp.operating_metrics(tr, pts, CFG)[0]
        self.assertEqual(m["matched_duration_s"], 2)
        self.assertEqual(m["matched_distance_m"], 20)

    def test_opposite_direction_is_not_inferred_as_legal_forward(self):
        _, pts = self.match([[80, 0], [70, 0], [60, 0]])
        self.assertEqual(pts[1]["match_status"], "opposite_direction")
        self.assertEqual(pts[2]["match_status"], "opposite_direction")

    def test_far_gps_is_off_route(self):
        _, pts = self.match([[10, 100]])
        self.assertEqual(pts[0]["match_status"], "off_route")

    def test_bad_gps_stays_unknown(self):
        _, pts = self.match([[10, 0]], extra=[{"gps_accuracy_m": "100"}])
        self.assertEqual(pts[0]["match_status"], "unknown_bad_gps")

    def test_parallel_revisited_corridor_is_ambiguous(self):
        shape = corridor([
            {"arc_id": "near:F", "order": 0, "coordinates": [[0, 0], [100, 0]], "start_m": 0, "length_m": 100},
            {"arc_id": "near2:F", "order": 1, "coordinates": [[0, 2], [100, 2]], "start_m": 1000, "length_m": 100}])
        _, pts = self.match([[10, 1], [20, 1]], shape)
        self.assertEqual(pts[0]["match_status"], "ambiguous")
        self.assertEqual(pts[1]["match_status"], "ambiguous")
        self.assertEqual(pts[0]["match_confidence"], 0)

    def test_impossible_progress_jump_is_flagged(self):
        shape = corridor([
            {"arc_id": "near:F", "order": 0, "coordinates": [[0, 0], [100, 0]], "start_m": 0, "length_m": 100},
            {"arc_id": "far:F", "order": 1, "coordinates": [[0, 100], [100, 100]], "start_m": 10000, "length_m": 100}])
        _, pts = self.match([[10, 0], [20, 100]], shape)
        self.assertEqual(pts[1]["match_status"], "continuity_unresolved")

    def test_gap_resets_continuity(self):
        tr, pts = tp.validate([trip()], [point(0), point(10)], CFG, ROUTES)
        for p, xy in zip(pts, [[80, 0], [10, 0]]): p["_xy"] = xy
        output = tp.match_points(pts, tr, corridor(), CFG)
        self.assertEqual(output[1]["match_status"], "matched")
        self.assertIn("heading_unknown", output[1]["match_flags"])

    def test_capped_candidates_report_ambiguity(self):
        arcs = [{"arc_id": f"e{i}:F", "order": i, "coordinates": [[0, i / 10], [100, i / 10]], "start_m": 100 * i, "length_m": 100} for i in range(15)]
        _, pts = self.match([[10, 0]], corridor(arcs))
        self.assertEqual(pts[0]["match_status"], "ambiguous")
        self.assertIn("candidate_limit_reached", pts[0]["match_flags"])


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.input = self.root / "fixtures"; self.input.mkdir()
        self.cfg = copy.deepcopy(CFG); self.cfg["map_matching"]["enabled"] = False
        self.cfgpath = self.root / "trip_processing.json"; self.cfgpath.write_text(json.dumps(self.cfg))
        self.src = {"routes": ROUTES, "hashes": {"fake-graph": "sha256"}, "snapshot_utc": "2026-10-01T00:00:00Z", "source_bundle_sha256": "bundle-v1"}
        self.sourcepatch = patch.object(tp, "route_sources", return_value=self.src); self.sourcepatch.start()
        self.lockpatch = patch.object(tp, "lock", return_value=nullcontext()); self.lockpatch.start()

    def tearDown(self):
        self.sourcepatch.stop(); self.lockpatch.stop(); self.tmp.cleanup()

    def write_inputs(self, points=None, trips=None):
        for name, rows, fields in [("trips.csv", [trip()] if trips is None else trips, CFG["required_trip_fields"]),
                                  ("gps_points.csv", [point(0), point(1)] if points is None else points, CFG["required_point_fields"] + ["gps_accuracy_m"])]:
            tp.write_csv(self.input / name, rows, fields)

    def run_import(self, demo=True):
        return tp.run(self.root, self.cfgpath, self.input, self.root, demo)

    def test_empty_real_is_awaiting_measurements_no_generated_data(self):
        self.write_inputs([], [])
        result = self.run_import(False)
        self.assertEqual(result["status"], "awaiting_measurements")
        self.assertEqual(result["point_count"], 0)
        self.assertFalse((self.root / "data/raw/measurements/real").exists())

    def test_fixture_requires_explicit_demo_flag(self):
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "require --demo"): self.run_import(False)

    def test_fixture_sidecar_stays_test_when_folder_renamed(self):
        self.write_inputs()
        renamed = self.root / "incoming"; self.input.rename(renamed); self.input = renamed
        (renamed / "fixture_provenance.json").write_text('{"is_test_data": true}')
        with self.assertRaisesRegex(ValueError, "require --demo"): self.run_import(False)

    def test_raw_bytes_hashes_and_cache_identical(self):
        self.write_inputs(points=[point(0), point(1, speed_unit="mph")])
        before = {p.name: p.read_bytes() for p in self.input.iterdir()}
        first = self.run_import(); second = self.run_import()
        self.assertTrue(first["is_test_data"])
        self.assertTrue(second["cache_hit"])
        raw = Path(first["raw_directory"])
        self.assertEqual((raw / "trips.csv").read_bytes(), before["trips.csv"])
        self.assertEqual((raw / "points.csv").read_bytes(), before["gps_points.csv"])
        self.assertEqual(first["point_count"], first["processed_point_count"])
        self.assertTrue(first["raw_source_bytes_preserved"])
        self.assertFalse((self.root / "data/processed/trip_processing/real").exists())

    def test_changed_inputs_create_new_version_and_keep_old(self):
        self.write_inputs(); first = self.run_import()
        self.write_inputs(points=[point(0), point(1), point(2)])
        second = self.run_import()
        self.assertNotEqual(first["directory"], second["directory"])
        self.assertTrue(Path(first["directory"]).is_dir())
        self.assertEqual(json.loads((Path(first["directory"]) / "points_qc.json").read_text()).__len__(), 2)

    def test_corrupted_cache_is_rejected_never_overwritten(self):
        self.write_inputs(); result = self.run_import()
        path = Path(result["directory"]) / "points_qc.json"; path.write_text("corrupted")
        with self.assertRaisesRegex(RuntimeError, "Corrupted immutable processed"): self.run_import()
        self.assertEqual(path.read_text(), "corrupted")

    def test_transaction_error_leaves_no_complete_version(self):
        self.write_inputs()
        with patch.object(tp, "operating_metrics", side_effect=RuntimeError("simulated failure")):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"): self.run_import()
        processed = self.root / "data/processed/trip_processing/demo"
        self.assertEqual(list(processed.iterdir()), [])
        self.assertFalse((self.root / "reports/trips/latest_demo.json").exists())
        # Raw input archive is intentionally retained even if downstream processing fails.
        self.assertEqual(len(list((self.root / "data/raw/measurements/demo").iterdir())), 1)

    def test_malformed_and_short_csv_have_schema_or_row_flags(self):
        self.write_inputs()
        (self.input / "gps_points.csv").write_text("trip_id,timestamp,latitude,longitude,speed,speed_unit\nT001,bad,21,105,36\n")
        result = self.run_import()
        self.assertEqual(result["processed_point_count"], 1)
        row = json.loads((Path(result["directory"]) / "points_qc.json").read_text())[0]
        self.assertIn("short_csv_row", row["flags"])
        self.assertIn("invalid_timestamp", row["flags"])

    def test_raw_archive_integrity_guard(self):
        self.write_inputs(); first = self.run_import()
        (Path(first["raw_directory"]) / "points.csv").write_text("tampered")
        self.cfg["idle_speed_kmh"] = 2; self.cfgpath.write_text(json.dumps(self.cfg))
        with self.assertRaisesRegex(RuntimeError, "Immutable raw copy"): self.run_import()

    def test_duplicate_header_quarantines_parseable_records_from_metrics(self):
        self.write_inputs()
        (self.input / "gps_points.csv").write_text("trip_id,timestamp,latitude,longitude,speed,speed,speed_unit\nT001,2026-10-06T08:00:00+07:00,21,105,1,36,km/h\nT001,2026-10-06T08:00:01+07:00,21,105,1,36,km/h\n")
        result = self.run_import()
        self.assertIn("duplicate_header", result["schema_errors"]["points"])
        rows = json.loads((Path(result["directory"]) / "points_qc.json").read_text())
        self.assertEqual(len(rows), 2)
        self.assertTrue(all("invalid_source_schema" in row["flags"] for row in rows))
        m = json.loads((Path(result["directory"]) / "operating_metrics.json").read_text())[0]
        self.assertEqual(m["speed_valid_duration_s"], 0)

    def test_raw_integrity_also_checked_when_processed_cache_is_valid(self):
        self.write_inputs(); first = self.run_import()
        (Path(first["raw_directory"]) / "points.csv").write_text("tampered")
        with self.assertRaisesRegex(RuntimeError, "Immutable raw copy"): self.run_import()


if __name__ == "__main__": unittest.main(verbosity=2)
