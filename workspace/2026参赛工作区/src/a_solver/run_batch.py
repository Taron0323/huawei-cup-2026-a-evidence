#!/usr/bin/env python3
"""Reproducible A-problem batch runner; retains each failure and exact result.

AI-assisted code: Codex / OpenAI, 2026-09-23. Runtime model and release date
are not exposed to this script and remain UNVERIFIED in the run manifest.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import gzip
import hashlib
import json
import os
import platform
import resource
import signal
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
import a_solver as solver
from verify import check_plan, check_result


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_json(path, value, compressed=False):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    Path(path).write_bytes(gzip.compress(data, mtime=0) if compressed else data)


def write_csv(path, rows):
    if not rows:
        return
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def timeout_handler(signum, frame):
    raise TimeoutError("Per-evaluation time budget exceeded")


def run_task(task):
    case, cores, algorithm, seed, block_size, problems, root, budget = task
    dest = Path(root) / "runs" / algorithm / f"seed{seed}_block{block_size}" / case / f"{cores}core"
    dest.mkdir(parents=True, exist_ok=False)
    start, rows, checks, failures = now(), [], [], []
    signal.signal(signal.SIGALRM, timeout_handler)
    with (dest / "execution.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            graph = solver.load_graph(solver.DATA_ROOT / f"{case}.json")
            generated_at = time.perf_counter()
            plan = solver.make_plan(graph, cores, algorithm, seed, block_size)
            generation_seconds = time.perf_counter() - generated_at
            save_json(dest / "plan.json", plan)
            plan_check = check_plan(graph, plan)
            save_json(dest / "plan_check.json", plan_check)
            for problem in problems:
                started = time.perf_counter()
                try:
                    signal.alarm(budget)
                    result = solver.evaluate(graph, plan, problem)
                    signal.alarm(0)
                    elapsed = time.perf_counter() - started
                    result_path = dest / f"problem{problem}.json.gz"
                    save_json(result_path, result, compressed=True)
                    verified = check_result(graph, plan, result)
                    verified.update(problem=problem, result_sha256=sha(result_path))
                    checks.append(verified)
                    row = solver.metric_row(case, cores, algorithm, problem, result, elapsed)
                    row.update(seed=seed, block_size=block_size,
                               generation_seconds=round(generation_seconds, 6),
                               status="AI_VERIFIED", global_optimality="NOT_PROVEN",
                               result_file=str(result_path.relative_to(root)),
                               plan_sha256=sha(dest / "plan.json"), result_sha256=sha(result_path))
                    rows.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                except Exception as exc:
                    signal.alarm(0)
                    failure = {"case": case, "cores": cores, "algorithm": algorithm,
                               "seed": seed, "block_size": block_size, "problem": problem,
                               "error": str(exc), "type": type(exc).__name__}
                    failures.append(failure)
                    traceback.print_exc()
                    save_json(dest / f"problem{problem}_failure.json", failure)
        except Exception as exc:
            signal.alarm(0)
            failures.append({"case": case, "cores": cores, "algorithm": algorithm,
                             "seed": seed, "block_size": block_size, "problem": "plan",
                             "error": str(exc), "type": type(exc).__name__})
            traceback.print_exc()
    save_json(dest / "checks.json", checks)
    save_json(dest / "task_manifest.json", {"started_at": start, "ended_at": now(),
                                           "status": "FAILED" if failures else "AI_VERIFIED",
                                           "rows": rows, "failures": failures})
    return rows, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cases")
    parser.add_argument("--cores", default="1,2,3,4,5")
    parser.add_argument("--algorithms", default="balanced_greedy,component_aware,component_packed")
    parser.add_argument("--seeds", default="0")
    parser.add_argument("--block-size", type=int, default=100)
    parser.add_argument("--problems", default="1,2,3")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1,
                        help="Worker processes (default: all available logical CPU cores)")
    parser.add_argument("--evaluation-timeout", type=int, default=1200)
    args = parser.parse_args()
    root = args.output_root.resolve()
    if root.is_relative_to(solver.WORKSPACE / "inputs"):
        parser.error("output must not be inside raw inputs")
    cases = solver.parse_cases(args.cases)
    cores = [int(value) for value in args.cores.split(",")]
    problems = tuple(int(value) for value in args.problems.split(","))
    algorithms = args.algorithms.split(",")
    seeds = [int(value) for value in args.seeds.split(",")]
    if (not cases or not cores or not set(cores) <= set(range(1, 6))
            or not problems or not set(problems) <= {1, 2, 3}
            or args.workers < 1 or args.block_size < 1 or args.evaluation_timeout < 1):
        parser.error("invalid case/core/problem/worker/block-size/time-budget configuration")
    if not set(algorithms) <= {"balanced_greedy", "balanced_contiguous", "component_aware", "component_packed", "random_stub", "singlecore"}:
        parser.error("unknown algorithm")
    if len(set(cases)) != len(cases) or len(set(cores)) != len(cores) or len(set(algorithms)) != len(algorithms) or len(set(seeds)) != len(seeds):
        parser.error("duplicate run dimension")
    for case in cases:
        if not (solver.DATA_ROOT / f"{case}.json").is_file():
            parser.error(f"missing case: {case}")
    root.mkdir(parents=True, exist_ok=False)
    code = sorted(Path(__file__).parent.glob("*.py")) + sorted(solver.RAW_CODE.glob("*.py"))
    inputs = [solver.DATA_ROOT / f"{case}.json" for case in cases] + [solver.CONFIG_PATH]
    fingerprint = {str(p.relative_to(solver.WORKSPACE)): sha(p) for p in code + inputs}
    tasks = [(case, k, alg, seed, args.block_size, problems, str(root), args.evaluation_timeout)
             for case in cases for k in cores for alg in (["singlecore"] if k == 1 else algorithms)
             for seed in (seeds if alg == "random_stub" else [0])]
    # Launch the largest graphs first to reduce idle workers at the end.
    sizes = {case: (solver.DATA_ROOT / f"{case}.json").stat().st_size for case in cases}
    tasks.sort(key=lambda task: (-sizes[task[0]], task[0], task[1], task[2], task[3]))
    config = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    manifest = {"run_id": root.name, "started_at": now(), "pid": os.getpid(),
                "command": [sys.executable, *sys.argv], "config": config,
                "python": sys.version, "platform": platform.platform(),
                "logical_cpu_count": os.cpu_count(), "compute_backend": "CPU multiprocessing",
                "task_order": "largest_input_first",
                "dependencies": "Python standard library and byte-preserved supplied evaluator",
                "ai_tool": "Codex", "ai_provider": "OpenAI", "ai_model": "UNVERIFIED",
                "ai_effort": "UNVERIFIED", "ai_release_date": "UNVERIFIED",
                "fingerprints": fingerprint, "tasks": len(tasks), "status": "RUNNING"}
    manifest["parameter_sha256"] = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    save_json(root / "run_manifest.json", manifest)
    (root / "source_snapshot").mkdir()
    for path in Path(__file__).parent.glob("*.py"):
        (root / "source_snapshot" / path.name).write_bytes(path.read_bytes())
    rows, failures, started = [], [], time.perf_counter()
    with (root / "progress.jsonl").open("w", encoding="utf-8") as log:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_task, task): task for task in tasks}
            for index, future in enumerate(as_completed(futures), 1):
                task = futures[future]
                task_rows, task_failures = future.result()
                rows.extend(task_rows)
                failures.extend(task_failures)
                event = {"finished_tasks": index, "total_tasks": len(tasks), "case": task[0],
                         "cores": task[1], "algorithm": task[2], "rows": len(task_rows),
                         "failures": len(task_failures), "elapsed_seconds": round(time.perf_counter() - started, 3)}
                line = json.dumps(event)
                log.write(line + "\n")
                log.flush()
                print(line, flush=True)
                write_csv(root / "metrics.csv", sorted(rows, key=lambda r: (r["problem"], r["cores"], r["case"], r["algorithm"], r["seed"])))
                save_json(root / "failures.json", failures)
    unchanged = all(sha(solver.WORKSPACE / p) == digest for p, digest in fingerprint.items())
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    worker_cpu_seconds = usage.ru_utime + usage.ru_stime
    wall_seconds = time.perf_counter() - started
    manifest.update(ended_at=now(), elapsed_seconds=time.perf_counter() - started,
                    rows=len(rows), failures=len(failures), fingerprints_unchanged=unchanged,
                    worker_cpu_seconds=worker_cpu_seconds,
                    average_worker_core_equivalents=worker_cpu_seconds / wall_seconds,
                    average_worker_cpu_capacity_percent=100 * worker_cpu_seconds / wall_seconds / (os.cpu_count() or 1),
                    status="COMPUTED" if not failures and unchanged else "PARTIAL",
                    exit_code=0 if not failures and unchanged else 1)
    save_json(root / "run_manifest.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("status", "rows", "failures", "elapsed_seconds", "fingerprints_unchanged")}))
    return manifest["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
