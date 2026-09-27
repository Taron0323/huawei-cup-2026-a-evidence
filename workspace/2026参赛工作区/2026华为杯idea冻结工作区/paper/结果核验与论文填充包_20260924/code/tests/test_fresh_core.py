import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huawei_code.graph import load_graph, static_view
from huawei_code.plan import canonical_plan, validate_plan, seed_plans
from huawei_code.gpu_score import backend_info, rank_load_vectors


def test_static_graph_and_plan_protocol():
    graph = load_graph(ROOT / "data/raw/A题/data/case_001.json")
    view = static_view(graph)
    for scene in ("A", "B"):
        plans = seed_plans(view, 2, scene)
        assert plans
        for plan in plans.values():
            validate_plan(view, plan, 2)


def test_canonical_order_is_preserved():
    plan = canonical_plan({10: 4, 20: 2, 30: 4}, [[4, 2], []])
    assert plan["core_schedules"][0] == [0, 1]


def test_gpu_or_cpu_rank_is_explicit():
    order, info = rank_load_vectors([[1, 4], [3, 2], [8, 8]])
    assert order == [1, 0, 2]
    assert info["backend"] in {"mps", "cpu", "unavailable"}
