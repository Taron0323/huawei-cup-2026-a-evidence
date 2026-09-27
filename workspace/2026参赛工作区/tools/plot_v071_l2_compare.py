#!/usr/bin/env python3
"""Plot the required Q3 same-plan no-L2 versus read-only-L2 curve.

The source is the already computed cache_pairs.csv.  This script does not run
the official evaluator and does not infer values for PROFILE_ONLY cases.
"""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    grouped: dict[int, dict[str, list[float]]] = defaultdict(lambda: {"no_l2": [], "l2": []})
    for row in rows(args.pairs):
        status = row.get("pair_status", "").strip().upper()
        if status not in {"AI_VERIFIED", "VERIFIED", "COMPUTED", "SUCCESS", "OK"}:
            continue
        try:
            core = int(row["cores"])
            no_l2 = float(row["no_l2_makespan"])
            l2 = float(row["cache_makespan"])
        except (KeyError, TypeError, ValueError):
            continue
        grouped[core]["no_l2"].append(no_l2)
        grouped[core]["l2"].append(l2)

    cores = sorted(grouped)
    if cores != [1, 2, 3, 4, 5]:
        raise SystemExit(f"expected complete K=1..5 pairs, got {cores}")
    no_l2_means = [statistics.mean(grouped[k]["no_l2"]) for k in cores]
    l2_means = [statistics.mean(grouped[k]["l2"]) for k in cores]

    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.unicode_minus": False, "font.size": 9})
    fig, ax = plt.subplots(figsize=(6.4, 3.7))
    ax.plot(cores, no_l2_means, marker="o", linewidth=2, color="#64748b", label="No L2")
    ax.plot(cores, l2_means, marker="s", linewidth=2, color="#0f766e", label="Read-only L2")
    ax.set_xlabel("Cores K")
    ax.set_ylabel("Mean makespan (cycles)")
    ax.set_xticks(cores)
    ax.grid(alpha=0.22)
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(args.output / "v071_l2_vs_no_l2_by_core.pdf")
    fig.savefig(args.output / "v071_l2_vs_no_l2_by_core.png", dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    main()
