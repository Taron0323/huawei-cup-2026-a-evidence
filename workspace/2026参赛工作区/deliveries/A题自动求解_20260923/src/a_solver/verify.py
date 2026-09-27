"""Independent plan and observable timeline checks (no evaluator helpers)."""

from collections import Counter, defaultdict
from graphlib import TopologicalSorter


def dependencies(graph):
    ops = {op["id"]: op for op in graph["ops"]}
    producers, consumers, succ = defaultdict(set), defaultdict(set), defaultdict(set)
    for edge in graph["edges"]:
        a, b = edge["source"], edge["target"]
        if a in ops and b in ops:
            succ[a].add(b)
        elif a in ops:
            producers[b].add(a)
        elif b in ops:
            consumers[a].add(b)
    for tensor, sources in producers.items():
        for source in sources:
            succ[source].update(consumers[tensor])
    eligible = {node for node, op in ops.items() if op["op"] not in {"COPY_IN", "COPY_OUT"}}
    links = set()
    for source in eligible:
        pending, seen = list(succ[source]), set()
        while pending:
            target = pending.pop()
            if target in seen:
                continue
            seen.add(target)
            if target in eligible:
                links.add((source, target))
            else:
                pending.extend(succ[target])
    return eligible, links


def check_plan(graph, plan):
    eligible, links = dependencies(graph)
    mapping = {int(node): sg for node, sg in plan["node_to_subgraph"].items()}
    assert set(mapping) == eligible, "operation coverage"
    assert all(type(sg) is int and sg >= 0 for sg in mapping.values()), "subgraph domain"
    flat = [sg for sequence in plan["core_schedules"] for sg in sequence]
    assert len(flat) == len(set(flat)) and set(flat) == set(mapping.values()), "schedule coverage"
    precedes = {sg: set() for sg in flat}
    for a, b in links:
        if mapping[a] != mapping[b]:
            precedes[mapping[b]].add(mapping[a])
    for sequence in plan["core_schedules"]:
        for a, b in zip(sequence, sequence[1:]):
            precedes[b].add(a)
    list(TopologicalSorter(precedes).static_order())
    return {"status": "AI_VERIFIED", "eligible_ops": len(eligible),
            "dependency_edges": len(links), "subgraphs": len(flat),
            "coverage_residual": 0, "order_cycle_count": 0}


def check_result(graph, plan, result):
    eligible, links = dependencies(graph)
    ops = {op["id"]: op for op in graph["ops"]}
    original, counts, pipe_overlap = {}, Counter(), 0
    all_ops, tasks = [], {}
    for core in result["per_core_timeline"]:
        pipes = defaultdict(list)
        for task in core["tasks"]:
            tasks[task["task_id"]] = (core["core_id"], task)
        for op in core["ops"]:
            assert 0 <= op["start"] <= op["end"], "negative operation time"
            assert op["end"] - op["start"] == op["duration"], "duration identity"
            pipes[op["pipe"]].append(op)
            all_ops.append(op)
            if op["op_id"] in eligible:
                node = op["op_id"]
                counts[node] += 1
                original[node] = op
                assert op["duration"] == max(1, ops[node]["cycles"]), "compute duration"
        for sequence in pipes.values():
            sequence.sort(key=lambda op: (op["start"], op["end"]))
            for a, b in zip(sequence, sequence[1:]):
                pipe_overlap = max(pipe_overlap, a["end"] - b["start"])
    assert set(counts) == eligible and all(v == 1 for v in counts.values()), "timeline coverage"
    assert pipe_overlap == 0, "pipeline overlap"
    dependency_violation = max([0] + [original[a]["end"] - original[b]["start"] for a, b in links])
    assert dependency_violation == 0, "original data dependency"
    assert result["makespan"] == max((op["end"] for op in all_ops), default=0), "makespan identity"
    peak_excess = max([0] + [size - result["capacity_bytes"][pos]
                            for peak in result["memory_peak_by_core"].values()
                            for pos, size in peak.items()])
    assert peak_excess == 0, "evaluator-reported memory peak"
    movement = result["data_movement_bytes"]
    assert movement["scheduled_copy_bytes"] - movement["original_graph_copy_bytes"] == movement["added_copy_bytes"], "traffic identity"
    assert movement["partition_added_copy_bytes"] + movement["spill_added_copy_bytes"] == movement["added_copy_bytes"], "traffic decomposition"
    sync_violation = max([0] + [item["copy_in_release"] - item["copy_in_start"]
                              for item in result.get("cross_core_transfers", [])])
    assert sync_violation == 0, "cross-core release time"
    cache = result.get("cache_stats")
    if cache:
        total = cache["hit_bytes"] + cache["miss_bytes"]
        expected = cache["hit_bytes"] / total if total else 0.0
        assert abs(cache["hit_rate"] - expected) <= 1e-12, "byte-weighted cache hit rate"
        assert 0 <= cache["hit_rate"] <= 1, "cache rate range"
    return {"status": "AI_VERIFIED", "operations_checked": len(all_ops),
            "pipeline_overlap_cycles": pipe_overlap, "dependency_violation_cycles": dependency_violation,
            "reported_capacity_excess_bytes": peak_excess, "sync_violation_cycles": sync_violation,
            "limitation": "Memory occupancy is checked against evaluator-reported peaks; this is not an independent memory simulator."}
