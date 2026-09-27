#!/usr/bin/env python3
"""Run the three mechanism controls specified by the frozen A idea."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huawei_code.candidates import (  # noqa: E402
    _boundary_node_variants, _group_move_variants, _merge_variants, _move_node,
    _split_group_variants, capacity_variants, core_order_variants,
)
from huawei_code.graph import load_graph, static_view  # noqa: E402
from huawei_code.official import evaluate, load_modules, profile, read_config, summary  # noqa: E402
from huawei_code.plan import _make_plan, _split_order, legacy_seed_plans, plan_key, seed_plans, validate_plan  # noqa: E402
from huawei_code.scoring import light_score  # noqa: E402


REPRESENTATIVE_CASES = ["case_051", "case_012", "case_067", "case_081", "case_016", "case_062"]
CONTROL_SCENES = {
    "no_receive_domain": ("A", "B"),
    "no_capacity_guidance": ("B",),
    "light_direct_select": ("A",),
}


def evaluator_dir() -> Path:
    return Path(os.environ.get(
        "HUAWEI_EVALUATOR_DIR", str(ROOT / "vendor/official_evaluator_fast"))).resolve()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rank_config(config: dict, control: str) -> dict:
    if control != "no_capacity_guidance":
        return config
    value = json.loads(json.dumps(config))
    value["capacity"] = {position: 10**18 for position in value["capacity"]}
    return value


def rank_score(view: dict, item: dict, scene: str, config: dict, control: str) -> tuple:
    light = item["light"]
    if control != "no_receive_domain":
        return tuple(light["score"])
    plan = item["plan"]
    mapping = {int(node): int(group) for node, group in plan["node_to_subgraph"].items()}
    core_of = {int(group): core for core, groups in enumerate(plan["core_schedules"]) for group in groups}
    finish = {}
    for node in map(int, view["topological"]):
        parent_finish = 0
        for parent in map(int, view["preds"][str(node)]):
            wait = config["a_waits"]["cross"] if scene == "A" and mapping[parent] != mapping[node] else 0
            if scene == "B" and core_of[mapping[parent]] != core_of[mapping[node]]:
                wait = config["b_wait"]
            parent_finish = max(parent_finish, finish[parent] + wait)
        finish[node] = parent_finish + max(1, int(view["ops"][str(node)].get("cycles", 0)))
    return (max(max(finish.values(), default=0), max(light["loads"].values(), default=0)), int(light["pressure_bytes"]))


def start_items(view: dict, scene: str, cores: int, config: dict, control: str) -> list[dict]:
    ranking = rank_config(config, control)
    starts = seed_plans(view, cores, scene, None if control == "no_receive_domain" else ranking)
    if control == "no_receive_domain":
        no_domain = dict(view)
        no_domain["tensor_sizes"] = {tid: 0 for tid in view["tensor_sizes"]}
        for label, count, order in ((f"{scene}2", 2 * cores if scene == "A" else 4 * cores, "d" if scene == "A" else "h"), (f"{scene}3", 4 * cores if scene == "A" else 8 * cores, "h" if scene == "A" else "r")):
            starts[label] = _make_plan(_split_order(no_domain, view[f"{order}_order"], count), cores, view)
    if control == "no_capacity_guidance":
        starts["B3"] = _make_plan(_split_order(view, view["h_order"], 8 * cores), cores, view, scene, ranking)
    starts.update(legacy_seed_plans(view, cores, scene))
    starts = [{"candidate": f"{name}_base", "source": "legacy_seed" if name.startswith("L") else "seed", "plan": plan} for name, plan in starts.items()]
    unique = {}
    for item in starts:
        unique.setdefault(plan_key(item["plan"]), item)
    result = list(unique.values())
    for item in result:
        item["light"] = light_score(view, item["plan"], scene, ranking)
        item["rank_score"] = rank_score(view, item, scene, ranking, control)
    return result


def path_boundary_variants(view: dict, plan: dict, cores: int, scene: str):
    mapping = {int(node): int(group) for node, group in plan["node_to_subgraph"].items()}
    core_of = {int(group): core for core, groups in enumerate(plan["core_schedules"]) for group in groups}
    loads = {core: sum(int(view["ops"][str(node)]["cycles"]) for node, group in mapping.items() if core_of[group] == core) for core in range(cores)}
    nodes = sorted(mapping, key=lambda node: (-int(view["ops"][str(node)]["cycles"]), -int(view["depth"].get(str(node), 0)), node))[:32]
    variants = []
    for node in nodes:
        neighbors = [int(other) for other in view["preds"][str(node)] + view["succs"][str(node)]]
        targets = sorted({core_of[mapping[other]] for other in neighbors if core_of[mapping[other]] != core_of[mapping[node]]})
        targets += [core for core in sorted(range(cores), key=lambda core: (loads[core], core)) if core != core_of[mapping[node]] and core not in targets][:1]
        for target in targets[:2]:
            for position in sorted({0, len(plan["core_schedules"][target])}):
                candidate = _move_node(view, plan, node, target, position, cores)
                if candidate is not None:
                    variants.append((f"path_n{node}_c{target}_p{position}", candidate, "ordinary"))
                    if len(variants) >= (8 if scene == "A" else 16):
                        return variants
    return variants


def control_variants(view: dict, plan: dict, cores: int, scene: str, config: dict, control: str, limit: int):
    split_view = view
    if control == "no_receive_domain":
        split_view = dict(view)
        split_view["tensor_sizes"] = {tid: 0 for tid in view["tensor_sizes"]}
    order_variants = core_order_variants(view, plan, cores, config)
    if control == "no_receive_domain":
        order_variants = [item for item in order_variants if not item[0].startswith("order_cache")]
    if control == "no_capacity_guidance":
        order_variants = [item for item in order_variants if not item[0].startswith("order_release")]
    categories = [
        _group_move_variants(view, plan, cores),
        _split_group_variants(split_view, plan, cores),
        _merge_variants(view, plan, cores),
        path_boundary_variants(view, plan, cores, scene) if control == "no_receive_domain" else _boundary_node_variants(view, plan, cores, scene),
        order_variants,
    ]
    if control != "no_capacity_guidance":
        categories.append(capacity_variants(view, plan, cores, config))
    seen = {plan_key(plan)}
    result = []
    for index in range(max(map(len, categories), default=0)):
        for category in categories:
            if index >= len(category):
                continue
            name, candidate, source = category[index]
            key = plan_key(candidate)
            if key not in seen:
                result.append((name, candidate, source))
                seen.add(key)
                if len(result) >= limit:
                    return result
    return result


def control_representatives(view: dict, initial: dict, cores: int, scene: str, config: dict, control: str):
    size = int(view["compute_ops"])
    rounds, limit = ((10, 64 if scene == "A" else 48) if size <= 2000 else (2, 48 if scene == "A" else 36) if size <= 10000 else (1, 32 if scene == "A" else 24))
    ranking = rank_config(config, control)
    current = initial
    pressure = int(initial["light"]["pressure_bytes"])
    ordinary = capacity = None
    seen = {plan_key(initial["plan"])}
    for round_index in range(rounds):
        round_items = []
        for name, plan, source in control_variants(view, current["plan"], cores, scene, ranking, control, limit):
            key = plan_key(plan)
            if key in seen:
                continue
            seen.add(key)
            item = {"candidate": f"r{round_index + 1}_{name}", "source": source, "plan": plan, "light": light_score(view, plan, scene, ranking)}
            item["rank_score"] = rank_score(view, item, scene, ranking, control)
            round_items.append(item)
            if control != "no_capacity_guidance" and int(item["light"]["pressure_bytes"]) < pressure:
                if capacity is None or (int(item["light"]["pressure_bytes"]), item["rank_score"], key) < (int(capacity["light"]["pressure_bytes"]), capacity["rank_score"], plan_key(capacity["plan"])):
                    capacity = item
        improved = [item for item in round_items if item["rank_score"] < current["rank_score"]]
        if not improved:
            break
        current = min(improved, key=lambda item: (item["rank_score"], plan_key(item["plan"])))
        ordinary = current
    return ordinary, capacity


def choose_plans(view: dict, scene: str, cores: int, config: dict, control: str, scene_out: Path, modules) -> list[dict]:
    starts = start_items(view, scene, cores, config, control)
    if control == "light_direct_select":
        initial = min(starts, key=lambda item: (item["rank_score"], item["candidate"]))
        ordinary, capacity = control_representatives(view, initial, cores, scene, config, control)
        pool = starts + [item for item in (ordinary, capacity) if item is not None]
        unique = {plan_key(item["plan"]): item for item in reversed(pool)}
        selected = sorted(unique.values(), key=lambda item: (item["rank_score"], item["candidate"]))[:2]
        write_json(scene_out / "light_ranking.json", {"starts": [{"candidate": item["candidate"], "source": item["source"], "score": item["rank_score"]} for item in starts], "selected": [item["candidate"] for item in selected]})
        return selected

    profiled, failures = [], []
    for item in starts:
        try:
            item["profile_score"] = profile(view["_graph"], item["plan"], scene, config, modules)["profile_score"]
            profiled.append(item)
        except Exception as exc:
            failures.append({"candidate": item["candidate"], "error_type": type(exc).__name__, "error": str(exc)})
    initial = min(profiled, key=lambda item: (tuple(item["profile_score"]), item["candidate"]))
    ordinary, capacity = control_representatives(view, initial, cores, scene, config, control)
    representatives = []
    known = {plan_key(item["plan"]) for item in starts}
    for item in (ordinary, capacity):
        if item is None or plan_key(item["plan"]) in known:
            continue
        known.add(plan_key(item["plan"]))
        try:
            item["profile_score"] = profile(view["_graph"], item["plan"], scene, config, modules)["profile_score"]
            representatives.append(item)
        except Exception as exc:
            failures.append({"candidate": item["candidate"], "error_type": type(exc).__name__, "error": str(exc)})
    write_json(scene_out / "profile_ranking.json", {"starts": [{"candidate": item["candidate"], "profile_score": item["profile_score"]} for item in profiled], "representatives": [{"candidate": item["candidate"], "profile_score": item["profile_score"]} for item in representatives], "failures": failures})
    alternatives = [item for item in profiled if item is not initial]
    alternatives += [item for item in representatives if tuple(item["profile_score"]) < tuple(initial["profile_score"])]
    return [initial] + sorted(alternatives, key=lambda item: (tuple(item["profile_score"]), item["candidate"]))[:1]


def worker(job: dict) -> list[dict]:
    data = ROOT / "data/raw/A题/data"
    modules = load_modules(evaluator_dir())
    config = read_config(modules, data / "config.txt")
    graph = load_graph(data / f"{job['case']}.json")
    view = static_view(graph)
    view["_graph"] = graph
    scene_out = Path(job["output_root"]) / job["control"] / job["case"] / f"{job['cores']}core" / job["scene"]
    plans = choose_plans(view, job["scene"], job["cores"], config, job["control"], scene_out, modules)
    rows = []
    for rank, item in enumerate(plans, start=1):
        candidate, plan, source = item["candidate"], item["plan"], item["source"]
        validate_plan(view, plan, job["cores"])
        write_json(scene_out / "candidates" / candidate / "plan.json", plan)
        started = time.perf_counter()
        try:
            result = evaluate(graph, plan, {"A": 1, "B": 2, "C": 3}[job["scene"]], config, modules)
            write_json(scene_out / "candidates" / candidate / "result.json", result)
            row = {
                "case": job["case"], "cores": job["cores"], "scene": job["scene"],
                "control": job["control"], "candidate": candidate, "source": source,
                "rank": rank, "status": "AI_VERIFIED", "plan_sha256": plan_key(plan),
                "evaluation_seconds": time.perf_counter() - started,
                "selected": False, "definition": job["definition"], **summary(result),
            }
        except Exception as exc:
            row = {
                "case": job["case"], "cores": job["cores"], "scene": job["scene"],
                "control": job["control"], "candidate": candidate, "source": source,
                "rank": rank, "status": "EVALUATION_FAILED", "plan_sha256": plan_key(plan),
                "evaluation_seconds": time.perf_counter() - started, "selected": False,
                "definition": job["definition"], "error_type": type(exc).__name__, "error": str(exc),
            }
            write_json(scene_out / "candidates" / candidate / "evaluation_failure.json", row)
        rows.append(row)
    successful = [row for row in rows if row["status"] == "AI_VERIFIED"]
    if successful:
        best = min(successful, key=lambda row: (row["makespan"], row["added_copy_bytes"], row["candidate"]))
        best["selected"] = True
        write_json(scene_out / "final_selection.json", {"candidate": best["candidate"], "source": best["source"], "plan_sha256": best["plan_sha256"], "makespan": best["makespan"], "added_copy_bytes": best["added_copy_bytes"], "full_calls": len(rows)})
    write_json(scene_out / "job_status.json", {"status": "COMPUTED" if len(successful) == len(rows) else "PARTIAL", "rows": rows})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--parallel", type=int, default=8)
    args = parser.parse_args()
    out = args.output_root.resolve()
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    out.mkdir(parents=True)
    definitions = {
        "no_receive_domain": "A/B starts and local edits use compute load, path and id instead of receive-domain byte priorities; real copy traffic remains in official profile and evaluation.",
        "no_capacity_guidance": "B R start uses H; capacity anchors, edits, representative and pressure ranking are removed; official Step2 spilling remains active.",
        "light_direct_select": "A starts and ordinary/capacity representatives are ranked directly by the light score without independent official profile selection.",
    }
    jobs = []
    for control, scenes in CONTROL_SCENES.items():
        for case in REPRESENTATIVE_CASES:
            for cores in (2, 5):
                for scene in scenes:
                    jobs.append({"control": control, "case": case, "cores": cores, "scene": scene, "definition": definitions[control], "output_root": str(out)})
    manifest = {"run_id": out.name, "status": "RUNNING", "cases": REPRESENTATIVE_CASES, "cores": [2, 5], "controls": definitions, "jobs": len(jobs), "parallel": args.parallel, "official_evaluator_dir": str(evaluator_dir()), "idea_sha256": file_sha(ROOT / "idea/A题_Final_idea_给codex运行.md"), "config_sha256": file_sha(ROOT / "data/raw/A题/data/config.txt"), "solver_source_sha256": {str(path.relative_to(ROOT)): file_sha(path) for path in (Path(__file__).resolve(), ROOT / "src/huawei_code/candidates.py", ROOT / "src/huawei_code/plan.py", ROOT / "src/huawei_code/scoring.py", ROOT / "src/huawei_code/official.py")}, "started_at": time.time()}
    write_json(out / "run_manifest.json", manifest)
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(worker, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            rows.extend(result)
            print(json.dumps({"control": result[0]["control"], "case": result[0]["case"], "cores": result[0]["cores"], "scene": result[0]["scene"], "statuses": [row["status"] for row in result]}, ensure_ascii=False), flush=True)
    write_csv(out / "controls.csv", rows)
    status = "COMPUTED" if sum(row["selected"] for row in rows) == len(jobs) and all(row["status"] == "AI_VERIFIED" for row in rows) else "PARTIAL"
    write_json(out / "run_manifest.json", {**manifest, "status": status, "rows": len(rows), "verified_rows": sum(row["status"] == "AI_VERIFIED" for row in rows), "selected_jobs": sum(row["selected"] for row in rows), "ended_at": time.time()})
    print(json.dumps({"run_id": out.name, "status": status, "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
