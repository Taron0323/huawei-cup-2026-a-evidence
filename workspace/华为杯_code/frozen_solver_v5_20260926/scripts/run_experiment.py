#!/usr/bin/env python3
"""Profile-guided finite search for the frozen Huawei Cup A idea."""

from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import platform
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huawei_code.candidates import event_timing_variants, generate_candidates  # noqa: E402
from huawei_code.graph import load_graph, static_view  # noqa: E402
from huawei_code.gpu_score import backend_info, rank_load_vectors  # noqa: E402
from huawei_code.official import evaluate, file_sha, load_modules, profile, read_config, summary  # noqa: E402
from huawei_code.plan import extend_plan_with_empty_cores, plan_key, validate_plan  # noqa: E402
from huawei_code.scoring import light_score  # noqa: E402
from huawei_code.verification import check_result  # noqa: E402


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cases_arg(raw: str | None) -> list[str]:
    if not raw:
        return ["case_001"]
    return [item if item.startswith("case_") else f"case_{int(item):03d}" for item in raw.split(",")]


def scene_call_limit(scene: str, requested: int) -> int:
    return min(requested, 2) if scene in {"A", "B"} else min(requested, 4)


def light_sort_key(item):
    return (tuple(item["light"].get("score", (10**30,))), item["candidate"])


def profile_sort_key(item):
    score = (item.get("profile") or {}).get("profile_score")
    if score is None:
        return (10**30, 10**30, 10**30, item["candidate"])
    return (tuple(int(value) for value in score), item["candidate"])


def profile_item(item, *, graph, view, scene, cores, config, modules, scene_out) -> bool:
    """Run and cache the official kernel-expansion profile for one candidate."""
    candidate_out = scene_out / "candidates" / item["candidate"]
    write_json(candidate_out / "plan.json", item["plan"])
    if "profile_status" in item:
        return item["profile_status"] == "PROFILED"
    try:
        validate_plan(view, item["plan"], cores)
        started = time.perf_counter()
        result = profile(graph, item["plan"], scene, config, modules)
        result["elapsed_seconds"] = time.perf_counter() - started
        item["profile"] = result
        item["profile_status"] = "PROFILED"
        write_json(candidate_out / "profile.json", result)
        return True
    except Exception as exc:
        failure = {
            "status": "PROFILE_FAILED", "error_type": type(exc).__name__,
            "error": str(exc), "candidate": item["candidate"],
            "scene": scene, "cores": cores,
        }
        item["profile_status"] = "PROFILE_FAILED"
        item["profile_failure"] = failure
        write_json(candidate_out / "profile_failure.json", failure)
        return False


def add_candidate(candidates, seen, name, plan, source, view, scene, config, *, mandatory=False):
    key = plan_key(plan)
    if key in seen:
        return next((item for item in candidates if plan_key(item["plan"]) == key), None)
    item = {
        "candidate": name,
        "source": source,
        "plan": plan,
        "mandatory": bool(mandatory),
        "light": light_score(view, plan, scene, config),
    }
    candidates.append(item)
    seen.add(key)
    return item


def candidate_ledger(candidates):
    rows = []
    for item in candidates:
        row = {
            "candidate": item["candidate"],
            "source": item["source"],
            "mandatory": bool(item.get("mandatory")),
            "plan_sha256": plan_key(item["plan"]),
            "light": item["light"],
            "profile_status": item.get("profile_status", "NOT_PROFILED"),
        }
        if item.get("profile") is not None:
            row["profile"] = item["profile"]
        if item.get("profile_failure") is not None:
            row["profile_failure"] = item["profile_failure"]
        if item.get("official_summary") is not None:
            row["official_summary"] = item["official_summary"]
        rows.append(row)
    return rows


def select_c_candidate(remaining, evaluated_items, full_calls):
    if not remaining:
        raise ValueError("no remaining candidate")
    mandatory = [item for item in remaining if item.get("mandatory")]
    if mandatory and not evaluated_items:
        return min(mandatory, key=lambda item: (item.get("source") != "incumbent", item["candidate"]))
    if full_calls == 1:
        event_items = [item for item in remaining if item.get("source") == "event_timing"]
        pool = event_items or remaining
        return max(pool, key=lambda item: (
            int(item["light"].get("cache_hit_bytes", 0)),
            int(item["light"].get("cache_reuse_potential", 0)),
            float(item["light"].get("cache_expected_gain", 0.0)),
            -int(item["light"].get("light_time", 0)), item["candidate"],
        ))
    if full_calls == 2:
        return min(remaining, key=light_sort_key)
    if full_calls == 3:
        typed = [item for item in remaining if item.get("source") in {"cache_delay", "event_timing", "timing"}]
        return max(typed or remaining, key=lambda item: (
            int(item["light"].get("cache_hit_bytes", 0)),
            float(item["light"].get("cache_expected_gain", 0.0)),
            -int(item["light"].get("light_time", 0)), item["candidate"],
        ))
    return min(remaining, key=light_sort_key)


def normalize_cache_events(events, profile_result):
    """Attach the original logical tensor ID to official COPY_IN events."""
    mapping = (profile_result or {}).get("copy_in_logical_tids", {})
    normalized = []
    for event in events:
        item = dict(event)
        key = f"{int(event.get('core_id', -1))}:{int(event.get('op_id', -1))}"
        logical_tid = mapping.get(key)
        if logical_tid is not None:
            item["logical_tensor_id"] = int(logical_tid)
        normalized.append(item)
    return normalized


def main() -> None:
    gc.disable()
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
    official_dir = Path(os.environ.get(
        "HUAWEI_EVALUATOR_DIR", str(ROOT / "vendor/official_evaluator"))).resolve()
    modules = load_modules(official_dir)
    config = read_config(modules, data / "config.txt")
    cases = cases_arg(args.cases)
    cores = [int(value) for value in args.cores.split(",")]
    scenes = [value.strip().upper() for value in args.scenes.split(",")]
    fast_profile = os.environ.get("HUAWEI_FAST_PROFILE") == "1"
    idea = ROOT / "idea/A题_Final_idea_给codex运行.md"
    source_paths = [
        ROOT / "scripts/run_experiment.py", ROOT / "scripts/run_full_matrix.py",
        ROOT / "src/huawei_code/candidates.py", ROOT / "src/huawei_code/plan.py",
        ROOT / "src/huawei_code/scoring.py", ROOT / "src/huawei_code/official.py",
        ROOT / "src/huawei_code/verification.py",
    ]
    manifest = {
        "run_id": output.name, "status": "RUNNING",
        "algorithm": "fresh_final_idea_cache_search_v0.7_profile_guided_event_timing_monotonic_fallback",
        "idea": str(idea.relative_to(ROOT)), "idea_sha256": file_sha(idea),
        "config": str((data / "config.txt").relative_to(ROOT)), "config_sha256": file_sha(data / "config.txt"),
        "solver_source_sha256": {str(path.relative_to(ROOT)): file_sha(path) for path in source_paths},
        "official_code_sha256": {path.name: file_sha(path) for path in sorted(official_dir.glob("*.py"))},
        "cases": cases, "cores": cores, "scenes": scenes,
        "full_candidates_requested": args.full_candidates,
        "scene_call_limits": {scene: scene_call_limit(scene, args.full_candidates) for scene in ("A", "B", "C")},
        "workers": args.workers, "python": sys.version, "platform": platform.platform(), "gc_disabled": True,
        "fast_profile": fast_profile,
        "official_evaluator_dir": str(official_dir),
        "backend": backend_info(), "new_workspace": True,
        "selection_policy": "A/B profile four starts, then profile ordinary/capacity representatives; C starts from B winner and adds official cache-event timing anchors; official makespan is authoritative; monotonic fallback is separately recorded",
    }
    write_json(output / "run_manifest.json", manifest)

    rows = []
    combination_status = {}
    for case in cases:
        graph = load_graph(data / f"{case}.json")
        view = static_view(graph)
        write_json(output / "static" / f"{case}.json", view)
        b_best, previous_best, previous_final = {}, {}, {}
        t1_result = None
        for core_count in cores:
            for scene in scenes:
                base_plan = b_best.get(core_count) if scene == "C" else None
                incumbent_plan = extend_plan_with_empty_cores(view, previous_best[scene], core_count) if scene in previous_best else None
                combo = f"{case}/{core_count}core/{scene}"
                if scene == "C" and base_plan is None:
                    combination_status[combo] = "SKIPPED_NO_B_RESULT"
                    rows.append({"case": case, "cores": core_count, "scene": scene, "status": "SKIPPED_NO_B_RESULT"})
                    continue

                candidates = generate_candidates(
                    view, core_count, scene, config,
                    base_plan=None if scene == "C" else base_plan,
                    incumbent_plan=base_plan if scene == "C" else incumbent_plan,
                )
                vectors = [list(item["light"]["loads"].values()) + [0] * max(0, core_count - len(item["light"]["loads"])) for item in candidates]
                gpu_order, gpu_info = rank_load_vectors(vectors) if vectors else ([], backend_info())
                for rank, index in enumerate(gpu_order):
                    candidates[index]["gpu_load_rank"] = rank
                candidates.sort(key=light_sort_key)
                candidate_seen = {plan_key(item["plan"]) for item in candidates}
                scene_out = output / "cases" / case / f"{core_count}core" / scene
                write_json(scene_out / "gpu_rank.json", gpu_info)

                evaluation_queue = []
                if scene in {"A", "B"}:
                    starts = sorted((item for item in candidates if item["source"] == "seed"), key=lambda item: item["candidate"])
                    if fast_profile:
                        # The completion budget uses one light-ranked seed and
                        # one official call per scene.  The standard path
                        # below keeps the full profile portfolio unchanged.
                        x0 = min(starts, key=light_sort_key) if starts else candidates[0]
                        profile_item(x0, graph=graph, view=view, scene=scene, cores=core_count, config=config, modules=modules, scene_out=scene_out)
                        evaluation_queue = [x0]
                    else:
                        for item in starts:
                            profile_item(item, graph=graph, view=view, scene=scene, cores=core_count, config=config, modules=modules, scene_out=scene_out)
                        valid_starts = [item for item in starts if item.get("profile_status") == "PROFILED"]
                        x0 = min(valid_starts, key=profile_sort_key) if valid_starts else (min(starts, key=light_sort_key) if starts else candidates[0])
                        reps = []
                        ordinary = [item for item in candidates if item["source"] in {"ordinary", "aggregate", "timing"} and item is not x0]
                        capacity = [item for item in candidates if item["source"] == "capacity" and item is not x0]
                        if ordinary:
                            reps.append(min(ordinary, key=light_sort_key))
                        if capacity:
                            reps.append(min(capacity, key=lambda item: (int(item["light"].get("pressure_bytes", 0)), tuple(item["light"].get("score", ())), item["candidate"])))
                        for item in reps:
                            profile_item(item, graph=graph, view=view, scene=scene, cores=core_count, config=config, modules=modules, scene_out=scene_out)
                        profile_pool = [item for item in valid_starts + reps if item.get("profile_status") == "PROFILED" and item is not x0]
                        evaluation_queue = [x0] + sorted(profile_pool, key=profile_sort_key)
                else:
                    mandatory = [item for item in candidates if item.get("mandatory")]
                    evaluation_queue = [min(mandatory, key=lambda item: (item.get("source") != "incumbent", item["candidate"]))] if mandatory else candidates[:1]
                write_json(scene_out / "candidate_ledger.json", candidate_ledger(candidates))

                evaluated_items, attempted = [], set()
                initial_result, initial_item = None, None
                full_calls, call_limit, event_added = 0, scene_call_limit(scene, args.full_candidates), False

                def run_full(item):
                    nonlocal full_calls, initial_result, initial_item
                    if item is None or item["candidate"] in attempted:
                        return None
                    attempted.add(item["candidate"])
                    if not profile_item(item, graph=graph, view=view, scene=scene, cores=core_count, config=config, modules=modules, scene_out=scene_out):
                        failure = item.get("profile_failure", {})
                        row = {"case": case, "cores": core_count, "scene": scene, "candidate": item["candidate"], "source": item["source"], "status": "PROFILE_FAILED", "plan_sha256": plan_key(item["plan"]), "gpu_backend": gpu_info.get("backend"), "error": failure.get("error")}
                        rows.append(row)
                        print(json.dumps(row, ensure_ascii=False), flush=True)
                        return None
                    full_calls += 1
                    candidate_out = scene_out / "candidates" / item["candidate"]
                    try:
                        started = time.perf_counter()
                        result = evaluate(graph, item["plan"], {"A": 1, "B": 2, "C": 3}[scene], config, modules)
                        elapsed = time.perf_counter() - started
                        write_json(candidate_out / "result.json", result)
                        write_json(candidate_out / "result_check.json", check_result(view, item["plan"], result, core_count))
                    except Exception as exc:
                        failure = {"status": "EVALUATION_FAILED", "error_type": type(exc).__name__, "error": str(exc), "candidate": item["candidate"], "scene": scene, "case": case, "cores": core_count}
                        write_json(candidate_out / "evaluation_failure.json", failure)
                        row = {"case": case, "cores": core_count, "scene": scene, "candidate": item["candidate"], "source": item["source"], "status": "EVALUATION_FAILED", "plan_sha256": plan_key(item["plan"]), "profile_seconds": (item.get("profile") or {}).get("elapsed_seconds"), "profile_score": (item.get("profile") or {}).get("profile_score"), "gpu_backend": gpu_info.get("backend"), "error": str(exc)}
                        rows.append(row)
                        print(json.dumps(row, ensure_ascii=False), flush=True)
                        return None
                    item["official_summary"] = summary(result)
                    evaluated_items.append((result, item))
                    row = {"case": case, "cores": core_count, "scene": scene, "candidate": item["candidate"], "source": item["source"], "status": "AI_VERIFIED", "plan_sha256": plan_key(item["plan"]), "profile_seconds": (item.get("profile") or {}).get("elapsed_seconds"), "profile_score": (item.get("profile") or {}).get("profile_score"), "evaluation_seconds": elapsed, "gpu_backend": gpu_info.get("backend"), **item["light"], **summary(result)}
                    rows.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                    if initial_result is None:
                        initial_result, initial_item = result, item
                        write_json(scene_out / "initial_plan.json", item["plan"])
                        write_json(scene_out / "initial_selection.json", {"candidate": item["candidate"], "plan_sha256": plan_key(item["plan"]), "makespan": result["makespan"], "added_copy_bytes": result["data_movement_bytes"]["added_copy_bytes"], "profile_score": (item.get("profile") or {}).get("profile_score"), "full_calls": full_calls})
                    return result

                while full_calls < call_limit and len(attempted) < len(candidates):
                    remaining = [item for item in candidates if item["candidate"] not in attempted]
                    if not remaining:
                        break
                    if scene in {"A", "B"}:
                        item = next((candidate for candidate in evaluation_queue if candidate["candidate"] not in attempted), None)
                        if item is None:
                            item = min(remaining, key=profile_sort_key if any(candidate.get("profile_status") == "PROFILED" for candidate in remaining) else light_sort_key)
                    else:
                        item = select_c_candidate(remaining, evaluated_items, full_calls)
                    result = run_full(item)
                    if scene == "C" and result is not None and not event_added:
                        events = normalize_cache_events(
                            result.get("cache_events", []), item.get("profile"))
                        miss_bytes, miss_count = {}, {}
                        for event in events:
                            if event.get("event") == "miss":
                                tid = int(event.get("logical_tensor_id", event.get("tensor_id", -1)))
                                miss_bytes[tid] = miss_bytes.get(tid, 0) + int(event.get("size_bytes", 0))
                                miss_count[tid] = miss_count.get(tid, 0) + 1
                        write_json(scene_out / "cache_event_anchors.json", {"source_candidate": item["candidate"], "event_count": len(events), "logical_mapping_count": sum(1 for event in events if "logical_tensor_id" in event), "repeated_miss_tensors": sorted(tid for tid, count in miss_count.items() if count >= 2), "miss_bytes_by_tensor": miss_bytes})
                        for name, plan, source in event_timing_variants(view, base_plan, core_count, events, config):
                            add_candidate(candidates, candidate_seen, name, plan, source, view, scene, config)
                        event_added = True
                        write_json(scene_out / "candidate_ledger.json", candidate_ledger(candidates))

                if evaluated_items:
                    fallback_reasons = []
                    def evaluated_for_plan(plan):
                        key = plan_key(plan)
                        return next(((result, item) for result, item in evaluated_items if plan_key(item["plan"]) == key), None)

                    best_result, best_item = min(evaluated_items, key=lambda pair: (pair[0]["makespan"], pair[0]["data_movement_bytes"]["added_copy_bytes"], pair[1]["candidate"]))
                    if scene in {"A", "B"}:
                        prior_result, prior_plan = previous_final.get(scene), previous_best.get(scene)
                        if prior_result is not None and best_result["makespan"] > prior_result["makespan"]:
                            fallback_plan = extend_plan_with_empty_cores(view, prior_plan, core_count)
                            fallback_reasons.append("makespan_increased_over_previous_core")
                            if evaluated_for_plan(fallback_plan) is None:
                                fallback_item = add_candidate(candidates, candidate_seen, f"{scene}_monotonic_previous_{core_count}core", fallback_plan, "monotonic_fallback", view, scene, config)
                                run_full(fallback_item)
                        best_result, best_item = min(evaluated_items, key=lambda pair: (pair[0]["makespan"], pair[0]["data_movement_bytes"]["added_copy_bytes"], pair[1]["candidate"]))
                        if t1_result is not None and best_result["makespan"] > t1_result["makespan"]:
                            baseline_item = next((item for item in candidates if item["candidate"].startswith(f"{scene}0_")), None)
                            if baseline_item is not None:
                                fallback_reasons.append("makespan_above_single_core_baseline")
                                if evaluated_for_plan(baseline_item["plan"]) is None:
                                    fallback_item = add_candidate(candidates, candidate_seen, f"{scene}_monotonic_baseline_{core_count}core", baseline_item["plan"], "monotonic_fallback", view, scene, config)
                                    run_full(fallback_item)
                    best_result, best_item = min(evaluated_items, key=lambda pair: (pair[0]["makespan"], pair[0]["data_movement_bytes"]["added_copy_bytes"], pair[1]["candidate"]))
                    hit_items = [pair for pair in evaluated_items if int((pair[0].get("cache_stats") or {}).get("hit_bytes", 0)) > 0]
                    best_hit = max(hit_items, key=lambda pair: (int((pair[0].get("cache_stats") or {}).get("hit_bytes", 0)), -int(pair[0]["makespan"]), pair[1]["candidate"])) if hit_items else None
                    fastest_hit = min(hit_items, key=lambda pair: (pair[0]["makespan"], pair[0]["data_movement_bytes"]["added_copy_bytes"], pair[1]["candidate"])) if hit_items else None
                    cache_diagnostic = {"final_cache_hit_bytes": int((best_result.get("cache_stats") or {}).get("hit_bytes", 0)), "evaluated_candidate_count": len(evaluated_items), "evaluated_hit_candidate_count": len(hit_items), "zero_hit_final_with_hit_alternative": bool(not int((best_result.get("cache_stats") or {}).get("hit_bytes", 0)) and hit_items), "max_hit_candidate": best_hit[1]["candidate"] if best_hit else None, "max_hit_bytes": int((best_hit[0].get("cache_stats") or {}).get("hit_bytes", 0)) if best_hit else 0, "fastest_hit_candidate": fastest_hit[1]["candidate"] if fastest_hit else None, "fastest_hit_makespan": int(fastest_hit[0]["makespan"]) if fastest_hit else None, "fastest_hit_bytes": int((fastest_hit[0].get("cache_stats") or {}).get("hit_bytes", 0)) if fastest_hit else 0}
                    write_json(scene_out / "final_plan.json", best_item["plan"])
                    write_json(scene_out / "final_selection.json", {"candidate": best_item["candidate"], "plan_sha256": plan_key(best_item["plan"]), "makespan": best_result["makespan"], "added_copy_bytes": best_result["data_movement_bytes"]["added_copy_bytes"], "full_calls": full_calls, "call_limit": call_limit, "fallback_reasons": fallback_reasons, "cache_diagnostic": cache_diagnostic})
                    write_json(scene_out / "candidate_ledger.json", candidate_ledger(candidates))
                    combination_status[combo] = "AI_VERIFIED"
                    if scene == "B":
                        b_best[core_count] = best_item["plan"]
                    previous_best[scene], previous_final[scene] = best_item["plan"], best_result
                    if scene == "A" and core_count == 1:
                        t1_result = best_result
                else:
                    combination_status[combo] = "NO_VALID_RESULT"

    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    complete = bool(combination_status) and all(status == "AI_VERIFIED" for status in combination_status.values())
    manifest.update({"status": "COMPUTED" if complete else "PARTIAL", "rows": len(rows), "combination_status": combination_status, "ended_at": time.time(), "active_experiment_processes": []})
    write_json(output / "run_manifest.json", manifest)
    print(json.dumps({"run_id": output.name, "status": manifest["status"], "rows": len(rows), "backend": manifest["backend"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
