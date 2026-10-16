"""T5 hand-calculated cases; synthetic temporary data never enter real storage."""
import copy
import csv
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lez import operating_metrics as kin
from lez import trip_processing as tp

ROOT = Path(__file__).resolve().parents[2]
CFG = tp.load_config(ROOT)


def calculate(seconds, speeds_ms, cfg=None, **changes):
    cfg = copy.deepcopy(cfg or CFG)
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    metadata = {'trip_id':'TEST_ONLY_trip','route_id':'A01','vehicle_id':'TEST_ONLY_vehicle','driver_id':'TEST_ONLY_driver',
        'started_at':start.isoformat(),'ended_at':(start+timedelta(seconds=seconds[-1])).isoformat(),
        'measurement_date':'2020-01-01','time_block':'morning_peak','sampling_zone':'A',
        'lez_status_at_measurement':'unknown','route_version':'TEST_ONLY_route','policy_version':'TEST_ONLY_policy',
        'source_bundle_sha256':'TEST_ONLY_bundle','collection_stage':'main','day_type':'weekday','source_row':2,**changes}
    points = [{'trip_id':metadata['trip_id'],'timestamp':(start+timedelta(seconds=s)).isoformat(),
        'latitude':21,'longitude':105.8,'speed':v,'speed_unit':'m/s','source_row':i+2}
        for i,(s,v) in enumerate(zip(seconds,speeds_ms))]
    tr,pts=tp.validate([metadata],points,cfg,{'A01':metadata})
    details=[];metrics=tp.operating_metrics(tr,pts,cfg,details=details)
    return metrics[0],details[0],cfg


class T5MathematicsTests(unittest.TestCase):
    def test_five_hand_check_examples_pass(self):
        report=kin.self_check(CFG)
        self.assertEqual(report['status'],'passed')
        self.assertEqual(len(report['cases']),5)
        self.assertTrue(report['is_test_data'])
        self.assertEqual(report['real_measurements_created'],0)

    def test_stationary_time_is_kept_and_distance_ratios_are_undefined(self):
        m,d,cfg=calculate([0,1,3],[0,0,0])
        self.assertIsNone(m['rpa_m_s2']);self.assertIsNone(m['pke_m_s2'])
        self.assertEqual(m['distance_metric_status'],'zero_or_near_zero_distance')
        self.assertEqual(m['safd_valid_time_denominator_s'],3)
        self.assertEqual(sum(d['histogram'].values()),3)
        self.assertEqual(m['idle_fraction_valid_speed_time'],1)

    def test_constant_motion_has_zero_rpa_pke_not_null(self):
        m,_,_=calculate([0,1,3],[2,2,2])
        self.assertEqual(m['rpa_m_s2'],0)
        self.assertEqual(m['pke_m_s2'],0)
        self.assertEqual(m['kinematic_distance_m'],6)

    def test_positive_kinetic_energy_has_no_half_factor(self):
        m,_,_=calculate([0,2,4,6],[0,2,2,0])
        self.assertAlmostEqual(m['rpa_numerator_m2_s2'],2)
        self.assertAlmostEqual(m['pke_numerator_m2_s2'],4)
        self.assertAlmostEqual(m['rpa_m_s2'],0.25)
        self.assertAlmostEqual(m['pke_m_s2'],0.5)

    def test_irregular_acceleration_average_is_weighted_by_duration(self):
        m,_,_=calculate([0,1,3],[0,1,5])
        self.assertAlmostEqual(m['mean_acceleration_m_s2'],5/3)
        self.assertNotAlmostEqual(m['mean_acceleration_m_s2'],1.5)
        self.assertAlmostEqual(m['rms_acceleration_m_s2'],math.sqrt(3))

    def test_irregular_negative_average_keeps_sign_and_duration_weight(self):
        m,_,_=calculate([0,1,3],[5,4,0])
        self.assertAlmostEqual(m['mean_deceleration_m_s2'],-5/3)
        self.assertEqual(m['rpa_m_s2'],0)
        self.assertEqual(m['pke_m_s2'],0)

    def test_rpa_threshold_is_separate_from_mode_classification(self):
        cfg=copy.deepcopy(CFG);cfg['operating_metrics']['positive_acceleration_threshold_m_s2']=2
        m,_,_=calculate([0,2],[0,2],cfg)
        self.assertEqual(m['rpa_m_s2'],0)
        self.assertEqual(m['pke_m_s2'],2)
        self.assertEqual(m['acceleration_time_s'],2)

    def test_low_distance_policy_is_configurable_and_recorded(self):
        cfg=copy.deepcopy(CFG);cfg['operating_metrics']['distance_epsilon_m']=10
        m,_,_=calculate([0,2],[0,2],cfg)
        self.assertIsNone(m['rpa_m_s2'])
        self.assertEqual(m['distance_epsilon_m'],10)
        self.assertIsNone(kin.pooled_metrics([m])['rpa_m_s2'])

    def test_gap_is_audited_and_recovery_does_not_bridge_missing_time(self):
        m,d,_=calculate([0,10,11],[0,2,2])
        self.assertEqual(m['kinematic_valid_duration_s'],1)
        self.assertEqual(m['kinematic_distance_m'],2)
        self.assertEqual(d['interval_audit'][0]['status'],'excluded')
        self.assertIn('invalid_or_gap_interval',d['interval_audit'][0]['reasons'])
        self.assertEqual(d['interval_audit'][1]['status'],'used')

    def test_invalid_acceleration_is_excluded_but_next_interval_recovers(self):
        m,d,_=calculate([0,1,2],[0,30,30])
        self.assertEqual(m['kinematic_valid_interval_count'],1)
        self.assertEqual(m['kinematic_distance_m'],30)
        self.assertEqual(d['interval_audit'][0]['status'],'excluded')

    def test_no_usable_intervals_produces_null_values_and_empty_safd(self):
        m,d,_=calculate([0,10],[0,2])
        self.assertIsNone(m['rpa_m_s2'])
        self.assertIsNone(m['kinematic_distance_m'])
        self.assertIsNone(m['safd_in_grid_fraction'])
        self.assertEqual(d['histogram'],{})

    def test_same_linear_profile_sampling_resolution_preserves_integrals(self):
        m1,_,_=calculate([0,2],[0,2])
        m2,_,_=calculate([0,0.5,1,1.5,2],[0,0.5,1,1.5,2])
        for field in ['rpa_m_s2','pke_m_s2','kinematic_distance_m','kinematic_valid_duration_s']:
            self.assertAlmostEqual(m1[field],m2[field])


class T5DistributionTests(unittest.TestCase):
    def test_bin_edges_are_disjoint_and_last_upper_edge_is_included(self):
        edges=[0,5,10]
        self.assertEqual([kin.bin_index(x,edges) for x in [0,5,10]],[0,1,1])
        self.assertIsNone(kin.bin_index(-1,edges))
        self.assertIsNone(kin.bin_index(11,edges))

    def test_crossing_speed_bin_allocates_time_to_both_bins(self):
        cfg=copy.deepcopy(CFG);cfg['operating_metrics']['speed_edges_kmh']=[0,3.6,7.2]
        m,d,cfg=calculate([0,2],[0,2],cfg)
        cells=list(kin.histogram_rows(d['histogram'],m['kinematic_valid_duration_s'],kin.protocol(cfg)))
        self.assertEqual(len(cells),2)
        self.assertAlmostEqual(cells[0]['duration_s'],1)
        self.assertAlmostEqual(cells[1]['duration_s'],1)
        self.assertAlmostEqual(sum(c['fraction_of_valid_time'] for c in cells),1)

    def test_deceleration_crosses_speed_bins_in_reverse_without_negative_time(self):
        cfg=copy.deepcopy(CFG);cfg['operating_metrics']['speed_edges_kmh']=[0,3.6,7.2]
        _,d,_=calculate([0,2],[2,0],cfg)
        self.assertEqual(len(d['histogram']),2)
        self.assertTrue(all(math.isclose(x,1) for x in d['histogram'].values()))

    def test_outside_speed_grid_is_reported_without_clipping_or_renormalizing(self):
        cfg=copy.deepcopy(CFG);cfg['operating_metrics']['speed_edges_kmh']=[0,10]
        m,d,cfg=calculate([0,2],[0,20/3.6],cfg)
        self.assertAlmostEqual(m['safd_in_grid_duration_s'],1)
        self.assertAlmostEqual(m['safd_outside_grid_duration_s'],1)
        fractions=[r['fraction_of_valid_time'] for r in kin.histogram_rows(d['histogram'],2,kin.protocol(cfg))]
        self.assertAlmostEqual(sum(fractions),0.5)
        self.assertEqual(m['safd_status'],'outside_grid_present')

    def test_outside_acceleration_grid_keeps_all_valid_time_in_denominator(self):
        cfg=copy.deepcopy(CFG);cfg['operating_metrics']['acceleration_edges_m_s2']=[-0.1,0.1]
        m,d,_=calculate([0,2],[0,2],cfg)
        self.assertEqual(d['histogram'],{})
        self.assertEqual(m['safd_valid_time_denominator_s'],2)
        self.assertEqual(m['safd_outside_grid_duration_s'],2)
        self.assertEqual(m['safd_in_grid_fraction'],0)

    def test_pooled_safd_uses_seconds_not_equal_weights_per_trip(self):
        cfg=copy.deepcopy(CFG);cfg['operating_metrics']['speed_edges_kmh']=[0,5,10]
        a,da,_=calculate([0,1],[1,1],cfg,trip_id='TEST_ONLY_A')
        b,db,_=calculate([0,3],[2,2],cfg,trip_id='TEST_ONLY_B')
        _,rows,_=kin.export_tables([a,b],[da,db],cfg)
        group=[r for r in rows if r['aggregation']=='overall']
        self.assertEqual(len(group),2)
        self.assertAlmostEqual(group[0]['fraction_of_valid_time'],0.25)
        self.assertAlmostEqual(group[1]['fraction_of_valid_time'],0.75)

    def test_pooled_rpa_uses_distance_numerator_not_mean_of_ratios(self):
        a,_,_=calculate([0,2,4,6],[0,2,2,0])
        b,_,_=calculate([0,5],[20,20])
        summary=next(r for r in tp.operating_summary([a,b]) if r['aggregation']=='overall')
        self.assertAlmostEqual(summary['rpa_m_s2'],2/108)
        self.assertNotAlmostEqual(summary['rpa_m_s2'],(a['rpa_m_s2']+b['rpa_m_s2'])/2)

    def test_pilot_and_main_are_never_silently_pooled(self):
        a,da,cfg=calculate([0,1],[1,1],collection_stage='main')
        b,db,_=calculate([0,1],[2,2],collection_stage='pilot')
        overall=[r for r in tp.operating_summary([a,b]) if r['aggregation']=='overall']
        self.assertEqual({r['collection_stage'] for r in overall},{'pilot','main'})
        _,safd,_=kin.export_tables([a,b],[da,db],cfg)
        self.assertEqual({r['collection_stage'] for r in safd if r['aggregation']=='overall'},{'pilot','main'})

    def test_invalid_metadata_do_not_enter_pooled_safd_or_scalar_metrics(self):
        a,da,cfg=calculate([0,1],[1,1]);b=copy.deepcopy(a);b['metadata_valid']=False
        overall=next(r for r in tp.operating_summary([a,b]) if r['aggregation']=='overall')
        self.assertEqual(overall['excluded_metadata_trips'],1)
        self.assertEqual(overall['kinematic_valid_duration_s'],1)
        _,safd,_=kin.export_tables([a,b],[da,da],cfg)
        self.assertEqual(next(r for r in safd if r['aggregation']=='overall')['valid_time_denominator_s'],1)

    def test_protocol_rejects_invalid_edges_definitions_and_numbers(self):
        variants=[('speed_edges_kmh',[0,5,5]),('acceleration_edges_m_s2',[0,float('nan')]),
            ('distance_epsilon_m',0),('positive_acceleration_threshold_m_s2',True),
            ('positive_acceleration_threshold_m_s2','0'),('pke_definition','include_half'),('interval_model','bridge_gaps')]
        for key,value in variants:
            cfg=copy.deepcopy(CFG);cfg['operating_metrics'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):tp.load_config(config=cfg)


class T5StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='TEST_ONLY_T5_');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.incoming=self.root/'fixtures';self.incoming.mkdir()
        self.cfg=copy.deepcopy(CFG);self.cfg['map_matching']['enabled']=False
        self.source={'routes':{'A01':{'sampling_zone':'A','policy_version':'TEST_ONLY_policy','route_version':'TEST_ONLY_route','source_bundle_sha256':'TEST_ONLY_bundle'}},
            'hashes':{},'snapshot_utc':'2026-10-01T00:00:00Z','source_bundle_sha256':'TEST_ONLY_bundle'}
        self.patch=patch.object(tp,'route_sources',return_value=self.source);self.patch.start();self.addCleanup(self.patch.stop)
        t={'trip_id':'TEST_ONLY_trip','route_id':'A01','vehicle_id':'TEST_ONLY_vehicle','driver_id':'TEST_ONLY_driver',
            'started_at':'2020-01-01T07:00:00+07:00','ended_at':'2020-01-01T07:00:02+07:00','measurement_date':'2020-01-01',
            'time_block':'morning_peak','sampling_zone':'A','lez_status_at_measurement':'unknown','policy_version':'TEST_ONLY_policy','route_version':'TEST_ONLY_route','source_bundle_sha256':'TEST_ONLY_bundle'}
        points=[{'trip_id':t['trip_id'],'timestamp':f'2020-01-01T07:00:0{i}+07:00','latitude':21,'longitude':105.8,'speed':v,'speed_unit':'m/s'} for i,v in [(0,0),(2,2)]]
        tp.write_csv(self.incoming/'trips.csv',[t],list(t))
        tp.write_csv(self.incoming/'gps_points.csv',points,list(points[0]))

    def run_import(self):
        return tp.run(self.root,config=self.cfg,input_dir=self.incoming,output_root=self.root,demo=True)

    def test_exports_are_complete_versioned_and_integrity_checked(self):
        report=self.run_import();directory=Path(report['directory'])
        expected=['safd_by_trip.json','safd_by_group.json','safd_by_trip.csv','safd_by_group.csv','kinematic_intervals.csv','operating_protocol.json']
        for name in expected:self.assertTrue((directory/name).is_file(),name)
        self.assertEqual(report['operating_metrics_version'],kin.VERSION)
        metrics=json.loads((directory/'operating_metrics.json').read_text())
        self.assertEqual(metrics[0]['rpa_m_s2'],1)
        self.assertEqual(metrics[0]['pke_m_s2'],2)
        self.assertTrue(self.run_import()['cache_hit'])
        (directory/'safd_by_trip.json').write_text('corrupt')
        with self.assertRaisesRegex(RuntimeError,'Corrupted immutable'):self.run_import()

    def test_bin_change_reuses_byte_identical_raw_copy_but_creates_new_results(self):
        before=(self.incoming/'gps_points.csv').read_bytes()
        first=self.run_import();self.cfg['operating_metrics']['speed_edges_kmh']=[0,10,180]
        second=self.run_import()
        self.assertNotEqual(first['directory'],second['directory'])
        self.assertEqual(first['raw_directory'],second['raw_directory'])
        self.assertEqual((self.incoming/'gps_points.csv').read_bytes(),before)

    def test_empty_real_input_reports_waiting_not_zero_rpa(self):
        for name,fields in [('trips.csv',self.cfg['required_trip_fields']),('gps_points.csv',self.cfg['required_point_fields'])]:tp.write_csv(self.incoming/name,[],fields)
        report=tp.run(self.root,config=self.cfg,input_dir=self.incoming,output_root=self.root)
        self.assertEqual(report['status'],'awaiting_measurements')
        self.assertEqual(report['operating_metrics_status'],'awaiting_measurements')
        self.assertEqual(report['safd_trip_rows'],0)
        self.assertNotIn('directory',report)
        self.assertFalse(report['is_test_data'])

    def test_corridor_preparation_still_works_before_any_measurement(self):
        def worker(project,payload):
            result={'routes':{'A01':{'arcs':[{'arc_id':'TEST_ONLY_arc'}]}}}
            tp.atomic_json(payload['result'],result)
            return result
        with patch.object(tp,'qgis_call',side_effect=worker):
            prepared=tp.prepare(self.root,config=self.cfg,output_root=self.root)
        self.assertEqual(prepared['status'],'prepared')
        self.assertEqual(prepared['route_count'],1)
        directory=Path(prepared['directory'])
        self.assertEqual({p.name for p in directory.iterdir()},{'corridors.json','qa.json','manifest.json'})
        with patch.object(tp,'qgis_call',side_effect=AssertionError('cache should be reused')):
            self.assertTrue(tp.prepare(self.root,config=self.cfg,output_root=self.root)['cache_hit'])


if __name__=='__main__':unittest.main()
