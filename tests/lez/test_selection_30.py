import copy
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lez.selection_metrics import D, criteria, feasible_add, normalize_scores, number, select, summary


def toy():
    cells=[('V1','RC1'),('V2','RC4'),('N1','RC1'),('N2','RC4')]
    features=[];vectors=[];walks=[];parts={};pc={};sets=[]
    for i,(group,s,rc) in enumerate([('inside','V1','RC1'),('inside','V1','RC1'),('inside','V2','RC4'),('inside','V2','RC4'),('outside','N1','RC1'),('outside','N1','RC1'),('outside','N2','RC4'),('outside','N2','RC4')]):
        v=np.zeros(4);j=next(j for j,c in enumerate(cells) if c==(s,rc));v[j]=10+i
        rid=f'R{i}';pid=f'p{i}';features.append({'route_id':rid,'group':group,'stratum_id':s,'rc_target':rc})
        vectors.append(v);walks.append({'route_id':rid,'length_m':float(v.sum())});parts[pid]={'length_m':float(v.sum())};pc[pid]=[(j,float(v.sum()))];sets.append({pid})
    vectors=np.array(vectors);X=np.arange(8)[:,None]/7
    return {'cells':cells,'features':features,'walks':walks,'vectors':vectors,'q':np.array([.1,.4,.1,.4]),
            'network_lengths':np.array([100.,400.,100.,400.]),'P':vectors/vectors.sum(axis=1)[:,None],
            'X':X,'distances':np.abs(X-X.T),'bins':[{('f',i//2)} for i in range(8)],
            'overlaps':np.eye(8),'corridors':np.eye(8),'part_sets':sets,'parts':parts,'part_cells':pc,
            'masks':{'inside':np.array([True,True,False,False]),'outside':np.array([False,False,True,True])}}


def options():
    return {'quota':{'inside':2,'outside':2},'required_strata':['V1','V2','N1','N2'],
            'weights':{'C1':25,'C2':15,'C3':15,'C4':15,'C5':10,'C6':10,'C7':10},
            'minimum_cell_fraction':.3,'tie_tolerance':1e-10,'seed_count':4,'max_corridor_overlap':.7,
            'max_swap_rounds':10,'swap_min_improvement':1e-9,'minimum_quantile_diversity_retained':.9,'max_domain_D_worsening':.02}


class SelectionTests(unittest.TestCase):
    def test_missing_attribute_stays_unknown(self):
        for v in (None,'','signals','2;3','50|60','none'):
            self.assertIsNone(number(v,speed=True))
        self.assertEqual(number('2'),2)
        self.assertIsNone(number('1.5'))
        self.assertIsNone(number('2 km/h'))
        self.assertIsNone(number('0'))
        self.assertEqual(number('1.5',speed=True),1.5)
        self.assertAlmostEqual(number('30 mph',speed=True),48.28032)

    def test_empty_sample_is_not_a_zero_distribution(self):
        self.assertIsNone(D(np.zeros(4),np.ones(4)/4))
        self.assertEqual(D(np.ones(4),np.ones(4)/4),0)

    def test_quota_does_not_discard_an_unrepresented_stratum(self):
        d=toy();o=options()
        self.assertFalse(feasible_add(d,[0,4],1,o['quota'],set(o['required_strata'])))
        self.assertTrue(feasible_add(d,[0,4],2,o['quota'],set(o['required_strata'])))

    def test_unknown_C6_keeps_raw_missing_and_separate_neutral_assumption(self):
        d=toy();r,n=criteria(d,[0,4],[2,3,6,7],options())
        self.assertEqual(n['effective_weights'],{c:w/100 for c,w in options()['weights'].items()})
        self.assertAlmostEqual(sum(n['effective_weights'].values()),1)
        self.assertIsNone(n['C6_observation'])
        self.assertEqual(n['C6_assumed_for_scoring_only'],2.5)
        for row in r:
            self.assertIsNone(row['raw']['C6'])
            self.assertEqual(row['normalized']['C6'],.5)
            self.assertTrue(row['C6_score_is_assumption'])
            self.assertAlmostEqual(row['score_upper_unknown_C6']-row['score_lower_unknown_C6'],10)
            self.assertAlmostEqual(row['score']-row['score_lower_unknown_C6'],5)
            self.assertAlmostEqual(row['score_upper_unknown_C6']-row['score'],5)

    def test_constant_C1_to_C5_receive_one_and_preserve_nominal_weights(self):
        raw=[{'route_id':rid,'raw':{'C1':.2,'C2':.1,'C3':.4,'C4':.6,'C5':.3,'C6':None,'C7':0}}
             for rid in ('A','B')]
        r,n=normalize_scores(raw,options())
        self.assertEqual(n['effective_weights'],{c:w/100 for c,w in options()['weights'].items()})
        self.assertEqual(n['constant_rule'],'all_one_preserve_weights')
        for row in r:
            self.assertEqual({c:row['normalized'][c] for c in ('C1','C2','C3','C4','C5')},
                             dict.fromkeys(('C1','C2','C3','C4','C5'),1.0))
            self.assertAlmostEqual(row['score'],85)
            self.assertAlmostEqual(row['score_lower_unknown_C6'],80)
            self.assertAlmostEqual(row['score_upper_unknown_C6'],90)

    def test_drop_C6_is_an_explicit_sensitivity_policy(self):
        o=options();o['C6_missing_policy']='unknown_weight_zero_renormalize_other_criteria'
        r,n=criteria(toy(),[0,4],[2,3,6,7],o)
        expected={c:(0 if c=='C6' else w/90) for c,w in o['weights'].items()}
        self.assertEqual(n['effective_weights'],expected)
        self.assertAlmostEqual(sum(n['effective_weights'].values()),1)
        self.assertIsNone(n['C6_assumed_for_scoring_only'])
        for row in r:
            self.assertIsNone(row['raw']['C6'])
            self.assertIsNone(row['normalized']['C6'])
            self.assertFalse(row['C6_score_is_assumption'])
            self.assertAlmostEqual(row['score_lower_unknown_C6'],row['score'])
            self.assertAlmostEqual(row['score_upper_unknown_C6'],row['score'])

    def test_drop_constant_criterion_requires_an_explicit_sensitivity_policy(self):
        o=options();o['constant_criterion_policy']='drop_and_renormalize_weights'
        d=toy();r,n=criteria(d,[0,4],[2,3],o)
        self.assertEqual(n['effective_weights']['C4'],0)
        self.assertIsNone(r[0]['normalized']['C4'])
        self.assertAlmostEqual(sum(n['effective_weights'].values()),1)

    def test_selection_is_deterministic_and_preserves_quota_and_strata(self):
        d=toy();o=options();s,h,sw,_=select(d,o);other=select(d,o)[0]
        self.assertEqual(s,other)
        metrics=summary(d,s)
        self.assertEqual((metrics['inside'],metrics['outside']),(2,2))
        self.assertEqual(set(metrics['represented_primary_strata']),set(o['required_strata']))
        self.assertEqual(len(set(s)),4)
        self.assertTrue(all(x['D_after']<x['D_before'] for x in sw))

    def test_history_explains_candidates_blocked_by_quota(self):
        s,h,sw,_=select(toy(),options())
        self.assertTrue(any(r['hard_rejected_candidates'] for r in h[1:]))
        self.assertTrue(all('effective_weights' in r['normalization'] for r in h[1:]))

    def test_overlap_cost_is_not_rewarded(self):
        o=options();raw=[{'raw':{'C1':1,'C2':1,'C3':1,'C4':v,'C5':1,'C6':None,'C7':0},'route_id':str(v)} for v in [0,.6]]
        r,n=normalize_scores(raw,o)
        self.assertGreater(r[0]['score'],r[1]['score'])
        self.assertEqual((r[0]['normalized']['C4'],r[1]['normalized']['C4']),(1,0))
        self.assertAlmostEqual(r[0]['score']-r[1]['score'],15)


if __name__=='__main__':unittest.main()
