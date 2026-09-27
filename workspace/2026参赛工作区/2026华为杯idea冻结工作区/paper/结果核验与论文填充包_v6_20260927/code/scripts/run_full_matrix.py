#!/usr/bin/env python3
"""Run and aggregate the 100-graph A/B/C main matrix in resumable batches."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/A题/data"
RUNNER = ROOT / "scripts/run_experiment.py"


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def solver_source_sha256() -> dict[str, str]:
    paths = [
        ROOT / "scripts/run_experiment.py",
        ROOT / "scripts/run_full_matrix.py",
        ROOT / "src/huawei_code/candidates.py",
        ROOT / "src/huawei_code/official.py",
        ROOT / "src/huawei_code/plan.py",
        ROOT / "src/huawei_code/scoring.py",
        ROOT / "src/huawei_code/verification.py",
        ROOT / "src/huawei_code/gpu_score.py",
    ]
    return {str(path.relative_to(ROOT)): file_sha(path) for path in paths}


def case_size(case: str) -> int:
    payload = json.loads((DATA / f"{case}.json").read_text(encoding="utf-8"))
    ops = payload.get("operations", payload.get("ops", []))
    if isinstance(ops, dict):
        ops = ops.values()
    return sum(1 for op in ops if str(op.get("op", "")).upper() not in {"COPY", "COPY_IN", "COPY_OUT"} and int(op.get("cycles", 0) or 0) > 0)


def all_cases(raw: str | None) -> list[str]:
    if raw:
        return [item if item.startswith("case_") else f"case_{int(item):03d}" for item in raw.split(",")]
    return [f"case_{index:03d}" for index in range(1, 101)]


def split_balanced(cases: list[str], count: int) -> list[list[str]]:
    bins = [[0, []] for _ in range(count)]
    for case in sorted(cases, key=lambda item: (-case_size(item), item)):
        target = min(range(count), key=lambda index: (bins[index][0], index))
        bins[target][0] += case_size(case)
        bins[target][1].append(case)
    return [sorted(values[1]) for values in bins if values[1]]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def aggregate(root: Path, batches: list[dict], full_candidates: int) -> dict:
    rows = []
    for batch in batches:
        metrics = Path(batch["output_root"]) / "metrics.csv"
        if not metrics.exists():
            continue
        with metrics.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                row["batch"] = batch["batch"]
                rows.append(row)
    fields = sorted({key for row in rows for key in row})
    if fields:
        with (root / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    status_counts = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    all_computed = bool(batches) and all(batch.get("status") == "COMPUTED" and batch.get("returncode") == 0 for batch in batches)
    manifest = {
        "run_id": root.name,
        "status": "COMPUTED" if all_computed else "PARTIAL",
        "cases": sorted({case for batch in batches for case in batch["cases"]}),
        "case_count": len({case for batch in batches for case in batch["cases"]}),
        "cores": [1, 2, 3, 4, 5],
        "scenes": ["A", "B", "C"],
        "full_candidates": full_candidates,
        "solver_source_sha256": solver_source_sha256(),
        "config_sha256": file_sha(DATA / "config.txt"),
        "matrix_note": "A includes 1-core rows as a baseline; formal Q1 summaries use A cores 2-5.",
        "batches": batches,
        "rows": len(rows),
        "status_counts": status_counts,
        "ended_at": time.time(),
    }
    write_json(root / "run_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cases")
    parser.add_argument("--batch-count", type=int, default=4)
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--full-candidates", type=int, default=2)
    args = parser.parse_args()
    root = args.output_root.resolve()
    if root.exists():
        raise SystemExit(f"refusing existing output: {root}")
    root.mkdir(parents=True)
    cases = all_cases(args.cases)
    batches_cases = split_balanced(cases, max(1, min(args.batch_count, len(cases))))
    write_json(root / "case_sizes.json", {case: case_size(case) for case in cases})
    jobs = []
    for index, batch_cases in enumerate(batches_cases, start=1):
        batch_root = root / f"batch_{index:02d}"
        log_path = root / f"batch_{index:02d}.console.log"
        jobs.append({"batch": index, "cases": batch_cases, "output_root": str(batch_root), "log": str(log_path), "status": "PENDING", "returncode": None})
    write_json(root / "run_manifest.json", {"run_id": root.name, "status": "RUNNING", "cases": cases, "batch_count": len(jobs), "parallel": args.parallel, "full_candidates": args.full_candidates, "solver_source_sha256": solver_source_sha256(), "config_sha256": file_sha(DATA / "config.txt"), "jobs": jobs, "started_at": time.time()})

    env = os.environ.copy()
    env.update({"PYTHONPATH": str(ROOT / "src"), "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"})
    active: dict[int, tuple[subprocess.Popen, object]] = {}
    next_job = 0
    while next_job < len(jobs) or active:
        while next_job < len(jobs) and len(active) < max(1, args.parallel):
            job = jobs[next_job]
            command = [sys.executable, str(RUNNER), "--output-root", job["output_root"], "--cases", ",".join(job["cases"]), "--cores", "1,2,3,4,5", "--scenes", "A,B,C", "--full-candidates", str(args.full_candidates), "--workers", "1"]
            log = open(job["log"], "w", encoding="utf-8")
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
            job["status"] = "RUNNING"
            active[next_job] = (process, log)
            next_job += 1
            print(json.dumps({"event": "started", "batch": job["batch"], "cases": job["cases"], "pid": process.pid}, ensure_ascii=False), flush=True)
        finished = []
        for slot, (process, log) in active.items():
            returncode = process.poll()
            if returncode is None:
                continue
            log.close()
            job = jobs[slot]
            job["returncode"] = returncode
            child_manifest = Path(job["output_root"]) / "run_manifest.json"
            if child_manifest.exists():
                child = json.loads(child_manifest.read_text(encoding="utf-8"))
                job["status"] = child.get("status", "UNKNOWN")
                job["rows"] = child.get("rows", 0)
                job["status_counts"] = child.get("status_counts", {})
            else:
                job["status"] = "FAILED"
            finished.append(slot)
            print(json.dumps({"event": "finished", "batch": job["batch"], "status": job["status"], "returncode": returncode}, ensure_ascii=False), flush=True)
        for slot in finished:
            del active[slot]
        if active:
            time.sleep(2)
    aggregate(root, jobs, args.full_candidates)
    print(json.dumps(json.loads((root / "run_manifest.json").read_text(encoding="utf-8")), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
