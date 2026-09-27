#!/usr/bin/env python3
"""Finite V0.7.1 candidate generator.

The supplied evaluator remains authoritative.  This module implements the
V0.7.1 trial's deterministic H/R/D starts, resident-domain aware ordering,
capacity-oriented candidates, and bounded local edits.  It deliberately keeps
the submitted interface to ``node_to_subgraph`` and ``core_schedules``.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/a_solver"))
import a_solver  # type: ignore  # noqa: E402
from verify import check_plan  # type: ignore  # noqa: E402


def eligible_ops(graph: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(op["id"]): op for op in graph.get("ops", [])
            if op.get("op") not in {"COPY_IN", "COPY_OUT"}}


def dependencies(graph: dict[str, Any]) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    # Build the contracted compute graph directly from tensor producer and
    # consumer lists.  The legacy helper walks every excluded COPY path once
    # per source operation, which becomes quadratic on the largest attachment
    # graphs.  COPY_IN/COPY_OUT are boundary nodes and therefore do not create
    # compute-to-compute edges themselves.
    ops = {int(op["id"]): op for op in graph.get("ops", [])}
    eligible = {node for node, op in ops.items() if op.get("op") not in {"COPY_IN", "COPY_OUT"}}
    producers: dict[int, set[int]] = defaultdict(set)
    consumers: dict[int, set[int]] = defaultdict(set)
    succs = {node: set() for node in eligible}
    for edge in graph.get("edges", []):
        source, target = int(edge["source"]), int(edge["target"])
        if source in ops and target in ops:
            if source in eligible and target in eligible:
                succs[source].add(target)
        elif source in ops and target not in ops:
            producers[target].add(source)
        elif source not in ops and target in ops:
            consumers[source].add(target)
    for tensor, sources in producers.items():
        targets = consumers.get(tensor, ())
        for source in sources:
            if source in eligible:
                succs[source].update(target for target in targets if target in eligible and target != source)
    preds = {node: set() for node in eligible}
    for source, targets in succs.items():
        for target in targets:
            preds[target].add(source)
    return preds, succs


def weights(graph: dict[str, Any]) -> dict[int, float]:
    return {node: max(1.0, float(op.get("cycles", 0)))
            for node, op in eligible_ops(graph).items()}


def topological(nodes: Iterable[int], preds: dict[int, set[int]], succs: dict[int, set[int]]) -> list[int]:
    node_set = set(nodes)
    indegree = {n: len(preds[n] & node_set) for n in node_set}
    ready = [n for n, d in indegree.items() if d == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for nxt in sorted(succs[n] & node_set):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, nxt)
    if len(order) != len(node_set):
        raise ValueError("cyclic eligible graph")
    return order


def weak_components(graph: dict[str, Any]) -> list[set[int]]:
    pred, succ = dependencies(graph)
    remaining = set(pred)
    components: list[set[int]] = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        stack = [seed]
        component = {seed}
        while stack:
            n = stack.pop()
            for nxt in sorted((pred[n] | succ[n]) & remaining):
                remaining.remove(nxt)
                component.add(nxt)
                stack.append(nxt)
        components.append(component)
    return components


def critical_heights(graph: dict[str, Any]) -> dict[int, float]:
    pred, succ = dependencies(graph)
    order = topological(pred, pred, succ)
    op_w = weights(graph)
    height: dict[int, float] = {}
    for n in reversed(order):
        height[n] = op_w[n] + max((height[x] for x in succ[n]), default=0.0)
    return height


def h_order(graph: dict[str, Any]) -> list[int]:
    pred, succ = dependencies(graph)
    heights = critical_heights(graph)
    indegree = {n: len(pred[n]) for n in pred}
    ready = [( -heights[n], n) for n, d in indegree.items() if d == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        _, n = heapq.heappop(ready)
        order.append(n)
        for nxt in sorted(succ[n]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, (-heights[nxt], nxt))
    return order


def d_order(graph: dict[str, Any]) -> list[int]:
    pred, succ = dependencies(graph)
    op_w = weights(graph)
    components = weak_components(graph)
    components.sort(key=lambda c: (-sum(op_w[n] for n in c), min(c)))
    result: list[int] = []
    for component in components:
        # DFS order differs from H while remaining topological.
        indegree = {n: len(pred[n] & component) for n in component}
        stack = sorted((n for n, d in indegree.items() if d == 0), reverse=True)
        local: list[int] = []
        while stack:
            n = stack.pop()
            local.append(n)
            for nxt in sorted(succ[n] & component, reverse=True):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    stack.append(nxt)
        result.extend(local)
    return result


def r_order(graph: dict[str, Any]) -> list[int]:
    pred, succ = dependencies(graph)
    heights = critical_heights(graph)
    ops = eligible_ops(graph)
    tensor_by_id = {int(t["id"]): t for t in graph.get("tensors", [])}
    consumers: dict[int, set[int]] = defaultdict(set)
    produced_by_op: dict[int, set[int]] = defaultdict(set)
    for edge in graph.get("edges", []):
        src, dst = int(edge["source"]), int(edge["target"])
        if src in tensor_by_id and dst in ops:
            consumers[src].add(dst)
        elif src in ops and dst in tensor_by_id:
            produced_by_op[src].add(dst)
    # Index tensor access by operation once.  Re-scanning every tensor for
    # each ready operation makes R-order construction quadratic on the large
    # official graphs.
    consumed_by_op: dict[int, set[int]] = defaultdict(set)
    for tensor, users in consumers.items():
        for user in users:
            consumed_by_op[user].add(tensor)
    indegree = {n: len(pred[n]) for n in pred}
    ready = {n for n, d in indegree.items() if d == 0}
    order: list[int] = []
    while ready:
        def score(n: int) -> tuple[float, float, int]:
            release = sum(float(tensor_by_id[t].get("size", 0))
                          for t in consumed_by_op.get(n, ()))
            produce = sum(float(tensor_by_id[t].get("size", 0))
                          for t in produced_by_op.get(n, set()))
            return (-(release - produce), -heights[n], n)
        n = min(ready, key=score)
        ready.remove(n)
        order.append(n)
        for nxt in succ[n]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.add(nxt)
    return order


def split_order(order: list[int], blocks: int, graph: dict[str, Any]) -> list[list[int]]:
    if not order:
        return []
    blocks = max(1, min(len(order), blocks))
    w = weights(graph)
    total = sum(w[n] for n in order)
    result: list[list[int]] = []
    start = 0
    acc = 0.0
    remaining_weight = total
    for i, n in enumerate(order):
        acc += w[n]
        left = len(order) - i - 1
        groups_left = blocks - len(result) - 1
        target = remaining_weight / max(1, blocks - len(result))
        if len(result) < blocks - 1 and left >= groups_left and acc >= target:
            result.append(order[start:i + 1])
            start = i + 1
            remaining_weight -= acc
            acc = 0.0
    if start < len(order):
        result.append(order[start:])
    return [g for g in result if g]


def component_groups(graph: dict[str, Any], max_blocks: int | None = None) -> list[list[int]]:
    pred, succ = dependencies(graph)
    ops_w = weights(graph)
    comps = weak_components(graph)
    comps.sort(key=lambda c: (-sum(ops_w[n] for n in c), min(c)))
    groups: list[list[int]] = []
    for c in comps:
        order = topological(c, pred, succ)
        if max_blocks and len(order) > max_blocks * 200:
            groups.extend(split_order(order, max_blocks, graph))
        else:
            groups.append(order)
    return groups


def block_plan(groups: list[list[int]], cores: int, graph: dict[str, Any],
               assignment: str = "greedy") -> dict[str, Any]:
    op_w = weights(graph)
    schedules = [[] for _ in range(cores)]
    loads = [0.0] * cores
    mapping: dict[int, int] = {}
    for sg, group in enumerate(groups):
        if assignment == "round_robin":
            core = sg % cores
        else:
            core = min(range(cores), key=lambda k: (loads[k], k))
        schedules[core].append(sg)
        loads[core] += sum(op_w[n] for n in group)
        mapping.update({n: sg for n in group})
    return {"node_to_subgraph": mapping, "core_schedules": schedules}


def groups_from_plan(graph: dict[str, Any], plan: dict[str, Any]) -> list[tuple[list[int], int]]:
    by_sg: dict[int, list[int]] = defaultdict(list)
    for n, sg in plan["node_to_subgraph"].items():
        by_sg[int(sg)].append(int(n))
    core_of = {int(sg): core for core, seq in enumerate(plan["core_schedules"]) for sg in seq}
    pred, succ = dependencies(graph)
    out = []
    for sg, nodes in sorted(by_sg.items()):
        out.append((topological(nodes, pred, succ), core_of[sg]))
    return out


def plan_from_blocks(blocks: list[tuple[list[int], int]], cores: int) -> dict[str, Any]:
    schedules = [[] for _ in range(cores)]
    mapping: dict[int, int] = {}
    for sg, (nodes, core) in enumerate(blocks):
        schedules[core].append(sg)
        mapping.update({n: sg for n in nodes})
    return {"node_to_subgraph": mapping, "core_schedules": schedules}


def normalize_blocks(blocks: list[tuple[list[int], int]], graph: dict[str, Any]) -> list[tuple[list[int], int]]:
    pred, succ = dependencies(graph)
    normalized = []
    for nodes, core in blocks:
        unique = set(nodes)
        normalized.append((topological(unique, pred, succ), core))
    return normalized


def resident_pressure(graph: dict[str, Any], blocks: list[tuple[list[int], int]]) -> int:
    # A cheap domain-aware proxy used only to order capacity representatives.
    pred, succ = dependencies(graph)
    block_of = {n: i for i, (nodes, _) in enumerate(blocks) for n in nodes}
    op_ids = sorted(block_of)
    pressure = 0
    for u in op_ids:
        for v in succ[u]:
            if block_of[u] != block_of[v]:
                pressure += max(1, int(abs(v - u)))
    return pressure


def start_plans(graph: dict[str, Any], cores: int, scene: str) -> list[tuple[str, dict[str, Any]]]:
    n = len(eligible_ops(graph))
    starts: list[tuple[str, dict[str, Any]]] = []
    all_nodes = sorted(eligible_ops(graph))
    starts.append((scene + "0", block_plan([all_nodes], cores, graph, "round_robin")))
    comp = component_groups(graph, max_blocks=max(1, cores))
    starts.append((scene + "1", block_plan(comp, cores, graph)))
    if scene == "A":
        starts.append(("A2", block_plan(split_order(d_order(graph), min(n, 2 * cores), graph), cores, graph)))
        starts.append(("A3", block_plan(split_order(h_order(graph), min(n, 4 * cores), graph), cores, graph)))
    else:
        starts.append(("B2", block_plan(split_order(h_order(graph), min(n, 4 * cores), graph), cores, graph)))
        # R-order scores every ready operation.  On a very wide large graph
        # that ready set can be O(n), making repeated argmin scans dominate
        # the experiment.  H-order is the deterministic bounded fallback for
        # this scale; its identity is kept in the candidate name.
        if n > 20_000:
            starts.append(("B3_H_fallback", block_plan(split_order(h_order(graph), min(n, 8 * cores), graph), cores, graph)))
        else:
            starts.append(("B3", block_plan(split_order(r_order(graph), min(n, 8 * cores), graph), cores, graph)))
    return starts


def local_candidates(graph: dict[str, Any], plan: dict[str, Any], cores: int,
                     scene: str, limit: int) -> list[tuple[str, dict[str, Any]]]:
    blocks = groups_from_plan(graph, plan)
    candidates: list[tuple[str, dict[str, Any]]] = []
    # Move a bounded number of blocks to another core.
    for i, (nodes, core) in enumerate(blocks):
        for target in range(cores):
            if target == core:
                continue
            edited = list(blocks)
            edited[i] = (nodes, target)
            candidates.append((f"{scene}_move_{i}_{target}", plan_from_blocks(edited, cores)))
            if len(candidates) >= limit:
                return candidates
    # Merge adjacent blocks on the same core.
    for i in range(len(blocks) - 1):
        if blocks[i][1] == blocks[i + 1][1]:
            merged = (blocks[i][0] + blocks[i + 1][0], blocks[i][1])
            edited = blocks[:i] + [merged] + blocks[i + 2:]
            candidates.append((f"{scene}_merge_{i}", plan_from_blocks(normalize_blocks(edited, graph), cores)))
            if len(candidates) >= limit:
                return candidates
    # Split the largest block at its middle; this is the explicit fine-grain path.
    if blocks:
        i = max(range(len(blocks)), key=lambda j: len(blocks[j][0]))
        nodes, core = blocks[i]
        if len(nodes) >= 4:
            mid = len(nodes) // 2
            edited = blocks[:i] + [(nodes[:mid], core), (nodes[mid:], core)] + blocks[i + 1:]
            candidates.append((f"{scene}_split_{i}", plan_from_blocks(normalize_blocks(edited, graph), cores)))
    # Reorder adjacent same-core blocks (C's event timing candidate).
    for i in range(len(blocks) - 1):
        if blocks[i][1] == blocks[i + 1][1]:
            edited = list(blocks)
            edited[i], edited[i + 1] = edited[i + 1], edited[i]
            candidates.append((f"{scene}_reorder_{i}", plan_from_blocks(edited, cores)))
            if len(candidates) >= limit:
                break
    return candidates[:limit]


def candidate_pool(graph: dict[str, Any], cores: int, scene: str,
                   local_limit: int = 12) -> list[tuple[str, dict[str, Any], str]]:
    starts = start_plans(graph, cores, scene)
    result: list[tuple[str, dict[str, Any], str]] = [(name, plan, "start") for name, plan in starts]
    # Expand only the two most structurally distinct starts.  V0.7.1's budget
    # is bounded; the official evaluator decides which candidate survives.
    # On the largest supplied graphs, validating every local edit is more
    # expensive than the official profile. Keep the four auditable starts and
    # reserve local edits for graphs where their validation is tractable.
    if len(eligible_ops(graph)) <= 20_000:
        for name, plan in starts[-2:]:
            for edit_name, edit_plan in local_candidates(graph, plan, cores, scene, local_limit // 2):
                result.append((edit_name, edit_plan, "local"))
    seen: set[str] = set()
    unique: list[tuple[str, dict[str, Any], str]] = []
    large_graph = len(eligible_ops(graph)) > 20_000
    for name, plan, source in result:
        if not large_graph:
            try:
                check_plan(graph, plan)
            except Exception:
                continue
        else:
            # Starts are built from topological orders and only regroup those
            # orders.  Keep a linear coverage check here; the official profile
            # remains the authoritative full feasibility check for these
            # large cases, while avoiding the quadratic legacy verifier.
            eligible = set(eligible_ops(graph))
            mapping = {int(node): int(group) for node, group in plan.get("node_to_subgraph", {}).items()}
            flat = [int(group) for sequence in plan.get("core_schedules", []) for group in sequence]
            if set(mapping) != eligible or len(flat) != len(set(flat)) or set(flat) != set(mapping.values()):
                continue
        payload = json.dumps(plan, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        if digest not in seen:
            seen.add(digest)
            unique.append((name, plan, source))
    return unique


def cache_candidates(graph: dict[str, Any], base_plan: dict[str, Any], cores: int) -> list[tuple[str, dict[str, Any], str]]:
    result = [("C_base", base_plan, "base")]
    blocks = groups_from_plan(graph, base_plan)
    # Aggregate neighboring blocks and a timing reorder form the two explicit
    # C mechanisms; a split gives the dispersal alternative when available.
    for i in range(len(blocks) - 1):
        if blocks[i][1] == blocks[i + 1][1]:
            merged = blocks[:i] + [([*blocks[i][0], *blocks[i + 1][0]], blocks[i][1])] + blocks[i + 2:]
            result.append((f"C_aggregate_{i}", plan_from_blocks(normalize_blocks(merged, graph), cores), "aggregate"))
            break
    for i in range(len(blocks) - 1):
        if blocks[i][1] == blocks[i + 1][1]:
            edited = list(blocks)
            edited[i], edited[i + 1] = edited[i + 1], edited[i]
            result.append((f"C_timing_{i}", plan_from_blocks(edited, cores), "timing"))
            break
    if blocks:
        i = max(range(len(blocks)), key=lambda j: len(blocks[j][0]))
        nodes, core = blocks[i]
        if len(nodes) >= 4:
            mid = len(nodes) // 2
            split = blocks[:i] + [(nodes[:mid], core), (nodes[mid:], core)] + blocks[i + 1:]
            result.append((f"C_disperse_{i}", plan_from_blocks(normalize_blocks(split, graph), cores), "disperse"))
    unique: list[tuple[str, dict[str, Any], str]] = []
    seen: set[str] = set()
    for name, plan, source in result:
        try:
            check_plan(graph, plan)
        except Exception:
            continue
        digest = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        if digest not in seen:
            seen.add(digest)
            unique.append((name, plan, source))
    return unique
