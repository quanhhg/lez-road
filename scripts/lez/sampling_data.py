"""Sequential, resumable HTTP inputs for the LEZ research sampler (no QGIS import)."""
from __future__ import annotations

import json
import math
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

from .common import WORK, atomic_bytes, atomic_json, digest, file_hash, input_path, now, relative


class DeferredRequest(RuntimeError):
    pass


def request(session, method, url, **kwargs):
    """Finite retries; a long server cooldown is deferred, never shortened."""
    from email.utils import parsedate_to_datetime
    error = None
    for attempt in range(3):
        try:
            response = session.request(method, url, timeout=(20, 210), **kwargs)
            if response.status_code in {429, 500, 502, 503, 504}:
                raw = response.headers.get('Retry-After')
                delay = 5 * 2 ** attempt + random.random()
                if raw:
                    try:
                        server_delay = float(raw)
                    except ValueError:
                        try:
                            server_delay = (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds()
                        except (TypeError,ValueError):
                            server_delay = 0
                    delay = max(delay, server_delay)
                code = response.status_code
                response.close()
                if delay > 60:
                    raise DeferredRequest(f'HTTP {code}: retry after at least {delay:.1f}s in a later run')
                error = RuntimeError(f'Temporary HTTP {code}')
                if attempt < 2:
                    time.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout) as exc:
            error = exc
            if attempt < 2:
                time.sleep(5 * 2 ** attempt + random.random())
    raise RuntimeError(f'Request failed after 3 attempts: {error}')


def validate_activity(payload, snapshot):
    if not isinstance(payload, dict) or payload.get('remark') or not payload.get('osm3s'):
        raise ValueError('Overpass error, incomplete response, or missing metadata')
    objects = payload.get('elements')
    if not isinstance(objects, list) or not objects or objects[-1].get('type') != 'count':
        raise ValueError('Missing final Overpass count')
    counts = Counter(o.get('type') for o in objects[:-1])
    tags = objects[-1].get('tags', {})
    for singular, plural in [('node', 'nodes'), ('way', 'ways'), ('relation', 'relations')]:
        if int(tags.get(plural, -1)) != counts[singular]:
            raise ValueError('Overpass count mismatch: ' + plural)
    if int(tags.get('total', -1)) != len(objects)-1 or set(counts) - {'node', 'way', 'relation'}:
        raise ValueError('Overpass total/type mismatch')
    if payload['osm3s']['timestamp_osm_base'] < snapshot:
        raise ValueError('Server base predates requested snapshot')
    ids = set()
    for obj in objects[:-1]:
        key = (obj['type'], obj['id'])
        if key in ids or not obj.get('version') or not obj.get('timestamp') or obj['timestamp'] > snapshot:
            raise ValueError('Duplicate ID or metadata inconsistent with requested snapshot')
        ids.add(key)
        position = obj if obj['type'] == 'node' else obj.get('center', {})
        if not (-90 <= position.get('lat', 100) <= 90 and -180 <= position.get('lon', 200) <= 180):
            raise ValueError('Activity object has no usable point/center')
    return dict(counts)


def _cached_response(raw_path, manifest_path, identity):
    try:
        manifest = json.loads(manifest_path.read_text())
        if manifest['identity'] == identity and manifest['sha256'] == file_hash(raw_path):
            return json.loads(raw_path.read_text())
    except (OSError, KeyError, ValueError):
        pass
    return None


def fetch_inputs(work=WORK, progress=print):
    from .common import processing_lock
    with processing_lock(work):
        return _fetch_inputs(work,progress)


def _fetch_inputs(work=WORK, progress=print):
    work = Path(work)
    prepared = json.loads((work / 'data/interim/sampling/requests.json').read_text())
    folder = work / 'data/raw/sampling'
    folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({'User-Agent': 'Hanoi-LEZ-research/0.3 (sequential sampling inputs)', 'Accept': 'application/json'})
    errors, population, activities = [], [], []
    report = {'started_at': now(), 'new_population_parts': 0, 'population_cache_parts': 0,
              'new_activity_queries': 0, 'activity_cache_queries': 0}
    try:
        # Exactly one Overpass request in flight, at the configured endpoint.
        for task in prepared['activity_queries']:
            query, name = task['query'], task['name']
            identity = digest({'query': query, 'endpoint': prepared['endpoint'], 'snapshot': prepared['snapshot_utc']})
            raw = folder / ('activity_' + name + '.json')
            meta = raw.with_suffix('.manifest.json')
            payload = _cached_response(raw, meta, identity)
            try:
                if payload is not None:
                    try:
                        validate_activity(payload, prepared['snapshot_utc'])
                    except ValueError:
                        payload = None
                if payload is None:
                    if progress: progress('Overpass: ' + name)
                    response = request(session, 'POST', prepared['endpoint'], data={'data': query})
                    content = response.content
                    payload = response.json()
                    check = validate_activity(payload, prepared['snapshot_utc'])
                    # Preserve the exact HTTP response, not a rewritten JSON serialization.
                    atomic_bytes(raw, content)
                    atomic_json(meta, {'identity': identity, 'sha256': file_hash(raw), 'downloaded_at': now(),
                                       'endpoint': prepared['endpoint'], 'snapshot': prepared['snapshot_utc'],
                                       'query': query, 'counts': check, 'valid': True})
                    report['new_activity_queries'] += 1
                    time.sleep(8)
                else:
                    report['activity_cache_queries'] += 1
                for obj in payload['elements'][:-1]:
                    position = obj if obj['type'] == 'node' else obj['center']
                    activities.append({'osm_key': obj['type'] + '/' + str(obj['id']), 'category': name,
                                       'lon': position['lon'], 'lat': position['lat'], 'tags': obj.get('tags', {})})
            except (RuntimeError, ValueError, requests.RequestException, KeyError) as exc:
                errors.append({'source': 'activity', 'id': name, 'error': str(exc)})
        activity_valid = not any(e['source'] == 'activity' for e in errors)
        atomic_json(work / 'data/interim/sampling/activity_features.json',
                    {'complete': activity_valid, 'snapshot_utc': prepared['snapshot_utc'], 'endpoint': prepared['endpoint'],
                     'features': activities, 'source_hashes': {t['name']: file_hash(folder / ('activity_' + t['name'] + '.json'))
                                                            for t in prepared['activity_queries'] if (folder / ('activity_' + t['name'] + '.json')).exists()},
                     'coverage': 'configured tile envelope; filter to study polygons after download',
                     'limitation': 'Mapped OSM features are activity proxies, not a census of establishments or revenue.'})
        api = 'https://api.worldpop.org/v2'
        for index, task in enumerate(prepared['population_tasks']):
            identity = digest({'url': api, 'body': task['body']})
            raw = folder / ('population_' + task['task_key'] + '.json')
            meta = raw.with_suffix('.manifest.json')
            payload = _cached_response(raw, meta, identity)
            try:
                if payload is None:
                    submit_path = raw.with_suffix('.submitted.json')
                    try:
                        submitted = json.loads(submit_path.read_text())
                        if submitted['identity'] != identity:
                            submitted = None
                    except (OSError, KeyError, ValueError):
                        submitted = None
                    if submitted is None:
                        if progress: progress(f'WorldPop {index+1}/{len(prepared["population_tasks"])}: {task["name"]}')
                        response = request(session, 'POST', api + '/population', json=task['body'])
                        submitted = {'identity': identity, 'task_id': response.json()['task_id'], 'submitted_at': now()}
                        atomic_json(submit_path, submitted)
                    for poll in range(30):
                        response = request(session, 'GET', api + '/tasks/' + str(submitted['task_id']))
                        payload = response.json()
                        if payload['status'] in {'success', 'failure'}:
                            break
                        time.sleep(2)
                    if payload.get('status') != 'success':
                        if payload.get('status') == 'failure':
                            submit_path.unlink(missing_ok=True)
                        raise ValueError('WorldPop did not finish successfully: ' + str(payload.get('error') or payload.get('status')))
                    result = payload['result']
                    if result['data_year'] != task['body']['year'] or not math.isfinite(result['total_population']) or result['total_population'] < 0:
                        raise ValueError('Invalid population value/year')
                    atomic_bytes(raw, response.content)
                    atomic_json(meta, {'identity': identity, 'sha256': file_hash(raw), 'downloaded_at': now(),
                                       'url': api, 'body': task['body'], 'source': result['data_source']})
                    report['new_population_parts'] += 1
                    time.sleep(0.5)
                else:
                    report['population_cache_parts'] += 1
                if payload.get('status') != 'success' or payload['result']['data_year'] != task['body']['year']:
                    raise ValueError('Invalid population cache')
                population.append({'admin_id': task['admin_id'], 'task_key': task['task_key'],
                                   'population': payload['result']['total_population'], 'year': payload['result']['data_year'],
                                   'source': payload['result']['data_source'], 'area_m2': task['area_m2'],
                                   'response_sha256': file_hash(raw)})
            except (RuntimeError, ValueError, requests.RequestException, KeyError) as exc:
                # A known expired server task can be resubmitted in a later run.
                # Do not resubmit pending/unknown tasks, which could duplicate server work.
                if isinstance(exc,requests.HTTPError) and exc.response is not None and exc.response.status_code in {404,410}:
                    raw.with_suffix('.submitted.json').unlink(missing_ok=True)
                errors.append({'source': 'population', 'id': task['task_key'], 'error': str(exc)})
        atomic_json(work / 'data/interim/sampling/population_admin.json',
                    {'complete': len(population) == len(prepared['population_tasks']), 'year': 2025,
                     'api': api, 'parts': population, 'expected_tasks': prepared['population_tasks'],
                     'status': 'modeled_2025_population_not_official_counts_or_2030_prediction',
                     'geometry_simplification_m': prepared['population_geometry_simplification_m']})
    finally:
        session.close()
        report.update(finished_at=now(), errors=errors)
        atomic_json(work / 'reports/sampling/input_downloads.json', report)
    return report
