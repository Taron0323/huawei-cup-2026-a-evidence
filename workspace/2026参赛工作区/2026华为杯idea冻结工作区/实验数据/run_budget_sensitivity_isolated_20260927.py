#!/usr/bin/env python3
"""Run an isolated official-evaluation budget trace for six representative graphs.

This file deliberately does not modify the frozen matrix or the solver source.  It
generates candidates with the current v7 source, evaluates a fixed light-score
order up to 20 attempts, and writes cumulative best results at budgets 2/5/10/20.
The output is an evidence package for the reviewer suggestion, not a replacement
for the main matrix.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

SOURCE_ROOT = Path("/Users/futaoran/Desktop/华为杯2026/华为杯_code/solver_review_v7_20260926").resolve()
OUT = Path("/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/budget_sensitivity_20260927_v1").resolve()
DATA = SOURCE_ROOT / "data/raw/A题/data"
EVALUATOR = SOURCE_ROOT / "vendor/official_evaluator"
CASES = ["case_012", "case_016", "case_051", "case_062", "case_067", "case_081"]
CORES = 5
SCENES = ["A", "B", "C"]
BUDGETS = [2, 5, 10, 20]

sys.path.insert(0, str(SOURCE_ROOT / "src"))
from huawei_code.candidates import generate_candidates  # noqa: E402
from huawei_code.graph import load_graph, static_view  # noqa: E402
from huawei_code.official import evaluate, file_sha, load_modules, read_config, summary  # noqa: E402
from huawei_code.plan import plan_key, validate_plan  # noqa: E402


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source_hashes() -> dict[str, str]:
    paths = [SOURCE_ROOT / "scripts/run_experiment.py"]
    paths.extend(sorted((SOURCE_ROOT / "src").rglob("*.py")))
    paths.extend(sorted(EVALUATOR.glob("*.py")))
    return {str(path.relative_to(SOURCE_ROOT)): file_sha(path) for path in paths if path.exists()}


def candidate_order(candidates: list[dict]) -> list[dict]:
    """Place mandatory anchors first, preserving the generated light-score order."""
    mandatory = [item for item in candidates if item.get("mandatory_rank") is not None]
    ordinary = [item for item in candidates if item.get("mandatory_rank") is None]
    mandatory.sort(key=lambda item: (int(item["mandatory_rank"]), item["candidate"]))
    return mandatory + ordinary


def evaluate_cell(graph, view, config, modules, case: str, scene: str, incumbent_plan=None) -> tuple[list[dict], dict]:
    candidates = generate_candidates(
        view,
        CORES,
        scene,
        config,
        base_plan=None,
        incumbent_plan=incumbent_plan if scene == "C" else None,
        lower_core_plan=None,
    )
    ordered = candidate_order(candidates)
    cell_dir = OUT / "cells" / case / f"{CORES}core" / scene
    write_json(cell_dir / "candidate_ledger.json", [
        {k: v for k, v in item.items() if k != "plan"} | {"plan_sha256": plan_key(item["plan"])}
        for item in ordered
    ])
    rows: list[dict] = []
    for index, item in enumerate(ordered[: max(BUDGETS)], start=1):
        candidate_dir = cell_dir / "candidates" / f"{index:02d}_{item['candidate']}"
        write_json(candidate_dir / "plan.json", item["plan"])
        row = {
            "case": case,
            "cores": CORES,
            "scene": scene,
            "order": index,
            "candidate": item["candidate"],
            "source": item.get("source"),
            "mandatory_rank": item.get("mandatory_rank"),
            "plan_sha256": plan_key(item["plan"]),
            "status": "PENDING",
        }
        started = time.perf_counter()
        try:
            validate_plan(view, item["plan"], CORES)
            result = evaluate(graph, item["plan"], {"A": 1, "B": 2, "C": 3}[scene], config, modules)
            elapsed = time.perf_counter() - started
            write_json(candidate_dir / "result.json", result)
            checked = summary(result)
            row.update({"status": "AI_VERIFIED", "evaluation_seconds": elapsed, **checked})
        except Exception as exc:  # retain every failed attempt as budget evidence
            row.update({
                "status": "EVALUATION_FAILED",
                "evaluation_seconds": time.perf_counter() - started,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            write_json(candidate_dir / "failure.json", row)
        rows.append(row)
        with (OUT / "attempts.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps({k: row.get(k) for k in ("case", "scene", "order", "candidate", "status", "evaluation_seconds", "makespan")}, ensure_ascii=False), flush=True)
    metadata = {
        "case": case,
        "cores": CORES,
        "scene": scene,
        "candidate_count": len(ordered),
        "attempt_count": len(rows),
        "verified_count": sum(row["status"] == "AI_VERIFIED" for row in rows),
        "failed_count": sum(row["status"] != "AI_VERIFIED" for row in rows),
        "incumbent_plan_sha256": plan_key(incumbent_plan) if incumbent_plan is not None else None,
    }
    write_json(cell_dir / "cell_manifest.json", metadata)
    return rows, metadata


def cumulative_rows(rows: list[dict], baseline: float | None) -> list[dict]:
    output = []
    valid = []
    for budget in BUDGETS:
        attempted = [row for row in rows if int(row["order"]) <= budget]
        valid = [row for row in attempted if row["status"] == "AI_VERIFIED"]
        best = min(valid, key=lambda row: (int(row["makespan"]), int(row.get("added_copy_bytes", 0)), int(row["order"]))) if valid else None
        output.append({
            "budget": budget,
            "attempted": len(attempted),
            "successful": len(valid),
            "success_rate": len(valid) / len(attempted) if attempted else None,
            "best_candidate": best["candidate"] if best else None,
            "best_order": best["order"] if best else None,
            "best_makespan": best.get("makespan") if best else None,
            "best_added_copy_bytes": best.get("added_copy_bytes") if best else None,
            "best_evaluation_seconds": best.get("evaluation_seconds") if best else None,
            "speedup_vs_baseline": baseline / best["makespan"] if baseline and best else None,
            "cumulative_eval_seconds": sum(float(row.get("evaluation_seconds", 0.0)) for row in attempted),
        })
    return output


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({field for row in rows for field in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing existing output: {OUT}")
    OUT.mkdir(parents=True)
    modules = load_modules(EVALUATOR)
    config = read_config(modules, DATA / "config.txt")
    manifest = {
        "run_id": OUT.name,
        "status": "RUNNING",
        "protocol": "current solver_review_v7 candidate generation; mandatory anchors first, then generated light-score order; fixed 5-core representative cells; cumulative budgets 2/5/10/20",
        "cases": CASES,
        "cores": CORES,
        "scenes": SCENES,
        "budgets": BUDGETS,
        "source_root": str(SOURCE_ROOT),
        "official_evaluator": str(EVALUATOR),
        "source_sha256": source_hashes(),
        "python": sys.version,
        "platform": platform.platform(),
        "started_at": time.time(),
        "limitations": [
            "isolated representative experiment; not a replacement for the 100-graph frozen matrix",
            "candidate generation is fixed before the 20-attempt trace; C uses the B winner at budget 20 as its incumbent",
            "budget curves count all attempts, including evaluator failures, and select the shortest successful Makespan",
            "no manuscript source is modified by this run",
        ],
    }
    write_json(OUT / "run_manifest.json", manifest)
    all_attempts: list[dict] = []
    all_budget: list[dict] = []
    for case in CASES:
        graph = load_graph(DATA / f"{case}.json")
        view = static_view(graph)
        write_json(OUT / "static" / f"{case}.json", view)
        scene_rows: dict[str, list[dict]] = {}
        b_best_plan = None
        for scene in ("A", "B"):
            rows, _metadata = evaluate_cell(graph, view, config, modules, case, scene)
            scene_rows[scene] = rows
            verified = [row for row in rows if row["status"] == "AI_VERIFIED"]
            best = min(verified, key=lambda row: (int(row["makespan"]), int(row.get("added_copy_bytes", 0)), int(row["order"]))) if verified else None
            if scene == "B" and best:
                plan_path = OUT / "cells" / case / f"{CORES}core" / "B" / "candidates" / f"{int(best['order']):02d}_{best['candidate']}" / "plan.json"
                b_best_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if b_best_plan is not None:
            rows, _metadata = evaluate_cell(graph, view, config, modules, case, "C", incumbent_plan=b_best_plan)
            scene_rows["C"] = rows
        else:
            scene_rows["C"] = []
        # The single-core baseline is the same for all scenes in the official data;
        # use the first available 1-core A row in the frozen report only for the
        # representative speedup column, while preserving raw Makespan above.
        baseline_path = Path("/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/main_reports_20260924_v2/main_results.csv")
        baseline = None
        if baseline_path.exists():
            import pandas as pd
            base_df = pd.read_csv(baseline_path)
            subset = base_df[(base_df["case"] == case) & (base_df["cores"] == 1) & (base_df["scene"] == "A")]
            if len(subset):
                baseline = float(subset.iloc[0]["baseline_makespan"])
        for scene, rows in scene_rows.items():
            all_attempts.extend(rows)
            for item in cumulative_rows(rows, baseline):
                all_budget.append({"case": case, "scene": scene, "baseline_makespan": baseline, **item})
    write_csv(OUT / "attempts.csv", all_attempts)
    write_csv(OUT / "budget_summary.csv", all_budget)
    # Aggregate only over cells with a verified best at that budget; missing cells
    # remain explicit in the denominator columns.
    import pandas as pd
    bdf = pd.DataFrame(all_budget)
    aggregate = []
    for (scene, budget), group in bdf.groupby(["scene", "budget"], sort=True):
        speeds = pd.to_numeric(group["speedup_vs_baseline"], errors="coerce").dropna()
        aggregate.append({
            "scene": scene,
            "budget": int(budget),
            "cells": len(group),
            "cells_with_verified_best": int(speeds.size),
            "mean_speedup": float(speeds.mean()) if len(speeds) else None,
            "median_speedup": float(speeds.median()) if len(speeds) else None,
            "mean_success_rate": float(pd.to_numeric(group["success_rate"], errors="coerce").mean()),
            "mean_cumulative_eval_seconds": float(pd.to_numeric(group["cumulative_eval_seconds"], errors="coerce").mean()),
        })
    write_csv(OUT / "budget_aggregate.csv", aggregate)
    manifest.update({"status": "COMPUTED", "ended_at": time.time(), "attempt_rows": len(all_attempts), "budget_rows": len(all_budget), "aggregate_rows": len(aggregate)})
    write_json(OUT / "run_manifest.json", manifest)
    print(json.dumps({k: manifest[k] for k in ("run_id", "status", "attempt_rows", "budget_rows", "aggregate_rows")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
