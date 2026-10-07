"""Sensitivity integration: ordering, failures, interrupts and cache forwarding."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from lez import project_automation as automation


def selection():
    return {'status':'proposed_for_survey', 'selected_route_ids':[f'A{i:02d}' for i in range(1,11)]+[f'B{i:02d}' for i in range(1,9)]+[f'C{i:02d}' for i in range(1,13)],
            'policy_version':'policy_v1','paths':{'directory':'work/data/processed/selection_30/baseline'}}


def sensitivity():
    base=selection()
    return {'status':'completed_pre_survey_sensitivity','cache_hit':True,
            'baseline_reproduced_exactly':True,'baseline_selected_ids':base['selected_route_ids'],
            'baseline_directory':base['paths']['directory'],'policy_version':'policy_v1',
            'total_scenarios':114,'completed_scenarios':113,'expected_infeasible_scenarios':1,
            'unexpected_infeasible_scenarios':0,'network_calls':0,'baseline_selection_modified':False}


class AutomationSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.work=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)

    def run_with_mocks(self, sensitivity_result=None, sensitivity_error=None, force=False):
        calls=[];messages=[]
        def callback(name,result):
            def fn(*args,**kwargs):
                calls.append(name)
                if name=='sensitivity' and sensitivity_error:
                    raise sensitivity_error
                return copy.deepcopy(result)
            return fn
        with ExitStack() as stack:
            stack.enter_context(patch.object(automation,'preflight',return_value={'policy_version':'policy_v1'}))
            targets=[
                ('lez.sampling_abc.run_sampling','sampling',{'candidates':{'geometry_quota_achieved':True,'created_routes':60}}),
                ('lez.selection_30.run_selection','selection',selection()),
                ('lez.selection_sensitivity.run_sensitivity','sensitivity',sensitivity_result or sensitivity()),
                ('lez.export_route_maps.export_maps','maps',{'status':'exported'}),
                ('lez.field_workflow.prepare','field_templates',{'directory':str(self.work/'field')}),
                ('lez.field_workflow.status','field_status',{'status':'awaiting_field_observations'}),
                ('lez.field_workflow.build_update_plan','update_plan',{'status':'proposed_update_plan'}),
                ('lez.survey_revision.run','revision',{'status':'awaiting_field_observations','surveyed_set_locked':False}),
                ('lez.trip_processing.prepare','corridors',{'status':'prepared'}),
                ('lez.trip_processing.run','trips',{'status':'awaiting_measurements','trip_count':0}),
                ('lez.trip_processing.load_config','trip_config',{})]
            mocks={name:stack.enter_context(patch(target,side_effect=callback(name,result))) for target,name,result in targets}
            try:
                result=automation.run(self.work,force=force,progress=messages.append)
            except BaseException as exc:
                result=exc
        return result,calls,mocks,messages

    def test_sensitivity_after_selection_expected_infeasibility_is_reported(self):
        result,calls,mocks,messages=self.run_with_mocks()
        self.assertIsInstance(result,dict)
        self.assertEqual(calls[:4],['sampling','selection','sensitivity','maps'])
        self.assertEqual(result['status'],'automated_pre_survey_complete_awaiting_field_evidence')
        self.assertEqual(result['sensitivity_scenarios'],114)
        self.assertEqual(result['sensitivity_completed_scenarios'],113)
        self.assertEqual(result['sensitivity_expected_infeasible_scenarios'],1)
        self.assertTrue(result['steps']['selection_sensitivity']['cache_hit'])
        self.assertIn('selection_sensitivity',result['step_seconds'])
        self.assertGreaterEqual(result['step_seconds']['selection_sensitivity'],0)
        mocks['sensitivity'].assert_called_once()
        self.assertIs(mocks['sensitivity'].call_args.kwargs['force'],False)
        self.assertEqual(result,automation.status(self.work))
        self.assertEqual(result['measured_trips'],0)

    def test_force_option_is_forwarded_to_sensitivity(self):
        result,_,mocks,_=self.run_with_mocks(force=True)
        self.assertIsInstance(result,dict)
        self.assertIs(mocks['sensitivity'].call_args.kwargs['force'],True)

    def test_unresolved_scenario_stops_before_maps_and_preserves_completed_steps(self):
        value=sensitivity();value.update(status='completed_with_unresolved_scenarios',completed_scenarios=112,
            unexpected_infeasible_scenarios=1,unresolved=[{'id':'test_unresolved','reason':'no feasible seed'}])
        result,calls,_,_=self.run_with_mocks(sensitivity_result=value)
        self.assertIsInstance(result,ValueError)
        report=automation.status(self.work)
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['active_step'],'selection_sensitivity')
        self.assertEqual(list(report['steps']),['sampling_60','selection_30','selection_sensitivity'])
        self.assertNotIn('maps',calls)
        self.assertIn('test_unresolved',report['error'])

    def test_interruption_reports_active_step_then_resumes_with_cache(self):
        result,calls,_,_=self.run_with_mocks(sensitivity_error=KeyboardInterrupt())
        self.assertIsInstance(result,KeyboardInterrupt)
        report=automation.status(self.work)
        self.assertEqual(report['status'],'interrupted')
        self.assertEqual(report['active_step'],'selection_sensitivity')
        self.assertEqual(list(report['steps']),['sampling_60','selection_30'])
        self.assertNotIn('maps',calls)
        resumed,_,mocks,_=self.run_with_mocks()
        self.assertEqual(resumed['status'],'automated_pre_survey_complete_awaiting_field_evidence')
        self.assertTrue(resumed['steps']['selection_sensitivity']['cache_hit'])
        self.assertIs(mocks['sensitivity'].call_args.kwargs['force'],False)

    def test_stale_baseline_cannot_be_marked_complete(self):
        value=sensitivity();value['baseline_selected_ids'][0]='A20'
        result,calls,_,_=self.run_with_mocks(sensitivity_result=value)
        self.assertIsInstance(result,ValueError)
        self.assertIn('baseline',str(result))
        self.assertNotIn('maps',calls)

    def test_incomplete_counts_are_rejected(self):
        value=sensitivity();value['total_scenarios']=115
        with self.assertRaisesRegex(ValueError,'incomplete'):
            automation.validate_sensitivity(value,selection(),self.work)

    def test_initial_preflight_checks_protocol_without_requiring_frozen_selection(self):
        (self.work/'config').mkdir()
        (self.work/'data/raw/research').mkdir(parents=True)
        (self.work/'reports/overpass').mkdir(parents=True)
        (self.work/'data/hanoi_tiles').mkdir(parents=True)
        (self.work/'config/lez_policy.json').write_text(json.dumps({'policy_version':'policy_v1',
            'classification_basis':'dated_LEZ2027_pilot_and_LEZ2030_planned_ring3',
            'allow_population_activity_boundary_adjustments':False,'sources':[]}))
        (self.work/'data/raw/research/source_requirements.json').write_text(json.dumps({'current_request':{}}))
        (self.work/'reports/overpass/completion_audit.json').write_text('{}')
        (self.work/'data/hanoi_tiles/tiles.csv').write_text('tile_id,status\none,done\n')
        with ExitStack() as stack:
            stack.enter_context(patch('lez.sampling_abc.configuration',return_value={'method_version':'ABC_LEZ_FIRST_v1','policy_version':'policy_v1'}))
            stack.enter_context(patch('lez.selection_30.configuration',return_value={'zone_basis':'LEZ_first','policy_version':'policy_v1'}))
            stack.enter_context(patch('lez.sampling_abc.preflight',return_value={'status':'ready'}))
            stack.enter_context(patch('lez.trip_processing.load_config',return_value={}))
            stack.enter_context(patch('lez.field_workflow.config',return_value={}))
            protocol=stack.enter_context(patch('lez.selection_sensitivity.protocol',return_value={'method_version':'sensitivity_v1'}))
            frozen=stack.enter_context(patch('lez.selection_sensitivity.preflight_sensitivity',side_effect=AssertionError('fresh work has no selection yet')))
            result=automation.preflight(self.work)
        protocol.assert_called_once_with(self.work)
        frozen.assert_not_called()
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['sensitivity_method_version'],'sensitivity_v1')


if __name__=='__main__':unittest.main()
