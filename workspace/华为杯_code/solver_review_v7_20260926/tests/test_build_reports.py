import csv
import math

import pytest

from scripts.build_reports import build_cache_pairs, load_main_rows, validate_coverage


def test_aggregate_metrics_are_not_counted_twice(tmp_path):
    for path in (tmp_path / "metrics.csv", tmp_path / "batch_01" / "metrics.csv"):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["case", "cores", "scene", "candidate", "status"])
            writer.writeheader()
            writer.writerow({"case": "case_001", "cores": 1, "scene": "A", "candidate": "A0", "status": "AI_VERIFIED"})
    assert len(load_main_rows(tmp_path)) == 1


def test_incomplete_matrix_cannot_be_reported_as_complete():
    rows = [{"case": "case_001", "cores": 1, "scene": "A", "status": "AI_VERIFIED", "initial_candidate": "A0"}]
    with pytest.raises(ValueError, match="main matrix incomplete: 1/1500"):
        validate_coverage(rows, {"case_001": {}}, [])


def test_cache_pair_keeps_initial_hit_evidence_and_ratio_identity():
    rows = [
        {"case": "case_001", "cores": 2, "scene": "B", "status": "AI_VERIFIED", "final_plan_sha256": "xb", "final_makespan": 120},
        {"case": "case_001", "cores": 2, "scene": "C", "status": "AI_VERIFIED", "initial_plan_sha256": "xb", "final_plan_sha256": "xc", "initial_makespan": 100, "final_makespan": 80, "initial_cache_hit_bytes": 10, "initial_cache_miss_bytes": 90, "initial_cache_hit_rate": .1, "cache_hit_bytes": 40, "cache_miss_bytes": 60, "cache_hit_rate": .4},
    ]
    pair, = build_cache_pairs(rows)
    assert pair["c_starts_from_b"]
    assert (pair["c_initial_hit_bytes"], pair["c_initial_miss_bytes"], pair["c_initial_hit_rate"]) == (10, 90, .1)
    assert (pair["c_hit_bytes"], pair["c_miss_bytes"], pair["c_hit_rate"]) == (40, 60, .4)
    assert math.isclose(pair["s_hw"] * pair["s_adapt"], pair["s_opt"])
    assert math.isclose(pair["factor_identity_error"], 0, abs_tol=1e-12)
