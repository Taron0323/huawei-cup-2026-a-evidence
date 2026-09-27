"""60000 B Cache issue-order examples for the proxy and official evaluator."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huawei_code.scoring import (  # noqa: E402
    capacity_pressure,
    fifo_cache_replay,
    light_score,
    structural_byte_breakdown,
)
from huawei_code.official import evaluate, load_modules  # noqa: E402


CONFIG = {
    "bandwidth": 60,
    "capacity": {"L1": 524288, "UB": 131072},
    "a_waits": {"cross": 1000, "same": 100},
    "b_wait": 500,
    "cache": {"capacity": 1_048_576, "bandwidth": 250},
}


def _view(staggered: bool) -> dict:
    """Three cores read one input; staggered cores first read other inputs."""
    ops = {"1": {"cycles": 1000}, "2": {"cycles": 1000}, "3": {"cycles": 1000}}
    preds = {"1": [], "2": [], "3": []}
    topo = [1, 2, 3]
    mapping = {1: 0, 2: 1, 3: 2}
    schedules = [[0], [1], [2]]
    sizes = {"7": 60000}
    consumers = {"7": [1, 2, 3]}
    if staggered:
        ops.update({"20": {"cycles": 1000}, "30": {"cycles": 1000}})
        preds = {"1": [], "2": [20], "3": [30], "20": [], "30": []}
        topo = [1, 20, 2, 30, 3]
        mapping.update({20: 3, 30: 4})
        schedules = [[0], [3, 1], [4, 2]]
        sizes.update({"8": 60000, "9": 60000})
        consumers.update({"8": [20], "9": [30]})
    return {
        "ops": ops,
        "preds": preds,
        "topological": topo,
        "tensor_sizes": sizes,
        "tensor_consumers": consumers,
        "tensor_producers": {},
        "output_tensors": [],
        "node_to_subgraph": mapping,
        "core_schedules": schedules,
    }


def _plan(view: dict) -> dict:
    return {
        "node_to_subgraph": view["node_to_subgraph"],
        "core_schedules": view["core_schedules"],
    }


def _official_graph(staggered: bool, competing_inputs: bool = True) -> dict:
    nodes = (1, 2, 3, 20, 30) if staggered else (1, 2, 3)
    tensors = (7, 8, 9) if staggered and competing_inputs else (7,)
    edges = [{"source": 7, "target": node} for node in (1, 2, 3)]
    if staggered:
        edges.extend(({"source": 20, "target": 2}, {"source": 30, "target": 3}))
        if competing_inputs:
            edges.extend(({"source": 8, "target": 20}, {"source": 9, "target": 30}))
    return {
        "ops": [{"id": node, "op": "ADD", "pipe": "PIPE_V", "cycles": 1000} for node in nodes],
        "tensors": [{"id": tid, "pos": "L1", "size": 60000} for tid in tensors],
        "edges": edges,
    }


def _multi_producer_view() -> dict:
    """One tensor is produced and consumed on both of two cores."""
    return {
        "ops": {
            "10": {"cycles": 100},
            "11": {"cycles": 100},
            "1": {"cycles": 100},
            "2": {"cycles": 100},
        },
        "preds": {"10": [], "11": [], "1": [10], "2": [11]},
        "topological": [10, 11, 1, 2],
        "tensor_sizes": {"7": 60000},
        "tensor_consumers": {"7": [1, 2]},
        "tensor_producers": {"7": [10, 11]},
        "output_tensors": [],
        "node_to_subgraph": {10: 0, 1: 0, 11: 1, 2: 1},
        "core_schedules": [[0], [1]],
    }


def test_simultaneous_60000_byte_queries_all_miss():
    view = _view(staggered=False)
    replay = fifo_cache_replay(view, _plan(view), CONFIG)
    assert replay["hit_count"] == 0
    assert replay["miss_count"] == 3
    assert replay["hit_bytes"] == 0
    assert replay["miss_bytes"] == 180000
    assert [event["event"] for event in replay["events"]].count("insert") == 1


def test_staggered_60000_byte_queries_hit_after_first_completion():
    view = _view(staggered=True)
    replay = fifo_cache_replay(view, _plan(view), CONFIG)
    assert replay["hit_count"] == 2
    assert replay["miss_count"] == 3
    assert replay["hit_bytes"] == 120000
    assert replay["miss_bytes"] == 180000
    shared = [(event["time"], event["event"]) for event in replay["events"] if event["tensor_id"] == 7]
    assert shared == [(0, "miss"), (1000, "insert"), (1000, "hit"), (1000, "hit")]


def test_official_60000_byte_queries_follow_the_same_zero_to_two_hit_order():
    modules = load_modules(ROOT / "vendor" / "official_evaluator")
    simultaneous = _view(staggered=False)
    together = evaluate(_official_graph(False), _plan(simultaneous), 3, CONFIG, modules)
    assert together["cache_stats"]["copy_in_hits"] == 0
    assert together["cache_stats"]["copy_in_misses"] == 3
    assert [(event["time"], event["event"]) for event in together["cache_events"]] == [
        (0, "miss"), (0, "miss"), (0, "miss"), (3000, "insert")
    ]

    staggered = _view(staggered=True)
    delayed = evaluate(_official_graph(True), _plan(staggered), 3, CONFIG, modules)
    assert delayed["cache_stats"]["copy_in_hits"] == 2
    assert delayed["cache_stats"]["copy_in_misses"] == 3
    assert [(event["time"], event["event"], event["tensor_id"]) for event in delayed["cache_events"]] == [
        (0, "miss", 7), (0, "miss", 8), (0, "miss", 9),
        (3000, "insert", 7), (3000, "insert", 8), (3000, "insert", 9),
        (3000, "hit", 7), (3000, "hit", 7),
    ]
    # Merely putting a compute predecessor in an earlier group is insufficient:
    # MTE2 can issue COPY_IN concurrently with compute on PIPE_V.
    compute_only = evaluate(_official_graph(True, competing_inputs=False), _plan(staggered), 3, CONFIG, modules)
    assert compute_only["cache_stats"]["copy_in_hits"] == 0
    compute_only_view = _view(staggered=True)
    for tid in ("8", "9"):
        del compute_only_view["tensor_sizes"][tid]
        del compute_only_view["tensor_consumers"][tid]
    assert fifo_cache_replay(compute_only_view, _plan(compute_only_view), CONFIG)["hit_count"] == 0


def test_multi_producer_tensor_keeps_one_remote_query_per_consumer_core():
    replay = fifo_cache_replay(_multi_producer_view(), _plan(_multi_producer_view()), CONFIG)
    assert replay["query_count"] == 2
    assert replay["miss_count"] == 2
    assert replay["hit_count"] == 0


def test_service_breakdown_moves_only_hits_to_cache_pool():
    view = _view(staggered=True)
    plan = _plan(view)
    breakdown = structural_byte_breakdown(view, plan, "C")
    assert breakdown == {
        "input_read_bytes": 300000,
        "cross_read_bytes": 0,
        "cross_write_bytes": 0,
        "output_write_bytes": 0,
        "structural_copy_bytes": 300000,
    }
    score = light_score(view, plan, "C", CONFIG)
    assert score["copy_bytes"] == 300000
    assert score["cache_query_bytes"] == 300000
    assert score["cache_service_bytes"] == 120000
    assert score["ddr_service_bytes"] == 180000
    without_cache = light_score(view, plan, "B", CONFIG)
    assert without_cache["ddr_service_cycles"] == 5000
    assert score["ddr_service_cycles"] == 3000
    assert score["light_time"] < without_cache["light_time"]


def test_capacity_pressure_sums_each_core_pool_excess():
    view = _view(staggered=False)
    view["tensor_pos"] = {"7": "L1"}
    plan = _plan(view)
    config = {**CONFIG, "capacity": {"L1": 30000, "UB": 0}}
    assert capacity_pressure(view, plan, "C", config) == 90000


def _liveness_case():
    view = {
        "ops": {str(node): {"cycles": 1} for node in range(1, 7)},
        "preds": {str(node): ([node - 1] if node % 2 == 0 else []) for node in range(1, 7)},
        "topological": list(range(1, 7)),
        "tensor_sizes": {str(tid): 80 for tid in (101, 102, 103)},
        "tensor_pos": {str(tid): "L1" for tid in (101, 102, 103)},
        "tensor_producers": {"101": [1], "102": [3], "103": [5]},
        "tensor_consumers": {"101": [2], "102": [4], "103": [6]},
        "output_tensors": [],
    }
    graph = {
        "ops": [{"id": node, "op": "ADD", "pipe": "PIPE_V", "cycles": 1} for node in range(1, 7)],
        "tensors": [{"id": tid, "pos": "L1", "size": 80} for tid in (101, 102, 103)],
        "edges": [
            {"source": node, "target": tid}
            for node, tid in ((1, 101), (3, 102), (5, 103))
        ] + [
            {"source": tid, "target": node}
            for tid, node in ((101, 2), (102, 4), (103, 6))
        ],
    }
    return view, graph


def test_operation_level_lifetimes_release_short_lived_tensors_within_one_group():
    view, _graph = _liveness_case()
    plan = {"node_to_subgraph": {node: 0 for node in range(1, 7)}, "core_schedules": [[0]]}
    config = {**CONFIG, "capacity": {"L1": 160, "UB": 0}}
    assert capacity_pressure(view, plan, "C", config) == 0


def test_capacity_proxy_order_agrees_with_official_step2_spill_direction():
    view, graph = _liveness_case()
    mapping = {node: node - 1 for node in range(1, 7)}
    adjacent = [1, 2, 3, 4, 5, 6]
    overlapping = [1, 3, 5, 2, 4, 6]
    config = {**CONFIG, "capacity": {"L1": 160, "UB": 0}}
    proxy = []
    for sequence in (adjacent, overlapping):
        plan = {"node_to_subgraph": mapping, "core_schedules": [[mapping[node] for node in sequence]]}
        proxy.append(capacity_pressure(view, plan, "C", config))
    assert proxy == [0, 80]

    # Check the directional ranking against the unmodified official Step2,
    # which can spill a future-use tensor in the overlapping order.
    sys.path.insert(0, str(ROOT / "vendor" / "official_evaluator"))
    from schedule_step2 import step2_spill_insertion  # noqa: E402

    spills = [
        step2_spill_insertion(graph, sequence, config["capacity"])["spill_records"]
        for sequence in (adjacent, overlapping)
    ]
    assert len(spills[0]) == 0
    assert len(spills[1]) > 0
