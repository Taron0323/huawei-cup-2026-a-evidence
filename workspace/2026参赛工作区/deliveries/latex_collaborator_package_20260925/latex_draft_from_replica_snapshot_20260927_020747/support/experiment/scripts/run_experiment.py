#!/usr/bin/env python3
"""Run the fresh final-idea solver on selected A-problem graphs.

The default is a representative smoke run.  Full matrices require explicit
``--cases`` and ``--cores``; every run gets a new directory and a manifest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huawei_code.candidates import generate_candidates  # noqa: E402
from huawei_code.graph import load_graph, static_view  # noqa: E402
from huawei_code.gpu_score import backend_info, rank_load_vectors  # noqa: E402
from huawei_code.official import evaluate, file_sha, load_modules, profile, read_config, summary  # noqa: E402
from huawei_code.plan import pad_plan_cores, plan_key, seed_plans, validate_plan  # noqa: E402
from huawei_code.scoring import light_score  # noqa: E402
from huawei_code.verification import check_result  # noqa: E402


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _ensure_plan_candidate(candidates, view, cores, scene, config, plan, name, source):
    """Add a required plan unless an identical candidate is already present."""
    plan = pad_plan_cores(plan, cores)
    key = plan_key(plan)
    for item in candidates:
        if plan_key(item["plan"]) == key:
            return item
    return {
        "candidate": name,
        "source": source,
        "plan": plan,
        "light": light_score(view, plan, scene, config),
    }


def _prioritize_required(candidates, required):
    """Put required candidates first while retaining deterministic score order."""
    ordered = []
    seen = set()
    for item in required:
        key = plan_key(item["plan"])
        if key not in seen:
            ordered.append(item)
            seen.add(key)
    for item in candidates:
        key = plan_key(item["plan"])
        if key not in seen:
            ordered.append(item)
            seen.add(key)
    return ordered


def cases_arg(raw):
    if not raw:
        return ["case_001"]
    return [x if x.startswith("case_") else f"case_{int(x):03d}" for x in raw.split(",")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cases", default="case_001")
    parser.add_argument("--cores", default="1,2")
    parser.add_argument("--scenes", default="A,B,C")
    parser.add_argument("--full-candidates", type=int, default=2)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    output = args.output_root.resolve()
    if output.exists():
        raise SystemExit(f"refusing existing output: {output}")
    output.mkdir(parents=True)
    data = ROOT / "data/raw/A题/data"
    official_dir = ROOT / "vendor/official_evaluator"
    modules = load_modules(official_dir)
    config = read_config(modules, data / "config.txt")
    cases, cores, scenes = cases_arg(args.cases), [int(x) for x in args.cores.split(",")], [x.strip().upper() for x in args.scenes.split(",")]
    idea = ROOT / "idea/A题_Final_idea_给codex运行.md"
    manifest = {"run_id": output.name, "status": "RUNNING", "algorithm": "fresh_final_idea_v0.1", "idea": str(idea.relative_to(ROOT)), "idea_sha256": file_sha(idea), "cases": cases, "cores": cores, "scenes": scenes, "full_candidates": args.full_candidates, "workers": args.workers, "python": sys.version, "platform": platform.platform(), "official_code_sha256": {p.name: file_sha(p) for p in sorted(official_dir.glob("*.py"))}, "backend": backend_info(), "new_workspace": True}
    write_json(output / "run_manifest.json", manifest)
    rows = []
    combination_status = {}
    for case in cases:
        graph_path = data / f"{case}.json"
        graph = load_graph(graph_path)
        view = static_view(graph)
        write_json(output / "static" / f"{case}.json", view)
        b_best = {}
        scene_incumbents = {scene: [] for scene in ("A", "B", "C")}
        for k in cores:
            for scene in scenes:
                base_plan = b_best.get(k) if scene == "C" else None
                combo = f"{case}/{k}core/{scene}"
                if scene == "C" and base_plan is None:
                    combination_status[combo] = "SKIPPED_NO_B_RESULT"
                    rows.append({"case": case, "cores": k, "scene": scene, "status": "SKIPPED_NO_B_RESULT"})
                    continue
                candidates = generate_candidates(view, k, scene, config, base_plan=base_plan)
                # Every scene keeps a feasible incumbent in the comparison
                # set.  When core count grows, append idle cores rather than
                # forcing an already valid plan into an arbitrary split.
                required = []
                if scene in {"A", "B"}:
                    baseline = seed_plans(view, k, scene)[f"{scene}0"]
                    required.append(_ensure_plan_candidate(
                        candidates, view, k, scene, config, baseline,
                        f"{scene}0_base", "baseline",
                    ))
                elif base_plan is not None:
                    # Keep the first C evaluation as C(X_B) so the existing
                    # B/C paired reports retain their plan identity.
                    required.append(_ensure_plan_candidate(
                        candidates, view, k, scene, config, base_plan,
                        f"C_from_B_{k}core", "B_incumbent",
                    ))
                previous = [entry for entry in scene_incumbents[scene] if entry["cores"] <= k]
                if previous:
                    previous_entry = max(previous, key=lambda entry: entry["cores"])
                    previous_plan = pad_plan_cores(previous_entry["plan"], k)
                    required.append(_ensure_plan_candidate(
                        candidates, view, k, scene, config, previous_plan,
                        f"{scene}_incumbent_{previous_entry['cores']}to{k}", "incumbent",
                    ))
                candidates = _prioritize_required(candidates, required)
                vectors = [list(item["light"]["loads"].values()) + [0] * max(0, k - len(item["light"]["loads"])) for item in candidates]
                gpu_order, gpu_info = rank_load_vectors(vectors) if vectors else ([], backend_info())
                for rank, index in enumerate(gpu_order):
                    candidates[index]["gpu_load_rank"] = rank
                scene_out = output / "cases" / case / f"{k}core" / scene
                write_json(scene_out / "gpu_rank.json", gpu_info)
                write_json(scene_out / "candidate_ledger.json", [{"candidate": c["candidate"], "source": c["source"], "plan_sha256": plan_key(c["plan"]), "light": c["light"]} for c in candidates])
                evaluated_items = []
                initial_result = None
                initial_item = None
                attempted = set()
                full_calls = 0
                while full_calls < args.full_candidates and len(attempted) < len(candidates):
                    remaining = [c for c in candidates if c["candidate"] not in attempted]
                    item = remaining[0]
                    attempted.add(item["candidate"])
                    candidate_out = scene_out / "candidates" / item["candidate"]
                    write_json(candidate_out / "plan.json", item["plan"])
                    try:
                        validate_plan(view, item["plan"], k, scene)
                        prof_started = time.perf_counter()
                        prof = profile(graph, item["plan"], scene, config, modules)
                        prof["elapsed_seconds"] = time.perf_counter() - prof_started
                        write_json(candidate_out / "profile.json", prof)
                    except Exception as exc:
                        failure = {"status": "PROFILE_FAILED", "error_type": type(exc).__name__, "error": str(exc), "candidate": item["candidate"], "scene": scene, "case": case, "cores": k}
                        write_json(candidate_out / "profile_failure.json", failure)
                        row = {"case": case, "cores": k, "scene": scene, "candidate": item["candidate"], "source": item["source"], "status": "PROFILE_FAILED", "plan_sha256": plan_key(item["plan"]), "gpu_backend": gpu_info.get("backend"), "error": str(exc)}
                        rows.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
                        continue
                    problem = {"A": 1, "B": 2, "C": 3}[scene]
                    full_calls += 1
                    try:
                        started = time.perf_counter()
                        result = evaluate(graph, item["plan"], problem, config, modules)
                        elapsed = time.perf_counter() - started
                        write_json(candidate_out / "result.json", result)
                        check = check_result(view, item["plan"], result, k, scene)
                        write_json(candidate_out / "result_check.json", check)
                    except Exception as exc:
                        failure = {"status": "EVALUATION_FAILED", "error_type": type(exc).__name__, "error": str(exc), "candidate": item["candidate"], "scene": scene, "case": case, "cores": k}
                        write_json(candidate_out / "evaluation_failure.json", failure)
                        row = {"case": case, "cores": k, "scene": scene, "candidate": item["candidate"], "source": item["source"], "status": "EVALUATION_FAILED", "plan_sha256": plan_key(item["plan"]), "profile_seconds": prof["elapsed_seconds"], "gpu_backend": gpu_info.get("backend"), "error": str(exc)}
                        rows.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
                        continue
                    evaluated_items.append((result, item))
                    if initial_result is None:
                        initial_result, initial_item = result, item
                        write_json(scene_out / "initial_plan.json", item["plan"])
                        write_json(scene_out / "initial_selection.json", {"candidate": item["candidate"], "plan_sha256": plan_key(item["plan"]), "makespan": result["makespan"], "added_copy_bytes": result["data_movement_bytes"]["added_copy_bytes"], "full_calls": full_calls})
                    row = {"case": case, "cores": k, "scene": scene, "candidate": item["candidate"], "source": item["source"], "status": "AI_VERIFIED", "plan_sha256": plan_key(item["plan"]), "profile_seconds": prof["elapsed_seconds"], "evaluation_seconds": elapsed, "gpu_backend": gpu_info.get("backend"), **item["light"], **summary(result)}
                    rows.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                if evaluated_items:
                    best_result, best_item = min(evaluated_items, key=lambda pair: (pair[0]["makespan"], pair[0]["data_movement_bytes"]["added_copy_bytes"], pair[1]["candidate"]))
                    scene_incumbents[scene].append({"cores": k, "plan": best_item["plan"], "result": best_result})
                    write_json(scene_out / "final_plan.json", best_item["plan"])
                    write_json(scene_out / "final_selection.json", {"candidate": best_item["candidate"], "plan_sha256": plan_key(best_item["plan"]), "makespan": best_result["makespan"], "added_copy_bytes": best_result["data_movement_bytes"]["added_copy_bytes"], "full_calls": full_calls})
                    combination_status[combo] = "AI_VERIFIED"
                    if scene == "B":
                        b_best[k] = best_item["plan"]
                else:
                    combination_status[combo] = "NO_VALID_RESULT"
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    complete = all(status == "AI_VERIFIED" for status in combination_status.values())
    manifest.update({"status": "COMPUTED" if complete else "PARTIAL", "rows": len(rows), "combination_status": combination_status, "ended_at": time.time(), "active_experiment_processes": []})
    write_json(output / "run_manifest.json", manifest)
    print(json.dumps({"run_id": output.name, "status": manifest["status"], "rows": len(rows), "backend": manifest["backend"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
