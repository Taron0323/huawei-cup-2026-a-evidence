#!/usr/bin/env python3
"""Audit zero-byte Cache-hit selections without modifying the main matrix."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_experiment import normalize_cache_events  # noqa: E402


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def rescue_for(rescue_root: Path | None, case: str, cores: int) -> dict:
    if rescue_root is None:
        return {}
    path = rescue_root / "cases" / case / f"{cores}core" / "C" / "rescue_selection.json"
    return read_json(path) if path.exists() else {}


def classify(selection: dict, result: dict, events: list[dict], rescue: dict) -> str:
    hit_bytes = int((result.get("cache_stats") or {}).get("hit_bytes", 0))
    if hit_bytes > 0:
        return "final_has_cache_hit"
    query_counts = Counter(int(event.get("logical_tensor_id", event.get("tensor_id", -1))) for event in events if event.get("event") in {"hit", "miss"})
    repeated_final = any(count >= 2 for count in query_counts.values())
    if rescue.get("hit_candidate_count", 0) > 0:
        return "hit_found_in_rescue"
    diagnostic = selection.get("cache_diagnostic") or {}
    if diagnostic.get("zero_hit_final_with_hit_alternative"):
        return "hit_alternative_in_main_search"
    if not repeated_final:
        return "single_core_no_repeated_copy_in_final" if int(selection["cores"]) == 1 else "no_repeated_copy_in_final"
    return "repeated_misses_no_hit_candidate"


def main() -> None:
    parser = argparse.ArgumentParser()
    roots = parser.add_mutually_exclusive_group(required=True)
    roots.add_argument("--main-root", type=Path)
    roots.add_argument("--main-roots", type=Path, nargs="+")
    parser.add_argument("--rescue-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    main_roots = [path.resolve() for path in (args.main_roots or [args.main_root])]
    rescue_root = args.rescue_root.resolve() if args.rescue_root else None
    output = args.output_root.resolve()
    if output.exists():
        raise SystemExit(f"refusing existing output: {output}")

    rows = []
    seen = set()
    paths = []
    for main_root in main_roots:
        for pattern in ("batch_*/cases/*/*core/C/final_selection.json", "case_*_*core/cases/*/*core/C/final_selection.json", "cases/*/*core/C/final_selection.json"):
            paths.extend(main_root.glob(pattern))
    for selection_path in sorted(paths):
        scene_root = selection_path.parent
        case = scene_root.parent.parent.name
        cores = int(scene_root.parent.name[:-4])
        if (case, cores) in seen:
            continue
        seen.add((case, cores))
        selection = read_json(selection_path)
        selection_for_classification = {**selection, "cores": cores}
        candidate = selection["candidate"]
        result_path = scene_root / "candidates" / candidate / "result.json"
        profile_path = scene_root / "candidates" / candidate / "profile.json"
        result = read_json(result_path) if result_path.exists() else {}
        profile = read_json(profile_path) if profile_path.exists() else {}
        events = normalize_cache_events(result.get("cache_events", []), profile)
        rescue = rescue_for(rescue_root, case, cores)
        stats = result.get("cache_stats") or {}
        diagnostic = selection.get("cache_diagnostic") or {}
        rows.append({
            "case": case,
            "cores": cores,
            "status": "AI_VERIFIED" if result else "MISSING_RESULT",
            "final_candidate": candidate,
            "final_makespan": selection.get("makespan"),
            "final_cache_hit_bytes": int(stats.get("hit_bytes", 0)),
            "final_cache_miss_bytes": int(stats.get("miss_bytes", 0)),
            "final_cache_accesses": int(stats.get("accesses", 0)),
            "logical_event_mapping_count": sum(1 for event in events if "logical_tensor_id" in event),
            "event_count": len(events),
            "repeated_logical_tensor_count": sum(1 for count in Counter(int(event.get("logical_tensor_id", event.get("tensor_id", -1))) for event in events if event.get("event") in {"hit", "miss"}).values() if count >= 2),
            "evaluated_hit_candidate_count": int(diagnostic.get("evaluated_hit_candidate_count", 0)),
            "main_max_hit_bytes": int(diagnostic.get("max_hit_bytes", 0)),
            "rescue_hit_candidate_count": int(rescue.get("hit_candidate_count", 0)),
            "rescue_fastest_hit_candidate": (rescue.get("fastest_hit") or {}).get("candidate"),
            "rescue_fastest_hit_makespan": (rescue.get("fastest_hit") or {}).get("makespan"),
            "rescue_fastest_hit_bytes": (rescue.get("fastest_hit") or {}).get("cache_hit_bytes", 0),
            "epsilon_0_005_candidate": ((rescue.get("epsilon_hit_choices") or {}).get("0.005") or {}).get("candidate"),
            "epsilon_0_01_candidate": ((rescue.get("epsilon_hit_choices") or {}).get("0.01") or {}).get("candidate"),
            "category": classify(selection_for_classification, result, events, rescue),
        })

    summary = {
        "main_roots": [str(root) for root in main_roots],
        "rescue_root": str(rescue_root) if rescue_root else None,
        "rows": len(rows),
        "final_zero_hit_rows": sum(int(row["final_cache_hit_bytes"]) == 0 for row in rows),
        "category_counts": dict(Counter(row["category"] for row in rows)),
        "multi_core_zero_hit_rows": sum(int(row["cores"]) > 1 and int(row["final_cache_hit_bytes"]) == 0 for row in rows),
        "main_root_immutable": True,
        "claim_boundary": "Official final selections remain makespan-first. Rescue and epsilon rows are separate cache-aware alternatives.",
    }
    output.mkdir(parents=True)
    write_csv(output / "cache_zero_audit.csv", rows)
    write_json(output / "cache_zero_audit.json", {"summary": summary, "rows": rows})
    write_json(output / "run_manifest.json", {"run_id": output.name, "status": "COMPUTED", **summary})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
