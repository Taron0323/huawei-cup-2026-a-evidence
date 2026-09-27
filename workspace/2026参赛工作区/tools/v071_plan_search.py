"""Deterministic V0.7.1 seed construction and plan normalization."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _weight(view: dict[str, Any], nodes: list[int]) -> tuple[int, int]:
    pipe = {"PIPE_M": 0, "PIPE_V": 1}
    values = [0, 0]
    for node in nodes:
        values[pipe.get(_op(view, node).get("pipe"), 1)] += max(1, int(_op(view, node).get("cycles", 0)))
    return values[0], values[1]


def _op(view: dict[str, Any], node: int) -> dict[str, Any]:
    return view["_ops"][int(node)]


def canonical_plan(plan: dict[str, Any], graph_or_view: dict[str, Any]) -> dict[str, Any]:
    groups: dict[int, list[int]] = defaultdict(list)
    for node, group in plan["node_to_subgraph"].items():
        groups[int(group)].append(int(node))
    ordered = sorted((sorted(nodes) for nodes in groups.values()), key=lambda nodes: (min(nodes), len(nodes)))
    remap = {old: index for index, nodes in enumerate(ordered) for old in [next(group for group, values in groups.items() if sorted(values) == nodes)]}
    mapping = {str(node): remap[int(group)] for node, group in plan["node_to_subgraph"].items()}
    schedules = []
    for sequence in plan["core_schedules"]:
        values = [remap[int(group)] for group in sequence if int(group) in remap]
        schedules.append(sorted(dict.fromkeys(values), key=lambda group: min(int(node) for node, mapped in mapping.items() if mapped == group)))
    # Keep a stable integer mapping internally; the official JSON writer accepts either.
    return {"node_to_subgraph": {int(node): int(group) for node, group in mapping.items()}, "core_schedules": schedules}


def _chunks(order: list[int], target: int, view: dict[str, Any]) -> list[list[int]]:
    if not order:
        return []
    count = max(1, min(len(order), int(target)))
    total = sum(max(1, int(_op(view, node).get("cycles", 0))) for node in order)
    chunks: list[list[int]] = []
    start = 0
    remaining_total, remaining_chunks = total, count
    for index in range(count - 1):
        target_load = remaining_total / remaining_chunks
        current: list[int] = []
        load = 0
        while start < len(order) - (remaining_chunks - 1):
            weight = max(1, int(_op(view, order[start]).get("cycles", 0)))
            if current and abs(load + weight - target_load) > abs(load - target_load):
                break
            current.append(order[start]); start += 1; load += weight
        if not current:
            current.append(order[start]); start += 1; load = max(1, int(_op(view, current[0]).get("cycles", 0)))
        chunks.append(current)
        remaining_total -= load
        remaining_chunks -= 1
    chunks.append(order[start:])
    return [chunk for chunk in chunks if chunk]


def _make_plan(chunks: list[list[int]], cores: int, view: dict[str, Any], *, packed: bool = False) -> dict[str, Any]:
    mapping = {node: group for group, chunk in enumerate(chunks) for node in chunk}
    loads = [0] * cores
    schedules = [[] for _ in range(cores)]
    for group, chunk in enumerate(chunks):
        m, v = _weight(view, chunk)
        core = min(range(cores), key=lambda k: (max(loads[k], m), max(loads[k], v), loads[k], k))
        schedules[core].append(group)
        loads[core] += max(m, v)
    if packed and chunks:
        # A1/B1 use at most one component block per core; the caller already
        # sorted components by descending weight.
        schedules = [[] for _ in range(cores)]
        for group in range(len(chunks)):
            schedules[min(group, cores - 1)].append(group)
    return canonical_plan({"node_to_subgraph": mapping, "core_schedules": schedules}, view)


def _component_seed(view: dict[str, Any], cores: int) -> dict[str, Any]:
    components = [list(component) for component in view["components"]]
    components.sort(key=lambda nodes: (-max(_weight(view, nodes)), min(nodes)))
    buckets = [[] for _ in range(cores)]
    loads = [0] * cores
    for component in components:
        m, v = _weight(view, component)
        core = min(range(cores), key=lambda k: (max(loads[k] + m, loads[k] + v), loads[k], k))
        buckets[core].extend(component)
        loads[core] += max(m, v)
    chunks = [nodes for nodes in buckets if nodes]
    # Components are independent; use one subgraph per core bucket.
    return _make_plan(chunks, cores, view, packed=True)


def build_seed(view: dict[str, Any], cores: int, seed: str) -> dict[str, Any]:
    seed = seed.upper()
    if seed.endswith("0"):
        order = list(view["topological_order"])
        return _make_plan([order] if order else [], cores, view, packed=True)
    if seed.endswith("1"):
        return _component_seed(view, cores)
    if seed == "A2":
        order, count = view["d_order"], 2 * cores
    elif seed in {"A3", "B2"}:
        order, count = view["h_order"], 4 * cores
    elif seed == "B3":
        order, count = view["r_order"], 8 * cores
    else:
        raise ValueError(f"unknown V0.7.1 seed: {seed}")
    return _make_plan(_chunks(order, count, view), cores, view)


def build_seed_set(view: dict[str, Any], cores: int, scene: str) -> dict[str, dict[str, Any]]:
    names = [f"{scene}0", f"{scene}1", "A2", "A3"] if scene == "A" else ["B0", "B1", "B2", "B3"]
    return {name: build_seed(view, cores, name) for name in names}
