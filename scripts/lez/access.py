"""Conservative, versioned motorcycle access decisions; no GIS dependency."""
from __future__ import annotations

MODES = ("motorcycle", "motor_vehicle", "vehicle", "access")
DENIED = {"no", "private", "agricultural", "forestry", "customers", "delivery", "destination", "permit"}
ALLOWED = {"yes", "designated", "permissive"}
DEFAULT_EXCLUDED = {"motorway", "motorway_link", "footway", "cycleway", "pedestrian", "steps",
                    "bridleway", "path", "construction", "proposed", "platform", "raceway", "corridor"}
ROAD_CLASSES = {"primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link",
                "residential", "unclassified", "service", "living_street"}
RC = {"primary": "RC1", "primary_link": "RC1", "secondary": "RC2", "secondary_link": "RC2",
      "tertiary": "RC3", "tertiary_link": "RC3", "residential": "RC4", "unclassified": "RC4"}


def access_value(tags, direction=None):
    for mode in MODES:
        directional = f"{mode}:{direction}" if direction else None
        if directional and directional in tags:
            return directional, str(tags[directional]).strip().lower()
        if mode in tags:
            return mode, str(tags[mode]).strip().lower()
    return None, None


def relevant_conditionals(tags):
    prefixes = (*MODES, "oneway", "oneway:motorcycle", "oneway:motor_vehicle", "oneway:vehicle")
    return sorted(k for k in tags if k.endswith(":conditional") and any(k == p + ":conditional" or k.startswith(p + ":") for p in prefixes))


def classify_way(tags, config=None):
    config = config or {}
    highway = tags.get("highway", "")
    key, value = access_value(tags)
    reasons, status = [], "provisionally_allowed"
    if highway in set(config.get("excluded_highways", DEFAULT_EXCLUDED)):
        status, reasons = "excluded", ["research_excluded_highway:" + highway]
    elif highway in {"trunk", "trunk_link"} or tags.get("motorroad") == "yes":
        status, reasons = "review_required", ["motorroad_or_trunk_requires_evidence"]
    elif highway not in set(config.get("provisional_highways", ROAD_CLASSES)):
        status, reasons = "review_required", ["unclassified_access_for_highway:" + highway]
    policy_status, policy_reasons = status, list(reasons)
    if value in {"no", "private"}:
        status, reasons = "excluded", [f"{key}={value}"]
    elif value in DENIED or value in {"discouraged", "use_sidepath"}:
        if status != "excluded":
            status, reasons = "review_required", [f"restricted_access:{key}={value}"]
    elif value is not None and value not in ALLOWED:
        if status != "excluded":
            status, reasons = "review_required", [f"unsupported_access:{key}={value}"]
    elif not reasons:
        reasons = [f"osm_{key}={value}" if key else "road_class_default_not_field_verified"]
    conditions = relevant_conditionals(tags)
    if conditions and status != "excluded":
        status = "review_required"
        reasons += ["unevaluated_conditional:" + ",".join(conditions)]
    if conditions and policy_status != "excluded":
        policy_status = "review_required"
        policy_reasons += ["unevaluated_conditional:" + ",".join(conditions)]
    if any(k.startswith("access:lanes") or k.startswith("motorcycle:lanes") or k.startswith("motor_vehicle:lanes") for k in tags):
        if status != "excluded":
            status = "review_required"
            reasons.append("lane_access_requires_review")
        if policy_status != "excluded":
            policy_status = "review_required"
            policy_reasons.append("lane_access_requires_review")
    return {"status": status, "reasons": reasons, "access_key": key, "access_value": value,
            "policy_status": policy_status, "policy_reasons": policy_reasons,
            "rc": RC.get(highway, "connector" if highway in {"service", "living_street"} else "other"),
            "verified": False}


def directions(tags):
    key = next((k for k in ("oneway:motorcycle", "oneway:motor_vehicle", "oneway:vehicle", "oneway") if k in tags), None)
    value = str(tags[key]).strip().lower() if key else ("yes" if tags.get("junction") == "roundabout" or tags.get("highway") in {"motorway", "motorway_link"} else "no")
    if value in {"yes", "1", "true"}:
        allowed = ["forward"]
    elif value == "-1":
        allowed = ["backward"]
    elif value in {"no", "0", "false"}:
        allowed = ["forward", "backward"]
    else:
        return [], ["unsupported_oneway:" + value]
    oneway_rank = {"oneway:motorcycle":0,"oneway:motor_vehicle":1,"oneway:vehicle":2,"oneway":2,None:2}[key]
    for direction in (d for d in ("forward", "backward") if d not in allowed):
        explicit = next((f"{mode}:{direction}" for mode in MODES if f"{mode}:{direction}" in tags), None)
        if explicit is None or str(tags[explicit]).strip().lower() not in ALLOWED:
            continue
        rank = MODES.index(explicit.split(":")[0])
        if rank < oneway_rank:
            allowed.append(direction)
        elif rank == oneway_rank:
            return [], ["conflicting_oneway_and_directional_access:" + explicit]
    return allowed, []


def directional_decision(tags, direction, base):
    result = dict(base, status=base["policy_status"], reasons=list(base["policy_reasons"]))
    key, value = access_value(tags, direction)
    if value in {"no", "private"}:
        result.update(status="excluded")
        result["reasons"].append(f"{key}={value}")
    elif value is not None and value not in ALLOWED:
        if result["status"] != "excluded":
            result.update(status="review_required")
            result["reasons"].append(f"directional_access_requires_review:{key}={value}")
    elif not result["reasons"]:
        result["reasons"] = [f"osm_{key}={value}" if key else "road_class_default_not_field_verified"]
    return result


def node_decision(tags):
    key, value = access_value(tags)
    if tags.get("locked") == "yes":
        return "review_required", "barrier_locked"
    if tags.get("locked:conditional"):
        return "review_required", "barrier_locked_conditional"
    if value in {"no", "private"}:
        return "excluded", f"node_{key}={value}"
    if relevant_conditionals(tags):
        return "review_required", "node_conditional_access"
    if value is not None and value not in ALLOWED:
        return "review_required", f"node_{key}={value}"
    if tags.get("barrier") and tags["barrier"] not in {"no", "entrance"} and value not in ALLOWED:
        return "review_required", "barrier_without_motorcycle_evidence:" + tags["barrier"]
    return "provisionally_allowed", "node_has_no_identified_block"


def restriction_spec(obj):
    tags = obj.get("tags", {})
    base = {"restriction_id": obj["id"], "tags": tags, "members": obj.get("members", [])}
    if tags.get("type") != "restriction":
        return dict(base, status="not_applicable", reason="not_a_restriction")
    exceptions = {s.strip() for s in tags.get("except", "").split(";")}
    if exceptions & {"motorcycle", "motor_vehicle", "vehicle"}:
        return dict(base, status="not_applicable", reason="motorcycle_excepted")
    if any(k.startswith("restriction") and k.endswith(":conditional") for k in tags) or any(k in tags for k in ("day_on", "day_off", "hour_on", "hour_off")):
        return dict(base, status="review_required", reason="conditional_turn_not_evaluated")
    value = next((tags[k] for k in ("restriction:motorcycle", "restriction:motor_vehicle", "restriction:vehicle", "restriction") if k in tags), None)
    if value is None:
        return dict(base, status="not_applicable", reason="restriction_for_other_mode")
    froms = [m["ref"] for m in base["members"] if m.get("role") == "from" and m["type"] == "way"]
    tos = [m["ref"] for m in base["members"] if m.get("role") == "to" and m["type"] == "way"]
    via = [m for m in base["members"] if m.get("role") == "via"]
    result = dict(base, value=value, from_ways=froms, to_ways=tos, via=via)
    supported = {"no_left_turn", "no_right_turn", "no_straight_on", "no_u_turn", "no_entry", "no_exit",
                 "only_left_turn", "only_right_turn", "only_straight_on", "only_u_turn"}
    if not froms or not tos or not via or value not in supported:
        return dict(result, status="review_required", reason="unsupported_or_malformed_turn")
    if len(via) != 1 or via[0]["type"] != "node":
        return dict(result, status="review_required", reason="via_way_state_not_implemented")
    return dict(result, status="candidate", reason="via_node_restriction", via_node=via[0]["ref"])
