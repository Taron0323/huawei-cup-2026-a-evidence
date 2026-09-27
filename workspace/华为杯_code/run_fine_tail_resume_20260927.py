#!/usr/bin/env python3
"""Continue fine-grained rescue jobs after an interrupted scheduler."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def complete_prior(prior_root: Path) -> set[tuple[str, int]]:
    done = set()
    for job_root in prior_root.glob("job_*_*core"):
        match = re.search(r"_(case_\d+)_(\d+)core$", job_root.name)
        if match is None:
            continue
        case, cores = match.group(1), int(match.group(2))
        if all((job_root / "cases" / case / f"{cores}core" / scene / "final_selection.json").exists() for scene in ("A", "B", "C")):
            done.add((case, cores))
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--prior-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--parallel", type=int, default=16)
    args = parser.parse_args()
    main_root = args.main_root.resolve()
    prior_root = args.prior_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    done_prior = complete_prior(prior_root)
    manifest = json.loads((main_root / "run_manifest.json").read_text(encoding="utf-8"))
    jobs = []
    for batch in manifest["jobs"]:
        batch_root = Path(batch["output_root"])
        for case in batch["cases"]:
            case_root = batch_root / "cases" / case
            for cores in (1, 2, 3, 4, 5):
                if (case, cores) in done_prior:
                    continue
                if all((case_root / f"{cores}core" / scene / "final_selection.json").exists() for scene in ("A", "B", "C")):
                    continue
                jobs.append({"case": case, "cores": cores, "missing_scenes": [scene for scene in ("A", "B", "C") if not (case_root / f"{cores}core" / scene / "final_selection.json").exists()], "source_batch": int(batch["batch"])})
    save(output_root / "job_plan.json", {"main_root": str(main_root), "prior_root": str(prior_root), "jobs": jobs, "started_at": time.time()})
    solver_root = Path(__file__).resolve().parent / "solver_review_v7_20260926"
    evaluator = solver_root / "vendor/official_evaluator_fast"
    env = os.environ.copy()
    env.update({"HUAWEI_FAST_PROFILE": "1", "HUAWEI_EVALUATOR_DIR": str(evaluator), "PYTHONPATH": str(solver_root / "src"), "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"})

    def run(item):
        index = jobs.index(item)
        job_root = output_root / f"job_{index:03d}_{item['case']}_{item['cores']}core"
        with (output_root / f"job_{index:03d}_{item['case']}_{item['cores']}core.log").open("w", encoding="utf-8") as log:
            code = subprocess.run([sys.executable, str(solver_root / "scripts/run_experiment.py"), "--output-root", str(job_root), "--cases", item["case"], "--cores", str(item["cores"]), "--scenes", "A,B,C", "--full-candidates", "2", "--workers", "1"], cwd=solver_root, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        return {**item, "output_root": str(job_root), "returncode": code}

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(run, item) for item in jobs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps({"case": result["case"], "cores": result["cores"], "returncode": result["returncode"]}, ensure_ascii=False), flush=True)
    save(output_root / "rescue_manifest.json", {"status": "COMPUTED" if all(item["returncode"] == 0 for item in results) else "PARTIAL", "main_root": str(main_root), "prior_root": str(prior_root), "official_evaluator_dir": str(evaluator), "fast_profile": True, "jobs": sorted(results, key=lambda item: (item["case"], item["cores"])), "job_count": len(results), "ended_at": time.time()})


if __name__ == "__main__":
    main()
