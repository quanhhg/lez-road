"""Reproducible A/B/C polygons from cached OSM road alignments.

These polygons implement the research ring-band design. They are not an
official government GIS extract and remain independent of LEZ policy zones.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections import defaultdict
from pathlib import Path

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsVectorLayer,
                       QgsWkbTypes)

from .common import atomic_json, file_hash, input_path, relative
from .gis import sink


def configuration(work):
    path = Path(work) / "config/ring_boundaries.json"
    options = json.loads(path.read_text())
    if options.get("metric_crs") != "EPSG:3405":
        raise ValueError("A/B/C boundaries require metric EPSG:3405")
    return options


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class _Union:
    def __init__(self):
        self.parent = {}

    def find(self, value):
        self.parent.setdefault(value, value)
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def merge(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a
            return True
        return False


def _road_graph(layer, definition, transform):
    names = set(definition.get("names", []))
    contains = definition.get("name_contains", [])
    refs = set(definition.get("refs", []))
    tokens = sorted(names | set(contains) | refs)
    expression = " OR ".join('"tags_json" LIKE \'%'+v.replace("'", "''")+"%\'" for v in tokens)
    request = QgsFeatureRequest().setFilterExpression(expression)
    nodes, adjacency, sources = {}, defaultdict(list), []
    union = _Union()
    bbox = definition["bbox_wgs84"]
    inverse = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:3405"),
                                     QgsCoordinateReferenceSystem("EPSG:4326"),
                                     transform)
    allowed_classes = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
                       "secondary", "secondary_link", "tertiary", "tertiary_link", "service", "construction", "proposed"}
    for feature in layer.getFeatures(request):
        tags = json.loads(feature["tags_json"])
        name = tags.get("name", "")
        if not (name in names or any(v in name for v in contains) or refs.intersection(tags.get("ref", "").split(";"))):
            continue
        if tags.get("highway") not in allowed_classes:
            continue
        points = feature.geometry().asPolyline()
        if len(points) < 2:
            continue
        middle = inverse.transform(points[len(points)//2])
        if not (bbox[0] <= middle.x() <= bbox[2] and bbox[1] <= middle.y() <= bbox[3]):
            continue
        coordinates = [(p.x(), p.y()) for p in points]
        u, v = str(feature["from_node"]), str(feature["to_node"])
        length = feature.geometry().length()
        edge = {"segment_id": feature["segment_id"], "way_id": int(feature["way_id"]),
                "name": name, "highway": tags.get("highway"), "method": "cached_osm_alignment",
                "length_m": length, "coordinates": coordinates}
        adjacency[u].append((v, length, edge, False))
        adjacency[v].append((u, length, edge, True))
        nodes[u], nodes[v] = coordinates[0], coordinates[-1]
        union.merge(u, v)
        sources.append({k: edge[k] for k in ("segment_id", "way_id", "name", "highway", "length_m")})
    if not nodes:
        raise ValueError("No cached source road geometries matched ring definition")
    # Candidate joins resolve short missing junctions and dual carriageways.
    # A 1000m cost penalty below protects genuine alignment geometry.
    tolerance = definition["maximum_component_snap_m"]
    grid = defaultdict(list)
    for identifier, point in nodes.items():
        grid[(math.floor(point[0]/tolerance), math.floor(point[1]/tolerance))].append(identifier)
    candidates = []
    for u, point in nodes.items():
        gx, gy = math.floor(point[0]/tolerance), math.floor(point[1]/tolerance)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for v in grid.get((gx+dx, gy+dy), []):
                    if u < v and not any(edge[0] == v for edge in adjacency[u]):
                        distance = _distance(point, nodes[v])
                        if distance <= tolerance:
                            candidates.append((distance, u, v))
    gaps = []
    for length, u, v in sorted(candidates):
        different_component = union.merge(u, v)
        if different_component or length <= tolerance:
            edge = {"way_id": None, "segment_id": None, "name": "component endpoint snap",
                    "highway": None, "method": "component_snap", "length_m": length,
                    "coordinates": [nodes[u], nodes[v]]}
            # The penalty keeps genuine alignment geometry preferable. Short
            # lateral joins are used only to resolve distant interchange
            # connections between dual carriageways, including same-component
            # carriageways that otherwise require kilometre-scale detours.
            adjacency[u].append((v, length+1000, edge, False))
            adjacency[v].append((u, length+1000, edge, True))
            gaps.append({"from_node": u, "to_node": v, "length_m": length})
    return nodes, adjacency, sources, gaps


def _shortest(adjacency, start, finish):
    queue, distance, previous = [(0.0, start)], {start: 0.0}, {}
    while queue:
        cost, u = heapq.heappop(queue)
        if cost != distance[u]:
            continue
        if u == finish:
            break
        for v, length, edge, reverse in adjacency[u]:
            value = cost + length
            if value < distance.get(v, math.inf):
                distance[v] = value
                previous[v] = (u, edge, reverse)
                heapq.heappush(queue, (value, v))
    if finish not in distance:
        raise ValueError(f"Ring road alignment is disconnected: {start} -> {finish}")
    result, cursor = [], finish
    while cursor != start:
        u, edge, reverse = previous[cursor]
        result.append((edge, reverse))
        cursor = u
    return list(reversed(result))


def _ring(layer, definition, context):
    project = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                                    QgsCoordinateReferenceSystem("EPSG:3405"), context)
    nodes, graph, sources, candidate_gaps = _road_graph(layer, definition, context)
    anchors, matched = [], []
    for lon, lat in definition["waypoints_wgs84"]:
        p = project.transform(QgsPointXY(lon, lat))
        point = (p.x(), p.y())
        node = min(nodes, key=lambda key: (_distance(point, nodes[key]), key))
        offset = _distance(point, nodes[node])
        if offset > 500:
            raise ValueError(f"Ring waypoint is {offset:.1f}m from its cached corridor")
        anchors.append(node)
        matched.append({"requested_wgs84": [lon, lat], "source_node": node, "offset_m": offset})
    edges = []
    for a, b in zip(anchors, anchors[1:]):
        edges.extend(_shortest(graph, a, b))
    coordinates, used = [], []
    for edge, reverse in edges:
        points = list(reversed(edge["coordinates"])) if reverse else edge["coordinates"]
        coordinates.extend(points if not coordinates else points[1:])
        record = {k: edge.get(k) for k in ("segment_id", "way_id", "name", "highway", "method", "length_m")}
        if edge["method"] == "component_snap":
            record["coordinates_metric"] = points
        used.append(record)
    closure = definition.get("northern_closure")
    explicit_closure = None
    if closure:
        # Endpoints are snapped OSM corridor nodes; intermediate coordinates
        # are explicit research closure vertices from configuration.
        closure_points = [coordinates[-1]]
        for lon, lat in closure["coordinates_wgs84"][1:-1]:
            p = project.transform(QgsPointXY(lon, lat))
            closure_points.append((p.x(), p.y()))
        closure_points.append(coordinates[0])
        closure_length = sum(_distance(a,b) for a,b in zip(closure_points, closure_points[1:]))
        if closure_length > closure["maximum_length_m"]:
            raise ValueError("Explicit northern closure exceeded configured maximum")
        coordinates.extend(closure_points[1:])
        explicit_closure = {**closure, "actual_length_m": closure_length,
                            "coordinates_metric": closure_points}
    if coordinates[0] != coordinates[-1]:
        raise ValueError("Ring alignment is not closed")
    # Remove immediate reverse traversals introduced by snapping a waypoint
    # to a parallel carriageway node. No smoothing or convex hull is used.
    simplified = []
    for point in coordinates:
        if len(simplified) >= 2 and point == simplified[-2]:
            simplified.pop()
        elif not simplified or point != simplified[-1]:
            simplified.append(point)
    # A waypoint on a cul-de-sac/parallel-carriageway branch may create a
    # closed detour before the main ring. Erase repeated-vertex detours while
    # preserving the final closing vertex and record how much was removed.
    erased, positions = [], {}
    removed_loop_length = 0.0
    for index, point in enumerate(simplified):
        if point in positions and not (index == len(simplified)-1 and point == simplified[0]):
            start = positions[point]
            loop = erased[start:]+[point]
            removed_loop_length += sum(_distance(a,b) for a,b in zip(loop,loop[1:]))
            for previous in erased[start+1:]:
                positions.pop(previous, None)
            erased = erased[:start+1]
        else:
            positions[point] = len(erased)
            erased.append(point)
    simplified = erased
    polygon = QgsGeometry.fromPolygonXY([[QgsPointXY(*p) for p in simplified]])
    repaired_slivers = 0.0
    if polygon.isEmpty() or not polygon.isGeosValid():
        repaired = polygon.makeValid()
        if repaired.isMultipart():
            pieces = repaired.asGeometryCollection()
            pieces.sort(key=lambda geometry:geometry.area(), reverse=True)
            repaired_slivers = sum(g.area() for g in pieces[1:])
            if not pieces or repaired_slivers > pieces[0].area()*0.002:
                raise ValueError("Ring corridor has a material self-intersection; inspect source alignment")
            polygon = pieces[0]
        else:
            polygon = repaired
        if polygon.isEmpty() or not polygon.isGeosValid() or polygon.type()!=QgsWkbTypes.PolygonGeometry:
            raise ValueError("Reconstructed ring polygon remains invalid")
    line = QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in simplified])
    area = polygon.area()/1e6
    bounds = definition["area_bounds_km2"]
    if not bounds[0] <= area <= bounds[1]:
        raise ValueError(f"Reconstructed ring area {area:.3f} km2 is outside plausibility limits")
    used_gaps = [e for e in used if e["method"] == "component_snap"]
    report = {"area_km2": area, "perimeter_m": line.length(),
              "erased_repeated_vertex_detour_m": removed_loop_length,
              "geos_polygonization_discarded_sliver_m2": repaired_slivers,
              "geometry_sha256": hashlib.sha256(bytes(polygon.asWkb())).hexdigest(),
              "waypoints": matched, "source_way_ids": sorted({e["way_id"] for e in used if e["way_id"] is not None}),
              "used_alignment_segments": used, "component_snap_edges": used_gaps,
              "component_snap_total_m": sum(e["length_m"] for e in used_gaps),
              "component_snap_max_m": max((e["length_m"] for e in used_gaps), default=0),
              "explicit_northern_closure": explicit_closure,
              "source_way_count": len({e["way_id"] for e in used if e["way_id"] is not None}),
              "source_segments_matched": len(sources), "graph_component_connections": len(candidate_gaps),
              "includes_proposed_alignment": any(e["highway"] == "proposed" for e in used),
              "includes_construction_alignment": any(e["highway"] == "construction" for e in used)}
    return polygon, line, report


def build(work, hanoi, context, output_dir=None, options=None):
    """Return metric ring polygons, A/B/C groups, lines and provenance report.

    hanoi must be the validated EPSG:3405 Hanoi boundary. No network call or
    source-data edit occurs. Optional output writes only derived artifacts.
    """
    work = Path(work)
    options = configuration(work) if options is None else options
    path = input_path(work, options["source_network"])
    layer = QgsVectorLayer(str(path)+"|layername="+options.get("source_layer", "segments"), "ring_source", "ogr")
    if not layer.isValid() or layer.crs().authid() != options["metric_crs"]:
        raise ValueError("Cannot read cached metric road alignment layer")
    ring1, line1, report1 = _ring(layer, options["ring1"], context)
    ring3, line3, report3 = _ring(layer, options["ring3"], context)
    excess = ring1.difference(ring3).area()
    if excess > 0.01:
        raise ValueError("Ring 1 polygon is not fully inside Ring 3")
    groups = {"A": hanoi.intersection(ring1), "B": hanoi.intersection(ring3).difference(ring1),
              "C": hanoi.difference(ring3)}
    if any(g.isEmpty() or not g.isGeosValid() for g in groups.values()):
        raise ValueError("Invalid or empty A/B/C research group")
    union = QgsGeometry.unaryUnion(list(groups.values()))
    gap = hanoi.difference(union).area()
    overlap = sum(g.area() for g in groups.values())-union.area()
    if abs(gap)>0.05 or abs(overlap)>0.05:
        raise ValueError("A/B/C group topology check failed")
    report = {"status": options["definition_status"], "official_gis_verified": False,
              "metric_crs": options["metric_crs"], "source_network": relative(path, work),
              "source_network_sha256": file_hash(path), "sources": options["sources"],
              "rings": {"ring1": report1, "ring3": report3},
              "group_areas_km2": {key: g.area()/1e6 for key,g in groups.items()},
              "hanoi_gap_m2": gap, "group_overlap_m2": overlap,
              "ring1_outside_ring3_m2": excess,
              "notes": ["A/B/C groups describe research ring bands; LEZ membership remains a separate geometry overlay.",
                        "Road alignment includes cached proposed/construction geometry for the planned 2030 ring definition.",
                        "Northern Ring 3 closure is an explicit research approximation and requires official GIS replacement."]}
    closure = report3["explicit_northern_closure"]
    closure_line = QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in closure["coordinates_metric"]])
    exclusion = hanoi.intersection(closure_line.buffer(options["ring3"]["northern_closure"].get("uncertainty_buffer_m", 2000), 12))
    join_buffers = []
    for ring_report in (report1, report3):
        for edge in ring_report["component_snap_edges"]:
            line = QgsGeometry.fromPolylineXY([QgsPointXY(*point) for point in edge["coordinates_metric"]])
            join_buffers.append(line.buffer(200, 8))
    if join_buffers:
        exclusion = hanoi.intersection(QgsGeometry.unaryUnion([exclusion]+join_buffers))
    report["routing_exclusion"] = {"reason":"uncertain_missing_northern_ring3_alignment_and_short_corridor_joins", "buffer_m":options["ring3"]["northern_closure"].get("uncertainty_buffer_m", 2000), "short_join_buffer_m":200, "short_join_count":len(join_buffers), "area_km2":exclusion.area()/1e6,
                                    "policy":"Exclude every physical route part intersecting this uncertainty band from A/B/C candidate generation"}
    result = {"ring1": ring1, "ring3": ring3, "groups": groups, "exclusion_geometry": exclusion,
              "lines": {"ring1": line1, "ring3": line3}, "report": report}
    if output_dir is not None:
        export(result, output_dir, context)
    return result


def build_regions(work, directory, context, crs, hanoi):
    """Controller adapter: return (group polygons, report, uncertain alignment band)."""
    if crs != "EPSG:3405":
        raise ValueError("A/B/C ring geometry requires EPSG:3405")
    result = build(work, hanoi, context, output_dir=directory)
    return result["groups"], result["report"], result["exclusion_geometry"]


def export(result, output_dir, context):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir/"abc_boundaries.gpkg"
    crs = result["report"]["metric_crs"]
    with sink(path, "abc_groups", [("abc_group","str"),("definition","str"),("area_km2","float")], QgsWkbTypes.MultiPolygon, crs, context) as output:
        for code, geometry in result["groups"].items():
            copy = QgsGeometry(geometry)
            copy.convertToMultiType()
            output.add({"abc_group": code, "definition": {"A":"inside_ring1", "B":"ring1_to_ring3", "C":"outside_ring3"}[code], "area_km2":geometry.area()/1e6}, copy)
    with sink(path, "ring_polygons", [("ring_id","str"),("official_gis_verified","bool")], QgsWkbTypes.Polygon, crs, context) as output:
        for code in ("ring1","ring3"):
            output.add({"ring_id":code,"official_gis_verified":False}, result[code])
    with sink(path, "ring_alignment", [("ring_id","str")], QgsWkbTypes.LineString, crs, context) as output:
        for code, geometry in result["lines"].items():
            output.add({"ring_id":code}, geometry)
    with sink(path, "routing_exclusion", [("reason","str"),("buffer_m","float")], QgsWkbTypes.MultiPolygon, crs, context) as output:
        geometry = QgsGeometry(result["exclusion_geometry"])
        geometry.convertToMultiType()
        output.add({"reason":"uncertain_northern_ring3_closure","buffer_m":result["report"]["routing_exclusion"]["buffer_m"]},geometry)
    atomic_json(output_dir/"abc_boundaries_report.json", result["report"])
    return path
