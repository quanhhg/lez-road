"""Offline regression checks for topology, access, restrictions and boundary gaps."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from lez.access import classify_way, directional_decision, directions, node_decision, restriction_spec
from lez.common import atomic_json, file_hash
from lez.graph import MotorcycleNetwork
from lez.network import build_network, split_ranges
from lez.osm_index import merge_objects


class AccessTests(unittest.TestCase):
    def test_specific_motorcycle_overrides_generic_denial(self):
        result = classify_way({"highway":"residential","access":"no","motorcycle":"yes"})
        self.assertEqual(result["status"],"provisionally_allowed")
        self.assertFalse(result["verified"])

    def test_missing_motorcycle_is_never_verified(self):
        self.assertEqual(classify_way({"highway":"primary"})["status"],"provisionally_allowed")
        self.assertFalse(classify_way({"highway":"primary"})["verified"])

    def test_conditional_is_not_ignored(self):
        self.assertEqual(classify_way({"highway":"residential","motorcycle:conditional":"no @ (Mo-Fr)"})["status"],"review_required")

    def test_reverse_and_motorcycle_oneway_exception(self):
        self.assertEqual(directions({"oneway":"-1"})[0],["backward"])
        self.assertEqual(directions({"oneway":"yes","oneway:motorcycle":"no"})[0],["forward","backward"])
        self.assertEqual(set(directions({"oneway":"yes","motorcycle:backward":"yes","motor_vehicle:backward":"no"})[0]),{"forward","backward"})
        self.assertTrue(directions({"oneway:motorcycle":"yes","motorcycle:backward":"yes"})[1])

    def test_directional_denial_and_generic_specificity(self):
        tags={"highway":"residential","motorcycle:backward":"no"}
        base=classify_way(tags)
        self.assertEqual(directional_decision(tags,"backward",base)["status"],"excluded")
        for highway,status in (("motorway","excluded"),("trunk","review_required")):
            tags={"highway":highway,"access":"no","motorcycle:forward":"yes"}
            self.assertEqual(directional_decision(tags,"forward",classify_way(tags))["status"],status)
        self.assertEqual(directional_decision(tags,"forward",base)["status"],"provisionally_allowed")
        self.assertEqual(directional_decision({"motorcycle":"yes","access:backward":"no"},"backward",base)["status"],"provisionally_allowed")
        tags={"highway":"residential","access":"no","motorcycle:forward":"yes"}
        base=classify_way(tags)
        self.assertEqual(directional_decision(tags,"forward",base)["status"],"provisionally_allowed")
        self.assertEqual(directional_decision(tags,"backward",base)["status"],"excluded")

    def test_barrier_and_highway_review(self):
        self.assertEqual(node_decision({"barrier":"gate"})[0],"review_required")
        self.assertEqual(node_decision({"barrier":"gate","motorcycle":"yes"})[0],"provisionally_allowed")
        self.assertEqual(classify_way({"highway":"trunk","motorcycle":"yes"})["status"],"review_required")
        self.assertEqual(classify_way({"highway":"motorway"})["status"],"excluded")
        self.assertEqual(node_decision({"barrier":"gate","motorcycle":"yes","locked":"yes"})[0],"review_required")

    def test_turn_exceptions_and_via_way(self):
        obj={"id":1,"tags":{"type":"restriction","restriction":"no_left_turn","except":"motorcycle"},"members":[]}
        self.assertEqual(restriction_spec(obj)["status"],"not_applicable")
        obj["tags"].pop("except")
        obj["members"]=[{"type":"way","ref":10,"role":"from"},{"type":"way","ref":11,"role":"via"},{"type":"way","ref":12,"role":"to"}]
        self.assertEqual(restriction_spec(obj)["reason"],"via_way_state_not_implemented")

    def test_real_ids_drive_cuts(self):
        self.assertEqual(split_ranges([1,2,3,4],{2,3}),[(0,1),(1,2),(2,3)])
        self.assertEqual(split_ranges([1,2,3,4],{99}),[(0,3)])

    def test_conflicting_objects_are_not_silently_selected(self):
        db=sqlite3.connect(":memory:")
        db.executescript("CREATE TABLE objects(type,id,version,payload,sha256,PRIMARY KEY(type,id));CREATE TABLE object_tiles(type,id,tile_id,PRIMARY KEY(type,id,tile_id));")
        obj={"type":"node","id":1,"version":1,"lat":0,"lon":0}
        signatures={}
        self.assertEqual(merge_objects(db,[obj],"a",signatures),1)
        self.assertEqual(merge_objects(db,[obj],"b",signatures),0)
        with self.assertRaisesRegex(ValueError,"Conflicting snapshot"):
            merge_objects(db,[dict(obj,lon=1)],"c",signatures)
        db.close()

    def test_turn_aware_graph_applies_no_and_only(self):
        arcs=[{"arc_id":"a","from_node":"1","to_node":"2"},{"arc_id":"b","from_node":"2","to_node":"3"},{"arc_id":"c","from_node":"2","to_node":"4"}]
        graph=MotorcycleNetwork({"arcs":arcs,"turn_rules":[{"kind":"no","restriction_id":1,"from_arc":"a","to_arc":"b"}]})
        self.assertFalse(graph.validate_walk(["a","b"])[0]);self.assertTrue(graph.validate_walk(["a","c"])[0])
        graph=MotorcycleNetwork({"arcs":arcs,"turn_rules":[{"kind":"only","restriction_id":1,"from_arc":"a","to_arc":"b"}]})
        self.assertFalse(graph.validate_walk(["a","c"])[0]);self.assertTrue(graph.validate_walk(["a","b"])[0])


class GISIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:import qgis.core
        except ImportError:raise unittest.SkipTest("Run GIS integration checks with the registered PyQGIS interpreter")

    def boundary_fixture(self, work, definitions=False, overlap=False):
        from lez.gis import QgsGeometry,QgsWkbTypes,initialize,sink
        from qgis.core import QgsRectangle
        for directory in ('config','maps/hanoi_tiles','data/hanoi_tiles/data/raw','data/raw'):(work/directory).mkdir(parents=True,exist_ok=True)
        context=initialize(work)
        def polygon(path,layer,rows):
            with sink(path,layer,[("stratum_id","str")],QgsWkbTypes.MultiPolygon,'EPSG:3857',context) as output:
                for code,rect in rows:
                    g=QgsGeometry.fromRect(QgsRectangle(*rect));g.convertToMultiType();output.add({'stratum_id':code},g)
        polygon(work/'maps/hanoi_tiles/hanoi_download_grid.gpkg','download_tiles',[('grid',(0,0,100,100))])
        polygon(work/'data/raw/hanoi.gpkg','hanoi',[('hanoi',(0,0,100,100))])
        raw=work/'data/hanoi_tiles/data/raw/hanoi_osm_20261001.json';atomic_json(raw,{})
        atomic_json(raw.with_name('boundary_manifest.json'),{'response_sha256':file_hash(raw)})
        atomic_json(work/'data/hanoi_tiles/tile_project.json',{'snapshot_utc':'2026-10-01T00:00:00Z','metric_crs':'EPSG:3857'})
        config={'hanoi_source':{'path':'data/raw/hanoi.gpkg','status':'technical_osm','scope_confirmed':definitions},'lez_source':{'path':'data/raw/lez.gpkg' if definitions else None,'status':'research_confirmed','source_id':'fixture'},'strata_mapping':'config/strata_mapping.csv'}
        atomic_json(work/'config/boundary_project.json',config)
        codes=['V'+str(i) for i in range(1,6)]+['N'+str(i) for i in range(1,11)]
        fields=['stratum_id','domain','geometry_path','layer','selector_field','selector_values','source_id','status']
        with (work/'config/strata_mapping.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
            for code in codes:writer.writerow({'stratum_id':code,'domain':'inside' if code.startswith('V') else 'outside','geometry_path':'data/raw/strata.gpkg' if definitions else '', 'layer':'strata','selector_field':'stratum_id','selector_values':json.dumps([code]),'source_id':'fixture','status':'research_confirmed'})
        if definitions:
            polygon(work/'data/raw/lez.gpkg','lez',[('lez',(0,0,50,100))])
            rows=[]
            for i in range(1,6):rows.append(('V'+str(i),((i-1)*10,0,i*10+(1 if overlap and i==1 else 0),100)))
            for i in range(1,11):rows.append(('N'+str(i),(50+(i-1)*5,0,50+i*5,100)))
            polygon(work/'data/raw/strata.gpkg','strata',rows)

    def test_missing_boundary_inputs_are_reported_without_fake_strata(self):
        from lez.boundaries import prepare
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);self.boundary_fixture(work)
            directory,report,_=prepare(work)
            self.assertFalse(report['stage_a_complete'])
            self.assertEqual(report['layers']['strata'],0)
            self.assertFalse(report['invented_lez_or_strata'])
            self.assertTrue(any(p['component']=='lez_2030' for p in report['needs_input']))
            self.assertTrue(prepare(work)[2])

    def test_explicit_polygons_pass_and_overlap_fails(self):
        from lez.boundaries import prepare
        for overlap in (False,True):
            with self.subTest(overlap=overlap), tempfile.TemporaryDirectory() as folder:
                work=Path(folder);self.boundary_fixture(work,True,overlap)
                _,report,_=prepare(work)
                self.assertEqual(report['layers']['strata'],15)
                self.assertEqual(report['stage_a_complete'],not overlap)
                if overlap:self.assertGreater(report['strata_qa']['V']['overlap_area_m2'],1)

    def test_network_scope_clipping_direction_barrier_and_no_false_bridge_join(self):
        from lez.gis import QgsGeometry,QgsWkbTypes,initialize,sink
        from qgis.core import QgsPointXY,QgsRectangle
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);(work/'config').mkdir();index=work/'index';index.mkdir();boundary=work/'boundary';boundary.mkdir()
            atomic_json(work/'config/access_rules.json',{})
            context=initialize(work)
            scope=QgsGeometry.fromRect(QgsRectangle(-222.64,-222.64,222.64,222.64))
            scope.convertToMultiType()
            with sink(boundary/'zones.gpkg','hanoi',[("id","str")],QgsWkbTypes.MultiPolygon,'EPSG:3857',context) as out:out.add({'id':'hanoi'},scope)
            db=sqlite3.connect(index/'osm_index.sqlite');db.executescript("CREATE TABLE objects(type,id,payload);CREATE TABLE object_tiles(type,id,tile_id);")
            locations={1:(-.001,0),2:(0,0),3:(.001,0),5:(0,.001),6:(-.001,.0005),7:(.001,.0005),8:(-.001,-.001),9:(.001,-.001),10:(-.001,.0015),11:(.001,.0015),12:(-.003,.0009),13:(.001,.0009)}
            for n,(x,y) in locations.items():
                obj={'type':'node','id':n,'lon':x,'lat':y,'version':1,'tags':{'barrier':'gate'} if n==9 else {}}
                db.execute('INSERT INTO objects VALUES (?,?,?)',('node',n,json.dumps(obj)))
            definitions=[(10,[1,2],{}),(11,[2,3],{}),(20,[2,5],{}),(30,[6,7],{'bridge':'yes','layer':'1'}),(40,[8,9],{}),(50,[10,11],{'oneway':'-1'}),(60,[12,13],{})]
            for w,refs,tags in definitions:
                db.execute('INSERT INTO objects VALUES (?,?,?)',('way',w,json.dumps({'type':'way','id':w,'version':1,'nodes':refs,'tags':{'highway':'residential',**tags}})))
                db.execute('INSERT INTO object_tiles VALUES (?,?,?)',('way',w,'fixture'))
            rel={'type':'relation','id':999,'tags':{'type':'restriction','restriction':'no_left_turn'},'members':[{'type':'way','ref':10,'role':'from'},{'type':'node','ref':2,'role':'via'},{'type':'way','ref':20,'role':'to'}]}
            db.execute('INSERT INTO objects VALUES (?,?,?)',('relation',999,json.dumps(rel)));db.commit();db.close()
            output,report,_=build_network(work,index,{'metric_crs':'EPSG:3857','snapshot_utc':'2026-10-01T00:00:00Z','selected_tiles':1,'is_full_scope':False,'counts':{'node':len(locations),'way':7,'relation':1}},boundary)
            core=sqlite3.connect(output/'network_tables.sqlite');core.row_factory=sqlite3.Row
            self.assertEqual(report['restriction_statuses']['resolved'],1)
            self.assertEqual(core.execute('SELECT COUNT(*) FROM arcs WHERE way_id=40 AND routable=1').fetchone()[0],0)
            self.assertEqual(core.execute('SELECT direction FROM arcs WHERE way_id=50').fetchone()[0],'backward')
            self.assertEqual(core.execute("SELECT COUNT(*) FROM nodes WHERE node_id='osm/2'").fetchone()[0],1)
            self.assertFalse(any(r[0]=='osm/2' for r in core.execute('SELECT from_node FROM arcs WHERE way_id=30')))
            self.assertGreater(core.execute('SELECT COUNT(*) FROM nodes WHERE artificial=1').fetchone()[0],0)
            clipped=core.execute('SELECT length_m,scope_length_m FROM segments WHERE way_id=60').fetchone()
            self.assertLess(clipped['scope_length_m'],clipped['length_m'])
            a=core.execute("SELECT arc_id FROM arcs WHERE way_id=10 AND direction='forward'").fetchone()[0]
            b=core.execute("SELECT arc_id FROM arcs WHERE way_id=20 AND direction='forward'").fetchone()[0]
            graph=MotorcycleNetwork.load(output/'motorcycle_graph.json.gz')
            self.assertFalse(graph.validate_walk([a,b])[0])
            self.assertEqual(report['dangling_arc_endpoints'],0)
            self.assertEqual(report['verified_allowed_segments'],0)
            core.close()
            self.assertTrue(build_network(work,index,{'metric_crs':'EPSG:3857','snapshot_utc':'2026-10-01T00:00:00Z','selected_tiles':1,'is_full_scope':False,'counts':{}},boundary)[2])


if __name__=='__main__':unittest.main(verbosity=2)
