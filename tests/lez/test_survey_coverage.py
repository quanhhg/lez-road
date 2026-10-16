"""T3 temporary, explicitly synthetic fixtures; never write real measurements."""
import copy
import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from lez import survey_coverage as survey
from lez import trip_processing as trips

ROOT = Path(__file__).resolve().parents[2]


def config():
    return survey.configuration(ROOT)


def route(rid="A01", zone="A"):
    return {"route_id": rid, "sampling_zone": zone, "route_version": "route-" + rid,
            "source_bundle_sha256": "TEST_ONLY_bundle", "policy_version": "TEST_ONLY_policy", "length_m": "1000"}


def record():
    return {**route(), "trip_id": "TEST_ONLY_trip", "vehicle_id": "TEST_ONLY_vehicle", "driver_id": "TEST_ONLY_driver",
        "device_id": "TEST_ONLY_device", "started_at": "2026-10-01T07:30:00+07:00", "ended_at": "2026-10-01T07:31:00+07:00",
        "measurement_date": "2026-10-01", "time_block": "morning_peak", "day_type": "weekday", "calendar_checked": "yes",
        "weather": "dry", "event_status": "none_reported", "collection_stage": "main", "travel_direction": "as_planned", "valid": True}


def metric():
    return {**route(), "trip_id": "TEST_ONLY_trip", "metadata_valid": True, "declared_duration_s": 60,
        "speed_valid_duration_s": 60, "gps_valid_duration_s": 60, "matched_duration_s": 60,
        "matched_distance_m": 1000, "match_status_counts": {"matched": 61}}


class SurveyDesignTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config()
        self.now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)

    def evaluate(self, rows=None, metrics=None, cfg=None, **kwargs):
        return survey.evaluate([route()], [record()] if rows is None else rows,
            [metric()] if metrics is None else metrics, cfg or self.cfg, now=self.now, **kwargs)

    def test_schedule_has_unique_stable_slots_without_measurements(self):
        routes = [route(f'{zone}{i:02d}', zone) for zone, n in [('A',10),('B',8),('C',12)] for i in range(1,n+1)]
        rows = survey.schedule_rows(routes, self.cfg)
        self.assertEqual(len(rows), 360)
        self.assertEqual(len({r['plan_id'] for r in rows}), 360)
        self.assertEqual(rows, survey.schedule_rows(list(reversed(routes)), self.cfg))
        self.assertTrue(all(not r['trip_id'] and not r['measurement_date'] for r in rows))
        self.assertTrue(all(r['status'] == 'schedule_template_not_measured' for r in rows))

    def test_no_data_never_counts_proposals_as_measurements(self):
        summary, _, matrix, audit, conditions = self.evaluate([], [])
        self.assertEqual(summary['status'], 'awaiting_measurements')
        self.assertEqual(summary['planned_cells'], 6)
        self.assertEqual(summary['coverage_eligible_trips'], 0)
        self.assertTrue(all(r['valid_trips'] == 0 and r['target_met'] is None for r in matrix))
        self.assertEqual(audit, [])
        self.assertEqual(conditions, [])

    def test_valid_trip_counts_one_cell_but_does_not_certify_sufficiency(self):
        summary, _, matrix, audit, _ = self.evaluate()
        self.assertEqual(summary['status'], 'awaiting_design_confirmation')
        self.assertEqual(summary['observed_cells'], 1)
        self.assertTrue(audit[0]['coverage_eligible'])
        self.assertEqual(audit[0]['route_length_fraction'], 1)
        self.assertFalse(summary['data_sufficiency_assessed'])
        self.assertFalse(summary['field_gates_automatically_passed'])
        self.assertEqual(sum(r['valid_trips'] for r in matrix), 1)

    def test_old_trip_metadata_remains_visible_but_is_not_counted(self):
        r = record()
        for name in survey.EXTRA_TRIP_FIELDS:
            r.pop(name, None)
        summary, _, _, audit, _ = self.evaluate([r])
        self.assertEqual(summary['coverage_eligible_trips'], 0)
        self.assertIn('missing:device_id', audit[0]['reasons'])
        self.assertIn('missing:day_type', audit[0]['reasons'])

    def test_date_uses_hanoi_timezone_and_checks_declared_block(self):
        r = record(); r.update(started_at='2026-10-01T00:30:00Z', ended_at='2026-10-01T00:31:00Z')
        self.assertTrue(self.evaluate([r])[3][0]['coverage_eligible'])
        r.update(time_block='day_off_peak')
        self.assertIn('trip_outside_declared_time_block', self.evaluate([r])[3][0]['reasons'])

    def test_time_block_upper_boundary_and_crossing_are_checked(self):
        r = record(); r.update(started_at='2026-10-01T08:59:00+07:00',ended_at='2026-10-01T09:00:00+07:00')
        self.assertTrue(self.evaluate([r])[3][0]['coverage_eligible'])
        r['ended_at'] = '2026-10-01T09:00:01+07:00'
        self.assertFalse(self.evaluate([r])[3][0]['coverage_eligible'])
        r.update(started_at='2026-10-01T09:00:00+07:00',ended_at='2026-10-01T09:01:00+07:00')
        self.assertFalse(self.evaluate([r])[3][0]['coverage_eligible'])

    def test_weekend_and_holiday_declarations_not_inferred_as_normal_days(self):
        r = record(); r['day_type'] = 'weekend'
        self.assertIn('calendar_weekday_weekend_mismatch', self.evaluate([r])[3][0]['reasons'])
        r.update(day_type='holiday')
        self.assertIn('holiday_needs_calendar_reference', self.evaluate([r])[3][0]['reasons'])
        r.update(calendar_note='TEST_ONLY holiday declaration',calendar_evidence_uri='https://example.org/TEST_ONLY')
        result = self.evaluate([r])
        self.assertTrue(result[3][0]['quality_passed'])
        self.assertFalse(result[3][0]['coverage_eligible'])
        self.assertEqual(result[0]['holiday_trips'], 1)

    def test_sourced_calendar_override_can_mark_special_workday(self):
        cfg = copy.deepcopy(self.cfg)
        cfg['survey_design']['calendar_overrides']['2026-10-03'] = {'day_type':'weekday','source':'TEST_ONLY example'}
        r = record(); r.update(started_at='2026-10-03T07:30:00+07:00',ended_at='2026-10-03T07:31:00+07:00',measurement_date='2026-10-03')
        self.assertTrue(self.evaluate([r],cfg=cfg)[3][0]['coverage_eligible'])
        r['day_type'] = 'weekend'
        self.assertIn('configured_calendar_mismatch', self.evaluate([r],cfg=cfg)[3][0]['reasons'])

    def test_unchecked_calendar_wrong_direction_future_and_version_are_rejected(self):
        for key,value,reason in [('calendar_checked','unknown','calendar_not_checked'),
            ('travel_direction','deviated','direction_not_as_planned'),('route_version','old','route_version_mismatch'),
            ('ended_at','2027-10-01T07:31:00+07:00','invalid_or_future_time_range')]:
            r=record();r[key]=value
            with self.subTest(key=key): self.assertIn(reason,self.evaluate([r])[3][0]['reasons'])

    def test_qc_is_required_and_one_valid_second_cannot_fill_a_cell(self):
        self.assertFalse(self.evaluate(qc_ready=False)[3][0]['coverage_eligible'])
        m=metric();m.update(speed_valid_duration_s=1,gps_valid_duration_s=1,matched_duration_s=1,matched_distance_m=1)
        row=self.evaluate(metrics=[m])[3][0]
        self.assertEqual(row['speed_time_fraction'],1/60)
        for key in ['speed_time_fraction','gps_time_fraction','matched_time_fraction','route_length_fraction']:
            self.assertIn('insufficient_'+key,row['reasons'])

    def test_unknown_weather_event_and_unexplained_exceptions_need_correction(self):
        for updates,reason in [({'weather':'unknown'},'unknown_weather'),({'event_status':'unknown'},'unknown_event_status'),
            ({'weather':'other'},'other_weather_needs_notes'),({'event_status':'unusual_event'},'unusual_event_needs_notes')]:
            r=record();r.update(updates)
            with self.subTest(updates=updates): self.assertIn(reason,self.evaluate([r])[3][0]['reasons'])

    def test_weather_events_pilot_reported_separately_without_fake_gate_passes(self):
        r=record();r.update(weather='heavy_rain',event_status='unusual_event',event_notes='TEST_ONLY event')
        result=self.evaluate([r])
        self.assertTrue(result[3][0]['coverage_eligible'])
        self.assertEqual(result[4][0]['weather'],'heavy_rain')
        self.assertEqual(result[0]['unusual_event_trips'],1)
        r['collection_stage']='pilot'
        result=self.evaluate([r])
        self.assertFalse(result[3][0]['coverage_eligible'])
        self.assertEqual(result[0]['pilot_trips'],1)
        self.assertEqual(result[0]['observed_cells'],0)

    def test_duplicate_trip_plan_and_metrics_cannot_inflate_counts(self):
        self.assertEqual(self.evaluate([record(),record()])[0]['coverage_eligible_trips'],0)
        self.assertFalse(self.evaluate(metrics=[metric(),metric()])[3][0]['coverage_eligible'])
        r=record();r['plan_id']=survey.schedule_rows([route()],self.cfg)[0]['plan_id']
        self.assertTrue(self.evaluate([r])[3][0]['coverage_eligible'])
        r['time_block']='day_off_peak'
        self.assertIn('plan_slot_mismatch',self.evaluate([r])[3][0]['reasons'])

    def test_opposite_GPS_direction_and_zero_denominators_are_rejected(self):
        m=metric();m['match_status_counts']['opposite_direction']=1
        self.assertIn('GPS_opposite_direction',self.evaluate(metrics=[m])[3][0]['reasons'])
        m=metric();m['declared_duration_s']=0
        self.assertFalse(self.evaluate(metrics=[m])[3][0]['coverage_eligible'])

    def test_targets_and_dates_are_independent_of_planning_repeat_count(self):
        cfg=copy.deepcopy(self.cfg)
        cfg['survey_design']['status']='approved'
        cfg['survey_design']['coverage_targets']={'minimum_valid_trips_per_cell':2,'minimum_distinct_dates_per_cell':2}
        r=record();r2=copy.deepcopy(r);r2['trip_id']='TEST_ONLY_second'
        r2.update(started_at='2026-10-01T07:32:00+07:00',ended_at='2026-10-01T07:33:00+07:00')
        m=metric();m2=copy.deepcopy(m);m2['trip_id']=r2['trip_id']
        matrix=self.evaluate([r,r2],[m,m2],cfg=cfg)[2]
        observed=next(x for x in matrix if x['valid_trips'])
        self.assertEqual(observed['remaining_valid_trips'],0)
        self.assertEqual(observed['remaining_distinct_dates'],1)
        self.assertEqual(observed['status'],'below_target')
        r2.update(started_at='2026-10-02T07:30:00+07:00',ended_at='2026-10-02T07:31:00+07:00',measurement_date='2026-10-02')
        result=self.evaluate([r,r2],[m,m2],cfg=cfg)
        self.assertEqual(next(x for x in result[2] if x['valid_trips'])['status'],'target_met')
        self.assertEqual(result[0]['status'],'coverage_incomplete')

    def test_overlapping_resources_cannot_inflate_trip_counts(self):
        r2=record();r2['trip_id']='TEST_ONLY_second'
        m2=metric();m2['trip_id']=r2['trip_id']
        result=self.evaluate([record(),r2],[metric(),m2])
        self.assertEqual(result[0]['coverage_eligible_trips'],0)
        for field in ['device_id','vehicle_id','driver_id']:
            self.assertIn('overlapping_'+field,result[3][0]['reasons'])
        r2.update(device_id='second_device',vehicle_id='second_vehicle',driver_id='second_driver')
        self.assertEqual(self.evaluate([record(),r2],[metric(),m2])[0]['coverage_eligible_trips'],2)

    def test_approved_coverage_completion_still_leaves_T6_pending(self):
        cfg=copy.deepcopy(self.cfg)
        cfg['survey_design']['status']='approved'
        cfg['survey_design']['coverage_targets']={'minimum_valid_trips_per_cell':1,'minimum_distinct_dates_per_cell':1}
        rows=[];metrics=[]
        for day,kind in [('2026-10-01','weekday'),('2026-10-03','weekend')]:
            for block in cfg['time_blocks']:
                r=record();tid='TEST_ONLY_'+day+'_'+block['time_block'];hour=block['local_start']
                minute=int(hour[-2:])+1
                r.update(trip_id=tid,started_at=day+'T'+hour+':00+07:00',ended_at=day+'T'+hour[:3]+f'{minute:02d}'+':00+07:00',
                    measurement_date=day,day_type=kind,time_block=block['time_block'])
                m=metric();m['trip_id']=tid
                rows.append(r);metrics.append(m)
        result=self.evaluate(rows,metrics,cfg=cfg)
        self.assertEqual(result[0]['status'],'coverage_targets_met_pending_T6')
        self.assertFalse(result[0]['data_sufficiency_assessed'])
        self.assertEqual(result[0]['observed_cells'],6)

    def test_config_rejects_ambiguous_or_unapproved_requirements(self):
        for change in ['duplicate_day','overlap','bad_quality','half_targets','approved_without_targets']:
            cfg=copy.deepcopy(self.cfg)
            if change=='duplicate_day':cfg['survey_design']['planned_day_types']=['weekday','weekday']
            elif change=='overlap':cfg['time_blocks'][1]['local_start']='08:00'
            elif change=='bad_quality':cfg['survey_design']['quality_rules']['minimum_speed_time_fraction']=float('nan')
            elif change=='half_targets':cfg['survey_design']['coverage_targets']['minimum_valid_trips_per_cell']=2
            else:cfg['survey_design']['status']='approved'
            with self.subTest(change=change),self.assertRaises(ValueError):survey.configuration(ROOT,cfg)


class SurveyPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='TEST_ONLY_T3_')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'config').mkdir()
        self.cfg=config()
        (self.root/'config/field_workflow.json').write_text(json.dumps(self.cfg))
        self.tc=trips.load_config(ROOT)
        (self.root/'config/trip_processing.json').write_text(json.dumps(self.tc))
        incoming=self.root/self.tc['input_directory'];incoming.mkdir(parents=True)
        self.incoming=incoming
        trips.write_csv(incoming/'trips.csv',[],self.tc['required_trip_fields'])
        trips.write_csv(incoming/'gps_points.csv',[],self.tc['required_point_fields'])
        source=self.root/'TEST_ONLY_source.txt';source.write_text('Synthetic source contract, not a route')
        self.routes=[route(f'{z}{i:02d}',z) for z,n in [('A',10),('B',8),('C',12)] for i in range(1,n+1)]
        self.src={'routes':{r['route_id']:r for r in self.routes},'hashes':{str(source):trips.file_hash(source)}}

    def run_coverage(self,**kwargs):
        with patch.object(trips,'route_sources',return_value=self.src):
            return survey.run(self.root,**kwargs)

    def test_empty_publication_cache_tampering_and_no_source_writes(self):
        before=(self.incoming/'trips.csv').read_bytes()
        result=self.run_coverage()
        self.assertEqual(result['planned_cells'],180)
        self.assertEqual(result['planned_slots'],360)
        self.assertEqual(result['trip_rows'],0)
        self.assertFalse(result['cache_hit'])
        self.assertEqual((self.incoming/'trips.csv').read_bytes(),before)
        directory=Path(result['paths']['directory'])
        self.assertTrue(trips.cache_valid(directory,result['fingerprint']))
        self.assertTrue(self.run_coverage()['cache_hit'])
        (directory/'coverage_matrix.csv').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'Corrupt immutable T3'):self.run_coverage()

    def test_template_upgrade_preserves_populated_BOM_input_byte_for_byte(self):
        p=self.incoming/'trips.csv'
        result=survey.ensure_trip_template(p,self.tc['required_trip_fields'])
        self.assertEqual(result['action'],'empty_template_upgraded')
        with p.open() as f:self.assertIn('device_id',next(csv.reader(f)))
        raw=b'\xef\xbb\xbftrip_id,route_id\r\nTEST_ONLY,A01\r\n'
        p.write_bytes(raw)
        result=survey.ensure_trip_template(p,self.tc['required_trip_fields'])
        self.assertEqual(result['action'],'populated_file_preserved')
        self.assertIn('device_id',result['missing_columns'])
        self.assertEqual(p.read_bytes(),raw)

    def test_new_input_requires_new_QC_instead_of_reusing_old_counts(self):
        r=record();r['lez_status_at_measurement']='unknown'
        trips.write_csv(self.incoming/'trips.csv',[r],list(r))
        result=self.run_coverage()
        self.assertEqual(result['status'],'awaiting_trip_qc')
        self.assertEqual(result['coverage_eligible_trips'],0)

    def test_demo_report_cannot_enter_real_coverage(self):
        with self.assertRaisesRegex(ValueError,'demo/test'):
            self.run_coverage(trip_report={'is_test_data':True})

    def test_atomic_failure_does_not_replace_previous_report(self):
        result=self.run_coverage()
        previous=(self.root/survey.REPORT).read_bytes()
        cfg=copy.deepcopy(self.cfg);cfg['survey_design']['version']='TEST_ONLY_new_design'
        with patch.object(trips,'publish_directory',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
            self.run_coverage(config=cfg)
        self.assertEqual((self.root/survey.REPORT).read_bytes(),previous)
        self.assertTrue(Path(result['paths']['directory']).exists())

    def make_QC_bundle(self):
        r=record();r['lez_status_at_measurement']='unknown'
        trips.write_csv(self.incoming/'trips.csv',[r],list(r))
        inv=trips.input_inventory(self.root,self.tc)
        raw=self.root/'TEST_ONLY_raw_archive';raw.mkdir()
        for label,item in inv.items():
            (raw/(label+'.csv')).write_bytes(Path(item['path']).read_bytes())
        temporary=self.root/'TEST_ONLY_temp';temporary.mkdir()
        directory=self.root/'TEST_ONLY_QC_bundle'
        report={'status':'processed','fingerprint':'TEST_ONLY_qc','is_test_data':False,
            'directory':str(directory),'source_hashes':self.src['hashes'],'input_files':inv,
            'raw_directory':str(raw),'config':self.tc,'map_matching':{'executed':True}}
        trips.atomic_json(temporary/'trips_qc.json',[r])
        trips.atomic_json(temporary/'operating_metrics.json',[metric()])
        trips.publish_directory(temporary,directory,report['fingerprint'],report,['trips_qc.json','operating_metrics.json'])
        return report

    def test_valid_QC_bundle_is_used_and_original_bytes_remain_unchanged(self):
        report=self.make_QC_bundle()
        before=(self.incoming/'trips.csv').read_bytes()
        result=self.run_coverage(trip_report=report)
        self.assertEqual(result['coverage_eligible_trips'],1)
        self.assertEqual(result['observed_cells'],1)
        self.assertEqual((self.incoming/'trips.csv').read_bytes(),before)
        cfg=copy.deepcopy(self.tc);cfg['max_gap_s']=2
        result=self.run_coverage(trip_report=report,trip_config=cfg)
        self.assertEqual(result['status'],'awaiting_trip_qc')
        self.assertEqual(result['coverage_eligible_trips'],0)

    def test_corrupt_QC_or_archived_source_cannot_be_used(self):
        report=self.make_QC_bundle()
        Path(report['raw_directory'],'trips.csv').write_text('corrupt original copy')
        with self.assertRaisesRegex(ValueError,'Archived raw'):
            self.run_coverage(trip_report=report)
        Path(report['raw_directory'],'trips.csv').write_bytes((self.incoming/'trips.csv').read_bytes())
        Path(report['directory'],'operating_metrics.json').write_text('[]')
        with self.assertRaisesRegex(ValueError,'QC immutable bundle'):
            self.run_coverage(trip_report=report)


if __name__=='__main__':
    unittest.main()
