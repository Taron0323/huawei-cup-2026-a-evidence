#!/usr/bin/env python3
"""Recheck zero-hit Problem-3 selections with bounded official event candidates."""

from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from huawei_code.candidates import event_timing_variants  # noqa: E402
from huawei_code.graph import load_graph, static_view  # noqa: E402
from huawei_code.official import evaluate, load_modules, read_config, summary  # noqa: E402
from huawei_code.plan import plan_key, validate_plan  # noqa: E402
from huawei_code.scoring import light_score  # noqa: E402
from run_experiment import normalize_cache_events  # noqa: E402


def evaluator_dir() -> Path:
    return Path(os.environ.get(
        "HUAWEI_EVALUATOR_DIR", str(ROOT / "vendor/official_evaluator_fast"))).resolve()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def discover_jobs(main_roots: list[Path]) -> list[dict]:
    jobs = []
    seen = set()
    patterns = ("batch_*/cases/*/*core/C/final_selection.json", "case_*_*core/cases/*/*core/C/final_selection.json", "cases/*/*core/C/final_selection.json")
    for main_root in main_roots:
        paths = []
        for pattern in patterns:
            paths.extend(main_root.glob(pattern))
        for selection_path in sorted(paths):
            scene_root = selection_path.parent
            case = scene_root.parent.parent.name
            cores = int(scene_root.parent.name[:-4])
            key = (case, cores)
            if key in seen:
                continue
            seen.add(key)
            selection = read_json(selection_path)
            diagnostic = selection.get("cache_diagnostic", {})
            if int(diagnostic.get("final_cache_hit_bytes", 0)) > 0:
                continue
            if int(diagnostic.get("evaluated_hit_candidate_count", 0)) > 0:
                continue
            jobs.append({"case": case, "cores": cores, "scene_root": str(scene_root), "selection": selection, "main_root": str(main_root)})
    return jobs


def candidate_pool(view: dict, base_plan: dict, scene_root: Path, events: list[dict], config: dict, max_candidates: int) -> list[tuple[str, dict, str]]:
    variants = event_timing_variants(view, base_plan, len(base_plan["core_schedules"]), events, config)
    pool = [(name, plan, source) for name, plan, source in variants]
    evaluated_keys = set()
    ledger_path = scene_root / "candidate_ledger.json"
    if ledger_path.exists():
        for item in read_json(ledger_path):
            candidate_name = item.get("candidate")
            candidate_dir = scene_root / "candidates" / str(candidate_name)
            if (candidate_dir / "result.json").exists():
                evaluated_keys.add(item.get("plan_sha256"))
            if item.get("source") not in {"event_timing", "timing", "cache_delay", "disperse", "capacity"}:
                continue
            plan_path = candidate_dir / "plan.json"
            if plan_path.exists():
                pool.append((item["candidate"], read_json(plan_path), item["source"]))
    unique = {}
    for name, plan, source in pool:
        if plan_key(plan) in evaluated_keys:
            continue
        unique.setdefault(plan_key(plan), (name, plan, source))
    ranked = []
    for name, plan, source in unique.values():
        light = light_score(view, plan, "C", config)
        ranked.append((
            -int(light.get("cache_hit_bytes", 0)),
            -float(light.get("cache_expected_gain", 0.0)),
            int(light.get("light_time", 0)),
            name,
            plan,
            source,
        ))
    ranked.sort(key=lambda item: item[:4])
    return [(name, plan, source) for _hit, _gain, _time, name, plan, source in ranked[:max_candidates]]


def worker(job: dict) -> dict:
    scene_root = Path(job["scene_root"])
    output_scene = Path(job["output_scene"])
    case = job["case"]
    cores = int(job["cores"])
    data = ROOT / "data/raw/A题/data"
    modules = load_modules(evaluator_dir())
    config = read_config(modules, data / "config.txt")
    graph = load_graph(data / f"{case}.json")
    view = static_view(graph)
    base_plan = read_json(scene_root.parent / "B" / "final_plan.json")
    initial = read_json(scene_root / "initial_selection.json")
    initial_result_path = scene_root / "candidates" / initial["candidate"] / "result.json"
    initial_profile_path = scene_root / "candidates" / initial["candidate"] / "profile.json"
    initial_result = read_json(initial_result_path)
    initial_profile = read_json(initial_profile_path) if initial_profile_path.exists() else {}
    events = normalize_cache_events(initial_result.get("cache_events", []), initial_profile)
    candidates = candidate_pool(view, base_plan, scene_root, events, config, int(job["max_candidates"]))
    rows = []
    best = {"candidate": job["selection"]["candidate"], "makespan": int(job["selection"]["makespan"]), "added_copy_bytes": int(job["selection"].get("added_copy_bytes", 0)), "cache_hit_bytes": 0, "source": "main_final"}
    hit_candidates = []
    for candidate, plan, source in candidates:
        validate_plan(view, plan, cores)
        started = time.perf_counter()
        try:
            result = evaluate(graph, plan, 3, config, modules)
            result_summary = summary(result)
            row = {"case": case, "cores": cores, "candidate": candidate, "source": source, "status": "AI_VERIFIED", "plan_sha256": plan_key(plan), "evaluation_seconds": time.perf_counter() - started, **result_summary}
            write_json(output_scene / "candidates" / candidate / "plan.json", plan)
            write_json(output_scene / "candidates" / candidate / "result.json", result)
            cache_hit = int(result_summary.get("cache_hit_bytes") or 0)
            if cache_hit > 0:
                hit_candidates.append({"candidate": candidate, "source": source, "makespan": int(result_summary["makespan"]), "added_copy_bytes": int(result_summary["added_copy_bytes"] or 0), "cache_hit_bytes": cache_hit, "plan_sha256": plan_key(plan)})
            if (int(result_summary["makespan"]), int(result_summary["added_copy_bytes"] or 0), candidate) < (best["makespan"], best["added_copy_bytes"], best["candidate"]):
                best = {"candidate": candidate, "makespan": int(result_summary["makespan"]), "added_copy_bytes": int(result_summary["added_copy_bytes"] or 0), "cache_hit_bytes": cache_hit, "source": source, "plan_sha256": plan_key(plan)}
        except Exception as exc:
            row = {"case": case, "cores": cores, "candidate": candidate, "source": source, "status": "EVALUATION_FAILED", "plan_sha256": plan_key(plan), "evaluation_seconds": time.perf_counter() - started, "error_type": type(exc).__name__, "error": str(exc)}
        rows.append(row)
    main_makespan = int(job["selection"]["makespan"])
    hit_candidates.sort(key=lambda item: (item["makespan"], item["added_copy_bytes"], item["candidate"]))
    fastest_hit = hit_candidates[0] if hit_candidates else None
    max_hit = max(hit_candidates, key=lambda item: (item["cache_hit_bytes"], -item["makespan"], -item["added_copy_bytes"], item["candidate"])) if hit_candidates else None
    epsilon_choices = {}
    for epsilon in (0.005, 0.01):
        eligible = [item for item in hit_candidates if item["makespan"] <= main_makespan * (1.0 + epsilon)]
        epsilon_choices[str(epsilon)] = min(eligible, key=lambda item: (item["added_copy_bytes"], item["makespan"], item["candidate"])) if eligible else None
    rescue = {
        "case": case, "cores": cores, "main_final": job["selection"], "source_candidate": initial["candidate"],
        "event_count": len(events), "candidate_count": len(candidates), "best": best,
        "hit_candidate_count": len(hit_candidates), "fastest_hit": fastest_hit, "max_hit": max_hit,
        "epsilon_hit_choices": epsilon_choices,
        "replaced_main_final": best["candidate"] != job["selection"]["candidate"],
        "main_root_immutable": True,
    }
    write_json(output_scene / "rescue_selection.json", rescue)
    write_csv(output_scene / "rescue_metrics.csv", rows)
    return {"case": case, "cores": cores, "status": "COMPUTED", "rows": rows, "rescue": rescue}


def main() -> None:
    parser = argparse.ArgumentParser()
    roots = parser.add_mutually_exclusive_group(required=True)
    roots.add_argument("--main-root", type=Path)
    roots.add_argument("--main-roots", type=Path, nargs="+")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--parallel", type=int, default=8)
    parser.add_argument("--max-candidates", type=int, default=8)
    args = parser.parse_args()
    main_roots = [path.resolve() for path in (args.main_roots or [args.main_root])]
    out = args.output_root.resolve()
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    out.mkdir(parents=True)
    jobs = discover_jobs(main_roots)
    for job in jobs:
        job["max_candidates"] = args.max_candidates
        job["output_scene"] = str(out / "cases" / job["case"] / f"{job['cores']}core" / "C")
    write_json(out / "run_manifest.json", {"run_id": out.name, "status": "RUNNING", "main_roots": [str(root) for root in main_roots], "jobs": len(jobs), "max_candidates": args.max_candidates, "parallel": args.parallel, "official_evaluator_dir": str(evaluator_dir()), "started_at": time.time()})
    records = []
    with ProcessPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(worker, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            records.append(result)
            print(json.dumps({"case": result["case"], "cores": result["cores"], "rows": len(result["rows"]), "replaced": result["rescue"]["replaced_main_final"]}, ensure_ascii=False), flush=True)
    summary_rows = []
    for record in records:
        rescue = record["rescue"]
        fastest_hit = rescue.get("fastest_hit") or {}
        max_hit = rescue.get("max_hit") or {}
        summary_rows.append({"case": record["case"], "cores": record["cores"], "status": record["status"], "candidate_count": rescue["candidate_count"], "event_count": rescue["event_count"], "hit_candidate_count": rescue.get("hit_candidate_count", 0), "main_candidate": rescue["main_final"]["candidate"], "main_makespan": rescue["main_final"]["makespan"], "rescue_candidate": rescue["best"]["candidate"], "rescue_makespan": rescue["best"]["makespan"], "rescue_hit_bytes": rescue["best"]["cache_hit_bytes"], "fastest_hit_candidate": fastest_hit.get("candidate"), "fastest_hit_makespan": fastest_hit.get("makespan"), "fastest_hit_bytes": fastest_hit.get("cache_hit_bytes", 0), "max_hit_candidate": max_hit.get("candidate"), "max_hit_makespan": max_hit.get("makespan"), "max_hit_bytes": max_hit.get("cache_hit_bytes", 0), "epsilon_0_005_candidate": (rescue.get("epsilon_hit_choices", {}).get("0.005") or {}).get("candidate"), "epsilon_0_01_candidate": (rescue.get("epsilon_hit_choices", {}).get("0.01") or {}).get("candidate"), "replaced_main_final": rescue["replaced_main_final"]})
    write_csv(out / "rescue_summary.csv", summary_rows)
    status = "COMPUTED" if records and all(record["status"] == "COMPUTED" for record in records) else "PARTIAL"
    write_json(out / "run_manifest.json", {"run_id": out.name, "status": status, "main_roots": [str(root) for root in main_roots], "jobs": len(jobs), "completed_jobs": len(records), "summary_rows": len(summary_rows), "replaced_count": sum(row["replaced_main_final"] for row in summary_rows), "ended_at": time.time()})
    print(json.dumps({"run_id": out.name, "status": status, "jobs": len(jobs), "replaced_count": sum(row["replaced_main_final"] for row in summary_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
