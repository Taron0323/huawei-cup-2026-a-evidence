#!/usr/bin/env python3
"""Merge completed tail-rescue combinations into a paused v7 main matrix."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import time


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_rows(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and {"case", "cores", "scene", "status"} <= set(value):
            rows.append(value)
    return rows


def key(row: dict) -> tuple[str, int, str]:
    return str(row["case"]), int(row["cores"]), str(row["scene"])


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({field for row in rows for field in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--rescue-root", type=Path, required=True)
    args = parser.parse_args()
    main_root = args.main_root.resolve()
    rescue_root = args.rescue_root.resolve()
    main_manifest = read_json(main_root / "run_manifest.json")
    rescue_manifest = read_json(rescue_root / "run_manifest.json")

    case_to_batch = {}
    jobs = []
    for job in main_manifest["jobs"]:
        copied = dict(job)
        copied["cases"] = list(job["cases"])
        jobs.append(copied)
        for case in job["cases"]:
            case_to_batch[case] = (Path(job["output_root"]), job["batch"])

    rescue_cases = [case for job in rescue_manifest["jobs"] for case in job["cases"]]
    merged_cases = []
    copied_combinations = []
    for rescue_job in rescue_manifest["jobs"]:
        rescue_batch = Path(rescue_job["output_root"])
        for case in rescue_job["cases"]:
            source_case = rescue_batch / "cases" / case
            if case not in case_to_batch or not source_case.exists():
                continue
            target_batch, _batch_id = case_to_batch[case]
            target_case = target_batch / "cases" / case
            merged_cases.append(case)
            for source_core in sorted(source_case.glob("*core")):
                for source_scene in sorted(source_core.iterdir()):
                    if not source_scene.is_dir():
                        continue
                    source_selection = source_scene / "final_selection.json"
                    if not source_selection.exists():
                        continue
                    target_scene = target_case / source_core.name / source_scene.name
                    if (target_scene / "final_selection.json").exists():
                        continue
                    target_scene.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source_scene, target_scene, dirs_exist_ok=True)
                    copied_combinations.append({"case": case, "cores": int(source_core.name[:-4]), "scene": source_scene.name})

    rescue_rows_by_key = {}
    standard_rows_by_batch = {}
    rescue_rows_by_batch = {}
    for job in jobs:
        batch_root = Path(job["output_root"])
        rows = []
        rows.extend(read_rows(batch_root / "metrics.csv"))
        rows.extend(read_rows(main_root / f"batch_{int(job['batch']):02d}.console.log"))
        standard_rows_by_batch[int(job["batch"])] = {key(row): row for row in rows if {"case", "cores", "scene"} <= set(row)}
    for rescue_job in rescue_manifest["jobs"]:
        rescue_batch_id = int(rescue_job["batch"])
        rescue_batch = Path(rescue_job["output_root"])
        rows = []
        rows.extend(read_rows(rescue_batch / "metrics.csv"))
        rows.extend(read_rows(rescue_root / f"batch_{rescue_batch_id:02d}.console.log"))
        for row in rows:
            rescue_rows_by_key[key(row)] = row

    for job in jobs:
        batch_id = int(job["batch"])
        rows_by_key = dict(standard_rows_by_batch.get(batch_id, {}))
        batch_root = Path(job["output_root"])
        for case in job["cases"]:
            case_root = batch_root / "cases" / case
            for combo in case_root.glob("*core/*"):
                if combo.is_dir() and (combo / "final_selection.json").exists():
                    combo_key = (case, int(combo.parent.name[:-4]), combo.name)
                    if combo_key not in rows_by_key and combo_key in rescue_rows_by_key:
                        rows_by_key[combo_key] = rescue_rows_by_key[combo_key]
        rows = sorted(rows_by_key.values(), key=lambda row: key(row))
        write_csv(batch_root / "metrics.csv", rows)
        status_counts = {}
        for row in rows:
            status = str(row.get("status", ""))
            status_counts[status] = status_counts.get(status, 0) + 1
        child_path = batch_root / "run_manifest.json"
        child = read_json(child_path) if child_path.exists() else {"run_id": batch_root.name}
        child.update({
            "status": "COMPUTED" if len(rows) == len(job["cases"]) * 15 and not status_counts.get("EVALUATION_FAILED") else "PARTIAL",
            "rows": len(rows),
            "status_counts": status_counts,
            "tail_fast_rescue": True,
            "tail_fast_rescue_cases": [case for case in job["cases"] if case in rescue_cases],
            "ended_at": time.time(),
        })
        write_json(child_path, child)
        job["status"] = child["status"]
        job["returncode"] = 0 if child["status"] == "COMPUTED" else 1
        job["rows"] = len(rows)
        job["status_counts"] = status_counts

    from scripts.run_full_matrix import aggregate

    merged = aggregate(main_root, jobs, int(main_manifest["full_candidates"]))
    merged["tail_fast_rescue"] = {
        "enabled": True,
        "rescue_root": str(rescue_root),
        "fast_profile": True,
        "cases": sorted(set(merged_cases)),
        "copied_combinations": copied_combinations,
        "copied_count": len(copied_combinations),
        "note": "Only combinations missing from the paused standard matrix were filled from the independently recorded fast-profile rescue run; existing standard results were retained.",
    }
    write_json(main_root / "run_manifest.json", merged)
    print(json.dumps({"status": merged["status"], "rows": merged["rows"], "copied": len(copied_combinations)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
