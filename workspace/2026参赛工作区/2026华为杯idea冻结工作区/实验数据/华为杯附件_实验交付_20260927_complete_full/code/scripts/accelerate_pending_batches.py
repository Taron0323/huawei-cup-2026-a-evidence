#!/usr/bin/env python3
"""Start the four queued v6 batches now and reconcile the parent manifest."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_full_matrix import ROOT, RUNNER, aggregate, solver_source_sha256, write_json


MAIN_ROOT = Path("/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/v6_main_2call_20260926_2230")
PARENT_PID = 6755


def parent_running() -> bool:
    try:
        os.kill(PARENT_PID, 0)
        return True
    except ProcessLookupError:
        return False


def main() -> None:
    initial = json.loads((MAIN_ROOT / "run_manifest.json").read_text(encoding="utf-8"))
    if initial["solver_source_sha256"] != solver_source_sha256():
        raise ValueError("main solver source differs from the running parent")
    jobs = initial["jobs"]
    pending = jobs[12:]
    if len(pending) != 4 or any(Path(job["output_root"]).exists() for job in pending):
        raise ValueError("the expected four pending batch roots are not all free")
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT / "src"),
        "HUAWEI_EVALUATOR_DIR": str(ROOT / "vendor/official_evaluator_fast"),
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
    })
    active = []
    for job in pending:
        log_path = MAIN_ROOT / f"batch_{job['batch']:02d}.manual.console.log"
        log = log_path.open("w", encoding="utf-8")
        command = [sys.executable, str(RUNNER), "--output-root", job["output_root"], "--cases", ",".join(job["cases"]), "--cores", "1,2,3,4,5", "--scenes", "A,B,C", "--full-candidates", str(initial["full_candidates"]), "--workers", "1"]
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
        active.append((job, process, log, log_path))
        print(json.dumps({"event": "manual_batch_started", "batch": job["batch"], "pid": process.pid, "cases": job["cases"]}, ensure_ascii=False), flush=True)
    record = {"status": "RUNNING", "reason": "use four idle CPU slots while the original parent runs twelve batches", "original_parallel": initial["parallel"], "effective_parallel": 16, "parent_pid": PARENT_PID, "solver_source_sha256": initial["solver_source_sha256"], "batches": [{"batch": job["batch"], "pid": process.pid, "cases": job["cases"], "log": str(log_path)} for job, process, _log, log_path in active], "started_at": time.time()}
    write_json(MAIN_ROOT / "manual_acceleration_manifest.json", record)
    for job, process, log, _log_path in active:
        code = process.wait()
        log.close()
        print(json.dumps({"event": "manual_batch_finished", "batch": job["batch"], "returncode": code}, ensure_ascii=False), flush=True)
        if code != 0:
            raise RuntimeError(f"manual batch {job['batch']} failed with exit code {code}")
    while parent_running():
        time.sleep(10)
    parent_manifest = json.loads((MAIN_ROOT / "run_manifest.json").read_text(encoding="utf-8"))
    write_json(MAIN_ROOT / "parent_manifest_after_acceleration.json", parent_manifest)
    for job in jobs:
        child = json.loads((Path(job["output_root"]) / "run_manifest.json").read_text(encoding="utf-8"))
        job["status"] = child["status"]
        job["returncode"] = 0 if child["status"] == "COMPUTED" else 1
        job["rows"] = child.get("rows", 0)
        job["status_counts"] = child.get("status_counts", {})
        if job["batch"] >= 13:
            job["log"] = str(MAIN_ROOT / f"batch_{job['batch']:02d}.manual.console.log")
    merged = aggregate(MAIN_ROOT, jobs, initial["full_candidates"])
    record.update({"status": merged["status"], "parent_status_before_reconciliation": parent_manifest["status"], "reconciled_batches": len(jobs), "ended_at": time.time()})
    write_json(MAIN_ROOT / "manual_acceleration_manifest.json", record)
    print(json.dumps({"event": "main_reconciled", "status": merged["status"], "batches": len(jobs), "rows": merged["rows"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
