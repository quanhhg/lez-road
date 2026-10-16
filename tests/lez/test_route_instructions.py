"""T2 contracts: preserve directed occurrences, GPX and immutable publications."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from lez import route_instructions as ri

PROJECT = Path(__file__).resolve().parents[2]
CFG = ri.configuration(PROJECT)


def fixture(lines=None, names=None, ids=None, extra_tags=None):
    lines = lines or [[[0, 0], [100, 0]], [[100, 0], [100, 100]]]
    names = names or ["Phố Một", "Phố Hai"]
    ids = ids or ["a"+str(i)+":F" for i in range(len(lines))]
    metadata, tags, outgoing, nodes, arcs = {}, {}, {}, {}, []
    for i,(line,name,aid) in enumerate(zip(lines,names,ids)):
        start,end = str(tuple(line[0])),str(tuple(line[-1]))
        sid=aid.split(":")[0]
        backward=aid.endswith(":B")
        source={"arc_id":aid,"part_id":sid+":p0","segment_id":sid,"way_id":i,
                "from_node":start,"to_node":end,"direction":"backward" if backward else "forward",
                "length_m":ri.path_length(line)}
        metadata[aid]=source
        tags[sid]={"name":name,**((extra_tags or {}).get(i,{}))}
        nodes[start]=[105+line[0][0]/100000,21+line[0][1]/100000]
        nodes[end]=[105+line[-1][0]/100000,21+line[-1][1]/100000]
        outgoing.setdefault(start,[]).append(source)
        arcs.append({k:source[k] for k in ["arc_id","from_node","to_node","direction","length_m"]}|
                    {"order":i,"coordinates":line,"start_m":sum(ri.path_length(l) for l in lines[:i])})
    walk={"route_id":"A01","arc_ids":ids,"group":"inside"}
    row={"route_id":"A01","sampling_zone":"A","group":"inside","policy_version":"test-policy",
         "route_version":"test-version","source_bundle_sha256":"test-source",
         "length_m":sum(ri.path_length(l) for l in lines)}
    return walk,row,{"arcs":arcs},(metadata,tags,outgoing,nodes)


def planned_route(**kwargs):
    w,m,c,a=fixture(**kwargs)
    r=ri.build_route(w,m,c,a,CFG)
    wgs=lambda p:[105+p[0]/100000,21+p[1]/100000]
    r["coordinates_wgs84"]=[wgs(p) for p in r["coordinates"]]
    for arc in r["arcs"]:arc["coordinates_wgs84"]=[wgs(p) for p in arc["coordinates"]]
    for step in r["steps"]:
        step["start_wgs84"]=wgs(step["start_xy"]);step["end_wgs84"]=wgs(step["end_xy"])
    return r


class GeometryTests(unittest.TestCase):
    def test_turn_signs_and_wraparound(self):
        east=[[0,0],[100,0]]
        self.assertAlmostEqual(ri.turn_angle(east,[[100,0],[100,100]],12),90)
        self.assertAlmostEqual(ri.turn_angle(east,[[100,0],[100,-100]],12),-90)
        self.assertEqual(ri.maneuver(179,CFG),"uturn")
        self.assertEqual(ri.maneuver(-179,CFG),"uturn")
        self.assertEqual(ri.maneuver(15,CFG),"straight")

    def test_repeated_coordinates_and_short_arc_have_stable_tangents(self):
        self.assertEqual(ri.tangent([[0,0],[0,0],[1,0]],12),[1,0])
        self.assertEqual(ri.compass([[0,0],[1,0]],12),"Đông")

    def test_repeated_arc_occurrences_and_uturn_are_not_deduplicated(self):
        lines=[[[0,0],[100,0]],[[100,0],[0,0]],[[0,0],[100,0]]]
        w,m,c,a=fixture(lines=lines,names=["Phố Một"]*3,ids=["a:F","a:B","a:F"])
        route=ri.build_route(w,m,c,a,CFG)
        self.assertEqual([v for s in route["steps"] for v in s["arc_ids"]],w["arc_ids"])
        self.assertEqual(route["coordinates"],[[0,0],[100,0],[0,0],[100,0]])
        self.assertEqual(route["length_m"],300)
        self.assertEqual(sum(s["maneuver"]=="uturn" for s in route["steps"]),2)
        self.assertAlmostEqual(sum(s["length_m"] for s in route["steps"]),300)

    def test_disconnected_geometry_is_rejected(self):
        w,m,c,a=fixture(lines=[[[0,0],[100,0]],[[101,0],[101,100]]])
        with self.assertRaisesRegex(ValueError,"Disconnected"):ri.build_route(w,m,c,a,CFG)

    def test_changed_direction_or_length_is_rejected(self):
        w,m,c,a=fixture()
        c["arcs"][0]["direction"]="backward"
        with self.assertRaisesRegex(ValueError,"direction"):ri.build_route(w,m,c,a,CFG)
        w,m,c,a=fixture();m["length_m"]+=2
        with self.assertRaisesRegex(ValueError,"length"):ri.build_route(w,m,c,a,CFG)

    def test_unnamed_road_is_identified_without_invented_name(self):
        r=planned_route(names=["",""])
        self.assertTrue(all(a["unnamed"] for a in r["arcs"]))
        self.assertIn("chưa có tên OSM",r["steps"][0]["road_name"])
        self.assertIn("unnamed_road",r["steps"][0]["review_flags"])

    def test_roundabout_has_no_invented_exit_number(self):
        r=planned_route(extra_tags={1:{"junction":"roundabout"}})
        self.assertEqual(r["steps"][1]["maneuver"],"roundabout_enter")
        self.assertIn("roundabout_review",r["steps"][1]["review_flags"])
        self.assertNotIn("lối ra thứ",r["steps"][1]["instruction"])

    def test_named_bend_without_branch_still_preserves_geometry(self):
        r=planned_route(lines=[[[0,0],[100,0]],[[100,0],[150,10]]],names=["Phố Một"]*2)
        self.assertEqual(len(r["steps"]),2)  # one moving step plus arrival
        self.assertEqual(r["steps"][0]["arc_ids"],["a0:F","a1:F"])

    def test_invalid_thresholds_and_nonfinite_config_are_rejected(self):
        for key,value in [("bearing_distance_m",float("nan")),("expected_route_count",True),
                          ("straight_angle_deg",90),("endpoint_tolerance_m",-1)]:
            cfg=copy.deepcopy(CFG);cfg[key]=value
            with self.assertRaises(ValueError):ri.configuration(config=cfg)


class ExportTests(unittest.TestCase):
    def test_long_segments_get_ordered_direction_arrows(self):
        r=planned_route(lines=[[[0,0],[9900,0]],[[9900,0],[10000,0]]],names=["A","A"])
        root=ET.fromstring(ri.route_svg(r))
        arrows=[p for p in root.iter("{http://www.w3.org/2000/svg}path") if p.get("marker-end")]
        self.assertGreaterEqual(len(arrows),18)
        xs=[float(p.get("d").split(",")[0][1:]) for p in arrows]
        self.assertEqual(xs,sorted(xs))

    def test_dropped_gpx_points_cannot_be_marked_complete(self):
        r=planned_route()
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            sums,steps,reviews=ri.render_exports([r],p,{"snapshot_utc":"2026-10-01"},CFG)
            path=p/"gpx/A01.gpx";tree=ET.parse(path)
            segment=tree.find(".//{"+ri.GPX_NS+"}trkseg")
            segment.remove(list(segment)[-1]);tree.write(path)
            with self.assertRaisesRegex(ValueError,"number"):
                ri._validate_bundle([r],{"walk_rows":[fixture()[0]]},sums,steps,reviews,0,p)

    def test_gpx_preserves_retracing_and_has_no_measurement_timestamps(self):
        r=planned_route(lines=[[[0,0],[100,0]],[[100,0],[0,0]]],names=["A","A"])
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"route.gpx";ri.export_gpx(r,path)
            root=ET.parse(path).getroot();ns={"g":ri.GPX_NS}
            pts=root.findall("g:trk/g:trkseg/g:trkpt",ns)
            self.assertEqual(len(pts),len(r["coordinates_wgs84"]))
            self.assertEqual(pts[0].attrib,pts[-1].attrib)
            self.assertEqual(len(root.findall("g:wpt",ns)),len(r["steps"]))
            self.assertEqual(root.findall(".//g:time",ns),[])
            self.assertIn("không phải",root.find("g:metadata/g:desc",ns).text)

    def test_untrusted_road_names_are_escaped_in_html_and_valid_xml(self):
        bad='<script>alert("x")</script> & Phố'
        route=planned_route(names=[bad,"Phố Hai"])
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            ri.render_exports([route],p,{"snapshot_utc":"2026-10-01T00:00:00Z"},CFG)
            sheet=(p/"routes/A01.html").read_text()
            self.assertNotIn(bad,sheet)
            self.assertIn("&lt;script&gt;",sheet)
            self.assertNotIn("@@ROWS@@",sheet)
            ET.parse(p/"gpx/A01.gpx")
            self.assertTrue((p/"maps/A01.svg").is_file())
            self.assertTrue((p/"gpx_30_routes.zip").is_file())
            stored=json.loads((p/"route_instructions.json").read_text())
            self.assertEqual(stored["routes"][0]["arcs"][0]["road_name"],bad)

    def test_endpoint_transform_check_catches_swapped_coordinates(self):
        r=planned_route();nodes=fixture()[3][3]
        self.assertLess(ri.check_wgs84_endpoints([r],nodes,CFG),0.001)
        r["arcs"][0]["coordinates_wgs84"][0]=[21,105]
        with self.assertRaises(ValueError):ri.check_wgs84_endpoints([r],nodes,CFG)


class SourceContractsTests(unittest.TestCase):
    def test_reordered_or_duplicate_source_routes_are_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);walks=p/"selected_walks.json"
            walks.write_text(json.dumps([{"route_id":"A01","arc_ids":["a:F","b:F"]}]))
            (p/"selected_route_arcs.csv").write_text("route_id,order,arc_id\nA01,0,b:F\nA01,1,a:F\n")
            src={"walks":str(walks),"routes":{"A01":{}},"hashes":{}}
            cfg={**CFG,"expected_route_count":1}
            with patch.object(ri.tp,"route_sources",return_value=src):
                with self.assertRaisesRegex(ValueError,"disagrees"):ri.source_inputs(p,cfg)
            walks.write_text(json.dumps([{"route_id":"A01","arc_ids":["a:F"]}]*2))
            with patch.object(ri.tp,"route_sources",return_value=src):
                with self.assertRaisesRegex(ValueError,"duplicated"):ri.source_inputs(p,{**cfg,"expected_route_count":2})


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.w,self.m,self.c,self.attrs=fixture()
        self.corridors=self.root/"corridor-cache";self.corridors.mkdir()
        (self.corridors/"corridors.json").write_text(json.dumps({"routes":{"A01":self.c}}))
        self.source={"routes":{"A01":self.m},"walk_rows":[self.w],"hashes":{},"ordered_arcs":{},
                     "selection":str(self.root/"selection.json"),"snapshot_utc":"2026-10-01T00:00:00Z",
                     "source_bundle_sha256":"fixture-source"}
        self.cfg={**CFG,"expected_route_count":1}

    def run_fixture(self):
        def coords(routes,*args):
            for r in routes:
                complete=planned_route()
                r["coordinates_wgs84"]=complete["coordinates_wgs84"]
                for arc,other in zip(r["arcs"],complete["arcs"]):arc["coordinates_wgs84"]=other["coordinates_wgs84"]
                for step,other in zip(r["steps"],complete["steps"]):
                    step["start_wgs84"]=other["start_wgs84"];step["end_wgs84"]=other["end_wgs84"]
        from contextlib import ExitStack
        with ExitStack() as s:
            s.enter_context(patch.object(ri,"source_inputs",return_value=self.source))
            s.enter_context(patch.object(ri,"source_attributes",return_value=self.attrs))
            s.enter_context(patch.object(ri,"add_wgs84",side_effect=coords))
            s.enter_context(patch.object(ri.tp,"load_config",return_value={}))
            s.enter_context(patch.object(ri.tp,"prepare",return_value={
                "direction_and_turns_validated":True,"directory":str(self.corridors)}))
            return ri.run(self.root,config=self.cfg,progress=None)

    def test_second_run_reuses_verified_cache_and_detects_tampering(self):
        first=self.run_fixture();second=self.run_fixture()
        self.assertFalse(first["cache_hit"]);self.assertTrue(second["cache_hit"])
        self.assertTrue((self.root/"maps/route_instructions").is_symlink())
        self.assertTrue(ri.status(self.root)["cache_valid"])
        d=ri.tp.resolve(self.root,first["paths"]["directory"])
        (d/"route_steps.csv").write_text("corrupted")
        self.assertEqual(ri.status(self.root)["status"],"cache_invalid")
        with self.assertRaisesRegex(RuntimeError,"Corrupt"):self.run_fixture()

    def test_interrupted_export_keeps_previous_publication(self):
        first=self.run_fixture();before=(self.root/ri.REPORT).read_bytes()
        self.cfg["bearing_distance_m"]=13
        with patch.object(ri,"render_exports",side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.run_fixture()
        self.assertEqual((self.root/ri.REPORT).read_bytes(),before)
        self.assertTrue(ri.tp.resolve(self.root,first["paths"]["index"]).is_file())
        self.assertFalse(list((self.root/"data/processed/route_instructions").glob(".t2-*")))

    def test_real_directory_is_never_replaced_by_map_link(self):
        (self.root/"maps/route_instructions").mkdir(parents=True)
        keep=self.root/"maps/route_instructions/user.txt";keep.write_text("keep")
        with self.assertRaisesRegex(RuntimeError,"non-symlink"):self.run_fixture()
        self.assertEqual(keep.read_text(),"keep")


if __name__=="__main__":unittest.main()
