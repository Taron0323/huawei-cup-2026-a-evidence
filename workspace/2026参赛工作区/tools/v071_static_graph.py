"""Static graph views used by the V0.7.1 trial runner.

The module intentionally keeps the official attachment read-only.  It builds
deterministic operation orders and the domain counters needed by the trial
search; official execution remains the authority for timing and spill data.
"""

from __future__ import annotations

from collections import defaultdict
import heapq
import json
from pathlib import Path
from typing import Any


COMPUTE_OPS = frozenset({"COPY_IN", "COPY_OUT"})


def load_case(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _compute_ids(graph: dict[str, Any]) -> list[int]:
    return sorted(int(op["id"]) for op in graph.get("ops", []) if op.get("op") not in COMPUTE_OPS)


def _views(graph: dict[str, Any]) -> tuple[dict[int, set[int]], dict[int, set[int]], dict[int, dict[str, Any]]]:
    """Return contracted compute predecessor/successor maps and operations."""
    ops = {int(op["id"]): op for op in graph.get("ops", [])}
    eligible = set(_compute_ids(graph))
    producers: dict[int, set[int]] = defaultdict(set)
    consumers: dict[int, set[int]] = defaultdict(set)
    for edge in graph.get("edges", []):
        source, target = int(edge["source"]), int(edge["target"])
        if source in eligible and target not in eligible:
            producers[target].add(source)
        elif source not in eligible and target in eligible:
            consumers[source].add(target)
    succs = {node: set() for node in eligible}
    preds = {node: set() for node in eligible}
    for tensor, sources in producers.items():
        for source in sources:
            for target in consumers.get(tensor, ()):
                if source != target and target in eligible:
                    succs[source].add(target)
                    preds[target].add(source)
    return preds, succs, ops


def _topological(nodes: set[int], preds: dict[int, set[int]], succs: dict[int, set[int]]) -> list[int]:
    indegree = {node: len(preds[node] & nodes) for node in nodes}
    ready = [node for node, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for target in sorted(succs[node] & nodes):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, target)
    if len(order) != len(nodes):
        raise ValueError("contracted compute graph is cyclic")
    return order


def _components(nodes: set[int], preds: dict[int, set[int]], succs: dict[int, set[int]]) -> list[list[int]]:
    remaining = set(nodes)
    result: list[list[int]] = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        component = {seed}
        stack = [seed]
        while stack:
            node = stack.pop()
            neighbours = (preds[node] | succs[node]) & remaining
            remaining.difference_update(neighbours)
            component.update(neighbours)
            stack.extend(sorted(neighbours))
        result.append(sorted(component))
    return result


def _dfs_order(component: list[int], preds: dict[int, set[int]], succs: dict[int, set[int]]) -> list[int]:
    """Deterministic DFS reverse-postorder, repaired to a valid topological order."""
    nodes = set(component)
    roots = sorted(node for node in nodes if not (preds[node] & nodes))
    seen: set[int] = set()
    post: list[int] = []

    # Use an explicit stack so deep linear graphs do not hit Python's
    # recursion limit.  ``expanded`` records the postorder return event.
    def visit_iterative(start: int) -> None:
        stack: list[tuple[int, bool]] = [(start, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                post.append(node)
                continue
            if node in seen:
                continue
            seen.add(node)
            stack.append((node, True))
            for target in reversed(sorted(succs[node] & nodes)):
                if target not in seen:
                    stack.append((target, False))

    for root in roots:
        visit_iterative(root)
    for node in sorted(nodes - seen):
        visit_iterative(node)
    candidate = list(reversed(post))
    position = {node: index for index, node in enumerate(candidate)}
    for source in nodes:
        for target in succs[source] & nodes:
            if position[source] >= position[target]:
                return _topological(nodes, preds, succs)
    return candidate


def _h_order(nodes: set[int], preds: dict[int, set[int]], succs: dict[int, set[int]], ops: dict[int, dict[str, Any]]) -> tuple[list[int], dict[int, int]]:
    depth: dict[int, int] = {}
    for node in reversed(_topological(nodes, preds, succs)):
        depth[node] = max((depth[target] for target in succs[node] & nodes), default=0) + max(1, int(ops[node].get("cycles", 0)))
    indegree = {node: len(preds[node] & nodes) for node in nodes}
    ready = [(-depth[node], node) for node, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        _, node = heapq.heappop(ready)
        order.append(node)
        for target in sorted(succs[node] & nodes):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, (-depth[target], target))
    return order, depth


def _r_order(graph: dict[str, Any], nodes: set[int], preds: dict[int, set[int]], succs: dict[int, set[int]], ops: dict[int, dict[str, Any]], h: dict[int, int]) -> list[int]:
    tensors = {int(t["id"]): t for t in graph.get("tensors", [])}
    producers: dict[int, int] = {}
    consumers: dict[int, set[int]] = defaultdict(set)
    for edge in graph.get("edges", []):
        source, target = int(edge["source"]), int(edge["target"])
        if source in nodes and target in tensors:
            producers[target] = source
        elif source in tensors and target in nodes:
            consumers[source].add(target)
    remaining_use = {tid: len(consumers.get(tid, ())) for tid in tensors}
    consumed_tensors: dict[int, list[int]] = defaultdict(list)
    produced_tensors: dict[int, list[int]] = defaultdict(list)
    for tid, users in consumers.items():
        for node in users:
            consumed_tensors[node].append(tid)
    for tid, producer in producers.items():
        produced_tensors[producer].append(tid)
    indegree = {node: len(preds[node] & nodes) for node in nodes}
    ready = {node for node, degree in indegree.items() if degree == 0}
    order: list[int] = []
    while ready:
        shortlist = sorted(ready, key=lambda node: (-h[node], node))[:8]
        def release_score(node: int) -> tuple[int, int, int]:
            release = 0
            for tid in consumed_tensors.get(node, ()):
                if remaining_use.get(tid, 0) == 1:
                    release += int(tensors[tid].get("size", 0))
            produced = sum(int(tensors[tid].get("size", 0)) for tid in produced_tensors.get(node, ()))
            return release - produced, h[node], -node
        chosen = max(shortlist, key=release_score)
        ready.remove(chosen)
        order.append(chosen)
        for tid in consumed_tensors.get(chosen, ()):
            remaining_use[tid] = max(0, remaining_use.get(tid, 0) - 1)
        for target in sorted(succs[chosen] & nodes):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.add(target)
    if len(order) != len(nodes):
        raise ValueError("R order failed on cyclic graph")
    return order


def build_static_views(graph: dict[str, Any]) -> dict[str, Any]:
    preds, succs, ops = _views(graph)
    nodes = set(preds)
    topo = _topological(nodes, preds, succs)
    components = _components(nodes, preds, succs)
    components.sort(key=lambda comp: (-sum(max(1, int(ops[n].get("cycles", 0))) for n in comp), min(comp)))
    h_order, h_depth = _h_order(nodes, preds, succs, ops)
    d_order: list[int] = []
    for component in components:
        d_order.extend(_dfs_order(component, preds, succs))
    r_order = _r_order(graph, nodes, preds, succs, ops, h_depth)
    pipe_work = defaultdict(int)
    for node in nodes:
        pipe_work[str(ops[node].get("pipe", "UNKNOWN"))] += max(1, int(ops[node].get("cycles", 0)))
    tensors = {int(t["id"]): t for t in graph.get("tensors", [])}
    producers: dict[int, set[int]] = defaultdict(set)
    consumers: dict[int, set[int]] = defaultdict(set)
    copy_out = set()
    op_types = {int(op["id"]): op.get("op") for op in graph.get("ops", [])}
    for edge in graph.get("edges", []):
        source, target = int(edge["source"]), int(edge["target"])
        if source in nodes and target in tensors:
            producers[target].add(source)
        elif source in tensors and target in nodes:
            consumers[source].add(target)
        elif source in tensors and op_types.get(target) == "COPY_OUT":
            copy_out.add(source)
    inputs = {tid for tid, users in consumers.items() if users and not (producers.get(tid, set()) & nodes)}
    produced = {tid for tid, owners in producers.items() if owners & nodes}
    output_tensors = {tid for tid in produced if tid in copy_out or not (consumers.get(tid) & nodes)}
    original_copy = 0
    for op in graph.get("ops", []):
        if op.get("op") not in {"COPY_IN", "COPY_OUT"}:
            continue
        op_id = int(op["id"])
        for edge in graph.get("edges", []):
            if op.get("op") == "COPY_IN" and int(edge["source"]) == op_id and int(edge["target"]) in tensors:
                original_copy += int(tensors[int(edge["target"])].get("size", 0))
            if op.get("op") == "COPY_OUT" and int(edge["target"]) == op_id and int(edge["source"]) in tensors:
                original_copy += int(tensors[int(edge["source"])].get("size", 0))
    total_cycles = sum(max(1, int(ops[node].get("cycles", 0))) for node in nodes)
    longest_path = max(h_depth.values(), default=0)
    w_m = sum(max(1, int(ops[node].get("cycles", 0))) for node in nodes if ops[node].get("pipe") == "PIPE_M")
    w_v = sum(max(1, int(ops[node].get("cycles", 0))) for node in nodes if ops[node].get("pipe") == "PIPE_V")
    return {
        "nodes": sorted(nodes),
        "preds": {str(node): sorted(preds[node]) for node in nodes},
        "succs": {str(node): sorted(succs[node]) for node in nodes},
        "components": components,
        "topological_order": topo,
        "d_order": d_order,
        "h_order": h_order,
        "r_order": r_order,
        "h_depth": {str(k): v for k, v in h_depth.items()},
        "pipe_work": dict(pipe_work),
        "n_compute": len(nodes),
        "total_cycles": total_cycles,
        "longest_path_cycles": longest_path,
        "w_m_cycles": w_m,
        "w_v_cycles": w_v,
        "original_copy_bytes": original_copy,
        "input_tensors": sorted(inputs),
        "output_tensors": sorted(output_tensors),
        "tensor_sizes": {str(tid): int(t.get("size", 0)) for tid, t in tensors.items()},
        "tensor_producers": {str(tid): sorted(values) for tid, values in producers.items()},
        "tensor_consumers": {str(tid): sorted(values) for tid, values in consumers.items()},
    }


def compute_domain_bytes(view: dict[str, Any], plan: dict[str, Any], scene: str) -> dict[str, int]:
    mapping = {int(op): int(sg) for op, sg in plan["node_to_subgraph"].items()}
    core_by_sg = {int(sg): core for core, schedule in enumerate(plan["core_schedules"]) for sg in schedule}
    q0 = 0
    tensor_ids = set(view["tensor_consumers"]) | set(view["tensor_producers"])
    output_ids = {int(x) for x in view["output_tensors"]}
    for tid in tensor_ids:
        consumers = view["tensor_consumers"].get(tid, [])
        users = [int(node) for node in consumers if int(node) in mapping]
        producer = [int(node) for node in view["tensor_producers"].get(tid, []) if int(node) in mapping]
        if not users and not producer:
            continue
        size = int(view["tensor_sizes"].get(tid, 0))
        if scene == "A":
            domains = {mapping[node] for node in users}
            if not producer:
                q0 += size * len(domains)
            else:
                p = mapping[producer[0]]
                remote = {domain for domain in domains if domain != p}
                if remote or int(tid) in output_ids:
                    q0 += size * (len(remote) + 1)
        else:
            domains = {core_by_sg[mapping[node]] for node in users}
            if not producer:
                q0 += size * len(domains)
            else:
                p = core_by_sg[mapping[producer[0]]]
                remote = {domain for domain in domains if domain != p}
                q0 += size * (2 * len(remote) + (1 if int(tid) in output_ids else 0))
    return {"structural_copy_bytes": q0, "original_copy_bytes": int(view["original_copy_bytes"]), "added_copy_bytes_lower_bound": q0 - int(view["original_copy_bytes"])}
