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
from huawei_code.plan import extend_plan_with_empty_cores, plan_key, validate_plan  # noqa: E402
from huawei_code.verification import check_result  # noqa: E402


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cases_arg(raw):
    if not raw:
        return ["case_001"]
    return [x if x.startswith("case_") else f"case_{int(x):03d}" for x in raw.split(",")]


def select_candidate(remaining, scene, base_plan, evaluated_items, full_calls):
    """Use a C portfolio so cache-aware plans reach the official evaluator."""
    if not remaining:
        raise ValueError("no remaining candidate")
    mandatory = [item for item in remaining if item.get("mandatory")]
    if mandatory:
        return min(mandatory, key=lambda item: (item.get("source") != "incumbent", item["candidate"]))
    if scene != "C":
        if full_calls == 1:
            capacity_items = [item for item in remaining if item.get("source") == "capacity"]
            if capacity_items:
                # Reserve one official call for a capacity-risk edit.  Its
                # pressure is a triage signal only; final selection remains
                # official makespan followed by added copy bytes.
                return max(capacity_items, key=lambda item: (
                    int(item["light"].get("pressure_bytes", 0)),
                    -int(item["light"].get("light_time", 0)),
                    item["candidate"],
                ))
        if full_calls == 2:
            typed = [item for item in remaining if item.get("source") in {"ordinary", "capacity"}]
            if typed:
                return min(typed, key=lambda item: (tuple(item["light"]["score"]), item["candidate"]))
        return remaining[0]
    base_key = plan_key(base_plan) if base_plan is not None else None
    if not evaluated_items:
        base = next((item for item in remaining if plan_key(item["plan"]) == base_key), None)
        if base is not None:
            return base
    if full_calls == 1:
        # The first post-baseline call is deliberately the candidate with the
        # greatest replayed hit opportunity, including disperse candidates.
        return max(remaining, key=lambda item: (
            int(item["light"].get("cache_hit_bytes", 0)),
            int(item["light"].get("cache_reuse_potential", 0)),
            float(item["light"].get("cache_expected_gain", 0.0)),
            -int(item["light"].get("light_time", 0)),
            -int(item["light"].get("copy_bytes", 0)),
            item["candidate"],
        ))
    if full_calls == 2:
        # The second post-baseline call covers the fastest light-score plan,
        # which can win even when a hit-heavy plan adds too much traffic.
        return min(remaining, key=lambda item: (tuple(item["light"]["score"]), item["candidate"]))
    if full_calls == 3:
        # Reserve a call for a capacity-risk edit before ordinary timing
        # alternatives.  This is an evaluation quota, not an assumed gain.
        capacity_items = [item for item in remaining if item.get("source") == "capacity"]
        if capacity_items:
            return max(capacity_items, key=lambda item: (
                int(item["light"].get("pressure_bytes", 0)),
                -int(item["light"].get("light_time", 0)),
                item["candidate"],
            ))
    if full_calls == 4:
        # Keep a distinct timing/aggregate plan in the portfolio when present.
        typed = [item for item in remaining if item["source"] in {"timing", "aggregate", "disperse"}]
        if typed:
            return max(typed, key=lambda item: (
                float(item["light"].get("cache_expected_gain", 0.0)),
                int(item["light"].get("cache_hit_bytes", 0)),
                -int(item["light"].get("light_time", 0)),
                item["candidate"],
            ))
    return remaining[0]


def scene_call_limit(scene: str, requested: int) -> int:
    """Apply the Idea's official-evaluation quota per scene."""
    if scene in {"A", "B"}:
        return min(requested, 2)
    return min(requested, 4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cases", default="case_001")
    parser.add_argument("--cores", default="1,2")
    parser.add_argument("--scenes", default="A,B,C")
    parser.add_argument("--full-candidates", type=int, default=6)
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
    solver_sources = [
        ROOT / "scripts/run_experiment.py",
        ROOT / "scripts/run_full_matrix.py",
        ROOT / "src/huawei_code/candidates.py",
        ROOT / "src/huawei_code/plan.py",
        ROOT / "src/huawei_code/scoring.py",
        ROOT / "src/huawei_code/verification.py",
    ]
    manifest = {"run_id": output.name, "status": "RUNNING", "algorithm": "fresh_final_idea_cache_search_v0.5_scene_quota_diagnostics", "idea": str(idea.relative_to(ROOT)), "idea_sha256": file_sha(idea), "config": str((data / "config.txt").relative_to(ROOT)), "config_sha256": file_sha(data / "config.txt"), "solver_source_sha256": {str(path.relative_to(ROOT)): file_sha(path) for path in solver_sources}, "cases": cases, "cores": cores, "scenes": scenes, "full_candidates_requested": args.full_candidates, "scene_call_limits": {"A": scene_call_limit("A", args.full_candidates), "B": scene_call_limit("B", args.full_candidates), "C": scene_call_limit("C", args.full_candidates)}, "workers": args.workers, "python": sys.version, "platform": platform.platform(), "official_code_sha256": {p.name: file_sha(p) for p in sorted(official_dir.glob("*.py"))}, "backend": backend_info(), "new_workspace": True, "selection_policy": "mandatory incumbent/base; reserve capacity-source official candidate when budget permits; then timing/cache candidates; final official makespan then added copy bytes; record cache-hit alternatives separately"}
    write_json(output / "run_manifest.json", manifest)
    rows = []
    combination_status = {}
    for case in cases:
        graph_path = data / f"{case}.json"
        graph = load_graph(graph_path)
        view = static_view(graph)
        write_json(output / "static" / f"{case}.json", view)
        b_best = {}
        previous_best = {}
        for k in cores:
            for scene in scenes:
                base_plan = b_best.get(k) if scene == "C" else None
                incumbent_plan = None
                if scene in previous_best:
                    incumbent_plan = extend_plan_with_empty_cores(view, previous_best[scene], k)
                combo = f"{case}/{k}core/{scene}"
                if scene == "C" and base_plan is None:
                    combination_status[combo] = "SKIPPED_NO_B_RESULT"
                    rows.append({"case": case, "cores": k, "scene": scene, "status": "SKIPPED_NO_B_RESULT"})
                    continue
                if scene == "C":
                    # Keep the B winner as the mandatory first C evaluation,
                    # while retaining bounded alternative starts for cache
                    # timing and repeated Spill/Reload opportunities.
                    candidates = generate_candidates(
                        view, k, scene, config,
                        base_plan=None,
                        incumbent_plan=base_plan,
                    )
                else:
                    candidates = generate_candidates(view, k, scene, config, base_plan=base_plan, incumbent_plan=incumbent_plan)
                vectors = [list(item["light"]["loads"].values()) + [0] * max(0, k - len(item["light"]["loads"])) for item in candidates]
                gpu_order, gpu_info = rank_load_vectors(vectors) if vectors else ([], backend_info())
                for rank, index in enumerate(gpu_order):
                    candidates[index]["gpu_load_rank"] = rank
                candidates.sort(key=lambda item: (tuple(item["light"]["score"]), item["candidate"]))
                scene_out = output / "cases" / case / f"{k}core" / scene
                write_json(scene_out / "gpu_rank.json", gpu_info)
                write_json(scene_out / "candidate_ledger.json", [{"candidate": c["candidate"], "source": c["source"], "plan_sha256": plan_key(c["plan"]), "light": c["light"]} for c in candidates])
                evaluated_items = []
                initial_result = None
                initial_item = None
                attempted = set()
                full_calls = 0
                call_limit = scene_call_limit(scene, args.full_candidates)
                while full_calls < call_limit and len(attempted) < len(candidates):
                    remaining = [c for c in candidates if c["candidate"] not in attempted]
                    if scene in {"A", "B"} and full_calls and not evaluated_items:
                        item = next((c for c in remaining if c["candidate"].startswith(f"{scene}0_")), remaining[0])
                    else:
                        item = select_candidate(remaining, scene, base_plan, evaluated_items, full_calls)
                    attempted.add(item["candidate"])
                    candidate_out = scene_out / "candidates" / item["candidate"]
                    write_json(candidate_out / "plan.json", item["plan"])
                    try:
                        validate_plan(view, item["plan"], k)
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
                        check = check_result(view, item["plan"], result, k)
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
                    hit_items = [pair for pair in evaluated_items if int((pair[0].get("cache_stats") or {}).get("hit_bytes", 0)) > 0]
                    best_hit = max(hit_items, key=lambda pair: (int((pair[0].get("cache_stats") or {}).get("hit_bytes", 0)), -int(pair[0]["makespan"]), pair[1]["candidate"])) if hit_items else None
                    fastest_hit = min(hit_items, key=lambda pair: (pair[0]["makespan"], pair[0]["data_movement_bytes"]["added_copy_bytes"], pair[1]["candidate"])) if hit_items else None
                    best_cache_hit_bytes = int((best_result.get("cache_stats") or {}).get("hit_bytes", 0))
                    cache_diagnostic = {
                        "final_cache_hit_bytes": best_cache_hit_bytes,
                        "evaluated_candidate_count": len(evaluated_items),
                        "evaluated_hit_candidate_count": len(hit_items),
                        "zero_hit_final_with_hit_alternative": bool(best_cache_hit_bytes == 0 and hit_items),
                        "max_hit_candidate": best_hit[1]["candidate"] if best_hit else None,
                        "max_hit_bytes": int((best_hit[0].get("cache_stats") or {}).get("hit_bytes", 0)) if best_hit else 0,
                        "fastest_hit_candidate": fastest_hit[1]["candidate"] if fastest_hit else None,
                        "fastest_hit_makespan": int(fastest_hit[0]["makespan"]) if fastest_hit else None,
                        "fastest_hit_bytes": int((fastest_hit[0].get("cache_stats") or {}).get("hit_bytes", 0)) if fastest_hit else 0,
                    }
                    write_json(scene_out / "final_plan.json", best_item["plan"])
                    write_json(scene_out / "final_selection.json", {"candidate": best_item["candidate"], "plan_sha256": plan_key(best_item["plan"]), "makespan": best_result["makespan"], "added_copy_bytes": best_result["data_movement_bytes"]["added_copy_bytes"], "full_calls": full_calls, "call_limit": call_limit, "cache_diagnostic": cache_diagnostic})
                    combination_status[combo] = "AI_VERIFIED"
                    if scene == "B":
                        b_best[k] = best_item["plan"]
                    previous_best[scene] = best_item["plan"]
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
