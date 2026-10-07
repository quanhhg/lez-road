"""Notebook/CLI entry point; launches the registered PyQGIS runtime when needed."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "lez"

from .common import WORK, atomic_json, event, file_hash, input_path, now, processing_lock, publish_link, relative, write_csv


def kernel_spec():
    candidates = [Path.home() / "Library/Jupyter/kernels/pyqgis-423/kernel.json",
                  Path.home() / ".local/share/jupyter/kernels/pyqgis-423/kernel.json"]
    for path in candidates:
        if path.exists():
            spec = json.loads(path.read_text())
            if Path(spec["argv"][0]).is_file():
                return spec
    raise RuntimeError("The registered Python (PyQGIS 4.2.3) kernel was not found. Configure that runtime before processing geometry.")


def preflight(work=WORK, tile_ids=None):
    from .osm_index import inventory
    work = Path(work)
    sources = inventory(work, tile_ids)
    required = ["boundary_project.json", "boundary_sources.json", "legal_pdf_sources.json", "strata_mapping.csv", "access_rules.json"]
    for name in required:
        if not (work / "config" / name).is_file():
            raise ValueError("Missing config: " + name)
    spec = kernel_spec()
    env = os.environ.copy();env.update(spec.get("env", {}))
    check = subprocess.run([spec["argv"][0], "-c", "import json;from qgis.core import Qgis;import requests;print(json.dumps({'qgis':Qgis.QGIS_VERSION}))"], env=env, capture_output=True, text=True, timeout=30)
    if check.returncode:
        raise RuntimeError("PyQGIS runtime check failed: " + check.stderr[-2500:])
    boundary = json.loads((work / "config/boundary_project.json").read_text())
    return {"snapshot_utc": sources["snapshot_utc"], "active_tiles": sources["active_tiles"],
            "selected_tiles": sources["selected_tiles"], "is_full_scope": sources["is_full_scope"],
            "raw_hashes_and_manifests_match": True, "qgis": json.loads(check.stdout.strip())["qgis"],
            "lez_polygon_configured": bool(boundary["lez_source"].get("path")),
            "network_calls": 0, "raw_osm_modified": False}


def status(work=WORK):
    path = Path(work) / "reports/lez/latest_pipeline.json"
    return json.loads(path.read_text()) if path.exists() else {"status": "not_run"}


def output_path(result, name, work=WORK):
    return input_path(work, result["paths"][name])


def _publish_review_lists(work, network_dir):
    import sqlite3
    folder = Path(work) / "reports/network"
    database = Path(network_dir) / "network_tables.sqlite"
    queries = {
        "restrictions_to_review.csv": "SELECT * FROM restrictions WHERE status='review_required' ORDER BY restriction_id",
        "segments_to_review.csv": "SELECT segment_id,way_id,from_node,to_node,length_m,scope_length_m,access_status,rc,reason,tags_json,tile_ids FROM segments WHERE access_status='review_required' ORDER BY segment_id",
        "geometry_to_review.csv": "SELECT * FROM issues ORDER BY object_id",
    }
    summary = {"network_dir": relative(network_dir, work), "recorded_at": now(), "files": {}}
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for name, query in queries.items():
            cursor = connection.execute(query)
            fields = [column[0] for column in cursor.description]
            rows = [dict(row) for row in cursor]
            destination = folder / name
            write_csv(destination, rows, fields)
            summary["files"][name] = {"path": relative(destination, work), "rows": len(rows), "sha256": file_hash(destination)}
    atomic_json(folder / "review_lists.json", summary)
    return summary


def run_pipeline(work=WORK, stage="all", tile_ids=None, force=False, fetch_sources=True, progress=print):
    if stage not in {"all", "boundaries", "network"}:
        raise ValueError("stage must be all, boundaries, or network")
    work = Path(work).resolve()
    spec = kernel_spec()
    env = os.environ.copy();env.update(spec.get("env", {}));env["PYTHONUNBUFFERED"] = "1"
    args = [spec["argv"][0], str(Path(__file__).resolve()), "run", "--worker", "--work", str(work), "--stage", stage]
    if force:args.append("--force")
    if not fetch_sources:args.append("--no-fetch-sources")
    if tile_ids is not None:
        if not tile_ids:raise ValueError("An empty tile_ids list is not an all-tiles request")
        args += ["--tile-ids", *tile_ids]
    process = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    recent = deque(maxlen=20)
    result = None
    try:
        for line in process.stdout:
            recent.append(line.rstrip())
            try:message = json.loads(line)
            except ValueError:
                if progress:progress(line.rstrip())
                continue
            if message.get("event") == "result":
                result = message["result"]
            elif progress:
                if message.get("event") == "progress":
                    details = {k:v for k,v in message.items() if k not in {"event","stage","message"}}
                    progress(f"[{message['stage']}] {message['message']} {details}")
                else:progress(message)
        code = process.wait()
        if code or result is None:
            raise RuntimeError("Pipeline worker failed:\n" + "\n".join(recent))
        return result
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate();process.wait(timeout=10)
        if progress:progress("Đã dừng. Các giai đoạn đã có manifest hoàn chỉnh được giữ lại để tiếp tục.")
        return status(work)


def worker(args):
    from .boundaries import capture_sources, prepare
    from .osm_index import build_index
    from .network import build_network
    work = Path(args.work).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    report = {"run_id": run_id, "started_at": now(), "status": "running", "paths": {}, "cache_hits": {}}
    with processing_lock(work):
        run_file = work / "reports/lez/runs" / (run_id + ".json")
        try:
            if not args.no_fetch_sources and args.stage in {"all", "boundaries"}:
                from .legal_sources import archive_sources
                report["source_capture"] = {"html": capture_sources(work), "pdf": archive_sources(work)}
            boundaries_dir, boundary_report, hit = prepare(work, args.force)
            report.update(boundaries=boundary_report, stage_a_complete=boundary_report["stage_a_complete"])
            report["paths"]["zones"] = relative(boundaries_dir / "zones.gpkg", work)
            report["paths"]["boundaries_dir"] = relative(boundaries_dir, work)
            report["cache_hits"]["boundaries"] = hit
            publish_link(work, "zones.gpkg", boundaries_dir / "zones.gpkg")
            atomic_json(run_file, report)
            if args.stage in {"all", "network"}:
                index_dir, index_report, hit = build_index(work, args.tile_ids, args.force)
                report["index"] = {k:v for k,v in index_report.items() if k != "tiles"}
                report["paths"]["index_dir"] = relative(index_dir, work)
                report["cache_hits"]["index"] = hit
                atomic_json(run_file, report)
                network_dir, network_report, hit = build_network(work, index_dir, index_report, boundaries_dir, args.force)
                report["network"] = network_report
                report["cache_hits"]["network"] = hit
                report["paths"].update(network_dir=relative(network_dir, work), network=relative(network_dir / "network.gpkg", work), graph=relative(network_dir / "motorcycle_graph.json.gz", work))
                if index_report["is_full_scope"]:
                    publish_link(work, "network.gpkg", network_dir / "network.gpkg")
                    publish_link(work, "motorcycle_graph.json.gz", network_dir / "motorcycle_graph.json.gz")
                    report["review_lists"] = _publish_review_lists(work, network_dir)
            report.update(status="processed" if report["stage_a_complete"] else "processed_with_pending_boundary_inputs", finished_at=now())
        except KeyboardInterrupt:
            report.update(status="interrupted", finished_at=now())
            atomic_json(run_file, report);atomic_json(work / "reports/lez/latest_pipeline.json", report)
            raise
        except Exception as exc:
            report.update(status="failed", error=str(exc), finished_at=now())
            atomic_json(run_file, report);atomic_json(work / "reports/lez/latest_pipeline.json", report)
            raise
        atomic_json(run_file, report)
        atomic_json(work / "reports/lez/latest_pipeline.json", report)
        print(json.dumps({"event":"result","result":report},ensure_ascii=False),flush=True)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "run", "status"])
    parser.add_argument("--work", default=str(WORK))
    parser.add_argument("--stage", choices=["all", "boundaries", "network"], default="all")
    parser.add_argument("--tile-ids", nargs="+")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-fetch-sources", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
    elif args.command == "check":
        print(json.dumps(preflight(args.work,args.tile_ids),ensure_ascii=False,indent=2))
    elif args.command == "status":
        print(json.dumps(status(args.work),ensure_ascii=False,indent=2))
    else:
        result = run_pipeline(args.work,args.stage,args.tile_ids,args.force,not args.no_fetch_sources)
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
