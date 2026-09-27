#!/usr/bin/env python3
"""Deterministic baseline and load-balanced solver for Huawei Cup 2026 A.

The official evaluator remains the authority for all timing and movement metrics.
This module only creates plans and calls the supplied evaluator functions.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_CODE = WORKSPACE / "inputs/raw/A题/附件/code"
DATA_ROOT = WORKSPACE / "inputs/raw/A题/附件/data"
sys.path.insert(0, str(RAW_CODE))
sys.dont_write_bytecode = True

from evaluation_validation import read_evaluation_config  # type: ignore  # noqa: E402
from multicore_cut_evaluate_problem_1 import (  # type: ignore  # noqa: E402
    evaluate_scene_a,
    read_scene_a_config,
)
from multicore_cut_evaluate_problem_2 import (  # type: ignore  # noqa: E402
    evaluate_scene_b,
    read_scene_b_config,
)
from multicore_cut_evaluate_problem_3 import (  # type: ignore  # noqa: E402
    evaluate_problem_3,
    read_cache_config,
)
from stub_multicore_cut_and_schedule import (  # type: ignore  # noqa: E402
    _build_op_adjacency,
    _contract_excluded_copy_nodes,
    generate_multicore_plan,
)


CONFIG_PATH = DATA_ROOT / "config.txt"


def load_graph(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def op_dependencies(graph: dict[str, Any]) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    op_ids = sorted(
        int(op["id"])
        for op in graph.get("ops", [])
        if op.get("op") not in {"COPY_IN", "COPY_OUT"}
    )
    _, succs = _build_op_adjacency(graph)
    _, contracted_succs = _contract_excluded_copy_nodes(op_ids, succs)
    eligible = set(op_ids)
    preds = {node: set() for node in op_ids}
    for source in op_ids:
        for target in contracted_succs[source]:
            if target in preds:
                preds[target].add(source)
    return preds, {node: set(contracted_succs[node]) & eligible for node in op_ids}


def topological_order(graph: dict[str, Any]) -> list[int]:
    preds, succs = op_dependencies(graph)
    indegree = {node: len(values) for node, values in preds.items()}
    ready = sorted(node for node, degree in indegree.items() if degree == 0)
    order: list[int] = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for target in sorted(succs[node]):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, target)
    if len(order) != len(indegree):
        raise ValueError("eligible operation graph is cyclic")
    return order


def topological_order_subset(nodes: set[int], preds: dict[int, set[int]], succs: dict[int, set[int]]) -> list[int]:
    indegree = {node: len(preds[node] & nodes) for node in nodes}
    ready = sorted(node for node, degree in indegree.items() if degree == 0)
    order: list[int] = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for target in sorted(succs[node] & nodes):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, target)
    if len(order) != len(nodes):
        raise ValueError("component operation graph is cyclic")
    return order


def component_aware_plan(graph: dict[str, Any], num_cores: int) -> dict[str, Any]:
    preds, succs = op_dependencies(graph)
    op_by_id = {int(op["id"]): op for op in graph.get("ops", [])}
    remaining = set(preds)
    components: list[set[int]] = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        stack = [seed]
        component = {seed}
        while stack:
            node = stack.pop()
            neighbours = (preds[node] | succs[node]) & remaining
            if neighbours:
                remaining.difference_update(neighbours)
                component.update(neighbours)
                stack.extend(sorted(neighbours))
        components.append(component)

    def component_weight(nodes: set[int]) -> float:
        return sum(max(1.0, float(op_by_id[node].get("cycles", 0))) for node in nodes)

    components.sort(key=lambda nodes: (-component_weight(nodes), min(nodes)))
    block_size = max(50, min(100, math.ceil(len(preds) / max(1, 2 * num_cores))))
    loads = [0.0] * num_cores
    schedules = [[] for _ in range(num_cores)]
    mapping: dict[int, int] = {}
    next_subgraph = 0
    for component in components:
        order = topological_order_subset(component, preds, succs)
        chunks = [order[start:start + block_size] for start in range(0, len(order), block_size)]
        component_weight_value = component_weight(component)
        # Small independent components stay together. This avoids creating
        # artificial cross-core transfers at a component boundary.
        if len(component) <= block_size * 2:
            core = min(range(num_cores), key=lambda index: (loads[index], index))
            target_cores = [core] * len(chunks)
        else:
            target_cores = []
            for chunk in chunks:
                core = min(range(num_cores), key=lambda index: (loads[index], index))
                target_cores.append(core)
        for chunk, core in zip(chunks, target_cores):
            subgraph = next_subgraph
            next_subgraph += 1
            for node in chunk:
                mapping[node] = subgraph
            schedules[core].append(subgraph)
            chunk_weight = sum(max(1.0, float(op_by_id[node].get("cycles", 0))) for node in chunk)
            loads[core] += chunk_weight
        if len(component) <= block_size * 2 and target_cores:
            # Keep the full component weight visible in the next assignment;
            # the per-chunk updates above already sum to this value.
            loads[target_cores[0]] = max(loads[target_cores[0]], component_weight_value)
    for schedule in schedules:
        schedule.sort()
    return {"node_to_subgraph": mapping, "core_schedules": schedules}


def subgraph_weights(graph: dict[str, Any], plan: dict[str, Any]) -> dict[int, float]:
    op_by_id = {int(op["id"]): op for op in graph.get("ops", [])}
    weights: dict[int, float] = {}
    for node_id, subgraph in plan["node_to_subgraph"].items():
        node = op_by_id[int(node_id)]
        # Cycles dominate. A small transfer proxy discourages very uneven
        # partitions without attempting to replace the official evaluator.
        weights[int(subgraph)] = weights.get(int(subgraph), 0.0) + max(1.0, float(node.get("cycles", 0)))
    return weights


def rebalance_plan(graph: dict[str, Any], plan: dict[str, Any], num_cores: int, policy: str) -> dict[str, Any]:
    subgraphs = sorted({int(value) for value in plan["node_to_subgraph"].values()})
    weights = subgraph_weights(graph, plan)
    schedules = [[] for _ in range(num_cores)]
    if not subgraphs:
        return {"node_to_subgraph": plan["node_to_subgraph"], "core_schedules": schedules}
    if policy == "random":
        return {"node_to_subgraph": plan["node_to_subgraph"], "core_schedules": plan["core_schedules"]}
    if policy == "greedy":
        loads = [0.0] * num_cores
        for subgraph in subgraphs:
            core = min(range(num_cores), key=lambda index: (loads[index], index))
            schedules[core].append(subgraph)
            loads[core] += weights.get(subgraph, 1.0)
    elif policy == "contiguous":
        total = sum(weights.get(subgraph, 1.0) for subgraph in subgraphs)
        target = total / num_cores
        core = 0
        current = 0.0
        remaining = len(subgraphs)
        for subgraph in subgraphs:
            must_leave_core = remaining <= num_cores - core - 1
            if core < num_cores - 1 and current > 0 and current + weights.get(subgraph, 1.0) > target and not must_leave_core:
                core += 1
                current = 0.0
            schedules[core].append(subgraph)
            current += weights.get(subgraph, 1.0)
            remaining -= 1
    else:
        raise ValueError(f"unknown plan policy: {policy}")
    return {"node_to_subgraph": plan["node_to_subgraph"], "core_schedules": schedules}


def component_packed_plan(graph: dict[str, Any], num_cores: int, block_size: int) -> dict[str, Any]:
    """Pack independent components; split large components in topological order."""
    preds, succs = op_dependencies(graph)
    ops = {int(op["id"]): op for op in graph["ops"]}
    remaining = set(preds)
    components = []
    for seed in sorted(preds):
        if seed not in remaining:
            continue
        remaining.remove(seed)
        component, stack = {seed}, [seed]
        while stack:
            node = stack.pop()
            neighbours = (preds[node] | succs[node]) & remaining
            remaining.difference_update(neighbours)
            component.update(neighbours)
            stack.extend(sorted(neighbours))
        components.append(component)

    def weight(nodes):
        return sum(max(1, ops[node]["cycles"]) for node in nodes)

    components.sort(key=lambda nodes: (-weight(nodes), min(nodes)))
    loads = [0] * num_cores
    schedules = [[] for _ in range(num_cores)]
    groups: list[list[int]] = []
    pending: list[list[int]] = [[] for _ in range(num_cores)]

    def emit(nodes, core):
        schedules[core].append(len(groups))
        groups.append(nodes)

    for component in components:
        order = topological_order_subset(component, preds, succs)
        if len(order) <= block_size:
            core = min(range(num_cores), key=lambda index: (loads[index], index))
            if pending[core] and len(pending[core]) + len(order) > block_size:
                emit(pending[core], core)
                pending[core] = []
            pending[core].extend(order)
            loads[core] += weight(order)
        else:
            for start in range(0, len(order), block_size):
                chunk = order[start:start + block_size]
                core = min(range(num_cores), key=lambda index: (loads[index], index))
                emit(chunk, core)
                loads[core] += weight(chunk)
    for core, nodes in enumerate(pending):
        if nodes:
            emit(nodes, core)
    return {
        "node_to_subgraph": {node: sg for sg, nodes in enumerate(groups) for node in nodes},
        "core_schedules": schedules,
    }


def make_plan(graph: dict[str, Any], num_cores: int, algorithm: str,
              seed: int = 0, block_size: int = 100) -> dict[str, Any]:
    if not 1 <= num_cores <= 5 or block_size < 1:
        raise ValueError("cores must be 1..5 and block_size must be positive")
    eligible_count = sum(
        op.get("op") not in {"COPY_IN", "COPY_OUT"} for op in graph.get("ops", [])
    )
    if algorithm == "random_stub":
        return generate_multicore_plan(graph, num_cores=num_cores, seed=seed, min_subgraph_size=50, max_subgraph_size=100)
    if algorithm == "singlecore":
        return {"node_to_subgraph": {int(op["id"]): 0 for op in graph["ops"]
                                      if op["op"] not in {"COPY_IN", "COPY_OUT"}},
                "core_schedules": [[0] if eligible_count else []] + [[] for _ in range(num_cores - 1)]}
    if algorithm == "component_packed":
        return component_packed_plan(graph, num_cores, block_size)
    if algorithm == "component_aware":
        return component_aware_plan(graph, num_cores)
    # Keep enough subgraphs for parallel work while avoiding thousands of tiny
    # tasks. The range is deliberately deterministic and data-size aware.
    block_size = max(50, min(100, math.ceil(eligible_count / max(1, 2 * num_cores))))
    order = topological_order(graph)
    mapping = {
        node_id: index // block_size
        for index, node_id in enumerate(order)
    }
    base = {
        "node_to_subgraph": mapping,
        "core_schedules": [list(sorted(set(mapping.values())))],
    }
    policy = {"balanced_contiguous": "contiguous", "balanced_greedy": "greedy"}.get(algorithm)
    if policy is None:
        raise ValueError(f"unknown algorithm: {algorithm}")
    return rebalance_plan(graph, base, num_cores, policy)


def evaluate(graph: dict[str, Any], plan: dict[str, Any], problem: int) -> dict[str, Any]:
    settings = read_evaluation_config(str(CONFIG_PATH))
    capacity = settings["capacity"]
    bandwidth = settings["bandwidth"]
    if problem == 1:
        waits = read_scene_a_config(str(CONFIG_PATH))
        return evaluate_scene_a(
            graph,
            plan,
            bandwidth=bandwidth,
            capacity=capacity,
            cross_core_wait=waits["task_cross_core_wait_cycles"],
            same_core_wait=waits["task_same_core_wait_cycles"],
        )
    scene = read_scene_b_config(str(CONFIG_PATH))
    if problem == 2:
        return evaluate_scene_b(
            graph,
            plan,
            bandwidth=bandwidth,
            capacity=capacity,
            cross_core_copy_delay=scene["cross_core_copy_delay_cycles"],
        )
    if problem == 3:
        cache = read_cache_config(str(CONFIG_PATH))
        return evaluate_problem_3(
            graph,
            plan,
            bandwidth=bandwidth,
            capacity=capacity,
            cross_core_copy_delay=scene["cross_core_copy_delay_cycles"],
            **cache,
        )
    raise ValueError(f"unknown problem: {problem}")


def metric_row(case: str, cores: int, algorithm: str, problem: int, result: dict[str, Any], elapsed: float) -> dict[str, Any]:
    movement = result.get("data_movement_bytes", {})
    cache = result.get("cache_stats") or {}
    return {
        "case": case,
        "cores": cores,
        "algorithm": algorithm,
        "problem": problem,
        "makespan": result.get("makespan"),
        "added_copy_bytes": movement.get("added_copy_bytes"),
        "scheduled_copy_bytes": movement.get("scheduled_copy_bytes"),
        "cache_hit_rate": cache.get("hit_rate", ""),
        "cache_hits": cache.get("hits", ""),
        "cache_accesses": cache.get("accesses", ""),
        "elapsed_seconds": round(elapsed, 6),
    }


def run_one(task: tuple[str, int, str, tuple[int, ...], str]) -> tuple[list[dict[str, Any]], list[tuple[str, dict[str, Any], dict[str, Any]]]]:
    case, cores, algorithm, problems, output_root = task
    graph_path = DATA_ROOT / f"{case}.json"
    graph = load_graph(graph_path)
    plan = make_plan(graph, cores, algorithm)
    output_dir = Path(output_root) / "runs" / algorithm / case / f"{cores}core"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows: list[dict[str, Any]] = []
    artifacts: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for problem in problems:
        started = time.perf_counter()
        result = evaluate(graph, plan, problem)
        elapsed = time.perf_counter() - started
        result_path = output_dir / f"problem{problem}.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rows.append(metric_row(case, cores, algorithm, problem, result, elapsed))
        artifacts.append((str(result_path), plan, result))
    return rows, artifacts


def write_metrics(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case", "cores", "algorithm", "problem", "makespan", "added_copy_bytes",
        "scheduled_copy_bytes", "cache_hit_rate", "cache_hits", "cache_accesses", "elapsed_seconds",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["problem"], row["cores"], row["case"], row["algorithm"])))


def parse_cases(raw: str | None) -> list[str]:
    if raw:
        return [item if item.startswith("case_") else f"case_{int(item):03d}" for item in raw.split(",")]
    return [path.stem for path in sorted(DATA_ROOT.glob("case_*.json"))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cases")
    parser.add_argument("--cores", default="2,3,4,5")
    parser.add_argument("--algorithms", default="balanced_contiguous")
    parser.add_argument("--problems", default="1,2,3")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    cases = parse_cases(args.cases)
    cores = tuple(int(value) for value in args.cores.split(","))
    algorithms = tuple(args.algorithms.split(","))
    problems = tuple(int(value) for value in args.problems.split(","))
    tasks = [
        (case, core, algorithm, problems, str(args.output_root.resolve()))
        for case in cases
        for core in cores
        for algorithm in algorithms
    ]
    rows: list[dict[str, Any]] = []
    started = time.time()
    if args.workers <= 1:
        for task in tasks:
            task_rows, _ = run_one(task)
            rows.extend(task_rows)
            print(json.dumps({"case": task[0], "cores": task[1], "algorithm": task[2], "rows": task_rows}, ensure_ascii=False), flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_one, task): task for task in tasks}
            for future in as_completed(futures):
                task = futures[future]
                task_rows, _ = future.result()
                rows.extend(task_rows)
                print(json.dumps({"case": task[0], "cores": task[1], "algorithm": task[2], "rows": task_rows}, ensure_ascii=False), flush=True)
    write_metrics(rows, args.output_root / "metrics.csv")
    summary = {
        "cases": cases,
        "cores": cores,
        "algorithms": algorithms,
        "problems": problems,
        "rows": len(rows),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    (args.output_root / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
