#!/usr/bin/env python3
"""Start four queued v7 batches and reconcile the main run after completion."""

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
PARENT_PID = 13980


def main() -> None:
    initial = json.loads((MAIN_ROOT / "run_manifest.json").read_text(encoding="utf-8"))
    if initial["solver_source_sha256"] != solver_source_sha256():
        raise ValueError("v7 source differs from the running parent")
    jobs = initial["jobs"]
    extra = jobs[10:14]
    if len(extra) != 4 or any(Path(job["output_root"]).exists() for job in extra):
        raise ValueError("batches 11-14 must be unstarted")

    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT / "src"),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
    })
    active = []
    for job in extra:
        log_path = MAIN_ROOT / f"batch_{job['batch']:02d}.manual.console.log"
        log = log_path.open("w", encoding="utf-8")
        command = [
            sys.executable, str(RUNNER), "--output-root", job["output_root"],
            "--cases", ",".join(job["cases"]), "--cores", "1,2,3,4,5",
            "--scenes", "A,B,C", "--full-candidates",
            str(initial["full_candidates"]), "--workers", "1",
        ]
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True
        )
        active.append((job, process, log, str(log_path)))
        print(json.dumps({"batch": job["batch"], "pid": process.pid}), flush=True)

    record = {
        "status": "RUNNING",
        "parent_pid": PARENT_PID,
        "original_parallel": initial["parallel"],
        "effective_parallel": 12,
        "solver_source_sha256": initial["solver_source_sha256"],
        "batches": [{"batch": job["batch"], "pid": process.pid, "log": log_path}
                    for job, process, _log, log_path in active],
        "started_at": time.time(),
    }
    write_json(MAIN_ROOT / "manual_acceleration_manifest.json", record)

    for job, process, log, _log_path in active:
        code = process.wait()
        log.close()
        print(json.dumps({"batch": job["batch"], "returncode": code}), flush=True)
        if code != 0:
            raise RuntimeError(f"batch {job['batch']} exited with {code}")
    while os.system(f"kill -0 {PARENT_PID} 2>/dev/null") == 0:
        time.sleep(10)

    parent_manifest = json.loads((MAIN_ROOT / "run_manifest.json").read_text(encoding="utf-8"))
    write_json(MAIN_ROOT / "parent_manifest_after_acceleration.json", parent_manifest)
    for job in jobs:
        child = json.loads((Path(job["output_root"]) / "run_manifest.json").read_text(encoding="utf-8"))
        job["status"] = child["status"]
        job["returncode"] = 0
        job["rows"] = child.get("rows", 0)
        job["status_counts"] = child.get("status_counts", {})
        if job in extra:
            job["log"] = str(MAIN_ROOT / f"batch_{job['batch']:02d}.manual.console.log")
    merged = aggregate(MAIN_ROOT, jobs, initial["full_candidates"])
    record.update({"status": merged["status"], "rows": merged["rows"], "ended_at": time.time()})
    write_json(MAIN_ROOT / "manual_acceleration_manifest.json", record)
    print(json.dumps({"status": merged["status"], "rows": merged["rows"]}), flush=True)


if __name__ == "__main__":
    main()
