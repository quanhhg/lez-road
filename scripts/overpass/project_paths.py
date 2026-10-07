"""Portable paths for the work/data, work/maps and work/reports layout."""
import json
from pathlib import Path


WORK_DIR = Path(__file__).resolve().parents[2]
DATA_ROOT = WORK_DIR / "data" / "hanoi_tiles"


def project_file(root, name):
    """Resolve a project file; standalone test projects retain their old layout."""
    root = Path(root).resolve()
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Expected a relative project filename: {name}")
    marker = root / "project_layout.json"
    if not marker.exists():
        return root / relative
    layout = json.loads(marker.read_text(encoding="utf-8"))
    if layout.get("schema_version") != 1:
        raise ValueError("Unsupported project_layout.json schema.")
    workspace = (root / layout["workspace_root"]).resolve()
    if workspace == root or not root.is_relative_to(workspace):
        raise ValueError("The configured workspace must contain the data directory.")
    mapped = layout.get("files", {}).get(relative.as_posix())
    if mapped is None and relative.parts:
        directory = layout.get("directories", {}).get(relative.parts[0])
        if directory is not None:
            mapped = str(Path(directory).joinpath(*relative.parts[1:]))
    if mapped is None:
        return root / relative
    mapped_path = Path(mapped)
    destination = (workspace / mapped_path).resolve()
    if mapped_path.is_absolute() or destination == workspace or not destination.is_relative_to(workspace):
        raise ValueError(f"Output path escapes the configured workspace: {name}")
    if destination == root or destination.is_relative_to(root):
        raise ValueError(f"Mapped output collides with the data directory: {name}")
    return destination
