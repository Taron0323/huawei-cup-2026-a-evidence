#!/usr/bin/env python3
"""Run a bounded V0.7.1 smoke trial in a new results directory.

This entry point exercises the §11 static views, seed plans, official profile
bridge, and complete evaluator.  It never writes to the supplied attachment or
to a previous run directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_CODE = ROOT / "inputs/raw/A题/附件/code"
DATA_ROOT = ROOT / "inputs/raw/A题/附件/data"
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "src/a_solver"))
from v071_official_bridge import evaluate_plan, load_official_modules, profile_plan, read_config, result_summary  # noqa: E402
from v071_plan_search import build_seed_set  # noqa: E402
from v071_static_graph import build_static_views, load_case  # noqa: E402
from verify import check_plan, check_result  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def parse_cases(raw: str) -> list[str]:
    return [item if item.startswith("case_") else f"case_{int(item):03d}" for item in raw.split(",")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cases", default="case_001")
    parser.add_argument("--cores", default="1,2")
    parser.add_argument("--scenes", default="A,B,C")
    parser.add_argument("--seeds", default="A0,A1,B0,B1")
    args = parser.parse_args()
    output = args.output_root.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {output}")
    output.mkdir(parents=True)
    modules = load_official_modules(RAW_CODE)
    config = read_config(modules, DATA_ROOT / "config.txt")
    cases = parse_cases(args.cases)
    cores = [int(value) for value in args.cores.split(",")]
    scenes = [value.strip().upper() for value in args.scenes.split(",")]
    seeds = [value.strip().upper() for value in args.seeds.split(",")]
    started = time.perf_counter()
    manifest = {
        "run_id": output.name,
        "status": "RUNNING",
        "command": sys.argv,
        "cases": cases,
        "cores": cores,
        "scenes": scenes,
        "seeds": seeds,
        "config_sha256": sha(DATA_ROOT / "config.txt"),
        "official_code_sha256": {path.name: sha(path) for path in sorted(RAW_CODE.glob("*.py"))},
        "source": "V0.7.1 independent smoke entry; official evaluator remains authoritative",
    }
    save(output / "run_manifest.json", manifest)
    metrics = []
    for case in cases:
        graph_path = DATA_ROOT / f"{case}.json"
        if not graph_path.is_file():
            raise SystemExit(f"missing case: {graph_path}")
        graph = load_case(graph_path)
        view = build_static_views(graph)
        # The order generator keeps operations internal-only; attach raw ops for
        # local seed construction, then omit it from the persisted static view.
        view["_ops"] = {int(op["id"]): op for op in graph.get("ops", [])}
        persisted = {key: value for key, value in view.items() if key != "_ops"}
        save(output / "static" / f"{case}.json", persisted)
        for core_count in cores:
            scene_seed_sets = {}
            for scene in scenes:
                scene_seed_sets[scene] = build_seed_set(view, core_count, scene)
            for seed_name in seeds:
                scene = "A" if seed_name.startswith("A") else "B"
                if scene not in scenes:
                    continue
                plan = scene_seed_sets[scene][seed_name]
                for eval_scene in scenes:
                    run_dir = output / "runs" / case / f"{core_count}core" / seed_name / eval_scene
                    save(run_dir / "plan.json", plan)
                    plan_check = check_plan(graph, plan)
                    save(run_dir / "plan_check.json", plan_check)
                    domain = __import__("v071_static_graph").compute_domain_bytes(view, plan, eval_scene)
                    save(run_dir / "domain.json", domain)
                    profile_started = time.perf_counter()
                    profile = profile_plan(graph, plan, eval_scene, config, modules)
                    profile["elapsed_seconds"] = round(time.perf_counter() - profile_started, 6)
                    save(run_dir / "profile.json", profile)
                    result_started = time.perf_counter()
                    result = evaluate_plan(graph, plan, {"A": 1, "B": 2, "C": 3}[eval_scene], config, modules)
                    elapsed = time.perf_counter() - result_started
                    save(run_dir / "result.json", result)
                    result_check = check_result(graph, plan, result)
                    save(run_dir / "result_check.json", result_check)
                    summary = result_summary(result, eval_scene)
                    summary.update({"case": case, "cores": core_count, "seed": seed_name, "elapsed_seconds": round(elapsed, 6), "profile_seconds": profile["elapsed_seconds"], "result_file": str((run_dir / "result.json").relative_to(output))})
                    metrics.append(summary)
                    print(json.dumps(summary, ensure_ascii=False), flush=True)
    save(output / "metrics.json", metrics)
    manifest.update({"status": "AI_VERIFIED", "rows": len(metrics), "elapsed_seconds": round(time.perf_counter() - started, 3)})
    save(output / "run_manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
