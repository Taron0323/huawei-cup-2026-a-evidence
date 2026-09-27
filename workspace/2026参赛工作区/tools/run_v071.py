#!/usr/bin/env python3
"""Run the V0.7.1 finite candidate experiment with auditable outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/a_solver"))
sys.path.insert(0, str(ROOT / "src/v071_solver"))
sys.path.insert(0, str(ROOT / "tools"))
import a_solver  # type: ignore  # noqa: E402
import v071_solver  # type: ignore  # noqa: E402
from verify import check_result  # type: ignore  # noqa: E402
from v071_official_bridge import (  # type: ignore  # noqa: E402
    load_official_modules,
    profile_plan,
    read_config,
)
from v071_static_graph import build_static_views, compute_domain_bytes  # type: ignore  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_file(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def metric(case: str, cores: int, problem: int, name: str, source: str,
           result: dict, elapsed: float, plan: dict, graph: dict) -> dict:
    move = result.get("data_movement_bytes", {})
    cache = result.get("cache_stats") or {}
    plan_sha = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return {
        "case": case, "cores": cores, "problem": problem, "candidate": name,
        "source": source, "makespan": result.get("makespan"),
        "added_copy_bytes": move.get("added_copy_bytes"),
        "scheduled_copy_bytes": move.get("scheduled_copy_bytes"),
        "partition_added_copy_bytes": move.get("partition_added_copy_bytes"),
        "spill_added_copy_bytes": move.get("spill_added_copy_bytes"),
        "cache_hit_rate": cache.get("hit_rate", ""),
        "cache_hit_bytes": cache.get("hit_bytes", ""),
        "cache_miss_bytes": cache.get("miss_bytes", ""),
        "elapsed_seconds": round(elapsed, 6), "plan_sha256": plan_sha,
        "status": "AI_VERIFIED", "global_optimality": "NOT_PROVEN",
    }


def eval_one(graph: dict, plan: dict, problem: int) -> tuple[dict, float]:
    start = time.perf_counter()
    result = a_solver.evaluate(graph, plan, problem)
    elapsed = time.perf_counter() - start
    check_result(graph, plan, result)
    return result, elapsed


def core_max_load(graph: dict, plan: dict) -> int:
    """Return the deterministic compute-cycle load of the busiest core."""
    op_by_id = {int(op["id"]): op for op in graph.get("ops", [])}
    core_by_subgraph = {
        int(subgraph): core
        for core, sequence in enumerate(plan["core_schedules"])
        for subgraph in sequence
    }
    loads = [0] * len(plan["core_schedules"])
    for node, subgraph in plan["node_to_subgraph"].items():
        core = core_by_subgraph[int(subgraph)]
        loads[core] += max(1, int(op_by_id[int(node)].get("cycles", 0)))
    return max(loads, default=0)


def profile_only_row(case: str, cores: int, problem: int, name: str, source: str,
                     profile_rank: int, profile: dict, domain: dict) -> dict:
    movement = profile.get("movement", {})
    return {
        "case": case, "cores": cores, "problem": problem, "candidate": name,
        "source": source, "status": "PROFILE_ONLY",
        "global_optimality": "NOT_ASSESSED", "profile_rank": profile_rank,
        "profile_scheduled_copy_bytes": movement.get("scheduled_copy_bytes"),
        "profile_spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
        "profile_spill_ops": profile.get("spill_ops"),
        "static_q0_bytes": domain.get("structural_copy_bytes"),
        "core_max_load": domain.get("core_max_load"),
    }


def run_case(task: tuple[str, int, str, str, int, int]) -> dict:
    case, cores, output_root, problems_raw, full_candidates, long_graph_full_candidates = task
    problems = tuple(int(x) for x in problems_raw.split(","))
    out = Path(output_root) / "cases" / case / f"{cores}core"
    out.mkdir(parents=True, exist_ok=False)
    graph = a_solver.load_graph(a_solver.DATA_ROOT / f"{case}.json")
    large_graph = len(v071_solver.eligible_ops(graph)) > 20_000
    effective_full_candidates = (long_graph_full_candidates if large_graph else full_candidates)
    # V0.7.1 evidence is collected before complete evaluation.  The bridge
    # imports only the byte-preserved official evaluator; it never writes raw
    # inputs or changes the shared config.
    official_modules = load_official_modules(a_solver.RAW_CODE)
    official_config = read_config(official_modules, a_solver.CONFIG_PATH)
    static_view = build_static_views(graph)
    static_view["_ops"] = {int(op["id"]): op for op in graph.get("ops", [])}
    save_json(out / "static_view.json", {key: value for key, value in static_view.items() if key != "_ops"})
    rows: list[dict] = []
    selected: dict[str, dict] = {}
    candidates_by_scene: dict[str, list[tuple[str, dict, str]]] = {}
    for scene in ("A", "B"):
        candidates_by_scene[scene] = v071_solver.candidate_pool(graph, cores, scene, local_limit=8)
    # Q1 and Q2 each use their own candidate pool.  Q3 starts from the selected
    # B plan and adds aggregate/disperse/timing candidates.
    candidate_ledger: list[dict] = []
    for problem, scene in ((1, "A"), (2, "B")):
        if problem not in problems:
            continue
        profiled: list[dict] = []
        scored: list[tuple[tuple[float, float, str], dict, tuple[str, dict, str]]] = []
        for name, plan, source in candidates_by_scene[scene]:
            candidate_dir = out / "candidates" / scene / f"{name}__{len(candidate_ledger):04d}"
            candidate_dir.mkdir(parents=True, exist_ok=False)
            save_json(candidate_dir / "plan.json", plan)
            ledger_entry = {"candidate": name, "source": source, "scene": scene,
                            "problem": problem, "cores": cores,
                            "plan_file": str((candidate_dir / "plan.json").relative_to(out))}
            try:
                domain = compute_domain_bytes(static_view, plan, scene)
                domain["core_max_load"] = core_max_load(graph, plan)
                profile = profile_plan(graph, plan, scene, official_config, official_modules)
                save_json(candidate_dir / "static_domain.json", domain)
                save_json(candidate_dir / "profile.json", profile)
                ledger_entry.update({"domain_file": str((candidate_dir / "static_domain.json").relative_to(out)),
                                     "profile_file": str((candidate_dir / "profile.json").relative_to(out)),
                                     "profile_status": profile.get("status", "AI_VERIFIED"),
                                     "profile_movement": profile.get("movement"),
                                     "profile_spill_ops": profile.get("spill_ops"),
                                     "static_q0_bytes": domain.get("structural_copy_bytes"),
                                     "core_max_load": domain.get("core_max_load")})
                profile_key = (domain["core_max_load"],
                               profile.get("movement", {}).get("scheduled_copy_bytes", 0),
                               profile.get("spill_ops", 0), name)
                profiled.append({"key": profile_key, "name": name, "plan": plan,
                                 "source": source, "profile": profile,
                                 "domain": domain, "ledger": ledger_entry,
                                 "candidate_dir": candidate_dir})
            except Exception as exc:
                ledger_entry.update({"official_status": "PROFILE_FAILED", "error": repr(exc)})
                rows.append({"case": case, "cores": cores, "problem": problem,
                             "candidate": name, "source": source,
                             "status": "PROFILE_FAILED", "error": repr(exc)})
            candidate_ledger.append(ledger_entry)
        profiled.sort(key=lambda item: item["key"])
        for rank, item in enumerate(profiled, 1):
            item["ledger"]["profile_rank"] = rank
            if rank > effective_full_candidates:
                item["ledger"]["official_status"] = "PROFILE_ONLY"
                rows.append(profile_only_row(case, cores, problem, item["name"],
                                             item["source"], rank, item["profile"], item["domain"]))
                continue
            try:
                result, elapsed = eval_one(graph, item["plan"], problem)
                save_json(item["candidate_dir"] / "result.json", result)
                row = metric(case, cores, problem, item["name"], item["source"], result, elapsed, item["plan"], graph)
                row.update({"profile_rank": rank, "core_max_load": item["domain"]["core_max_load"],
                            "static_q0_bytes": item["domain"].get("structural_copy_bytes"),
                            "profile_scheduled_copy_bytes": item["profile"].get("movement", {}).get("scheduled_copy_bytes"),
                            "profile_spill_ops": item["profile"].get("spill_ops")})
                rows.append(row)
                item["ledger"].update({"official_status": "AI_VERIFIED",
                                        "makespan": result.get("makespan"),
                                        "added_copy_bytes": result.get("data_movement_bytes", {}).get("added_copy_bytes"),
                                        "official_elapsed_seconds": round(elapsed, 6)})
                scored.append(((float(result["makespan"]), float(result["data_movement_bytes"]["added_copy_bytes"]), item["name"]), result,
                               (item["name"], item["plan"], item["source"])))
            except Exception as exc:
                item["ledger"].update({"official_status": "FAILED", "error": repr(exc)})
                rows.append({"case": case, "cores": cores, "problem": problem,
                             "candidate": item["name"], "source": item["source"],
                             "status": "FAILED", "error": repr(exc), "profile_rank": rank})
        if scored:
            scored.sort(key=lambda item: item[0])
            best = scored[0]
            selected[scene] = {"candidate": best[2][0], "source": best[2][2], "plan": best[2][1], "result": best[1]}
        elif profiled:
            # A profile-only long graph still exposes the best screened plan,
            # but it is never promoted to an official Makespan result.
            best_profile = profiled[0]
            selected[scene] = {"candidate": best_profile["name"], "source": best_profile["source"],
                               "plan": best_profile["plan"], "result": None,
                               "profile_only": True}
    if 3 in problems and "B" in selected:
        cands = v071_solver.cache_candidates(graph, selected["B"]["plan"], cores)
        profiled_c: list[dict] = []
        scored = []
        for name, plan, source in cands:
            candidate_dir = out / "candidates" / "C" / f"{name}__{len(candidate_ledger):04d}"
            candidate_dir.mkdir(parents=True, exist_ok=False)
            save_json(candidate_dir / "plan.json", plan)
            ledger_entry = {"candidate": name, "source": source, "scene": "C",
                            "problem": 3, "cores": cores,
                            "plan_file": str((candidate_dir / "plan.json").relative_to(out))}
            try:
                domain = compute_domain_bytes(static_view, plan, "C")
                domain["core_max_load"] = core_max_load(graph, plan)
                profile = profile_plan(graph, plan, "C", official_config, official_modules)
                save_json(candidate_dir / "static_domain.json", domain)
                save_json(candidate_dir / "profile.json", profile)
                ledger_entry.update({"domain_file": str((candidate_dir / "static_domain.json").relative_to(out)),
                                     "profile_file": str((candidate_dir / "profile.json").relative_to(out)),
                                     "profile_status": profile.get("status", "AI_VERIFIED"),
                                     "profile_movement": profile.get("movement"),
                                     "profile_spill_ops": profile.get("spill_ops"),
                                     "static_q0_bytes": domain.get("structural_copy_bytes"),
                                     "core_max_load": domain.get("core_max_load")})
                profile_key = (domain["core_max_load"],
                               profile.get("movement", {}).get("scheduled_copy_bytes", 0),
                               profile.get("spill_ops", 0), name)
                profiled_c.append({"key": profile_key, "name": name, "plan": plan,
                                   "source": source, "profile": profile,
                                   "domain": domain, "ledger": ledger_entry,
                                   "candidate_dir": candidate_dir})
            except Exception as exc:
                ledger_entry.update({"official_status": "PROFILE_FAILED", "error": repr(exc)})
                rows.append({"case": case, "cores": cores, "problem": 3,
                             "candidate": name, "source": source,
                             "status": "PROFILE_FAILED", "error": repr(exc)})
            candidate_ledger.append(ledger_entry)
        profiled_c.sort(key=lambda item: item["key"])
        for rank, item in enumerate(profiled_c, 1):
            item["ledger"]["profile_rank"] = rank
            if rank > effective_full_candidates:
                item["ledger"]["official_status"] = "PROFILE_ONLY"
                rows.append(profile_only_row(case, cores, 3, item["name"],
                                             item["source"], rank, item["profile"], item["domain"]))
                continue
            try:
                result, elapsed = eval_one(graph, item["plan"], 3)
                save_json(item["candidate_dir"] / "result.json", result)
                row = metric(case, cores, 3, item["name"], item["source"], result, elapsed, item["plan"], graph)
                row.update({"profile_rank": rank, "core_max_load": item["domain"]["core_max_load"],
                            "static_q0_bytes": item["domain"].get("structural_copy_bytes"),
                            "profile_scheduled_copy_bytes": item["profile"].get("movement", {}).get("scheduled_copy_bytes"),
                            "profile_spill_ops": item["profile"].get("spill_ops")})
                rows.append(row)
                item["ledger"].update({"official_status": "AI_VERIFIED",
                                        "makespan": result.get("makespan"),
                                        "added_copy_bytes": result.get("data_movement_bytes", {}).get("added_copy_bytes"),
                                        "cache_hit_bytes": (result.get("cache_stats") or {}).get("hit_bytes"),
                                        "cache_miss_bytes": (result.get("cache_stats") or {}).get("miss_bytes"),
                                        "official_elapsed_seconds": round(elapsed, 6)})
                scored.append(((float(result["makespan"]), float(result["data_movement_bytes"]["added_copy_bytes"]), item["name"]), result,
                               (item["name"], item["plan"], item["source"])))
            except Exception as exc:
                item["ledger"].update({"official_status": "FAILED", "error": repr(exc)})
                rows.append({"case": case, "cores": cores, "problem": 3,
                             "candidate": item["name"], "source": item["source"],
                             "status": "FAILED", "error": repr(exc), "profile_rank": rank})
        if scored:
            scored.sort(key=lambda item: item[0])
            best = scored[0]
            selected["C"] = {"candidate": best[2][0], "source": best[2][2], "plan": best[2][1], "result": best[1]}
            # Same-plan no-L2 result gives the hardware-only paired comparison.
            no_l2, no_l2_elapsed = eval_one(graph, best[2][1], 2)
            rows.append(metric(case, cores, 2, best[2][0] + "_same_plan_no_l2", "paired_no_l2", no_l2, no_l2_elapsed, best[2][1], graph))
            c_item = selected["C"]
            save_json(out / "c_same_plan_pair.json", {
                "case": case, "cores": cores,
                "candidate": best[2][0],
                "source": best[2][2],
                "pair_status": "OFFICIAL_PAIRED_PROXY_NOT_ASSESSED",
                "cache_proxy": {
                    "status": "NOT_IMPLEMENTED",
                    "predicted_hit_bytes": None,
                    "predicted_miss_bytes": None,
                    "note": "Current finite trial records official FIFO events; it does not use those events as a proxy prediction.",
                },
                "plan_file": str((out / "selected_C_plan.json").relative_to(out)),
                "cache_result": {"makespan": c_item["result"].get("makespan"),
                                 "added_copy_bytes": c_item["result"].get("data_movement_bytes", {}).get("added_copy_bytes"),
                                 "cache_stats": c_item["result"].get("cache_stats")},
                "same_plan_no_l2_result": {"makespan": no_l2.get("makespan"),
                                           "added_copy_bytes": no_l2.get("data_movement_bytes", {}).get("added_copy_bytes")},
                "cache_speedup": (no_l2.get("makespan", 0) / c_item["result"].get("makespan", 1)),
                "no_l2_elapsed_seconds": round(no_l2_elapsed, 6),
            })
        elif profiled_c:
            best_profile = profiled_c[0]
            selected["C"] = {"candidate": best_profile["name"], "source": best_profile["source"],
                              "plan": best_profile["plan"], "result": None,
                              "profile_only": True}
    save_json(out / "candidate_ledger.json", candidate_ledger)
    for scene, item in selected.items():
        save_json(out / f"selected_{scene}.json", {k: v for k, v in item.items() if k != "result"})
        if item.get("result") is None:
            save_json(out / f"selected_{scene}_profile_only.json", {k: v for k, v in item.items() if k != "result"})
        else:
            save_json(out / f"selected_{scene}_result.json", item["result"])
        save_json(out / f"selected_{scene}_plan.json", item["plan"])
    save_json(out / "case_manifest.json", {
        "case": case, "cores": cores, "rows": len(rows),
        "full_candidates": full_candidates,
        "effective_full_candidates": effective_full_candidates,
        "large_graph": large_graph,
        "profile_only_rows": sum(row.get("status") == "PROFILE_ONLY" for row in rows),
        "selected": {k: {"candidate": v["candidate"], "source": v["source"]} for k, v in selected.items()},
        "ended_at": now(),
    })
    # Do not send full evaluator timelines through ProcessPool pipes.  They are
    # already persisted in selected_*_result.json; returning only the metrics
    # summary prevents long-tail workers from blocking while pickling results.
    selected_summary = {}
    for scene, item in selected.items():
        result = item["result"]
        if result is None:
            continue
        movement = result.get("data_movement_bytes", {})
        cache = result.get("cache_stats") or {}
        selected_summary[scene] = {
            "candidate": item["candidate"],
            "source": item["source"],
            "plan_sha256": hashlib.sha256(json.dumps(item["plan"], sort_keys=True).encode()).hexdigest(),
            "makespan": result.get("makespan"),
            "added_copy_bytes": movement.get("added_copy_bytes"),
            "cache_hit_rate": cache.get("hit_rate", ""),
        }
    return {"case": case, "cores": cores, "rows": rows, "selected": selected_summary}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cases")
    parser.add_argument("--cores", default="1,2,3,4,5")
    parser.add_argument("--problems", default="1,2,3")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--full-candidates", type=int, default=4,
                        help="Complete official evaluations per problem after profile ranking (default: 4)")
    parser.add_argument("--long-graph-full-candidates", type=int, default=0,
                        help="Complete evaluations for graphs with >20,000 compute ops (default: 0; profile-only)")
    args = parser.parse_args()
    if args.full_candidates < 1:
        parser.error("--full-candidates must be positive")
    if args.long_graph_full_candidates < 0:
        parser.error("--long-graph-full-candidates must be nonnegative")
    root = args.output_root.resolve()
    if root.exists():
        raise SystemExit(f"output exists: {root}")
    root.mkdir(parents=True)
    cases = a_solver.parse_cases(args.cases)
    cores = [int(x) for x in args.cores.split(",")]
    tasks = [(case, k, str(root), args.problems, args.full_candidates, args.long_graph_full_candidates) for case in cases for k in cores]
    manifest = {"run_id": root.name, "algorithm": "V0.7.1 resident-domain finite candidate trial", "started_at": now(), "status": "RUNNING", "cases": cases, "cores": cores, "problems": [int(x) for x in args.problems.split(",")], "workers": args.workers, "full_candidates": args.full_candidates, "long_graph_full_candidates": args.long_graph_full_candidates, "large_graph_threshold_ops": 20000, "python": sys.version, "platform": platform.platform(), "input_manifest": "inputs/manifest.json", "idea": "idea/A题_Idea_V0.7.1_融合修订.md", "idea_sha256": sha_file(ROOT.parent / "idea/A题_Idea_V0.7.1_融合修订.md")}
    save_json(root / "run_manifest.json", manifest)
    all_rows: list[dict] = []
    selected_rows: list[dict] = []
    done = 0
    with (root / "progress.jsonl").open("w", encoding="utf-8") as progress:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_case, task): task for task in tasks}
            for future in as_completed(futures):
                result = future.result()
                done += 1
                all_rows.extend(result["rows"])
                for scene, selected in result["selected"].items():
                    selected_rows.append({"case": result["case"], "cores": result["cores"], "scene": scene, "candidate": selected["candidate"], "source": selected["source"], "plan_sha256": selected["plan_sha256"], "makespan": selected["makespan"], "added_copy_bytes": selected["added_copy_bytes"], "cache_hit_rate": selected["cache_hit_rate"]})
                event = {"finished": done, "total": len(tasks), "case": result["case"], "cores": result["cores"], "rows": len(result["rows"]), "time": now()}
                progress.write(json.dumps(event, ensure_ascii=False) + "\n")
                progress.flush()
                print(json.dumps(event, ensure_ascii=False), flush=True)
    fields = sorted({key for row in all_rows for key in row})
    with (root / "candidate_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(all_rows)
    fields = sorted({key for row in selected_rows for key in row})
    with (root / "selected_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(selected_rows)
    manifest.update({"ended_at": now(), "status": "COMPUTED", "tasks": len(tasks), "candidate_rows": len(all_rows), "selected_rows": len(selected_rows), "failures": sum(row.get("status") == "FAILED" for row in all_rows)})
    save_json(root / "run_manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
