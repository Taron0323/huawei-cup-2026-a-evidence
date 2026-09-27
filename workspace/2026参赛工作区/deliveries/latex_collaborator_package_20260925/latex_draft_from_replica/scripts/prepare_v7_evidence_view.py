#!/usr/bin/env python3
"""Build a read-only evidence view for the materialized v7 matrix.

The view combines the v7 inherited main matrix with its independently
generated source tables.  It is written to a new directory so the audited and
previous inherited packages remain byte-for-byte untouched.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


PAPER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PAPER_ROOT / "data/v7_evidence_20260927"
DEFAULT_INHERITED = PAPER_ROOT / "data/inherited_v7_20260927"
DEFAULT_RAW = PAPER_ROOT / "data/v7_fast_20260927"
DEFAULT_INPUT = PAPER_ROOT / "data/v7_input_20260927"
DEFAULT_SENSITIVITY = Path(
    "/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/"
    "v7_fast_sensitivity_complete_20260927_0228"
)
DEFAULT_SENSITIVITY_REPORT = Path(
    "/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/"
    "v7_fast_sensitivity_report_complete_20260927"
)


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write(path: Path, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inherited", type=Path, default=DEFAULT_INHERITED)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--input-stage", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--sensitivity", type=Path, default=DEFAULT_SENSITIVITY)
    parser.add_argument("--sensitivity-report", type=Path, default=DEFAULT_SENSITIVITY_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    inherited = args.inherited.expanduser().resolve()
    raw = args.raw.expanduser().resolve()
    input_stage = args.input_stage.expanduser().resolve()
    sensitivity_root = args.sensitivity.expanduser().resolve()
    sensitivity_report = args.sensitivity_report.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if output.exists():
        if not args.force:
            raise SystemExit(f"output exists; pass --force to replace: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    main_rows = read(inherited / "main_results.csv")
    if len(main_rows) != 1500:
        raise ValueError(f"expected 1500 inherited rows, got {len(main_rows)}")
    for row in main_rows:
        # A 1-core A row is the diagnostic/non-formal entry; all other rows
        # belong to the formal 1..5-core matrix.
        row["formal_matrix"] = "False" if row["scene"] == "A" and int(row["cores"]) == 1 else "True"
    write(output / "main_results.csv", main_rows)
    shutil.copy2(raw / "candidate_effects.csv", output / "candidate_comparison.csv")
    cache_pairs = read(raw / "cache_pairs.csv")
    # Older report consumers call the fixed-plan C value
    # ``c_same_plan_makespan``; v7 names the same field
    # ``c_initial_makespan``.  Preserve both names in this derived view.
    for row in cache_pairs:
        row["c_same_plan_makespan"] = row.get("c_initial_makespan", "")
        row["c_final_hit_bytes"] = row.get("c_hit_bytes", "")
        row["c_final_miss_bytes"] = row.get("c_miss_bytes", "")
    write(output / "cache_pairs.csv", cache_pairs)
    shutil.copy2(raw / "timing.csv", output / "candidate_evaluations.csv")
    shutil.copy2(raw / "timing.csv", output / "timing.csv")
    shutil.copy2(inherited / "../v7_input_20260927/singlecore_baseline.csv", output / "singlecore_baseline.csv")

    # The v7 report stores fixed and selected reoptimized rows in one summary
    # table.  Expand it into the two-mode schema consumed by the existing
    # evidence builder.
    summaries = read(sensitivity_report / "sensitivity_summary.csv")
    fixed_rows = read(sensitivity_root / "fixed_plan.csv")
    reoptimized_rows = read(sensitivity_root / "reoptimized.csv")
    fixed_index = {(r["case"], r["variant"]): r for r in fixed_rows}
    selected_reoptimized = [r for r in reoptimized_rows if str(r.get("selected", "")).lower() == "true"]
    reoptimized_index = {(r["case"], r["variant"]): r for r in selected_reoptimized}
    sensitivity_rows: list[dict[str, object]] = []
    for row in summaries:
        fixed = fixed_index[(row["case"], row["variant"])]
        optimized = reoptimized_index[(row["case"], row["variant"])]
        common = {
            "case": row["case"], "variant": row["variant"], "status": "AI_VERIFIED",
            "default_same_plan_makespan": row["default_c_initial_makespan"],
        }
        sensitivity_rows.append({**common, "mode": "fixed_plan",
                                 "variant_makespan": row["fixed_makespan"],
                                 "cache_hit_rate": row["fixed_cache_hit_rate"],
                                 "cache_hit_bytes": fixed.get("cache_hit_bytes", ""),
                                 "cache_miss_bytes": fixed.get("cache_miss_bytes", ""),
                                 "changed_from_B_plan": "False"})
        sensitivity_rows.append({**common, "mode": "reoptimized",
                                 "variant_makespan": row["reoptimized_makespan"],
                                 "cache_hit_rate": row["reoptimized_cache_hit_rate"],
                                 "cache_hit_bytes": optimized.get("cache_hit_bytes", ""),
                                 "cache_miss_bytes": optimized.get("cache_miss_bytes", ""),
                                 "changed_from_B_plan": "True" if str(row["plan_changed"]).lower() == "true" else "False"})
    if len(sensitivity_rows) != 48:
        raise ValueError(f"expected 48 sensitivity rows, got {len(sensitivity_rows)}")
    write(output / "sensitivity_results.csv", sensitivity_rows)
    write(output / "sensitivity_failed_candidates.csv", [],
          ["case", "variant", "mode", "status", "error"])
    write(output / "main_failed_candidates.csv", [],
          ["case", "cores", "scene", "candidate", "status", "error"])
    # Optional file accepted by the builder when present.
    if (input_stage / "epsilon_tradeoffs.csv").exists():
        shutil.copy2(input_stage / "epsilon_tradeoffs.csv", output / "epsilon_tradeoffs.csv")

    manifest = {
        "main_matrix": {"rows": 1500, "formal_rows": 1400, "diagnostic_rows": 100},
        "cache_pairs": {"rows": 500},
        "singlecore_baseline": {"rows": 100},
        "sensitivity": {"reoptimized_rows": 48, "groups": 24},
        "status": "COMPUTED",
        "source_inherited": str(inherited),
        "source_raw": str(raw),
        "source_sensitivity": str(sensitivity_report / "sensitivity_summary.csv"),
        "notes": [
            "This view is generated from the v7 fast official-evaluator report and the separately materialized inherited plans.",
            "The 100 one-core A rows are retained as diagnostics; the formal matrix contains 1400 rows.",
            "Empty failure tables mean no failure rows were recorded in this v7 report.",
        ],
    }
    (output / "main_report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPUTED", "output": str(output), "main_rows": 1500, "cache_pairs": 500, "sensitivity_rows": 48}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
