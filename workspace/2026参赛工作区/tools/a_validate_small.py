"""Exact and adversarial checks for the A solver, using synthetic fixtures only."""

import argparse
import copy
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src/a_solver"))
import a_solver
from run_batch import save_json, write_csv
from verify import check_plan, check_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []

    def record(name, actual, expected, method):
        rows.append({"check_id": name, "object": "synthetic fixture only", "expected_property": str(expected),
                     "method": method, "tolerance": 0, "actual_value": str(actual),
                     "status": "AI_VERIFIED" if actual == expected else "FAILED"})

    weights = [8, 7, 6, 5]
    graph = {"ops": [{"id": i, "op": "ADD", "pipe": "PIPE_V", "cycles": c}
                     for i, c in enumerate(weights)], "tensors": [], "edges": []}
    enumeration = []
    for assignment in itertools.product(range(2), repeat=4):
        plan = {"node_to_subgraph": dict(enumerate(assignment)),
                "core_schedules": [[k] if k in assignment else [] for k in range(2)]}
        expected = max(sum(c for c, k in zip(weights, assignment) if k == core) for core in range(2))
        for problem in (1, 2, 3):
            result = a_solver.evaluate(graph, plan, problem)
            check_plan(graph, plan)
            check_result(graph, plan, result)
            enumeration.append({"assignment": "".join(map(str, assignment)), "problem": problem,
                                "analytic_makespan": expected, "official_makespan": result["makespan"]})
    record("EXACT-01", sum(r["analytic_makespan"] != r["official_makespan"] for r in enumeration), 0,
           "All 16 core assignments, 3 evaluators; independent load-sum oracle")
    record("EXACT-02", min(r["official_makespan"] for r in enumeration), sum(weights) // 2,
           "Attained lower bound max(sum/k,max job) proves the optimum for this independent-job fixture")
    write_csv(args.output / "exact_enumeration.csv", enumeration)

    empty = {"ops": [], "tensors": [], "edges": []}
    for problem in (1, 2, 3):
        result = a_solver.evaluate(empty, {"node_to_subgraph": {}, "core_schedules": [[], []]}, problem)
        record(f"BOUNDARY-empty-p{problem}", result["makespan"], 0, "No computation or traffic")

    serial = copy.deepcopy(graph)
    serial["tensors"] = [{"id": 10 + i, "pos": "UB", "size": 0} for i in range(3)]
    serial["edges"] = [edge for i in range(3) for edge in
                       ({"source": i, "target": 10 + i}, {"source": 10 + i, "target": i + 1})]
    plan = a_solver.make_plan(serial, 2, "singlecore")
    for problem in (1, 2, 3):
        result = a_solver.evaluate(serial, plan, problem)
        record(f"BOUNDARY-serial-p{problem}", result["makespan"], sum(weights), "Zero-size tensor chain, one occupied core")
    invalid = {"node_to_subgraph": {0: 0, 1: 1, 2: 0, 3: 1}, "core_schedules": [[0], [1]]}
    try:
        check_plan(serial, invalid)
        rejected = False
    except Exception:
        rejected = True
    record("REJECT-cycle", rejected, True, "Acyclic original graph contracted into a cyclic subgraph graph")
    invalid = a_solver.make_plan(graph, 2, "singlecore")
    invalid["node_to_subgraph"].pop(0)
    try:
        check_plan(graph, invalid)
        rejected = False
    except Exception:
        rejected = True
    record("REJECT-missing", rejected, True, "Remove an eligible operation")
    plan = a_solver.make_plan(graph, 2, "singlecore")
    result = a_solver.evaluate(graph, plan, 1)
    result["makespan"] += 1
    try:
        check_result(graph, plan, result)
        rejected = False
    except Exception:
        rejected = True
    record("REJECT-number", rejected, True, "Perturb authoritative makespan after evaluation")

    actual_graph = a_solver.load_graph(a_solver.DATA_ROOT / "case_001.json")
    plan = a_solver.make_plan(actual_graph, 4, "component_packed")
    base = a_solver.evaluate(actual_graph, plan, 2)
    settings = a_solver.read_evaluation_config(str(a_solver.CONFIG_PATH))
    cache = a_solver.read_cache_config(str(a_solver.CONFIG_PATH))
    scene = a_solver.read_scene_b_config(str(a_solver.CONFIG_PATH))
    no_cache = a_solver.evaluate_problem_3(actual_graph, plan, **settings,
                 cross_core_copy_delay=scene["cross_core_copy_delay_cycles"],
                 cache_capacity_bytes=0, cache_bandwidth_bytes_per_cycle=cache["cache_bandwidth_bytes_per_cycle"])
    record("CROSS-cache-zero", no_cache["makespan"], base["makespan"], "Problem 3 zero cache degenerates to problem 2")
    rows[-1]["object"] = "case_001; diagnostic config only"
    save_json(args.output / "diagnostic_case001_p2.json", base)
    save_json(args.output / "diagnostic_case001_cache0.json", no_cache)
    write_csv(args.output / "validation_checks.csv", rows)
    save_json(args.output / "summary.json", {"checks": len(rows), "failed": sum(r["status"] == "FAILED" for r in rows),
              "scope": "Synthetic exactness and rejection tests; one actual-input degeneration check. No full-case optimality claim."})
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return int(any(r["status"] == "FAILED" for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
