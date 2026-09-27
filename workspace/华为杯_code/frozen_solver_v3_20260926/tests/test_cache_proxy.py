"""审阅用 Cache 查询时序解析例。

这些微例只检查轻量 FIFO 代理的事件语义，不替代官方问题三评估器：
60000 B、DDR=60 B/cycle、Cache=250 B/cycle 时，首读需要 1000 cycle。
同时发射的三个查询都在首读完成前观察到空 Cache；错峰到 1000 cycle 的
两个查询则在完成事件先于查询事件处理后命中。
"""

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


CONFIG = {
    "bandwidth": 60,
    "capacity": {"L1": 524288, "UB": 131072},
    "a_waits": {"cross": 1000, "same": 100},
    "b_wait": 500,
    "cache": {"capacity": 1_048_576, "bandwidth": 250},
}


def _view(staggered: bool) -> dict:
    """Three cores read one 60000 B input; optionally delay cores 1 and 2."""
    ops = {"1": {"cycles": 1000}, "2": {"cycles": 1000}, "3": {"cycles": 1000}}
    preds = {"1": [], "2": [], "3": []}
    topo = [1, 2, 3]
    mapping = {1: 0, 2: 1, 3: 2}
    schedules = [[0], [1], [2]]
    if staggered:
        ops.update({"20": {"cycles": 1000}, "30": {"cycles": 1000}})
        preds = {"1": [], "2": [20], "3": [30], "20": [], "30": []}
        topo = [1, 20, 2, 30, 3]
        mapping = {1: 0, 20: 1, 2: 1, 30: 2, 3: 2}
    return {
        "ops": ops,
        "preds": preds,
        "topological": topo,
        "tensor_sizes": {"7": 60000},
        "tensor_consumers": {"7": [1, 2, 3]},
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
    assert replay["miss_count"] == 1
    assert replay["hit_bytes"] == 120000
    assert replay["miss_bytes"] == 60000
    # The first read completes and inserts at t=1000 before the two queries
    # at the same timestamp are issued.
    events = [(event["time"], event["event"]) for event in replay["events"]]
    assert events[:3] == [(0, "miss"), (1000, "insert"), (1000, "hit")]


def test_service_breakdown_moves_only_hits_to_cache_pool():
    view = _view(staggered=True)
    plan = _plan(view)
    breakdown = structural_byte_breakdown(view, plan, "C")
    assert breakdown == {
        "input_read_bytes": 180000,
        "cross_read_bytes": 0,
        "cross_write_bytes": 0,
        "output_write_bytes": 0,
        "structural_copy_bytes": 180000,
    }
    score = light_score(view, plan, "C", CONFIG)
    assert score["copy_bytes"] == 180000
    assert score["cache_query_bytes"] == 180000
    assert score["cache_service_bytes"] == 120000
    assert score["ddr_service_bytes"] == 60000


def test_capacity_pressure_sums_each_core_pool_excess():
    view = _view(staggered=False)
    view["tensor_pos"] = {"7": "L1"}
    plan = _plan(view)
    config = {**CONFIG, "capacity": {"L1": 30000, "UB": 0}}
    assert capacity_pressure(view, plan, "C", config) == 90000
