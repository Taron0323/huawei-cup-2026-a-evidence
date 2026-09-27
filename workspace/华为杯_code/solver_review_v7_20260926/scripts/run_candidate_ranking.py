#!/usr/bin/env python3
"""Evaluate one previously unmeasured candidate for each representative cell."""

from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huawei_code.graph import load_graph  # noqa: E402
from huawei_code.official import evaluate, load_modules, profile, read_config, summary  # noqa: E402
from huawei_code.plan import plan_key  # noqa: E402
from run_controls import REPRESENTATIVE_CASES, evaluator_dir, write_json  # noqa: E402


PRIORITY = {"capacity_representative": 0, "event_timing": 1, "timing": 2, "cache_delay": 3, "capacity": 4, "ordinary_chain": 5, "ordinary": 6}


def direction(left: tuple, right: tuple) -> int:
    return (left > right) - (left < right)


def find_scene(main_root: Path, case: str, cores: int, scene: str) -> Path | None:
    paths = list(main_root.glob(f"batch_*/cases/{case}/{cores}core/{scene}/final_selection.json"))
    if not paths:
        return None
    ledger = paths[0].parent / "candidate_ledger.json"
    return paths[0].parent if ledger.exists() and ledger.stat().st_mtime_ns >= paths[0].stat().st_mtime_ns else None


def worker(job: dict) -> dict:
    scene_root = Path(job["scene_root"])
    output = Path(job["output_root"]) / job["case"] / f"{job['cores']}core" / job["scene"]
    graph = load_graph(ROOT / "data/raw/A题/data" / f"{job['case']}.json")
    modules = load_modules(evaluator_dir())
    config = read_config(modules, ROOT / "data/raw/A题/data/config.txt")
    ledger = json.loads((scene_root / "candidate_ledger.json").read_text(encoding="utf-8"))
    selected = json.loads((scene_root / "final_selection.json").read_text(encoding="utf-8"))
    incumbent = next(item for item in ledger if item["candidate"] == selected["candidate"])
    incumbent_dir = scene_root / "candidates" / incumbent["candidate"]
    incumbent_profile = json.loads((incumbent_dir / "profile.json").read_text(encoding="utf-8"))
    incumbent_result = json.loads((incumbent_dir / "result.json").read_text(encoding="utf-8"))
    candidates = [item for item in ledger if (scene_root / "candidates" / item["candidate"] / "plan.json").exists() and not (scene_root / "candidates" / item["candidate"] / "result.json").exists() and item["profile_status"] != "PROFILE_FAILED"]
    candidates.sort(key=lambda item: (PRIORITY.get(item["source"], 9), tuple(item["light"]["score"]), item["plan_sha256"]))
    profile_failures = []
    chosen = chosen_profile = chosen_plan = None
    for item in candidates:
        plan = json.loads((scene_root / "candidates" / item["candidate"] / "plan.json").read_text(encoding="utf-8"))
        source_profile = scene_root / "candidates" / item["candidate"] / "profile.json"
        try:
            value = json.loads(source_profile.read_text(encoding="utf-8")) if source_profile.exists() else profile(graph, plan, job["scene"], config, modules)
        except Exception as exc:
            profile_failures.append({"candidate": item["candidate"], "error_type": type(exc).__name__, "error": str(exc)})
            continue
        chosen, chosen_profile, chosen_plan = item, value, plan
        break
    if chosen is None:
        row = {"case": job["case"], "cores": job["cores"], "scene": job["scene"], "status": "NO_VALID_UNMEASURED_CANDIDATE", "profile_failures": len(profile_failures)}
        write_json(output / "profile_failures.json", profile_failures)
        write_json(output / "record.json", row)
        return row

    write_json(output / "candidate_plan.json", chosen_plan)
    write_json(output / "candidate_profile.json", chosen_profile)
    write_json(output / "profile_failures.json", profile_failures)
    row = {
        "case": job["case"], "cores": job["cores"], "scene": job["scene"],
        "candidate": chosen["candidate"], "candidate_source": chosen["source"],
        "candidate_plan_sha256": plan_key(chosen_plan), "main_candidate": incumbent["candidate"],
        "main_plan_sha256": selected["plan_sha256"], "profile_failures": len(profile_failures),
        "light_direction": direction(tuple(chosen["light"]["score"]), tuple(incumbent["light"]["score"])),
        "profile_direction": direction(tuple(chosen_profile["profile_score"]), tuple(incumbent_profile["profile_score"])),
        "candidate_light_score": json.dumps(chosen["light"]["score"]),
        "main_light_score": json.dumps(incumbent["light"]["score"]),
        "candidate_profile_score": json.dumps(chosen_profile["profile_score"]),
        "main_profile_score": json.dumps(incumbent_profile["profile_score"]),
    }
    started = time.perf_counter()
    try:
        result = evaluate(graph, chosen_plan, {"A": 1, "B": 2, "C": 3}[job["scene"]], config, modules)
        write_json(output / "candidate_result.json", result)
        candidate_summary = summary(result)
        incumbent_summary = summary(incumbent_result)
        row.update({
            "status": "AI_VERIFIED", "evaluation_seconds": time.perf_counter() - started,
            "candidate_makespan": candidate_summary["makespan"], "main_makespan": incumbent_summary["makespan"],
            "candidate_added_copy_bytes": candidate_summary["added_copy_bytes"], "main_added_copy_bytes": incumbent_summary["added_copy_bytes"],
            "official_direction": direction((candidate_summary["makespan"], candidate_summary["added_copy_bytes"]), (incumbent_summary["makespan"], incumbent_summary["added_copy_bytes"])),
            "candidate_cache_hit_bytes": candidate_summary["cache_hit_bytes"], "main_cache_hit_bytes": incumbent_summary["cache_hit_bytes"],
        })
        row["light_agrees_with_official"] = row["light_direction"] == row["official_direction"]
        row["profile_agrees_with_official"] = row["profile_direction"] == row["official_direction"]
        row["light_delta_error_cycles"] = (chosen["light"]["light_time"] - incumbent["light"]["light_time"]) - (candidate_summary["makespan"] - incumbent_summary["makespan"])
    except Exception as exc:
        row.update({"status": "EVALUATION_FAILED", "evaluation_seconds": time.perf_counter() - started, "error_type": type(exc).__name__, "error": str(exc)})
    write_json(output / "record.json", row)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--parallel", type=int, default=2)
    args = parser.parse_args()
    main_root, out = args.main_root.resolve(), args.output_root.resolve()
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    out.mkdir(parents=True)
    cells = {(case, cores, scene) for case in REPRESENTATIVE_CASES for cores in (2, 5) for scene in ("A", "B", "C")}
    manifest = {"run_id": out.name, "status": "RUNNING", "main_root": str(main_root), "cells": len(cells), "parallel": args.parallel, "selection_rule": "source priority, light score, plan key among generated candidates with saved plans but no complete official result", "official_evaluator_dir": str(evaluator_dir()), "started_at": time.time()}
    write_json(out / "run_manifest.json", manifest)
    rows = []
    with ProcessPoolExecutor(max_workers=args.parallel) as pool:
        futures = set()
        while cells or futures:
            for case, cores, scene in sorted(cells):
                scene_root = find_scene(main_root, case, cores, scene)
                if scene_root is None:
                    continue
                futures.add(pool.submit(worker, {"case": case, "cores": cores, "scene": scene, "scene_root": str(scene_root), "output_root": str(out)}))
                cells.remove((case, cores, scene))
            if not futures:
                time.sleep(5)
                continue
            completed, futures = wait(futures, timeout=5, return_when=FIRST_COMPLETED)
            for future in completed:
                row = future.result()
                rows.append(row)
                print(json.dumps({key: row.get(key) for key in ("case", "cores", "scene", "status", "light_agrees_with_official", "profile_agrees_with_official")}, ensure_ascii=False), flush=True)
    fields = sorted({field for row in rows for field in row})
    with (out / "candidate_ranking.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    valid = [row for row in rows if row["status"] == "AI_VERIFIED"]
    manifest.update({"status": "COMPUTED" if len(rows) == 36 else "PARTIAL", "rows": len(rows), "valid_pairs": len(valid), "evaluation_failures": sum(row["status"] == "EVALUATION_FAILED" for row in rows), "light_agreement": sum(row["light_agrees_with_official"] for row in valid), "profile_agreement": sum(row["profile_agrees_with_official"] for row in valid), "ended_at": time.time()})
    write_json(out / "run_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
