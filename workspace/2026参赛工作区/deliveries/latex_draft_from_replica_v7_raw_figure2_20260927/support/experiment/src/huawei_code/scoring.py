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
    """Count logical boundary COPY bytes without charging internal tensors twice.

    The input and produced-tensor branches are mutually exclusive.  For A, a
    produced tensor crossing Task boundaries is written once by its source and
    read once by each remote Task.  For B/C, the official construction emits a
    write/read pair for each remote core.  Spill and event timing are handled
    by the official evaluator and are deliberately outside this static score.
    """
    scene = scene.upper()
    if scene not in {"A", "B", "C"}:
        raise ValueError("scene must be A, B or C")
    mapping, core_of_node = _maps(view, plan)
    sizes = {int(k): int(v) for k, v in view["tensor_sizes"].items()}
    consumers = {int(k): [int(x) for x in v] for k, v in view["tensor_consumers"].items()}
    producers = {int(k): [int(x) for x in v] for k, v in view["tensor_producers"].items()}
    inputs = set(map(int, view.get("input_tensors", [])))
    outputs = set(map(int, view.get("output_tensors", [])))

    def domain(node: int) -> int:
        return mapping[node] if scene == "A" else core_of_node[node]

    total = 0
    for tid, users in consumers.items():
        size = sizes.get(tid, 0)
        owners = producers.get(tid, [])
        if not owners:
            # External inputs are charged once per receiving Task/core.
            total += size * len({domain(node) for node in users if node in mapping})
            continue
        owner = owners[0]
        remote = {domain(node) for node in users if node in mapping and domain(node) != domain(owner)}
        if scene == "A":
            total += size * (len(remote) + int(bool(remote) or tid in outputs))
        else:
            total += size * (2 * len(remote) + int(tid in outputs))

    # Preserve output tensors with no listed consumers: the producer still
    # emits the final write required by the official construction.
    for tid in outputs - set(consumers):
        owners = producers.get(tid, [])
        if owners:
            total += sizes.get(tid, 0)
    return int(total)


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


def _logical_copy_queries(view: dict[str, Any], plan: dict[str, Any], scene: str):
    """Return one proxy read query per logical tensor and receiving domain.

    The proxy follows the static boundary rules used by ``structural_bytes``;
    it does not replay COPY completion, FIFO insertion, or eviction events.
    """
    scene = scene.upper()
    mapping, core_of_node = _maps(view, plan)
    sizes = {int(k): int(v) for k, v in view["tensor_sizes"].items()}
    consumers = {int(k): [int(x) for x in v] for k, v in view["tensor_consumers"].items()}
    producers = {int(k): [int(x) for x in v] for k, v in view["tensor_producers"].items()}
    schedules = {
        int(core): {int(group): pos for pos, group in enumerate(sequence)}
        for core, sequence in enumerate(plan["core_schedules"])
    }

    def domain(node: int) -> int:
        return mapping[node] if scene == "A" else core_of_node[node]

    for tid, users in consumers.items():
        size = sizes.get(tid, 0)
        if size <= 0:
            continue
        owners = producers.get(tid, [])
        owner_domain = domain(owners[0]) if owners else None
        receivers = {}
        for node in users:
            if node not in mapping:
                continue
            receiver = domain(node)
            if owner_domain is not None and receiver == owner_domain:
                continue
            # Keep the earliest consumer in each receiving domain as the
            # proxy query position; repeated consumers share one logical read.
            position = schedules[core_of_node[node]][mapping[node]] if scene != "A" else schedules[0].get(mapping[node], 0)
            receivers[receiver] = min(receivers.get(receiver, position), position)
        for receiver, position in sorted(receivers.items(), key=lambda item: (item[1], item[0])):
            yield tid, receiver, position, size


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
        # This is a static ordering proxy: one query per receiving core/domain.
        # It deliberately does not claim to predict the official FIFO state.
        queries = list(_logical_copy_queries(view, plan, scene))
        by_tensor = defaultdict(list)
        for tid, receiver, position, size in queries:
            by_tensor[tid].append((position, receiver, size))
        for entries in by_tensor.values():
            entries.sort(key=lambda item: (item[0], item[1]))
            size = entries[0][2]
            if len(entries) > 1 and size <= config["cache"]["capacity"]:
                hits = len(entries) - 1
                cache_hits += hits * size
                cache_work += hits * max(1, math.ceil(size / config["cache"]["bandwidth"]))
        light_time = max(light_time, cache_work)
    return {"scene": scene, "light_time": int(light_time), "copy_bytes": int(copy_bytes), "pressure_bytes": int(pressure), "cache_hit_bytes": int(cache_hits), "loads": dict(loads), "score": (int(light_time), int(copy_bytes), int(pressure))}
