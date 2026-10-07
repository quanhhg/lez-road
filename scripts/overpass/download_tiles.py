"""Sequential, resumable Overpass downloads. No QGIS dependency and no grid changes."""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import html
import inspect
import io
import json
import math
import os
import random
import re
import tempfile
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

from project_paths import DATA_ROOT, project_file

ROOT = DATA_ROOT
STATES = {"pending", "done", "failed", "heavy", "split"}
PROGRESS_FIELDS = ["last_error", "last_error_kind", "last_attempt_at", "completed_at",
                   "download_attempts", "empty_road_result"]
CORE_FIELDS = ["tile_id", "query_file", "response_dir", "snapshot_utc", "south", "west", "north", "east"]
LOCKS = {}


class ProjectError(ValueError):
    pass


class DownloadError(Exception):
    def __init__(self, message, kind="invalid_response", retryable=False, heavy=False,
                 http_status=None, retry_after=0):
        super().__init__(message)
        self.kind, self.retryable, self.heavy = kind, retryable, heavy
        self.http_status, self.retry_after = http_status, retry_after


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value):
    if not isinstance(value, str):
        raise ProjectError("Timestamp must be a string.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProjectError(f"Invalid timestamp: {value}") from exc
    if result.tzinfo is None:
        raise ProjectError("Timestamp must include its timezone.")
    return result.astimezone(timezone.utc)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())


def csv_bytes(rows, fields):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows({key: row.get(key, "") for key in fields} for row in rows)
    return output.getvalue().encode("utf-8-sig")


@contextmanager
def project_lock(root=ROOT):
    """One writer per project; nested geometry helpers can reuse their own lock."""
    root = Path(root).resolve()
    owner = (os.getpid(), threading.get_ident())
    key = str(root)
    if key in LOCKS and LOCKS[key][0] == owner:
        yield
        return
    handle = (root / ".tile_project.lock").open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProjectError("Another downloader/grid operation is running for this project.") from exc
        LOCKS[key] = (owner, handle)
        try:
            yield
        finally:
            LOCKS.pop(key, None)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def locked_project_operation(function):
    """Decorator used by build_tiles so verify/split cannot race with downloads."""
    signature = inspect.signature(function)
    @wraps(function)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        with project_lock(bound.arguments["root"]):
            recover_state(bound.arguments["root"])
            return function(*args, **kwargs)
    return wrapped


def recover_state(root):
    """Finish an interrupted CSV/history transaction; caller must hold the lock."""
    root = Path(root)
    journal = root / ".tile_state_transaction.json"
    if journal.exists():
        transaction = json.loads(journal.read_text(encoding="utf-8"))
        atomic_json(root / "tiles_history.json", transaction["history"])
        atomic_bytes(root / "tiles.csv", csv_bytes(transaction["rows"], transaction["fields"]))
        journal.unlink()


def persist_state(root, rows, history, fields):
    # The journal makes two atomic renames recoverable as one logical transaction.
    root = Path(root)
    journal = root / ".tile_state_transaction.json"
    atomic_json(journal, dict(rows=rows, history=history, fields=fields))
    recover_state(root)


def merge_download_progress(root, tiles):
    path = Path(root) / "tiles_history.json"
    if not path.exists():
        return tiles
    existing = {t["tile_id"]: t for t in json.loads(path.read_text(encoding="utf-8"))}
    merged = []
    for proposed in tiles:
        tile = dict(proposed)
        old = existing.get(tile["tile_id"])
        if old:
            if tile["status"] == "split" and old["status"] == "done":
                raise ProjectError("Cannot split a completed tile.")
            if tile["status"] != "split":
                tile["status"] = old["status"]
            for key in PROGRESS_FIELDS:
                if key in old:
                    tile[key] = old[key]
        merged.append(tile)
    return merged


def persist_tile_state(root, tiles, fields):
    fields = list(dict.fromkeys(list(fields) + [key for t in tiles for key in t]))
    rows = sorted((t for t in tiles if t["status"] != "split"), key=lambda t: t["tile_id"])
    persist_state(root, rows, tiles, fields)


@dataclass(frozen=True)
class DownloadOptions:
    interval_seconds: float = 15.0
    connect_timeout: float = 10.0
    read_timeout: float = 240.0
    max_attempts: int = 3
    backoff_base_seconds: float = 30.0
    backoff_max_seconds: float = 300.0
    jitter_seconds: float = 5.0
    retry_failed: bool = True
    retry_heavy: bool = True
    user_agent: str = "Hanoi-LEZ-research/0.2 (sequential Overpass downloader)"

    def validate(self):
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10:
            raise ProjectError("max_attempts must be an integer from 1 to 10.")
        for name in ("interval_seconds", "connect_timeout", "read_timeout", "backoff_base_seconds",
                     "backoff_max_seconds", "jitter_seconds"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ProjectError(f"{name} must be finite and nonnegative.")
        if min(self.connect_timeout, self.read_timeout) <= 0 or not self.user_agent.strip():
            raise ProjectError("Timeouts must be positive; User-Agent cannot be empty.")
        if self.backoff_max_seconds < self.backoff_base_seconds:
            raise ProjectError("backoff_max_seconds cannot be less than backoff_base_seconds.")


def safe_path(root, value):
    if not isinstance(value, str) or not value.strip():
        raise ProjectError("Missing input/output path.")
    path = (root / value).resolve()
    if path == root or not path.is_relative_to(root):
        raise ProjectError(f"Path escapes or replaces the project root: {value}")
    return path


def read_project(root):
    root = Path(root).resolve()
    recover_state(root)
    config = json.loads((root / "tile_project.json").read_text(encoding="utf-8"))
    # Validate report/map relocation before any request or progress write.
    project_file(root, "latest_run.json")
    project_file(root, "hanoi_download_grid.gpkg")
    if set(config.get("tile_status_values", [])) != STATES:
        raise ProjectError("tile_project.json must define pending/done/failed/heavy/split.")
    endpoint = config.get("endpoint", "")
    url = urlsplit(endpoint)
    if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password:
        raise ProjectError("Invalid configured HTTP endpoint.")
    if not url.path.rstrip("/").endswith("/interpreter") or url.query or url.fragment:
        raise ProjectError("Expected a configured Overpass interpreter endpoint.")
    snapshot = parse_timestamp(config.get("snapshot_utc"))
    if snapshot > datetime.now(timezone.utc):
        raise ProjectError("Snapshot is in the future.")
    with (root / "tiles.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    if not fields or any(key not in fields for key in CORE_FIELDS + ["status"]):
        raise ProjectError("CSV lacks required tile/configuration columns.")
    history = json.loads((root / "tiles_history.json").read_text(encoding="utf-8"))
    for name, records in (("CSV", rows), ("history", history)):
        ids = [t.get("tile_id") for t in records]
        if any(not isinstance(i, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids):
            raise ProjectError(f"Invalid tile_id in {name}.")
        if len(set(ids)) != len(ids):
            raise ProjectError(f"Duplicate tile_id in {name}.")
        if any(t.get("status") not in STATES for t in records):
            raise ProjectError(f"Unknown tile status in {name}.")
    by_id = {t["tile_id"]: t for t in history}
    active_ids = {t["tile_id"] for t in history if t["status"] != "split"}
    if {t["tile_id"] for t in rows if t["status"] != "split"} != active_ids:
        raise ProjectError("CSV and history disagree on active/split tile identities.")
    queries, destinations = {}, {}
    protected = [root / "queries", root / "data/raw"]
    protected += [root / n for n in ("tile_project.json", "tiles.csv", "tiles_history.json",
                                     "build_tiles.py", "download_tiles.py")]
    for tile in rows:
        tile_id = tile["tile_id"]
        if tile_id not in by_id:
            raise ProjectError(f"CSV tile absent from history: {tile_id}")
        historic = by_id[tile_id]
        for key in CORE_FIELDS:
            left, right = tile[key], historic.get(key)
            equal = (float(left) == float(right) if key in ("south", "west", "north", "east") else left == right)
            if not equal:
                raise ProjectError(f"CSV/history mismatch in {tile_id}: {key}")
        historic["status"] = tile["status"]
        for key in PROGRESS_FIELDS:
            if key in tile:
                value = tile[key]
                if key == "download_attempts" and value != "":
                    try:
                        value = int(value)
                    except (ValueError, TypeError) as exc:
                        raise ProjectError(f"Invalid attempt count for {tile_id}.") from exc
                    if value < 0:
                        raise ProjectError(f"Negative attempt count for {tile_id}.")
                elif key == "empty_road_result" and value != "":
                    if str(value).lower() not in ("true", "false"):
                        raise ProjectError(f"Invalid empty-road flag for {tile_id}.")
                    value = str(value).lower() == "true"
                historic[key] = value
            elif key in historic:
                tile[key] = historic[key]
        if tile["status"] == "split":
            continue
        if parse_timestamp(tile["snapshot_utc"]) != snapshot:
            raise ProjectError(f"Tile snapshot differs from project snapshot: {tile_id}")
        bbox = [float(tile[k]) for k in ("south", "west", "north", "east")]
        if not all(math.isfinite(v) for v in bbox) or not (-90 <= bbox[0] < bbox[2] <= 90 and -180 <= bbox[1] < bbox[3] <= 180):
            raise ProjectError(f"Invalid bbox: {tile_id}")
        query_path = safe_path(root, tile["query_file"])
        if not query_path.is_file():
            raise ProjectError(f"Query file missing: {query_path}")
        raw_query = query_path.read_bytes()
        query = raw_query.decode("utf-8")
        dates = re.findall(r'\[\s*date\s*:\s*"([^"]+)"\s*\]', query)
        if len(dates) != 1 or parse_timestamp(dates[0]) != snapshot:
            raise ProjectError(f"Query snapshot mismatch: {tile_id}")
        if not re.search(r'\[\s*out\s*:\s*json\s*\]', query) or not re.search(r'out\s+meta\s*;', query):
            raise ProjectError(f"Query must request JSON/meta: {tile_id}")
        if not re.search(r'out\s+count\s*;\s*$', query):
            raise ProjectError(f"Query must end with out count: {tile_id}")
        destination = safe_path(root, tile["response_dir"])
        if destination.exists() and not destination.is_dir():
            raise ProjectError(f"Response directory is a file: {tile_id}")
        if any(parent.exists() and not parent.is_dir() for parent in destination.parents if parent.is_relative_to(root)):
            raise ProjectError(f"Response parent path is a file: {tile_id}")
        for path in protected + [query_path] + list(destinations.values()):
            if destination == path or destination.is_relative_to(path) or path.is_relative_to(destination):
                raise ProjectError(f"Output directory collision: {tile_id}: {destination}")
        manifest_path = destination / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                manifest = {}
            if not isinstance(manifest, dict):
                manifest = {}
            if manifest.get("tile_id") not in (None, tile_id):
                raise ProjectError(f"Output belongs to another tile: {destination}")
        queries[tile_id] = dict(text=query, sha256=sha256(raw_query), path=query_path)
        destinations[tile_id] = destination
    for destination in destinations.values():
        for entry in queries.values():
            if destination == entry["path"] or entry["path"].is_relative_to(destination):
                raise ProjectError("Response directory overlaps a query file.")
    fields = list(dict.fromkeys(fields + PROGRESS_FIELDS))
    return dict(root=root, config=config, snapshot=snapshot, rows=rows, fields=fields,
                history=history, by_id=by_id, queries=queries, destinations=destinations)


def classify_message(message):
    text = message.lower()
    if any(s in text for s in ("parse error", "static error", "syntax error")):
        return "query_error", False, False
    if any(s in text for s in ("timed out", "timeout", "ran out of memory", "out of memory",
                               "too busy", "overload", "resource limit")):
        return "query_resource", True, True
    if "rate limit" in text or "too many requests" in text:
        return "rate_limit", True, False
    return "incomplete_response", True, False


def decode_response_json(raw):
    def reject_constant(value):
        raise ValueError(f"Non-standard JSON numeric constant: {value}")
    return json.loads(raw, parse_constant=reject_constant)


def validate_payload(payload, snapshot):
    def invalid(message):
        raise DownloadError(message, "incomplete_response", True)
    if not isinstance(payload, dict):
        invalid("JSON is not an object.")
    if payload.get("remark"):
        message = str(payload["remark"])
        kind, retryable, heavy = classify_message(message)
        raise DownloadError(message, kind, retryable, heavy)
    elements = payload.get("elements")
    if not isinstance(elements, list) or not elements:
        invalid("Missing elements/final count.")
    if any(not isinstance(e, dict) or e.get("type") not in {"node", "way", "relation", "count"} for e in elements):
        invalid("Unknown/malformed element.")
    if sum(e["type"] == "count" for e in elements) != 1 or elements[-1]["type"] != "count":
        invalid("Missing unique final count element.")
    objects = elements[:-1]
    counts = Counter(e["type"] for e in objects)
    reported = elements[-1].get("tags", {})
    if not isinstance(reported, dict):
        invalid("Malformed count tags.")
    expected_counts = {kind + "s": counts[kind] for kind in ("node", "way", "relation")}
    expected_counts["total"] = len(objects)
    for name, expected in expected_counts.items():
        value = reported.get(name)
        if type(value) is not int and not (isinstance(value, str) and re.fullmatch(r"[0-9]+", value)):
            invalid("Malformed count record: counts must be nonnegative integers.")
        try:
            if int(value) != expected:
                invalid("Object counts do not match the final count record.")
        except (TypeError, ValueError):
            invalid("Malformed count record.")
    index = {}
    for obj in objects:
        if type(obj.get("id")) is not int or obj["id"] <= 0:
            invalid("Invalid OSM id.")
        key = (obj["type"], obj["id"])
        if key in index:
            invalid(f"Duplicate object: {key}")
        index[key] = obj
    for obj in objects:
        kind, object_id = obj["type"], obj["id"]
        if "tags" in obj and not isinstance(obj["tags"], dict):
            invalid(f"{kind}/{object_id} has malformed tags.")
        if kind == "node":
            for name, limit in (("lat", 90), ("lon", 180)):
                value = obj.get(name)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
                    invalid(f"Node {object_id} lacks valid coordinates.")
        elif kind == "way":
            refs = obj.get("nodes")
            if not isinstance(refs, list) or len(refs) < 2 or any(type(n) is not int or ("node", n) not in index for n in refs):
                invalid(f"Way {object_id} has missing/invalid node references.")
        else:
            members = obj.get("members")
            if not isinstance(members, list) or any(not isinstance(m, dict) or m.get("type") not in ("node", "way", "relation") or type(m.get("ref")) is not int or (m["type"], m["ref"]) not in index for m in members):
                invalid(f"Relation {object_id} has missing/invalid members.")
        if type(obj.get("version")) is not int or obj["version"] < 1:
            invalid(f"{kind}/{object_id} lacks valid version metadata.")
        try:
            changed = parse_timestamp(obj.get("timestamp"))
        except ProjectError:
            invalid(f"{kind}/{object_id} lacks valid timestamp metadata.")
        if changed > snapshot:
            invalid(f"{kind}/{object_id} is newer than the requested snapshot.")
    osm3s = payload.get("osm3s")
    if not isinstance(osm3s, dict):
        invalid("Missing/invalid osm3s metadata.")
    try:
        base = parse_timestamp(osm3s.get("timestamp_osm_base"))
    except ProjectError:
        invalid("Missing/invalid timestamp_osm_base.")
    if base < snapshot:
        invalid("Server data has not reached the requested snapshot.")
    roads = sum(o["type"] == "way" and "highway" in o.get("tags", {}) for o in objects)
    return dict(passed=True, counts={k: counts[k] for k in ("node", "way", "relation")},
                total=len(objects), road_way_count=roads, empty_road_result=roads == 0,
                timestamp_osm_base=payload["osm3s"]["timestamp_osm_base"],
                checks=["final_count", "unique_typed_ids", "node_coordinates", "way_nodes",
                        "relation_members", "object_metadata", "snapshot", "no_error_remark"])


def check_cache(project, tile):
    destination = project["destinations"][tile["tile_id"]]
    raw_path, manifest_path = destination / "response.json", destination / "manifest.json"
    if not raw_path.exists() and not manifest_path.exists():
        return None, "missing"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifest is not a JSON object.")
        raw = raw_path.read_bytes()
        expected_bbox = [float(tile[k]) for k in ("south", "west", "north", "east")]
        expected = dict(tile_id=tile["tile_id"], endpoint=project["config"]["endpoint"],
                        snapshot_utc=tile["snapshot_utc"], bbox=expected_bbox,
                        query_sha256=project["queries"][tile["tile_id"]]["sha256"])
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise ValueError("Cache belongs to a different tile/query/snapshot/bbox/endpoint.")
        if manifest.get("response_sha256") != sha256(raw):
            raise ValueError("Response hash mismatch.")
        if manifest.get("http_status") != 200 or not isinstance(manifest.get("validation"), dict) or not manifest["validation"].get("passed"):
            raise ValueError("Manifest lacks successful HTTP/validation evidence.")
        validation = validate_payload(decode_response_json(raw), project["snapshot"])
        if validation != manifest.get("validation") or validation["counts"] != manifest.get("counts"):
            raise ValueError("Manifest validation/counts disagree with the raw response.")
        if manifest.get("empty_road_result") != validation["empty_road_result"]:
            raise ValueError("Manifest lacks matching empty-road result evidence.")
        parse_timestamp(manifest["request_started_at"])
        parse_timestamp(manifest["download_finished_at"])
        return manifest, None
    except (OSError, ValueError, TypeError, KeyError, DownloadError) as exc:
        return None, str(exc)


def state_counts(project):
    counts = Counter(t["status"] for t in project["rows"] if t["status"] != "split")
    return {state: counts[state] for state in ("pending", "done", "failed", "heavy")}


def set_status(project, tile, status, **progress):
    if status not in STATES or tile["status"] == "split":
        raise ProjectError("Invalid status update.")
    tile.update(status=status, **progress)
    project["by_id"][tile["tile_id"]].update(status=status, **progress)
    persist_state(project["root"], project["rows"], project["history"], project["fields"])


def preflight(root=ROOT, options=None):
    options = options or DownloadOptions()
    options.validate()
    with project_lock(root):
        project = read_project(root)
        return dict(passed=True, active_tiles=len(project["queries"]),
                    split_tiles=sum(t["status"] == "split" for t in project["history"]),
                    counts=state_counts(project), endpoint=project["config"]["endpoint"],
                    snapshot_utc=project["config"]["snapshot_utc"],
                    query_files_checked=len(project["queries"]), network_calls=0,
                    options=asdict(options))


def status_report(root=ROOT):
    with project_lock(root):
        project = read_project(root)
        problems = [{k: t.get(k, "") for k in ("tile_id", "status", "last_error_kind", "last_error", "download_attempts")}
                    for t in project["rows"] if t["status"] in ("failed", "heavy")]
        for problem in problems:
            problem["last_error"] = readable_error(problem["last_error"])
        latest = project_file(root, "latest_run.json")
        return dict(counts=state_counts(project), problems=problems,
                    latest_run=json.loads(latest.read_text()) if latest.exists() else None)


def readable_error(message):
    """Readable view of server HTML; original response/error logs are preserved."""
    text = html.unescape(re.sub(r"<[^>]*>", " ", str(message)))
    text = " ".join(text.split())
    match = re.search(r"(?:runtime|parse|static) error:", text, re.I)
    if match:
        prefix = re.match(r"HTTP \d+", text)
        return ((prefix.group(0) + ": ") if prefix else "") + text[match.start():]
    return text


def append_log(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def retry_after_seconds(value):
    if value is None:
        return 0.0
    try:
        return max(0.0, float(value))
    except (ValueError, TypeError):
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0.0


def slot_wait_seconds(text):
    """The 'Rate limit' line is total slots, not currently available slots."""
    if re.search(r'\b[1-9]\d*\s+slots? available now', text, re.I):
        return 0.0
    waits = []
    for timestamp in re.findall(r'Slot available after:\s*(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)', text):
        waits.append(max(0.0, (parse_timestamp(timestamp) - datetime.now(timezone.utc)).total_seconds()))
    return min(waits) + 1 if waits else 0.0


def server_wait(session, endpoint, options):
    url = urlsplit(endpoint)
    status_path = url.path.rstrip("/").removesuffix("/interpreter") + "/status"
    status_url = urlunsplit((url.scheme, url.netloc, status_path, "", ""))
    try:
        response = session.get(status_url, timeout=(options.connect_timeout, 30), allow_redirects=False)
        try:
            return slot_wait_seconds(response.text) if response.status_code == 200 else 0.0
        finally:
            response.close()
    except requests.RequestException:
        return 0.0


def interruptible_wait(seconds, emit, tile_id, reason, sleep_fn):
    remaining = max(0.0, seconds)
    while remaining > 0:
        step = min(30.0, remaining)
        emit("waiting", tile_id=tile_id, reason=reason, seconds_remaining=round(remaining, 1))
        sleep_fn(step)
        remaining -= step


def cooldown_seconds(project):
    path = project["root"] / "download_cooldown.json"
    if not path.exists():
        return 0.0
    cooldown = json.loads(path.read_text())
    if cooldown["endpoint"] != project["config"]["endpoint"]:
        return 0.0
    return max(0.0, (parse_timestamp(cooldown["not_before_utc"]) - datetime.now(timezone.utc)).total_seconds())


def save_cooldown(project, seconds, reason):
    seconds = max(seconds, cooldown_seconds(project))
    atomic_json(project["root"] / "download_cooldown.json",
                dict(endpoint=project["config"]["endpoint"], reason=reason,
                     not_before_utc=(datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()))


def log_error(project, tile, error, attempt=0, response_bytes=None):
    destination = project["destinations"][tile["tile_id"]]
    record = dict(timestamp=utc_now(), tile_id=tile["tile_id"], attempt=attempt,
                  kind=error.kind, message=str(error), http_status=error.http_status,
                  retryable=error.retryable, heavy=error.heavy,
                  snapshot_utc=tile["snapshot_utc"],
                  query_sha256=project["queries"][tile["tile_id"]]["sha256"])
    if response_bytes is not None:
        body = destination / "errors" / f"{uuid.uuid4().hex}.body"
        atomic_bytes(body, response_bytes)
        record["response_body_file"] = str(body.relative_to(project["root"]))
    append_log(destination / "errors.jsonl", record)
    return record


def request_tile(session, project, tile, options):
    endpoint = project["config"]["endpoint"]
    response = session.post(endpoint, data={"data": project["queries"][tile["tile_id"]]["text"]},
                            timeout=(options.connect_timeout, options.read_timeout), allow_redirects=False)
    try:
        raw = response.content
        status = response.status_code
        text = raw[:20000].decode("utf-8", errors="replace")
        after = retry_after_seconds(response.headers.get("Retry-After"))
        if status != 200:
            if status == 429:
                error = DownloadError("HTTP 429: " + text[:1200], "rate_limit", True, False, status, after)
            elif status == 504:
                error = DownloadError("HTTP 504: " + text[:1200], "query_resource", True, True, status, after)
            else:
                kind, retry, heavy = classify_message(text)
                if kind != "query_error" and status in (408, 425, 500, 502, 503):
                    kind, retry = "server_temporary", True
                elif status not in (408, 425, 500, 502, 503):
                    retry = False
                error = DownloadError(f"HTTP {status}: {text[:1200]}", kind, retry, heavy, status, after)
            error.response_bytes = raw
            raise error
        try:
            payload = decode_response_json(raw)
        except (ValueError, UnicodeError) as exc:
            kind, retry, heavy = classify_message(text)
            error = DownloadError("HTTP 200 without valid JSON: " + text[:1200], kind, retry, heavy, status, after)
            error.response_bytes = raw
            raise error from exc
        try:
            validation = validate_payload(payload, project["snapshot"])
        except DownloadError as error:
            error.http_status, error.retry_after, error.response_bytes = status, after, raw
            raise
        return raw, validation, dict(http_status=status, endpoint_returned=response.url,
                                     content_type=response.headers.get("Content-Type"))
    finally:
        response.close()


def save_response(project, tile, raw, validation, evidence, started_at, attempt):
    destination = project["destinations"][tile["tile_id"]]
    # Preserve previous bytes (including corrupt caches) instead of editing raw OSM.
    present = [destination / name for name in ("response.json", "manifest.json") if (destination / name).exists()]
    if present:
        archive = destination / "archive" / uuid.uuid4().hex
        archive.mkdir(parents=True)
        for path in present:
            atomic_bytes(archive / path.name, path.read_bytes())
    manifest = dict(tile_id=tile["tile_id"], bbox=[float(tile[k]) for k in ("south", "west", "north", "east")],
                    bbox_order="south,west,north,east", snapshot_utc=tile["snapshot_utc"],
                    endpoint=project["config"]["endpoint"], **evidence,
                    query_file=tile["query_file"], query_sha256=project["queries"][tile["tile_id"]]["sha256"],
                    response_sha256=sha256(raw), request_started_at=started_at, download_finished_at=utc_now(),
                    counts=validation["counts"], validation=validation, attempt_in_run=attempt,
                    empty_road_result=validation["empty_road_result"])
    atomic_bytes(destination / "response.json", raw)
    atomic_json(destination / "manifest.json", manifest)
    return manifest


def print_progress(event):
    kind, tile_id = event["event"], event.get("tile_id", "")
    if kind == "waiting":
        print(f"  {tile_id}: wait {event['seconds_remaining']}s ({event['reason']})", flush=True)
    elif kind in ("start", "done", "cache", "failed", "heavy", "retry", "interrupted", "finished", "cache_invalid"):
        counts = event.get("counts", {})
        extra = readable_error(event.get("message", ""))
        print(f"[{kind}] {tile_id} {counts} {extra}".strip(), flush=True)


def run_download(root=ROOT, options=None, progress=print_progress, tile_ids=None, *, _sleep=time.sleep):
    """Run all eligible active tiles. Re-running first validates every selected cache."""
    options = options or DownloadOptions()
    options.validate()
    root = Path(root).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    start_clock = time.monotonic()
    started = utc_now()
    with project_lock(root):
        project = read_project(root)
        selected = [t for t in project["rows"] if t["status"] != "split"]
        if tile_ids is not None:
            requested = set(tile_ids)
            if requested - {t["tile_id"] for t in selected}:
                raise ProjectError("Requested unknown/split tile IDs.")
            selected = [t for t in selected if t["tile_id"] in requested]
        # Also reconcile pre-existing CSV/history status differences before the run.
        persist_state(root, project["rows"], project["history"], project["fields"])
        stats = dict(new_downloads=0, cache_hits=0, attempted_tiles=0, http_requests=0,
                     invalid_caches=0, interrupted=False, empty_road_results=0, skipped_tiles=0)
        session = None
        current = None
        last_post_clock = None

        def emit(kind, **data):
            event = dict(timestamp=utc_now(), event=kind, run_id=run_id, counts=state_counts(project), **data)
            append_log(project_file(root, f"runs/{run_id}.events.jsonl"), event)
            if progress is not None:
                progress(event)

        try:
            session = requests.Session()
            session.headers.update({"User-Agent": options.user_agent})
            for position, tile in enumerate(selected, 1):
                current = tile
                manifest, cache_error = check_cache(project, tile)
                if manifest is not None:
                    set_status(project, tile, "done", last_error="", last_error_kind="",
                               completed_at=manifest["download_finished_at"],
                               empty_road_result=manifest["empty_road_result"])
                    stats["cache_hits"] += 1
                    stats["empty_road_results"] += int(manifest["empty_road_result"])
                    emit("cache", tile_id=tile["tile_id"], position=position, total=len(selected))
                    current = None
                    continue
                if cache_error != "missing" or tile["status"] == "done":
                    stats["invalid_caches"] += 1
                    error = DownloadError("Cache requires download: " + cache_error, "cache_invalid")
                    log_error(project, tile, error)
                    set_status(project, tile, "pending", last_error=str(error), last_error_kind=error.kind)
                    emit("cache_invalid", tile_id=tile["tile_id"], message=str(error))
                if (tile["status"] == "failed" and not options.retry_failed) or (tile["status"] == "heavy" and not options.retry_heavy):
                    stats["skipped_tiles"] += 1
                    current = None
                    continue
                stats["attempted_tiles"] += 1
                emit("start", tile_id=tile["tile_id"], position=position, total=len(selected))
                resource_error_seen = False
                for attempt in range(1, options.max_attempts + 1):
                    if last_post_clock is not None:
                        delay = max(0.0, options.interval_seconds - (time.monotonic() - last_post_clock))
                        interruptible_wait(delay, emit, tile["tile_id"], "request interval", _sleep)
                    interruptible_wait(cooldown_seconds(project), emit, tile["tile_id"], "server cooldown", _sleep)
                    attempt_started = utc_now()
                    attempts_so_far = int(tile.get("download_attempts") or 0)
                    set_status(project, tile, "pending", last_attempt_at=attempt_started,
                               download_attempts=attempts_so_far + 1)
                    stats["http_requests"] += 1
                    try:
                        raw, validation, evidence = request_tile(session, project, tile, options)
                    except requests.RequestException as exc:
                        error = DownloadError(f"{type(exc).__name__}: {exc}", "network_error", True)
                    except DownloadError as exc:
                        error = exc
                    else:
                        last_post_clock = time.monotonic()
                        manifest = save_response(project, tile, raw, validation, evidence, attempt_started, attempt)
                        set_status(project, tile, "done", last_error="", last_error_kind="",
                                   completed_at=manifest["download_finished_at"],
                                   empty_road_result=manifest["empty_road_result"])
                        stats["new_downloads"] += 1
                        stats["empty_road_results"] += int(manifest["empty_road_result"])
                        emit("done", tile_id=tile["tile_id"], validation=validation)
                        break
                    last_post_clock = time.monotonic()
                    resource_error_seen |= error.heavy
                    log_error(project, tile, error, attempt, getattr(error, "response_bytes", None))
                    server_delay = server_wait(session, project["config"]["endpoint"], options) if error.kind == "rate_limit" else 0
                    server_minimum = max(error.retry_after, server_delay, 15 if error.kind == "rate_limit" else 0)
                    if server_minimum > 0:
                        save_cooldown(project, server_minimum, error.kind)
                    if not error.retryable or attempt == options.max_attempts:
                        status = "heavy" if resource_error_seen and error.kind != "query_error" else "failed"
                        set_status(project, tile, status, last_error=str(error), last_error_kind=error.kind)
                        emit(status, tile_id=tile["tile_id"], message=readable_error(str(error)))
                        break
                    backoff = min(options.backoff_max_seconds, options.backoff_base_seconds * 2**(attempt-1))
                    # Retry-After and slot times are lower bounds; never truncate them to the backoff cap.
                    delay = max(backoff, server_minimum) + random.uniform(0, options.jitter_seconds)
                    emit("retry", tile_id=tile["tile_id"], attempt=attempt, delay_seconds=round(delay, 1), message=readable_error(str(error)))
                    interruptible_wait(delay, emit, tile["tile_id"], error.kind, _sleep)
                current = None
        except KeyboardInterrupt:
            stats["interrupted"] = True
            recover_state(root)
            if current is not None:
                error = DownloadError("Interrupted; resume will validate cache before sending another request.", "interrupted")
                log_error(project, current, error)
            emit("interrupted", tile_id=current["tile_id"] if current else "")
        finally:
            if session is not None:
                session.close()
            latest_project = read_project(root)
            report = dict(run_id=run_id, started_at=started, finished_at=utc_now(),
                          elapsed_seconds=round(time.monotonic()-start_clock, 3),
                          endpoint=project["config"]["endpoint"], snapshot_utc=project["config"]["snapshot_utc"],
                          selected_tiles=len(selected), active_tiles=len(project["queries"]),
                          options=asdict(options), **stats, counts=state_counts(latest_project),
                          problems=[{k: t.get(k, "") for k in ("tile_id", "status", "last_error_kind", "last_error")}
                                    for t in latest_project["rows"] if t["status"] in ("failed", "heavy")])
            atomic_json(project_file(root, f"runs/{run_id}.json"), report)
            atomic_json(project_file(root, "latest_run.json"), report)
        emit("finished", message=f"new={stats['new_downloads']}, cache={stats['cache_hits']}, elapsed={report['elapsed_seconds']}s")
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "run", "status"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    options = DownloadOptions(interval_seconds=args.interval, max_attempts=args.max_attempts)
    result = preflight(args.root, options) if args.action == "check" else status_report(args.root) if args.action == "status" else run_download(args.root, options)
    print(json.dumps(result, ensure_ascii=False, indent=2))
