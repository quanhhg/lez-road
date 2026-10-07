"""Temporary fixtures only: no observations are written to real measurement data."""
import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "scripts/lez/field_workflow.py"
SPEC = importlib.util.spec_from_file_location("field_workflow", SOURCE)
fw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fw)


class EvidenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="field_workflow_test_")
        self.directory = Path(self.tmp.name)
        source_cfg = Path(__file__).resolve().parents[2] / "config/field_workflow.json"
        self.cfg = json.loads(source_cfg.read_text())
        self.evidence = self.directory / "TEST_ONLY_note.txt"
        self.evidence.write_text("UNIT TEST FIXTURE; not a field observation")
        self.report = self.directory / "selection_source.json"
        self.report.write_text("{}")
        self.registry = [{"route_id": "A01", "sampling_zone": "A", "lez2030_group": "inside",
            "policy_version": "LEZ2027_2030_LEZ_FIRST_v1", "route_version": "routehash1",
            "source_bundle_sha256": "bundlehash", "selected": "True"}]
        fw.write_csv(self.directory / "route_registry.csv", self.registry)
        fw.write_csv(self.directory / "route_part_registry.csv", [{"route_id": "A01", "part_id": "p1",
            "segment_id": "s1", "arc_id": "a1", "walk_order": 1}])
        fw.write_json(self.directory / "manifest.json", {"config": self.cfg, "fingerprint": "source1",
            "source_selection_report": str(self.report), "source_selection_report_sha256": fw.sha(self.report),
            "source_file_hashes": {str(self.evidence): fw.sha(self.evidence)}})
        fw.write_csv(self.directory / "field_observations.csv", [], fw.OBS_FIELDS)
        self.base = {f: "" for f in fw.OBS_FIELDS}
        self.base.update(observation_id="test01", route_id="A01", observed_at="2026-10-01T10:00:00+07:00",
            survey_date="2026-10-01", observer="TEST_ONLY", evidence_uri=str(self.evidence),
            evidence_type="field_note", evidence_source="field", field="G1", value="passed",
            status="observed", coverage="whole_route", sampling_zone="A", lez2030_group="inside",
            policy_version=self.registry[0]["policy_version"], route_version="routehash1",
            source_bundle_sha256="bundlehash", lez_status_at_survey="unknown")
        self.now = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def validate(self, rows):
        return fw.validate_observations(self.directory, rows, now=self.now)

    def record(self, field, value="passed", **kwargs):
        row = copy.deepcopy(self.base)
        row.update(observation_id=field, field=field, value=value)
        row.update(kwargs)
        return row

    def test_empty_input_stays_unknown(self):
        state = fw.status(self.directory)
        self.assertEqual(state["status"], "awaiting_field_observations")
        self.assertEqual(state["C6_unknown_count"], 1)
        self.assertFalse(state["surveyed_set_locked"])
        self.assertEqual(state["G1_G4_G5_G6_unknown_counts"], {"G1": 1, "G4": 1, "G5": 1, "G6": 1})

    def test_valid_field_gate_evidence(self):
        self.assertTrue(self.validate([self.base])["valid"])

    def test_reject_missing_actual_date(self):
        for key in ("observed_at", "survey_date", "observer", "evidence_uri"):
            row = self.record("G1", **{key: ""})
            with self.subTest(key=key):
                self.assertFalse(self.validate([row])["valid"])

    def test_reject_naive_and_future_and_wrong_date(self):
        examples = ["2026-10-01T10:00:00", "2027-01-01T10:00:00+07:00", "bad-date"]
        for value in examples:
            with self.subTest(value=value):
                self.assertFalse(self.validate([self.record("G1", observed_at=value)])["valid"])
        self.assertFalse(self.validate([self.record("G1", survey_date="2026-09-30")])["valid"])

    def test_hanoi_date_uses_local_timezone(self):
        row = self.record("G1", observed_at="2026-09-30T18:00:00Z", survey_date="2026-10-01")
        self.assertTrue(self.validate([row])["valid"])

    def test_reject_wrong_route_and_policy_snapshot(self):
        for key, value in [("route_id", "A99"), ("sampling_zone", "B"), ("lez2030_group", "outside"),
                           ("policy_version", "old"), ("route_version", "old_geometry"),
                           ("source_bundle_sha256", "old_bundle")]:
            with self.subTest(key=key):
                self.assertFalse(self.validate([self.record("G1", **{key: value})])["valid"])

    def test_reject_foreign_part_and_segment(self):
        self.assertFalse(self.validate([self.record("lanes", "2", unit="count", part_id="other", coverage="part")])["valid"])
        self.assertFalse(self.validate([self.record("lanes", "2", unit="count", segment_id="other", coverage="segment")])["valid"])
        self.assertTrue(self.validate([self.record("lanes", "2", unit="count", part_id="p1", segment_id="s1", coverage="part")])["valid"])

    def test_unknown_never_contains_fake_numeric_value(self):
        self.assertFalse(self.validate([self.record("lanes", "2", status="unknown", unit="count")])["valid"])
        self.assertTrue(self.validate([self.record("lanes", "", status="unknown", observed_at="", survey_date="")])["valid"])

    def test_wrong_units_and_nonfinite_values(self):
        for value in ("nan", "inf", "-1", "0", "not_numeric"):
            with self.subTest(value=value):
                self.assertFalse(self.validate([self.record("maxspeed", value, unit="km/h")])["valid"])
        self.assertFalse(self.validate([self.record("maxspeed", "50", unit="m/s")])["valid"])
        self.assertFalse(self.validate([self.record("lanes", "2.5", unit="count")])["valid"])

    def test_duplicate_id_and_conflicting_simultaneous_values(self):
        self.assertFalse(self.validate([self.base, self.base])["valid"])
        rows = [self.record("lanes", "2", unit="count"), self.record("lanes", "3", observation_id="second", unit="count")]
        self.assertFalse(self.validate(rows)["valid"])

    def test_missing_evidence_file_and_actual_policy_evidence(self):
        self.assertFalse(self.validate([self.record("G1", evidence_uri=str(self.directory / "missing.jpg"))])["valid"])
        self.assertFalse(self.validate([self.record("G1", lez_status_at_survey="inside")])["valid"])
        self.assertTrue(self.validate([self.record("G1", lez_status_at_survey="inside", policy_evidence_uri=str(self.evidence))])["valid"])

    def test_desk_evidence_does_not_pass_field_gate(self):
        row = self.record("G1", evidence_source="desk", evidence_type="desk_note")
        self.assertTrue(self.validate([row])["valid"])
        state = fw.assess_routes(self.registry, [row], self.cfg)[0]
        self.assertEqual(state["G1"], "unknown")

    def test_partial_route_gate_is_rejected(self):
        self.assertFalse(self.validate([self.record("G1", part_id="p1", coverage="part")])["valid"])

    def test_G5_requires_two_distinct_dates(self):
        first = self.record("G5")
        state = fw.assess_routes(self.registry, [first], self.cfg)[0]
        self.assertEqual(state["G5"], "unknown")
        same_day = self.record("G5", observation_id="rep2", observed_at="2026-10-01T11:00:00+07:00")
        self.assertEqual(fw.assess_routes(self.registry, [first, same_day], self.cfg)[0]["G5"], "unknown")
        other_day = self.record("G5", observation_id="rep2", observed_at="2026-09-30T11:00:00+07:00", survey_date="2026-09-30")
        self.assertEqual(fw.assess_routes(self.registry, [first, other_day], self.cfg)[0]["G5"], "passed")

    def test_G5_failure_resets_the_repeat_evidence(self):
        old = self.record("G5", observation_id="old", observed_at="2026-09-29T10:00:00+07:00", survey_date="2026-09-29")
        fail = self.record("G5", "failed", observation_id="fail", observed_at="2026-09-30T10:00:00+07:00", survey_date="2026-09-30")
        new = self.record("G5")
        self.assertEqual(fw.assess_routes(self.registry, [old, fail, new], self.cfg)[0]["G5"], "unknown")

    def test_raw_import_preserves_BOM_and_bytes(self):
        incoming = self.directory / "TEST_ONLY_bom.csv"
        fw.write_csv(incoming, [self.base], fw.OBS_FIELDS)
        raw = b"\xef\xbb\xbf" + incoming.read_bytes()
        incoming.write_bytes(raw)
        self.assertTrue(fw.import_observations(self.directory, incoming)["valid"])
        archived = self.directory / "imports" / (fw.sha(incoming)[:20] + ".csv")
        self.assertEqual(archived.read_bytes(), raw)

    def test_G6_requires_both_safe_anchors(self):
        state = fw.assess_routes(self.registry, [self.record("G6_start")], self.cfg)[0]
        self.assertEqual(state["G6"], "unknown")
        state = fw.assess_routes(self.registry, [self.record("G6_start"), self.record("G6_end")], self.cfg)[0]
        self.assertEqual(state["G6"], "passed")

    def complete_evidence(self):
        records = [self.record(f) for f in ("G1", "G4", "G5", "G6_start", "G6_end")]
        records.append(self.record("G5", observation_id="repeat", observed_at="2026-09-30T10:00:00+07:00", survey_date="2026-09-30"))
        rubric = self.cfg["c6"]["rubric_version"]
        records.extend(self.record(f, "no_limitation", rubric_version=rubric) for f in self.cfg["c6"]["supporting_fields"])
        records.append(self.record("C6", "5", unit="score_0_to_5", rubric_version=rubric))
        return records

    def test_C6_requires_supporting_fields_and_gates(self):
        records = self.complete_evidence()
        self.assertTrue(self.validate(records)["valid"])
        full = fw.assess_routes(self.registry, records, self.cfg)[0]
        self.assertEqual(full["C6"], "5")
        missing = [r for r in records if r["field"] != "C6_gps"]
        self.assertEqual(fw.assess_routes(self.registry, missing, self.cfg)[0]["C6"], "")
        no_G1 = [r for r in records if r["field"] != "G1"]
        self.assertEqual(fw.assess_routes(self.registry, no_G1, self.cfg)[0]["C6"], "")

    def test_C6_range_rubric_and_integer(self):
        for value in ("-1", "6", "2.5"):
            with self.subTest(value=value):
                self.assertFalse(self.validate([self.record("C6", value, unit="score_0_to_5", rubric_version=self.cfg["c6"]["rubric_version"])])["valid"])
        self.assertFalse(self.validate([self.record("C6", "5", unit="score_0_to_5", rubric_version="invented")])["valid"])

    def test_failed_gate_blocks_positive_C6(self):
        rows = self.complete_evidence()
        next(r for r in rows if r["field"] == "G1")["value"] = "failed"
        assessment = fw.assess_routes(self.registry, rows, self.cfg)[0]
        self.assertEqual(assessment["G1"], "failed")
        self.assertEqual(assessment["C6"], "")
        self.assertEqual(assessment["decision_status"], "proposed_replace_or_repair")

    def test_policy_review_can_resolve_previous_unknown_without_editing_history(self):
        rows = self.complete_evidence()
        policy = self.record("policy_status", "inside", observation_id="dated_policy_review", policy_evidence_uri=str(self.evidence))
        self.assertTrue(self.validate([policy])["valid"])
        assessment = fw.assess_routes(self.registry, rows + [policy], self.cfg)[0]
        self.assertEqual(assessment["actual_date_policy_review"], "evidence_recorded")
        self.assertEqual(assessment["decision_status"], "eligible_for_manual_surveyed_set_review")
        self.assertEqual(rows[0]["lez_status_at_survey"], "unknown")

    def test_explicit_policy_status_requires_policy_source(self):
        self.assertFalse(self.validate([self.record("policy_status", "inside")])["valid"])

    def test_complete_evidence_still_does_not_lock_set(self):
        rows = self.complete_evidence()
        for row in rows:
            row["lez_status_at_survey"] = "inside"
            row["policy_evidence_uri"] = str(self.evidence)
        assessment = fw.assess_routes(self.registry, rows, self.cfg)[0]
        self.assertEqual(assessment["decision_status"], "eligible_for_manual_surveyed_set_review")
        self.assertFalse(assessment["surveyed_set_locked"])

    def test_import_is_idempotent_and_correction_does_not_overwrite(self):
        incoming = self.directory / "TEST_ONLY_import.csv"
        fw.write_csv(incoming, [self.base], fw.OBS_FIELDS)
        self.assertTrue(fw.import_observations(self.directory, incoming)["valid"])
        again = fw.import_observations(self.directory, incoming)
        self.assertEqual(again["idempotent_ignored_count"], 1)
        changed = copy.deepcopy(self.base)
        changed["value"] = "failed"
        fw.write_csv(incoming, [changed], fw.OBS_FIELDS)
        self.assertFalse(fw.import_observations(self.directory, incoming)["valid"])
        self.assertEqual(fw.read_csv(self.directory / "field_observations.csv")[0]["value"], "passed")

    def test_stale_same_id_geometry_source_blocks_import(self):
        self.evidence.write_text("changed immutable fixture geometry source")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            fw.assert_current_source(self.directory)

    def test_changed_selection_report_blocks_import(self):
        self.report.write_text('{"new": true}')
        with self.assertRaisesRegex(ValueError, "Selection changed"):
            fw.assert_current_source(self.directory)

    def test_malformed_csv_header_and_width(self):
        p = self.directory / "malformed.csv"
        for content in ("a,a\n1,2\n", "a,b\n1,2,3\n", "a,b\n1\n"):
            p.write_text(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                fw.read_csv(p)


if __name__ == "__main__":
    unittest.main()
