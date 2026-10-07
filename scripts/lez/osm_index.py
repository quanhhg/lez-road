"""Validate and deduplicate downloaded tiles without changing their raw bytes."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

from .common import WORK, atomic_json, cached_manifest, canonical, code_hash, commit_manifest, digest, event, file_hash, relative


def downloader(work):
    path = str(Path(work) / "scripts/overpass")
    if path not in sys.path:
        sys.path.insert(0, path)
    import download_tiles
    return download_tiles


def inventory(work=WORK, tile_ids=None):
    work = Path(work)
    root = work / "data/hanoi_tiles"
    config = json.loads((root / "tile_project.json").read_text())
    with (root / "tiles.csv").open(newline="", encoding="utf-8-sig") as stream:
        rows = [r for r in csv.DictReader(stream) if r["status"] != "split"]
    if len({r["tile_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate active tile_id")
    selected = None if tile_ids is None else set(tile_ids)
    if selected is not None and (not selected or not selected <= {r["tile_id"] for r in rows}):
        raise ValueError("tile_ids must be a nonempty subset of the active tiles")
    records = []
    for r in sorted(rows, key=lambda r: r["tile_id"]):
        if selected is not None and r["tile_id"] not in selected:
            continue
        if r["status"] != "done" or r["snapshot_utc"] != config["snapshot_utc"]:
            raise ValueError("Tile is not complete at the configured snapshot: " + r["tile_id"])
        destination = (root / r["response_dir"]).resolve()
        query = (root / r["query_file"]).resolve()
        if not destination.is_relative_to(root.resolve()) or not query.is_relative_to(root.resolve()):
            raise ValueError("A tile path escapes the data root")
        m = json.loads((destination / "manifest.json").read_text())
        expected = {"tile_id": r["tile_id"], "snapshot_utc": config["snapshot_utc"], "endpoint": config["endpoint"],
                    "bbox": [float(r[k]) for k in ("south", "west", "north", "east")],
                    "query_sha256": file_hash(query), "response_sha256": file_hash(destination / "response.json")}
        if any(m.get(k) != v for k, v in expected.items()) or m.get("http_status") != 200 or not m.get("validation", {}).get("passed"):
            raise ValueError("Invalid tile cache/hash: " + r["tile_id"])
        records.append(dict(expected, response_path=relative(destination / "response.json", work)))
    return {"snapshot_utc": config["snapshot_utc"], "endpoint": config["endpoint"],
            "metric_crs": config["metric_crs"], "active_tiles": len(rows), "selected_tiles": len(records),
            "is_full_scope": len(records) == len(rows), "tiles": records}


def merge_objects(conn, objects, tile_id, signatures):
    fresh, provenance = [], []
    for obj in objects:
        if obj["type"] == "count":
            continue
        key = obj["type"], obj["id"]
        payload = canonical(obj)
        signature = digest(obj)
        previous = signatures.get(key)
        if previous is not None and previous != signature:
            raise ValueError(f"Conflicting snapshot object {key[0]}/{key[1]} in tile {tile_id}; no version was silently selected")
        if previous is None:
            signatures[key] = signature
            fresh.append((*key, obj["version"], payload, signature))
        provenance.append((*key, tile_id))
    conn.executemany("INSERT INTO objects VALUES (?,?,?,?,?)", fresh)
    conn.executemany("INSERT INTO object_tiles VALUES (?,?,?)", provenance)
    return len(fresh)


def build_index(work=WORK, tile_ids=None, force=False):
    work = Path(work)
    sources = inventory(work, tile_ids)
    fp = digest({"schema": 1, "source": sources, "code": code_hash(["common.py", "osm_index.py"]),
                 "validator": file_hash(work / "scripts/overpass/download_tiles.py")})
    directory = work / "data/interim/osm" / fp[:20]
    cached = None if force else cached_manifest(directory, fp)
    if cached:
        event("index", "Đọc chỉ mục OSM đã kiểm tra", unique_objects=cached["report"]["unique_objects"])
        return directory, cached["report"], True
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / ".osm_index.building.sqlite"
    temp.unlink(missing_ok=True)
    conn = sqlite3.connect(temp)
    signatures = {}
    try:
        conn.executescript("""
          CREATE TABLE objects(type TEXT NOT NULL,id INTEGER NOT NULL,version INTEGER NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(type,id)) WITHOUT ROWID;
          CREATE TABLE object_tiles(type TEXT NOT NULL,id INTEGER NOT NULL,tile_id TEXT NOT NULL,PRIMARY KEY(type,id,tile_id)) WITHOUT ROWID;
        """)
        d = downloader(work)
        with d.project_lock(work / "data/hanoi_tiles"):
            project = d.read_project(work / "data/hanoi_tiles")
            by_id = {r["tile_id"]: r for r in project["rows"]}
            source_count = 0
            for i, record in enumerate(sources["tiles"], 1):
                tile = by_id[record["tile_id"]]
                manifest, error = d.check_cache(project, tile)
                if error or manifest["response_sha256"] != record["response_sha256"]:
                    raise ValueError(f"Cache changed or failed validation: {tile['tile_id']}: {error}")
                payload = d.decode_response_json(project["destinations"][tile["tile_id"]].joinpath("response.json").read_bytes())
                source_count += len(payload["elements"]) - 1
                merge_objects(conn, payload["elements"], tile["tile_id"], signatures)
                conn.commit()
                if i == 1 or i % 10 == 0 or i == len(sources["tiles"]):
                    event("index", "Ghép dữ liệu OSM", completed_tiles=i, total_tiles=len(sources["tiles"]), unique_objects=len(signatures))
        counts = dict(conn.execute("SELECT type,COUNT(*) FROM objects GROUP BY type"))
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Index integrity check failed")
        report = dict(sources, unique_objects=sum(counts.values()), counts=counts,
                      input_objects=source_count, duplicate_objects_removed=source_count-sum(counts.values()), conflicts=0,
                      raw_data_modified=False)
        conn.close()
        temp.replace(directory / "osm_index.sqlite")
        atomic_json(directory / "index_report.json", report)
        commit_manifest(directory, fp, report, ["osm_index.sqlite", "index_report.json"])
        return directory, report, False
    except BaseException:
        conn.close()
        raise


def open_index(directory):
    return sqlite3.connect(f"file:{Path(directory) / 'osm_index.sqlite'}?mode=ro", uri=True)
