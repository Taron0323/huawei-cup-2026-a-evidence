#!/usr/bin/env python3
"""Summarize the completed cache sensitivity experiment and render figures."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evidence_contract import (  # noqa: E402
    check_companion, main_signature, official_hashes, read_complete_manifest,
    selected_scene,
)

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
    run_manifest = read_complete_manifest(source / "run_manifest.json")
    main_roots = [Path(path) for path in run_manifest.get("main_roots", [])]
    if not main_roots:
        raise ValueError("sensitivity run has no bound main roots")
    signature = main_signature(main_roots, check_files=False)
    if os.environ.get("HUAWEI_ALLOW_PROVENANCE_MISMATCH") != "1":
        check_companion(run_manifest, signature, cases=sorted(CASES))
    if official_hashes(Path(run_manifest["official_evaluator_dir"])) != run_manifest["official_code_sha256"]:
        raise ValueError("sensitivity evaluator changed since run")

    fixed = read_csv(source / "fixed_plan.csv")
    reoptimized = read_csv(source / "reoptimized.csv")
    expected = {(case, variant) for case in CASES for variant in VARIANTS}
    fixed_keys = {(row["case"], row["variant"]) for row in fixed}
    reopt_keys = {(row["case"], row["variant"]) for row in reoptimized}
    if fixed_keys != expected or reopt_keys != expected:
        raise ValueError(f"incomplete sensitivity groups: fixed_missing={sorted(expected - fixed_keys)} reopt_missing={sorted(expected - reopt_keys)}")

    summary = []
    failures = []
    defaults = {}
    for case in CASES:
        _b_dir, b_selection, _b_plan, _b_result = selected_scene(main_roots, case, 5, "B")
        _c_dir, c_selection, _c_plan, c_result = selected_scene(main_roots, case, 5, "C", "initial")
        if b_selection["plan_sha256"] != c_selection["plan_sha256"]:
            raise ValueError(f"C initial is not B final plan: {case}")
        defaults[case] = (b_selection["plan_sha256"], float(c_result["makespan"]))
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
        b_plan_sha, default_c_ms = defaults[case]
        if f["plan_sha256"] != b_plan_sha:
            raise ValueError(f"sensitivity fixed plan differs from B final: {case}/{variant}")
        f_ms = number(f, "makespan")
        r_ms = number(r, "makespan")
        summary.append({
            "case": case,
            "variant": variant,
            "fixed_makespan": f_ms,
            "reoptimized_makespan": r_ms,
            "reoptimized_candidate": r["candidate"],
            "b_plan_sha256": b_plan_sha,
            "reoptimized_plan_sha256": r["plan_sha256"],
            "plan_changed": r["plan_sha256"] != b_plan_sha,
            "default_c_initial_makespan": default_c_ms,
            "fixed_to_default_ratio": f_ms / default_c_ms,
            "reoptimized_to_default_ratio": r_ms / default_c_ms,
            "fixed_to_reoptimized_ratio": f_ms / r_ms if r_ms else float("nan"),
            "fixed_cache_hit_rate": number(f, "cache_hit_rate"),
            "reoptimized_cache_hit_rate": number(r, "cache_hit_rate"),
            "fixed_added_copy_bytes": number(f, "added_copy_bytes"),
            "reoptimized_added_copy_bytes": number(r, "added_copy_bytes"),
            "reoptimized_failed_alternatives": sum(row["status"] != "AI_VERIFIED" for row in reopt_rows),
            "gpu_backend": r.get("gpu_backend", ""),
        })

    out.mkdir(parents=True)
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
        fixed_to_default_ratio=("fixed_to_default_ratio", "mean"),
        reoptimized_to_default_ratio=("reoptimized_to_default_ratio", "mean"),
        plan_changed=("plan_changed", "sum"),
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
    fig.savefig(fig_dir / "sensitivity_makespan.png"); fig.savefig(fig_dir / "sensitivity_makespan.svg"); fig.savefig(fig_dir / "sensitivity_makespan.pdf"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=160)
    ax.plot(list(x), grouped["fixed_cache_hit_rate"], marker="o", label="fixed B plan")
    ax.plot(list(x), grouped["reoptimized_cache_hit_rate"], marker="o", label="reoptimized")
    ax.set_xticks(list(x), [value.replace("cache_", "").replace("_", " ") for value in grouped["variant"]], rotation=20, ha="right")
    ax.set_ylabel("mean cache hit rate")
    ax.set_title("Cache sensitivity: hit rate")
    ax.grid(alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(fig_dir / "sensitivity_hit_rate.png"); fig.savefig(fig_dir / "sensitivity_hit_rate.svg"); fig.savefig(fig_dir / "sensitivity_hit_rate.pdf"); plt.close(fig)

    backends = sorted({row.get("gpu_backend", "") for row in reoptimized if row.get("gpu_backend")})
    lines = [
        "# A题 Cache 敏感性实验",
        "",
        f"固定计划和重优化均使用官方 Problem-3 评估器。固定计划为同图 5 核 B 最终计划；重优化在每个硬件变体下重新生成有限候选，再以官方评估结果选出可用候选。记录的负载排序后端：{', '.join(backends) if backends else '未记录'}。",
        "",
        f"固定计划：{len(fixed)} 条，全部 `AI_VERIFIED`。重优化候选：{len(reoptimized)} 条，其中成功 {sum(row['status'] == 'AI_VERIFIED' for row in reoptimized)} 条，失败 {len(failures)} 条；每组均至少有一个成功候选。",
        "",
        "| 变体 | 图数 | 固定/默认逐图比均值 | 重优化/默认逐图比均值 | 重优化改变计划 | 固定命中率 | 重优化命中率 | 失败候选数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in grouped.to_dict("records"):
        lines.append(f"| {row['variant']} | {int(row['cases'])} | {row['fixed_to_default_ratio']:.4f} | {row['reoptimized_to_default_ratio']:.4f} | {int(row['plan_changed'])}/{int(row['cases'])} | {row['fixed_cache_hit_rate']:.4f} | {row['reoptimized_cache_hit_rate']:.4f} | {int(row['failure_alternatives'])} |")
    lines += ["", "失败候选完整错误文本见 `sensitivity_failures.csv`；图在 `figures/`。"]
    (out / "sensitivity_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {"status": "COMPUTED", "source": str(source), "main_roots": [str(root) for root in main_roots], "source_signature": signature, "summary_rows": len(summary), "fixed_rows": len(fixed), "reoptimized_rows": len(reoptimized), "reoptimized_failures": len(failures), "changed_plans": sum(row["plan_changed"] for row in summary), "all_groups_have_selected_result": True, "provenance_warning": "Current solver files differ from the original main-matrix hashes; sensitivity results retain their own recorded snapshot." if os.environ.get("HUAWEI_ALLOW_PROVENANCE_MISMATCH") == "1" else None}
    (out / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
