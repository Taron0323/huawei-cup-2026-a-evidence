"""Generate and evaluate a legal plan for one A graph and one problem.

AI-assisted: Codex / OpenAI, 2026-09-23; exact model/release UNVERIFIED.
"""

import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src/a_solver"))
import a_solver as solver
from run_batch import now, save_json, sha, write_csv
from verify import check_plan, check_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--cores", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--problem", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.is_relative_to(ROOT / "inputs"):
        parser.error("output must not be inside inputs")
    out.mkdir(parents=True, exist_ok=False)
    graph = solver.load_graph(args.graph)
    algorithms = (["singlecore"] if args.cores == 1 else
                  ["balanced_greedy", "component_aware", "component_packed", "singlecore"])
    rows, candidates, errors = [], [], []
    started = time.perf_counter()
    for algorithm in algorithms:
        dest = out / algorithm
        dest.mkdir()
        try:
            plan = solver.make_plan(graph, args.cores, algorithm)
            save_json(dest / "plan.json", plan)
            save_json(dest / "plan_check.json", check_plan(graph, plan))
            tick = time.perf_counter()
            result = solver.evaluate(graph, plan, args.problem)
            save_json(dest / "result.json.gz", result, compressed=True)
            save_json(dest / "result_check.json", check_result(graph, plan, result))
            rows.append(solver.metric_row(args.graph.stem, args.cores, algorithm,
                                          args.problem, result, time.perf_counter() - tick))
            candidates.append((result["makespan"], result["data_movement_bytes"]["added_copy_bytes"], algorithm, plan))
        except Exception as exc:
            error = {"algorithm": algorithm, "type": type(exc).__name__, "error": str(exc)}
            errors.append(error)
            save_json(dest / "failure.json", error)
    save_json(out / "failures.json", errors)
    if not candidates:
        raise RuntimeError("All candidate plans failed; see failures.json")
    best = min(candidates, key=lambda item: item[:3])
    save_json(out / "plan.json", best[3])
    write_csv(out / "metrics.csv", rows)
    save_json(out / "run_manifest.json", {"created_at": now(), "status": "AI_VERIFIED",
        "graph_sha256": sha(args.graph), "config_sha256": sha(solver.CONFIG_PATH),
        "selected_algorithm": best[2], "makespan": best[0], "added_copy_bytes": best[1],
        "cores": args.cores, "problem": args.problem, "candidate_failures": len(errors),
        "elapsed_seconds": time.perf_counter() - started, "global_optimality": "NOT_PROVEN"})
    print(f"Selected {best[2]}: {best[0]} cycles; plan: {out / 'plan.json'}")


if __name__ == "__main__":
    main()
