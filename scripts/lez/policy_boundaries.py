"""Dated LEZ-first A/B/C geometry, independent of population/activity adjustments.

A is the 2027 pilot KV1/KV2/KV3 enclosing street contour, B is the
2030 planned Ring 3 LEZ proxy minus A, and C is Hanoi minus that 2030 proxy.
Official source documents exist; the cached OSM-derived polygons are technical
approximations, never authenticated official GIS or field access permission.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsVectorLayer,
                       QgsWkbTypes)

from . import abc_boundaries
from .common import atomic_json, file_hash, input_path, relative
from .gis import check_layers, read_polygon, sink


def configuration(work):
    options = json.loads((Path(work)/"config/lez_policy.json").read_text())
    if options.get("metric_crs") != "EPSG:3405":
        raise ValueError("LEZ-first polygons require metric EPSG:3405")
    if options.get("classification_basis") != "dated_LEZ2027_pilot_and_LEZ2030_planned_ring3":
        raise ValueError("Unexpected LEZ-first classification basis")
    if options.get("allow_population_activity_boundary_adjustments") is not False:
        raise ValueError("LEZ-first classification forbids population/activity boundary changes")
    return options


def _distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])


def _pilot_geometry(layer, definition, context):
    """Trace only named enclosing streets; road class/access do not define a boundary."""
    names=set(definition["names"])
    request=QgsFeatureRequest().setFilterExpression(" OR ".join('"tags_json" LIKE \'%'+v.replace("'","''")+"%\'" for v in sorted(names)))
    inverse=QgsCoordinateTransform(layer.crs(),QgsCoordinateReferenceSystem("EPSG:4326"),context)
    project=QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),layer.crs(),context)
    nodes,graph={},defaultdict(list)
    bbox=definition["bbox_wgs84"]
    for feature in layer.getFeatures(request):
        tags=json.loads(feature["tags_json"])
        if tags.get("name") not in names:
            continue
        points=feature.geometry().asPolyline()
        if len(points)<2:
            continue
        middle=inverse.transform(points[len(points)//2])
        if not (bbox[0]<=middle.x()<=bbox[2] and bbox[1]<=middle.y()<=bbox[3]):
            continue
        u,v=str(feature["from_node"]),str(feature["to_node"])
        coordinates=[(p.x(),p.y()) for p in points]
        edge={"segment_id":feature["segment_id"],"way_id":int(feature["way_id"]),"name":tags["name"],
              "highway":tags.get("highway"),"method":"cached_osm_named_boundary_street", "length_m":feature.geometry().length(),"coordinates":coordinates}
        nodes[u],nodes[v]=coordinates[0],coordinates[-1]
        graph[u].append((v,edge["length_m"],edge,False));graph[v].append((u,edge["length_m"],edge,True))
    if not nodes:
        raise ValueError("2027 named boundary streets not found in cached network")
    tolerance=float(definition["maximum_component_snap_m"])
    grid=defaultdict(list)
    for identifier,p in nodes.items():
        grid[(math.floor(p[0]/tolerance),math.floor(p[1]/tolerance))].append(identifier)
    for u,p in sorted(nodes.items()):
        gx,gy=math.floor(p[0]/tolerance),math.floor(p[1]/tolerance)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for v in grid.get((gx+dx,gy+dy),[]):
                    if u>=v or any(e[0]==v for e in graph[u]):
                        continue
                    length=_distance(p,nodes[v])
                    if length>tolerance:
                        continue
                    edge={"segment_id":None,"way_id":None,"name":"explicit_boundary_endpoint_snap","highway":None,
                          "method":"component_snap","length_m":length,"coordinates":[p,nodes[v]]}
                    graph[u].append((v,length+1000,edge,False));graph[v].append((u,length+1000,edge,True))
    anchors,matched=[],[]
    for lon,lat in definition["waypoints_wgs84"]:
        p=project.transform(QgsPointXY(lon,lat));point=(p.x(),p.y())
        identifier=min(nodes,key=lambda key:(_distance(point,nodes[key]),key))
        offset=_distance(point,nodes[identifier])
        if offset>definition.get("maximum_waypoint_offset_m",100):
            raise ValueError(f"2027 boundary waypoint is {offset:.1f}m from cached named street")
        anchors.append(identifier);matched.append({"requested_wgs84":[lon,lat],"source_node":identifier,"offset_m":offset})
    edges=[]
    for start,finish in zip(anchors,anchors[1:]):
        edges.extend(abc_boundaries._shortest(graph,start,finish))
    coordinates,used=[],[]
    for edge,reverse in edges:
        points=list(reversed(edge["coordinates"])) if reverse else edge["coordinates"]
        coordinates.extend(points if not coordinates else points[1:])
        record={k:edge[k] for k in ("segment_id","way_id","name","highway","method","length_m")}
        if edge["method"]=="component_snap":
            record["coordinates_metric"]=points
        used.append(record)
    if not coordinates or coordinates[0]!=coordinates[-1]:
        raise ValueError("2027 street contour did not close")
    # Immediate reverse edges and waypoint side branches are explicit trace
    # artifacts, not changes to the official area. Their lengths are reported.
    simple=[]
    for point in coordinates:
        if len(simple)>1 and point==simple[-2]:simple.pop()
        elif not simple or point!=simple[-1]:simple.append(point)
    erased,positions=[],{}
    detour=0.0
    for index,point in enumerate(simple):
        if point in positions and not(index==len(simple)-1 and point==simple[0]):
            start=positions[point];loop=erased[start:]+[point]
            detour+=sum(_distance(a,b) for a,b in zip(loop,loop[1:]))
            for previous in erased[start+1:]:positions.pop(previous,None)
            erased=erased[:start+1]
        else:
            positions[point]=len(erased);erased.append(point)
    polygon=QgsGeometry.fromPolygonXY([[QgsPointXY(*p) for p in erased]])
    if polygon.isEmpty() or not polygon.isGeosValid():
        raise ValueError("2027 named street contour self-intersects; inspect source/map discrepancy")
    line=QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in erased])
    area=polygon.area()/1e6
    lo,hi=definition["area_bounds_km2"]
    if not lo<=area<=hi:
        raise ValueError(f"2027 proxy area {area:.3f}km2 outside stated plausibility range")
    segments=[u for u in used if u["method"]=="component_snap"]
    used_names=sorted({u["name"] for u in used if u["way_id"] is not None})
    return polygon,line,{"geometry_status":"official_map_informed_cached_osm_street_contour_proxy", "official_gis_verified":False,
        "area_km2":area,"perimeter_m":line.length(),"reference_area_km2":definition["reference_area_km2"],
        "reference_perimeter_m":definition["reference_perimeter_m"], "reference_area_difference_fraction":area/definition["reference_area_km2"]-1,
        "geometry_sha256":hashlib.sha256(bytes(polygon.asWkb())).hexdigest(),"waypoints":matched,
        "used_alignment_segments":used,"component_snap_edges":segments,"component_snap_total_m":sum(s["length_m"] for s in segments),
        "component_snap_max_m":max((s["length_m"] for s in segments),default=0),"erased_repeated_vertex_detour_m":detour,
        "source_way_ids":sorted({u["way_id"] for u in used if u["way_id"] is not None}),"used_street_names":used_names,
        "declared_official_streets_absent_from_final_trace":[n for n in definition["official_street_names"] if not any(name in (n,"Phố "+n,"Đường "+n) for name in used_names)],
        "map_informed_connectors":definition["map_informed_connectors"],"interpretation_issues":definition["interpretation_issues"]}


def compose(hanoi,lez2027,lez2030,tolerance_m2=0.1):
    """Compose exclusive zones and reject policy containment/coverage defects."""
    for name,g in (("hanoi",hanoi),("lez2027",lez2027),("lez2030",lez2030)):
        if g.isEmpty() or not g.isGeosValid() or g.type()!=QgsWkbTypes.PolygonGeometry:
            raise ValueError("Invalid policy polygon: "+name)
    outside=lez2027.difference(lez2030).area()
    if outside>tolerance_m2:
        raise ValueError("LEZ2027 is not contained in LEZ2030")
    a=hanoi.intersection(lez2027);scope=hanoi.intersection(lez2030)
    groups={"A":a,"B":scope.difference(a),"C":hanoi.difference(scope)}
    if any(g.isEmpty() or not g.isGeosValid() for g in groups.values()):
        raise ValueError("Empty/invalid LEZ-first A/B/C zone")
    union=QgsGeometry.unaryUnion(list(groups.values()))
    gap=hanoi.difference(union).area();excess=union.difference(hanoi).area()
    pairs={a+b:groups[a].intersection(groups[b]).area() for a,b in (("A","B"),("A","C"),("B","C"))}
    union_error=QgsGeometry.unaryUnion([groups["A"],groups["B"]]).symDifference(scope).area()
    if max(gap,excess,union_error,*pairs.values())>tolerance_m2:
        raise ValueError("LEZ-first zone composition failed topology/purity checks")
    return groups,{"lez2027_outside_lez2030_m2":outside,"hanoi_gap_m2":gap,"hanoi_excess_m2":excess,
                   "pairwise_overlap_m2":pairs,"A_union_B_vs_LEZ2030_difference_m2":union_error,
                   "area_tolerance_m2":tolerance_m2,"group_areas_km2":{k:g.area()/1e6 for k,g in groups.items()}}


def build(work,hanoi,context,output_dir=None,options=None):
    work=Path(work);options=configuration(work) if options is None else options
    if options.get("metric_crs") != "EPSG:3405" or options.get("classification_basis") != "dated_LEZ2027_pilot_and_LEZ2030_planned_ring3":
        raise ValueError("Invalid LEZ-first configuration basis or CRS")
    if options.get("allow_population_activity_boundary_adjustments") is not False:
        raise ValueError("LEZ-first classification forbids population/activity boundary changes")
    hashes={}
    for source in options["local_sources"]:
        path=input_path(work,source["path"])
        if not path.is_file() or file_hash(path)!=source["sha256"]:
            raise ValueError("Policy source missing/changed: "+str(path))
        hashes[relative(path,work)]=source["sha256"]
    ring_options=json.loads(input_path(work,options["ring_config"]).read_text())
    network=input_path(work,options["source_network"])
    ring_options["source_network"]=str(network)
    rings=abc_boundaries.build(work,hanoi,context,options=ring_options)
    layer=QgsVectorLayer(str(network)+"|layername="+options.get("source_layer","segments"),"pilot_boundary_source","ogr")
    if not layer.isValid() or layer.crs().authid()!=options["metric_crs"]:
        raise ValueError("Invalid cached2027 boundary street layer")
    pilot,pilot_line,pilot_report=_pilot_geometry(layer,options["lez2027_pilot"],context)
    pilot=hanoi.intersection(pilot);lez2030=hanoi.intersection(rings["ring3"])
    groups,checks=compose(hanoi,pilot,lez2030,options.get("area_tolerance_m2",0.1))
    if pilot.difference(rings["ring1"]).area()>options.get("area_tolerance_m2",0.1):
        raise ValueError("2027 pilot outside wholeRing1 reference")
    buffers=[rings["exclusion_geometry"],pilot_line.buffer(options["lez2027_pilot"]["boundary_uncertainty_buffer_m"],12)]
    for edge in pilot_report["component_snap_edges"]:
        line=QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in edge["coordinates_metric"]])
        buffers.append(line.buffer(options["lez2027_pilot"]["join_uncertainty_buffer_m"],8))
    exclusion=hanoi.intersection(QgsGeometry.unaryUnion(buffers))
    comparison=None
    reference=options.get("historical_admin_extent_reference")
    if reference:
        path=input_path(work,reference["path"])
        if path.is_file():
            admin=read_polygon(path,options["metric_crs"],context,reference["layer"])
            comparison={"status":"comparison_only_not_classification", "path":relative(path,work),"sha256":file_hash(path),
                        "admin_extent_area_km2":admin.area()/1e6,"ring3_proxy_area_km2":lez2030.area()/1e6,
                        "admin_extent_outside_ring3_km2":admin.difference(lez2030).area()/1e6,
                        "ring3_not_in_admin_extent_km2":lez2030.difference(admin).area()/1e6}
    report={"schema_version":1,"policy_version":options["policy_version"],"verified_as_of":options["verified_as_of"],
        "status":"provisional_LEZ_first_desktop_geometry_ready_for_candidate_generation", "official_gis_verified":False,
        "classification_basis":options["classification_basis"],"metric_crs":options["metric_crs"],
        "source_network":relative(network,work),"source_network_sha256":file_hash(network),"source_document_hashes":hashes,
        "sources":options["official_sources"],"statutory2027":options["statutory2027"],"statutory2030":options["statutory2030"],
        "zones":{"A":"LEZ2027 pilot KV1/KV2/KV3 technical street-contour proxy", "B":"LEZ2030 plannedRing3 proxy minus LEZ2027 pilot", "C":"Hanoi technical boundary minus LEZ2030 plannedRing3 proxy"},
        "boundary_adjustments_applied":False,"population_activity_classification_used":False,
        "whole_ring1_is_2027_pilot":False,"rings":rings["report"]["rings"],"pilot2027":pilot_report,
        "checks":checks,"group_areas_km2":checks["group_areas_km2"],"hanoi_gap_m2":checks["hanoi_gap_m2"],
        "group_overlap_m2":sum(checks["pairwise_overlap_m2"].values()),"historical_admin_reference_comparison":comparison,
        "routing_exclusion":{"reason":"uncertain2027pilot_boundary_and_unfinished_ring3_alignment", "pilot_boundary_buffer_m":options["lez2027_pilot"]["boundary_uncertainty_buffer_m"],"pilot_join_buffer_m":options["lez2027_pilot"]["join_uncertainty_buffer_m"],"buffer_m":2000,"area_km2":exclusion.area()/1e6,
            "policy":"Exclude route physical parts intersecting uncertainty band; do not remove uncertainty bands from the zonepartition"},
        "candidate_quota":options["candidate_quota"],"selection_quota":options["selection_quota"],
        "coverage_limitations":options["coverage_limitations"],"notes":options["notes"]}
    result={"groups":groups,"lez2027":pilot,"lez2030":lez2030,"ring1":rings["ring1"],"ring3":rings["ring3"],"exclusion_geometry":exclusion,
            "lines":{"lez2027":pilot_line,**rings["lines"]},"report":report}
    if output_dir is not None:export(result,output_dir,context)
    return result


def build_regions(work,directory,context,crs,hanoi):
    """Adapter compatible with sampling_abc's current region builder."""
    if crs!="EPSG:3405":raise ValueError("LEZ-first geometry requires EPSG:3405")
    result=build(work,hanoi,context,output_dir=directory)
    return result["groups"],result["report"],result["exclusion_geometry"]


def export(result,output_dir,context):
    folder=Path(output_dir);folder.mkdir(parents=True,exist_ok=True)
    path=folder/"abc_boundaries.gpkg";crs=result["report"]["metric_crs"]
    with sink(path,"abc_groups",[("abc_group","str"),("definition","str"),("area_km2","float"),("policy_version","str"),("official_gis_verified","bool")],QgsWkbTypes.MultiPolygon,crs,context) as out:
        for code,geometry in result["groups"].items():
            g=QgsGeometry(geometry);g.convertToMultiType()
            out.add({"abc_group":code,"definition":result["report"]["zones"][code],"area_km2":g.area()/1e6,"policy_version":result["report"]["policy_version"],"official_gis_verified":False},g)
    with sink(path,"policy_zones",[("zone_id","str"),("effective_from","str"),("status","str"),("official_gis_verified","bool"),("area_km2","float")],QgsWkbTypes.MultiPolygon,crs,context) as out:
        for code,start in (("lez2027","2027-01-01"),("lez2030","2030-01-01"),("ring1","2028-01-01"),("ring3",None)):
            g=QgsGeometry(result[code]);g.convertToMultiType()
            out.add({"zone_id":code,"effective_from":start,"status":"technical_proxy","official_gis_verified":False,"area_km2":g.area()/1e6},g)
    with sink(path,"policy_alignment",[("zone_id","str")],QgsWkbTypes.LineString,crs,context) as out:
        for code,g in result["lines"].items():out.add({"zone_id":code},g)
    with sink(path,"routing_exclusion",[("reason","str"),("area_km2","float")],QgsWkbTypes.MultiPolygon,crs,context) as out:
        g=QgsGeometry(result["exclusion_geometry"]);g.convertToMultiType()
        out.add({"reason":result["report"]["routing_exclusion"]["reason"],"area_km2":g.area()/1e6},g)
    with sink(path,"ring_polygons",[("ring_id","str"),("official_gis_verified","bool")],QgsWkbTypes.MultiPolygon,crs,context) as out:
        for code in ("ring1","ring3"):
            g=QgsGeometry(result[code]);g.convertToMultiType()
            out.add({"ring_id":code,"official_gis_verified":False},g)
    with sink(path,"ring_alignment",[("ring_id","str")],QgsWkbTypes.LineString,crs,context) as out:
        for code in ("ring1","ring3"):out.add({"ring_id":code},result["lines"][code])
    check_layers(path,{"abc_groups":3,"policy_zones":4,"policy_alignment":3,"routing_exclusion":1,"ring_polygons":2,"ring_alignment":2},crs)
    import shutil
    shutil.copy2(path,folder/"policy_boundaries.gpkg")
    atomic_json(folder/"policy_boundaries_report.json",result["report"])
    # Prior sampler expects this reportfilename; it containsLEZ-first metadata.
    atomic_json(folder/"abc_boundaries_report.json",result["report"])
    return path
