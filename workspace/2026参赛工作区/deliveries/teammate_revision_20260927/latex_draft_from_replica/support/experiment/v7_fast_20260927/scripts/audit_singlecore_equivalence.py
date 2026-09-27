#!/usr/bin/env python3
"""Compare a fast single-core baseline with preserved original-evaluator rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


FIELDS = (
    "status", "makespan", "scheduled_copy_bytes", "original_graph_copy_bytes",
    "added_copy_bytes", "partition_added_copy_bytes", "spill_added_copy_bytes",
    "cache_hit_bytes", "cache_miss_bytes", "cache_hit_rate",
)


def rows(path: Path) -> dict[str, dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["case"]: row for row in csv.DictReader(handle)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-metrics", type=Path, required=True)
    parser.add_argument("--fast-metrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    original, fast = rows(args.original_metrics), rows(args.fast_metrics)
    mismatches = [
        {"case": case, "field": field, "original": original[case][field], "fast": fast[case][field]}
        for case in sorted(original.keys() & fast.keys())
        for field in FIELDS
        if original[case][field] != fast[case][field]
    ]
    audit = {
        "status": "MATCH" if set(original) == set(fast) == {f"case_{index:03d}" for index in range(1, 101)} and not mismatches else "MISMATCH",
        "original_metrics": str(args.original_metrics.resolve()),
        "original_sha256": sha256(args.original_metrics),
        "fast_metrics": str(args.fast_metrics.resolve()),
        "fast_sha256": sha256(args.fast_metrics),
        "original_cases": len(original),
        "fast_cases": len(fast),
        "missing_in_fast": sorted(original.keys() - fast.keys()),
        "extra_in_fast": sorted(fast.keys() - original.keys()),
        "compared_fields": FIELDS,
        "mismatches": mismatches,
    }
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "original_cases": len(original), "fast_cases": len(fast), "mismatches": len(mismatches)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
