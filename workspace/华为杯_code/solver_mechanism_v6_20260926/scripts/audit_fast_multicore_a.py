#!/usr/bin/env python3
"""Compare selected multi-core A plans under the original and fast evaluators."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huawei_code.graph import load_graph  # noqa: E402
from huawei_code.official import evaluate, load_modules, read_config, summary  # noqa: E402

PAIRS = (("case_051", 2), ("case_051", 5), ("case_067", 2),
         ("case_067", 5), ("case_016", 5))


def worker(main_root: Path, evaluator_dir: Path) -> list[dict]:
    modules = load_modules(evaluator_dir)
    config = read_config(modules, ROOT / "data/raw/A题/data/config.txt")
    rows = []
    for case, cores in PAIRS:
        plan_path = next(main_root.glob(f"batch_*/cases/{case}/{cores}core/A/final_plan.json"))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        graph = load_graph(ROOT / "data/raw/A题/data" / f"{case}.json")
        result = evaluate(graph, plan, 1, config, modules)
        canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        rows.append({"case": case, "cores": cores, "summary": summary(result),
                     "result_sha256": hashlib.sha256(canonical.encode()).hexdigest()})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker-dir", type=Path)
    args = parser.parse_args()
    main_root = args.main_root.resolve()
    if args.worker_dir:
        print(json.dumps(worker(main_root, args.worker_dir.resolve()), ensure_ascii=False))
        return
    runs = {}
    for name in ("official_evaluator", "official_evaluator_fast"):
        evaluator = ROOT / "vendor" / name
        completed = subprocess.run(
            [sys.executable, __file__, "--main-root", str(main_root),
             "--output", str(args.output), "--worker-dir", str(evaluator)],
            check=True, capture_output=True, text=True,
        )
        runs[name] = json.loads(completed.stdout)
    comparisons = []
    for original, fast in zip(runs["official_evaluator"], runs["official_evaluator_fast"]):
        comparisons.append({"case": original["case"], "cores": original["cores"],
                            "summary_match": original["summary"] == fast["summary"],
                            "full_result_match": original["result_sha256"] == fast["result_sha256"],
                            "original": original, "fast": fast})
    report = {"status": "MATCH" if all(row["summary_match"] and row["full_result_match"] for row in comparisons) else "MISMATCH",
              "sampled_pairs": len(comparisons), "comparisons": comparisons}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "sampled_pairs": len(comparisons)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
