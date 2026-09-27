"""Measure useful A-evaluator throughput and result equality at 6/10/14 workers."""

import argparse
import csv
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src/a_solver"))
from run_batch import now, save_json, write_csv


def signature(folder):
    with (folder / "metrics.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return {(r["case"], r["cores"], r["algorithm"], r["problem"]):
            (r["plan_sha256"], r["result_sha256"], r["makespan"], r["added_copy_bytes"])
            for r in rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", default="6,10,14")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    summaries, reference = [], None
    for workers in map(int, args.workers.split(",")):
        dest = root / f"workers{workers}"
        command = [sys.executable, "src/a_solver/run_batch.py", "--output-root", str(dest),
                   "--cases", "001,002,016,025,076", "--cores", "4", "--workers", str(workers)]
        started, samples, processes = time.perf_counter(), [], {}
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1",
                   OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
        with (root / f"workers{workers}.log").open("w") as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            parent = psutil.Process(process.pid)
            while process.poll() is None:
                cpu, rss = 0.0, 0
                try:
                    current = [parent, *parent.children(recursive=True)]
                except psutil.NoSuchProcess:
                    current = []
                for proc in current:
                    try:
                        observed = processes.setdefault(proc.pid, proc)
                        cpu += observed.cpu_percent()
                        rss += observed.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                samples.append({"elapsed_seconds": time.perf_counter() - started,
                    "process_cpu_percent_one_core_100": cpu,
                    "process_cpu_capacity_percent": cpu / (os.cpu_count() or 1),
                    "process_rss_bytes": rss, "system_memory_percent": psutil.virtual_memory().percent,
                    "system_swap_used_bytes": psutil.swap_memory().used,
                    "process_count": len(current)})
                time.sleep(1)
        elapsed = time.perf_counter() - started
        write_csv(root / f"workers{workers}_resources.csv", samples)
        if process.returncode:
            raise RuntimeError(f"{command} failed: see {log.name}")
        current_signature = signature(dest)
        if reference is None:
            reference = current_signature
        if current_signature != reference:
            raise AssertionError("Changing parallelism changed a result or plan hash")
        manifest = json.loads((dest / "run_manifest.json").read_text())
        summary = {"workers": workers, "rows": manifest["rows"],
            "elapsed_seconds": manifest["elapsed_seconds"], "wrapper_elapsed_seconds": elapsed,
            "evaluations_per_second": manifest["rows"] / manifest["elapsed_seconds"],
            "mean_worker_cpu_capacity_percent": manifest["average_worker_cpu_capacity_percent"],
            "peak_process_cpu_capacity_percent": max(r["process_cpu_capacity_percent"] for r in samples),
            "peak_process_rss_bytes": max(r["process_rss_bytes"] for r in samples),
            "swap_growth_bytes": max(r["system_swap_used_bytes"] for r in samples) - samples[0]["system_swap_used_bytes"],
            "results_equal": True, "failures": manifest["failures"]}
        summaries.append(summary)
        write_csv(root / "summary.csv", summaries)
        print(json.dumps(summary), flush=True)
    best = min(summaries, key=lambda row: row["elapsed_seconds"])
    save_json(root / "benchmark_manifest.json", {"created_at": now(), "status": "AI_VERIFIED",
        "python": sys.version, "platform": platform.platform(), "psutil_version": psutil.__version__,
        "selected_workers": best["workers"], "results": summaries,
        "speedup_over_6_workers": summaries[0]["elapsed_seconds"] / best["elapsed_seconds"],
        "measurement": "One sweep of identical 45-evaluation workloads; process CPU is sampled once per second. System activity may affect timing.",
        "gpu_backend": "NOT_AVAILABLE in supplied heap/dictionary event evaluator",
        "memory_policy": "Allocate only actual workload memory; no filler allocations."})


if __name__ == "__main__":
    main()
