"""Rebuild all A results in an isolated copy and a new standard-library venv.

AI-assisted: Codex, OpenAI, 2026-09-23; exact model/release UNVERIFIED.
"""

import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src/a_solver"))
from run_batch import now, save_json, sha, write_csv


def rows(folder):
    with (folder / "metrics.csv").open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def compare(source, rebuilt):
    fields = ("makespan", "added_copy_bytes", "scheduled_copy_bytes", "cache_hit_rate",
              "plan_sha256", "result_sha256", "status", "global_optimality")
    dims = ("case", "cores", "algorithm", "problem", "seed", "block_size")
    left = {tuple(r[d] for d in dims): r for r in rows(source)}
    right = {tuple(r[d] for d in dims): r for r in rows(rebuilt)}
    assert left.keys() == right.keys(), "reproduction coverage mismatch"
    differences = [{"key": key, "field": field, "original": row[field], "rebuilt": right[key][field]}
                   for key, row in left.items() for field in fields if row[field] != right[key][field]]
    return {"source": str(source), "rebuilt": str(rebuilt), "rows": len(left),
            "fields": fields, "tolerance": 0, "differences": differences,
            "status": "AI_VERIFIED" if not differences else "FAILED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--fallback-run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    isolated = out / "workspace"
    for relative in ("src/a_solver", "inputs/raw/A题/附件"):
        shutil.copytree(ROOT / relative, isolated / relative,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    copied = {str(p.relative_to(isolated)): sha(p) for p in isolated.rglob("*") if p.is_file()}
    assert all(sha(ROOT / name) == digest for name, digest in copied.items())
    save_json(out / "copy_manifest.json", copied)
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(isolated / ".venv")], check=True)
    python = isolated / ".venv/bin/python"
    environment = subprocess.check_output([str(python), "-c",
        "import json,sys,site; print(json.dumps({'version':sys.version,'prefix':sys.prefix,'base_prefix':sys.base_prefix,'user_site':site.ENABLE_USER_SITE,'path':sys.path}))"], text=True)
    save_json(out / "environment.json", json.loads(environment))
    manifest = {"started_at": now(), "status": "RUNNING", "pid": os.getpid(),
                "command": [sys.executable, *sys.argv], "workers": args.workers,
                "isolation": "Copied raw A inputs and source; new venv without pip or system site packages",
                "comparisons": []}
    save_json(out / "reproducibility_manifest.json", manifest)
    for label, source in (("full", args.source_run.resolve()), ("fallback", args.fallback_run.resolve())):
        source_manifest = json.loads((source / "run_manifest.json").read_text())
        assert source_manifest["status"] == "COMPUTED"
        dest = isolated / "results" / f"clean_{label}_v1"
        config = source_manifest["config"]
        command = [str(python), "src/a_solver/run_batch.py", "--output-root", str(dest),
                   "--workers", str(args.workers)]
        for field in ("cases", "cores", "algorithms", "seeds", "block_size", "problems", "evaluation_timeout"):
            if config.get(field) is not None:
                command += ["--" + field.replace("_", "-"), str(config[field])]
        print(json.dumps({"stage": label, "status": "STARTED", "workers": args.workers}), flush=True)
        samples, tracked = [], {}
        start = time.perf_counter()
        with (out / f"{label}.log").open("w") as log:
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
            child = subprocess.Popen(command, cwd=isolated, env=env, stdout=log, stderr=subprocess.STDOUT)
            proc = psutil.Process(child.pid)
            while child.poll() is None:
                cpu, rss = 0.0, 0
                try:
                    processes = [proc, *proc.children(recursive=True)]
                except psutil.NoSuchProcess:
                    processes = []
                for item in processes:
                    try:
                        item = tracked.setdefault(item.pid, item)
                        cpu += item.cpu_percent()
                        rss += item.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                samples.append({"elapsed_seconds": time.perf_counter() - start,
                    "cpu_capacity_percent": cpu / (os.cpu_count() or 1), "rss_bytes": rss,
                    "system_swap_used_bytes": psutil.swap_memory().used})
                write_csv(out / f"{label}_resources.csv", samples)
                time.sleep(3)
        if child.returncode:
            manifest.update(status="FAILED", failure_stage=label, exit_code=child.returncode, ended_at=now())
            save_json(out / "reproducibility_manifest.json", manifest)
            raise RuntimeError(f"Clean {label} failed; see {out / (label + '.log')}")
        check = compare(source, dest)
        save_json(out / f"{label}_comparison.json", check)
        manifest["comparisons"].append(check)
        assert not check["differences"], f"Clean {label} differs"
        rebuilt_manifest = json.loads((dest / "run_manifest.json").read_text())
        manifest[label + "_performance"] = {
            "elapsed_seconds": rebuilt_manifest["elapsed_seconds"],
            "average_worker_cpu_capacity_percent": rebuilt_manifest["average_worker_cpu_capacity_percent"],
            "peak_cpu_capacity_percent": max(s["cpu_capacity_percent"] for s in samples),
            "peak_rss_bytes": max(s["rss_bytes"] for s in samples)}
        save_json(out / "reproducibility_manifest.json", manifest)
        print(json.dumps({"stage": label, "status": check["status"], "rows": check["rows"],
                          "elapsed_seconds": rebuilt_manifest["elapsed_seconds"]}), flush=True)
    manifest.update(status="AI_VERIFIED", ended_at=now(), rows=sum(c["rows"] for c in manifest["comparisons"]))
    save_json(out / "reproducibility_manifest.json", manifest)


if __name__ == "__main__":
    main()
