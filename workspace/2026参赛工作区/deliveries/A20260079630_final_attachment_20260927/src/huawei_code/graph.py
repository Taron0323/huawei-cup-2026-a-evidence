# 人工智能工具辅助编程声明：本程序及代码在人工智能工具辅助下完成。
# 工具名称：OpenAI Codex；版本/型号：GPT-6 系列（准确会话型号以平台记录为准）；
# 开发机构：OpenAI；版本发布日期：以实际平台记录为准。
# 队员已对算法、参数、输入输出和官方评估结果进行人工核对，并保留后处理记录。

"""Static graph representation for the fresh A-problem solver.

The official attachment is treated as read-only.  This module only derives
indexes and deterministic topological orders; it never assigns execution times.
"""

from __future__ import annotations

from collections import defaultdict
import heapq
import json
from pathlib import Path
from typing import Any, Iterable

COPY_OPS = frozenset({"COPY_IN", "COPY_OUT"})


def load_graph(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _compute_ops(graph: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(op["id"]): op for op in graph.get("ops", []) if op.get("op") not in COPY_OPS}


def _tensor_links(graph: dict[str, Any]):
    ops = {int(op["id"]): op for op in graph.get("ops", [])}
    compute = set(_compute_ops(graph))
    tensors = {int(t["id"]): t for t in graph.get("tensors", [])}
    producers: dict[int, set[int]] = defaultdict(set)
    consumers: dict[int, set[int]] = defaultdict(set)
    copy_out: set[int] = set()
    for edge in graph.get("edges", []):
        a, b = int(edge["source"]), int(edge["target"])
        if a in compute and b in tensors:
            producers[b].add(a)
        elif a in tensors and b in compute:
            consumers[a].add(b)
        elif a in tensors and b in ops and ops[b].get("op") == "COPY_OUT":
            copy_out.add(a)
    preds = {node: set() for node in compute}
    succs = {node: set() for node in compute}
    for tid, owners in producers.items():
        for owner in owners:
            for consumer in consumers.get(tid, ()):
                if owner != consumer:
                    succs[owner].add(consumer)
                    preds[consumer].add(owner)
    inputs = {tid for tid, users in consumers.items() if users and not (producers.get(tid, set()) & compute)}
    produced = {tid for tid, owners in producers.items() if owners & compute}
    outputs = {tid for tid in produced if tid in copy_out or not (consumers.get(tid, set()) & compute)}
    return tensors, producers, consumers, copy_out, inputs, outputs, preds, succs


def topological(nodes: Iterable[int], preds: dict[int, set[int]], succs: dict[int, set[int]]) -> list[int]:
    node_set = set(nodes)
    indegree = {node: len(preds[node] & node_set) for node in node_set}
    ready = [node for node, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for nxt in sorted(succs[node] & node_set):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, nxt)
    if len(order) != len(node_set):
        raise ValueError("contracted compute graph is cyclic")
    return order


def weak_components(nodes: set[int], preds: dict[int, set[int]], succs: dict[int, set[int]]) -> list[list[int]]:
    left = set(nodes)
    components: list[list[int]] = []
    while left:
        seed = min(left)
        left.remove(seed)
        component = {seed}
        stack = [seed]
        while stack:
            node = stack.pop()
            neighbours = (preds[node] | succs[node]) & left
            left.difference_update(neighbours)
            component.update(neighbours)
            stack.extend(sorted(neighbours))
        components.append(sorted(component))
    return components


def reverse_path_priority(nodes, preds, succs, ops):
    topo = topological(nodes, preds, succs)
    depth = {}
    for node in reversed(topo):
        depth[node] = max((depth[nxt] for nxt in succs[node]), default=0) + max(1, int(ops[node].get("cycles", 0)))
    indegree = {node: len(preds[node]) for node in nodes}
    ready = [(-depth[node], node) for node in nodes if indegree[node] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        _, node = heapq.heappop(ready)
        order.append(node)
        for nxt in sorted(succs[node]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, (-depth[nxt], nxt))
    return order, depth


def release_priority(graph, nodes, preds, succs, ops, depth):
    tensors, producers, consumers, *_ = _tensor_links(graph)
    remaining = {tid: len(users) for tid, users in consumers.items()}
    consumed = defaultdict(list)
    produced = defaultdict(list)
    for tid, users in consumers.items():
        for node in users:
            consumed[node].append(tid)
    for tid, owners in producers.items():
        for node in owners:
            produced[node].append(tid)
    indegree = {node: len(preds[node]) for node in nodes}
    ready = {node for node in nodes if indegree[node] == 0}
    order = []
    while ready:
        shortlist = sorted(ready, key=lambda n: (-depth[n], n))[:8]
        def key(node):
            released = sum(int(tensors[t].get("size", 0)) for t in consumed[node] if remaining.get(t, 0) == 1)
            created = sum(int(tensors[t].get("size", 0)) for t in produced[node])
            return (released - created, depth[node], -node)
        node = max(shortlist, key=key)
        ready.remove(node)
        order.append(node)
        for tid in consumed[node]:
            remaining[tid] = max(0, remaining.get(tid, 0) - 1)
        for nxt in succs[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.add(nxt)
    if len(order) != len(nodes):
        raise ValueError("release-priority order failed")
    return order


def static_view(graph: dict[str, Any]) -> dict[str, Any]:
    ops = _compute_ops(graph)
    tensors, producers, consumers, copy_out, inputs, outputs, preds, succs = _tensor_links(graph)
    nodes = set(ops)
    topo = topological(nodes, preds, succs)
    components = weak_components(nodes, preds, succs)
    components.sort(key=lambda c: (-sum(max(1, int(ops[n].get("cycles", 0))) for n in c), min(c)))
    h_order, depth = reverse_path_priority(nodes, preds, succs, ops)
    d_order = [n for component in components for n in topological(component, preds, succs)]
    r_order = release_priority(graph, nodes, preds, succs, ops, depth)
    pipe_work = defaultdict(int)
    for node, op in ops.items():
        pipe_work[op.get("pipe", "UNKNOWN")] += max(1, int(op.get("cycles", 0)))
    return {
        "nodes": sorted(nodes),
        "ops": {str(k): v for k, v in ops.items()},
        "preds": {str(k): sorted(v) for k, v in preds.items()},
        "succs": {str(k): sorted(v) for k, v in succs.items()},
        "components": components, "topological": topo, "h_order": h_order, "d_order": d_order, "r_order": r_order,
        "depth": {str(k): v for k, v in depth.items()}, "pipe_work": dict(pipe_work),
        "tensor_sizes": {str(k): int(v.get("size", 0)) for k, v in tensors.items()},
        "tensor_pos": {str(k): str(v.get("pos", "UB")) for k, v in tensors.items()},
        "tensor_producers": {str(k): sorted(v) for k, v in producers.items()},
        "tensor_consumers": {str(k): sorted(v) for k, v in consumers.items()},
        "input_tensors": sorted(inputs), "output_tensors": sorted(outputs),
        "compute_ops": len(nodes), "total_cycles": sum(max(1, int(v.get("cycles", 0))) for v in ops.values()),
    }
