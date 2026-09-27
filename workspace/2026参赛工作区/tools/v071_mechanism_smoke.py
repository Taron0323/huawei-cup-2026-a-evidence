#!/usr/bin/env python3
"""Small, auditable V0.7.1 mechanism smoke test.

This tool implements only the smallest independently testable part of the
V0.7.1 design: a deterministic light ranking tuple and a two-slot ledger.
It intentionally does not change ``run_v071.py`` or any prior result run.

The light replay is a screening proxy.  It uses the contracted compute DAG,
plan domains, fixed wait constants, the structural copy lower bound, and the
optimistic C input reuse rule from Idea section 7.3.  It never writes a light
estimate into an official Makespan field.  The official evaluator remains the
authority for the diagnostic comparisons below.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src/a_solver"), str(ROOT / "src/v071_solver"), str(ROOT / "tools")]

import a_solver  # type: ignore  # noqa: E402
import v071_solver  # type: ignore  # noqa: E402
from v071_official_bridge import (  # type: ignore  # noqa: E402
    evaluate_plan,
    load_official_modules,
    profile_plan,
    read_config,
    result_summary,
)
from v071_static_graph import build_static_views, compute_domain_bytes  # type: ignore  # noqa: E402


def sha_plan(plan: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ceil_div(value: int, divisor: int) -> int:
    if value <= 0:
        return 0
    return (value + divisor - 1) // divisor


def plan_maps(graph: dict[str, Any], plan: dict[str, Any]) -> tuple[
    dict[int, int], dict[int, int], dict[int, list[int]], dict[int, set[int]], dict[int, set[int]], dict[int, dict[str, Any]]
]:
    """Return block/core maps and the contracted operation graph."""
    mapping = {int(node): int(sg) for node, sg in plan["node_to_subgraph"].items()}
    core_by_sg = {
        int(sg): core for core, sequence in enumerate(plan["core_schedules"])
        for sg in sequence
    }
    nodes_by_sg: dict[int, list[int]] = defaultdict(list)
    for node, sg in mapping.items():
        nodes_by_sg[sg].append(node)
    preds, succs = v071_solver.dependencies(graph)
    ops = v071_solver.eligible_ops(graph)
    return mapping, core_by_sg, dict(nodes_by_sg), preds, succs, ops


def light_path_cycles(
    graph: dict[str, Any], plan: dict[str, Any], scene: str
) -> tuple[int, int, dict[int, int]]:
    """Compute a conservative DAG path proxy and the per-core compute loads.

    Every operation keeps its official cycle count.  Cross-block edges use the
    fixed A (1000) or B/C (500) wait from the supplied configuration.  The
    operation graph remains the only dependency source, so this is a lower
    level screening estimate rather than an execution simulation.
    """
    mapping, core_by_sg, nodes_by_sg, preds, succs, ops = plan_maps(graph, plan)
    loads: dict[int, int] = defaultdict(int)
    for node, sg in mapping.items():
        loads[core_by_sg[sg]] += max(1, int(ops[node].get("cycles", 0)))
    topo = v071_solver.topological(mapping, preds, succs)
    finish: dict[int, int] = {}
    scene = scene.upper()
    for node in topo:
        sg = mapping[node]
        core = core_by_sg[sg]
        best = 0
        for parent in preds[node]:
            psg = mapping[parent]
            pcore = core_by_sg[psg]
            if scene == "A":
                wait = 1000 if psg != sg else 0
            else:
                wait = 500 if pcore != core else 0
            best = max(best, finish[parent] + wait)
        finish[node] = best + max(1, int(ops[node].get("cycles", 0)))
    return max([max(finish.values(), default=0), max(loads.values(), default=0)]), max(loads.values(), default=0), dict(loads)


def c_input_light_work(
    view: dict[str, Any], plan: dict[str, Any], q0: int, bandwidth: int,
    cache_capacity: int, cache_bandwidth: int,
) -> tuple[int, int, int, int]:
    """Return (DDR work, Cache work, input bytes, cached bytes) for C proxy."""
    mapping, core_by_sg, _nodes_by_sg, _preds, _succs, _ops = plan_maps_from_view_plan(view, plan)
    ddr_work = 0
    cache_work = 0
    input_structural = 0
    cached_bytes = 0
    tensor_sizes = {int(k): int(v) for k, v in view["tensor_sizes"].items()}
    consumers = {int(k): [int(x) for x in v] for k, v in view["tensor_consumers"].items()}
    for tid in view["input_tensors"]:
        tid = int(tid)
        cores = {core_by_sg[mapping[node]] for node in consumers.get(tid, ()) if node in mapping}
        size = tensor_sizes.get(tid, 0)
        if not cores or size <= 0:
            continue
        r = len(cores)
        input_structural += size * r
        if size <= cache_capacity:
            ddr_work += ceil_div(size, bandwidth)
            cache_work += max(0, r - 1) * ceil_div(size, cache_bandwidth)
            cached_bytes += max(0, r - 1) * size
        else:
            ddr_work += r * ceil_div(size, bandwidth)
    other_q0 = max(0, q0 - input_structural)
    ddr_work += ceil_div(other_q0, bandwidth)
    return ddr_work, cache_work, input_structural, cached_bytes


def plan_maps_from_view_plan(view: dict[str, Any], plan: dict[str, Any]) -> tuple[dict[int, int], dict[int, int], dict[int, list[int]], dict[int, set[int]], dict[int, set[int]], dict[int, dict[str, Any]]]:
    """Minimal map helper when the graph is unavailable in C proxy code.

    The static view stores all maps needed for input-domain accounting.  Empty
    graph maps are sufficient for the unused return positions.
    """
    mapping = {int(node): int(sg) for node, sg in plan["node_to_subgraph"].items()}
    core_by_sg = {
        int(sg): core for core, sequence in enumerate(plan["core_schedules"])
        for sg in sequence
    }
    return mapping, core_by_sg, {}, {}, {}, {}


def light_tuple(
    graph: dict[str, Any], view: dict[str, Any], plan: dict[str, Any], scene: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Build the screening tuple described in Idea equations (19)-(20)."""
    scene = scene.upper()
    domain = compute_domain_bytes(view, plan, scene)
    h_proxy, core_max, loads = light_path_cycles(graph, plan, scene)
    bandwidth = int(config["bandwidth"])
    q0 = int(domain["structural_copy_bytes"])
    cache_capacity = int(config["cache"]["cache_capacity_bytes"])
    cache_bandwidth = int(config["cache"]["cache_bandwidth_bytes_per_cycle"])
    if scene == "C":
        ddr_work, cache_work, input_bytes, cached_bytes = c_input_light_work(
            view, plan, q0, bandwidth, cache_capacity, cache_bandwidth
        )
        primary = max(h_proxy, ddr_work, cache_work)
        secondary = ddr_work + cache_work
    else:
        ddr_work = ceil_div(q0, bandwidth)
        cache_work = 0
        input_bytes = 0
        cached_bytes = 0
        primary = max(h_proxy, ddr_work)
        secondary = ddr_work
    # Pressure is deliberately a separate tie-break, never an official claim.
    pressure = q0 + core_max
    return {
        "primary": int(primary),
        "secondary_work": int(secondary),
        "pressure_proxy": int(pressure),
        "h_proxy_cycles": int(h_proxy),
        "core_max_load": int(core_max),
        "core_loads": {str(k): int(v) for k, v in sorted(loads.items())},
        "q0_structural_bytes": q0,
        "ddr_work_proxy": int(ddr_work),
        "cache_work_proxy": int(cache_work),
        "input_structural_bytes": int(input_bytes),
        "cached_input_bytes_proxy": int(cached_bytes),
        "sort_key": [int(primary), int(secondary), int(pressure), sha_plan(plan)],
        "status": "PROXY_ONLY",
    }


def evaluate_once(graph: dict[str, Any], plan: dict[str, Any], problem: int, config: dict[str, Any], modules: dict[str, Any]) -> tuple[dict[str, Any], float]:
    start = time.perf_counter()
    result = evaluate_plan(graph, plan, problem, config, modules)
    elapsed = time.perf_counter() - start
    return result, elapsed


def mechanism_candidate_pool(graph: dict[str, Any], cores: int, scene: str) -> list[tuple[str, dict[str, Any], str]]:
    """Get a bounded pool without invoking the quadratic legacy checker.

    The official profile still checks each selected plan.  For graphs with at
    least 10,000 compute operations this smoke keeps only the four deterministic
    starts; local edits would be a separate experiment and are not needed to
    test the ranking/ledger interface.  Smaller graphs use the existing
    candidate pool unchanged.
    """
    if len(v071_solver.eligible_ops(graph)) < 10_000:
        return v071_solver.candidate_pool(graph, cores, scene, local_limit=8)
    starts = v071_solver.start_plans(graph, cores, scene)
    eligible = set(v071_solver.eligible_ops(graph))
    unique: list[tuple[str, dict[str, Any], str]] = []
    seen: set[str] = set()
    for name, plan in starts:
        mapping = {int(node): int(group) for node, group in plan["node_to_subgraph"].items()}
        flat = [int(group) for sequence in plan["core_schedules"] for group in sequence]
        if set(mapping) != eligible or len(flat) != len(set(flat)) or set(flat) != set(mapping.values()):
            continue
        digest = sha_plan(plan)
        if digest in seen:
            continue
        seen.add(digest)
        unique.append((name, plan, "start"))
    return unique


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_scene(
    graph: dict[str, Any], view: dict[str, Any], config: dict[str, Any], modules: dict[str, Any],
    scene: str, problem: int, candidates: list[tuple[str, dict[str, Any], str]],
    out: Path, diagnostic_all: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    for name, plan, source in candidates:
        proxy = light_tuple(graph, view, plan, scene, config)
        prepared.append({"name": name, "plan": plan, "source": source, "proxy": proxy})
    prepared.sort(key=lambda item: tuple(item["proxy"]["sort_key"]))
    for rank, item in enumerate(prepared, 1):
        item["proxy_rank"] = rank
    # A profile is needed for the two selected plans and one adjacent plan.
    # Full profile expansion remains available for small diagnostic graphs;
    # large graphs use the bounded top-three probe to avoid turning this smoke
    # test into another full experiment.
    profile_limit = len(prepared) if len(v071_solver.eligible_ops(graph)) < 10_000 else min(3, len(prepared))
    for item in prepared[:profile_limit]:
        item["profile"] = profile_plan(graph, item["plan"], scene, config, modules)
    for item in prepared[profile_limit:]:
        item["profile"] = {"status": "NOT_PROFILED", "movement": {}, "spill_ops": None}
    # A two-slot account is always exactly two distinct plans when available.
    slots = prepared[:2]
    slot_plan_hashes = {sha_plan(item["plan"]) for item in slots}
    for item in prepared:
        item["slot"] = 1 if item is slots[0] else 2 if item is slots[1] else None
        item["slot_status"] = "RESERVED" if item["slot"] else "NOT_SELECTED"
        item["dedup_status"] = "UNIQUE" if sha_plan(item["plan"]) in slot_plan_hashes else "OUTSIDE_SLOT"
    eval_items = (prepared[:profile_limit] if diagnostic_all else slots)
    official_by_hash: dict[str, dict[str, Any]] = {}
    for item in eval_items:
        plan_hash = sha_plan(item["plan"])
        if plan_hash in official_by_hash:
            item["official_status"] = "DEDUP_REUSED"
            item["official"] = official_by_hash[plan_hash]
            continue
        try:
            result, elapsed = evaluate_once(graph, item["plan"], problem, config, modules)
            summary = result_summary(result, scene)
            summary["elapsed_seconds"] = round(elapsed, 6)
            summary["status"] = "AI_VERIFIED"
            official_by_hash[plan_hash] = summary
            item["official_status"] = "AI_VERIFIED_DIAGNOSTIC" if diagnostic_all and not item["slot"] else "AI_VERIFIED_SLOT"
            item["official"] = summary
        except Exception as exc:  # preserve failures as slot evidence
            item["official_status"] = "FAILED"
            item["official"] = {"status": "FAILED", "error": repr(exc)}
    for item in prepared:
        proxy = item["proxy"]
        profile = item["profile"]
        movement = profile.get("movement", {})
        official = item.get("official", {})
        records.append({
            "scene": scene,
            "problem": problem,
            "candidate": item["name"],
            "source": item["source"],
            "plan_sha256": sha_plan(item["plan"]),
            "proxy_rank": item["proxy_rank"],
            "slot": item["slot"],
            "slot_status": item["slot_status"],
            "dedup_status": item["dedup_status"],
            "proxy_primary": proxy["primary"],
            "proxy_secondary_work": proxy["secondary_work"],
            "proxy_pressure": proxy["pressure_proxy"],
            "proxy_h_cycles": proxy["h_proxy_cycles"],
            "proxy_q0_bytes": proxy["q0_structural_bytes"],
            "proxy_ddr_work": proxy["ddr_work_proxy"],
            "proxy_cache_work": proxy["cache_work_proxy"],
            "profile_scheduled_copy_bytes": movement.get("scheduled_copy_bytes"),
            "profile_spill_ops": profile.get("spill_ops"),
            "profile_status": profile.get("status"),
            "official_status": item.get("official_status", "NOT_EVALUATED"),
            "official_makespan": official.get("makespan"),
            "official_added_copy_bytes": official.get("added_copy_bytes"),
            "official_cache_hit_bytes": official.get("cache_hit_bytes"),
            "official_cache_miss_bytes": official.get("cache_miss_bytes"),
            "official_elapsed_seconds": official.get("elapsed_seconds"),
        })
    state = {
        "scene": scene,
        "problem": problem,
        "candidate_count": len(prepared),
        "slot_capacity": 2,
        "slots_used": len(slots),
        "slot_1": {"candidate": slots[0]["name"], "plan_sha256": sha_plan(slots[0]["plan"])} if slots else None,
        "slot_2": {"candidate": slots[1]["name"], "plan_sha256": sha_plan(slots[1]["plan"])} if len(slots) > 1 else None,
        "duplicate_plans_within_slots": len(slot_plan_hashes) != len(slots),
        "diagnostic_all_official": diagnostic_all,
        "proxy_status": "PROXY_ONLY",
        "official_selection_status": "DIAGNOSTIC_ONLY",
    }
    return records, state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--case", help="one case (compatibility alias for --cases)")
    parser.add_argument("--cases", help="comma-separated cases; defaults to case_001")
    parser.add_argument("--cores", type=int, help="one core count (compatibility alias for --cores-list)")
    parser.add_argument("--cores-list", help="comma-separated core counts; defaults to 2")
    parser.add_argument("--diagnostic-all", action="store_true", help="Evaluate every candidate for ranking cross-check; never changes the two-slot ledger.")
    args = parser.parse_args()
    out = args.output_root.resolve()
    if out.exists():
        raise SystemExit(f"output exists: {out}")
    out.mkdir(parents=True)
    modules = load_official_modules(a_solver.RAW_CODE)
    config = read_config(modules, a_solver.CONFIG_PATH)
    case_text = args.cases or args.case or "case_001"
    core_text = args.cores_list or (str(args.cores) if args.cores is not None else "2")
    cases = [item.strip() for item in case_text.split(",") if item.strip()]
    core_list = [int(item.strip()) for item in core_text.split(",") if item.strip()]
    all_records: list[dict[str, Any]] = []
    all_states: list[dict[str, Any]] = []
    all_pairs: list[dict[str, Any]] = []
    unit_manifests: list[dict[str, Any]] = []
    for case in cases:
        for cores in core_list:
            unit_out = out / "cases" / case / f"{cores}core"
            unit_out.mkdir(parents=True, exist_ok=False)
            graph = a_solver.load_graph(a_solver.DATA_ROOT / f"{case}.json")
            view = build_static_views(graph)
            (unit_out / "static_view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            unit_records: list[dict[str, Any]] = []
            unit_states: list[dict[str, Any]] = []
            # A and B have independent candidate pools. C starts from B's light slot 1.
            a_candidates = mechanism_candidate_pool(graph, cores, "A")
            b_candidates = mechanism_candidate_pool(graph, cores, "B")
            rows, state = run_scene(graph, view, config, modules, "A", 1, a_candidates, unit_out, args.diagnostic_all)
            unit_records.extend(rows); unit_states.append(state)
            rows, state = run_scene(graph, view, config, modules, "B", 2, b_candidates, unit_out, args.diagnostic_all)
            unit_records.extend(rows); unit_states.append(state)
            b_slot1_hash = state["slot_1"]["plan_sha256"] if state.get("slot_1") else None
            b_item = next((x for x in b_candidates if sha_plan(x[1]) == b_slot1_hash), None)
            if b_item is None:
                raise RuntimeError(f"{case}/{cores}: B light slot 1 plan unavailable for C dependency")
            c_candidates = v071_solver.cache_candidates(graph, b_item[1], cores)
            rows, state = run_scene(graph, view, config, modules, "C", 3, c_candidates, unit_out, args.diagnostic_all)
            unit_records.extend(rows); unit_states.append(state)
            # Same-plan B no-cache pairing is evaluated only for C slot 1/2 candidates;
            # it is a diagnostic comparator and does not add C slots.
            c_slot_rows = [r for r in unit_records if r["scene"] == "C" and r.get("slot") in (1, 2)]
            unit_pairs = []
            for row in c_slot_rows:
                item = next(x for x in c_candidates if sha_plan(x[1]) == row["plan_sha256"])
                try:
                    b_result, elapsed = evaluate_once(graph, item[1], 2, config, modules)
                    unit_pairs.append({
                        "case": case, "cores": cores,
                        "c_candidate": row["candidate"], "plan_sha256": row["plan_sha256"],
                        "c_official_makespan": row["official_makespan"],
                        "b_same_plan_makespan": b_result.get("makespan"),
                        "b_same_plan_added_copy_bytes": b_result.get("data_movement_bytes", {}).get("added_copy_bytes"),
                        "paired_elapsed_seconds": round(elapsed, 6),
                        "pair_status": "AI_VERIFIED_DIAGNOSTIC",
                        "cache_proxy_status": "NOT_IMPLEMENTED",
                    })
                except Exception as exc:
                    unit_pairs.append({"case": case, "cores": cores, "c_candidate": row["candidate"], "plan_sha256": row["plan_sha256"], "pair_status": "FAILED", "error": repr(exc), "cache_proxy_status": "NOT_IMPLEMENTED"})
            for row in unit_records:
                row.update({"case": case, "cores": cores})
            for state_item in unit_states:
                state_item.update({"case": case, "cores": cores})
            (unit_out / "slot_state.json").write_text(json.dumps(unit_states, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (unit_out / "c_same_plan_pairs.json").write_text(json.dumps(unit_pairs, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            write_rows(unit_out / "mechanism_candidates.csv", unit_records)
            unit_manifest = {
                "run_id": out.name,
                "case": case,
                "cores": cores,
                "status": "COMPUTED",
                "scenes": ["A", "B", "C"],
                "candidate_rows": len(unit_records),
                "diagnostic_all_official": bool(args.diagnostic_all),
                "light_proxy_status": "PROXY_ONLY",
                "official_result_status": "AI_VERIFIED_DIAGNOSTIC",
                "two_slot_status": "RECORDED_ONLY",
                "cache_fifo_proxy_status": "NOT_IMPLEMENTED",
                "old_v2_untouched": True,
                "idea": "idea/A题_Idea_V0.7.1_融合修订.md",
            }
            (unit_out / "run_manifest.json").write_text(json.dumps(unit_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            all_records.extend(unit_records)
            all_states.extend(unit_states)
            all_pairs.extend(unit_pairs)
            unit_manifests.append(unit_manifest)
    (out / "slot_state.json").write_text(json.dumps(all_states, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "c_same_plan_pairs.json").write_text(json.dumps(all_pairs, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_rows(out / "mechanism_candidates.csv", all_records)
    manifest = {
        "run_id": out.name,
        "status": "COMPUTED",
        "cases": cases,
        "cores": core_list,
        "scenes": ["A", "B", "C"],
        "candidate_rows": len(all_records),
        "unit_count": len(unit_manifests),
        "diagnostic_all_official": bool(args.diagnostic_all),
        "light_proxy_status": "PROXY_ONLY",
        "official_result_status": "AI_VERIFIED_DIAGNOSTIC",
        "two_slot_status": "RECORDED_ONLY",
        "cache_fifo_proxy_status": "NOT_IMPLEMENTED",
        "old_v2_untouched": True,
        "idea": "idea/A题_Idea_V0.7.1_融合修订.md",
        "units": unit_manifests,
    }
    (out / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": out.name, "candidate_rows": len(all_records), "unit_count": len(unit_manifests)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
