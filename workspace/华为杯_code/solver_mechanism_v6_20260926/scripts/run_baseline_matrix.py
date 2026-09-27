#!/usr/bin/env python3
"""Run and aggregate the official single-core baselines in balanced batches."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_full_matrix import all_cases, case_size, split_balanced, write_json

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_singlecore_baseline.py"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cases")
    parser.add_argument("--batch-count", type=int, default=4)
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--evaluator-dir", type=Path, default=ROOT / "vendor/official_evaluator")
    args = parser.parse_args()
    root = args.output_root.resolve()
    if root.exists():
        raise SystemExit(f"refusing existing output: {root}")
    root.mkdir(parents=True)
    cases = all_cases(args.cases)
    batches_cases = split_balanced(cases, max(1, min(args.batch_count, len(cases))))
    jobs = []
    for index, batch_cases in enumerate(batches_cases, start=1):
        jobs.append({"batch": index, "cases": batch_cases, "output_root": str(root / f"batch_{index:02d}"), "log": str(root / f"batch_{index:02d}.console.log"), "status": "PENDING", "returncode": None})
    write_json(root / "case_sizes.json", {case: case_size(case) for case in cases})
    write_json(root / "run_manifest.json", {"run_id": root.name, "status": "RUNNING", "cases": cases, "batch_count": len(jobs), "parallel": args.parallel, "official_evaluator_dir": str(args.evaluator_dir.resolve()), "jobs": jobs, "started_at": time.time()})
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(ROOT / "src"), "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"})
    active = {}
    next_job = 0
    while next_job < len(jobs) or active:
        while next_job < len(jobs) and len(active) < max(1, args.parallel):
            job = jobs[next_job]
            command = [sys.executable, str(RUNNER), "--output-root", job["output_root"], "--cases", ",".join(job["cases"]), "--evaluator-dir", str(args.evaluator_dir.resolve())]
            log = open(job["log"], "w", encoding="utf-8")
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
            job["status"] = "RUNNING"
            active[next_job] = (process, log)
            next_job += 1
            print(json.dumps({"event": "started", "batch": job["batch"], "pid": process.pid}, ensure_ascii=False), flush=True)
        finished = []
        for slot, (process, log) in active.items():
            returncode = process.poll()
            if returncode is None:
                continue
            log.close()
            job = jobs[slot]
            job["returncode"] = returncode
            child_path = Path(job["output_root"]) / "run_manifest.json"
            if child_path.exists():
                child = json.loads(child_path.read_text(encoding="utf-8"))
                job["status"] = child.get("status", "UNKNOWN")
                job["rows"] = child.get("rows", 0)
            else:
                job["status"] = "FAILED"
            finished.append(slot)
            print(json.dumps({"event": "finished", "batch": job["batch"], "status": job["status"], "returncode": returncode}, ensure_ascii=False), flush=True)
        for slot in finished:
            del active[slot]
        if active:
            time.sleep(2)
    rows = []
    for job in jobs:
        path = Path(job["output_root"]) / "metrics.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                row["batch"] = job["batch"]
                rows.append(row)
    fields = sorted({key for row in rows for key in row})
    with (root / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {"run_id": root.name, "status": "COMPUTED" if jobs and all(job["status"] == "COMPUTED" and job["returncode"] == 0 for job in jobs) else "PARTIAL", "cases": cases, "rows": len(rows), "official_evaluator_dir": str(args.evaluator_dir.resolve()), "batches": jobs, "ended_at": time.time()}
    write_json(root / "run_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
