"""Offline regression tests. HTTP responses are mocked; real API is never called."""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "overpass"))

import requests
import download_tiles as d


def payload(empty=False):
    meta = dict(version=1, timestamp="2026-09-30T00:00:00Z")
    objects = [] if empty else [
        dict(type="node", id=1, lat=21.0, lon=105.8, **meta),
        dict(type="node", id=2, lat=21.01, lon=105.81, **meta),
        dict(type="way", id=10, nodes=[1, 2], tags={"highway": "residential"}, **meta),
        dict(type="relation", id=20, members=[dict(type="way", ref=10, role="from")], **meta),
    ]
    objects.append(dict(type="count", tags={"nodes": "0" if empty else "2", "ways": "0" if empty else "1",
                                            "relations": "0" if empty else "1", "total": "0" if empty else "4"}))
    return dict(osm3s={"timestamp_osm_base": "2026-10-02T00:00:00Z"}, elements=objects)


def response(value=None, status=200, headers=None):
    r = requests.Response()
    r.status_code = status
    r.url = "https://overpass-api.de/api/interpreter"
    r._content = value if isinstance(value, bytes) else json.dumps(value or payload(), indent=3).encode()
    r._content_consumed = True
    r.headers.update(headers or {"Content-Type": "application/json"})
    return r


class FakeSession:
    def __init__(self, items, status_text="2 slots available now."):
        self.items = list(items)
        self.calls = []
        self.headers = {}
        self.status_text = status_text
        self.closed = False
        self.gets = []

    def post(self, endpoint, **kwargs):
        self.calls.append((endpoint, kwargs))
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def get(self, endpoint, **kwargs):
        self.gets.append(endpoint)
        return response(self.status_text.encode())

    def close(self):
        self.closed = True


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="overpass-offline-")
        self.root = Path(self.temp.name)
        source = d.ROOT
        self.config = json.loads((source / "tile_project.json").read_text())
        self.tiles = json.loads((source / "tiles_history.json").read_text())[:3]
        self.fields = list(d.CORE_FIELDS) + ["status"]
        (self.root / "queries").mkdir()
        for tile in self.tiles:
            tile["status"] = "pending"
            for key in d.PROGRESS_FIELDS:
                tile.pop(key, None)
            (self.root / tile["query_file"]).write_bytes((source / tile["query_file"]).read_bytes())
        self.save()
        self.options = d.DownloadOptions(interval_seconds=0, backoff_base_seconds=0,
                                         backoff_max_seconds=0, jitter_seconds=0, max_attempts=2)
        self.sleeps = []

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        d.atomic_json(self.root / "tile_project.json", self.config)
        d.atomic_json(self.root / "tiles_history.json", self.tiles)
        d.atomic_bytes(self.root / "tiles.csv", d.csv_bytes(self.tiles, self.fields))

    def run_fake(self, items, ids=None, options=None, status_text="2 slots available now."):
        fake = FakeSession(items, status_text)
        with patch.object(d.requests, "Session", return_value=fake):
            report = d.run_download(self.root, options or self.options, progress=None,
                                    tile_ids=ids, _sleep=self.sleeps.append)
        self.assertTrue(fake.closed)
        return report, fake

    def one(self):
        return [self.tiles[0]["tile_id"]]

    def test_preflight_offline_no_qgis(self):
        with patch.object(d.requests, "Session", side_effect=AssertionError("Network forbidden")):
            check = d.preflight(self.root)
        self.assertEqual(check["active_tiles"], 3)
        self.assertEqual(check["network_calls"], 0)
        self.assertFalse(any(name == "qgis" or name.startswith("qgis.") for name in sys.modules))

    def test_relocated_reports_and_cache_resume(self):
        workspace = self.root
        self.root = workspace / "data" / "hanoi_tiles"
        self.root.mkdir(parents=True)
        shutil.copytree(workspace / "queries", self.root / "queries")
        self.save()
        d.atomic_json(self.root / "project_layout.json", {
            "schema_version": 1,
            "workspace_root": "../..",
            "files": {"latest_run.json": "reports/overpass/latest_run.json"},
            "directories": {"runs": "reports/overpass/runs"},
        })
        first, _ = self.run_fake([response()], self.one())
        second, cached = self.run_fake([], self.one())
        self.assertEqual(first["new_downloads"], 1)
        self.assertEqual(second["cache_hits"], 1)
        self.assertEqual(cached.calls, [])
        reports = workspace / "reports" / "overpass"
        self.assertEqual(json.loads((reports / "latest_run.json").read_text())["run_id"], second["run_id"])
        self.assertTrue((reports / "runs" / (first["run_id"] + ".json")).is_file())
        self.assertFalse((self.root / "latest_run.json").exists())
        self.assertEqual(d.status_report(self.root)["latest_run"]["run_id"], second["run_id"])

    def test_relocated_output_cannot_escape_workspace(self):
        d.atomic_json(self.root / "project_layout.json", {
            "schema_version": 1,
            "workspace_root": "..",
            "files": {"latest_run.json": "../outside-project.json"},
        })
        with patch.object(d.requests, "Session", side_effect=AssertionError("Network forbidden")):
            with self.assertRaisesRegex(ValueError, "escapes"):
                d.preflight(self.root)

    def test_raw_bytes_and_verified_cache(self):
        original = response()
        raw = original.content
        first, fake = self.run_fake([original], self.one())
        target = self.root / self.tiles[0]["response_dir"]
        self.assertEqual((target / "response.json").read_bytes(), raw)
        self.assertEqual(fake.calls[0][1]["data"]["data"], (self.root / self.tiles[0]["query_file"]).read_text())
        self.assertFalse(fake.calls[0][1]["allow_redirects"])
        second, fake2 = self.run_fake([], self.one())
        self.assertEqual((first["new_downloads"], second["cache_hits"], second["http_requests"]), (1, 1, 0))
        self.assertEqual(fake2.calls, [])

    def test_pending_cache_recovers_done(self):
        self.run_fake([response()], self.one())
        with d.project_lock(self.root):
            p = d.read_project(self.root)
            d.set_status(p, p["rows"][0], "pending")
        report, fake = self.run_fake([], self.one())
        self.assertEqual(report["cache_hits"], 1)
        self.assertEqual(report["counts"]["done"], 1)
        self.assertEqual(fake.calls, [])

    def test_done_without_data_downloads_again(self):
        self.tiles[0]["status"] = "done"
        self.save()
        report, _ = self.run_fake([response()], self.one())
        self.assertEqual(report["invalid_caches"], 1)
        self.assertEqual(report["new_downloads"], 1)

    def test_corrupt_cache_preserved_and_only_one_redownload(self):
        ids = [t["tile_id"] for t in self.tiles[:2]]
        self.run_fake([response(), response()], ids)
        directory = self.root / self.tiles[0]["response_dir"]
        (directory / "response.json").write_bytes(b"corrupt original")
        report, fake = self.run_fake([response()], ids)
        self.assertEqual((report["new_downloads"], report["cache_hits"]), (1, 1))
        archives = list((directory / "archive").glob("*/response.json"))
        self.assertEqual(archives[0].read_bytes(), b"corrupt original")
        self.assertEqual(len(fake.calls), 1)

    def test_changed_query_not_reused(self):
        self.run_fake([response()], self.one())
        query = self.root / self.tiles[0]["query_file"]
        query.write_text(query.read_text().replace("timeout:180", "timeout:181"))
        report, _ = self.run_fake([response()], self.one())
        self.assertEqual(report["new_downloads"], 1)
        self.assertEqual(report["cache_hits"], 0)

    def test_empty_road_result_done(self):
        report, _ = self.run_fake([response(payload(True))], self.one())
        self.assertEqual(report["counts"]["done"], 1)
        self.assertEqual(report["empty_road_results"], 1)

    def test_nonstandard_json_is_never_done(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                malformed = payload()
                malformed["generator"] = value
                report, fake = self.run_fake([response(malformed), response(malformed)], self.one())
                self.assertEqual(report["new_downloads"], 0)
                self.assertEqual(report["counts"]["failed"], 1)
                self.assertEqual(len(fake.calls), 2)
                self.assertFalse((self.root / self.tiles[0]["response_dir"] / "response.json").exists())

    def test_failures_do_not_stop_other_tiles(self):
        report, fake = self.run_fake([response(b"parse error", 400), response(b"timeout", 504),
                                     response(b"timeout", 504), response()])
        self.assertEqual(report["counts"], dict(pending=0, done=1, failed=1, heavy=1))
        self.assertEqual(len(fake.calls), 4)
        self.assertTrue((self.root / self.tiles[0]["response_dir"] / "errors.jsonl").exists())

    def test_network_and_server_retry_bounded(self):
        report, fake = self.run_fake([requests.ConnectionError("offline"), response()], self.one())
        self.assertEqual(report["counts"]["done"], 1)
        self.assertEqual(len(fake.calls), 2)
        report, fake = self.run_fake([response(b"bad gateway", 502), response(b"bad gateway", 502)], [self.tiles[1]["tile_id"]])
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(len(fake.calls), 2)

    def test_429_retry_after_and_server_slot(self):
        timestamp = (datetime.now(timezone.utc) + timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
        report, fake = self.run_fake([response(b"rate limited", 429, {"Retry-After": "120"}), response()],
                                     self.one(), status_text="Slot available after: " + timestamp)
        self.assertEqual(report["counts"]["done"], 1)
        self.assertGreaterEqual(sum(self.sleeps), 299)
        self.assertEqual(fake.gets, ["https://overpass-api.de/api/status"])

    def test_429_last_attempt_cooldown_applies_to_next_tile(self):
        options = d.DownloadOptions(interval_seconds=0, backoff_base_seconds=0,
                                    backoff_max_seconds=0, jitter_seconds=0, max_attempts=1)
        report, _ = self.run_fake([response(b"rate limited", 429, {"Retry-After": "120"}), response()],
                                  [t["tile_id"] for t in self.tiles[:2]], options)
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(report["counts"]["done"], 1)
        self.assertGreaterEqual(sum(self.sleeps), 119)
        self.assertTrue((self.root / "download_cooldown.json").exists())

    def test_ctrl_c_and_resume(self):
        ids = [t["tile_id"] for t in self.tiles[:2]]
        first, _ = self.run_fake([response(), KeyboardInterrupt()], ids)
        self.assertTrue(first["interrupted"])
        self.assertEqual(first["counts"]["done"], 1)
        second, _ = self.run_fake([response()], ids)
        self.assertEqual((second["cache_hits"], second["new_downloads"]), (1, 1))

    def test_csv_history_transaction_recovers_after_partial_write(self):
        original = d.atomic_bytes
        def fail_csv(path, data):
            if Path(path).name == "tiles.csv":
                raise OSError("Simulated interrupted CSV write")
            return original(path, data)
        with d.project_lock(self.root):
            p = d.read_project(self.root)
            with patch.object(d, "atomic_bytes", side_effect=fail_csv):
                with self.assertRaises(OSError):
                    d.set_status(p, p["rows"][0], "done")
            self.assertTrue((self.root / ".tile_state_transaction.json").exists())
            restored = d.read_project(self.root)
        self.assertEqual(restored["rows"][0]["status"], "done")
        self.assertEqual(restored["history"][0]["status"], "done")
        self.assertFalse((self.root / ".tile_state_transaction.json").exists())

    def test_geometry_export_preserves_download_progress(self):
        self.run_fake([response()], self.one())
        stale = copy.deepcopy(self.tiles)
        merged = d.merge_download_progress(self.root, stale)
        self.assertEqual(merged[0]["status"], "done")
        with d.project_lock(self.root):
            d.persist_tile_state(self.root, merged, self.fields)
            p = d.read_project(self.root)
        self.assertEqual(p["rows"][0]["status"], "done")

    def test_split_tiles_are_skipped(self):
        self.tiles[0]["status"] = "split"
        self.save()
        (self.root / self.tiles[0]["query_file"]).unlink()
        report, fake = self.run_fake([response(), response()])
        self.assertEqual(report["active_tiles"], 2)
        self.assertEqual(len(fake.calls), 2)

    def test_preflight_rejects_duplicates_missing_query_snapshot_and_collision(self):
        for problem in ("duplicate", "query", "snapshot", "collision"):
            with self.subTest(problem=problem):
                saved = copy.deepcopy(self.tiles)
                if problem == "duplicate":
                    self.tiles.append(copy.deepcopy(self.tiles[0]))
                elif problem == "snapshot":
                    self.tiles[0]["snapshot_utc"] = "2099-01-01T00:00:00Z"
                elif problem == "collision":
                    self.tiles[1]["response_dir"] = self.tiles[0]["response_dir"]
                self.save()
                query = self.root / self.tiles[0]["query_file"]
                raw = query.read_bytes()
                if problem == "query":
                    query.unlink()
                with self.assertRaises(d.ProjectError):
                    d.preflight(self.root)
                query.write_bytes(raw)
                self.tiles = saved
                self.save()

    def test_validation_rejects_incomplete_and_wrong_snapshot(self):
        for problem in ("count", "fractional_count", "boolean_count", "node", "way", "relation", "timestamp", "base", "version", "remark", "malformed_meta"):
            with self.subTest(problem=problem):
                p = payload()
                if problem == "count": p["elements"][-1]["tags"]["total"] = "999"
                elif problem == "fractional_count": p["elements"][-1]["tags"]["ways"] = 1.5
                elif problem == "boolean_count": p["elements"][-1]["tags"]["ways"] = True
                elif problem == "node": p["elements"][0].pop("lat")
                elif problem == "way": p["elements"][2]["nodes"] = [1, 999]
                elif problem == "relation": p["elements"][3]["members"][0]["ref"] = 999
                elif problem == "timestamp": p["elements"][0]["timestamp"] = "2026-10-02T00:00:00Z"
                elif problem == "base": p["osm3s"]["timestamp_osm_base"] = "2026-09-01T00:00:00Z"
                elif problem == "version": p["elements"][0].pop("version")
                elif problem == "remark": p["remark"] = "runtime error: Query timed out"
                elif problem == "malformed_meta": p["osm3s"] = None
                with self.assertRaises(d.DownloadError):
                    d.validate_payload(p, d.parse_timestamp(self.config["snapshot_utc"]))

    def test_retry_after_date_and_slots_parser(self):
        value = (datetime.now(timezone.utc) + timedelta(seconds=120)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.assertGreater(d.retry_after_seconds(value), 118)
        self.assertEqual(d.retry_after_seconds("nonsense"), 0)
        self.assertEqual(d.slot_wait_seconds("Rate limit: 2\n0 slots available now."), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
