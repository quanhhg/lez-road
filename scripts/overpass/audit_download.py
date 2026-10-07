"""Read-only payload audit after a run; writes a report but sends no HTTP requests."""
import hashlib
import json
from pathlib import Path

import download_tiles as d


def audit(root=d.ROOT):
    root = Path(root).resolve()
    with d.project_lock(root):
        d.recover_state(root)
        raw_history = {t["tile_id"]: t for t in json.loads((root / "tiles_history.json").read_text())}
        project = d.read_project(root)
        valid, invalid, empty = [], [], []
        total_bytes = 0
        mismatches = []
        progress_mismatches = []
        for tile in project["rows"]:
            if tile["status"] != raw_history[tile["tile_id"]]["status"]:
                mismatches.append(tile["tile_id"])
            canonical = project["by_id"][tile["tile_id"]]
            for field in d.PROGRESS_FIELDS:
                if canonical.get(field, "") != raw_history[tile["tile_id"]].get(field, ""):
                    progress_mismatches.append(dict(tile_id=tile["tile_id"], field=field))
            if tile["status"] == "split":
                continue
            manifest, error = d.check_cache(project, tile)
            if manifest is not None and tile["status"] == "done":
                valid.append(tile["tile_id"])
                total_bytes += (project["destinations"][tile["tile_id"]] / "response.json").stat().st_size
                if manifest["empty_road_result"]:
                    empty.append(tile["tile_id"])
            else:
                invalid.append(dict(tile_id=tile["tile_id"], status=tile["status"],
                                    cache_error=error, last_error=d.readable_error(tile.get("last_error", ""))))
        baseline = json.loads((d.project_file(root, "implementation_baseline.json")).read_text())
        changed = []
        for group in ("geometry_hashes", "query_hashes"):
            for name, expected in baseline[group].items():
                if hashlib.sha256(d.project_file(root, name).read_bytes()).hexdigest() != expected:
                    changed.append(name)
        report = dict(audited_at=d.utc_now(), active_tiles=len(project["queries"]),
                      valid_done_tiles=len(valid), counts=d.state_counts(project),
                      all_active_tiles_complete=not invalid and len(valid)==len(project["queries"]),
                      attention_required=invalid, empty_road_tiles=empty,
                      total_response_bytes=total_bytes, csv_history_status_mismatches=mismatches,
                      csv_history_progress_mismatches=progress_mismatches,
                      project_state_consistent=not mismatches and not progress_mismatches,
                      changed_geometry_or_query_files=changed, network_calls=0)
        d.atomic_json(d.project_file(root, "completion_audit.json"), report)
        return report


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
