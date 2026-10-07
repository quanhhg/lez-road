import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lez.sampling_abc import composition
from lez.graph import MotorcycleNetwork
from lez.routing import generate

class SamplingABC(unittest.TestCase):
    def test_matrix_keeps_domains_independent_of_ABC(self):
        matrix={('A','RC1'):100,('B','RC2'):200,('C','RC4'):300,('C',None):30}
        domains={('A','RC1','inside'):80,('A','RC1','outside'):20,('B','RC2','inside'):150,('B','RC2','outside'):50,('C','RC4','inside'):50,('C','RC4','outside'):250}
        network,sample,connectors,report=composition(matrix,{('C','RC4'):60},{('C','RC4'):40},domains)
        self.assertEqual(len(network),12);self.assertEqual(len(sample),12)
        self.assertEqual(report['network_rc_m'],600);self.assertEqual(report['network_rc_domain_m'],{'inside':280,'outside':320})
        self.assertEqual(report['network_connector_m'],30)
        self.assertAlmostEqual(sum(r['network_fraction_all_rc'] for r in network),1)
        self.assertAlmostEqual(report['D_combined'],.5)
    def test_empty_sample_is_unknown(self):
        _,_,_,report=composition({('A','RC1'):100})
        self.assertIsNone(report['D_combined']);self.assertIsNone(report['sample_fraction_sum'])
    def test_negative_length_rejected(self):
        with self.assertRaises(ValueError):composition({('A','RC1'):-1})
    def test_route_uses_explicit_group_and_stays_in_ABC(self):
        coordinates={'0':(0,0),'1':(1000,0),'2':(500,900),'3':(500,400)}
        arcs=[];meta={}
        for i,(u,v) in enumerate([('0','1'),('1','2'),('2','0'),('0','3'),('3','1')]):
            pid=f'p{i}';length=1000 if i<3 else 500
            zone='A' if i<3 else 'B'
            meta[pid]={'pure_group':'inside','pure_zone':zone,'cells':[(zone,'RC1',length)],'reference_inside_m':length,'length_m':length}
            for direction,a,b in [('forward',u,v),('backward',v,u)]:
                arcs.append({'arc_id':pid+direction,'part_id':pid,'from_node':a,'to_node':b,'direction':direction,'length_m':length,'rc':'RC1'})
        network=MotorcycleNetwork({'arcs':arcs,'turn_rules':[]})
        design={'attempts_per_target':30,'minimum_anchor_separation_m':400,'max_search_states':1000,'urban_min_m':1500,'urban_max_m':4000,'outside_min_m':8000,'outside_max_m':10000,'target_cell_min_fraction':.3,'max_corridor_similarity':.7,'overlap_review_fraction':.5}
        routes,failed,_=generate(network,meta,coordinates,[{'route_id':'A01','stratum_id':'A','sampling_zone':'A','group':'inside','rc_target':'RC1'}],design)
        self.assertEqual(failed,[]);self.assertEqual(len(routes),1)
        self.assertEqual(routes[0]['group'],'inside')
        self.assertTrue(all(meta[p]['pure_zone']=='A' for p in routes[0]['part_ids']))
if __name__=='__main__':unittest.main()
