#!/usr/bin/env python3
"""One-command A computation from read-only raw inputs, using a fresh run ID.

AI-assisted: Codex / OpenAI, 2026-09-23; exact model/release UNVERIFIED.
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "full"), default="full")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    out = (args.output_root or ROOT / "results" / ("reproduce_" + datetime.now().strftime("%Y%m%d_%H%M%S"))).resolve()
    if not out.is_relative_to(ROOT) or out.is_relative_to(ROOT / "inputs") or out.exists():
        parser.error("Choose a new output directory inside this workspace, outside inputs")
    out.mkdir(parents=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")

    def run(script, *options):
        command = [sys.executable, str(ROOT / script), *map(str, options)]
        subprocess.run(command, cwd=ROOT, env=env, check=True)

    representative = "001,002,016,025,076"
    if args.mode == "smoke":
        run("src/a_solver/run_batch.py", "--output-root", out / "smoke_v1", "--cases", representative,
            "--cores", "4", "--workers", args.workers)
        print(f"Smoke test complete: {out / 'smoke_v1/run_manifest.json'}")
        return
    run("src/a_solver/run_batch.py", "--output-root", out / "full_v1", "--workers", args.workers)
    run("tools/a_analyze_results.py", "--source", out / "full_v1", "--output", out / "analysis_preliminary")
    slow = json.loads((out / "analysis_preliminary/analysis_manifest.json").read_text())["slower_cases"]
    fallback_options = []
    if slow:
        run("src/a_solver/run_batch.py", "--output-root", out / "fallback_v1", "--cases", ",".join(slow),
            "--cores", "2,3,4,5", "--algorithms", "singlecore", "--workers", args.workers)
        fallback_options = ["--fallback", out / "fallback_v1"]
    run("tools/a_analyze_results.py", "--source", out / "full_v1", *fallback_options, "--output", out / "analysis_final")
    run("src/a_solver/run_batch.py", "--output-root", out / "smoke_v1", "--cases", representative,
        "--cores", "4", "--workers", args.workers)
    for block in (50, 200):
        run("src/a_solver/run_batch.py", "--output-root", out / f"sensitivity_block{block}", "--cases", representative,
            "--cores", "4", "--algorithms", "component_packed", "--block-size", block, "--workers", args.workers)
    run("src/a_solver/run_batch.py", "--output-root", out / "random_seeds_v1", "--cases", representative,
        "--cores", "4", "--algorithms", "random_stub", "--seeds", "0,1,2", "--workers", args.workers)
    run("tools/a_cache_sensitivity.py", "--output", out / "cache_sensitivity_v1")
    run("tools/a_make_figures.py", "--analysis", out / "analysis_final", "--runs", out, "--output", out / "figures")
    run("tools/a_paper_data.py", "--analysis", out / "analysis_final", "--runs", out, "--output", out / "paper_data")
    print(f"Full computation, sensitivity, figures and numerical paper tables complete: {out}")


if __name__ == "__main__":
    main()
