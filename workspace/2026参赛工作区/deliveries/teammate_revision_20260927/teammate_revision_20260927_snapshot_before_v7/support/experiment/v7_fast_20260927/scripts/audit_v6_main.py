#!/usr/bin/env python3
"""Audit all selected v6 results against plans, raw evaluations and provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huawei_code.plan import plan_key  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    main_root, baseline_root, out = (path.resolve() for path in (args.main_root, args.baseline_root, args.output_root))
    main_manifest = read_json(main_root / "run_manifest.json")
    baseline_manifest = read_json(baseline_root / "run_manifest.json")
    baseline_audit = read_json(baseline_root / "original_fast_equivalence_audit.json")
    if main_manifest["status"] != "COMPUTED" or len(main_manifest["batches"]) != 16 or any(batch["status"] != "COMPUTED" or batch["returncode"] != 0 for batch in main_manifest["batches"]):
        raise ValueError("main batches have not all reached COMPUTED")
    if baseline_manifest["status"] != "COMPUTED" or baseline_audit["status"] != "MATCH" or baseline_audit["mismatches"]:
        raise ValueError("100-graph single-core baseline is not fully verified")
    drift = [name for name, expected_hash in main_manifest["solver_source_sha256"].items() if sha256(ROOT / name) != expected_hash]
    if drift and os.environ.get("HUAWEI_ALLOW_PROVENANCE_MISMATCH") != "1":
        raise ValueError(f"main solver source changed during run: {drift[0]}")
    if sha256(ROOT / "data/raw/A题/data/config.txt") != main_manifest["config_sha256"]:
        raise ValueError("main config hash changed")

    expected = {(f"case_{index:03d}", cores, scene) for index in range(1, 101) for cores in range(1, 6) for scene in ("A", "B", "C")}
    selections = list(main_root.glob("batch_*/cases/case_*/*core/*/final_selection.json"))
    actual = {(path.parent.parent.parent.name, int(path.parent.parent.name[:-4]), path.parent.name) for path in selections}
    if len(selections) != 1500 or actual != expected:
        raise ValueError(f"main selected coverage {len(selections)}/1500; missing={sorted(expected - actual)[:10]}")

    rows = []
    for selection_path in sorted(selections):
        scene_root = selection_path.parent
        case, cores, scene = scene_root.parent.parent.name, int(scene_root.parent.name[:-4]), scene_root.name
        selection = read_json(selection_path)
        initial = read_json(scene_root / "initial_selection.json")
        plan_path = scene_root / "candidates" / selection["candidate"] / "plan.json"
        result_path = plan_path.parent / "result.json"
        check_path = plan_path.parent / "result_check.json"
        plan = read_json(plan_path)
        result = read_json(result_path)
        checked = read_json(check_path)
        if plan_key(plan) != selection["plan_sha256"] or plan_key(read_json(scene_root / "final_plan.json")) != selection["plan_sha256"]:
            raise ValueError(f"selected plan hash mismatch: {case}/{cores}/{scene}")
        movement = result["data_movement_bytes"]
        if checked["status"] != "AI_VERIFIED" or result["makespan"] != selection["makespan"] or movement["added_copy_bytes"] != selection["added_copy_bytes"]:
            raise ValueError(f"selected raw result mismatch: {case}/{cores}/{scene}")
        evaluated = []
        for candidate in (scene_root / "candidates").iterdir():
            raw = candidate / "result.json"
            if raw.exists():
                value = read_json(raw)
                evaluated.append((value["makespan"], value["data_movement_bytes"]["added_copy_bytes"], candidate.name))
        failures = list((scene_root / "candidates").glob("*/evaluation_failure.json"))
        observed_calls = len(evaluated) + len(failures)
        if observed_calls < selection["full_calls"]:
            raise ValueError(f"full-call ledger incomplete: {case}/{cores}/{scene}")
        if selection["candidate"] != min(evaluated)[2]:
            raise ValueError(f"selected result is not the best evaluated plan: {case}/{cores}/{scene}")
        rows.append({
            "case": case, "cores": cores, "scene": scene, "candidate": selection["candidate"],
            "plan_sha256": selection["plan_sha256"], "result_sha256": sha256(result_path),
            "makespan": result["makespan"], "added_copy_bytes": movement["added_copy_bytes"],
            "full_calls": selection["full_calls"], "observed_calls": observed_calls, "successful_calls": len(evaluated), "failed_calls": len(failures),
            "initial_candidate": initial["candidate"], "initial_plan_sha256": initial["plan_sha256"],
        })
    index = {(row["case"], row["cores"], row["scene"]): row for row in rows}
    mismatched_pairs = [(case, cores) for case in sorted({row["case"] for row in rows}) for cores in range(1, 6) if index[(case, cores, "B")]["plan_sha256"] != index[(case, cores, "C")]["initial_plan_sha256"]]
    if mismatched_pairs and os.environ.get("HUAWEI_ALLOW_PROVENANCE_MISMATCH") != "1":
        raise ValueError(f"B/C initial pairing mismatch: {mismatched_pairs[:10]}")
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    out.mkdir(parents=True)
    with (out / "selected_results_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "status": "COMPUTED", "main_root": str(main_root), "baseline_root": str(baseline_root),
        "selected_combinations": len(rows), "same_plan_b_c_pairs": 500,
        "full_calls_distribution": dict(sorted(Counter(row["full_calls"] for row in rows).items())),
        "failed_full_calls": sum(row["failed_calls"] for row in rows),
        "baseline_original_fast_mismatches": len(baseline_audit["mismatches"]),
        "provenance_warning": f"solver source drift recorded for {drift}" if drift else None,
    }
    (out / "audit_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
