#!/usr/bin/env python3
"""Prepare v7 main-matrix inputs for the inherited-evidence materializer.

This adapter creates a new, self-contained staging directory from the
2026-09-27 v7 report and its official baseline run.  It does not modify any
historical report, source run, or the existing inherited_20260927 directory.
The actual plan materialization is delegated to the existing
``materialize_inherited_evidence.py`` implementation through a separately
copied v7-tagged script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


PAPER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = Path(
    "/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/"
    "v7_fast_reports_complete_20260927"
)
DEFAULT_MAIN_ROOT = Path(
    "/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/"
    "v7_fast_equiv_20260927_0030"
)
DEFAULT_BASELINE_ROOT = Path(
    "/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/"
    "v7_fast_baseline_equiv_20260927_0030"
)
DEFAULT_STAGE = PAPER_ROOT / "data/v7_input_20260927"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def find_batch(main_root: Path, row: dict[str, str]) -> Path:
    batch = str(row.get("batch", ""))
    name = batch.split(":", 1)[-1]
    path = main_root / name
    if not path.is_dir():
        raise FileNotFoundError(f"batch directory not found for {batch}: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--main-root", type=Path, default=DEFAULT_MAIN_ROOT)
    parser.add_argument("--baseline-root", type=Path, default=DEFAULT_BASELINE_ROOT)
    parser.add_argument("--stage", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = args.report.expanduser().resolve()
    main_root = args.main_root.expanduser().resolve()
    baseline_root = args.baseline_root.expanduser().resolve()
    stage = args.stage.expanduser().resolve()
    for required in (report / "main_results.csv", report / "candidate_effects.csv",
                     report / "cache_pairs.csv", report / "timing.csv",
                     main_root, baseline_root / "metrics.csv"):
        if not required.exists():
            raise FileNotFoundError(required)
    if stage.exists():
        if not args.force:
            raise SystemExit(f"staging directory exists; pass --force to replace: {stage}")
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    main_rows = read_csv(report / "main_results.csv")
    if len(main_rows) != 1500:
        raise ValueError(f"expected 1500 v7 main rows, got {len(main_rows)}")
    keys = {(r["case"], int(r["cores"]), r["scene"]) for r in main_rows}
    expected = {(f"case_{i:03d}", k, s) for i in range(1, 101)
                for k in range(1, 6) for s in "ABC"}
    if keys != expected:
        raise ValueError(f"v7 matrix coverage mismatch: {len(keys)}/{len(expected)}")
    if any(r.get("status") != "AI_VERIFIED" for r in main_rows):
        raise ValueError("v7 main matrix contains non-AI_VERIFIED rows")

    source_rows: list[dict[str, object]] = []
    for row in main_rows:
        batch = find_batch(main_root, row)
        scene_root = batch / "cases" / row["case"] / f"{int(row['cores'])}core" / row["scene"]
        plan_path = scene_root / "final_plan.json"
        selection_path = scene_root / "final_selection.json"
        result_path = scene_root / "candidates" / str(row["final_candidate"]) / "result.json"
        for required in (plan_path, selection_path, result_path):
            if not required.exists():
                raise FileNotFoundError(required)
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        if selection.get("candidate") != row["final_candidate"]:
            raise ValueError(f"candidate mismatch: {row['case']}/{row['cores']}/{row['scene']}")
        if int(selection.get("makespan")) != int(float(row["final_makespan"])):
            raise ValueError(f"makespan mismatch: {row['case']}/{row['cores']}/{row['scene']}")
        source_rows.append({
            "case": row["case"], "cores": row["cores"], "scene": row["scene"],
            "final_plan_path": str(plan_path), "final_result_path": str(result_path),
            "final_plan_sha256_recorded": selection.get("plan_sha256", ""),
            "final_plan_sha256_file": sha256(plan_path),
            "final_result_sha256": sha256(result_path),
            "source_root": str(main_root),
        })

    baseline_rows: list[dict[str, object]] = []
    baseline = read_csv(baseline_root / "metrics.csv")
    if len(baseline) != 100:
        raise ValueError(f"expected 100 v7 baseline rows, got {len(baseline)}")
    baseline_lookup = {r["case"]: r for r in baseline}
    main_baselines = {r["case"]: int(float(r["baseline_makespan"])) for r in main_rows}
    for case, row in sorted(baseline_lookup.items()):
        if row.get("status") != "AI_VERIFIED":
            raise ValueError(f"baseline row not verified: {case}")
        if int(float(row["makespan"])) != main_baselines[case]:
            raise ValueError(f"baseline mismatch: {case}")
        result_path = main_root / str(next(r for r in main_rows if r["case"] == case and int(r["cores"]) == 1 and r["scene"] == "A")["batch"]).split(":", 1)[-1] / "cases" / case / "1core" / "A" / "candidates" / "A0_base" / "result.json"
        if not result_path.exists():
            raise FileNotFoundError(result_path)
        baseline_rows.append({**row, "result_path": str(result_path), "source_root": str(baseline_root)})

    shutil.copy2(report / "main_results.csv", stage / "main_results.csv")
    write_csv(stage / "result_sources.csv", source_rows)
    write_csv(stage / "singlecore_baseline.csv", baseline_rows)
    manifest = {
        "manifest_name": "V7_INHERITED_INPUT_MANIFEST",
        "status": "COMPUTED",
        "source_report": str(report), "source_main_root": str(main_root),
        "source_baseline_root": str(baseline_root),
        "main_results_sha256": sha256(report / "main_results.csv"),
        "main_rows": len(main_rows), "result_sources": len(source_rows),
        "baseline_rows": len(baseline_rows),
        "selection_input": "v7 final evaluated plan per (case, cores, scene); inherited materializer chooses shortest evaluated plan among 1..K plus the full-graph single-core baseline",
    }
    (stage / "V7_INPUT_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPUTED", "stage": str(stage), "rows": len(main_rows), "sources": len(source_rows), "baselines": len(baseline_rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
