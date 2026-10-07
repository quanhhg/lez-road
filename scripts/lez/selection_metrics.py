"""Pre-survey criteria from immutable route walks, OSM tags and RC-only lengths."""
from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .common import input_path

RC = ('RC1', 'RC2', 'RC3', 'RC4')
FEATURES = ['P_RC1', 'P_RC2', 'P_RC3', 'P_RC4', 'lanes', 'maxspeed',
            'junctions_per_km', 'signals_per_km', 'P_oneway']


def rows(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def number(value, speed=False):
    """Only unambiguous positive numeric OSM values; absence never becomes zero."""
    text = str(value or '').strip().lower()
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(km/h|kmh|kph|mph)?', text)
    if not match:
        return None
    result = float(match[1])
    if match[2] == 'mph':
        if not speed:
            return None
        result *= 1.609344
    if not speed and match[2]:
        return None
    if not speed and not result.is_integer():
        return None
    return result if result > 0 else None


def D(vector, network):
    denominator = float(np.sum(vector))
    return float(0.5 * np.abs(vector / denominator - network).sum()) if denominator else None


def load_data(work, report, options):
    work = Path(work)
    directory = input_path(work, report['paths']['directory'])
    walks = sorted(json.loads((directory / 'candidate_walks.json').read_text()), key=lambda r: r['route_id'])
    matrix = rows(directory / 'network_matrix.csv')
    expected_cells = len(options['required_strata']) * len(RC)
    if len(matrix) != expected_cells or any(r['rc'] not in RC for r in matrix):
        raise ValueError('Expected every configured spatial stratum × RC1–RC4 cell')
    cells = sorted((r['stratum_id'], r['rc']) for r in matrix)
    required_cells={(s,rc) for s in options['required_strata'] for rc in RC}
    if len(set(cells))!=len(cells) or set(cells)!=required_cells:
        raise ValueError('RC matrix cells must be unique and match every configured stratum × RC')
    index = {v: i for i, v in enumerate(cells)}
    lengths = np.array([float(next(r['network_length_m'] for r in matrix
                                   if (r['stratum_id'], r['rc']) == c)) for c in cells])
    if not np.all(np.isfinite(lengths)) or np.any(lengths < 0) or lengths.sum() <= 0:
        raise ValueError('Invalid RC-only network denominator')
    q = lengths / lengths.sum()
    sampling = json.loads(input_path(work, options.get('sampling_config', 'config/sampling_2030.json')).read_text())
    from .graph import MotorcycleNetwork
    graph = MotorcycleNetwork.load(input_path(work,sampling['graph_path']))
    if graph.data.get('snapshot_utc') != sampling['source_snapshot_utc']:
        raise ValueError('Route graph snapshot differs from configured OSM snapshot')
    for route in walks:
        valid, reason = graph.validate_walk(route['arc_ids'])
        if not valid:
            raise ValueError('Mandatory G2 failed for '+route['route_id']+': '+str(reason))
        if [graph.arcs[a]['part_id'] for a in route['arc_ids']] != route['part_ids']:
            raise ValueError('Ordered physical part IDs do not match source arcs')
    network = input_path(work, sampling['network_path'])
    db = sqlite3.connect('file:' + str(network) + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    wanted = sorted({p for r in walks for p in r['part_ids']})
    parts = {}
    for start in range(0, len(wanted), 500):
        chunk = wanted[start:start + 500]
        statement = ('SELECT p.part_id,p.length_m,p.from_node,p.to_node,s.tags_json,s.way_id '
                     'FROM scope_parts p JOIN segments s ON s.segment_id=p.segment_id '
                     'WHERE p.part_id IN (' + ','.join('?' * len(chunk)) + ')')
        for row in db.execute(statement, chunk):
            parts[row['part_id']] = dict(row)
    if len(parts) != len(wanted):
        raise ValueError('Route physical parts missing from source network')
    allowed_directions = {r[0]: r[1] for r in db.execute(
        'SELECT part_id,COUNT(DISTINCT direction) FROM arcs WHERE routable=1 GROUP BY part_id') if r[0] in parts}
    wanted_arcs={a for r in walks for a in r['arc_ids']}
    arc_access={r[0]:r[1] for r in db.execute('SELECT arc_id,access_status FROM arcs WHERE routable=1') if r[0] in wanted_arcs}
    if set(arc_access)!=wanted_arcs or any(v!='provisionally_allowed' for v in arc_access.values()):
        raise ValueError('Mandatory pre-survey G1_OSM failed: absent/non-routable/unresolved access arcs')
    normalized = sqlite3.connect('file:' + str(directory / 'network_parts.gpkg') + '?mode=ro', uri=True)
    table = normalized.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'").fetchone()[0]
    part_cells = defaultdict(list)
    part_domain_cells = defaultdict(list)
    columns = {row[1] for row in normalized.execute('PRAGMA table_info(' + table + ')')}
    group_column = ',group' if 'group' in columns else ''
    quoted_group = ',"group"' if 'group' in columns else ''
    for record in normalized.execute('SELECT part_id,stratum_id,rc,length_m' + quoted_group + ' FROM ' + table):
        pid, stratum, rc, length = record[:4]
        if pid in parts and rc in RC:
            cell = index[stratum, rc]
            part_cells[pid].append((cell, float(length)))
            group = record[4] if group_column else ('inside' if stratum.startswith('V') else 'outside')
            if group not in ('inside', 'outside'):
                raise ValueError('Overlay group must explicitly be inside or outside')
            part_domain_cells[pid].append((group, cell, float(length)))
    normalized.close()
    junctions = set()
    degree_sql = ('SELECT node,COUNT(*) AS degree FROM (SELECT DISTINCT node,neighbor FROM ('
                  'SELECT from_node AS node,to_node AS neighbor FROM arcs WHERE routable=1 '
                  'UNION SELECT to_node AS node,from_node AS neighbor FROM arcs WHERE routable=1)) '
                  'WHERE node<>neighbor GROUP BY node HAVING COUNT(*)>=3')
    for row in db.execute(degree_sql):
        junctions.add(row[0])
    signals = {f"osm/{r[0]}" for r in db.execute("SELECT control_id FROM controls WHERE on_way=1 AND (control_type='traffic_signals' OR tags_json LIKE '%traffic_signals%')")}
    db.close()

    # Fit explicit estimates only for scoring. Raw observed means remain separate.
    medians={}
    rc_by_part={graph.arcs[a]['part_id']:graph.arcs[a]['rc'] for a in wanted_arcs}
    for attribute in ('lanes','maxspeed'):
        observed=defaultdict(list)
        for pid,part in parts.items():
            value=number(json.loads(part['tags_json']).get(attribute),speed=attribute=='maxspeed')
            if value is not None:
                observed[rc_by_part[pid]].append(value)
                observed['all'].append(value)
        for rc in (*RC,'connector','all'):
            sample_values=observed.get(rc) or observed.get('all',[])
            medians[attribute,rc]=float(np.median(sample_values)) if sample_values else None
        if medians[attribute,'all'] is None:
            raise ValueError('No observed '+attribute+' value exists to fit the declared scoring model')

    vectors = np.zeros((len(walks), len(cells)))
    domain_vectors = {g: np.zeros((len(walks), len(cells))) for g in ('inside', 'outside')}
    features = []
    part_sets = []
    for i, route in enumerate(walks):
        total = float(route['length_m'])
        node_ids, street_names = set(), []
        lane_sum = lane_length = speed_sum = speed_length = one = osm_one = 0.0
        lane_model_sum=speed_model_sum=0.0
        for pid,aid in zip(route['part_ids'],route['arc_ids']):
            part = parts[pid]
            length = float(part['length_m'])
            tags = json.loads(part['tags_json'])
            for cell, size in part_cells[pid]:
                vectors[i, cell] += size
            for group, rc_index, size in part_domain_cells[pid]:
                domain_vectors[group][i, rc_index] += size
            node_ids.update((part['from_node'], part['to_node']))
            name = tags.get('name') or tags.get('ref') or '(đường chưa có tên OSM)'
            if not street_names or street_names[-1] != name:
                street_names.append(name)
            lane = number(tags.get('lanes'))
            direction=graph.arcs[aid]['direction']
            speed = number(tags.get('maxspeed:'+direction,tags.get('maxspeed')), speed=True)
            if lane is not None:
                lane_sum += lane * length
                lane_length += length
            if speed is not None:
                speed_sum += speed * length
                speed_length += length
            rc=graph.arcs[aid]['rc']
            lane_model_sum+=(lane if lane is not None else medians['lanes',rc])*length
            speed_model_sum+=(speed if speed is not None else medians['maxspeed',rc])*length
            explicit = str(tags.get('oneway', '')).lower()
            if explicit in ('yes', '1', 'true', '-1', 'reverse') or (tags.get('junction') == 'roundabout' and explicit not in ('no', '0', 'false')):
                osm_one += length
            if allowed_directions.get(pid) == 1:
                one += length
        rc_total = float(vectors[i].sum())
        if not 0 < rc_total <= total + 0.02:
            raise ValueError('Invalid route RC/full length balance: ' + route['route_id'])
        rc_lengths = [float(vectors[i, [j for j,c in enumerate(cells) if c[1] == rc]].sum()) for rc in RC]
        proportions = [length/total for length in rc_lengths]
        feature = {k: route[k] for k in ('route_id', 'stratum_id', 'rc_target', 'group', 'length_m', 'target_cell_fraction', 'reference_inside_length_fraction')}
        feature['sampling_zone'] = route.get('sampling_zone', route['stratum_id'])
        feature['lez2027_group'] = route.get('lez2027_group', 'unknown')
        feature['lez2030_group'] = route['group']
        feature['policy_version'] = route.get('policy_version', 'LEZ2030_research_scope')
        feature['survey_date'] = route.get('survey_date') or ''
        feature['lez_status_at_survey'] = route.get('lez_status_at_survey') or ''
        feature['quota_bucket'] = quota_bucket(feature, options)
        feature.update(dict(zip(FEATURES[:4], proportions)))
        feature.update({'P_'+rc+'_conditional_RC':length/rc_total for rc,length in zip(RC,rc_lengths)})
        feature.update(rc_length_m=rc_total, connector_length_m=max(0.0, total - rc_total),
                       lanes=lane_sum / lane_length if lane_length else None,
                       maxspeed=speed_sum / speed_length if speed_length else None,
                       lanes_known_length_fraction=min(1.0,max(0.0,lane_length / total)),
                       maxspeed_known_length_fraction=min(1.0,max(0.0,speed_length / total)),
                       lanes_scoring_model=lane_model_sum/total,
                       maxspeed_scoring_model=speed_model_sum/total,
                       lanes_imputed_length_fraction=min(1.0,max(0.0,1-lane_length/total)),
                       maxspeed_imputed_length_fraction=min(1.0,max(0.0,1-speed_length/total)),
                       junctions_per_km=len(node_ids & junctions) / (total / 1000),
                       signals_per_km=len(node_ids & signals) / (total / 1000),
                       P_oneway=one / total, P_osm_oneway=osm_one / total, street_sequence=' → '.join(street_names),
                       C6=None, C6_status='unknown_until_survey',
                       G1='survey_required', G1_OSM='passed_no_identified_source_graph_access_conflict', G2='passed_on_source_graph',
                       G3='awaiting_QGIS_geometry_check', G4='survey_required',
                       G5='survey_required', G6='survey_required', status='candidate_for_pre_survey_selection')
        features.append(feature)
        part_sets.append(set(route['part_ids']))

    complete_only=options.get('feature_policy')=='seven_complete_features'
    active = [name for name in FEATURES if not complete_only or name not in ('lanes', 'maxspeed')]
    raw = np.array([[r[name+'_scoring_model'] if name in ('lanes','maxspeed') else r[name] for name in active] for r in features], dtype=float)
    raw_names=list(active)
    minimum, maximum = raw.min(axis=0), raw.max(axis=0)
    span = maximum - minimum
    varying = span > 1e-12
    active = [name for name, enabled in zip(active, varying) if enabled]
    X = (raw[:, varying] - minimum[varying]) / span[varying]
    bins = []
    thresholds = {}
    for j, name in enumerate(active):
        thresholds[name] = sorted(set(float(v) for v in np.quantile(X[:, j], [0.25, 0.5, 0.75])))
    for i in range(len(walks)):
        bins.append({(name, int(np.searchsorted(thresholds[name], X[i, j], side='right'))) for j, name in enumerate(active)})
    distances = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(axis=2))
    overlaps = np.eye(len(walks))
    corridors = np.eye(len(walks))
    ids = {r['route_id']: i for i, r in enumerate(walks)}
    seen_pairs=set()
    for row in rows(directory / 'route_overlap.csv'):
        keys = list(row)
        # Source headers are checked explicitly; no positional coordinate interpretation.
        first = row.get('left', row.get('route_a', row.get('route_i', row.get('route_id_i'))))
        second = row.get('right', row.get('route_b', row.get('route_j', row.get('route_id_j'))))
        if first is None or second is None:
            raise ValueError('Unknown overlap header: ' + ','.join(keys))
        a, b = ids[first], ids[second]
        pair=tuple(sorted((a,b)))
        if a==b or pair in seen_pairs:
            raise ValueError('Duplicate/self overlap pair')
        seen_pairs.add(pair)
        overlaps[a,b] = overlaps[b,a] = float(row['traversed_overlap_fraction'])
        corridors[a,b] = corridors[b,a] = float(row['unique_corridor_overlap_fraction'])
    if len(seen_pairs)!=len(walks)*(len(walks)-1)//2:
        raise ValueError('Incomplete pairwise overlap table; missing pairs cannot mean zero overlap')
    if any(not np.all(np.isfinite(v)) or np.any(v<0) or np.any(v>1+1e-8) for v in (overlaps,corridors)):
        raise ValueError('Overlap fractions must be finite and in [0,1]')
    masks = {g: np.array([c[0].startswith('V' if g == 'inside' else 'N') for c in cells]) for g in ('inside', 'outside')}
    domain_lengths = {}
    for group in ('inside', 'outside'):
        key = 'network_' + group + '_length_m'
        if all(key in row for row in matrix):
            domain_lengths[group] = np.array([float(next(row[key] for row in matrix if (row['stratum_id'], row['rc']) == cell)) for cell in cells])
        else:
            domain_lengths[group] = np.where(masks[group], lengths, 0.0)
        if np.any(~np.isfinite(domain_lengths[group])) or np.any(domain_lengths[group] < 0):
            raise ValueError('Invalid explicit LEZ-domain network denominator')
    if not np.allclose(sum(domain_lengths.values()), lengths, atol=.02, rtol=1e-10):
        raise ValueError('Inside/outside RC network denominators do not partition the ABC matrix')
    if not np.allclose(sum(domain_vectors.values()), vectors, atol=.02, rtol=1e-10):
        raise ValueError('Domain route vectors do not partition ABC route vectors')
    return {'walks': walks, 'features': features, 'cells': cells, 'network_lengths': lengths,
            'q': q, 'vectors': vectors, 'P': vectors / np.array([r['length_m'] for r in walks])[:, None],
            'X': X, 'feature_names': active, 'bins': bins, 'distances': distances,
            'overlaps': overlaps, 'corridors': corridors, 'part_sets': part_sets,
            'parts': parts, 'part_cells': part_cells, 'masks': masks,
            'domain_vectors': domain_vectors, 'domain_lengths': domain_lengths,
            'normalization': {'method': 'fixed_minmax_on_all_60_candidates',
                'raw_min': dict(zip(raw_names, minimum.tolist())),
                'raw_max': dict(zip(raw_names, maximum.tolist())),
                'active_features': active, 'excluded_incomplete': ['lanes', 'maxspeed'] if complete_only else [],
                'RC_X_denominator':'full_route_length_including_connectors; separate conditional_RC fractions sum to one',
                'quartile_thresholds_in_normalized_space': thresholds,
                'imputation': 'RC-conditioned median of observed unique candidate-network parts, global observed median fallback; only scoring model, raw NULL preserved',
                'model_medians':{a:{rc:medians[a,rc] for rc in (*RC,'connector','all')} for a in ('lanes','maxspeed')},
                'model_is_observation':False}}


def summary(data, selected, threshold=0.30):
    vector = data['vectors'][selected].sum(axis=0)
    values = {'D_combined': D(vector, data['q'])}
    values['D_by_domain'] = {}
    for group in ('inside', 'outside'):
        domain_vector, q = domain_arrays(data, selected, group)
        values['D_by_domain'][group] = D(domain_vector, q / q.sum()) if q.sum() else None
    available = [v for v in values['D_by_domain'].values() if v is not None]
    values['D_domain_mean'] = sum(available) / len(available) if available else None
    values['route_count'] = len(selected)
    values['inside'] = sum(data['features'][i]['group'] == 'inside' for i in selected)
    values['outside'] = sum(data['features'][i]['group'] == 'outside' for i in selected)
    values['sampling_zone_counts'] = dict(sorted(Counter(data['features'][i].get('sampling_zone', data['features'][i]['stratum_id']) for i in selected).items()))
    values['zone_group_counts'] = {z: {g: sum(data['features'][i].get('sampling_zone', data['features'][i]['stratum_id']) == z and data['features'][i]['group'] == g for i in selected) for g in ('inside', 'outside')} for z in values['sampling_zone_counts']}
    values['quota_bucket_counts'] = dict(sorted(Counter(data['features'][i].get('quota_bucket', data['features'][i]['group']) for i in selected).items()))
    values['traversed_length_m'] = sum(float(data['walks'][i]['length_m']) for i in selected)
    values['rc_traversed_length_m'] = float(vector.sum())
    values['represented_primary_strata'] = sorted({data['features'][i]['stratum_id'] for i in selected})
    values['material_cells'] = int(np.any(data['P'][selected] >= threshold, axis=0).sum())
    values['touched_rc_cells'] = int((vector > 0).sum())
    covered_parts = set().union(*(data['part_sets'][i] for i in selected))
    unique = np.zeros(len(data['cells']))
    for pid in covered_parts:
        for cell, length in data['part_cells'][pid]:
            unique[cell] += length
    values['unique_rc_length_m'] = float(unique.sum())
    values['unique_rc_coverage_fraction'] = float(unique.sum() / data['network_lengths'].sum())
    values['quantile_groups_covered'] = len(set().union(*(data['bins'][i] for i in selected)))
    values['max_traversed_overlap_fraction'] = max((float(data['overlaps'][i,j]) for k,i in enumerate(selected) for j in selected[k+1:]), default=0.0)
    values['max_unique_corridor_overlap_fraction'] = max((float(data['corridors'][i,j]) for k,i in enumerate(selected) for j in selected[k+1:]), default=0.0)
    return values


def quota_buckets(options):
    """Turn disjoint zone/group subquotas into exact mutually exclusive slots."""
    buckets = {}
    claimed = set()
    for item in options.get('intersection_quota', []):
        group = item['group']
        zones = tuple(item['sampling_zones'])
        count = item['count']
        if group not in options['quota'] or not isinstance(count, int) or count < 0 or not zones:
            raise ValueError('Invalid zone × LEZ quota')
        keys = {(group, zone) for zone in zones}
        if keys & claimed or item['name'] in buckets:
            raise ValueError('Intersection quotas must be disjoint and named uniquely')
        claimed.update(keys)
        buckets[item['name']] = {'group': group, 'zones': zones, 'count': count}
    for group, target in options['quota'].items():
        remaining = target - sum(b['count'] for b in buckets.values() if b['group'] == group)
        if remaining < 0:
            raise ValueError('Zone/group subquotas exceed total LEZ quota')
        buckets[group + '_remaining'] = {'group': group, 'zones': None, 'count': remaining}
    return buckets


def quota_bucket(feature, options):
    zone = feature.get('sampling_zone', feature['stratum_id'])
    for name, bucket in quota_buckets(options).items():
        if bucket['group'] == feature['group'] and bucket['zones'] is not None and zone in bucket['zones']:
            return name
    return feature['group'] + '_remaining'


def domain_arrays(data, selected, group):
    """Domain D uses explicit LEZ overlay; ABC labels never imply LEZ membership."""
    if 'domain_vectors' in data:
        return data['domain_vectors'][group][selected].sum(axis=0), data['domain_lengths'][group]
    vector = data['vectors'][selected].sum(axis=0)
    mask = data['masks'][group]
    return vector[mask], data['network_lengths'][mask]


def _strata_fit(missing, availability, slots):
    """Assign each missing primary stratum to a remaining quota slot."""
    if not missing:
        return True
    stratum = min(missing, key=lambda s: sum(slots[b] > 0 and s in available for b, available in availability.items()))
    for bucket in sorted(slots):
        if slots[bucket] > 0 and stratum in availability[bucket]:
            trial = dict(slots); trial[bucket] -= 1
            if _strata_fit(missing - {stratum}, availability, trial):
                return True
    return False


def feasible_add(data, selected, candidate, quota, required, options=None):
    options = options or {'quota': quota}
    allowed = data.get('eligible_indices')
    if allowed is not None and (candidate not in allowed or any(i not in allowed for i in selected)):
        return False
    trial = selected + [candidate]
    if len(set(trial)) != len(trial):
        return False
    buckets = quota_buckets(options)
    counts = Counter(quota_bucket(data['features'][i], options) for i in trial)
    slots = {name: bucket['count'] - counts[name] for name, bucket in buckets.items()}
    if any(size < 0 for size in slots.values()):
        return False
    remaining = defaultdict(list)
    for i, feature in enumerate(data['features']):
        if i not in trial and (allowed is None or i in allowed):
            remaining[quota_bucket(feature, options)].append(i)
    if any(len(remaining[name]) < size for name, size in slots.items()):
        return False
    seen = {data['features'][i]['stratum_id'] for i in trial}
    missing = set(required) - seen
    availability = {name: {data['features'][i]['stratum_id'] for i in remaining[name]} for name in slots}
    if not _strata_fit(missing, availability, slots):
        return False
    mandatory = options.get('required_material_cells', options.get('mandatory_cells', []))
    if mandatory:
        indices = [data['cells'].index(tuple(cell)) for cell in mandatory]
        material = np.any(data['P'][trial] >= options['minimum_cell_fraction'], axis=0)
        pending = [j for j in indices if not material[j]]
        possible = [i for name, size in slots.items() if size > 0 for i in remaining[name]]
        if pending and (not possible or not np.all(np.any(data['P'][possible][:, pending] >= options['minimum_cell_fraction'], axis=0))):
            return False
    return True


def criteria(data, selected, candidates, options):
    total = data['vectors'][selected].sum(axis=0)
    old_D = D(total, data['q'])
    distribution = total / total.sum()
    deficit = np.maximum(0, data['q'] - distribution)
    covered_bins = set().union(*(data['bins'][i] for i in selected))
    seen_strata = {data['features'][i]['stratum_id'] for i in selected}
    seen_primary = {(data['features'][i]['stratum_id'], data['features'][i]['rc_target']) for i in selected}
    material = np.any(data['P'][selected] >= options['minimum_cell_fraction'], axis=0)
    result = []
    for i in candidates:
        feature = data['features'][i]
        own_material = data['P'][i] >= options['minimum_cell_fraction']
        novelty = float((own_material & ~material).sum() / own_material.sum()) if own_material.any() else 0.0
        raw = {
            'C1': old_D - D(total + data['vectors'][i], data['q']),
            'C2': float(data['P'][i].dot(deficit)),
            'C3': len(data['bins'][i] - covered_bins) / len(data['bins'][i]) if data['bins'][i] else None,
            'C4': float(data['overlaps'][i,selected].max()),
            'C5': float(data['distances'][i,selected].min()),
            'C6': feature.get('C6'),
            'C7': 2.0 * (feature['stratum_id'] not in seen_strata)
                  + 2.0 * ((feature['stratum_id'], feature['rc_target']) not in seen_primary) + novelty,
        }
        result.append({'candidate_index': i, 'route_id': feature['route_id'], 'raw': raw})
    return normalize_scores(result, options)


def normalize_scores(result, options):
    bounds = {}
    for c in ('C1', 'C2', 'C3', 'C4', 'C5'):
        available = [r['raw'][c] for r in result if r['raw'][c] is not None]
        bounds[c] = [min(available), max(available)] if available else [None, None]
    effective = dict(options['weights'])
    missing_policy=options.get('C6_missing_policy','neutral_assumption_with_score_interval')
    if missing_policy=='unknown_weight_zero_renormalize_other_criteria':
        effective['C6'] = 0.0
    constant_policy=options.get('constant_criterion_policy','all_one_preserve_weights')
    if constant_policy=='drop_and_renormalize_weights':
        for c, (low, high) in bounds.items():
            if low is None or high - low <= options['tie_tolerance']:
                effective[c] = 0.0
    norm = sum(effective.values())
    effective = {c: float(w / norm) for c,w in effective.items()} if norm else {c: 0.0 for c in effective}
    for row in result:
        z = {}
        for c,value in row['raw'].items():
            if c == 'C6':
                # This is a declared scoring assumption, never a raw field observation.
                if value is not None and (not math.isfinite(float(value)) or not 0 <= float(value) <= 5):
                    raise ValueError('Observed C6 must be finite and in [0,5]')
                z[c] = (float(value) if value is not None else options.get('C6_neutral_assumption',2.5))/5 if effective[c] else None
            elif c == 'C7':
                z[c] = value / 5
            else:
                low, high = bounds[c]
                if low is None:
                    raise ValueError('Missing mandatory non-field criterion '+c)
                if high-low<=options['tie_tolerance']:
                    z[c]=1.0 if constant_policy=='all_one_preserve_weights' else None
                else:
                    z[c] = ((high - value) if c == 'C4' else (value - low)) / (high - low)
        row['normalized'] = z
        row['score'] = 100 * sum(effective[c] * (z[c] or 0.0) for c in effective)
        assumed=100*effective['C6']*(z['C6'] or 0.0)
        unknown = row['raw']['C6'] is None
        row['score_lower_unknown_C6']=row['score']-assumed if unknown else row['score']
        row['score_upper_unknown_C6']=row['score']-assumed+100*effective['C6'] if unknown else row['score']
        row['C6_score_is_assumption']=bool(effective['C6']) and unknown
    return result, {'min_max': bounds, 'effective_weights': effective,
                    'constant_rule':constant_policy,'C6':missing_policy,
                    'C6_observation':None,'C6_assumed_for_scoring_only':options.get('C6_neutral_assumption',2.5) if effective['C6'] else None,
                    'unknown_C6_interval_note':'Per-route field C6 may vary independently in [0,5]; uniform endpoints do not test ranking stability.'}


def greedy(data, options, seed):
    selected = list(seed)
    history = [{'round': 0, 'selected_before': [], 'selected_after': [data['walks'][i]['route_id'] for i in selected],
                'seed': [data['walks'][i]['route_id'] for i in selected], 'method': 'seed_pair_minimum_RC_only_D',
                'set_metrics': summary(data, selected, options['minimum_cell_fraction'])}]
    quota = options['quota']
    required = set(options['required_strata'])
    while len(selected) < sum(quota.values()):
        eligible, rejected = [], []
        for i in range(len(data['walks'])):
            if i in selected:
                continue
            reason = None
            if not feasible_add(data, selected, i, quota, required, options):
                reason = 'would_exceed_quota_or_prevent_required_strata_completion'
            elif data['corridors'][i,selected].max() >= options['max_corridor_overlap']:
                reason = 'physical_corridor_overlap_at_or_above_cap'
            if reason:
                rejected.append({'route_id':data['walks'][i]['route_id'],'reason':reason})
            else:
                eligible.append(i)
        if not eligible:
            raise ValueError('No feasible candidate; quota/strata cannot be completed')
        scored, normalization = criteria(data, selected, eligible, options)
        best_score = max(r['score'] for r in scored)
        tied = [r for r in scored if best_score - r['score'] <= options['tie_tolerance']]
        best = sorted(tied, key=lambda r: (-r['raw']['C1'], r['raw']['C4'], r['route_id']))[0]
        uncertainty_competitors=[r['route_id'] for r in scored if r['route_id']!=best['route_id']
                                 and r['score_upper_unknown_C6']>=best['score_lower_unknown_C6']]
        previous = [data['walks'][i]['route_id'] for i in selected]
        selected.append(best['candidate_index'])
        history.append({'round': len(selected), 'selected_before': previous,
                        'selected_after': [data['walks'][i]['route_id'] for i in selected],
                        'chosen': best['route_id'], 'candidates': scored, 'normalization': normalization,
                        'C6_interval_competitors':uncertainty_competitors,
                        'C6_can_change_ranking':bool(uncertainty_competitors),
                        'hard_rejected_candidates': rejected,
                        'set_metrics': summary(data, selected, options['minimum_cell_fraction'])})
    return selected, history


def select(data, options):
    allowed = data.get('eligible_indices', set(range(len(data['features']))))
    inside = [i for i,r in enumerate(data['features']) if r['group'] == 'inside' and i in allowed]
    outside = [i for i,r in enumerate(data['features']) if r['group'] == 'outside' and i in allowed]
    seeds = sorted([(D(data['vectors'][[i,j]].sum(axis=0), data['q']), data['walks'][i]['route_id'], data['walks'][j]['route_id'], i,j)
                    for i in inside for j in outside
                    if feasible_add(data, [i], j, options['quota'], set(options['required_strata']), options)])[:options['seed_count']]
    if not seeds:
        raise ValueError('No feasible inside/outside seed pair for configured joint quotas')
    runs = []
    for _,_,_,i,j in seeds:
        try:
            selected, history = greedy(data, options, [i,j])
        except ValueError:
            continue
        metrics = summary(data, selected, options['minimum_cell_fraction'])
        runs.append((metrics['D_combined'], metrics['D_domain_mean'], tuple(sorted(selected)), selected, history, metrics))
    if not runs:
        raise ValueError('Every finite seed run failed quota/strata/overlap completion')
    best = min(runs, key=lambda r: r[:3])
    selected, history = list(best[3]), best[4]
    swaps = []
    initial_groups = best[5]['quantile_groups_covered']
    for round_no in range(options['max_swap_rounds']):
        current = summary(data, selected, options['minimum_cell_fraction'])
        base = data['vectors'][selected].sum(axis=0)
        choices = []
        for old in selected:
            others = [i for i in selected if i != old]
            for new in range(len(data['walks'])):
                if new in selected or data['features'][new]['group'] != data['features'][old]['group']:
                    continue
                value = D(base - data['vectors'][old] + data['vectors'][new], data['q'])
                if value >= current['D_combined'] - options['swap_min_improvement']:
                    continue
                if not feasible_add(data, others, new, options['quota'], set(options['required_strata']), options):
                    continue
                if data['corridors'][new,others].max() >= options['max_corridor_overlap']:
                    continue
                trial = others + [new]
                bins = len(set().union(*(data['bins'][i] for i in trial)))
                material = int(np.any(data['P'][trial] >= options['minimum_cell_fraction'], axis=0).sum())
                if bins < initial_groups * options['minimum_quantile_diversity_retained'] or material < current['material_cells']:
                    continue
                domain_ok = True
                trial_vector = base - data['vectors'][old] + data['vectors'][new]
                for group in ('inside', 'outside'):
                    domain_vector, q = domain_arrays(data, trial, group)
                    domain_D = D(domain_vector, q / q.sum()) if q.sum() else None
                    baseline_D = best[5]['D_by_domain'][group]
                    if domain_D is not None and baseline_D is not None and domain_D > baseline_D + options['max_domain_D_worsening']:
                        domain_ok = False
                if not domain_ok:
                    continue
                choices.append((value, data['features'][new]['route_id'], data['features'][old]['route_id'], old, new))
        if not choices:
            break
        value, _, _, old, new = min(choices)
        position = selected.index(old)
        selected[position] = new
        swaps.append({'round': round_no + 1, 'removed': data['features'][old]['route_id'],
                      'added': data['features'][new]['route_id'], 'D_before': current['D_combined'],
                      'D_after': value, 'improvement': current['D_combined'] - value})
    return selected, history, swaps, [{'seed': r[4][0]['seed'], **r[5]} for r in runs]
