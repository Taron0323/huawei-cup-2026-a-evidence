"""Fresh bridge to the byte-preserved official A-problem evaluator."""

from __future__ import annotations

from collections import OrderedDict, defaultdict
import hashlib
import heapq
import importlib
import math
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


def _task_profile(tasks, links, scene, config, plan_view=None):
    """Summarize the official intra-core expansion for candidate ranking.

    ``prepare_step3_execution`` is already part of the official builders, so
    the values below come from the evaluator's real expanded graph rather than
    the plan-level proxy.  The cross-core path is a deterministic lower-cost
    reconstruction used only to rank profiles; full event evaluation remains
    authoritative.
    """
    task_records = {}
    for task_id, task in tasks.items():
        step3 = task.get("step3", {})
        task_records[int(task_id)] = {
            "task_id": int(task_id),
            "core_id": int(task.get("core_id", task_id)),
            "makespan": int(step3.get("makespan", 0)),
            "expanded_ops": len(task.get("graph", {}).get("ops", ())),
            "spill_ops": sum(
                1 for op in task.get("graph", {}).get("ops", ())
                if op.get("spill_logical_tid") is not None
                or op.get("op") in {"SPILL_IN", "SPILL_OUT"}
            ),
            "memory_peak": dict(step3.get("memory_peak", {})),
            "ddr_ops": sum(1 for value in step3.get("ddr_transfer", {}).values() if value),
        }

    # A task's local Step3 timeline is measured from zero.  Add the explicit
    # inter-task waits and external COPY links to get a consistent reference
    # path for comparing profiles.
    predecessor_edges = []
    if scene == "A":
        for task_id, task in tasks.items():
            for pred in task.get("pred_tasks", ()):
                predecessor_edges.append((int(pred), int(task_id), "cross"))
        by_core = {}
        for task_id, task in tasks.items():
            by_core.setdefault(int(task.get("core_id", task_id)), []).append(int(task_id))
        core_orders = (plan_view or {}).get("core_orders", {})
        for core, order in by_core.items():
            planned = core_orders.get(core, core_orders.get(str(core), ()))
            ordered = [int(task_id) for task_id in planned if int(task_id) in order]
            ordered.extend(sorted(set(order) - set(ordered)))
            for left, right in zip(ordered, ordered[1:]):
                predecessor_edges.append((left, right, "same"))
    else:
        for link in links:
            predecessor_edges.append((
                int(link["source_core"]), int(link["target_core"]), "link",
                int(link["source_copy_out_id"]), int(link["target_copy_in_id"]),
            ))

    offsets = {task_id: 0 for task_id in task_records}
    # Task dependencies are acyclic.  A bounded relaxation also handles the
    # parallel-core link representation without duplicating the evaluator.
    for _ in range(max(1, len(task_records))):
        changed = False
        for edge in predecessor_edges:
            source, target, kind = edge[:3]
            if source not in task_records or target not in task_records:
                continue
            if kind == "same":
                delay = int(config["a_waits"]["same"])
                finish = offsets[source] + task_records[source]["makespan"] + delay
            elif kind == "cross":
                source_core = task_records[source]["core_id"]
                target_core = task_records[target]["core_id"]
                delay = int(config["a_waits"]["cross"] if source_core != target_core else config["a_waits"]["same"])
                finish = offsets[source] + task_records[source]["makespan"] + delay
            else:
                delay = int(config["b_wait"])
                source_end = task_records[source]["makespan"]
                target_end = task_records[target]["makespan"]
                target_op = edge[4]
                target_step3 = tasks[target].get("step3", {})
                target_prefix = int(target_step3.get("op_end", {}).get(target_op, 0))
                finish = offsets[source] + source_end + delay + max(0, target_end - target_prefix)
            if finish > offsets[target]:
                offsets[target] = finish
                changed = True
        if not changed:
            break

    reference_makespan = max(
        (offsets[task_id] + task_records[task_id]["makespan"] for task_id in task_records),
        default=0,
    )
    return task_records, int(reference_makespan)


def _expanded_reference(tasks, links, config, copy_in_meta, movement, scene):
    operations = {}
    predecessors = defaultdict(list)
    successors = defaultdict(list)

    def edge(source, target, delay=0):
        predecessors[target].append((source, delay))
        successors[source].append(target)

    for core, task in tasks.items():
        core = int(core)
        for op_id, op in task["op_by_id"].items():
            operations[(core, int(op_id))] = op
        for op_id, parents in task["op_preds"].items():
            for parent in parents:
                edge((core, int(parent)), (core, int(op_id)))
        for order in task["pipe_ops"].values():
            for left, right in zip(order, order[1:]):
                edge((core, int(left)), (core, int(right)))
    for link in links:
        edge(
            (int(link["source_core"]), int(link["source_copy_out_id"])),
            (int(link["target_core"]), int(link["target_copy_in_id"])),
            int(config["b_wait"]),
        )

    indegree = {node: len(predecessors[node]) for node in operations}
    ready = [node for node, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for target in successors[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, target)
    if len(order) != len(operations):
        raise ValueError("expanded execution graph has a cycle")

    durations = {node: max(0, int(op["cycles"])) for node, op in operations.items()}

    def times(changed):
        starts, finishes = {}, {}
        for node in order:
            starts[node] = max((finishes[parent] + delay for parent, delay in predecessors[node]), default=0)
            finishes[node] = starts[node] + changed[node]
        return starts, finishes, max(finishes.values(), default=0)

    starts, _finishes, _path = times(durations)
    hit_ops = set()
    hit_bytes = 0
    if scene == "C":
        capacity = int(config["cache"]["capacity"])
        bandwidth = int(config["cache"]["bandwidth"])
        queue = [(starts[node], 1, node[0], node[1], tid, size) for node, (tid, size) in copy_in_meta.items()]
        heapq.heapify(queue)
        entries = OrderedDict()
        used = 0
        while queue:
            now, kind, core, op_id, tid, size = heapq.heappop(queue)
            node = (core, op_id)
            if kind == 1:
                hit = 0 < size <= capacity and tid in entries
                if hit:
                    hit_ops.add(node)
                    hit_bytes += size
                duration = max(1, math.ceil(size / bandwidth)) if hit else durations[node]
                heapq.heappush(queue, (now + duration, 0, core, op_id, tid, size))
            elif 0 < size <= capacity and tid not in entries:
                while entries and used + size > capacity:
                    _old_tid, old_size = entries.popitem(last=False)
                    used -= old_size
                entries[tid] = size
                used += size

    adjusted = dict(durations)
    for node in hit_ops:
        adjusted[node] = max(1, math.ceil(copy_in_meta[node][1] / int(config["cache"]["bandwidth"])))
    _starts, _finishes, path = times(adjusted)
    ddr_work = sum(adjusted[node] for node, op in operations.items() if op["pipe"] in {"PIPE_MTE2", "PIPE_MTE3"} and node not in hit_ops)
    cache_work = sum(adjusted[node] for node in hit_ops)
    scheduled_bytes = int(movement.get("scheduled_copy_bytes", 0))
    spill_bytes = int(movement.get("spill_added_copy_bytes", 0))
    if scene == "C":
        ddr_bytes = max(0, scheduled_bytes - hit_bytes)
        score = [max(path, ddr_work, cache_work), ddr_bytes / int(config["bandwidth"]), -hit_bytes, spill_bytes]
    else:
        score = [max(path, ddr_work), scheduled_bytes, spill_bytes]
    return {
        "profile_score": score,
        "expanded_reference_makespan": path,
        "expanded_ddr_work": ddr_work,
        "expanded_cache_work": cache_work,
        "expanded_cache_hit_bytes": hit_bytes,
        "expanded_copy_in_queries": len(copy_in_meta),
        "profile_score_method": "expanded_dependency_path_and_one_fifo_replay" if scene == "C" else "expanded_dependency_path",
    }


def profile(graph, plan, scene, config, modules):
    scene = scene.upper()
    if scene == "A":
        tasks, cross_traffic, movement, plan_view = modules["a"]._build_scene_a_tasks(graph, plan, config["bandwidth"], config["capacity"])
        links = []
    else:
        builder = modules[scene.lower()]
        tasks, links, cross_traffic, movement, plan_view = builder._build_scene_b_tasks(graph, plan, bandwidth=config["bandwidth"], capacity=config["capacity"])
        modules["validation"].validate_execution(tasks, links)
    task_records, reference_makespan = _task_profile(tasks, links, scene, config, plan_view)
    copy_in_logical_tids = {}
    for task_id, task in tasks.items():
        core_id = int(task.get("core_id", task_id))
        for op_id, op in task.get("op_by_id", {}).items():
            if op.get("op") != "COPY_IN":
                continue
            logical_tids = []
            for tid in task.get("out_tids", {}).get(op_id, ()):
                tensor = task.get("tensor_by_id", {}).get(tid, {})
                if tensor.get("pos") != "DDR":
                    logical_tids.append(int(tensor.get("logical_tid", tid)))
            if logical_tids:
                copy_in_logical_tids[f"{core_id}:{int(op_id)}"] = logical_tids[0]
    scheduled_copy_bytes = int(movement.get("scheduled_copy_bytes", 0))
    spill_copy_bytes = int(movement.get("spill_added_copy_bytes", 0))
    ddr_cycles = math.ceil(scheduled_copy_bytes / int(config["bandwidth"])) if scheduled_copy_bytes else 0
    profile_time = max(reference_makespan, ddr_cycles)
    result = {
        "scene": scene,
        "tasks": len(tasks),
        "cross_links": len(links),
        "cross_task_traffic": cross_traffic,
        "movement": movement,
        "expanded_ops": sum(item["expanded_ops"] for item in task_records.values()),
        "spill_ops": sum(item["spill_ops"] for item in task_records.values()),
        "reference_makespan": int(reference_makespan),
        "ddr_cycles": int(ddr_cycles),
        "profile_score": [int(profile_time), scheduled_copy_bytes, spill_copy_bytes],
        "task_profiles": task_records,
        "copy_in_logical_tids": copy_in_logical_tids,
    }
    if scene in {"B", "C"}:
        copy_in_meta = {}
        for core, task in tasks.items():
            for op_id, op in task["op_by_id"].items():
                if op["op"] != "COPY_IN":
                    continue
                key = f"{int(core)}:{int(op_id)}"
                tid = copy_in_logical_tids.get(key)
                if tid is None:
                    continue
                local_tensors = [task["tensor_by_id"][out_tid] for out_tid in task["out_tids"].get(op_id, ()) if task["tensor_by_id"][out_tid]["pos"] != "DDR"]
                if local_tensors:
                    copy_in_meta[(int(core), int(op_id))] = (tid, int(local_tensors[0]["size"]))
        result.update(_expanded_reference(tasks, links, config, copy_in_meta, movement, scene))
    return result


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
