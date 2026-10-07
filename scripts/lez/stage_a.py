"""One-command boundary automation, separate from OSM road downloading/network building."""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'lez'

from .common import (WORK, atomic_json, file_hash, input_path, now, processing_lock,
                     publish_link, relative, write_csv)


def preflight_stage_a(work=WORK):
    from .pipeline import kernel_spec
    from .boundary_proposals import validate_rules
    work = Path(work)
    rules = json.loads((work / 'config/boundary_automation.json').read_text())
    validate_rules(rules)
    project = json.loads((work / 'data/hanoi_tiles/tile_project.json').read_text())
    raw = work / 'data/hanoi_tiles/data/raw/hanoi_osm_20261001.json'
    manifest = json.loads(raw.with_name('boundary_manifest.json').read_text())
    if file_hash(raw) != manifest['response_sha256'] or manifest['snapshot_utc'] != project['snapshot_utc']:
        raise ValueError('Boundary cache hash/snapshot mismatch')
    for name in ('boundary_project.json','strata_mapping.csv','boundary_sources.json','legal_pdf_sources.json'):
        if not (work / 'config' / name).is_file():
            raise ValueError('Missing boundary config: ' + name)
    spec = kernel_spec()
    env = os.environ.copy(); env.update(spec.get('env', {}))
    probe = subprocess.run([spec['argv'][0], '-c', "import json,requests;from qgis.core import Qgis;print(json.dumps({'qgis':Qgis.QGIS_VERSION}))"],
                           env=env, capture_output=True, text=True, timeout=30)
    if probe.returncode:
        raise RuntimeError('PyQGIS preflight failed: ' + probe.stderr[-1500:])
    source = input_path(work, rules['legal_scope']['source_file'])
    return {'snapshot_utc':project['snapshot_utc'], 'metric_crs':project['metric_crs'],
            'boundary_raw_hash_valid':True, 'road_cache_scanned':False,
            'legal_pdf_cache_valid':bool(source and source.exists() and file_hash(source) == rules['legal_scope']['verified_sha256']),
            'qgis':json.loads(probe.stdout)['qgis'], 'network_calls':0, 'automatic_activation':False}


def stage_a_status(work=WORK):
    path = Path(work) / 'reports/boundaries/latest_stage_a.json'
    return json.loads(path.read_text()) if path.exists() else {'status':'not_run'}


def _execute(work, fetch_sources=True, force=False):
    from .boundaries import capture_sources, prepare
    from .legal_sources import archive_sources
    from .admin_boundaries import build_admin_units
    from .boundary_proposals import build_proposal
    work = Path(work).resolve()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    report = {'run_id':run_id,'started_at':now(),'status':'running','paths':{},'cache_hits':{},
              'raw_osm_modified':False, 'road_downloads':0,'automatic_activation':False}
    run_file = work / 'reports/boundaries/runs' / (run_id + '.json')
    with processing_lock(work):
        try:
            report['preflight'] = preflight_stage_a(work)
            if fetch_sources:
                report['source_capture'] = {'html':capture_sources(work),'pdf':archive_sources(work)}
            admin_dir, admin_report, hit = build_admin_units(work, force)
            report['admin'] = admin_report
            report['cache_hits']['admin'] = hit
            report['paths']['admin_units'] = relative(admin_dir / 'admin_units.gpkg',work)
            report['paths']['admin_qa'] = relative(admin_dir / 'admin_qa.gpkg',work)
            atomic_json(run_file, report)
            proposal_error = None
            try:
                proposal_dir, proposal, hit = build_proposal(work, admin_dir, force)
                report['proposal'] = proposal
                report['cache_hits']['proposal'] = hit
                report['paths'].update(proposal_dir=relative(proposal_dir,work), draft_zones=proposal['zones'], preview=proposal['preview'],
                                       unassigned_admin_units=relative(proposal_dir / 'unassigned_admin_units.csv',work))
            except (ValueError, OSError) as exc:
                proposal_error = str(exc)
                report['proposal'] = {'status':'needs_input','error':proposal_error}
            active_dir, active, hit = prepare(work, force)
            report['active_boundaries'] = active
            report['stage_a_complete'] = active['stage_a_complete']
            report['cache_hits']['active_boundaries'] = hit
            report['paths']['zones'] = relative(active_dir / 'zones.gpkg',work)
            publish_link(work, 'admin_units.gpkg', admin_dir / 'admin_units.gpkg')
            publish_link(work, 'admin_boundary_qa.gpkg', admin_dir / 'admin_qa.gpkg')
            if not proposal_error:
                publish_link(work, 'zones_draft.gpkg', input_path(work,proposal['zones']))
            # A draft never replaces the active LEZ/strata config or zones.gpkg link.
            decisions = [dict(item, profile='active') for item in active['needs_input']]
            if proposal_error:
                decisions.append({'profile':'draft','component':'proposal','reason':'source_or_rule_error','detail':proposal_error})
            else:
                for row in proposal['boundary_qa']['needs_input']:
                    decisions.append(dict(row, profile='draft'))
                for name in proposal['unassigned_names']:
                    decisions.append({'profile':'draft','component':name,'reason':'unassigned_administrative_unit'})
            for field, area in admin_report['qa'].items():
                if area > 1:
                    decisions.append({'profile':'admin','component':field,'reason':'administrative_geometry_qa_requires_review','area_m2':area})
            fields = ['profile','component','reason','detail','area_m2','missing_area_m2','overlap_area_m2']
            write_csv(work / 'reports/boundaries/decisions_required.csv',decisions,fields)
            report['decisions_required'] = len(decisions)
            report['paths']['decisions_required'] = 'work/reports/boundaries/decisions_required.csv'
            report['status'] = 'complete' if report['stage_a_complete'] else 'automated_with_pending_research_definitions'
            report['finished_at'] = now()
        except KeyboardInterrupt:
            report.update(status='interrupted',finished_at=now())
            raise
        except Exception as exc:
            report.update(status='failed',error=str(exc),finished_at=now())
            raise
        finally:
            atomic_json(run_file,report)
            atomic_json(work / 'reports/boundaries/latest_stage_a.json',report)
    return report


def run_stage_a(work=WORK, fetch_sources=True, force=False, progress=print):
    from .pipeline import kernel_spec
    work = Path(work).resolve()
    spec = kernel_spec()
    env = os.environ.copy(); env.update(spec.get('env', {})); env['PYTHONUNBUFFERED'] = '1'
    arguments = [spec['argv'][0],str(Path(__file__).resolve()),'run','--worker','--work',str(work)]
    if not fetch_sources: arguments.append('--no-fetch-sources')
    if force: arguments.append('--force')
    process = subprocess.Popen(arguments,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    recent, result = deque(maxlen=25), None
    try:
        for line in process.stdout:
            recent.append(line.rstrip())
            try: message = json.loads(line)
            except ValueError:
                if progress: progress(line.rstrip())
                continue
            if message.get('event') == 'result': result = message['result']
            elif progress:
                if message.get('event') == 'progress':
                    progress(f"[{message['stage']}] {message['message']}")
                else: progress(message)
        if process.wait() or result is None:
            raise RuntimeError('Stage A worker failed:\n' + '\n'.join(recent))
        return result
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=10)
        if progress: progress('Đã dừng; các giai đoạn có manifest hoàn chỉnh được giữ để tiếp tục.')
        return stage_a_status(work)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['check','run','status'])
    parser.add_argument('--work',default=str(WORK))
    parser.add_argument('--no-fetch-sources',action='store_true')
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.command == 'check': output = preflight_stage_a(args.work)
    elif args.command == 'status': output = stage_a_status(args.work)
    elif args.worker: output = _execute(args.work,not args.no_fetch_sources,args.force)
    else: output = run_stage_a(args.work,not args.no_fetch_sources,args.force)
    if args.worker: print(json.dumps({'event':'result','result':output},ensure_ascii=False),flush=True)
    else: print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
