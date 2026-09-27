"""Independent light scoring used to rank fresh candidates before full eval."""

from __future__ import annotations

from collections import defaultdict, OrderedDict
import heapq
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


def structural_byte_breakdown(view: dict[str, Any], plan: dict[str, Any], scene: str) -> dict[str, int]:
    """Estimate logical boundary COPY bytes without counting local reads.

    A input is copied once per consumer subgraph.  For B/C each remote
    producer-core/consumer-core pair creates one COPY_OUT and one COPY_IN;
    final outputs add one write per producer core.  A uses the same domains
    but one source write serves all remote Tasks.  Cache hits do not change
    these logical COPY bytes; they only change the service pool.
    """
    scene = scene.upper()
    if scene not in {"A", "B", "C"}:
        raise ValueError("scene must be A, B, or C")
    mapping, core_of_node = _maps(view, plan)
    domain_of = mapping if scene == "A" else core_of_node
    sizes = {int(k): int(v) for k, v in view["tensor_sizes"].items()}
    consumers = {int(k): [int(x) for x in v] for k, v in view["tensor_consumers"].items()}
    producers = {int(k): [int(x) for x in v] for k, v in view["tensor_producers"].items()}
    outputs = set(map(int, view["output_tensors"]))
    input_bytes = cross_read_bytes = cross_write_bytes = output_write_bytes = 0
    for tid, users in consumers.items():
        size = sizes.get(tid, 0)
        if size <= 0:
            continue
        user_domains = {domain_of[node] for node in users if node in domain_of}
        owner_domains = {domain_of[node] for node in producers.get(tid, ()) if node in domain_of}
        if not owner_domains:
            input_bytes += size * len(user_domains)
            continue
        if scene == "A":
            remote_domains = user_domains - owner_domains
            cross_read_bytes += size * len(remote_domains)
            cross_write_bytes += size * len(owner_domains if remote_domains else ())
            if tid in outputs and not remote_domains:
                output_write_bytes += size * len(owner_domains)
        else:
            remote_pairs = {
                (owner_domain, user_domain)
                for owner_domain in owner_domains
                for user_domain in user_domains
                if owner_domain != user_domain
            }
            cross_read_bytes += size * len(remote_pairs)
            cross_write_bytes += size * len(remote_pairs)
            if tid in outputs:
                output_write_bytes += size * len(owner_domains)
    # A produced tensor can be an output without a compute consumer.  In that
    # case it does not appear in ``consumers`` and still needs a final write.
    for tid, owner_nodes in producers.items():
        if tid in consumers or tid not in outputs:
            continue
        owner_domains = {domain_of[node] for node in owner_nodes if node in domain_of}
        output_write_bytes += sizes.get(tid, 0) * len(owner_domains)
    return {
        "input_read_bytes": int(input_bytes),
        "cross_read_bytes": int(cross_read_bytes),
        "cross_write_bytes": int(cross_write_bytes),
        "output_write_bytes": int(output_write_bytes),
        "structural_copy_bytes": int(input_bytes + cross_read_bytes + cross_write_bytes + output_write_bytes),
    }


def structural_bytes(view: dict[str, Any], plan: dict[str, Any], scene: str) -> int:
    """Backward-compatible scalar form of :func:`structural_byte_breakdown`."""
    return structural_byte_breakdown(view, plan, scene)["structural_copy_bytes"]


def capacity_pressure(view: dict[str, Any], plan: dict[str, Any], scene: str, config: dict[str, Any]) -> int:
    mapping, _core_of_node = _maps(view, plan)
    groups = defaultdict(list)
    for node, group in mapping.items():
        groups[group].append(node)
    sizes = {int(k): int(v) for k, v in view["tensor_sizes"].items()}
    consumers = {int(k): [int(x) for x in v] for k, v in view["tensor_consumers"].items()}
    producers = {int(k): [int(x) for x in v] for k, v in view["tensor_producers"].items()}
    positions = {int(k): str(v) for k, v in view.get("tensor_pos", {}).items()}
    capacity_cfg = config.get("capacity", {})
    topo_rank = {int(node): index for index, node in enumerate(view["topological"])}
    pressure = 0
    for core in range(len(plan["core_schedules"])):
        # Preserve group priority and place each group's operations in a local
        # topological order.  Step1 may choose another order within a group;
        # the official Spill pass decides actual capacity behavior.
        sequence = [
            node
            for group in plan["core_schedules"][core]
            for node in sorted(groups[int(group)], key=lambda item: (topo_rank[item], item))
        ]
        order = {node: index for index, node in enumerate(sequence)}
        events = {"L1": defaultdict(int), "UB": defaultdict(int)}
        for tid in consumers.keys() | producers.keys():
            users = consumers.get(tid, ())
            local_users = [u for u in users if u in order]
            local_owners = [o for o in producers.get(tid, ()) if o in order]
            if not local_users and not local_owners:
                continue
            start = min([order[o] for o in local_owners] + [order[u] for u in local_users])
            end = max([order[u] for u in local_users] + [order[o] for o in local_owners])
            pos = positions.get(tid, "UB")
            if pos not in events:
                pos = "UB"
            size = sizes.get(tid, 0)
            if size <= 0:
                continue
            # Inclusive end keeps an input resident while an output is
            # allocated by the same operation, as in official Step2.
            events[pos][start] += size
            events[pos][end + 1] -= size
        for pos, changes in events.items():
            live = peak = 0
            for index in sorted(changes):
                live += changes[index]
                peak = max(peak, live)
            pressure += max(0, peak - int(capacity_cfg.get(pos, 0)))
    return pressure


def groups_for_core(groups, seq, core):
    for group in seq:
        yield from groups[int(group)]


def _group_layout(view: dict[str, Any], plan: dict[str, Any], scene: str, config: dict[str, Any]):
    """Build a deterministic node-time skeleton for cache candidate ranking.

    The skeleton is intentionally cheaper than the official evaluator.  It
    preserves contracted dependencies, per-core order, and the problem's
    cross-core delay so cache queries are ranked by their relative timing.
    """
    scene = scene.upper()
    mapping = {int(node): int(group) for node, group in plan["node_to_subgraph"].items()}
    schedules = [[int(group) for group in seq] for seq in plan["core_schedules"]]
    group_nodes = defaultdict(list)
    for node, group in mapping.items():
        group_nodes[group].append(node)
    core_of = {group: core for core, seq in enumerate(schedules) for group in seq}
    group_preds = {group: set() for group in group_nodes}
    group_succs = {group: set() for group in group_nodes}
    preds = {int(k): set(map(int, v)) for k, v in view["preds"].items()}
    for node, parents in preds.items():
        if node not in mapping:
            continue
        for parent in parents:
            if parent not in mapping:
                continue
            gp, gn = mapping[parent], mapping[node]
            if gp != gn:
                group_preds[gn].add(gp)
                group_succs[gp].add(gn)
    for seq in schedules:
        for left, right in zip(seq, seq[1:]):
            group_preds[right].add(left)
            group_succs[left].add(right)

    indegree = {group: len(parents) for group, parents in group_preds.items()}
    ready = [group for group, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    group_order = []
    while ready:
        group = heapq.heappop(ready)
        group_order.append(group)
        for child in sorted(group_succs[group]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(group_order) != len(group_nodes):
        raise ValueError("cache time skeleton has a contracted dependency cycle")

    ops = view["ops"]
    duration = {
        group: sum(max(1, int(ops[str(node)].get("cycles", 0))) for node in nodes)
        for group, nodes in group_nodes.items()
    }
    group_start, group_finish = {}, {}
    cross_wait = config["a_waits"]["cross"] if scene == "A" else config["b_wait"]
    for group in group_order:
        start = 0
        for parent in group_preds[group]:
            wait = cross_wait if core_of[parent] != core_of[group] else 0
            start = max(start, group_finish[parent] + wait)
        group_start[group] = start
        group_finish[group] = start + duration[group]

    topo_index = {node: index for index, node in enumerate(map(int, view["topological"]))}
    node_start, node_finish = {}, {}
    for group in group_order:
        cursor = group_start[group]
        for node in sorted(group_nodes[group], key=lambda item: (topo_index[item], item)):
            start = cursor
            for parent in preds[node]:
                if parent not in node_finish:
                    continue
                wait = cross_wait if core_of[mapping[parent]] != core_of[group] else 0
                start = max(start, node_finish[parent] + wait)
            finish = start + max(1, int(ops[str(node)].get("cycles", 0)))
            node_start[node], node_finish[node] = start, finish
            cursor = finish
    return mapping, core_of, group_nodes, node_start, node_finish


def fifo_cache_replay(view: dict[str, Any], plan: dict[str, Any], config: dict[str, Any], scene: str = "C") -> dict[str, Any]:
    """Replay query, completion, FIFO insertion and eviction events.

    A query observes the cache at its issue time.  COPY_IN queries use one
    MTE2 slot per core; a compute operation on another Pipe does not delay
    them.  At an equal timestamp completions retire before new queries.
    Shared DDR/Cache pool contention remains an official-evaluator concern.
    """
    scene = scene.upper()
    if scene != "C":
        return {"hit_bytes": 0, "miss_bytes": 0, "hit_count": 0, "miss_count": 0, "query_bytes": 0, "query_count": 0, "events": []}
    mapping, core_of, _groups, node_start, node_finish = _group_layout(view, plan, scene, config)
    sizes = {int(k): int(v) for k, v in view["tensor_sizes"].items()}
    consumers = {int(k): [int(x) for x in v] for k, v in view["tensor_consumers"].items()}
    producers = {int(k): [int(x) for x in v] for k, v in view["tensor_producers"].items()}
    capacity = int(config["cache"]["capacity"])
    ddr_bandwidth = int(config["bandwidth"])
    cache_bandwidth = int(config["cache"]["bandwidth"])
    group_position = {
        int(group): position
        for sequence in plan["core_schedules"]
        for position, group in enumerate(sequence)
    }
    queries_by_core = defaultdict(list)
    for tid, users in consumers.items():
        size = sizes.get(tid, 0)
        if size <= 0:
            continue
        owner_cores = {core_of[mapping[node]] for node in producers.get(tid, ()) if node in mapping}
        first_by_core = {}
        for node in users:
            if node not in mapping or node not in node_start:
                continue
            core = core_of[mapping[node]]
            candidate = (group_position[mapping[node]], node_start[node], node)
            if core not in first_by_core or candidate < first_by_core[core][0]:
                first_by_core[core] = (candidate, node)
        for core, ((position, _when, _node), node) in first_by_core.items():
            remote_owners = sorted(owner_cores - {core}) if owner_cores else [None]
            for owner_core in remote_owners:
                ready = 0
                if owner_core is not None:
                    last_producer = max(
                        node_finish[parent]
                        for parent in producers[tid]
                        if parent in mapping and core_of[mapping[parent]] == owner_core
                    )
                    ready = last_producer + math.ceil(size / ddr_bandwidth) + config["b_wait"]
                queries_by_core[core].append({
                    "ready": int(ready), "group_position": int(position),
                    "core": int(core), "node": int(node), "tensor_id": int(tid),
                    "size_bytes": int(size), "remote_core": owner_core,
                })
    for core, queries in queries_by_core.items():
        # COPY_IN shares one MTE2 Pipe per core.  A preceding compute op on
        # another Pipe does not by itself delay this query.
        queries.sort(key=lambda item: (item["group_position"], item["node"], item["tensor_id"], item["remote_core"] if item["remote_core"] is not None else -1))
        for position, event in enumerate(queries):
            event["core_position"] = position
    event_queue = []
    serial = 0
    for core in sorted(queries_by_core):
        first = queries_by_core[core][0]
        heapq.heappush(event_queue, (first["ready"], 1, serial, "query", first))
        serial += 1
    heapq.heapify(event_queue)
    cache_entries = OrderedDict()
    used = 0
    hit_bytes = miss_bytes = hit_count = miss_count = 0
    replay_events = []
    while event_queue:
        now, _event_kind, index, kind, event = heapq.heappop(event_queue)
        if kind == "query":
            tid = event["tensor_id"]
            size = event["size_bytes"]
            hit = size <= capacity and tid in cache_entries
            if hit:
                hit_count += 1
                hit_bytes += size
                bandwidth = cache_bandwidth
            else:
                miss_count += 1
                miss_bytes += size
                bandwidth = ddr_bandwidth
            duration = max(1, (size + bandwidth - 1) // bandwidth)
            finish = now + duration
            replay_events.append({**event, "time": int(now), "event": "hit" if hit else "miss", "finish": finish})
            heapq.heappush(event_queue, (finish, 0, index, "complete", {**event, "hit": hit}))
            continue
        tid = event["tensor_id"]
        size = event["size_bytes"]
        if size <= capacity and tid not in cache_entries:
            evicted = []
            while cache_entries and used + size > capacity:
                old_tid, old_size = cache_entries.popitem(last=False)
                used -= old_size
                evicted.append(old_tid)
            cache_entries[tid] = size
            used += size
            replay_events.append({"time": int(now), "event": "insert", "tensor_id": int(tid), "size_bytes": int(size), "evicted": evicted})
        next_position = event["core_position"] + 1
        core_queries = queries_by_core[event["core"]]
        if next_position < len(core_queries):
            following = core_queries[next_position]
            heapq.heappush(event_queue, (max(now, following["ready"]), 1, serial, "query", following))
            serial += 1
    return {
        "hit_bytes": int(hit_bytes),
        "miss_bytes": int(miss_bytes),
        "hit_count": int(hit_count),
        "miss_count": int(miss_count),
        "query_bytes": int(hit_bytes + miss_bytes),
        "query_count": int(hit_count + miss_count),
        "events": replay_events,
    }


def same_core_reuse_potential(view: dict[str, Any], plan: dict[str, Any], config: dict[str, Any]) -> int:
    """Estimate same-core repeated-read opportunities after a timing split.

    The official evaluator decides whether capacity pressure creates multiple
    Spill/Reload COPY_IN events.  This proxy only rewards plans that place the
    users of a cache-sized tensor in multiple same-core groups, which is the
    structural precondition hidden from the cross-core FIFO replay.
    """
    mapping, _core_of_node = _maps(view, plan)
    group_positions = {
        int(group): (core, position)
        for core, sequence in enumerate(plan["core_schedules"])
        for position, group in enumerate(sequence)
    }
    capacity = int(config["cache"]["capacity"])
    potential = 0
    for tid, users in view["tensor_consumers"].items():
        size = int(view["tensor_sizes"].get(str(tid), 0))
        if size <= 0 or size > capacity:
            continue
        by_core = defaultdict(set)
        for node in users:
            node = int(node)
            if node not in mapping:
                continue
            group = mapping[node]
            core, position = group_positions[group]
            by_core[core].add(position)
        for positions in by_core.values():
            if len(positions) < 2:
                continue
            gap = max(positions) - min(positions)
            potential += size * (len(positions) - 1) * max(1, min(gap, 8))
    return int(potential)


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
        if node not in mapping:
            continue
        best = 0
        for parent in preds[node]:
            if parent not in mapping:
                continue
            wait = config["a_waits"]["cross"] if scene == "A" and mapping[parent] != mapping[node] else 0
            if scene != "A" and core_of_node[parent] != core_of_node[node]:
                wait = config["b_wait"]
            best = max(best, finish[parent] + wait)
        finish[node] = best + max(1, int(view["ops"][str(node)].get("cycles", 0)))
    path = max(finish.values(), default=0)
    breakdown = structural_byte_breakdown(view, plan, scene)
    copy_bytes = breakdown["structural_copy_bytes"]
    ddr_work = math.ceil(copy_bytes / config["bandwidth"]) if copy_bytes else 0
    pressure = capacity_pressure(view, plan, scene, config)
    light_time = max(path, max(loads.values(), default=0), ddr_work)
    cache_work = 0
    cache_hits = 0
    reuse_potential = 0
    replay_error = None
    if scene == "C":
        try:
            replay = fifo_cache_replay(view, plan, config, scene)
        except ValueError as exc:
            replay_error = str(exc)
            replay = {"hit_bytes": 0, "miss_bytes": 0, "hit_count": 0, "miss_count": 0, "query_bytes": 0, "query_count": 0, "events": []}
    else:
        replay = {"hit_bytes": 0, "miss_bytes": 0, "hit_count": 0, "miss_count": 0, "query_bytes": 0, "query_count": 0, "events": []}
    if scene == "C":
        cache_hits = int(replay["hit_bytes"])
        reuse_potential = same_core_reuse_potential(view, plan, config)
        cache_work = math.ceil(cache_hits / config["cache"]["bandwidth"]) if cache_hits else 0
        # Cache hits leave the logical COPY count unchanged but move those
        # read bytes from DDR to the independent CACHE_READ service pool.
        ddr_service_bytes = max(0, copy_bytes - cache_hits)
        ddr_work = math.ceil(ddr_service_bytes / config["bandwidth"]) if ddr_service_bytes else 0
        light_time = max(path, max(loads.values(), default=0), ddr_work, cache_work)
    else:
        ddr_service_bytes = copy_bytes
    expected_gain = cache_hits * (1 / config["bandwidth"] - 1 / config["cache"]["bandwidth"]) if cache_hits else 0.0
    return {
        "scene": scene,
        "light_time": int(light_time),
        "copy_bytes": int(copy_bytes),
        "input_read_bytes": int(breakdown["input_read_bytes"]),
        "cross_read_bytes": int(breakdown["cross_read_bytes"]),
        "cross_write_bytes": int(breakdown["cross_write_bytes"]),
        "output_write_bytes": int(breakdown["output_write_bytes"]),
        "ddr_service_bytes": int(ddr_service_bytes),
        "cache_service_bytes": int(cache_hits),
        "ddr_service_cycles": int(ddr_work),
        "cache_service_cycles": int(cache_work),
        "pressure_bytes": int(pressure),
        "cache_hit_bytes": int(cache_hits),
        "cache_miss_bytes": int(replay["miss_bytes"]),
        "cache_hit_count": int(replay["hit_count"]),
        "cache_miss_count": int(replay["miss_count"]),
        "cache_query_bytes": int(replay.get("query_bytes", 0)),
        "cache_query_count": int(replay.get("query_count", 0)),
        "cache_expected_gain": float(expected_gain),
        "cache_replay_error": replay_error,
        "loads": dict(loads),
        "cache_reuse_potential": int(reuse_potential),
        "score": (int(light_time), int(copy_bytes), int(pressure), -int(cache_hits), -int(reuse_potential)),
    }
