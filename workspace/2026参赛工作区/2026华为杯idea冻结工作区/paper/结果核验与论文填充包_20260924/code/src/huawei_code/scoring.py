"""Independent light scoring used to rank fresh candidates before full eval."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any


def read_config(path):
    section = None
    values = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            section = line.strip("[]")
        else:
            key, value = line.split(maxsplit=1)
            values[(section, key)] = int(value)
    return {
        "bandwidth": values[("bandwidth", "bandwidth")],
        "capacity": {"L1": values[("capacity", "L1")], "UB": values[("capacity", "UB")]},
        "a_waits": {"cross": values[("multicore_scene_a", "task_cross_core_wait_cycles")], "same": values[("multicore_scene_a", "task_same_core_wait_cycles")]},
        "b_wait": values[("multicore_scene_b", "cross_core_copy_delay_cycles")],
        "cache": {"capacity": values[("problem_3", "cache_capacity_bytes")], "bandwidth": values[("problem_3", "cache_bandwidth_bytes_per_cycle")]},
    }


def _maps(view, plan):
    mapping = {int(node): int(group) for node, group in plan["node_to_subgraph"].items()}
    core_of = {int(group): core for core, seq in enumerate(plan["core_schedules"]) for group in seq}
    return mapping, {node: core_of[group] for node, group in mapping.items()}


def structural_bytes(view: dict[str, Any], plan: dict[str, Any], scene: str) -> int:
    mapping, core_of_node = _maps(view, plan)
    total = 0
    sizes = {int(k): int(v) for k, v in view["tensor_sizes"].items()}
    for tid, users in ((int(k), [int(x) for x in v]) for k, v in view["tensor_consumers"].items()):
        domains = {mapping[node] if scene == "A" else core_of_node[node] for node in users if node in mapping}
        total += sizes.get(tid, 0) * len(domains)
    producers = {int(k): [int(x) for x in v] for k, v in view["tensor_producers"].items()}
    outputs = set(map(int, view["output_tensors"]))
    for tid, owners in producers.items():
        domains = {mapping[node] if scene == "A" else core_of_node[node] for node in view["tensor_consumers"].get(str(tid), []) if int(node) in mapping and (mapping[int(node)] if scene == "A" else core_of_node[int(node)]) != (mapping[owners[0]] if scene == "A" else core_of_node[owners[0]])}
        total += sizes.get(tid, 0) * (len(domains) + (1 if domains or tid in outputs else 0))
    return total


def capacity_pressure(view: dict[str, Any], plan: dict[str, Any], scene: str, config: dict[str, Any]) -> int:
    mapping, core_of_node = _maps(view, plan)
    groups = defaultdict(list)
    for node, group in mapping.items():
        groups[group].append(node)
    sizes = {int(k): int(v) for k, v in view["tensor_sizes"].items()}
    consumers = {int(k): [int(x) for x in v] for k, v in view["tensor_consumers"].items()}
    producers = {int(k): [int(x) for x in v] for k, v in view["tensor_producers"].items()}
    positions = {int(k): str(v) for k, v in view.get("tensor_pos", {}).items()}
    pressure = 0
    for core in range(len(plan["core_schedules"])):
        seq = [g for g in plan["core_schedules"][core]]
        order = {node: i for i, g in enumerate(seq) for node in groups[int(g)]}
        events = {"L1": defaultdict(int), "UB": defaultdict(int)}
        # One interval per tensor/core is enough for the proxy.  The event
        # sweep removes the previous O(operations * tensors) scan on large
        # graphs; official Step2 remains authoritative for actual spilling.
        for tid, users in consumers.items():
            local_users = [u for u in users if u in order]
            local_owners = [o for o in producers.get(tid, []) if o in order]
            if not local_users and not local_owners:
                continue
            start = min([order[o] for o in local_owners] + [order[u] for u in local_users])
            end = max([order[u] for u in local_users] + [order[o] for o in local_owners])
            pos = positions.get(tid, "UB")
            if pos not in events:
                pos = "UB"
            size = sizes.get(tid, 0)
            events[pos][start] += size
            events[pos][end + 1] -= size
        for pos, changes in events.items():
            live = peak = 0
            for index in sorted(changes):
                live += changes[index]
                peak = max(peak, live)
            pressure += max(0, peak - int(config["capacity"].get(pos, 0)))
    return pressure


def groups_for_core(groups, seq, core):
    for group in seq:
        yield from groups[int(group)]


def light_score(view: dict[str, Any], plan: dict[str, Any], scene: str, config: dict[str, Any]) -> dict[str, Any]:
    mapping, core_of_node = _maps(view, plan)
    finish = {}
    loads = defaultdict(int)
    preds = {int(k): set(map(int, v)) for k, v in view["preds"].items()}
    for node, group in mapping.items():
        loads[core_of_node[node]] += max(1, int(view["ops"][str(node)].get("cycles", 0)))
    # A deterministic path proxy with the official wait constants.
    order = [int(n) for n in view["topological"]]
    for node in order:
        best = 0
        for parent in preds[node]:
            wait = config["a_waits"]["cross"] if scene == "A" and mapping[parent] != mapping[node] else 0
            if scene != "A" and core_of_node[parent] != core_of_node[node]:
                wait = config["b_wait"]
            best = max(best, finish[parent] + wait)
        finish[node] = best + max(1, int(view["ops"][str(node)].get("cycles", 0)))
    path = max(finish.values(), default=0)
    copy_bytes = structural_bytes(view, plan, scene)
    ddr_work = math.ceil(copy_bytes / config["bandwidth"]) if copy_bytes else 0
    pressure = capacity_pressure(view, plan, scene, config)
    light_time = max(path, max(loads.values(), default=0), ddr_work)
    cache_work = 0
    cache_hits = 0
    if scene == "C":
        # Query order is the core schedule order.  A second consumer can only
        # be a light hit after the first query's reference read completes.
        for tid, users in ((int(k), [int(x) for x in v]) for k, v in view["tensor_consumers"].items()):
            size = int(view["tensor_sizes"].get(str(tid), 0))
            if size <= 0:
                continue
            query = sorted((core_of_node[u], u) for u in users if u in core_of_node)
            if len(query) > 1 and size <= config["cache"]["capacity"]:
                hits = len(query) - 1
                cache_hits += hits * size
                cache_work += hits * max(1, math.ceil(size / config["cache"]["bandwidth"]))
        light_time = max(light_time, cache_work)
    return {"scene": scene, "light_time": int(light_time), "copy_bytes": int(copy_bytes), "pressure_bytes": int(pressure), "cache_hit_bytes": int(cache_hits), "loads": dict(loads), "score": (int(light_time), int(copy_bytes), int(pressure))}
