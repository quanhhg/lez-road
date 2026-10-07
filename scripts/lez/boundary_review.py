"""Read verified 2030 outputs and render their current research strata for notebook 03."""
from __future__ import annotations

if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "lez"

import argparse
import csv
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess

from .common import (WORK, atomic_json, cached_manifest, code_hash, commit_manifest,
                     digest, file_hash, input_path, now, relative)

STRATA = [f"V{i}" for i in range(1, 6)] + [f"N{i}" for i in range(1, 11)]
TOLERANCE_M2 = 0.1  # The tolerance already used by the derived sampling partition.
COLORS = ["#08519c", "#2171b5", "#4292c6", "#6baed6", "#9ecae1",
          "#005a32", "#238b45", "#41ab5d", "#74c476", "#a1d99b",
          "#006d6f", "#239c91", "#56b9a6", "#86cbb6", "#b1dfcb"]


def _csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def review_normalization(work=WORK, result=None):
    """Keep current classification, original source QA and legal verification separate."""
    from .normalization_2030 import normalization_status
    work = Path(work).resolve()
    result = normalization_status(work) if result is None else result
    if not result.get("paths", {}).get("directory"):
        raise ValueError("Chưa có chuẩn hóa 2030. Chạy cell chuẩn hóa trước khi xem phân tầng.")
    directory = input_path(work, result["paths"]["directory"])
    manifest = json.loads((directory / "manifest.json").read_text())
    verified = cached_manifest(directory, manifest["fingerprint"])
    if verified is None:
        raise ValueError("Cache chuẩn hóa thiếu/hỏng hoặc hash không khớp; chạy lại run_normalization.")
    if any(result.get(k) != verified["report"].get(k) for k in ("boundary", "paths", "checks")):
        raise ValueError("Báo cáo và manifest thuộc các kết quả chuẩn hóa khác nhau.")
    options = json.loads((work / "config/sampling_2030.json").read_text())
    admin_path = input_path(work, options["boundary_admin_path"])
    admin_manifest = json.loads((admin_path.parent / "manifest.json").read_text())
    if cached_manifest(admin_path.parent, admin_manifest["fingerprint"]) is None:
        raise ValueError("Cache địa bàn nguồn không còn hợp lệ.")
    admin = json.loads((admin_path.parent / "admin_report.json").read_text())
    inventory = _csv(admin_path.parent / "admin_units.csv")
    trace = _csv(directory / "strata_assignment_trace.csv")
    assignments = _csv(directory / "remaining_admin_assignments.csv")
    decisions = _csv(directory / "boundary_decisions.csv")
    zones = input_path(work, result["paths"]["zones"])
    with sqlite3.connect(zones.as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute("SELECT zone_id, status, area_m2 FROM strata ORDER BY zone_id").fetchall()
    boundary = result["boundary"]
    source_ids = {r["osm_relation_id"] for r in inventory}
    assigned_ids = {r["admin_id"] for r in trace if r["admin_id"] != "technical_gap"}
    unassigned = [r for r in inventory if r["osm_relation_id"] not in assigned_ids]
    pending = [r for r in decisions if r["reason"] != "population_activity_score"]
    mismatch = [r for r in trace if r["sampling_stratum"] not in STRATA or
                r["group"] != ("inside" if r["sampling_stratum"].startswith("V") else "outside")]
    checks = {
        "cache_hashes_match": True,
        "snapshot_matches": admin["snapshot_utc"] == options["source_snapshot_utc"],
        "all_15_strata_present": len(rows) == 15 and {r[0] for r in rows} == set(STRATA),
        "positive_strata_areas": all(math.isfinite(r[2]) and r[2] > 0 for r in rows),
        "all_source_admin_units_assigned": assigned_ids == source_ids,
        "stratum_group_consistent": not mismatch,
        "boundary_evidence_complete": not pending and boundary["pending_evidence_units"] == 0,
        "derived_gap_passes": math.isfinite(boundary["strata_gap_m2"]) and
                              0 <= boundary["strata_gap_m2"] <= TOLERANCE_M2,
        "derived_overlap_passes": math.isfinite(boundary["strata_overlap_m2"]) and
                                  abs(boundary["strata_overlap_m2"]) <= TOLERANCE_M2,
        "research_scope_active": boundary["research_scope_active"] is True,
    }
    problems = [{"category": "current_research_classification", "reason": name}
                for name, passed in checks.items() if not passed]
    problems += [{"category": "pending_boundary_evidence", "reason": r["reason"],
                  "name": r["name"], "unit_id": r["unit_id"]} for r in pending]
    if not boundary["official_gis_verified"]:
        problems.append({"category": "official_gis_verification", "reason": "not_verified",
                         "detail": "Hình học OSM đối chiếu chưa được xác minh là GIS chính thức."})
    by_id = {r[0]: r for r in rows}
    strata = [{"stratum_id": key, "group": "inside" if key.startswith("V") else "outside",
               "area_km2": by_id[key][2] / 1_000_000, "status": by_id[key][1],
               "admin_units": len({r["admin_id"] for r in trace
                                   if r["sampling_stratum"] == key and r["admin_id"] != "technical_gap"})}
              for key in STRATA if key in by_id]
    return {"research_partition_ready": all(checks.values()),
            "official_gis_verified": boundary["official_gis_verified"],
            "normalization_version": directory.name, "finished_at": result["finished_at"],
            "admin_units": len(source_ids), "unassigned_admin_units": unassigned,
            "pending_evidence_parts": pending, "remaining_assignments": assignments,
            "strata": strata, "trace": trace, "checks": checks, "issues": problems,
            "raw_admin_qa": admin["qa"], "derived_gap_m2": boundary["strata_gap_m2"],
            "derived_overlap_m2": boundary["strata_overlap_m2"], "tolerance_m2": TOLERANCE_M2,
            "zones": relative(zones, work), "network_calls": 0}


def _render(work, result, directory, fingerprint):
    from .gis import initialize
    from qgis.core import (QgsVectorLayer, QgsGeometry, QgsFillSymbol, QgsMapSettings,
                           QgsMapRendererParallelJob, QgsCategorizedSymbolRenderer,
                           QgsRendererCategory, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling,
                           QgsTextFormat, QgsTextBufferSettings)
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor, QImage, QPainter, QFont
    initialize(work)
    review = review_normalization(work, result)
    zones = input_path(work, result["paths"]["zones"])
    def layer(name, style=None):
        value = QgsVectorLayer(str(zones) + "|layername=" + name, name, "ogr")
        if not value.isValid():
            raise ValueError("Không đọc được lớp phân tầng hiện tại: " + name)
        if style:
            value.renderer().setSymbol(QgsFillSymbol.createSimple(style))
        return value
    hanoi = layer("hanoi", {"color": "#f7f8f5", "outline_color": "#444d56", "outline_width": "0.4"})
    reference = layer("reference_lez_2030", {"color": "0,0,0,0", "outline_color": "#883752",
                                           "outline_style": "dash", "outline_width": "0.6"})
    strata = layer("strata")
    strata.setRenderer(QgsCategorizedSymbolRenderer("zone_id", [
        QgsRendererCategory(key, QgsFillSymbol.createSimple({"color": color,
            "outline_color": "#ffffff", "outline_width": "0.25"}), key)
        for key, color in zip(STRATA, COLORS)]))
    label = QgsPalLayerSettings(); label.fieldName = "zone_id"
    text = QgsTextFormat(); text.setFont(QFont("Arial", 12, QFont.Weight.Bold)); text.setSize(12)
    buffer = QgsTextBufferSettings(); buffer.setEnabled(True); buffer.setSize(0.8); buffer.setColor(QColor("white"))
    text.setBuffer(buffer); label.setFormat(text)
    strata.setLabeling(QgsVectorLayerSimpleLabeling(label)); strata.setLabelsEnabled(True)
    # Measure the actual displayed polygons; cached report numbers alone cannot certify a map.
    features = list(strata.getFeatures())
    geometries = [f.geometry() for f in features]
    if len(features) != 15 or any(g.isEmpty() or not g.isGeosValid() for g in geometries):
        raise ValueError("Lớp hiện tại chưa đủ 15 đa giác hợp lệ.")
    union = QgsGeometry.unaryUnion(geometries)
    city = QgsGeometry.unaryUnion([f.geometry() for f in hanoi.getFeatures()])
    geometry_checks = {"strata": len(features), "crs": strata.crs().authid(),
                       "gap_m2": city.difference(union).area(),
                       "overlap_m2": sum(g.area() for g in geometries) - union.area()}
    if geometry_checks["crs"] != "EPSG:3405" or geometry_checks["gap_m2"] > TOLERANCE_M2 or abs(geometry_checks["overlap_m2"]) > TOLERANCE_M2:
        raise ValueError("Phân hoạch thực tế trên bản đồ chưa đạt QA: " + str(geometry_checks))
    def draw(extent):
        settings = QgsMapSettings(); settings.setLayers([reference, strata, hanoi])
        settings.setDestinationCrs(hanoi.crs()); extent.scale(1.06); settings.setExtent(extent)
        settings.setOutputSize(QSize(910, 910)); settings.setBackgroundColor(QColor("white"))
        job = QgsMapRendererParallelJob(settings); job.start(); job.waitForFinished()
        return job.renderedImage()
    image = QImage(1950, 1400, QImage.Format.Format_ARGB32); image.fill(QColor("white"))
    painter = QPainter(image); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#203749")); painter.setFont(QFont("Arial", 25, QFont.Weight.Bold))
    painter.drawText(45, 58, "LEZ 2030 · PHÂN TẦNG NGHIÊN CỨU HIỆN TẠI")
    snapshot = json.loads((work / "config/sampling_2030.json").read_text())["source_snapshot_utc"][:10]
    painter.setFont(QFont("Arial", 13)); painter.drawText(45, 96, "V1–V5: nhóm trong · N1–N10: nhóm ngoài · OSM " + snapshot + " · EPSG:3405")
    painter.setFont(QFont("Arial", 15, QFont.Weight.Bold))
    painter.drawText(45, 140, "Toàn phạm vi Hà Nội"); painter.drawText(995, 140, "Phóng to khu vực LEZ đối chiếu")
    painter.drawImage(35, 160, draw(hanoi.extent())); painter.drawImage(990, 160, draw(reference.extent()))
    painter.setFont(QFont("Arial", 13))
    for index, (key, color) in enumerate(zip(STRATA, COLORS)):
        x, y = 70 + (index // 5) * 590, 1120 + (index % 5) * 34
        painter.fillRect(x, y - 17, 30, 20, QColor(color))
        painter.drawText(x + 42, y, key + (" — trong" if key.startswith("V") else " — ngoài"))
    painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
    painter.drawText(45, 1325, "Nét đứt: đường bao đối chiếu 36 địa bàn OSM; chưa xác minh độc lập GIS chính thức.")
    painter.setFont(QFont("Arial", 11))
    painter.drawText(45, 1360, "Nguồn: OpenStreetMap contributors (ODbL), phạm vi nghiên cứu đã chuẩn hóa · phiên bản " + review["normalization_version"])
    painter.end()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "strata_2030.png"
    temporary = directory / ".strata_2030.tmp.png"
    if not image.save(str(temporary), "PNG"):
        raise RuntimeError("Không xuất được bản đồ phân tầng.")
    temporary.replace(destination)
    output = {"created_at": now(), "normalization_version": review["normalization_version"],
              "zones_sha256": file_hash(zones), "path": relative(destination, work),
              "geometry_checks": geometry_checks, "network_calls": 0, "cache_hit": False}
    commit_manifest(directory, fingerprint, output, ["strata_2030.png"])
    return output


def render_current_boundaries(work=WORK, result=None):
    """Launch the existing PyQGIS runtime; notebook itself needs no qgis import."""
    from .normalization_2030 import normalization_status
    from .pipeline import kernel_spec
    work = Path(work).resolve()
    result = normalization_status(work) if result is None else result
    review_normalization(work, result)
    zones = input_path(work, result["paths"]["zones"])
    fingerprint = digest({"zones_sha256": file_hash(zones), "code": code_hash(["boundary_review.py"]),
                          "normalization_version": input_path(work, result["paths"]["directory"]).name})
    directory = work / "reports/boundaries/current_2030" / fingerprint[:20]
    cached = cached_manifest(directory, fingerprint)
    if cached:
        return dict(cached["report"], cache_hit=True)
    spec = kernel_spec(); env = os.environ.copy(); env.update(spec.get("env", {}))
    command = [spec["argv"][0], str(Path(__file__).resolve()), "--work", str(work),
               "--report", str(input_path(work, result["paths"]["directory"]) / "report.json"),
               "--directory", str(directory), "--fingerprint", fingerprint]
    process = subprocess.run(command, env=env, text=True, capture_output=True, timeout=180)
    if process.returncode:
        raise RuntimeError("Không dựng được bản đồ hiện tại:\n" + process.stderr[-3000:] + process.stdout[-1000:])
    return json.loads(process.stdout.strip().splitlines()[-1])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--fingerprint", required=True)
    args = parser.parse_args()
    print(json.dumps(_render(args.work, json.loads(args.report.read_text()), args.directory,
                             args.fingerprint), ensure_ascii=False))
