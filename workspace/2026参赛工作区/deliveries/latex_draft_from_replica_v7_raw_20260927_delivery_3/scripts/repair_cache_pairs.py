#!/usr/bin/env python3
"""Rebuild B/C cache-pair fields from the three concrete result JSON files.

The old report retained only the final C cache counters.  This script keeps
the three plan/result identities explicit and derives the hardware scatter
from ``C(X_B)`` while retaining ``C(X_C)`` for the final-plan appendix.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def resolve_result(code_root: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.parts and relative_path.parts[0] == "code":
        relative_path = Path(*relative_path.parts[1:])
    path = code_root / relative_path
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def stats(result: dict) -> tuple[int, int, float]:
    cache = result.get("cache_stats") or {}
    hit = int(cache.get("hit_bytes", 0))
    miss = int(cache.get("miss_bytes", 0))
    return hit, miss, hit / (hit + miss) if hit + miss else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, required=True,
                        help="result_sources.csv generated from the audited run")
    parser.add_argument("--main-results", type=Path, required=True,
                        help="main_results.csv containing plan hashes")
    parser.add_argument("--code-root", type=Path, required=True,
                        help="root containing the relative code/results paths")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_rows = read_rows(args.sources)
    main_rows = read_rows(args.main_results)
    index = {(r["case"], int(r["cores"]), r["scene"]): r for r in source_rows}
    main_index = {(r["case"], int(r["cores"]), r["scene"]): r for r in main_rows}
    expected = {(f"case_{i:03d}", k, scene)
                for i in range(1, 101) for k in range(1, 6) for scene in "ABC"}
    if set(index) != expected:
        raise ValueError(f"result_sources coverage mismatch: {len(index)} rows")

    rows: list[dict[str, object]] = []
    for case in sorted({key[0] for key in index}):
        for cores in range(1, 6):
            b_source = index[(case, cores, "B")]
            c_source = index[(case, cores, "C")]
            b_path = resolve_result(args.code_root, b_source["final_result_path"])
            ci_path = resolve_result(args.code_root, c_source["initial_result_path"])
            cf_path = resolve_result(args.code_root, c_source["final_result_path"])
            b = json.loads(b_path.read_text(encoding="utf-8"))
            ci = json.loads(ci_path.read_text(encoding="utf-8"))
            cf = json.loads(cf_path.read_text(encoding="utf-8"))
            b_report = main_index[(case, cores, "B")]
            c_report = main_index[(case, cores, "C")]
            b_time, ci_time, cf_time = (int(b["makespan"]), int(ci["makespan"]), int(cf["makespan"]))
            b_hit, b_miss, _ = stats(b)
            ci_hit, ci_miss, ci_rate = stats(ci)
            cf_hit, cf_miss, cf_rate = stats(cf)
            row = {
                "case": case,
                "cores": cores,
                "b_plan_sha256": b_report["final_plan_sha256"],
                "c_initial_plan_sha256": c_report["initial_plan_sha256"],
                "c_final_plan_sha256": c_report["final_plan_sha256"],
                "c_starts_from_b": b_report["final_plan_sha256"] == c_report["initial_plan_sha256"],
                "b_makespan": b_time,
                "c_same_plan_makespan": ci_time,
                "c_initial_makespan": ci_time,
                "c_final_makespan": cf_time,
                "s_hw": b_time / ci_time,
                "s_adapt": ci_time / cf_time,
                "s_opt": b_time / cf_time,
                "factor_residual": b_time / cf_time - (b_time / ci_time) * (ci_time / cf_time),
                "c_initial_hit_bytes": ci_hit,
                "c_initial_miss_bytes": ci_miss,
                "c_initial_hit_rate": ci_rate,
                "c_final_hit_bytes": cf_hit,
                "c_final_miss_bytes": cf_miss,
                "c_final_hit_rate": cf_rate,
                "b_result_sha256": digest(b_path),
                "c_initial_result_sha256": digest(ci_path),
                "c_final_result_sha256": digest(cf_path),
                "b_result_path": b_source["final_result_path"],
                "c_initial_result_path": c_source["initial_result_path"],
                "c_final_result_path": c_source["final_result_path"],
            }
            # These are retained as aliases for old consumers; their meaning
            # is explicitly C(X_B), never the final C plan.
            row.update({"hit_bytes": ci_hit, "miss_bytes": ci_miss,
                        "c_hit_bytes": ci_hit, "c_miss_bytes": ci_miss,
                        "c_hit_rate": ci_rate})
            rows.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"rows": len(rows), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
