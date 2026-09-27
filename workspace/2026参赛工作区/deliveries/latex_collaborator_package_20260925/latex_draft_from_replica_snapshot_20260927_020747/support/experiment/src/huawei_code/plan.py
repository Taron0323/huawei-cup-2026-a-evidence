"""Submitted plan construction and validation for the fresh solver."""

from __future__ import annotations

from collections import defaultdict
import copy
import hashlib
import json
from typing import Any

from .graph import static_view, topological


def plan_key(plan: dict[str, Any]) -> str:
    payload = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def pad_plan_cores(plan: dict[str, Any], cores: int) -> dict[str, Any]:
    """Return ``plan`` represented on ``cores`` cores by appending empty cores.

    A plan found with fewer cores remains a valid candidate when the hardware
    exposes more cores: the additional cores may be left idle.  The helper
    copies the plan so incumbent bookkeeping never mutates a previously
    evaluated plan.  It deliberately does not contract or reorder any group.
    """
    schedules = plan["core_schedules"]
    if len(schedules) > cores:
        raise ValueError("cannot pad a plan to fewer cores")
    padded = copy.deepcopy(plan)
    padded["core_schedules"] = [list(sequence) for sequence in schedules]
    padded["core_schedules"].extend([[] for _ in range(cores - len(schedules))])
    return padded


def canonical_plan(mapping: dict[int, int], schedules: list[list[int]]) -> dict[str, Any]:
    """Renumber subgraphs while preserving every core's relative order."""
    first = {}
    for core, sequence in enumerate(schedules):
        for position, group in enumerate(sequence):
            first.setdefault(int(group), (core, position))
    ordered = sorted(first, key=lambda group: first[group])
    remap = {old: new for new, old in enumerate(ordered)}
    return {
        "node_to_subgraph": {int(node): remap[int(group)] for node, group in mapping.items()},
        "core_schedules": [[remap[int(group)] for group in sequence] for sequence in schedules],
    }


def validate_plan(view: dict[str, Any], plan: dict[str, Any], cores: int, scene: str = "A") -> None:
    scene = scene.upper()
    mapping = {int(node): int(group) for node, group in plan["node_to_subgraph"].items()}
    if set(mapping) != set(map(int, view["nodes"])):
        raise ValueError("plan does not cover exactly all compute operations")
    schedules = plan["core_schedules"]
    if len(schedules) != cores:
        raise ValueError("core_schedules length mismatch")
    flat = [int(group) for sequence in schedules for group in sequence]
    if len(flat) != len(set(flat)) or set(flat) != set(mapping.values()):
        raise ValueError("each nonempty subgraph must occur exactly once")
    positions = {(int(group), pos): core for core, sequence in enumerate(schedules) for pos, group in enumerate(sequence)}
    group_core = {group: core for (group, _), core in positions.items()}
    preds = {int(k): set(map(int, v)) for k, v in view["preds"].items()}
    succs = {int(k): set(map(int, v)) for k, v in view["succs"].items()}
    group_nodes = defaultdict(set)
    for node, group in mapping.items():
        group_nodes[group].add(node)
    group_preds = {group: set() for group in group_nodes}
    group_succs = {group: set() for group in group_nodes}
    for source, targets in succs.items():
        for target in targets:
            gs, gt = mapping[source], mapping[target]
            if gs != gt:
                group_succs[gs].add(gt)
                group_preds[gt].add(gs)
    if scene == "A":
        # Scene A's task-order edges are part of the submitted execution
        # graph.  Checking them catches cycles that the contracted data graph
        # alone cannot see.  B/C defer expanded operation/FIFO legality to the
        # official evaluator.
        for core, sequence in enumerate(schedules):
            for source, target in zip(sequence, sequence[1:]):
                group_succs[int(source)].add(int(target))
                group_preds[int(target)].add(int(source))
        topological(group_nodes, group_preds, group_succs)
    for core, sequence in enumerate(schedules):
        order = {int(group): i for i, group in enumerate(sequence)}
        for group in sequence:
            if group_core[int(group)] != core:
                raise ValueError("invalid core schedule")
        if scene == "A":
            for source, targets in group_succs.items():
                for target in targets:
                    if group_core[source] == core == group_core[target] and order[source] >= order[target]:
                        raise ValueError("same-core schedule violates contracted dependency")


def groups_from_plan(plan: dict[str, Any]) -> list[tuple[list[int], int]]:
    groups = defaultdict(list)
    for node, group in plan["node_to_subgraph"].items():
        groups[int(group)].append(int(node))
    core_of = {int(group): core for core, sequence in enumerate(plan["core_schedules"]) for group in sequence}
    return [(sorted(nodes), core_of[group]) for group, nodes in sorted(groups.items())]


def _weighted(view, nodes):
    return sum(max(1, int(view["ops"][str(node)].get("cycles", 0))) for node in nodes)


def _make_plan(chunks, cores, view, scene: str = "A"):
    mapping = {node: group for group, chunk in enumerate(chunks) for node in chunk}
    loads = [0] * cores
    schedules = [[] for _ in range(cores)]
    for group, chunk in enumerate(chunks):
        core = min(range(cores), key=lambda k: (loads[k], k))
        schedules[core].append(group)
        loads[core] += _weighted(view, chunk)
    plan = canonical_plan(mapping, schedules)
    validate_plan(view, plan, cores, scene)
    return plan


def seed_plans(view: dict[str, Any], cores: int, scene: str) -> dict[str, dict[str, Any]]:
    scene = scene.upper()
    if scene == "A":
        names = ["A0", "A1", "A2", "A3"]
    else:
        names = ["B0", "B1", "B2", "B3"]
    result = {}
    components = [list(x) for x in view["components"]]
    buckets = [[] for _ in range(cores)]
    loads = [0] * cores
    for component in components:
        core = min(range(cores), key=lambda k: (loads[k], k))
        buckets[core].extend(component)
        loads[core] += _weighted(view, component)
    result[f"{scene}0"] = _make_plan([view["topological"]], cores, view, scene)
    result[f"{scene}1"] = _make_plan([x for x in buckets if x], cores, view, scene)
    order = view["d_order"] if scene == "A" else view["h_order"]
    for name, count, order_name in ((f"{scene}2", 2 * cores, "d" if scene == "A" else "h"), (f"{scene}3", 4 * cores, "h" if scene == "A" else "r")):
        order = view[f"{order_name}_order"]
        count = min(count, len(order))
        chunks = []
        start = 0
        for i in range(count):
            remaining = count - i
            take = max(1, (len(order) - start + remaining - 1) // remaining)
            chunks.append(order[start:start + take])
            start += take
        result[name] = _make_plan(chunks, cores, view, scene)
    return result


def mutate_plan(view, plan, cores, mode, scene: str = "A"):
    groups = groups_from_plan(plan)
    if mode == "merge":
        for i in range(len(groups) - 1):
            if groups[i][1] == groups[i + 1][1]:
                nodes = groups[i][0] + groups[i + 1][0]
                return _make_plan([nodes if j == i else g[0] for j, g in enumerate(groups) if j not in {i, i + 1}] , cores, view, scene)
    if mode == "move" and groups:
        nodes, source = groups[0]
        target = (source + 1) % cores
        schedules = [list(x) for x in plan["core_schedules"]]
        group = next(g for g, (ns, c) in enumerate(groups) if c == source and ns == nodes)
        old_group = int(plan["core_schedules"][source][0])
        schedules[source].remove(old_group)
        schedules[target].append(old_group)
        candidate = canonical_plan({int(k): int(v) for k, v in plan["node_to_subgraph"].items()}, schedules)
        validate_plan(view, candidate, cores, scene)
        return candidate
    return plan
