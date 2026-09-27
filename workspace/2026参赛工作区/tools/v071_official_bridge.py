"""Small, explicit bridge from V0.7.1 plans to the supplied evaluator."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any


def load_official_modules(raw_code: Path) -> dict[str, Any]:
    sys.path.insert(0, str(raw_code))
    names = {
        "validation": "evaluation_validation",
        "a": "multicore_cut_evaluate_problem_1",
        "b": "multicore_cut_evaluate_problem_2",
        "c": "multicore_cut_evaluate_problem_3",
    }
    return {key: importlib.import_module(name) for key, name in names.items()}


def read_config(modules: dict[str, Any], config_path: Path) -> dict[str, Any]:
    validation = modules["validation"]
    a = modules["a"]
    b = modules["b"]
    c = modules["c"]
    settings = validation.read_evaluation_config(str(config_path))
    settings["a_waits"] = a.read_scene_a_config(str(config_path))
    settings["b_scene"] = b.read_scene_b_config(str(config_path))
    settings["cache"] = c.read_cache_config(str(config_path))
    return settings


def profile_plan(graph: dict[str, Any], plan: dict[str, Any], scene: str, config: dict[str, Any], modules: dict[str, Any]) -> dict[str, Any]:
    scene = scene.upper()
    if scene == "A":
        tasks, cross_task_traffic, movement, plan_view = modules["a"]._build_scene_a_tasks(graph, plan, config["bandwidth"], config["capacity"])
        cross_links = []
    else:
        builder = modules["b"] if scene == "B" else modules["c"]
        kwargs = dict(bandwidth=config["bandwidth"], capacity=config["capacity"])
        tasks, cross_links, cross_task_traffic, movement, plan_view = builder._build_scene_b_tasks(graph, plan, **kwargs)
    expanded_ops = sum(len(task.get("graph", {}).get("ops", ())) for task in tasks.values())
    pipe_ops = sum(sum(len(values) for values in task.get("pipe_ops", {}).values()) for task in tasks.values())
    spill_ops = sum(1 for task in tasks.values() for op in task.get("graph", {}).get("ops", ())
                    if op.get("spill_logical_tid") is not None
                    or op.get("op") in {"SPILL_IN", "SPILL_OUT"})
    return {
        "status": "AI_VERIFIED",
        "scene": scene,
        "tasks": len(tasks),
        "cross_links": len(cross_links),
        "cross_task_traffic": cross_task_traffic,
        "expanded_ops": expanded_ops,
        "pipe_ops": pipe_ops,
        "spill_ops": spill_ops,
        "movement": movement,
        "plan_view_keys": sorted(plan_view),
    }


def evaluate_plan(graph: dict[str, Any], plan: dict[str, Any], problem: int, config: dict[str, Any], modules: dict[str, Any], *, cache_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    common = {"bandwidth": config["bandwidth"], "capacity": config["capacity"]}
    if problem == 1:
        waits = config["a_waits"]
        return modules["a"].evaluate_scene_a(graph, plan, **common,
            cross_core_wait=waits["task_cross_core_wait_cycles"],
            same_core_wait=waits["task_same_core_wait_cycles"])
    scene = config["b_scene"]
    if problem == 2:
        return modules["b"].evaluate_scene_b(graph, plan, **common,
            cross_core_copy_delay=scene["cross_core_copy_delay_cycles"])
    cache = dict(config["cache"])
    if cache_overrides:
        cache.update(cache_overrides)
    return modules["c"].evaluate_problem_3(graph, plan, **common,
        cross_core_copy_delay=scene["cross_core_copy_delay_cycles"], **cache)


def result_summary(result: dict[str, Any], scene: str) -> dict[str, Any]:
    movement = result.get("data_movement_bytes", {})
    cache = result.get("cache_stats") or {}
    hit = int(cache.get("hit_bytes", 0) or 0)
    miss = int(cache.get("miss_bytes", 0) or 0)
    return {
        "status": "AI_VERIFIED",
        "scene": scene,
        "makespan": result.get("makespan"),
        "scheduled_copy_bytes": movement.get("scheduled_copy_bytes"),
        "added_copy_bytes": movement.get("added_copy_bytes"),
        "partition_added_copy_bytes": movement.get("partition_added_copy_bytes"),
        "spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
        "cache_hit_bytes": hit,
        "cache_miss_bytes": miss,
        "cache_hit_rate": cache.get("hit_rate", 0.0),
        "physical_ddr_bytes": movement.get("scheduled_copy_bytes", 0) - hit if scene == "C" else None,
    }
