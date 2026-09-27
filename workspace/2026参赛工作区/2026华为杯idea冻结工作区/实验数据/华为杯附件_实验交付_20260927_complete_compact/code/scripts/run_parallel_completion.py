#!/usr/bin/env python3
"""Complete missing graph/core combinations as independent A/B/C jobs.

The original matrix runs core counts serially inside one graph process so that
the optional monotonic fallback can compare adjacent core counts.  This
completion path keeps already written combinations and runs only missing
combinations independently, which removes that optional cross-core dependency
and makes the expensive official calls parallelizable.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/A题/data"
RUNNER = ROOT / "scripts/run_experiment.py"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def all_cases() -> list[str]:
    return [f"case_{index:03d}" for index in range(1, 101)]


def case_size(case: str) -> int:
    payload = read_json(DATA / f"{case}.json")
    ops = payload.get("operations", payload.get("ops", []))
    if isinstance(ops, dict):
        ops = ops.values()
    return sum(1 for op in ops if str(op.get("op", "")).upper() not in {"COPY", "COPY_IN", "COPY_OUT"} and int(op.get("cycles", 0) or 0) > 0)


def selection_result_exists(scene_root: Path) -> bool:
    selection_path = scene_root / "final_selection.json"
    if not selection_path.exists():
        return False
    selection = read_json(selection_path)
    candidate = selection.get("candidate")
    return bool(candidate and (scene_root / "candidates" / str(candidate) / "result.json").exists())


def find_scene(partial_roots: list[Path], case: str, cores: int, scene: str) -> Path | None:
    patterns = (
        f"batch_*/cases/{case}/{cores}core/{scene}",
        f"case_*_{cores}core/cases/{case}/{cores}core/{scene}",
        f"cases/{case}/{cores}core/{scene}",
    )
    for partial_root in partial_roots:
        paths = []
        for pattern in patterns:
            paths.extend(partial_root.glob(pattern))
        for path in sorted(paths):
            if selection_result_exists(path):
                return path
    return None


def missing_jobs(partial_roots: list[Path]) -> list[dict]:
    jobs = []
    for case in all_cases():
        size = case_size(case)
        for cores in range(1, 6):
            if all(find_scene(partial_roots, case, cores, scene) is not None for scene in ("A", "B", "C")):
                continue
            jobs.append({"case": case, "cores": cores, "case_size": size})
    return sorted(jobs, key=lambda item: (-item["case_size"], item["case"], item["cores"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partial-root", type=Path)
    parser.add_argument("--partial-roots", type=Path, nargs="+")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--parallel", type=int, default=16)
    parser.add_argument("--full-candidates", type=int, default=1)
    parser.add_argument(
        "--evaluator-dir", type=Path,
        default=ROOT / "vendor/official_evaluator_fast",
        help="Evaluator module directory; the fast copy is equivalent-checked against the preserved original.",
    )
    args = parser.parse_args()
    partial_roots = [path.resolve() for path in (args.partial_roots or ([args.partial_root] if args.partial_root else []))]
    if not partial_roots:
        parser.error("one of --partial-root or --partial-roots is required")
    output_root = args.output_root.resolve()
    evaluator_dir = args.evaluator_dir.resolve()
    if output_root.exists():
        raise SystemExit(f"refusing existing output: {output_root}")
    output_root.mkdir(parents=True)
    jobs = missing_jobs(partial_roots)
    for index, job in enumerate(jobs, start=1):
        job["job"] = index
        job["output_root"] = str(output_root / f"{job['case']}_{job['cores']}core")
        job["log"] = str(output_root / f"{job['case']}_{job['cores']}core.console.log")
        job["status"] = "PENDING"
        job["returncode"] = None
    write_json(output_root / "run_manifest.json", {
        "run_id": output_root.name,
        "status": "RUNNING",
        "partial_roots": [str(path) for path in partial_roots],
        "job_count": len(jobs),
        "parallel": args.parallel,
        "full_candidates": args.full_candidates,
        "official_evaluator_dir": str(evaluator_dir),
        "fast_profile": True,
        "selection_policy": "independent graph/core completion; no cross-core monotonic fallback; official A/B/C evaluation remains authoritative",
        "jobs": jobs,
        "started_at": time.time(),
    })

    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT / "src"),
        "HUAWEI_EVALUATOR_DIR": str(evaluator_dir),
        "HUAWEI_FAST_PROFILE": "1",
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
    })
    active: dict[int, tuple[subprocess.Popen, object]] = {}
    next_job = 0
    while next_job < len(jobs) or active:
        while next_job < len(jobs) and len(active) < max(1, args.parallel):
            job = jobs[next_job]
            command = [
                sys.executable, str(RUNNER),
                "--output-root", job["output_root"],
                "--cases", job["case"],
                "--cores", str(job["cores"]),
                "--scenes", "A,B,C",
                "--full-candidates", str(args.full_candidates),
                "--workers", "1",
            ]
            log = open(job["log"], "w", encoding="utf-8")
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
            job["status"] = "RUNNING"
            active[next_job] = (process, log)
            print(json.dumps({"event": "started", "job": job["job"], "case": job["case"], "cores": job["cores"], "pid": process.pid}, ensure_ascii=False), flush=True)
            next_job += 1
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
                child = read_json(child_manifest)
                job["status"] = child.get("status", "UNKNOWN")
                job["rows"] = child.get("rows", 0)
            else:
                job["status"] = "FAILED"
            finished.append(slot)
            print(json.dumps({"event": "finished", "job": job["job"], "case": job["case"], "cores": job["cores"], "status": job["status"], "returncode": returncode}, ensure_ascii=False), flush=True)
        for slot in finished:
            del active[slot]
        if active:
            time.sleep(2)

    complete = bool(jobs) and all(job.get("status") == "COMPUTED" and job.get("returncode") == 0 for job in jobs)
    manifest = {
        "run_id": output_root.name,
        "status": "COMPUTED" if complete else ("COMPUTED" if not jobs else "PARTIAL"),
        "partial_roots": [str(path) for path in partial_roots],
        "job_count": len(jobs),
        "completed_jobs": sum(job.get("status") == "COMPUTED" and job.get("returncode") == 0 for job in jobs),
        "failed_jobs": sum(not (job.get("status") == "COMPUTED" and job.get("returncode") == 0) for job in jobs),
        "parallel": args.parallel,
        "full_candidates": args.full_candidates,
        "official_evaluator_dir": str(evaluator_dir),
        "fast_profile": True,
        "selection_policy": "independent graph/core completion; no cross-core monotonic fallback; official A/B/C evaluation remains authoritative",
        "jobs": jobs,
        "ended_at": time.time(),
    }
    write_json(output_root / "run_manifest.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("run_id", "status", "job_count", "completed_jobs", "failed_jobs")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
