"""Build appendix tables from the final v7 selection report.

The candidate-level timing ledger is not used here.  Every table is derived
from ``v7_fast_reports_complete_20260927/main_results.csv`` (final_selection)
and the separately audited Cache pair/sensitivity reports.
"""
from __future__ import annotations

import csv
import random
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/v7_fast_20260927"
GEN = ROOT / "generated"


def read(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def f(row, key):
    return float(row[key])


def boot(values):
    rng = random.Random(20260927 + len(values))
    vals = sorted(st.mean(rng.choices(values, k=len(values))) for _ in range(1500))
    return vals[37], vals[1462]


def table(headers, rows, spec=None, caption=None, label=None):
    n = len(headers)
    spec = spec or ("c" + "r" * (n - 1))
    out = [f"\\begin{{longtable}}{{{spec}}}"]
    if caption:
        out.append(f"\\caption{{{caption}}}\\label{{{label}}}\\\\")
    out += [r"\toprule", " & ".join(headers) + " \\\\", r"\midrule", r"\endfirsthead",
            f"\\multicolumn{{{n}}}{{c}}{{续表}}\\\\", r"\toprule",
            " & ".join(headers) + " \\\\", r"\midrule", r"\endhead",
            f"\\midrule\\multicolumn{{{n}}}{{r}}{{续下页}}\\\\", r"\endfoot",
            r"\bottomrule", r"\endlastfoot"]
    out += [" & ".join(r) + " " + chr(92) * 2 for r in rows]
    out.append(r"\end{longtable}")
    return "\n".join(out) + "\n"


def main():
    rows = read("main_results.csv")
    by = {(r["case"], int(r["cores"]), r["scene"]): r for r in rows}
    cases = sorted({r["case"] for r in rows})
    # Summary table for the three speedup curves and initial-to-final ablation.
    summary = []
    for scene in "ABC":
        for k in range(1, 6):
            group = [by[(c, k, scene)] for c in cases]
            vals = [f(r, "speedup_vs_baseline") for r in group]
            gains = [f(r, "initial_to_final_relative_gain") * 100 for r in group]
            summary.append([scene, str(k), f"{st.mean(vals):.4f}", f"{st.median(vals):.4f}",
                            f"[{boot(vals)[0]:.4f},{boot(vals)[1]:.4f}]",
                            f"{st.mean(gains):.4f}", f"{sum(g > 1e-12 for g in gains)}/100"])
    (GEN / "v7_summary_tables.tex").write_text(table(
        ["场景", "核数", "平均加速比", "中位数", "95\\%实例区间", "初始至最终改善/\\%", "改善图数"],
        summary, "ccrrrrr", "v7主矩阵速度比与候选消融（100图）", "tab:v7-summary"), encoding="utf-8")

    # Cache decomposition, preserving the identity S_opt=S_hw*S_adapt.
    pairs = read("cache_pairs.csv")
    cache = []
    for k in range(1, 6):
        g = [r for r in pairs if int(r["cores"]) == k]
        cache.append([str(k), str(len(g)), f"{st.mean(f(r,'s_hw') for r in g):.4f}",
                      f"{st.mean(f(r,'s_adapt') for r in g):.4f}",
                      f"{st.mean(f(r,'s_opt') for r in g):.4f}"])
    (GEN / "v7_cache_tables.tex").write_text(table(
        ["核数", "样本", "$S_{\\rm hw}$", "$S_{\\rm adapt}$", "$S_{\\rm opt}$"],
        cache, "ccrrr", "v7 Cache 三段效应（500组同计划配对）", "tab:v7-cache"), encoding="utf-8")

    # Four hardware variants; the source report is already an aggregate over six graphs.
    sens = read("sensitivity_variant_summary.csv")
    sens_rows = []
    name = {"cache_capacity_half": "容量减半", "cache_capacity_double": "容量加倍",
            "cache_bandwidth_half": "带宽减半", "cache_bandwidth_double": "带宽加倍"}
    for r in sens:
        sens_rows.append([name.get(r["variant"], r["variant"]), r["cases"],
                          f"{f(r,'fixed_cache_hit_rate')*100:.4f}\\%",
                          f"{f(r,'reoptimized_cache_hit_rate')*100:.4f}\\%",
                          f"{f(r,'reoptimized_to_default_ratio'):.4f}",
                          r["plan_changed"] + "/6", r["failure_alternatives"]])
    (GEN / "v7_sensitivity_table.tex").write_text(table(
        ["硬件变体", "图数", "固定命中率", "重优化命中率", "重优化/默认工期比", "改计划", "失败候选"],
        sens_rows, "lcrrrcc", "Cache容量与带宽扰动（6张代表图）", "tab:v7-sensitivity"), encoding="utf-8")

    # Detailed selected final rows: one longtable per core count, all three scenes.
    detail = []
    for k in range(1, 6):
        body = []
        for c in cases:
            rr = [by[(c, k, s)] for s in "ABC"]
            body.append([c[-3:]] + sum(([str(int(f(r,"final_makespan"))), f"{f(r,'speedup_vs_baseline'):.3f}",
                                           str(int(f(r,"final_added_copy_bytes")))] for r in rr), []))
        detail.append(table(["图", "$T_A/S_A$", "$D_A$/B", "$T_B/S_B$", "$D_B$/B", "$T_C/S_C$", "$D_C$/B"],
                            body, "crrrrrr", f"{k}核三问最终方案逐例结果（100图）", f"tab:v7-detail-{k}"))
    (GEN / "v7_detail_tables.tex").write_text("\n".join(detail), encoding="utf-8")


if __name__ == "__main__":
    main()
