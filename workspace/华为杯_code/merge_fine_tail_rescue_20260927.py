#!/usr/bin/env python3
"""Merge fine-grained fast-evaluator jobs into the paused v7 main matrix."""

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


def rows_from(path: Path) -> list[dict]:
    if not path.exists():
        return []
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and {"case", "cores", "scene", "status"} <= set(value):
            rows.append(value)
    return rows


def row_key(row: dict) -> tuple[str, int, str]:
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
    parser.add_argument("--fine-root", type=Path, required=True)
    args = parser.parse_args()
    main_root = args.main_root.resolve()
    fine_root = args.fine_root.resolve()
    main_manifest = read_json(main_root / "run_manifest.json")
    fine_manifest = read_json(fine_root / "rescue_manifest.json")

    case_map = {}
    jobs = []
    main_jobs = main_manifest.get("jobs") or main_manifest.get("batches") or []
    for job in main_jobs:
        copied = dict(job)
        copied["cases"] = list(job["cases"])
        jobs.append(copied)
        for case in job["cases"]:
            case_map[case] = (Path(job["output_root"]), int(job["batch"]))

    copied = []
    copied_keys: set[tuple[str, int, str]] = set()
    fine_rows_by_batch: dict[int, dict[tuple[str, int, str], dict]] = {}
    fine_jobs = fine_manifest.get("jobs", [])
    for fine_job in fine_jobs:
        source_root = Path(fine_job["output_root"])
        case = str(fine_job["case"])
        cores = int(fine_job["cores"])
        source_core = source_root / "cases" / case / f"{cores}core"
        if case not in case_map:
            continue
        target_batch, batch_id = case_map[case]
        row_map = fine_rows_by_batch.setdefault(batch_id, {})
        for scene in ("A", "B", "C"):
            source_scene = source_core / scene
            if not (source_scene / "final_selection.json").exists():
                continue
            target_scene = target_batch / "cases" / case / f"{cores}core" / scene
            if not (target_scene / "final_selection.json").exists():
                target_scene.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_scene, target_scene, dirs_exist_ok=True)
                item = {"case": case, "cores": cores, "scene": scene, "source": str(source_scene)}
                copied.append(item)
                copied_keys.add((case, cores, scene))
        log_path = fine_root / (source_root.name + ".log")
        for row in rows_from(source_root / "metrics.csv") + rows_from(log_path):
            if {"case", "cores", "scene"} <= set(row):
                row_map[row_key(row)] = row

    standard_by_batch: dict[int, dict[tuple[str, int, str], dict]] = {}
    for job in jobs:
        batch_id = int(job["batch"])
        batch_root = Path(job["output_root"])
        standard = rows_from(batch_root / "metrics.csv") + rows_from(main_root / f"batch_{batch_id:02d}.console.log")
        row_map = {}
        for row in standard:
            if {"case", "cores", "scene"} <= set(row):
                combo = row_key(row)
                case, cores, scene = combo
                if (batch_root / "cases" / case / f"{cores}core" / scene / "final_selection.json").exists():
                    row_map[combo] = row
        standard_by_batch[batch_id] = row_map

    for job in jobs:
        batch_id = int(job["batch"])
        batch_root = Path(job["output_root"])
        rows_by_key = dict(standard_by_batch.get(batch_id, {}))
        for combo, row in fine_rows_by_batch.get(batch_id, {}).items():
            if combo in copied_keys or combo not in rows_by_key:
                rows_by_key[combo] = row
        rows = sorted(rows_by_key.values(), key=row_key)
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
            "tail_fast_rescue": bool(fine_rows_by_batch.get(batch_id)),
            "tail_fast_rescue_jobs": sum(1 for item in fine_jobs if int(item.get("source_batch", -1)) == batch_id),
            "ended_at": time.time(),
        })
        write_json(child_path, child)
        job["status"] = child["status"]
        job["returncode"] = 0 if child["status"] == "COMPUTED" else 1
        job["rows"] = len(rows)
        job["status_counts"] = status_counts

    from scripts.run_full_matrix import aggregate

    merged = aggregate(main_root, jobs, int(main_manifest.get("full_candidates", 2)))
    merged["tail_fast_rescue"] = {
        "enabled": True,
        "fine_root": str(fine_root),
        "fast_profile": True,
        "official_evaluator_dir": str(fine_manifest.get("official_evaluator_dir", "")),
        "job_count": len(fine_jobs),
        "copied_combinations": copied,
        "copied_count": len(copied),
        "note": "Existing standard-matrix combinations were retained; only missing combinations were filled from fine-grained fast-profile jobs.",
    }
    write_json(main_root / "run_manifest.json", merged)
    print(json.dumps({"status": merged["status"], "rows": merged["rows"], "copied": len(copied)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
