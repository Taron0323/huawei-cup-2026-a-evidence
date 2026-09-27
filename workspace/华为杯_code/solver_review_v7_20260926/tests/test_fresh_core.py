import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huawei_code.graph import load_graph, static_view
from huawei_code.plan import canonical_plan, extend_plan_with_empty_cores, legacy_seed_plans, plan_key, validate_plan, seed_plans
from huawei_code.candidates import _move_group_position, cache_delay_variants, capacity_variants, disperse_variants, event_timing_variants, generate_candidates, search_representatives
from huawei_code.official import load_modules, profile, read_config
from huawei_code.gpu_score import backend_info, rank_load_vectors
from huawei_code.scoring import light_score
sys.path.insert(0, str(ROOT / "scripts"))
from run_experiment import scene_call_limit
from run_full_matrix import file_sha, solver_source_sha256


def test_full_matrix_manifest_hashes_every_solver_source():
    actual = solver_source_sha256()
    expected_paths = [ROOT / "scripts/run_experiment.py", ROOT / "scripts/run_full_matrix.py"]
    expected_paths.extend((ROOT / "src").rglob("*.py"))
    expected = {str(path.relative_to(ROOT)): file_sha(path) for path in expected_paths}
    assert actual == expected


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


def test_plan_key_survives_json_roundtrip():
    plan = canonical_plan({2: 8, 10: 3, 11: 3}, [[8], [3]])
    assert plan_key(plan) == plan_key(json.loads(json.dumps(plan)))


def test_idea_and_legacy_seed_portfolios_are_legal():
    view = static_view(load_graph(ROOT / "data/raw/A题/data/case_001.json"))
    config = read_config(load_modules(ROOT / "vendor/official_evaluator"), ROOT / "data/raw/A题/data/config.txt")
    for scene in ("A", "B", "C"):
        starts = seed_plans(view, 2, scene, config)
        assert len(starts) == 4
        for plan in starts.values():
            validate_plan(view, plan, 2)
    assert len(set(legacy_seed_plans(view, 2, "B"))) == 4


def test_local_search_representatives_remain_legal():
    view = static_view(load_graph(ROOT / "data/raw/A题/data/case_001.json"))
    config = read_config(load_modules(ROOT / "vendor/official_evaluator"), ROOT / "data/raw/A题/data/config.txt")
    plan = seed_plans(view, 2, "B", config)["B1"]
    initial = {"plan": plan, "light": light_score(view, plan, "B", config)}
    ordinary, capacity, scored = search_representatives(view, initial, 2, "B", config)
    assert scored
    for item in (ordinary, capacity):
        if item is not None:
            validate_plan(view, item["plan"], 2)


def test_profile_rejects_cross_core_execution_cycle():
    graph = load_graph(ROOT / "data/raw/A题/data/case_051.json")
    view = static_view(graph)
    modules = load_modules(ROOT / "vendor/official_evaluator")
    config = read_config(modules, ROOT / "data/raw/A题/data/config.txt")
    start = legacy_seed_plans(view, 5, "B")["L3"]
    initial = {"plan": start, "light": light_score(view, start, "B", config)}
    _ordinary, _capacity, scored = search_representatives(view, initial, 5, "B", config)
    plan = next(item["plan"] for item in scored if item["candidate"] == "r1_boundary_n367_c2_p4")
    with pytest.raises(modules["validation"].EvaluationValidationError):
        profile(graph, plan, "B", config, modules)


def test_lower_core_plan_can_be_embedded_with_idle_core():
    graph = load_graph(ROOT / "data/raw/A题/data/case_001.json")
    view = static_view(graph)
    one_core = seed_plans(view, 1, "A")["A0"]
    embedded = extend_plan_with_empty_cores(view, one_core, 2)
    assert len(embedded["core_schedules"]) == 2
    assert embedded["core_schedules"][1] == []
    validate_plan(view, embedded, 2)


def test_mandatory_anchors_survive_candidate_deduplication():
    view = static_view(load_graph(ROOT / "data/raw/A题/data/case_001.json"))
    config = read_config(load_modules(ROOT / "vendor/official_evaluator"), ROOT / "data/raw/A题/data/config.txt")
    prior_b = extend_plan_with_empty_cores(view, seed_plans(view, 1, "B", config)["B2"], 2)
    b_items = generate_candidates(view, 2, "B", config, incumbent_plan=prior_b)
    b_anchors = {role: item for item in b_items for role in item["anchor_roles"]}
    assert set(b_anchors) == {"whole_graph", "component_pack", "lower_core"}
    assert len({plan_key(item["plan"]) for item in b_items}) == len(b_items)
    assert scene_call_limit("B", 2, sum(item["mandatory"] for item in b_items)) > sum(item["mandatory"] for item in b_items)

    prior_c = extend_plan_with_empty_cores(view, seed_plans(view, 1, "C", config)["C2"], 2)
    c_items = generate_candidates(view, 2, "C", config, incumbent_plan=b_anchors["component_pack"]["plan"], lower_core_plan=prior_c)
    c_anchors = {role: item for item in c_items for role in item["anchor_roles"]}
    assert set(c_anchors) == {"b_incumbent", "whole_graph", "component_pack", "lower_core"}
    assert len({plan_key(item["plan"]) for item in c_items}) == len(c_items)
    assert scene_call_limit("C", 2, sum(item["mandatory"] for item in c_items)) > sum(item["mandatory"] for item in c_items)


def test_basic_legality_is_checked_for_b_and_c():
    graph = load_graph(ROOT / "data/raw/A题/data/case_001.json")
    view = static_view(graph)
    modules = load_modules(ROOT / "vendor/official_evaluator")
    config = read_config(modules, ROOT / "data/raw/A题/data/config.txt")
    for scene in ("B", "C"):
        plan = seed_plans(view, 2, scene, config)[f"{scene}1"]
        validate_plan(view, plan, 2)
        modules[scene.lower()].derive_multicore_plan(graph, plan)

    chain = {
        "nodes": [1, 2, 3],
        "preds": {"1": [], "2": [1], "3": [2]},
        "succs": {"1": [2], "2": [3], "3": []},
    }
    with pytest.raises(ValueError, match="cyclic"):
        validate_plan(chain, canonical_plan({1: 0, 2: 1, 3: 0}, [[0], [1]]), 2)
    with pytest.raises(ValueError, match="same-core"):
        validate_plan(chain, canonical_plan({1: 0, 2: 1, 3: 2}, [[1, 0, 2], []]), 2)


def test_group_position_variant_is_reachable_and_legal():
    graph = load_graph(ROOT / "data/raw/A题/data/case_001.json")
    view = static_view(graph)
    base = seed_plans(view, 2, "C")["C3"]
    moved = next(
        (
            candidate
            for sequence in base["core_schedules"]
            if len(sequence) >= 2
            for group in sequence
            for position in range(len(sequence) + 1)
            if (candidate := _move_group_position(view, base, group, position)) is not None
            and plan_key(candidate) != plan_key(base)
        ),
        None,
    )
    assert moved is not None
    validate_plan(view, moved, 2)


def test_disperse_handles_serialized_plan_keys():
    graph = load_graph(ROOT / "data/raw/A题/data/case_001.json")
    view = static_view(graph)
    modules = load_modules(ROOT / "vendor/official_evaluator")
    config = read_config(modules, ROOT / "data/raw/A题/data/config.txt")
    base = json.loads(json.dumps(seed_plans(view, 2, "B")["B3"]))
    variants = disperse_variants(view, base, 2, config)
    assert variants
    validate_plan(view, variants[0][1], 2)


def test_cache_delay_reaches_a_busy_core_timing_state():
    graph = load_graph(ROOT / "data/raw/A题/data/case_001.json")
    view = static_view(graph)
    modules = load_modules(ROOT / "vendor/official_evaluator")
    config = read_config(modules, ROOT / "data/raw/A题/data/config.txt")
    base = seed_plans(view, 2, "B")["B3"]
    variants = cache_delay_variants(view, base, 2, config)
    assert variants
    assert all(source == "cache_delay" for _name, _plan, source in variants)
    assert any(light_score(view, plan, "C", config)["cache_hit_bytes"] > 0 for _name, plan, _source in variants)
    for _name, plan, _source in variants:
        validate_plan(view, plan, 2)


def test_capacity_variants_have_explicit_source_and_are_legal():
    graph = load_graph(ROOT / "data/raw/A题/data/case_001.json")
    view = static_view(graph)
    modules = load_modules(ROOT / "vendor/official_evaluator")
    config = read_config(modules, ROOT / "data/raw/A题/data/config.txt")
    base = seed_plans(view, 2, "B")["B3"]
    variants = capacity_variants(view, base, 2, config)
    assert variants
    assert all(source == "capacity" for _name, _plan, source in variants)
    for _name, plan, _source in variants:
        validate_plan(view, plan, 2)


def test_profile_records_copy_in_logical_tensor_mapping():
    graph = load_graph(ROOT / "data/raw/A题/data/case_001.json")
    view = static_view(graph)
    modules = load_modules(ROOT / "vendor/official_evaluator")
    config = read_config(modules, ROOT / "data/raw/A题/data/config.txt")
    plan = seed_plans(view, 2, "C")["C3"]
    result = profile(graph, plan, "C", config, modules)
    assert result["copy_in_logical_tids"]
    assert all(":" in key and isinstance(value, int)
               for key, value in result["copy_in_logical_tids"].items())


def test_event_timing_accepts_physical_event_with_logical_alias():
    view = {
        "ops": {"1": {"cycles": 100}, "2": {"cycles": 100}, "3": {"cycles": 100}},
        "nodes": [1, 2, 3],
        "preds": {"1": [], "2": [], "3": []},
        "succs": {"1": [], "2": [], "3": []},
        "topological": [1, 2, 3],
        "tensor_sizes": {"7": 60000},
        "tensor_consumers": {"7": [1, 2, 3]},
        "tensor_producers": {},
        "output_tensors": [],
        "node_to_subgraph": {1: 0, 2: 1, 3: 2},
        "core_schedules": [[0], [1], [2]],
    }
    base = {"node_to_subgraph": view["node_to_subgraph"], "core_schedules": view["core_schedules"]}
    config = {"cache": {"capacity": 1_048_576, "bandwidth": 250}}
    events = [
        {"event": "miss", "tensor_id": 1000000007, "logical_tensor_id": 7, "size_bytes": 60000, "time": 0},
        {"event": "miss", "tensor_id": 1000000007, "logical_tensor_id": 7, "size_bytes": 60000, "time": 1000},
    ]
    variants = event_timing_variants(view, base, 3, events, config)
    assert variants
    assert all(source == "event_timing" for _name, _plan, source in variants)
    for _name, plan, _source in variants:
        validate_plan(view, plan, 3)


def test_gpu_or_cpu_rank_is_explicit():
    order, info = rank_load_vectors([[1, 4], [3, 2], [8, 8]])
    assert order == [1, 0, 2]
    assert info["backend"] in {"mps", "cpu", "unavailable"}
