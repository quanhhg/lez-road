"""Meaningful checks for scenario semantics and the unchanged selection engine."""
import copy
import json
from pathlib import Path
import sys
import unittest

import numpy as np
from lez import selection_metrics as metrics
from lez import selection_sensitivity as sensitivity

sys.path.insert(0,str(Path(metrics.__file__).resolve().parents[2]/'tests/lez'))
from test_selection_abc import toy_abc, options


CFG = json.loads((Path(sensitivity.__file__).with_name('selection_sensitivity.json')
                 if Path(sensitivity.__file__).with_name('selection_sensitivity.json').exists()
                 else Path(metrics.__file__).resolve().parents[2]/'config/selection_sensitivity.json').read_text())


def toy_features():
    data=toy_abc()
    for i,row in enumerate(data['features']):
        row['quota_bucket']=metrics.quota_bucket(row,options())
        row.update({name:float(i%7)/6 for name in metrics.FEATURES})
        row.update(lanes=2.,maxspeed=50.,lanes_scoring_model=2.+i/100,
                   maxspeed_scoring_model=50.+i/10,lanes_imputed_length_fraction=.5,
                   maxspeed_imputed_length_fraction=.5,C6=None)
    data['bins']=[{(name,i//15) for name in metrics.FEATURES} for i in range(60)]
    return data


class SensitivityTests(unittest.TestCase):
    def test_zscore_keeps_rank_groups_and_uses_population_std(self):
        data=toy_features();original=copy.deepcopy(data['features'])
        transformed,params=sensitivity.scenario_data(data,{'scaling':'zscore'},CFG)
        self.assertEqual(transformed['bins'],data['bins'])
        self.assertTrue(params['C3_rank_groups_unchanged'])
        self.assertTrue(np.allclose(transformed['X'].mean(axis=0),0,atol=1e-12))
        self.assertTrue(np.allclose(transformed['X'].std(axis=0),1,atol=1e-12))
        self.assertEqual(data['features'],original)
        self.assertTrue(np.isfinite(transformed['distances']).all())

    def test_constant_features_drop_and_nonfinite_rejected(self):
        data=toy_features()
        for row in data['features']:row['P_RC1']=1.
        _,params=sensitivity.scenario_data(data,{},CFG)
        self.assertIn('P_RC1',params['dropped_constant'])
        data['features'][0]['P_RC2']=float('nan')
        with self.assertRaisesRegex(ValueError,'nonfinite'):
            sensitivity.scenario_data(data,{},CFG)

    def test_missing_component_shift_preserves_observation_and_complete_values(self):
        f={'lanes':2.,'lanes_scoring_model':3.,'lanes_imputed_length_fraction':.5}
        self.assertEqual(sensitivity.shifted_model(f,'lanes',1,[1,8]),3.5)
        self.assertEqual(f['lanes'],2.)
        f['lanes_imputed_length_fraction']=0
        self.assertEqual(sensitivity.shifted_model(f,'lanes',1,[1,8]),3.)
        f={'lanes':None,'lanes_scoring_model':2.,'lanes_imputed_length_fraction':1.}
        self.assertEqual(sensitivity.shifted_model(f,'lanes',-10,[1,8]),1.)

    def test_C6_heterogeneity_changes_score_without_inventing_raw_observation(self):
        opts=options();original=metrics.normalize_scores
        records=[{'route_id':rid,'raw':{f'C{i}':None if i==6 else .5 for i in range(1,8)}} for rid in ('A01','A02')]
        adapter=sensitivity.score_adapter(original,{'A01':1,'A02':5})
        result,_=adapter(records,opts)
        self.assertAlmostEqual(result[1]['score']-result[0]['score'],8.)
        self.assertTrue(all(r['raw']['C6'] is None for r in result))
        self.assertTrue(all(r['C6_score_is_assumption'] for r in result))
        self.assertIs(metrics.normalize_scores,original)
        with self.assertRaisesRegex(ValueError,'1,5'):
            sensitivity.score_adapter(original,{'A01':0,'A02':5})(copy.deepcopy(records),opts)

    def test_isolated_engine_does_not_patch_normal_module(self):
        isolated=sensitivity.isolated_engine();original=metrics.normalize_scores
        isolated.normalize_scores=lambda *a:None
        self.assertIs(metrics.normalize_scores,original)

    def test_scenario_definitions_reproduce_seed_and_zero_exclusions(self):
        ids=[f'{z}{i:02d}' for z in 'ABC' for i in range(1,21)]
        baseline=ids[:10]+ids[20:28]+ids[40:52]
        specs=sensitivity.scenarios(ids,baseline,CFG)
        self.assertEqual(specs,sensitivity.scenarios(ids,baseline,CFG))
        self.assertEqual(len(specs),114)
        availability=[s for s in specs if s['family']=='availability']
        self.assertEqual(len(availability),30)
        self.assertEqual({s['excluded_routes'][0] for s in availability},set(baseline))
        for s in specs:
            if s.get('C6_assumptions'):
                self.assertEqual(set(s['C6_assumptions']),set(ids))
                self.assertTrue(all(1<=v<=5 for v in s['C6_assumptions'].values()))

    def test_unavailable_candidate_never_reintroduced_and_quota_failure_explicit(self):
        data=toy_features();opts=options();engine=sensitivity.isolated_engine()
        selected,history,_,_=engine.select(data,opts)
        ids=[data['walks'][i]['route_id'] for i in selected];blocked=ids[0]
        spec={'id':'blocked','family':'availability','excluded_routes':[blocked]}
        result=sensitivity.run_scenario(engine,data,opts,spec,CFG,ids,history[-1]['selected_after'])
        self.assertEqual(result['status'],'completed')
        self.assertNotIn(blocked,result['selected_route_ids'])
        self.assertEqual(result['metrics']['quota_bucket_counts'],{'A_inside':10,'B_inside':8,'C_outside':12})
        spec.update(excluded_routes=[r['route_id'] for r in data['walks'] if r['route_id'].startswith('C')][:9],expected_infeasible=True)
        result=sensitivity.run_scenario(engine,data,opts,spec,CFG,ids,history[-1]['selected_after'])
        self.assertEqual(result['status'],'infeasible')
        self.assertEqual(result['available_by_quota_bucket']['C_outside'],11)


if __name__=='__main__':unittest.main()
