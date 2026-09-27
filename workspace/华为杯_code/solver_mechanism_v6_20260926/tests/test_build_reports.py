import csv

import pytest

from scripts.build_reports import load_main_rows, validate_coverage


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
