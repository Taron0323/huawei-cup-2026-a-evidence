#!/usr/bin/env python3
"""Summarize the completed cache sensitivity experiment and render figures."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

CASES = {"case_051", "case_012", "case_067", "case_081", "case_016", "case_062"}
VARIANTS = {"cache_capacity_half", "cache_capacity_double", "cache_bandwidth_half", "cache_bandwidth_double"}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def number(row: dict, key: str) -> float:
    value = row.get(key, "")
    return float(value) if value not in ("", None) else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    source = args.input_root.resolve()
    out = args.output_root.resolve()
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    out.mkdir(parents=True)

    fixed = read_csv(source / "fixed_plan.csv")
    reoptimized = read_csv(source / "reoptimized.csv")
    expected = {(case, variant) for case in CASES for variant in VARIANTS}
    fixed_keys = {(row["case"], row["variant"]) for row in fixed}
    reopt_keys = {(row["case"], row["variant"]) for row in reoptimized}
    if fixed_keys != expected or reopt_keys != expected:
        raise ValueError(f"incomplete sensitivity groups: fixed_missing={sorted(expected - fixed_keys)} reopt_missing={sorted(expected - reopt_keys)}")

    summary = []
    failures = []
    for case, variant in sorted(expected):
        fixed_rows = [row for row in fixed if row["case"] == case and row["variant"] == variant]
        reopt_rows = [row for row in reoptimized if row["case"] == case and row["variant"] == variant]
        fixed_ok = [row for row in fixed_rows if row["status"] == "AI_VERIFIED"]
        reopt_ok = [row for row in reopt_rows if row["status"] == "AI_VERIFIED"]
        selected = [row for row in reopt_ok if row.get("selected") == "True"]
        if len(fixed_ok) != 1 or len(selected) != 1:
            raise ValueError(f"missing usable result for {case}/{variant}: fixed={len(fixed_ok)} selected={len(selected)}")
        for row in reopt_rows:
            if row["status"] != "AI_VERIFIED":
                failures.append({"case": case, "variant": variant, "candidate": row.get("candidate", ""), "error_type": row.get("error_type", ""), "error": row.get("error", "")})
        f = fixed_ok[0]
        r = selected[0]
        f_ms = number(f, "makespan")
        r_ms = number(r, "makespan")
        summary.append({
            "case": case,
            "variant": variant,
            "fixed_makespan": f_ms,
            "reoptimized_makespan": r_ms,
            "reoptimized_candidate": r["candidate"],
            "fixed_to_reoptimized_ratio": f_ms / r_ms if r_ms else float("nan"),
            "fixed_cache_hit_rate": number(f, "cache_hit_rate"),
            "reoptimized_cache_hit_rate": number(r, "cache_hit_rate"),
            "fixed_added_copy_bytes": number(f, "added_copy_bytes"),
            "reoptimized_added_copy_bytes": number(r, "added_copy_bytes"),
            "reoptimized_failed_alternatives": sum(row["status"] != "AI_VERIFIED" for row in reopt_rows),
            "gpu_backend": r.get("gpu_backend", ""),
        })

    write_csv(out / "sensitivity_summary.csv", summary)
    write_csv(out / "sensitivity_failures.csv", failures)
    frame = pd.DataFrame(summary)
    variant_order = sorted(VARIANTS)
    grouped = frame.groupby("variant", sort=False).agg(
        cases=("case", "count"),
        fixed_makespan=("fixed_makespan", "mean"),
        reoptimized_makespan=("reoptimized_makespan", "mean"),
        fixed_cache_hit_rate=("fixed_cache_hit_rate", "mean"),
        reoptimized_cache_hit_rate=("reoptimized_cache_hit_rate", "mean"),
        failure_alternatives=("reoptimized_failed_alternatives", "sum"),
    ).reindex(variant_order).reset_index()
    grouped.to_csv(out / "sensitivity_variant_summary.csv", index=False)

    fig_dir = out / "figures"
    fig_dir.mkdir()
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=160)
    x = range(len(grouped))
    width = 0.36
    ax.bar([i - width / 2 for i in x], grouped["fixed_makespan"], width, label="fixed B plan")
    ax.bar([i + width / 2 for i in x], grouped["reoptimized_makespan"], width, label="reoptimized")
    ax.set_xticks(list(x), [value.replace("cache_", "").replace("_", " ") for value in grouped["variant"]], rotation=20, ha="right")
    ax.set_ylabel("mean Problem-3 makespan (cycles)")
    ax.set_title("Cache sensitivity: fixed plan vs reoptimized")
    ax.grid(axis="y", alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(fig_dir / "sensitivity_makespan.png"); fig.savefig(fig_dir / "sensitivity_makespan.svg"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=160)
    ax.plot(list(x), grouped["fixed_cache_hit_rate"], marker="o", label="fixed B plan")
    ax.plot(list(x), grouped["reoptimized_cache_hit_rate"], marker="o", label="reoptimized")
    ax.set_xticks(list(x), [value.replace("cache_", "").replace("_", " ") for value in grouped["variant"]], rotation=20, ha="right")
    ax.set_ylabel("mean cache hit rate")
    ax.set_title("Cache sensitivity: hit rate")
    ax.grid(alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(fig_dir / "sensitivity_hit_rate.png"); fig.savefig(fig_dir / "sensitivity_hit_rate.svg"); plt.close(fig)

    lines = [
        "# A题 Cache 敏感性实验",
        "",
        "固定计划和重优化均使用官方 Problem-3 评估器。固定计划为同图 5 核 B 最终计划；重优化在每个硬件变体下重新生成有限候选并使用 Apple MPS 排序负载向量，再以官方评估结果选择可用候选。",
        "",
        f"固定计划：{len(fixed)} 条，全部 `AI_VERIFIED`。重优化候选：{len(reoptimized)} 条，其中成功 {sum(row['status'] == 'AI_VERIFIED' for row in reoptimized)} 条，依赖环失败 {len(failures)} 条；每个 组均至少有一个成功候选。",
        "",
        "| 变体 | 图数 | 固定计划平均 makespan | 重优化平均 makespan | 固定命中率 | 重优化命中率 | 失败候选数 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in grouped.to_dict("records"):
        lines.append(f"| {row['variant']} | {int(row['cases'])} | {row['fixed_makespan']:.3f} | {row['reoptimized_makespan']:.3f} | {row['fixed_cache_hit_rate']:.4f} | {row['reoptimized_cache_hit_rate']:.4f} | {int(row['failure_alternatives'])} |")
    lines += ["", "失败候选完整错误文本见 `sensitivity_failures.csv`；图在 `figures/`。"]
    (out / "sensitivity_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {"status": "COMPUTED", "source": str(source), "summary_rows": len(summary), "fixed_rows": len(fixed), "reoptimized_rows": len(reoptimized), "reoptimized_failures": len(failures), "all_groups_have_selected_result": True}
    (out / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
