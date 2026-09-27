"""Independent diagnostic parameter sweep; never changes official config.txt."""

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src/a_solver"))
import a_solver
from run_batch import now, save_json, sha, write_csv
from verify import check_result


def task(args):
    case, capacity, bandwidth, root = args
    graph = a_solver.load_graph(a_solver.DATA_ROOT / f"{case}.json")
    plan = a_solver.make_plan(graph, 4, "component_packed")
    settings = a_solver.read_evaluation_config(str(a_solver.CONFIG_PATH))
    scene = a_solver.read_scene_b_config(str(a_solver.CONFIG_PATH))
    start = time.perf_counter()
    result = a_solver.evaluate_problem_3(graph, plan, **settings,
        cross_core_copy_delay=scene["cross_core_copy_delay_cycles"],
        cache_capacity_bytes=capacity, cache_bandwidth_bytes_per_cycle=bandwidth)
    check = check_result(graph, plan, result)
    path = Path(root) / f"{case}_capacity{capacity}_bandwidth{bandwidth}.json.gz"
    save_json(path, result, compressed=True)
    save_json(path.with_suffix(".check.json"), check)
    return {"case": case, "cores": 4, "algorithm": "component_packed", "block_size": 100,
            "capacity_bytes": capacity, "bandwidth_bytes_per_cycle": bandwidth,
            "makespan": result["makespan"], "added_copy_bytes": result["data_movement_bytes"]["added_copy_bytes"],
            "cache_hit_rate": result["cache_stats"]["hit_rate"], "elapsed_seconds": time.perf_counter() - start,
            "status": "AI_VERIFIED", "formal_config": capacity == 1048576 and bandwidth == 250,
            "result_file": path.name, "sha256": sha(path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = ["case_001", "case_002", "case_076"]
    grid = sorted({(c, 250) for c in (0, 524288, 1048576, 2097152)} |
                  {(1048576, b) for b in (60, 125, 250, 500)})
    fingerprint = {str(p.relative_to(ROOT)): sha(p) for p in
                   [Path(__file__), a_solver.CONFIG_PATH, *a_solver.RAW_CODE.glob("*.py"),
                    *Path(a_solver.__file__).parent.glob("*.py"),
                    *(a_solver.DATA_ROOT / f"{case}.json" for case in cases)]}
    manifest = {"started_at": now(), "command": sys.argv, "config_grid": grid,
                "cases": cases, "fingerprints": fingerprint, "status": "RUNNING"}
    save_json(args.output / "manifest.json", manifest)
    rows = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(task, (case, c, b, str(args.output))) for case in cases for c, b in grid]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(json.dumps(row), flush=True)
            write_csv(args.output / "metrics.csv", sorted(rows, key=lambda r: (r["case"], r["capacity_bytes"], r["bandwidth_bytes_per_cycle"])))
    assert all(sha(ROOT / p) == digest for p, digest in fingerprint.items())
    manifest.update(ended_at=now(), status="AI_VERIFIED", rows=len(rows), fingerprints_unchanged=True)
    save_json(args.output / "manifest.json", manifest)


if __name__ == "__main__":
    main()
