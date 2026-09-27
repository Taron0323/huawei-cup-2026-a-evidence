#!/usr/bin/env python3
"""Run the official single-core baseline for a set of raw graphs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huawei_code.official import file_sha, load_modules, read_config, summary  # noqa: E402


def cases_arg(raw: str | None) -> list[str]:
    if raw:
        return [item if item.startswith("case_") else f"case_{int(item):03d}" for item in raw.split(",")]
    return [f"case_{index:03d}" for index in range(1, 101)]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cases")
    parser.add_argument("--evaluator-dir", type=Path, default=ROOT / "vendor/official_evaluator")
    args = parser.parse_args()
    output = args.output_root.resolve()
    if output.exists():
        raise SystemExit(f"refusing existing output: {output}")
    output.mkdir(parents=True)
    data = ROOT / "data/raw/A题/data"
    official_dir = args.evaluator_dir.resolve()
    modules = load_modules(official_dir)
    import importlib
    singlecore = importlib.import_module("singlecore_evaluate")
    config = read_config(modules, data / "config.txt")
    cases = cases_arg(args.cases)
    manifest = {"run_id": output.name, "status": "RUNNING", "cases": cases, "official_evaluator_dir": str(official_dir), "official_code_sha256": {path.name: file_sha(path) for path in sorted(official_dir.glob("*.py"))}, "started_at": time.time()}
    write_json(output / "run_manifest.json", manifest)
    rows = []
    for case in cases:
        graph_path = data / f"{case}.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        case_out = output / "cases" / case
        started = time.perf_counter()
        try:
            result = singlecore.evaluate_singlecore(graph, bandwidth=config["bandwidth"], capacity=config["capacity"], cross_core_wait=0, same_core_wait=0)
            elapsed = time.perf_counter() - started
            write_json(case_out / "result.json", result)
            row = {"case": case, "status": "AI_VERIFIED", "elapsed_seconds": elapsed, **summary(result)}
        except Exception as exc:
            elapsed = time.perf_counter() - started
            failure = {"case": case, "status": "EVALUATION_FAILED", "error_type": type(exc).__name__, "error": str(exc), "elapsed_seconds": elapsed}
            write_json(case_out / "failure.json", failure)
            row = failure
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    fields = sorted({key for row in rows for key in row})
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest.update({"status": "COMPUTED" if all(row["status"] == "AI_VERIFIED" for row in rows) else "PARTIAL", "rows": len(rows), "ended_at": time.time()})
    write_json(output / "run_manifest.json", manifest)
    print(json.dumps({"run_id": output.name, "status": manifest["status"], "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
