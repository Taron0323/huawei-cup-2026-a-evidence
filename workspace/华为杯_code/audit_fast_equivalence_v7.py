#!/usr/bin/env python3
"""Compare the accelerated evaluator with original-evaluator v7 results."""

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent / "solver_review_v7_20260926"
sys.path.insert(0, str(ROOT / "src"))
from huawei_code.graph import load_graph
from huawei_code.official import evaluate, load_modules, read_config, summary


def collect(old_root: Path, limit: int) -> list[dict]:
    paths = sorted(old_root.glob("batch_*/cases/*/*core/*/final_selection.json"))
    by_key = {}
    for path in paths:
        scene_root = path.parent
        selection = json.loads(path.read_text(encoding="utf-8"))
        candidate_dir = scene_root / "candidates" / selection["candidate"]
        result_path = candidate_dir / "result.json"
        plan_path = candidate_dir / "plan.json"
        if not (result_path.exists() and plan_path.exists()):
            continue
        key = (scene_root.parent.parent.name, int(scene_root.parent.name[:-4]), scene_root.name)
        by_key[key] = {"selection": selection, "result": result_path, "plan": plan_path}
    keys = sorted(by_key)
    if len(keys) <= limit:
        chosen = keys
    else:
        stride = len(keys) / limit
        chosen = [keys[min(len(keys) - 1, int(index * stride))] for index in range(limit)]
        chosen = list(dict.fromkeys(chosen))
    return [{"case": key[0], "cores": key[1], "scene": key[2], **by_key[key]} for key in chosen]


def worker(item: dict) -> dict:
    data = ROOT / "data/raw/A题/data"
    modules = load_modules(ROOT / "vendor/official_evaluator_fast")
    config = read_config(modules, data / "config.txt")
    graph = load_graph(data / f"{item['case']}.json")
    plan = json.loads(Path(item["plan"]).read_text(encoding="utf-8"))
    original = json.loads(Path(item["result"]).read_text(encoding="utf-8"))
    started = time.perf_counter()
    accelerated = evaluate(graph, plan, {"A": 1, "B": 2, "C": 3}[item["scene"]], config, modules)
    left, right = summary(original), summary(accelerated)
    return {"case": item["case"], "cores": item["cores"], "scene": item["scene"], "candidate": item["selection"]["candidate"], "elapsed_seconds": time.perf_counter() - started, "same": left == right, "original": left, "accelerated": right}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--parallel", type=int, default=4)
    args = parser.parse_args()
    items = collect(args.original_root.resolve(), args.limit)
    with ProcessPoolExecutor(max_workers=args.parallel) as pool:
        rows = list(pool.map(worker, items))
    mismatches = [row for row in rows if not row["same"]]
    report = {"status": "MATCH" if not mismatches else "MISMATCH", "sampled_pairs": len(rows), "mismatches": mismatches, "comparisons": rows, "original_root": str(args.original_root.resolve()), "accelerated_evaluator": str(ROOT / "vendor/official_evaluator_fast")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "sampled_pairs": len(rows), "mismatches": len(mismatches)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
