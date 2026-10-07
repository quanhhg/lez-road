"""Turn-aware A* through ordered anchors, with reproducible candidate selection."""
from __future__ import annotations

import hashlib
import heapq
import math
import random
from collections import Counter, defaultdict


def midrank(values):
    """Ties have the same percentile; a constant series receives 0.5."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return {ordered[0]: 0.5}
    positions = defaultdict(list)
    for index, value in enumerate(ordered):
        positions[value].append(index)
    return {value: sum(ids)/len(ids)/(len(ordered)-1) for value, ids in positions.items()}


def classify(population_percentile, activity_percentile, weights, reference, threshold=0.5):
    if population_percentile is None or activity_percentile is None:
        return reference, None, 'pending_evidence_reference_retained'
    score = weights['population_density']*population_percentile + weights['activity_density']*activity_percentile
    return ('inside' if score >= threshold else 'outside'), score, 'population_activity_score'


def corridor_overlap(left, right, lengths):
    common = sum(lengths[p] for p in set(left) & set(right))
    denominator = min(sum(lengths[p] for p in set(left)), sum(lengths[p] for p in set(right)))
    return common/denominator if denominator else 0.0


def anchor_path(network, coordinates, anchors, allowed, cost, max_states=250000):
    """State includes incoming arc and anchor progress, including at the anchors."""
    if len(anchors) < 2 or len(set(anchors)) != len(anchors):
        raise ValueError('At least two distinct ordered anchors required')
    def distance(left, right):
        return math.dist(coordinates[left], coordinates[right])
    def heuristic(node, step):
        return 0.8*(distance(node, anchors[step]) + sum(distance(anchors[i], anchors[i+1]) for i in range(step,len(anchors)-1))) if step < len(anchors) else 0.0
    start = (None, 1)
    queue = [(heuristic(anchors[0], 1), 0.0, 0, start)]
    best, previous, serial, expanded = {start:0.0}, {}, 0, 0
    while queue:
        _, total, _, state = heapq.heappop(queue)
        if total != best.get(state):
            continue
        incoming, step = state
        node = anchors[0] if incoming is None else network.arcs[incoming]['to_node']
        if step == len(anchors):
            result = []
            while state != start:
                result.append(state[0]); state = previous[state]
            return list(reversed(result)), expanded
        expanded += 1
        if expanded > max_states:
            return None, expanded
        for arc in network.successors(node, incoming):
            arc_id = arc['arc_id']
            if arc_id not in allowed:
                continue
            # Avoid a fabricated out-and-back along the same physical part.
            if incoming is not None and network.arcs[incoming]['part_id'] == arc['part_id']:
                continue
            next_step = step + (arc['to_node'] == anchors[step])
            next_state = (arc_id, next_step)
            value = total + cost(arc)
            if value < best.get(next_state, math.inf):
                best[next_state], previous[next_state] = value, state
                serial += 1
                heapq.heappush(queue,(value+heuristic(arc['to_node'],next_step),value,serial,next_state))
    return None, expanded


def generate(network, part_meta, coordinates, targets, design, progress=None):
    allowed = defaultdict(set)
    nodes = defaultdict(set)
    lengths = {}
    for arc in network.arcs.values():
        part = part_meta.get(arc['part_id'])
        if not part or not part.get('pure_group'):
            continue
        group = part['pure_group']
        zone = part.get('pure_zone')
        if 'pure_zone' in part and not zone:
            continue
        key = (group, zone) if zone else group
        allowed[key].add(arc['arc_id'])
        lengths[arc['part_id']] = arc['length_m']
        for stratum, rc, length in part['cells']:
            if rc and length > 0:
                nodes[(group,stratum,rc)].update([arc['from_node'],arc['to_node']])
    selected, failures, usage = [], [], Counter()
    for target in targets:
        route_id, stratum, rc = target['route_id'], target['stratum_id'], target['rc_target']
        group = target.get('group') or ('inside' if route_id.startswith('L') else 'outside')
        allowed_key = (group, target['sampling_zone']) if target.get('sampling_zone') else group
        pool = sorted(nodes[(group,stratum,rc)])
        rng = random.Random(int(hashlib.sha256(route_id.encode()).hexdigest()[:12],16))
        accepted = None
        reasons = Counter()
        for attempt in range(design['attempts_per_target']):
            if len(pool) < 3:
                reasons['not_enough_target_cell_anchor_nodes'] += 1; break
            origin = pool[rng.randrange(len(pool))]
            radius = design.get('anchor_radius_by_zone_m', {}).get(target.get('sampling_zone'), 3500 if group == 'inside' else 8000)
            local = [n for n in pool if design['minimum_anchor_separation_m'] <= math.dist(coordinates[n],coordinates[origin]) <= radius]
            if len(local) < 2:
                reasons['no_spread_anchors_in_target_cell'] += 1; continue
            b, c = rng.sample(local,2)
            if math.dist(coordinates[b],coordinates[c]) < design['minimum_anchor_separation_m']:
                continue
            anchors = [origin,b,c]
            def cost(arc):
                part = part_meta[arc['part_id']]
                fraction = sum(length for h,k,length in part['cells'] if h==stratum and k==rc)/arc['length_m']
                return arc['length_m']*(1.3-0.5*min(1,fraction)+min(3,usage[arc['part_id']])*1.2)
            walk, expanded = anchor_path(network,coordinates,anchors,allowed[allowed_key],cost,design['max_search_states'])
            if walk is None:
                reasons['disconnected_or_search_limit'] += 1; continue
            valid, reason = network.validate_walk(walk)
            if not valid:
                raise RuntimeError('Generated invalid walk: ' + str(reason))
            arcs = [network.arcs[a] for a in walk]
            length = sum(a['length_m'] for a in arcs)
            lower = design['urban_min_m'] if group=='inside' else design['outside_min_m']
            upper = design['urban_max_m'] if group=='inside' else design['outside_max_m']
            if not lower <= length <= upper:
                reasons['outside_provisional_length_range'] += 1; continue
            parts = [a['part_id'] for a in arcs]
            unique = sum(lengths[p] for p in set(parts))
            if unique/length < 0.8:
                reasons['excessive_internal_repetition'] += 1; continue
            cell_length = sum(l for a in arcs for h,k,l in part_meta[a['part_id']]['cells'] if h==stratum and k==rc)
            if cell_length/length < design['target_cell_min_fraction']:
                reasons['target_cell_fraction_below_threshold'] += 1; continue
            similarity = max((corridor_overlap(parts,other['part_ids'],lengths) for other in selected),default=0.0)
            if similarity >= design['max_corridor_similarity']:
                reasons['too_similar_to_selected_corridor'] += 1; continue
            reference_length = sum(part_meta[a['part_id']]['reference_inside_m'] for a in arcs)
            accepted = dict(target, group=group, anchors=anchors, arc_ids=walk,part_ids=parts,length_m=length,
                            target_cell_fraction=cell_length/length, unique_length_fraction=unique/length,
                            reference_inside_length_fraction=reference_length/length,max_corridor_overlap=similarity,
                            attempt=attempt+1,search_states=expanded,status='pending_field_and_legal_geometry_confirmation')
            break
        if accepted:
            selected.append(accepted);usage.update(set(accepted['part_ids']))
        else:
            failures.append(dict(target,reasons=dict(reasons)))
        if progress:
            progress(route_id,len(selected),bool(accepted),dict(reasons))
    pairs = []
    for route in selected:
        route['max_corridor_overlap']=0.0
        route['max_overlap_traversed_fraction']=0.0
    for i,left in enumerate(selected):
        for right in selected[i+1:]:
            fraction = corridor_overlap(left['part_ids'],right['part_ids'],lengths)
            common=sum(lengths[p] for p in set(left['part_ids']) & set(right['part_ids']))
            traversed=common/min(left['length_m'],right['length_m'])
            for route in [left,right]:
                route['max_corridor_overlap']=max(route['max_corridor_overlap'],fraction)
                route['max_overlap_traversed_fraction']=max(route['max_overlap_traversed_fraction'],traversed)
            if fraction >= design['overlap_review_fraction']:
                pairs.append({'left':left['route_id'],'right':right['route_id'],'unique_corridor_overlap':fraction,
                              'traversed_overlap':traversed,'common_length_m':common})
    return selected, failures, pairs
