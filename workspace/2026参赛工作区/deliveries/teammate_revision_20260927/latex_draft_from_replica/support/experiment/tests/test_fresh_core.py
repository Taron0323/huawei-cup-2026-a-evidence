import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from huawei_code.graph import load_graph, static_view
from huawei_code.plan import canonical_plan, pad_plan_cores, validate_plan, seed_plans
from huawei_code.gpu_score import backend_info, rank_load_vectors


def test_static_graph_and_plan_protocol():
    graph = load_graph(ROOT / "data/raw/A题/data/case_001.json")
    view = static_view(graph)
    for scene in ("A", "B"):
        plans = seed_plans(view, 2, scene)
        assert plans
        for plan in plans.values():
            validate_plan(view, plan, 2, scene)


def test_canonical_order_is_preserved():
    plan = canonical_plan({10: 4, 20: 2, 30: 4}, [[4, 2], []])
    assert plan["core_schedules"][0] == [0, 1]


def test_same_core_contracted_cycle_is_scene_a_only():
    view = {
        "nodes": [0, 1],
        "ops": {"0": {"cycles": 1}, "1": {"cycles": 1}},
        "preds": {"0": [], "1": [0]},
        "succs": {"0": [1], "1": []},
    }
    plan = {"node_to_subgraph": {0: 0, 1: 1}, "core_schedules": [[1, 0]]}
    with pytest.raises(ValueError, match="contracted compute graph is cyclic"):
        validate_plan(view, plan, 1, "A")
    validate_plan(view, plan, 1, "B")
    validate_plan(view, plan, 1, "C")


def test_incumbent_plan_can_be_padded_with_idle_cores():
    original = {"node_to_subgraph": {0: 0, 1: 1}, "core_schedules": [[0], [1]]}
    padded = pad_plan_cores(original, 5)
    assert len(original["core_schedules"]) == 2
    assert len(padded["core_schedules"]) == 5
    assert padded["core_schedules"][:2] == original["core_schedules"]
    assert padded["core_schedules"][2:] == [[], [], []]


def test_required_incumbent_is_evaluated_before_light_ranked_variants():
    from run_experiment import _prioritize_required

    incumbent = {"candidate": "incumbent", "plan": {"core_schedules": [[0]]}}
    variant = {"candidate": "variant", "plan": {"core_schedules": [[0, 1]]}}
    assert [item["candidate"] for item in _prioritize_required([variant], [incumbent])] == ["incumbent", "variant"]


def test_gpu_or_cpu_rank_is_explicit():
    order, info = rank_load_vectors([[1, 4], [3, 2], [8, 8]])
    assert order == [1, 0, 2]
    assert info["backend"] in {"mps", "cpu", "unavailable"}
