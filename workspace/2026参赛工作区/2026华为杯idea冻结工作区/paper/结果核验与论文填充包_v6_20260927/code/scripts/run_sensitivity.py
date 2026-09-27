#!/usr/bin/env python3
"""Run the six-graph Problem-3 cache capacity/bandwidth sensitivity study."""

from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from huawei_code.candidates import event_timing_variants, generate_candidates, search_representatives
from huawei_code.graph import load_graph, static_view
from huawei_code.gpu_score import backend_info, rank_load_vectors
from huawei_code.official import evaluate, load_modules, read_config, summary
from huawei_code.plan import plan_key
from scripts.run_experiment import add_candidate, c_representatives, normalize_cache_events, profile_item

REPRESENTATIVE_CASES = ["case_051", "case_012", "case_067", "case_081", "case_016", "case_062"]
VARIANTS = ["cache_capacity_half", "cache_capacity_double", "cache_bandwidth_half", "cache_bandwidth_double"]


def evaluator_dir() -> Path:
    return Path(os.environ.get(
        "HUAWEI_EVALUATOR_DIR", str(ROOT / "vendor/official_evaluator_fast"))).resolve()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def config_variant(config: dict, variant: str) -> dict:
    value = json.loads(json.dumps(config))
    if variant == "cache_capacity_half":
        value["cache"]["capacity"] //= 2
    elif variant == "cache_capacity_double":
        value["cache"]["capacity"] *= 2
    elif variant == "cache_bandwidth_half":
        value["cache"]["bandwidth"] /= 2
    elif variant == "cache_bandwidth_double":
        value["cache"]["bandwidth"] *= 2
    return value


def worker(job: dict) -> dict:
    data = ROOT / "data/raw/A题/data"
    modules = load_modules(evaluator_dir())
    config = config_variant(read_config(modules, data / "config.txt"), job["variant"])
    graph = load_graph(data / f"{job['case']}.json")
    records = []

    def measure(candidate: str, plan: dict, source: str, rank: int | None = None) -> dict | None:
        started = time.perf_counter()
        try:
            result = evaluate(graph, plan, 3, config, modules)
            elapsed = time.perf_counter() - started
            records.append({"case": job["case"], "variant": job["variant"], "mode": job["mode"], "candidate": candidate, "source": source, "status": "AI_VERIFIED", "plan_sha256": plan_key(plan), "evaluation_seconds": elapsed, "gpu_backend": job.get("gpu_backend", backend_info().get("backend")), "gpu_rank": rank, **summary(result), "result": result, "plan": plan})
            return result
        except Exception as exc:
            records.append({"case": job["case"], "variant": job["variant"], "mode": job["mode"], "candidate": candidate, "source": source, "status": "EVALUATION_FAILED", "plan_sha256": plan_key(plan), "error_type": type(exc).__name__, "error": str(exc), "plan": plan})
            return None

    if job["mode"] == "fixed_plan":
        measure("fixed_B_plan", job["plan"], "fixed")
    else:
        view = static_view(graph)
        scene_out = Path(job["output_root"]) / "reoptimized" / job["case"] / job["variant"]
        generated = generate_candidates(view, 5, "C", config, base_plan=job["plan"])
        vectors = [list(item["light"]["loads"].values()) + [0] * max(0, 5 - len(item["light"]["loads"])) for item in generated]
        gpu_order, gpu_info = rank_load_vectors(vectors) if vectors else ([], backend_info())
        job["gpu_backend"] = gpu_info.get("backend")
        for rank, index in enumerate(gpu_order):
            generated[index]["gpu_load_rank"] = rank
        incumbent = next(item for item in generated if plan_key(item["plan"]) == plan_key(job["plan"]))
        incumbent["source"] = "incumbent"
        profile_item(incumbent, graph=graph, view=view, scene="C", cores=5, config=config, modules=modules, scene_out=scene_out)
        initial = measure(incumbent["candidate"], incumbent["plan"], "incumbent", incumbent.get("gpu_load_rank"))
        if initial is not None:
            seen = {plan_key(item["plan"]) for item in generated}
            events = normalize_cache_events(initial.get("cache_events", []), incumbent["profile"])
            for name, plan, source in event_timing_variants(view, job["plan"], 5, events, config):
                add_candidate(generated, seen, name, plan, source, view, "C", config)
            ordinary, capacity, scored = search_representatives(view, incumbent, 5, "C", config)
            write_json(scene_out / "local_search.json", {"scored_candidates": len(scored), "ordinary": ordinary["candidate"] if ordinary else None, "capacity": capacity["candidate"] if capacity else None})
            for representative, source in ((ordinary, "ordinary_chain"), (capacity, "capacity_representative")):
                if representative is not None:
                    add_candidate(generated, seen, representative["candidate"], representative["plan"], source, view, "C", config)
            selected = c_representatives(generated, incumbent, graph=graph, view=view, cores=5, config=config, modules=modules, scene_out=scene_out)
            if selected:
                item = selected[0]
                measure(item["candidate"], item["plan"], item["source"], item.get("gpu_load_rank"))
    if job["mode"] == "reoptimized":
        successful = [row for row in records if row["status"] == "AI_VERIFIED"]
        if successful:
            best = min(successful, key=lambda row: (row["makespan"], row["added_copy_bytes"], row["candidate"]))
            for row in records:
                row["selected"] = row is best
    return {"job": job, "records": records}


def find_b_plan(main_roots: list[Path], case: str) -> dict:
    for main_root in main_roots:
        paths = []
        for pattern in (
            f"batch_*/cases/{case}/5core/B/final_selection.json",
            f"case_*_5core/cases/{case}/5core/B/final_selection.json",
            f"cases/{case}/5core/B/final_selection.json",
        ):
            paths.extend(main_root.glob(pattern))
        for path in sorted(paths):
            selection = json.loads(path.read_text(encoding="utf-8"))
            plan_path = path.parent / "candidates" / selection["candidate"] / "plan.json"
            if plan_path.exists():
                return json.loads(plan_path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"missing B final plan for {case}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-root", type=Path)
    parser.add_argument("--main-roots", type=Path, nargs="+")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--wait-for-plans", action="store_true")
    args = parser.parse_args()
    main_roots = [path.resolve() for path in (args.main_roots or ([args.main_root] if args.main_root else []))]
    if not main_roots:
        parser.error("one of --main-root or --main-roots is required")
    out = args.output_root.resolve()
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    out.mkdir(parents=True)
    manifest = {"run_id": out.name, "status": "RUNNING", "main_roots": [str(root) for root in main_roots], "cases": REPRESENTATIVE_CASES, "variants": VARIANTS, "jobs": len(REPRESENTATIVE_CASES) * len(VARIANTS) * 2, "parallel": args.parallel, "official_evaluator_dir": str(evaluator_dir()), "started_at": time.time()}
    write_json(out / "run_manifest.json", manifest)
    records = []
    pending_cases = set(REPRESENTATIVE_CASES)
    with ProcessPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = set()
        while pending_cases or futures:
            for case in sorted(pending_cases):
                try:
                    plan = find_b_plan(main_roots, case)
                except FileNotFoundError:
                    if not args.wait_for_plans:
                        raise
                    continue
                pending_cases.remove(case)
                for variant in VARIANTS:
                    for mode in ("fixed_plan", "reoptimized"):
                        job = {"case": case, "variant": variant, "mode": mode, "plan": plan, "output_root": str(out)}
                        futures.add(pool.submit(worker, job))
                print(json.dumps({"event": "b_plan_ready", "case": case, "jobs_submitted": 8}, ensure_ascii=False), flush=True)
            if not futures:
                time.sleep(5)
                continue
            completed, futures = wait(futures, timeout=5, return_when=FIRST_COMPLETED)
            for future in completed:
                result = future.result()
                for row in result["records"]:
                    path = out / row["mode"] / row["case"] / row["variant"] / row["candidate"]
                    if "result" in row:
                        write_json(path / "result.json", row.pop("result"))
                    write_json(path / "plan.json", row.pop("plan"))
                    records.append(row)
                print(json.dumps({"case": result["job"]["case"], "variant": result["job"]["variant"], "mode": result["job"]["mode"], "status": [r["status"] for r in result["records"]]}, ensure_ascii=False), flush=True)
    fixed = [row for row in records if row["mode"] == "fixed_plan"]
    reopt = [row for row in records if row["mode"] == "reoptimized"]
    write_csv(out / "fixed_plan.csv", fixed)
    write_csv(out / "reoptimized.csv", reopt)
    selected_groups = {(row["case"], row["variant"]) for row in reopt if row.get("selected")}
    status = "COMPUTED" if len(fixed) == 24 and all(row["status"] == "AI_VERIFIED" for row in fixed) and len(selected_groups) == 24 else "PARTIAL"
    manifest = {"run_id": out.name, "status": status, "main_roots": [str(root) for root in main_roots], "cases": REPRESENTATIVE_CASES, "variants": VARIANTS, "fixed_rows": len(fixed), "reoptimized_rows": len(reopt), "selected_reoptimized_groups": len(selected_groups), "records": len(records), "ended_at": time.time()}
    write_json(out / "run_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
