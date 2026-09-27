#!/usr/bin/env python3
"""Run missing graph/core groups with the verified fast evaluator in parallel."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--parallel", type=int, default=16)
    args = parser.parse_args()
    main_root = args.main_root.resolve()
    output_root = args.output_root.resolve()
    if output_root.exists():
        raise SystemExit(f"refusing existing output: {output_root}")
    output_root.mkdir(parents=True)
    main_manifest = load(main_root / "run_manifest.json")
    jobs = []
    for batch in main_manifest["jobs"]:
        batch_root = Path(batch["output_root"])
        for case in batch["cases"]:
            case_root = batch_root / "cases" / case
            for cores in (1, 2, 3, 4, 5):
                missing = []
                for scene in ("A", "B", "C"):
                    if not (case_root / f"{cores}core" / scene / "final_selection.json").exists():
                        missing.append(scene)
                if missing:
                    jobs.append({
                        "case": case,
                        "cores": cores,
                        "missing_scenes": missing,
                        "source_batch": int(batch["batch"]),
                        "main_case_root": str(case_root),
                    })
    save(output_root / "job_plan.json", {"main_root": str(main_root), "jobs": jobs, "started_at": time.time()})
    solver_root = Path(__file__).resolve().parent / "solver_review_v7_20260926"
    evaluator = solver_root / "vendor/official_evaluator_fast"
    env = os.environ.copy()
    env.update({
        "HUAWEI_FAST_PROFILE": "1",
        "HUAWEI_EVALUATOR_DIR": str(evaluator),
        "PYTHONPATH": str(solver_root / "src"),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
    })

    def run(job):
        index = jobs.index(job)
        job_root = output_root / f"job_{index:03d}_{job['case']}_{job['cores']}core"
        log_path = output_root / f"job_{index:03d}_{job['case']}_{job['cores']}core.log"
        command = [
            sys.executable,
            str(solver_root / "scripts/run_experiment.py"),
            "--output-root", str(job_root),
            "--cases", job["case"],
            "--cores", str(job["cores"]),
            "--scenes", "A,B,C",
            "--full-candidates", "2",
            "--workers", "1",
        ]
        with log_path.open("w", encoding="utf-8") as log:
            code = subprocess.run(command, cwd=solver_root, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        return {**job, "output_root": str(job_root), "returncode": code}

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps({"case": result["case"], "cores": result["cores"], "returncode": result["returncode"]}, ensure_ascii=False), flush=True)
    status = "COMPUTED" if all(item["returncode"] == 0 for item in results) else "PARTIAL"
    save(output_root / "rescue_manifest.json", {
        "status": status,
        "main_root": str(main_root),
        "official_evaluator_dir": str(evaluator),
        "fast_profile": True,
        "jobs": sorted(results, key=lambda item: (item["case"], item["cores"])),
        "job_count": len(results),
        "ended_at": time.time(),
    })
    print(json.dumps({"status": status, "jobs": len(results)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
