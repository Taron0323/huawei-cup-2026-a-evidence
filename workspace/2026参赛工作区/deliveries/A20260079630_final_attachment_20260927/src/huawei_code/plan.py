# 人工智能工具辅助编程声明：本程序及代码在人工智能工具辅助下完成。
# 工具名称：OpenAI Codex；版本/型号：GPT-6 系列（准确会话型号以平台记录为准）；
# 开发机构：OpenAI；版本发布日期：以实际平台记录为准。
# 队员已对算法、参数、输入输出和官方评估结果进行人工核对，并保留后处理记录。

"""Submitted plan construction and validation for the fresh solver."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from typing import Any

from .graph import static_view, topological


def plan_key(plan: dict[str, Any]) -> str:
    normalized = {
        "node_to_subgraph": {str(int(node)): int(group) for node, group in plan["node_to_subgraph"].items()},
        "core_schedules": [[int(group) for group in sequence] for sequence in plan["core_schedules"]],
    }
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def canonical_plan(mapping: dict[int, int], schedules: list[list[int]]) -> dict[str, Any]:
    """Number subgraphs by their smallest operation id, preserving core order."""
    first = {}
    for node, group in mapping.items():
        first[int(group)] = min(first.get(int(group), int(node)), int(node))
    ordered = sorted(first, key=lambda group: (first[group], group))
    remap = {old: new for new, old in enumerate(ordered)}
    return {
        "node_to_subgraph": {int(node): remap[int(group)] for node, group in mapping.items()},
        "core_schedules": [[remap[int(group)] for group in sequence] for sequence in schedules],
    }


def extend_plan_with_empty_cores(view: dict[str, Any], plan: dict[str, Any], cores: int) -> dict[str, Any]:
    """Embed a feasible lower-core plan in a larger configuration.

    The problem permits idle cores.  Keeping the previous schedule as an
    incumbent therefore gives every higher-core run a feasible fallback while
    leaving the operation-to-subgraph mapping and all existing orderings intact.
    """
    schedules = [list(sequence) for sequence in plan["core_schedules"]]
    if len(schedules) > cores:
        raise ValueError("cannot embed a plan into fewer cores")
    schedules.extend([[] for _ in range(cores - len(schedules))])
    candidate = canonical_plan(
        {int(node): int(group) for node, group in plan["node_to_subgraph"].items()},
        schedules,
    )
    validate_plan(view, candidate, cores)
    return candidate


def validate_plan(view: dict[str, Any], plan: dict[str, Any], cores: int) -> None:
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
    topological(group_nodes, group_preds, group_succs)
    for core, sequence in enumerate(schedules):
        order = {int(group): i for i, group in enumerate(sequence)}
        for group in sequence:
            if group_core[int(group)] != core:
                raise ValueError("invalid core schedule")
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


def _pipe_work(view, nodes):
    work = [0, 0]
    for node in nodes:
        op = view["ops"][str(node)]
        work[0 if op["pipe"] == "PIPE_M" else 1] += max(1, int(op.get("cycles", 0)))
    return work


def _cut_bytes(view, order):
    position = {int(node): index for index, node in enumerate(order)}
    changes = [0] * (len(order) + 1)
    for tid, size in view["tensor_sizes"].items():
        related = [position[int(node)] for node in list(view["tensor_producers"].get(tid, ())) + list(view["tensor_consumers"].get(tid, ())) if int(node) in position]
        if len(related) < 2:
            continue
        left, right = min(related), max(related)
        changes[left + 1] += int(size)
        changes[right + 1] -= int(size)
    crossing = [0] * (len(order) + 1)
    for index in range(1, len(order)):
        crossing[index] = crossing[index - 1] + changes[index]
    return crossing


def _split_order(view, order, count):
    count = min(count, len(order))
    prefix = [[0], [0]]
    for node in order:
        work = _pipe_work(view, [node])
        for pipe in range(2):
            prefix[pipe].append(prefix[pipe][-1] + work[pipe])
    crossing = _cut_bytes(view, order)
    chunks = []
    start = 0
    for chunk_index in range(count - 1):
        remaining = count - chunk_index
        latest = len(order) - remaining + 1
        target = max(prefix[0][-1] - prefix[0][start], prefix[1][-1] - prefix[1][start]) / remaining
        options = []
        for end in range(start + 1, latest + 1):
            work = max(prefix[0][end] - prefix[0][start], prefix[1][end] - prefix[1][start])
            options.append((end, work))
        near = [(end, work) for end, work in options if abs(work - target) <= target * .1]
        end = min(near, key=lambda item: (crossing[item[0]], abs(item[1] - target), item[0]))[0] if near else min(options, key=lambda item: (abs(item[1] - target), item[0]))[0]
        chunks.append(order[start:end])
        start = end
    chunks.append(order[start:])
    return chunks


def _make_plan(chunks, cores, view, scene=None, config=None):
    mapping = {}
    schedules = [[] for _ in range(cores)]
    loads = [0] * cores
    for group, chunk in enumerate(chunks):
        for node in chunk:
            mapping[int(node)] = group
        if config is None:
            core = min(range(cores), key=lambda k: (loads[k], k))
        else:
            from .scoring import light_score
            core = min(range(cores), key=lambda k: (
                tuple(light_score(view, canonical_plan(mapping, [sequence + ([group] if index == k else []) for index, sequence in enumerate(schedules)]), scene, config)["score"]), k
            ))
        schedules[core].append(group)
        loads[core] += _weighted(view, chunk)
    plan = canonical_plan(mapping, schedules)
    validate_plan(view, plan, cores)
    return plan


def seed_plans(view: dict[str, Any], cores: int, scene: str, config=None) -> dict[str, dict[str, Any]]:
    scene = scene.upper()
    if scene == "A":
        names = ["A0", "A1", "A2", "A3"]
    else:
        names = ["B0", "B1", "B2", "B3"]
    result = {}
    components = [list(x) for x in view["components"]]
    buckets = [[] for _ in range(cores)]
    loads = [0] * cores
    pipe_loads = [[0, 0] for _ in range(cores)]
    for component in sorted(components, key=lambda nodes: (-max(_pipe_work(view, nodes)), min(nodes))):
        work = _pipe_work(view, component)
        core = min(range(cores), key=lambda k: (max(pipe_loads[k][0] + work[0], pipe_loads[k][1] + work[1], *(max(pipe_loads[j]) for j in range(cores) if j != k)), k))
        buckets[core].extend(component)
        loads[core] += _weighted(view, component)
        pipe_loads[core][0] += work[0]
        pipe_loads[core][1] += work[1]
    result[f"{scene}0"] = _make_plan([view["d_order"]], cores, view)
    bucket_mapping = {int(node): core for core, nodes in enumerate(buckets) for node in nodes}
    result[f"{scene}1"] = canonical_plan(bucket_mapping, [[core] if nodes else [] for core, nodes in enumerate(buckets)])
    validate_plan(view, result[f"{scene}1"], cores)
    for name, count, order_name in ((f"{scene}2", 2 * cores if scene == "A" else 4 * cores, "d" if scene == "A" else "h"), (f"{scene}3", 4 * cores if scene == "A" else 8 * cores, "h" if scene == "A" else "r")):
        order = view[f"{order_name}_order"]
        result[name] = _make_plan(_split_order(view, order, count), cores, view, scene, config)
    return result


def legacy_seed_plans(view: dict[str, Any], cores: int, scene: str) -> dict[str, dict[str, Any]]:
    """Rebuild the earlier deterministic starts for profile-level comparison."""
    def legacy_plan(chunks):
        mapping = {int(node): group for group, chunk in enumerate(chunks) for node in chunk}
        loads = [0] * cores
        schedules = [[] for _ in range(cores)]
        for group, chunk in enumerate(chunks):
            core = min(range(cores), key=lambda index: (loads[index], index))
            schedules[core].append(group)
            loads[core] += _weighted(view, chunk)
        first = {int(group): (core, position) for core, sequence in enumerate(schedules) for position, group in enumerate(sequence)}
        remap = {group: index for index, group in enumerate(sorted(first, key=first.get))}
        plan = {
            "node_to_subgraph": {node: remap[group] for node, group in mapping.items()},
            "core_schedules": [[remap[group] for group in sequence] for sequence in schedules],
        }
        validate_plan(view, plan, cores)
        return plan

    components = [list(nodes) for nodes in view["components"]]
    buckets = [[] for _ in range(cores)]
    loads = [0] * cores
    for component in components:
        core = min(range(cores), key=lambda index: (loads[index], index))
        buckets[core].extend(component)
        loads[core] += _weighted(view, component)
    result = {"L0": legacy_plan([view["topological"]]), "L1": legacy_plan([nodes for nodes in buckets if nodes])}
    for name, count, order_name in (("L2", 2 * cores, "d" if scene == "A" else "h"), ("L3", 4 * cores, "h" if scene == "A" else "r")):
        order = view[f"{order_name}_order"]
        count = min(count, len(order))
        chunks = []
        start = 0
        for index in range(count):
            remaining = count - index
            take = max(1, (len(order) - start + remaining - 1) // remaining)
            chunks.append(order[start:start + take])
            start += take
        result[name] = legacy_plan(chunks)
    return result


def mutate_plan(view, plan, cores, mode):
    groups = groups_from_plan(plan)
    if mode == "merge":
        for i in range(len(groups) - 1):
            if groups[i][1] == groups[i + 1][1]:
                nodes = groups[i][0] + groups[i + 1][0]
                return _make_plan([nodes if j == i else g[0] for j, g in enumerate(groups) if j not in {i, i + 1}] , cores, view)
    if mode == "move" and groups:
        nodes, source = groups[0]
        target = (source + 1) % cores
        schedules = [list(x) for x in plan["core_schedules"]]
        group = next(g for g, (ns, c) in enumerate(groups) if c == source and ns == nodes)
        old_group = int(plan["core_schedules"][source][0])
        schedules[source].remove(old_group)
        schedules[target].append(old_group)
        candidate = canonical_plan({int(k): int(v) for k, v in plan["node_to_subgraph"].items()}, schedules)
        validate_plan(view, candidate, cores)
        return candidate
    return plan
