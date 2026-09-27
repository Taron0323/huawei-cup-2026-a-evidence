#!/usr/bin/env python3
"""Measure DAG span and available width without invoking the event evaluator."""

from __future__ import annotations

import argparse
import csv
import heapq
import json
from collections import Counter
from pathlib import Path


def measure(path: Path) -> dict[str, int | float | str]:
    graph = json.loads(path.read_text(encoding="utf-8"))
    ops = {int(op["id"]): op for op in graph["ops"] if op.get("op") not in {"COPY_IN", "COPY_OUT"}}
    tensors = {int(tensor["id"]) for tensor in graph["tensors"]}
    producers: dict[int, set[int]] = {tensor: set() for tensor in tensors}
    consumers: dict[int, set[int]] = {tensor: set() for tensor in tensors}
    for edge in graph["edges"]:
        source, target = int(edge["source"]), int(edge["target"])
        if source in ops and target in tensors:
            producers[target].add(source)
        elif source in tensors and target in ops:
            consumers[source].add(target)
    preds = {node: set() for node in ops}
    succs = {node: set() for node in ops}
    for tensor in tensors:
        for parent in producers[tensor]:
            for child in consumers[tensor]:
                if parent != child:
                    preds[child].add(parent)
                    succs[parent].add(child)

    indegree = {node: len(parents) for node, parents in preds.items()}
    ready = [node for node, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    span_end: dict[int, int] = {}
    level: dict[int, int] = {}
    path_ops: dict[int, int] = {}
    while ready:
        node = heapq.heappop(ready)
        parent = max(preds[node], key=lambda item: (span_end[item], -item)) if preds[node] else None
        cycles = max(1, int(ops[node].get("cycles", 0)))
        span_end[node] = cycles + (span_end[parent] if parent is not None else 0)
        path_ops[node] = 1 + (path_ops[parent] if parent is not None else 0)
        level[node] = 1 + max((level[parent] for parent in preds[node]), default=0)
        for child in sorted(succs[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(span_end) != len(ops):
        raise ValueError(f"compute DAG is cyclic: {path.name}")

    remaining = set(ops)
    components = []
    while remaining:
        start = next(iter(remaining))
        component = {start}
        stack = [start]
        remaining.remove(start)
        while stack:
            node = stack.pop()
            neighbours = (preds[node] | succs[node]) & remaining
            remaining.difference_update(neighbours)
            component.update(neighbours)
            stack.extend(neighbours)
        components.append(component)
    work = sum(max(1, int(op.get("cycles", 0))) for op in ops.values())
    pipe_work = Counter()
    for op in ops.values():
        pipe_work[str(op.get("pipe", "UNKNOWN"))] += max(1, int(op.get("cycles", 0)))
    span = max(span_end.values(), default=0)
    return {
        "case": path.stem,
        "compute_ops": len(ops),
        "weak_components": len(components),
        "largest_component_ops": max(map(len, components), default=0),
        "total_work_cycles": work,
        "critical_path_cycles": span,
        "critical_path_ops": max(path_ops.values(), default=0),
        "work_over_span": work / span if span else 0,
        "max_topological_level_width": max(Counter(level.values()).values(), default=0),
        "m_pipe_work_cycles": pipe_work["PIPE_M"],
        "v_pipe_work_cycles": pipe_work["PIPE_V"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.data_dir.glob("case_*.json"))
    if len(paths) != 100:
        raise SystemExit(f"expected 100 cases, found {len(paths)}")
    rows = [measure(path) for path in paths]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} graph structure rows to {args.output}")


if __name__ == "__main__":
    main()
