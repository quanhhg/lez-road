"""Offline safety/algorithm checks; no HTTP calls and no QGIS import."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lez.graph import MotorcycleNetwork
from lez.routing import anchor_path, classify, corridor_overlap, midrank
from lez.sampling_data import DeferredRequest, _cached_response, request, validate_activity


class RoutingTests(unittest.TestCase):
    def graph(self):
        rows=[('ab','A','B'),('ad','A','D'),('db','D','B'),('bc','B','C')]
        return MotorcycleNetwork({'arcs':[{'arc_id':i,'part_id':i,'from_node':a,'to_node':b,'length_m':1} for i,a,b in rows],
                                  'turn_rules':[{'restriction_id':1,'from_arc':'ab','to_arc':'bc','kind':'no'}]})

    def test_turn_state_is_preserved_at_intermediate_anchor(self):
        network=self.graph();coords={'A':(0,0),'B':(1,0),'C':(2,0),'D':(0,1)}
        walk,_=anchor_path(network,coords,['A','B','C'],set(network.arcs),lambda a:a['length_m'])
        self.assertEqual(walk,['ad','db','bc'])
        self.assertEqual(network.validate_walk(walk),(True,None))

    def test_filtering_only_restriction_does_not_open_other_exit(self):
        network=MotorcycleNetwork({'arcs':[{'arc_id':i,'part_id':i,'from_node':a,'to_node':b,'length_m':1}
                                           for i,a,b in [('ab','A','B'),('bc','B','C'),('bd','B','D')]],
                                  'turn_rules':[{'restriction_id':1,'from_arc':'ab','to_arc':'bd','kind':'only'}]})
        coords={'A':(0,0),'B':(1,0),'C':(2,0),'D':(1,1)}
        walk,_=anchor_path(network,coords,['A','C'],{'ab','bc'},lambda a:1)
        self.assertIsNone(walk)

    def test_reverse_or_repeated_corridor_is_not_a_new_geometry(self):
        self.assertEqual(corridor_overlap(['x','y','x'],['y','x'],{'x':10,'y':20}),1)

    def test_missing_evidence_keeps_reference_without_zero_imputation(self):
        self.assertEqual(classify(None,1,{'population_density':.5,'activity_density':.5},'outside'),
                         ('outside',None,'pending_evidence_reference_retained'))

    def test_ties_get_identical_scores_and_dense_active_area_is_inside(self):
        ranks=midrank([1,1,10]);self.assertEqual(ranks[1],.25);self.assertEqual(ranks[10],1)
        self.assertEqual(classify(1,1,{'population_density':.5,'activity_density':.5},'outside')[0],'inside')
        self.assertEqual(classify(0,0,{'population_density':.5,'activity_density':.5},'inside')[0],'outside')


class HTTPTests(unittest.TestCase):
    def valid(self):
        return {'osm3s':{'timestamp_osm_base':'2026-10-04T00:00:00Z'},'elements':[
                {'type':'node','id':1,'version':1,'timestamp':'2026-09-01T00:00:00Z','lat':21,'lon':105},
                {'type':'count','tags':{'nodes':'1','ways':'0','relations':'0','total':'1'}}]}

    def test_incomplete_counts_remark_and_wrong_snapshot_rejected(self):
        self.assertEqual(validate_activity(self.valid(),'2026-10-01T00:00:00Z'),{'node':1})
        for change in ['count','remark','timestamp']:
            value=self.valid()
            if change=='count':value['elements'][-1]['tags']['total']='2'
            if change=='remark':value['remark']='runtime error: Query timed out'
            if change=='timestamp':value['elements'][0]['timestamp']='2026-10-03T00:00:00Z'
            with self.assertRaises(ValueError):validate_activity(value,'2026-10-01T00:00:00Z')

    def test_long_retry_after_is_deferred_not_truncated_or_bypassed(self):
        session=Mock();session.request.return_value=Mock(status_code=429,headers={'Retry-After':'120'})
        with patch('lez.sampling_data.time.sleep') as sleep:
            with self.assertRaises(DeferredRequest):request(session,'POST','https://example.test')
            self.assertEqual(session.request.call_count,1);sleep.assert_not_called()

    def test_corrupt_cache_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'raw.json';meta=Path(tmp)/'manifest.json'
            raw.write_text('{}');meta.write_text(json.dumps({'identity':'a','sha256':'wrong'}))
            self.assertIsNone(_cached_response(raw,meta,'a'))


class GISRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from qgis.core import QgsGeometry,QgsWkbTypes
        except ImportError:
            raise unittest.SkipTest('Run with registered PyQGIS runtime')
        cls.QgsGeometry=QgsGeometry;cls.QgsWkbTypes=QgsWkbTypes

    def test_line_and_point_collection_retains_all_line_length(self):
        from lez.sampling_2030 import _line
        source=self.QgsGeometry.fromWkt('GEOMETRYCOLLECTION (POINT (0 0), LINESTRING (1 1, 82.444989009 1))')
        result=_line(source)
        self.assertEqual(result.type(),self.QgsWkbTypes.LineGeometry)
        self.assertAlmostEqual(result.length(),81.444989009,places=8)

    def test_polygon_and_line_collection_conforms_to_polygon_layer(self):
        from lez.sampling_2030 import _polygon
        source=self.QgsGeometry.fromWkt('GEOMETRYCOLLECTION (POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0)), LINESTRING (4 4, 5 5))')
        result=_polygon(source)
        self.assertEqual(result.type(),self.QgsWkbTypes.PolygonGeometry)
        self.assertAlmostEqual(result.area(),4)
        self.assertTrue(result.isGeosValid())

    def test_touching_point_is_zero_length(self):
        from lez.sampling_2030 import _line
        source=self.QgsGeometry.fromWkt('POINT (0 0)')
        self.assertTrue(_line(source).isEmpty())

    def test_no_feasible_route_does_not_invent_a_sample_distribution(self):
        import csv
        from collections import Counter
        from lez.gis import initialize
        from lez.sampling_2030 import build_candidates
        options={'targets':[{'route_id':'L01','stratum_id':'V1','rc_target':'RC1'}],
                 'route_design':{'attempts_per_target':1,'target_cell_min_fraction':.3,
                                 'max_corridor_similarity':.7,'overlap_review_fraction':.5}}
        empty=MotorcycleNetwork({'arcs':[],'turn_rules':[]})
        matrix=Counter({('V1','RC1'):100,('N1','RC1'):200})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);context=initialize(root)
            result=build_candidates(root,root,(options,{},context,'EPSG:3405'),None,
                                    (empty,{},{},{},matrix,{}))
            self.assertEqual(result['created_routes'],0)
            self.assertIsNone(result['D_combined'])
            self.assertEqual(result['D_by_domain'],{'inside':None,'outside':None})
            with (root/'sample_matrix.csv').open() as stream:rows=list(csv.DictReader(stream))
            self.assertTrue(all(r['sample_fraction']=='' for r in rows))
            self.assertTrue((root/'candidate_routes.csv').read_text().startswith('route_id,'))


if __name__=='__main__':unittest.main(verbosity=2)
