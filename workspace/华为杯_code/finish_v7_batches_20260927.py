#!/usr/bin/env python3
"""Finish all v7 batches after taking over the queue dispatcher."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

SOLVER = Path(__file__).resolve().parent / "solver_review_v7_20260926"
sys.path.insert(0, str(SOLVER / "scripts"))
from run_full_matrix import ROOT, RUNNER, aggregate, solver_source_sha256, write_json

MAIN_ROOT = Path(
    "/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/"
    "v7_main_official_20260927_0010"
)


def child_status(job):
    path = Path(job["output_root"]) / "run_manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    initial = json.loads((MAIN_ROOT / "run_manifest.json").read_text(encoding="utf-8"))
    if initial["solver_source_sha256"] != solver_source_sha256():
        raise ValueError("v7 source differs from the recorded main run")
    jobs = initial["jobs"]
    pending = [job for job in jobs if child_status(job) is None]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT / "src"),
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
    })
    active = []
    for job in pending:
        log_path = MAIN_ROOT / f"batch_{job['batch']:02d}.takeover.console.log"
        log = log_path.open("w", encoding="utf-8")
        command = [
            sys.executable, str(RUNNER), "--output-root", job["output_root"],
            "--cases", ",".join(job["cases"]), "--cores", "1,2,3,4,5",
            "--scenes", "A,B,C", "--full-candidates", str(initial["full_candidates"]),
            "--workers", "1",
        ]
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, text=True)
        active.append((job, process, log, str(log_path)))
        print(json.dumps({"event": "started", "batch": job["batch"], "pid": process.pid}), flush=True)
    write_json(MAIN_ROOT / "takeover_manifest.json", {
        "status": "RUNNING", "started_at": time.time(), "pending_batches": [job["batch"] for job in pending],
        "pids": [process.pid for _job, process, _log, _path in active],
        "source_sha256": initial["solver_source_sha256"],
    })
    for job, process, log, _path in active:
        code = process.wait()
        log.close()
        print(json.dumps({"event": "finished", "batch": job["batch"], "returncode": code}), flush=True)
        if code != 0:
            raise RuntimeError(f"batch {job['batch']} exited with {code}")

    while True:
        current = [child_status(job) for job in jobs]
        if all(item is not None for item in current):
            break
        time.sleep(10)
    refreshed = json.loads((MAIN_ROOT / "run_manifest.json").read_text(encoding="utf-8"))
    write_json(MAIN_ROOT / "dispatcher_manifest_before_takeover_reconcile.json", refreshed)
    for job, item in zip(jobs, current):
        job["status"] = item["status"]
        job["returncode"] = 0 if item["status"] == "COMPUTED" else 1
        job["rows"] = item.get("rows", 0)
        job["status_counts"] = item.get("status_counts", {})
        if job["batch"] in {job2["batch"] for job2, _process, _log, _path in active}:
            job["log"] = str(MAIN_ROOT / f"batch_{job['batch']:02d}.takeover.console.log")
    merged = aggregate(MAIN_ROOT, jobs, initial["full_candidates"])
    write_json(MAIN_ROOT / "takeover_manifest.json", {
        "status": merged["status"], "rows": merged["rows"],
        "batches": len(jobs), "ended_at": time.time(),
    })
    print(json.dumps({"event": "reconciled", "status": merged["status"], "rows": merged["rows"]}), flush=True)


if __name__ == "__main__":
    main()
