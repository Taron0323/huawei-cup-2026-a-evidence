from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from huawei_code.candidates import generate_candidates, local_variants
from huawei_code.graph import load_graph, static_view
from huawei_code.official import load_modules, read_config
from huawei_code.plan import extend_plan_with_empty_cores, plan_key, seed_plans
from run_experiment import scene_call_limit, select_candidate


def inputs():
    view = static_view(load_graph(ROOT / "data/raw/A题/data/case_001.json"))
    modules = load_modules(ROOT / "vendor/official_evaluator")
    config = read_config(modules, ROOT / "data/raw/A题/data/config.txt")
    return view, config


def test_mandatory_order_survives_a_failed_first_evaluation():
    remaining = [
        {"candidate": "other", "source": "seed", "mandatory_rank": None, "light": {"score": (0,)}},
        {"candidate": "component", "source": "seed", "mandatory_rank": 1, "light": {"score": (1,)}},
        {"candidate": "lower_core", "source": "incumbent", "mandatory_rank": 2, "light": {"score": (2,)}},
    ]
    assert select_candidate(remaining, "A", None, [], 1)["candidate"] == "component"
    assert select_candidate(remaining[::2], "B", None, [], 2)["candidate"] == "lower_core"


def test_c_exploration_after_four_anchors_can_choose_cache_delay():
    remaining = [
        {"candidate": "timing", "source": "timing", "light": {"cache_expected_gain": 1, "cache_hit_bytes": 0, "light_time": 1}},
        {"candidate": "cache_delay", "source": "cache_delay", "light": {"cache_expected_gain": 2, "cache_hit_bytes": 10, "light_time": 2}},
    ]
    assert select_candidate(remaining, "C", None, [({"cache_stats": {}}, {})], 4)["candidate"] == "cache_delay"


def test_scene_limits_leave_one_exploration_after_all_distinct_anchors():
    assert [scene_call_limit(scene, 1) for scene in "ABC"] == [4, 4, 5]
    assert [scene_call_limit(scene, 99) for scene in "ABC"] == [4, 4, 5]


def test_a_b_mandatory_plans_cover_unique_anchors_and_deduplicate_identical_plans():
    view, config = inputs()
    for scene in "AB":
        lower = extend_plan_with_empty_cores(view, seed_plans(view, 1, scene)[f"{scene}3"], 2)
        candidates = generate_candidates(view, 2, scene, config, incumbent_plan=lower)
        mandatory = {plan_key(item["plan"]) for item in candidates if item["mandatory"]}
        seeds = seed_plans(view, 2, scene)
        assert {plan_key(seeds[f"{scene}{index}"]) for index in (0, 1)} | {plan_key(lower)} <= mandatory
        assert len({item["candidate"] for item in candidates}) == len(candidates)
        assert len({plan_key(item["plan"]) for item in candidates}) == len(candidates)

    identical = seed_plans(view, 1, "A")["A0"]
    candidates = generate_candidates(view, 1, "A", config, incumbent_plan=identical)
    assert sum(plan_key(item["plan"]) == plan_key(identical) for item in candidates) == 1
    assert next(item for item in candidates if plan_key(item["plan"]) == plan_key(identical))["mandatory_rank"] == 0


def test_c_mandatory_plans_cover_b_winner_c_seeds_and_previous_c_winner():
    view, config = inputs()
    b_winner = seed_plans(view, 2, "B")["B3"]
    lower_c = extend_plan_with_empty_cores(view, seed_plans(view, 1, "C")["C3"], 2)
    candidates = generate_candidates(view, 2, "C", config, base_plan=b_winner, incumbent_plan=lower_c)
    mandatory = {plan_key(item["plan"]): item["mandatory_rank"] for item in candidates if item["mandatory"]}
    c_seeds = seed_plans(view, 2, "C")
    assert mandatory[plan_key(b_winner)] == 0
    assert mandatory[plan_key(c_seeds["C0"])] == 1
    assert mandatory[plan_key(c_seeds["C1"])] == 2
    assert mandatory[plan_key(lower_c)] == 3
    assert len({item["candidate"] for item in candidates}) == len(candidates)
    assert len({plan_key(item["plan"]) for item in candidates}) == len(candidates)

    duplicate = generate_candidates(view, 2, "C", config, base_plan=b_winner, incumbent_plan=b_winner)
    same_plan = [item for item in duplicate if plan_key(item["plan"]) == plan_key(b_winner)]
    assert len(same_plan) == 1
    assert same_plan[0]["mandatory_rank"] == 0

    edited_plan = next(plan for name, plan, _source in local_variants(view, b_winner, 2, "C") if name != "base")
    promoted = generate_candidates(view, 2, "C", config, base_plan=b_winner, incumbent_plan=edited_plan)
    promoted_item = next(item for item in promoted if plan_key(item["plan"]) == plan_key(edited_plan))
    assert promoted_item["mandatory_rank"] == 3
    assert "lower_core" in promoted_item["anchor_roles"]
    assert sum(plan_key(item["plan"]) == plan_key(edited_plan) for item in promoted) == 1
