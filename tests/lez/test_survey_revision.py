"""Field updates may change scoring; incomplete evidence never becomes a survey."""
import copy
import unittest
from types import SimpleNamespace
from scripts.lez import selection_metrics as sm
from scripts.lez import survey_revision as sr


class ObservedRevisionTests(unittest.TestCase):
    def setUp(self):
        self.options={'weights':{'C1':25,'C2':15,'C3':15,'C4':15,'C5':10,'C6':10,'C7':10},
                      'tie_tolerance':1e-10,'C6_neutral_assumption':2.5}
        self.feature={'route_id':'A01','length_m':400,'lanes':None,'maxspeed':40,
                      'junctions_per_km':5,'signals_per_km':2.5}
        self.data={'features':[self.feature], 'walks':[{'route_id':'A01','part_ids':['p1','p2'], 'arc_ids':['a1','a2']}],
            'parts':{'p1':{'length_m':100,'tags_json':'{}'}, 'p2':{'length_m':300,'tags_json':'{"lanes":"2", "maxspeed":"40"}'}},
            'normalization':{'model_medians':{'lanes':{'RC2':2},'maxspeed':{'RC2':50}}}}
        self.graph=SimpleNamespace(arcs={'a1':{'part_id':'p1','rc':'RC2','direction':'forward'},
            'a2':{'part_id':'p2','rc':'RC2','direction':'forward'}, 'r1':{'part_id':'p1','rc':'RC2','direction':'backward'},
            'r2':{'part_id':'p2','rc':'RC2','direction':'backward'}})
        self.parts=[{'part_id':'p1','segment_id':'s1'},{'part_id':'p2','segment_id':'s2'}]
        self.decision={'route_id':'A01','G1':'unknown','G4':'unknown','G5':'unknown','G6':'unknown','C6':'','C6_status':'unknown_until_valid_field_evidence'}

    def observation(self,field,value,**kw):
        return dict(route_id='A01',status='observed',evidence_source='field',field=field,value=str(value),
                    coverage='part',part_id='p1',segment_id='s1',observed_at='2026-10-01T10:00:00+07:00',
                    observation_id='fixture',evidence_uri='TEST_ONLY',**kw)

    def overlay(self,rows,decision=None):
        return sr.numeric_overlay(self.data,rows,self.parts,self.graph,[decision or self.decision])

    def test_partial_lanes_are_weighted_and_raw_NULL_preserved(self):
        _, audit=self.overlay([self.observation('lanes',4)])
        self.assertIsNone(self.feature['lanes_osm'])
        self.assertEqual(self.feature['lanes_observed'],4)
        self.assertEqual(self.feature['lanes_observed_length_fraction'],.25)
        self.assertEqual(self.feature['lanes_scoring_model'],2.5)
        self.assertEqual(audit[0]['length_weight_m'],100)

    def test_point_lanes_and_partial_counts_are_not_extrapolated(self):
        r=self.observation('lanes',4);r['coverage']='point'
        c=self.observation('junction_count',8)
        self.overlay([r,c])
        self.assertIsNone(self.feature['lanes_observed'])
        self.assertEqual(self.feature['lanes_scoring_model'],2)
        self.assertEqual(self.feature['junctions_per_km'],5)

    def test_whole_route_count_uses_full_route_km(self):
        r=self.observation('junction_count',8);r['coverage']='whole_route'
        self.overlay([r]);self.assertEqual(self.feature['junctions_per_km'],20)
        self.assertEqual(self.feature['junctions_per_km_osm'],5)

    def test_latest_covered_assessment_wins(self):
        first=self.observation('lanes',4);second=copy.deepcopy(first)
        second.update(value='3',observed_at='2026-10-02T10:00:00+07:00',observation_id='new')
        self.overlay([second,first]);self.assertEqual(self.feature['lanes_observed'],3)

    def test_failed_gate_and_geometry_conflicts_block_candidate(self):
        d=dict(self.decision,G1='failed')
        blocked,_=self.overlay([self.observation('direction_change','changed')],d)
        self.assertIn('failed_G1',blocked['A01'])
        self.assertIn('graph_rebuild_required_direction_change',blocked['A01'])
        self.assertFalse(self.data['eligible_indices'])

    def test_oneway_change_requires_graph_rebuild(self):
        blocked,_=self.overlay([self.observation('oneway','true')])
        self.assertIn('graph_rebuild_required_oneway',blocked['A01'])

    def test_desk_numeric_does_not_become_field_value(self):
        r=self.observation('lanes',4);r['evidence_source']='desk'
        self.overlay([r]);self.assertIsNone(self.feature['lanes_observed'])

    def test_C6_actual_value_removes_unknown_interval(self):
        raw={'C1':.1,'C2':.2,'C3':.3,'C4':.4,'C5':.5,'C6':5,'C7':3}
        records,_=sm.normalize_scores([{'raw':raw}],self.options)
        r=records[0];self.assertFalse(r['C6_score_is_assumption'])
        self.assertEqual(r['normalized']['C6'],1)
        self.assertEqual(r['score_lower_unknown_C6'],r['score_upper_unknown_C6'])
        raw['C6']=None
        records,_=sm.normalize_scores([{'raw':raw}],self.options)
        self.assertTrue(records[0]['C6_score_is_assumption'])
        self.assertAlmostEqual(records[0]['score_upper_unknown_C6']-records[0]['score_lower_unknown_C6'],10)

    def test_observed_C6_zero_is_excluded(self):
        blocked,_=self.overlay([],dict(self.decision,C6='0'))
        self.assertIn('observed_C6_zero',blocked['A01'])

    def test_nonfinite_C6_rejected(self):
        raw={'C1':1,'C2':1,'C3':1,'C4':1,'C5':1,'C6':float('nan'),'C7':1}
        with self.assertRaises(ValueError):sm.normalize_scores([{'raw':raw}],self.options)

if __name__=='__main__':unittest.main()
