"""Portable directed graph with explicit turn-aware successor checks."""
from __future__ import annotations

import gzip
import json
from collections import defaultdict


def export_graph(db, path, snapshot):
    arcs = [dict(r) for r in db.execute("SELECT arc_id,part_id,segment_id,from_node,to_node,direction,length_m,rc FROM arcs WHERE routable=1 ORDER BY arc_id")]
    used = {a[k] for a in arcs for k in ("from_node", "to_node")}
    nodes = [dict(r) for r in db.execute("SELECT node_id,x,y,lon,lat,artificial FROM nodes ORDER BY node_id") if r["node_id"] in used]
    arc_ids = {a["arc_id"] for a in arcs}
    turns = [dict(r) for r in db.execute("SELECT * FROM turn_rules ORDER BY restriction_id,from_arc,to_arc") if r["from_arc"] in arc_ids]
    parent = {n: n for n in used}
    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    for a in arcs:
        x, y = find(a["from_node"]), find(a["to_node"])
        if x != y:
            parent[y] = x
    components = defaultdict(int)
    for n in used:
        components[find(n)] += 1
    graph = {"schema_version": 1, "snapshot_utc": snapshot, "status": "provisional_not_field_verified",
             "nodes": nodes, "arcs": arcs, "turn_rules": turns,
             "must_use_turn_aware_successors": True}
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(graph, stream, ensure_ascii=False, separators=(",", ":"))
    return {"nodes": len(nodes), "arcs": len(arcs), "turn_rules": len(turns),
            "weak_components": len(components), "largest_weak_component_nodes": max(components.values(), default=0)}


class MotorcycleNetwork:
    def __init__(self, data):
        self.data = data
        self.arcs = {a["arc_id"]: a for a in data["arcs"]}
        self.outgoing = defaultdict(list)
        for arc in self.arcs.values():
            self.outgoing[arc["from_node"]].append(arc)
        self.no = set()
        self.only = defaultdict(list)
        # Multiple only-restrictions on the same incoming arc are conjunctive.
        groups = defaultdict(set)
        for t in data["turn_rules"]:
            if t["kind"] == "no":
                self.no.add((t["from_arc"], t["to_arc"]))
            else:
                groups[t["from_arc"], t["restriction_id"]].add(t["to_arc"])
        for (from_arc, _), allowed in groups.items():
            self.only[from_arc].append(allowed)

    @classmethod
    def load(cls, path):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return cls(json.load(stream))

    def successors(self, node_id, incoming_arc=None):
        for arc in self.outgoing.get(node_id, []):
            target = arc["arc_id"]
            if incoming_arc is not None and ((incoming_arc, target) in self.no or any(target not in allowed for allowed in self.only.get(incoming_arc, []))):
                continue
            yield arc

    def validate_walk(self, arc_ids):
        previous = None
        for arc_id in arc_ids:
            if arc_id not in self.arcs:
                return False, "Arc is absent from the provisional routing graph: " + arc_id
            arc = self.arcs[arc_id]
            if previous is not None:
                if previous["to_node"] != arc["from_node"]:
                    return False, "Disconnected directed arcs"
                if arc_id not in {a["arc_id"] for a in self.successors(arc["from_node"], previous["arc_id"])}:
                    return False, "Turn restriction violated"
            previous = arc
        return True, None
