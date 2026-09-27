"""Fresh bridge to the byte-preserved official A-problem evaluator."""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path


def load_modules(code_dir: Path):
    sys.path.insert(0, str(code_dir))
    return {key: importlib.import_module(name) for key, name in {
        "validation": "evaluation_validation", "a": "multicore_cut_evaluate_problem_1",
        "b": "multicore_cut_evaluate_problem_2", "c": "multicore_cut_evaluate_problem_3",
    }.items()}


def read_config(modules, path: Path):
    validation, a, b, c = modules["validation"], modules["a"], modules["b"], modules["c"]
    settings = validation.read_evaluation_config(str(path))
    raw_a = a.read_scene_a_config(str(path))
    raw_b = b.read_scene_b_config(str(path))
    raw_c = c.read_cache_config(str(path))
    settings.update({
        "a_waits": {"cross": raw_a["task_cross_core_wait_cycles"], "same": raw_a["task_same_core_wait_cycles"]},
        "b_wait": raw_b["cross_core_copy_delay_cycles"],
        "cache": {"capacity": raw_c["cache_capacity_bytes"], "bandwidth": raw_c["cache_bandwidth_bytes_per_cycle"]},
    })
    return settings


def profile(graph, plan, scene, config, modules):
    scene = scene.upper()
    if scene == "A":
        tasks, cross_traffic, movement, plan_view = modules["a"]._build_scene_a_tasks(graph, plan, config["bandwidth"], config["capacity"])
        links = []
    else:
        builder = modules[scene.lower()]
        tasks, links, cross_traffic, movement, plan_view = builder._build_scene_b_tasks(graph, plan, bandwidth=config["bandwidth"], capacity=config["capacity"])
    return {"scene": scene, "tasks": len(tasks), "cross_links": len(links), "cross_task_traffic": cross_traffic, "movement": movement, "expanded_ops": sum(len(t.get("graph", {}).get("ops", ())) for t in tasks.values()), "spill_ops": sum(1 for t in tasks.values() for op in t.get("graph", {}).get("ops", ()) if op.get("spill_logical_tid") is not None or op.get("op") in {"SPILL_IN", "SPILL_OUT"})}


def evaluate(graph, plan, problem, config, modules, *, cache=False):
    common = {"bandwidth": config["bandwidth"], "capacity": config["capacity"]}
    if problem == 1:
        w = config["a_waits"]
        return modules["a"].evaluate_scene_a(graph, plan, **common, cross_core_wait=w["cross"], same_core_wait=w["same"])
    delay = config["b_wait"]
    if problem == 2:
        return modules["b"].evaluate_scene_b(graph, plan, **common, cross_core_copy_delay=delay)
    return modules["c"].evaluate_problem_3(graph, plan, **common, cross_core_copy_delay=delay, cache_capacity_bytes=config["cache"]["capacity"], cache_bandwidth_bytes_per_cycle=config["cache"]["bandwidth"])


def summary(result):
    movement = result.get("data_movement_bytes", {})
    cache = result.get("cache_stats") or {}
    return {"makespan": result.get("makespan"), "scheduled_copy_bytes": movement.get("scheduled_copy_bytes"), "original_graph_copy_bytes": movement.get("original_graph_copy_bytes"), "added_copy_bytes": movement.get("added_copy_bytes"), "partition_added_copy_bytes": movement.get("partition_added_copy_bytes"), "spill_added_copy_bytes": movement.get("spill_added_copy_bytes"), "cache_hit_bytes": cache.get("hit_bytes", 0), "cache_miss_bytes": cache.get("miss_bytes", 0), "cache_hit_rate": cache.get("hit_rate", 0.0)}


def file_sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
