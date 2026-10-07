"""Small standard-library helpers shared by the processing stages."""
from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

WORK = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def code_hash(filenames=None):
    paths = sorted(Path(__file__).parent.glob("*.py")) if filenames is None else [Path(__file__).parent / name for name in sorted(filenames)]
    return digest({p.name: file_hash(p) for p in paths})


def relative(path, work=WORK):
    path, work = Path(path).resolve(), Path(work).resolve()
    return "work/" + path.relative_to(work).as_posix() if path.is_relative_to(work) else str(path)


def input_path(work, value):
    if not value:
        return None
    path = Path(value)
    if path.parts[:1] == ("work",):
        path = Path(*path.parts[1:])
    return path.resolve() if path.is_absolute() else (Path(work) / path).resolve()


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())


def write_csv(path, rows, fields):
    import io
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    atomic_bytes(path, buffer.getvalue().encode("utf-8"))


@contextmanager
def processing_lock(work=WORK):
    path = Path(work) / "reports/lez/.processing.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another boundary/network pipeline is using this workspace.") from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def event(stage, message, **details):
    print(canonical({"event": "progress", "stage": stage, "message": message, **details}), flush=True)


def cached_manifest(directory, fingerprint):
    path = Path(directory) / "manifest.json"
    try:
        m = json.loads(path.read_text())
        if m["fingerprint"] != fingerprint or not m["complete"]:
            return None
        for name, expected in m["output_hashes"].items():
            if file_hash(Path(directory) / name) != expected:
                return None
        return m
    except (OSError, ValueError, KeyError, TypeError):
        return None


def commit_manifest(directory, fingerprint, report, outputs):
    directory = Path(directory)
    manifest = {"schema_version": SCHEMA_VERSION, "fingerprint": fingerprint,
                "complete": True, "finished_at": now(), "report": report,
                "output_hashes": {name: file_hash(directory / name) for name in outputs}}
    atomic_json(directory / "manifest.json", manifest)
    return manifest


def publish_link(work, name, target):
    path = Path(work) / "data/processed" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.is_symlink():
        raise RuntimeError(f"Refusing to replace an existing independent file: {path}")
    tmp = path.with_name("." + path.name + ".link")
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(os.path.relpath(target, path.parent))
    os.replace(tmp, path)
