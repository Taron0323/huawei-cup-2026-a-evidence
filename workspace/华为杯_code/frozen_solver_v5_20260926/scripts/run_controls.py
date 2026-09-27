#!/usr/bin/env python3
"""Run the three mechanism controls specified by the frozen A idea."""

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

from huawei_code.candidates import generate_candidates, local_variants  # noqa: E402
from huawei_code.graph import load_graph, static_view  # noqa: E402
from huawei_code.official import evaluate, load_modules, profile, read_config, summary  # noqa: E402
from huawei_code.plan import plan_key, seed_plans, validate_plan  # noqa: E402
from huawei_code.scoring import light_score  # noqa: E402


REPRESENTATIVE_CASES = ["case_051", "case_012", "case_067", "case_081", "case_016", "case_062"]
CONTROL_SCENES = {
    "no_receive_domain": ("A", "B"),
    "no_capacity_guidance": ("B",),
    "light_direct_select": ("A",),
}


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
        writer.writeheader()
        writer.writerows(rows)


def load_plan(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def choose_plans(view: dict, scene: str, cores: int, config: dict, control: str) -> list[tuple[str, dict, str]]:
    seeds = list(seed_plans(view, cores, scene).items())
    if control == "no_receive_domain":
        pool = [(name, plan, "seed_only") for name, plan in seeds]
    elif control == "no_capacity_guidance":
        pool = [(name, plan, "seed") for name, plan in seeds]
        for seed_name, seed in seeds:
            pool.extend((f"{seed_name}_{name}", plan, source) for name, plan, source in local_variants(view, seed, cores, scene) if source != "capacity")
    elif control == "light_direct_select":
        pool = [(item["candidate"], item["plan"], item["source"]) for item in generate_candidates(view, cores, scene, config)]
    else:
        raise ValueError(control)
    unique = {}
    for name, plan, source in pool:
        unique.setdefault(plan_key(plan), (name, plan, source))
    candidates = list(unique.values())
    if control == "light_direct_select":
        candidates.sort(key=lambda item: (tuple(light_score(view, item[1], scene, config)["score"]), item[0]))
    else:
        profiled = []
        modules = load_modules(evaluator_dir())
        for name, plan, source in candidates:
            try:
                profiled.append((profile(view["_graph"], plan, scene, config, modules)["profile_score"], name, plan, source))
            except Exception:
                pass
        profiled.sort(key=lambda item: (tuple(item[0]), item[1]))
        candidates = [(name, plan, source) for _score, name, plan, source in profiled]
    return candidates[:2]


def worker(job: dict) -> list[dict]:
    data = ROOT / "data/raw/A题/data"
    modules = load_modules(evaluator_dir())
    config = read_config(modules, data / "config.txt")
    graph = load_graph(data / f"{job['case']}.json")
    view = static_view(graph)
    view["_graph"] = graph
    plans = choose_plans(view, job["scene"], job["cores"], config, job["control"])
    rows = []
    for rank, (candidate, plan, source) in enumerate(plans, start=1):
        validate_plan(view, plan, job["cores"])
        started = time.perf_counter()
        try:
            result = evaluate(graph, plan, {"A": 1, "B": 2, "C": 3}[job["scene"]], config, modules)
            row = {
                "case": job["case"], "cores": job["cores"], "scene": job["scene"],
                "control": job["control"], "candidate": candidate, "source": source,
                "rank": rank, "status": "AI_VERIFIED", "plan_sha256": plan_key(plan),
                "evaluation_seconds": time.perf_counter() - started,
                "selection": rank == 1, "definition": job["definition"], **summary(result),
            }
        except Exception as exc:
            row = {
                "case": job["case"], "cores": job["cores"], "scene": job["scene"],
                "control": job["control"], "candidate": candidate, "source": source,
                "rank": rank, "status": "EVALUATION_FAILED", "plan_sha256": plan_key(plan),
                "evaluation_seconds": time.perf_counter() - started, "selection": False,
                "definition": job["definition"], "error_type": type(exc).__name__, "error": str(exc),
            }
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--parallel", type=int, default=8)
    args = parser.parse_args()
    out = args.output_root.resolve()
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    out.mkdir(parents=True)
    definitions = {
        "no_receive_domain": "Only the four deterministic seed plans are retained; no shared-input/domain-priority candidate portfolio is used. Official profile chooses the two evaluated plans.",
        "no_capacity_guidance": "Seed plans and non-capacity local edits are retained; capacity candidates and capacity source edits are excluded. Official profile chooses the two evaluated plans.",
        "light_direct_select": "The normal finite candidate portfolio is ranked directly by the light score; no official profile score is used for selection.",
    }
    jobs = []
    for control, scenes in CONTROL_SCENES.items():
        for case in REPRESENTATIVE_CASES:
            for cores in (2, 5):
                for scene in scenes:
                    jobs.append({"control": control, "case": case, "cores": cores, "scene": scene, "definition": definitions[control]})
    write_json(out / "run_manifest.json", {"run_id": out.name, "status": "RUNNING", "cases": REPRESENTATIVE_CASES, "cores": [2, 5], "controls": definitions, "jobs": len(jobs), "parallel": args.parallel, "official_evaluator_dir": str(evaluator_dir()), "started_at": time.time()})
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(worker, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            rows.extend(result)
            print(json.dumps({"control": result[0]["control"], "case": result[0]["case"], "cores": result[0]["cores"], "scene": result[0]["scene"], "statuses": [row["status"] for row in result]}, ensure_ascii=False), flush=True)
    write_csv(out / "controls.csv", rows)
    status = "COMPUTED" if rows and all(row["status"] == "AI_VERIFIED" for row in rows) else "PARTIAL"
    write_json(out / "run_manifest.json", {"run_id": out.name, "status": status, "cases": REPRESENTATIVE_CASES, "cores": [2, 5], "controls": definitions, "jobs": len(jobs), "rows": len(rows), "verified_rows": sum(row["status"] == "AI_VERIFIED" for row in rows), "ended_at": time.time()})
    print(json.dumps({"run_id": out.name, "status": status, "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
