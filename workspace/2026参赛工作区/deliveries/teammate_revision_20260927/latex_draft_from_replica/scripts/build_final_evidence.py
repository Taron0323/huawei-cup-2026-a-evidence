"""Rebuild paper tables and figures from the audited 2026-09-24 package."""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
import math
import os
import random
import statistics as st
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.patches import ConnectionPatch, FancyBboxPatch, Rectangle
from mpl_toolkits.axes_grid1.inset_locator import inset_axes, mark_inset

from evidence_data import assert_declared_count, infer_matrix_shape, resolve_data_dir

ROOT = Path(__file__).resolve().parents[1]
DATA = resolve_data_dir(ROOT, None, "data/audited_20260924")
IDEA_PATH = Path(os.environ.get("PAPER_IDEA_PATH", ROOT / "support/experiment/A题_Final_idea_给codex运行.md")).resolve()
FIG = ROOT / "figures"
GEN = ROOT / "generated"
# The reference figures use a white canvas, dark navy structure lines, and
# four pastel semantic colors.  Keep this palette shared by every plot.
BLUE, TEAL, AMBER, RED = "#215A82", "#2F8B78", "#E09A32", "#D45555"
PALE_BLUE, PALE_TEAL, PALE_AMBER, PALE_RED = "#DCEAF4", "#DCEFE9", "#F8E8C8", "#F6DDDD"
INK, GRID, EDGE = "#1F3345", "#C8D4DC", "#2A4355"
PANEL = "#F8FBFC"


def rows(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def first_rows(*names):
    for name in names:
        path = DATA / name
        if path.exists():
            return rows(name)
    raise FileNotFoundError(f"none of the evidence files exist: {names}")


def number(row, key):
    return float(row[key])


def latex_table(caption, label, headers, body, widths=None):
    n = len(headers)
    assert all(len(row) == n for row in body)
    spec = widths or ("c" + "r" * (n - 1))
    output = [r"\begin{longtable}{" + spec + "}",
              r"\caption{" + caption + r"}\label{" + label + r"}\\",
              r"\toprule", " & ".join(headers) + " \\\\", r"\midrule", r"\endfirsthead",
              r"\multicolumn{" + str(n) + r"}{c}{续表}\\", r"\toprule",
              " & ".join(headers) + " \\\\", r"\midrule", r"\endhead",
              r"\midrule\multicolumn{" + str(n) + r"}{r}{续下页}\\", r"\endfoot",
              r"\bottomrule", r"\endlastfoot"]
    output.extend(" & ".join(row) + " \\\\" for row in body)
    output.append(r"\end{longtable}")
    return "\n".join(output) + "\n"


def bootstrap_mean_interval(values):
    # The benchmark is fixed; this interval describes sensitivity to case mix.
    rng = random.Random(20260924 + len(values))
    sample_count = len(values) * 15
    sample = sorted(st.mean(rng.choices(values, k=len(values))) for _ in range(sample_count))
    return sample[int(sample_count * .025)], sample[int(sample_count * .975) - 1]


def inherited_plan_index(raw_index, cases):
    """Apply the reported per-case best-plan rule without changing raw evidence.

    For target K, the effective plan is the shortest evaluated plan at any
    core count j <= K, with the full-graph single-core baseline also eligible.
    A lower-core plan is padded with empty core lists, so its Makespan and
    recorded plan metrics remain valid for the target configuration.
    """
    effective = {}
    for case in cases:
        baseline = number(raw_index[case, 1, "A"], "baseline_makespan")
        for scene in "ABC":
            for target_k in range(1, 6):
                candidates = [raw_index[case, j, scene] for j in range(1, target_k + 1)]
                best = min(candidates, key=lambda row: (number(row, "final_makespan"),
                                                         number(row, "final_added_copy_bytes")))
                best_time = min(baseline, number(best, "final_makespan"))
                row = dict(best)
                row["cores"] = str(target_k)
                row["final_makespan"] = str(int(best_time))
                row["speedup_vs_baseline"] = str(baseline / best_time)
                row["inherited_from_cores"] = "0" if best_time == baseline else str(best["cores"])
                row["inherited_baseline_selected"] = str(best_time == baseline)
                effective[case, target_k, scene] = row
    return effective


def set_font():
    # The supplied PPTX references use a clean sans-serif Chinese face.
    for name in ("PingFang SC", "Hiragino Sans GB", "STHeiti Medium", "Noto Sans CJK SC", "SimHei", "SimSun"):
        try:
            path = font_manager.findfont(name, fallback_to_default=False)
            plt.rcParams.update({"font.family": font_manager.FontProperties(fname=path).get_name(),
                                 "axes.unicode_minus": False, "font.size": 9.5,
                                 "font.weight": "regular", "axes.titleweight": "bold",
                                 "pdf.fonttype": 42, "savefig.facecolor": "white",
                                 "figure.facecolor": "white", "axes.facecolor": PANEL,
                                 "axes.titlecolor": INK})
            return path
        except ValueError:
            continue
    raise RuntimeError("Chinese font unavailable for paper figures")


def decorate(ax, ylabel=None):
    """Apply the rounded-card, pastel-panel grammar used in the references."""
    ax.set_facecolor(PANEL)
    for spine in ("left", "bottom", "top", "right"):
        ax.spines[spine].set_color("#9FB0BA" if spine in ("top", "right") else INK)
        ax.spines[spine].set_linewidth(.75 if spine in ("top", "right") else .95)
    ax.grid(axis="y", color=GRID, linewidth=.7, linestyle=(0, (3, 3)))
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", colors=INK, labelsize=8.5, length=3, width=.75)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK, fontweight="bold")
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)
    ax.xaxis.label.set_fontweight("bold")
    ax.yaxis.label.set_fontweight("bold")


def style_legend(legend):
    """Use the rounded legend card used in the supplied PPTX references."""
    if legend is None:
        return
    legend.get_frame().set_facecolor("white")
    legend.get_frame().set_edgecolor("#A6B7C1")
    legend.get_frame().set_linewidth(.8)
    legend.get_frame().set_boxstyle("round,pad=0.32,rounding_size=0.10")
    legend.get_frame().set_alpha(.97)
    for text in legend.get_texts():
        text.set_color(INK)


def add_value_labels(ax, bars, formatter=lambda value: f"{value:.2f}", offset=3,
                     fontsize=8, color=INK):
    """Put compact values above vertical bars without changing the data."""
    for bar in bars:
        value = bar.get_height()
        y = value + offset if value >= 0 else value - offset
        va = "bottom" if value >= 0 else "top"
        ax.annotate(formatter(value),
                    (bar.get_x() + bar.get_width() / 2, value),
                    xytext=(0, offset if value >= 0 else -offset),
                    textcoords="offset points", ha="center", va=va,
                    fontsize=fontsize, color=color)


def plot_bar_with_hatch(ax, x, values, label, color, hatch, width=.20,
                        edgecolor=EDGE, alpha=.92):
    # The reference bars are solid pastel cards; color carries the series
    # identity and hatch is intentionally omitted to keep the plot readable.
    bars = ax.bar(x, values, width=width, label=label, color=color,
                  edgecolor=edgecolor, linewidth=1.15, hatch=None, alpha=.96,
                  zorder=3)
    return bars


def save(fig, name):
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight", pad_inches=.09)
    fig.savefig(FIG / f"{name}.png", dpi=240, bbox_inches="tight", pad_inches=.09)
    fig.savefig(FIG / f"{name}.svg", bbox_inches="tight", pad_inches=.09)
    plt.close(fig)


def plot_sensitivity_case_heatmap(response, cases):
    """Show all fixed-plan responses and enlarge the only strongly responsive case."""
    assert response and len(response) == len(cases)
    variant_count = len(response[0])
    assert variant_count > 0 and all(len(row) == variant_count for row in response)
    coral, teal = "#BD5B45", "#168C91"
    focus_case = "case_062" if "case_062" in cases else max(
        cases, key=lambda case: max(abs(value) for value in response[cases.index(case)])
    )
    fig = plt.figure(figsize=(7.7, 4.25), facecolor="white")
    matrix = fig.add_axes([.075, .18, .58, .53])
    detail = fig.add_axes([.75, .30, .23, .40])
    fig.text(.075, .955, "Cache 扰动的逐图工期响应", fontsize=11, weight="bold", color=INK)
    fig.text(.075, .895, "固定计划 · 5 核 · 问题 C · 相对默认配置的变化（%）",
             fontsize=8.1, color="#66777B")
    fig.text(.75, .795, f"{focus_case[-3:]} 号图 / 响应放大", fontsize=9.1, weight="bold", color=INK)

    matrix.set_xlim(0, 4)
    matrix.set_ylim(6, 0)
    matrix.set_xticks([.5, 1.5, 2.5, 3.5], ["减半", "加倍", "减半", "加倍"])
    matrix.xaxis.tick_top()
    matrix.tick_params(axis="x", length=0, labelsize=8.2, pad=6, colors=INK)
    matrix.set_yticks([i + .5 for i in range(6)], [case[-3:] for case in cases])
    matrix.tick_params(axis="y", length=0, labelsize=8.6, pad=9, colors=INK)
    for spine in matrix.spines.values():
        spine.set_visible(False)
    matrix.text(1, -1.00, "Cache 容量", ha="center", va="bottom",
                fontsize=8.7, weight="bold", color=INK)
    matrix.text(3, -1.00, "Cache 带宽", ha="center", va="bottom",
                fontsize=8.7, weight="bold", color=INK)
    matrix.plot([.06, 1.94], [-.70, -.70], color="#B9C6C8", lw=.9, clip_on=False)
    matrix.plot([2.06, 3.94], [-.70, -.70], color="#B9C6C8", lw=.9, clip_on=False)

    for i, values in enumerate(response):
        for j, value in enumerate(values):
            if abs(value) < 1e-11:
                fill, text_color, label = "#F3F5F4", "#91A0A2", "0"
            else:
                base = to_rgb(coral if value > 0 else teal)
                # The printed number is quantitative; the tint only helps find responses.
                strength = .12 + .68 * min(1, math.sqrt(abs(value) / 1.7))
                fill = tuple(1 - strength * (1 - channel) for channel in base)
                text_color = "white" if abs(value) >= 1 else INK
                label = f"{value:+.3f}"
            matrix.add_patch(Rectangle((j + .035, i + .075), .93, .85,
                                       facecolor=fill, edgecolor="white", linewidth=.7))
            matrix.text(j + .5, i + .5, label, ha="center", va="center",
                        fontsize=8.1, color=text_color,
                        weight="bold" if abs(value) >= .3 else "normal")
    focus = cases.index(focus_case)
    matrix.plot([2, 2], [.02, 5.98], color="white", lw=4, zorder=5)
    matrix.plot([2, 2], [.02, 5.98], color="#D2DDDE", lw=.85, zorder=6)
    matrix.add_patch(Rectangle((.01, focus + .05), 3.98, .90,
                               fill=False, edgecolor=coral, linewidth=1.25, zorder=7))

    focus_values = response[focus]
    detail.axvline(0, color="#89999D", linewidth=.9, zorder=1)
    detail.set_xlim(-.45, 2.62)
    detail.set_ylim(3.6, -.6)
    for y, value in enumerate(focus_values):
        detail.plot([0, value], [y, y], color=coral if value > 0 else teal,
                    lw=5.2, solid_capstyle="round", zorder=2)
        detail.scatter([value], [y], s=26, color=coral if value > 0 else teal,
                       edgecolor="white", linewidth=.5, zorder=3)
        detail.text(2.55, y, f"{value:+.3f}", va="center", ha="right",
                    fontsize=7.3, color=INK, weight="bold" if abs(value) >= .3 else "normal")
    detail.set_xticks([0, .8, 1.6], ["0", "0.8", "1.6"])
    detail.tick_params(axis="x", length=2.5, labelsize=7, colors="#6B7C80")
    detail.set_yticks(range(4), ["容 /2", "容 ×2", "带 /2", "带 ×2"])
    detail.tick_params(axis="y", length=0, labelsize=7.5, pad=4, colors=INK)
    detail.spines[["top", "left", "right"]].set_visible(False)
    detail.spines["bottom"].set_color("#B9C6C8")
    detail.spines["bottom"].set_linewidth(.7)
    fig.text(.865, .205, "工期变化 / %", ha="center", fontsize=7.4, color="#66777B")

    fig.text(.075, .085, "工期缩短", color=teal, fontsize=7.4, weight="bold")
    fig.text(.155, .085, "工期不变", color="#819195", fontsize=7.4, weight="bold")
    fig.text(.235, .085, "工期延长", color=coral, fontsize=7.4, weight="bold")
    fig.text(.745, .085, "色深辅助识别；以单元格数值为准", color="#66777B", fontsize=7.0)
    save(fig, "sensitivity_case_heatmap")


def plot_core_choice_tail(index_override=None):
    """Rank each case's evaluated best-core gain against its five-core plan."""
    source = DATA / "main_results.csv"
    with source.open(encoding="utf-8-sig", newline="") as stream:
        records = list(csv.DictReader(stream))
    index = index_override or {(r["case"], int(r["cores"]), r["scene"]): r for r in records}
    cases = sorted({r["case"] for r in records})
    shape = infer_matrix_shape(records)
    case_count = int(shape["case_count"])
    core_values = tuple(shape["cores"])
    scene_values = tuple(shape["scenes"])
    assert core_values == tuple(range(1, 6)) and scene_values == ("A", "B", "C")
    assert len(cases) == case_count and len(index) == len(records) == int(shape["main_rows"])
    assert set(index) == {(case, k, scene) for case in cases for scene in scene_values for k in core_values}
    assert all(r.get("status") in {"AI_VERIFIED", "AUDITED_STORED_RESULT"} for r in records)

    palette = {"A": BLUE, "B": TEAL, "C": AMBER}
    pale = {"A": PALE_BLUE, "B": PALE_TEAL, "C": PALE_AMBER}
    fig = plt.figure(figsize=(7.15, 4.05), facecolor="white")
    fig.text(.095, .974, "逐图继承最优计划后，五核方案不再出现退化", fontsize=11,
             weight="bold", color=INK, va="top")
    fig.text(.095, .921, f"{case_count} 张计算图 · 各场景分别排序 · 相对五核计划的工期降幅",
             fontsize=8.1, color="#66777B", va="top")
    fig.text(.765, .907, "超过阈值的图数", fontsize=8.2, color=INK,
             weight="bold", ha="center")
    for x, label in zip((.765, .846, .927), (">1%", ">5%", ">10%")):
        fig.text(x, .870, label, ha="center", fontsize=7.5, color="#66777B")

    stats = {}
    for scene, bottom in zip("ABC", (.655, .432, .209)):
        gains = []
        for case in cases:
            values = [number(index[case, k, scene], "final_makespan") for k in core_values]
            assert all(math.isfinite(value) and value > 0 for value in values)
            gains.append((case, 100 * (values[4] - min(values)) / values[4]))
        gains.sort(key=lambda item: (-item[1], item[0]))
        counts = [sum(value > threshold for _, value in gains) for threshold in (1, 5, 10)]
        mean = st.mean(value for _, value in gains)
        total_gain = sum(value for _, value in gains)
        top_five_share = 100 * sum(value for _, value in gains[:5]) / total_gain if total_gain else 0.0
        stats[scene] = {"mean_gain_percent": mean, "above_1_5_10": counts,
                        "top_five_share_percent": top_five_share,
                        "largest_case": gains[0][0], "largest_gain_percent": gains[0][1]}

        ax = fig.add_axes([.095, bottom, .615, .187])
        ranks = range(1, case_count + 1)
        values = [gain for _, gain in gains]
        ax.axvspan(.5, 5.5, facecolor=pale[scene], alpha=.35, zorder=0)
        for threshold in (1, 5, 10):
            ax.axhline(threshold, color="#A8B5B9", lw=.62,
                       ls=(0, (2, 3)), zorder=1)
        ax.fill_between(ranks, values, color=pale[scene], alpha=.47, zorder=2)
        ax.plot(ranks, values, color=palette[scene], lw=1.6, zorder=3)
        ax.scatter(list(ranks)[:5], values[:5], s=14, color=palette[scene],
                   edgecolor="white", linewidth=.45, zorder=4)
        ax.set_xlim(.5, case_count + .5)
        ax.set_ylim(0, 78)
        ax.set_yticks((0, 20, 40, 60))
        step = max(1, case_count // 5)
        ticks = tuple(sorted({1, *(step * index for index in range(1, 6)), case_count}))
        ax.set_xticks(ticks)
        ax.tick_params(axis="both", length=2.5, labelsize=7.2, colors=INK)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color("#84969B")
        ax.spines[["left", "bottom"]].set_linewidth(.65)
        ax.text(.98, .84, f"问题{ord(scene)-64} · 均值 {mean:.2f}%",
                ha="right", va="top", transform=ax.transAxes,
                color=palette[scene], fontsize=8, weight="bold")
        ax.annotate(f"{gains[0][0][-3:]}  {gains[0][1]:.1f}%",
                    xy=(1, gains[0][1]), xytext=(19, 66),
                    textcoords="data", fontsize=7.4, color=INK,
                    arrowprops={"arrowstyle": "-", "lw": .7, "color": palette[scene]})
        if scene != "C":
            ax.tick_params(axis="x", labelbottom=False)
        for x, count in zip((.765, .846, .927), counts):
            fig.text(x, bottom + .105, str(count), ha="center", va="center",
                     fontsize=11, weight="bold", color=palette[scene])
        fig.text(.845, bottom + .042, f"前 5 图占降幅总和 {top_five_share:.1f}%",
                 ha="center", fontsize=7.5, color=INK)

    fig.text(.402, .097, "逐图降幅排序（场景内降序）", ha="center",
             fontsize=8.1, color=INK)
    fig.text(.095, .039, "官方模拟工期；仅在已评价的 1–5 核计划内选最短，A 单核为辅助诊断。",
             fontsize=7.2, color="#66777B")
    save(fig, "core_choice_tail")
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="evidence CSV/manifest directory (defaults to PAPER_EVIDENCE_DATA or data/audited_20260924)",
    )
    parser.add_argument("--idea-path", type=Path, help="Idea file used for provenance hashing")
    parser.add_argument("--figures-only", action="store_true",
                        help="rebuild figures and summary without replacing generated LaTeX tables")
    args = parser.parse_args(argv)
    global DATA, IDEA_PATH
    DATA = resolve_data_dir(ROOT, args.data_dir, "data/audited_20260924")
    if args.idea_path is not None:
        IDEA_PATH = args.idea_path.expanduser().resolve()
    if not DATA.is_dir():
        raise FileNotFoundError(f"evidence data directory does not exist: {DATA}")
    main_rows = rows("main_results.csv")
    effects = first_rows("candidate_comparison.csv", "candidate_effects.csv")
    pairs = rows("cache_pairs.csv")
    sensitivity = rows("sensitivity_results.csv")
    sensitivity_failures = first_rows("sensitivity_failed_candidates.csv", "sensitivity_failures.csv")
    candidate_success = first_rows("candidate_evaluations.csv", "timing.csv")
    candidate_failures = first_rows("main_failed_candidates.csv", "candidate_failures.csv")
    baseline_rows = rows("singlecore_baseline.csv")
    epsilon_rows = rows("epsilon_tradeoffs.csv") if (DATA / "epsilon_tradeoffs.csv").exists() else []
    shape = infer_matrix_shape(main_rows)
    cases = list(shape["cases"])
    case_count = int(shape["case_count"])
    core_values = tuple(shape["cores"])
    scene_values = tuple(shape["scenes"])
    assert core_values == tuple(range(1, 6))
    assert scene_values == ("A", "B", "C")
    main_count = int(shape["main_rows"])
    assert_declared_count(DATA, main_count, "main_rows")
    assert_declared_count(DATA, len(baseline_rows), "baseline_rows")
    pair_keys = {(r["case"], int(r["cores"])) for r in pairs}
    assert len(pair_keys) == len(pairs)
    assert len(pair_keys) == case_count * len(core_values)
    pair_count = assert_declared_count(DATA, len(pair_keys), "cache_pairs")
    sensitivity_count = assert_declared_count(DATA, len(sensitivity), "sensitivity_rows")
    keys = {(r["case"], int(r["cores"]), r["scene"]) for r in main_rows}
    assert len(keys) == len(main_rows) == len(effects) == main_count
    assert keys == {(case, k, s) for case in cases for k in core_values for s in scene_values}
    assert all(r.get("status") in {"AUDITED_STORED_RESULT", "AI_VERIFIED"} for r in main_rows)
    formal_rows = [r for r in main_rows if r.get("formal_matrix", "True") == "True"]
    nonformal_rows = [r for r in main_rows if r.get("formal_matrix", "False") == "False"]
    assert len(nonformal_rows) == case_count
    assert len(formal_rows) == main_count - len(nonformal_rows)
    assert all(r.get("formal_matrix", "False") == "False" for r in nonformal_rows)
    assert len(baseline_rows) == case_count
    assert sensitivity_count == len(sensitivity)
    assert len(candidate_success) + len(candidate_failures) > 0
    sensitivity_index = {(r["case"], r["variant"], r["mode"]): r for r in sensitivity}
    assert len(sensitivity_index) == sensitivity_count
    assert {r["mode"] for r in sensitivity} == {"fixed_plan", "reoptimized"}
    assert all(r["status"] == "EVALUATION_FAILED" and "dependency cycle" in r["error"]
               for r in sensitivity_failures)
    index = {(r["case"], int(r["cores"]), r["scene"]): r for r in main_rows}
    pair_index = {(r["case"], int(r["cores"])): r for r in pairs}
    effect_index = {(r["case"], int(r["cores"]), r["scene"]): r for r in effects}
    assert set(effect_index) == keys
    baseline_index = {r["case"]: r for r in baseline_rows}
    assert set(baseline_index) == set(cases)
    for case in cases:
        base = number(index[case, 1, "A"], "baseline_makespan")
        assert base > 0 and base == number(baseline_index[case], "makespan")
        for k in range(1, 6):
            for scene in "ABC":
                r = index[case, k, scene]
                assert number(r, "final_makespan") > 0
                assert math.isclose(base / number(r, "final_makespan"), number(r, "speedup_vs_baseline"), rel_tol=1e-10)
                assert math.isclose(1 - number(r, "final_makespan") / number(r, "initial_makespan"),
                                    number(r, "initial_to_final_relative_gain"), abs_tol=1e-12)
                assert r["initial_plan_sha256"] and r["final_plan_sha256"] and r["final_source"]
            p = pair_index[case, k]
            b, c = index[case, k, "B"], index[case, k, "C"]
            assert b["final_plan_sha256"] == c["initial_plan_sha256"]
            assert number(p, "b_makespan") == number(b, "final_makespan")
            assert number(p, "c_same_plan_makespan") == number(c, "initial_makespan")
            assert number(p, "c_final_makespan") == number(c, "final_makespan")
            assert math.isclose(number(p, "s_hw") * number(p, "s_adapt"), number(p, "s_opt"), rel_tol=1e-12)
    GEN.mkdir(exist_ok=True)
    set_font()
    effective_index = inherited_plan_index(index, cases)
    plot_core_choice_tail(effective_index)
    summary = {"idea_sha256": hashlib.sha256(IDEA_PATH.read_bytes()).hexdigest(),
               "source_sha256": {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest() for name in
                                 ("main_results.csv", "candidate_comparison.csv", "cache_pairs.csv",
                                  "sensitivity_results.csv", "singlecore_baseline.csv")},
               "coverage": {"cases": len(cases), "formal_combinations": len(formal_rows),
                            "stored_combinations": len(main_rows),
                            "a_singlecore_diagnostics": sum(r["scene"] == "A" and int(r["cores"]) == 1 for r in main_rows),
                            "successful_candidates": len(candidate_success),
                            "failed_candidates": len(candidate_failures),
                            "cache_pairs": pair_count,
                            "sensitivity_groups": len(sensitivity) // 2,
                            "sensitivity_failed_alternatives": len(sensitivity_failures)},
               "selection_rule": "per-case minimum of evaluated plans at cores 1..K and the full-graph single-core baseline; lower-core plans are padded with empty core lists",
               "by_scene": {}, "cache": [], "sensitivity": []}
    for scene in "ABC":
        values = []
        stats = []
        for k in range(1, 6):
            items = [effective_index[case, k, scene] for case in cases]
            ratios = [number(r, "speedup_vs_baseline") for r in items]
            if scene in "AB" and k == 1:
                display = [1.] * case_count
            else:
                display = ratios
            lo, hi = bootstrap_mean_interval(display)
            gains = [number(r, "initial_to_final_relative_gain") for r in items]
            item = {"cores": k, "mean": st.mean(display), "median": st.median(display),
                    "raw_mean": st.mean(ratios), "ci_low": lo, "ci_high": hi,
                    "slow_count": sum(x < 1 for x in ratios),
                    "mean_gain_percent": 100 * st.mean(gains),
                    "improved_count": sum(number(r, "initial_makespan") > number(r, "final_makespan") for r in items),
                    "mean_added_copy_mib": st.mean(number(r, "final_added_copy_bytes") for r in items) / 2**20}
            stats.append(item)
            values.append(display)
        summary["by_scene"][scene] = stats
        xs = list(range(1, 6))
        means = [r["mean"] for r in stats]
        medians = [r["median"] for r in stats]
        lo = [r["ci_low"] for r in stats]
        hi = [r["ci_high"] for r in stats]
        y_span = max(hi) - min(lo)
        slowdown = sum(number(effective_index[case, 5, scene], "final_makespan") >
                       number(effective_index[case, 4, scene], "final_makespan") for case in cases)
        delta = means[4] - means[3]
        # The three questions share the same audited values but use different
        # visual grammars so that the reader can tell the intended reading
        # action from the layout: A is a side-by-side crop, B is an annotated
        # turning-point view, and C is a main plot with an inset crop.
        if scene == "A":
            figure, axes = plt.subplots(1, 2, figsize=(7.2, 3.05),
                                        gridspec_kw={"width_ratios": [2.2, 1]})
            ax, zoom = axes
            primary, secondary, band = BLUE, AMBER, PALE_BLUE
            decorate(ax, "对整图单核基准的加速比")
            ax.fill_between(xs, lo, hi, color=band, alpha=.58,
                            edgecolor="none", label="均值95%实例重采样区间", zorder=1)
            ax.plot(xs, lo, color=primary, lw=.55, alpha=.42, ls=(0, (2, 2)), zorder=2)
            ax.plot(xs, hi, color=primary, lw=.55, alpha=.42, ls=(0, (2, 2)), zorder=2)
            ax.plot(xs, means, "o-", color=primary, lw=2.15, ms=5.2,
                    markerfacecolor="white", markeredgewidth=1.2,
                    label="逐例比值均值", zorder=4)
            ax.plot(xs, medians, "s--", color=secondary, lw=1.55, ms=4.8,
                    markerfacecolor="white", markeredgewidth=1.0,
                    label="中位数", zorder=4)
            ax.axhline(1, color="#707B80", lw=.85, ls=(0, (2, 2)), zorder=2)
            ax.set_xticks(xs)
            ax.set_xlabel("核数")
            style_legend(ax.legend(loc="upper left", fontsize=8))
            ax.set_ylim(min(lo) - .08 * y_span, max(hi) + .23 * y_span)

            zoom_x = xs[3:]
            zoom_lo, zoom_hi = lo[3:], hi[3:]
            zoom_mean, zoom_median = means[3:], medians[3:]
            zoom_values = [*zoom_lo, *zoom_hi, *zoom_mean, *zoom_median]
            zoom_min, zoom_max = min(zoom_values), max(zoom_values)
            zoom_span = max(zoom_max - zoom_min, .08)
            crop_low = zoom_min - .10 * zoom_span
            crop_high = zoom_max + .10 * zoom_span
            crop = Rectangle((3.78, crop_low), 1.34, crop_high - crop_low,
                             fill=False, edgecolor=secondary, linewidth=.9,
                             linestyle=(0, (2, 2)), zorder=6)
            ax.add_patch(crop)
            for xy_a, xy_b in [((3.78, crop_high), (0, 1)),
                               ((3.78, crop_low), (0, 0))]:
                connector = ConnectionPatch(xyA=xy_a, coordsA="data", axesA=ax,
                                            xyB=xy_b, coordsB="axes fraction", axesB=zoom,
                                            color="#82939A", linewidth=.7,
                                            linestyle=(0, (2, 3)), alpha=.78,
                                            zorder=1)
                figure.add_artist(connector)
            decorate(zoom, "")
            zoom.fill_between(zoom_x, zoom_lo, zoom_hi, color=band, alpha=.58,
                              edgecolor="none", zorder=1)
            zoom.plot(zoom_x, zoom_lo, color=primary, lw=.5, alpha=.42,
                      ls=(0, (2, 2)), zorder=2)
            zoom.plot(zoom_x, zoom_hi, color=primary, lw=.5, alpha=.42,
                      ls=(0, (2, 2)), zorder=2)
            zoom.plot(zoom_x, zoom_mean, "o-", color=primary, lw=2.05, ms=5,
                      markerfacecolor="white", markeredgewidth=1.1, zorder=4)
            zoom.plot(zoom_x, zoom_median, "s--", color=secondary, lw=1.35, ms=4,
                      markerfacecolor="white", markeredgewidth=1.0, zorder=4)
            zoom.set_xlim(3.70, 5.30)
            zoom.set_xticks(zoom_x)
            zoom.set_xlabel("关键区间：4→5核", fontsize=8.0)
            zoom.set_title("4→5核局部放大", fontsize=9.5)
            zoom.set_ylim(min(zoom_lo) - .20 * zoom_span,
                          max(zoom_hi) + .42 * zoom_span)
            # Keep the numerical summary in the lower blank band of the crop.
            # The two curves and their interval occupy the upper half, so the
            # annotation cannot cover a marker or a confidence boundary.
            zoom.text(.95, .055,
                      f"均值 {zoom_mean[0]:.2f} → {zoom_mean[1]:.2f}\n"
                      f"Δ {delta:+.2f}；{slowdown} 图反升",
                      transform=zoom.transAxes, ha="right", va="bottom", fontsize=6.9,
                      color=INK, linespacing=1.25,
                      bbox={"facecolor": "white", "edgecolor": GRID,
                            "boxstyle": "round,pad=.34", "alpha": .97},
                      clip_on=True, zorder=8)
            for xpos, value, offset in ((4, zoom_mean[0], (-17, -13)),
                                        (5, zoom_mean[1], (7, -13))):
                zoom.annotate(f"{value:.2f}", xy=(xpos, value), xytext=offset,
                              textcoords="offset points", fontsize=6.8, color=primary,
                              ha="center", va="top", zorder=8,
                              bbox={"facecolor": "white", "edgecolor": "none",
                                    "pad": 0.8, "alpha": .88})
            for xpos, value, offset in ((4, zoom_median[0], (-17, 8)),
                                        (5, zoom_median[1], (7, 8))):
                zoom.annotate(f"{value:.2f}", xy=(xpos, value), xytext=offset,
                              textcoords="offset points", fontsize=6.8, color=secondary,
                              ha="center", va="bottom", zorder=8,
                              bbox={"facecolor": "white", "edgecolor": "none",
                                    "pad": 0.8, "alpha": .88})
            figure.suptitle(f"问题一：{case_count}图加速比（右侧为4→5核局部放大）", y=1.005,
                            fontsize=11, color=INK, fontweight="bold")
            figure.tight_layout()
        elif scene == "B":
            figure, ax = plt.subplots(figsize=(7.2, 3.45))
            primary, secondary, band = TEAL, RED, PALE_TEAL
            decorate(ax, "对整图单核基准的加速比")
            ax.fill_between(xs, lo, hi, color=band, alpha=.62,
                            edgecolor="none", label="均值95%实例重采样区间", zorder=1)
            ax.plot(xs, lo, color=primary, lw=.55, alpha=.46, ls=(0, (2, 2)), zorder=2)
            ax.plot(xs, hi, color=primary, lw=.55, alpha=.46, ls=(0, (2, 2)), zorder=2)
            ax.plot(xs, means, "D-", color=primary, lw=2.1, ms=5.1,
                    markerfacecolor="white", markeredgewidth=1.2,
                    label="逐例比值均值", zorder=4)
            ax.plot(xs, medians, "^--", color=secondary, lw=1.55, ms=4.8,
                    markerfacecolor="white", markeredgewidth=1.0,
                    label="中位数", zorder=4)
            ax.axhline(1, color="#707B80", lw=.85, ls=(0, (2, 2)), zorder=2)
            ax.axvspan(3.72, 5.10, color="#F7E6E5", alpha=.42, zorder=0)
            ax.axvline(4.5, color=secondary, lw=1.0, ls=(0, (3, 2)), alpha=.72, zorder=3)
            ax.set_xticks(xs)
            ax.set_xlabel("核数")
            ax.set_ylim(min(lo) - .08 * y_span, max(hi) + .30 * y_span)
            style_legend(ax.legend(loc="upper left", fontsize=8))
            # Put the turning-point explanation below the data band.  This
            # preserves the 4→5 marker and interval as the visual focus while
            # leaving the annotated sentence readable at paper scale.
            ax.text(.98, .105,
                    "4→5核逐图统计\n"
                    f"均值 {means[3]:.2f}→{means[4]:.2f}（Δ{delta:+.2f}）\n"
                    f"{slowdown} 张图工期反升",
                    transform=ax.transAxes, ha="right", va="bottom",
                    fontsize=7.2, color=INK, linespacing=1.25,
                    bbox={"facecolor": "white", "edgecolor": secondary,
                          "boxstyle": "round,pad=.38", "alpha": .96},
                    zorder=8)
            figure.tight_layout()
        else:
            figure, ax = plt.subplots(figsize=(7.2, 3.45))
            primary, secondary, band = AMBER, BLUE, PALE_AMBER
            decorate(ax, "对整图单核基准的加速比")
            ax.fill_between(xs, lo, hi, color=band, alpha=.62,
                            edgecolor="none", label="均值95%实例重采样区间", zorder=1)
            ax.plot(xs, lo, color=primary, lw=.55, alpha=.46, ls=(0, (2, 2)), zorder=2)
            ax.plot(xs, hi, color=primary, lw=.55, alpha=.46, ls=(0, (2, 2)), zorder=2)
            ax.plot(xs, means, "o-", color=primary, lw=2.15, ms=5.2,
                    markerfacecolor="white", markeredgewidth=1.2,
                    label="逐例比值均值", zorder=4)
            ax.plot(xs, medians, "s--", color=secondary, lw=1.55, ms=4.8,
                    markerfacecolor="white", markeredgewidth=1.0,
                    label="中位数", zorder=4)
            ax.axhline(1, color="#707B80", lw=.85, ls=(0, (2, 2)), zorder=2)
            ax.set_xticks(xs)
            ax.set_xlabel("核数")
            ax.set_ylim(min(lo) - .08 * y_span, max(hi) + .26 * y_span)
            style_legend(ax.legend(loc="upper left", fontsize=8))

            zoom = inset_axes(ax, width="42%", height="49%", loc="upper right",
                              borderpad=1.15)
            zoom_x, zoom_lo, zoom_hi = xs[3:], lo[3:], hi[3:]
            zoom_mean, zoom_median = means[3:], medians[3:]
            zoom_values = [*zoom_lo, *zoom_hi, *zoom_mean, *zoom_median]
            zoom_min, zoom_max = min(zoom_values), max(zoom_values)
            zoom_span = max(zoom_max - zoom_min, .08)
            decorate(zoom, "")
            zoom.fill_between(zoom_x, zoom_lo, zoom_hi, color=band, alpha=.72,
                              edgecolor="none", zorder=1)
            zoom.plot(zoom_x, zoom_lo, color=primary, lw=.5, alpha=.48,
                      ls=(0, (2, 2)), zorder=2)
            zoom.plot(zoom_x, zoom_hi, color=primary, lw=.5, alpha=.48,
                      ls=(0, (2, 2)), zorder=2)
            zoom.plot(zoom_x, zoom_mean, "o-", color=primary, lw=1.8, ms=4.2,
                      markerfacecolor="white", markeredgewidth=1.0, zorder=4)
            zoom.plot(zoom_x, zoom_median, "s--", color=secondary, lw=1.25, ms=3.8,
                      markerfacecolor="white", markeredgewidth=.9, zorder=4)
            zoom.set_xlim(3.72, 5.28)
            zoom.set_xticks(zoom_x)
            zoom.set_ylim(zoom_min - .38 * zoom_span,
                          zoom_max + .18 * zoom_span)
            zoom.tick_params(axis="both", labelsize=6.9, length=2)
            zoom.set_title("4→5核", fontsize=8.2, color=INK, pad=3)
            zoom.text(.95, .035, f"Δ均值 {delta:+.2f}\n{slowdown}图反升",
                      transform=zoom.transAxes, ha="right", va="bottom",
                      fontsize=6.6, color=INK,
                      bbox={"facecolor": "white", "edgecolor": GRID,
                            "boxstyle": "round,pad=.25", "alpha": .94})
            mark_inset(ax, zoom, loc1=2, loc2=3, fc="none", ec=secondary,
                       lw=.8, ls=(0, (2, 2)))
            figure.suptitle(f"问题三：{case_count}图加速比（主图内嵌4→5核窗口）", y=1.005,
                            fontsize=11, color=INK, fontweight="bold")
            figure.tight_layout()
        save(figure, f"speedup_{scene}")
    fig, ax = plt.subplots(figsize=(6.9, 3.3))
    xs = list(range(1, 6))
    for shift, scene, color, pale, hatch in zip((-.22, 0, .22), "ABC",
                                                (BLUE, TEAL, AMBER),
                                                (PALE_BLUE, PALE_TEAL, PALE_AMBER),
                                                ("/", "..", "\\\\")):
        vals = [r["mean_gain_percent"] for r in summary["by_scene"][scene]]
        bars = plot_bar_with_hatch(ax, [x + shift for x in xs], vals,
                                   f"问题{scene}", pale, hatch)
        add_value_labels(ax, bars, lambda value: f"{value:.1f}", offset=2.5,
                         fontsize=6.2)
    decorate(ax, "初始至最终平均工期降幅 / %")
    ax.set_xticks(xs)
    ax.set_xlabel("核数")
    style_legend(ax.legend(ncol=3, fontsize=8))
    fig.tight_layout()
    save(fig, "candidate_gain")

    # A/B comparison uses one point per changed graph; 61 exact ties are
    # reported as a single labelled reference point rather than jittered.
    fig, ax = plt.subplots(figsize=(7.05, 3.55))
    changed, same = [], []
    for case in cases:
        a, b = index[case, 5, "A"], index[case, 5, "B"]
        x = (number(b, "final_added_copy_bytes") -
             number(a, "final_added_copy_bytes")) / 2**20
        y = number(b, "final_makespan") / number(a, "final_makespan")
        (same if x == 0 and y == 1 else changed).append((case, x, y))
    assert len(same) + len(changed) == case_count
    for _, x, y in changed:
        ax.scatter(x, y, s=34, facecolor=TEAL if y < 1 else AMBER,
                   edgecolor="white", linewidth=.75, alpha=.9, zorder=4)
    ax.scatter([0], [1], s=185, marker="D", facecolor=PALE_BLUE,
               edgecolor=BLUE, linewidth=1.2, zorder=5)
    ax.annotate(f"{len(same)}图两项相同", (0, 1), xytext=(11, -24),
                textcoords="offset points", fontsize=8.2, color=BLUE,
                arrowprops={"arrowstyle": "-", "color": BLUE, "lw": .9})
    for case, text_xy in (("case_053", (-92, -25)), ("case_055", (18, 22))):
        _, x, y = next(row for row in changed if row[0] == case)
        ax.annotate(case[-3:], (x, y), xytext=text_xy, textcoords="offset points",
                    fontsize=8.4, color=INK, fontweight="bold",
                    arrowprops={"arrowstyle": "->", "color": INK, "lw": .9},
                    bbox={"facecolor": "white", "edgecolor": GRID, "pad": 2})
    ax.axhline(1, color=INK, lw=.9, ls=(0, (3, 3)))
    ax.axvline(0, color=INK, lw=.9, ls=(0, (3, 3)))
    ax.set_xscale("symlog", linthresh=.4)
    ax.set_yscale("log")
    ax.set_yticks([.25, .5, 1, 2, 3], ["0.25", "0.5", "1", "2", "3"])
    ax.set_xlabel("B相对A的额外搬运变化 / MiB（对称对数轴）")
    decorate(ax, "同图B/A工期比（<1表示B更快）")
    ax.set_title("五核逐图：核心驻留改变搬运与工期的对应关系", fontsize=10.5)
    ax.text(.98, .06, "青：B更快  ·  橙：B更慢", transform=ax.transAxes,
            ha="right", fontsize=8, color=INK)
    fig.tight_layout()
    save(fig, "ab_tradeoff_scatter")
    summary["ab_tradeoff"] = {"same_count": len(same), "changed_count": len(changed)}

    slow_matrix = [[sum(number(effective_index[case, k+1, scene], "final_makespan") >
                         number(effective_index[case, k, scene], "final_makespan") for case in cases)
                    for k in range(1, 5)] for scene in "ABC"]
    summary["marginal_slow_counts"] = dict(zip("ABC", slow_matrix))
    fig, ax = plt.subplots(figsize=(6.9, 2.75))
    cmap = LinearSegmentedColormap.from_list("slow", ["#E7F2EF", "#A9D2CE", "#E6C096", "#C87463"])
    image = ax.imshow(slow_matrix, cmap=cmap, vmin=0, vmax=40, aspect="auto")
    ax.set_xticks(range(4), ["1→2", "2→3", "3→4", "4→5"])
    ax.set_yticks(range(3), ["问题一", "问题二", "问题三"])
    ax.set_xlabel("核心数变化")
    ax.set_title(f"同图增加核心后的工期退化：每格以{case_count}图为分母", fontsize=10.5, pad=11)
    for i, values in enumerate(slow_matrix):
        for j, value in enumerate(values):
            ax.text(j, i, f"{value}图", ha="center", va="center",
                    color="#263B40", fontsize=10, fontweight="bold")
    ax.set_xticks([x-.5 for x in range(1, 4)], minor=True)
    ax.set_yticks([x-.5 for x in range(1, 3)], minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", bottom=False, left=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=ax, fraction=.035, pad=.025)
    colorbar.set_label("退化图数", fontsize=8.5)
    fig.tight_layout()
    save(fig, "marginal_slow_heatmap")
    for k in range(1, 6):
        ps = [pair_index[case, k] for case in cases]
        summary["cache"].append({"cores": k, **{field: st.mean(number(p, field) for p in ps) for field in ("s_hw", "s_adapt", "s_opt")},
                                 "improved_hw": sum(number(p, "s_hw") > 1 for p in ps),
                                 "adapted": sum(number(p, "s_adapt") > 1 for p in ps),
                                 "hit_rate_weighted": sum(number(p, "c_initial_hit_bytes") for p in ps) /
                                 sum(number(p, "c_initial_hit_bytes") + number(p, "c_initial_miss_bytes") for p in ps),
                                 "final_hit_rate_weighted": sum(number(p, "c_final_hit_bytes") for p in ps) /
                                 sum(number(p, "c_final_hit_bytes") + number(p, "c_final_miss_bytes") for p in ps)})
    fig, ax = plt.subplots(figsize=(6.9, 3.3))
    for field, label, color, marker in (("s_hw", "硬件变化", BLUE, "o"),
                                        ("s_adapt", "调度适配", AMBER, "s"),
                                        ("s_opt", "综合", TEAL, "^")):
        vals = [r[field] for r in summary["cache"]]
        ax.plot(xs, vals, marker + "-", color=color, lw=2.0, ms=5,
                markerfacecolor="white", markeredgewidth=1.05,
                label=label, zorder=4)
    decorate(ax, "逐例比值的算术平均")
    ax.set_xticks(xs)
    ax.set_xlabel("核数")
    style_legend(ax.legend(ncol=3, fontsize=8))
    all_cache_values = [r[field] for r in summary["cache"]
                        for field in ("s_hw", "s_adapt", "s_opt")]
    cache_span = max(all_cache_values) - min(all_cache_values)
    ax.set_ylim(min(all_cache_values) - .12 * max(cache_span, .005),
                max(all_cache_values) + .42 * max(cache_span, .005))
    five = summary["cache"][-1]
    ax.annotate(f"五核：硬件 {five['s_hw']:.4f}\n适配 {five['s_adapt']:.4f} · 综合 {five['s_opt']:.4f}",
                xy=(5, five["s_opt"]), xycoords="data",
                xytext=(.98, .94), textcoords="axes fraction",
                ha="right", va="top", fontsize=7.1, color=INK,
                bbox={"facecolor": "white", "edgecolor": GRID,
                      "boxstyle": "round,pad=.35", "alpha": .96},
                arrowprops={"arrowstyle": "-", "color": TEAL, "lw": .8,
                            "shrinkA": 4, "shrinkB": 4})
    fig.tight_layout()
    save(fig, "cache_decomposition")

    # Directly answer the third question with the same case set at each
    # core count.  The left panel uses absolute mean makespan; the right panel
    # reports the two C configurations relative to B(X_B), so the denominator
    # and the plan identity remain visible in the figure itself.
    direct = {"B(X_B)": [], "C(X_B)": [], "C(X_C)": []}
    ratios = {"C(X_B)/B(X_B)": [], "C(X_C)/B(X_B)": []}
    for k in range(1, 6):
        b_values = [number(index[case, k, "B"], "final_makespan") for case in cases]
        same_values = [number(pair_index[case, k], "c_same_plan_makespan") for case in cases]
        final_values = [number(pair_index[case, k], "c_final_makespan") for case in cases]
        direct["B(X_B)"].append(st.mean(b_values) / 1e6)
        direct["C(X_B)"].append(st.mean(same_values) / 1e6)
        direct["C(X_C)"].append(st.mean(final_values) / 1e6)
        ratios["C(X_B)/B(X_B)"].append(st.mean(same / b for same, b in zip(same_values, b_values)))
        ratios["C(X_C)/B(X_B)"].append(st.mean(final / b for final, b in zip(final_values, b_values)))
    fig, axes = plt.subplots(1, 2, figsize=(7.15, 3.25), gridspec_kw={"width_ratios": [1.45, 1]})
    ax, ratio_ax = axes
    palette = {"B(X_B)": BLUE, "C(X_B)": TEAL, "C(X_C)": AMBER}
    markers = {"B(X_B)": "o", "C(X_B)": "s", "C(X_C)": "^"}
    for label in direct:
        ax.plot(xs, direct[label], marker=markers[label], color=palette[label], lw=2.0,
                ms=5, markerfacecolor="white", markeredgewidth=1.0, label=label)
    for label, color, marker in (("C(X_B)/B(X_B)", TEAL, "s"), ("C(X_C)/B(X_B)", AMBER, "^")):
        ratio_ax.plot(xs, ratios[label], marker=marker, color=color, lw=1.9,
                      ms=4.6, markerfacecolor="white", markeredgewidth=1.0,
                      label=label)
    ax.set_xticks(xs); ratio_ax.set_xticks(xs)
    ax.set_xlabel("核数"); ratio_ax.set_xlabel("核数")
    decorate(ax, "平均工期 / $10^6$ cycle")
    decorate(ratio_ax, "相对 $B(X_B)$ 的工期比")
    ax.set_title("绝对工期", fontsize=9.8); ratio_ax.set_title("直接相对比较", fontsize=9.8)
    ax.grid(axis="y", color=GRID, linewidth=.55, linestyle=(0, (3, 3)))
    ratio_ax.axhline(1, color=INK, lw=.8, ls=(0, (3, 3)))
    style_legend(ax.legend(loc="best", fontsize=7.5))
    style_legend(ratio_ax.legend(loc="best", fontsize=7.0))
    ax.annotate(f"五核三段均值\n{direct['B(X_B)'][-1]:.2f} / {direct['C(X_B)'][-1]:.2f} / {direct['C(X_C)'][-1]:.2f}",
                xy=(5, direct["C(X_C)"][-1]), xycoords="data",
                xytext=(.97, .94), textcoords="axes fraction",
                ha="right", va="top", fontsize=6.9, color=INK,
                bbox={"facecolor": "white", "edgecolor": GRID,
                      "boxstyle": "round,pad=.3", "alpha": .96},
                arrowprops={"arrowstyle": "-", "color": AMBER, "lw": .75,
                            "shrinkA": 3, "shrinkB": 3})
    ratio_ax.annotate(f"五核：固定计划 {ratios['C(X_B)/B(X_B)'][-1]:.4f}\n重调度 {ratios['C(X_C)/B(X_B)'][-1]:.4f}",
                      xy=(5, ratios["C(X_C)/B(X_B)"][-1]), xycoords="data",
                      xytext=(.97, .92), textcoords="axes fraction",
                      ha="right", va="top", fontsize=6.8, color=INK,
                      bbox={"facecolor": "white", "edgecolor": GRID,
                            "boxstyle": "round,pad=.3", "alpha": .96},
                      arrowprops={"arrowstyle": "-", "color": AMBER, "lw": .75,
                                  "shrinkA": 3, "shrinkB": 3})
    fig.suptitle("问题三：无 Cache、固定计划 Cache 与重调度 Cache 的同核直接比较",
                 fontsize=10.8, y=1.02)
    fig.tight_layout()
    save(fig, "cache_direct_comparison")

    fig, ax = plt.subplots(figsize=(7.0, 3.55))
    for case in cases:
        p = pair_index[case, 5]
        hit, miss = number(p, "c_initial_hit_bytes"), number(p, "c_initial_miss_bytes")
        x = 100 * hit / (hit + miss) if hit + miss else 0
        y = 100 * (
            1 - number(p, "c_same_plan_makespan") / number(p, "b_makespan")
        )
        ax.scatter(x, y, s=30, facecolor=TEAL if y > 1e-10 else PALE_BLUE,
                   edgecolor=INK, linewidth=.45, alpha=.83, zorder=3)
        if case in ("case_080", "case_055"):
            offset = (15, 15) if case == "case_080" else (13, -22)
            ax.annotate(case[-3:], (x, y), xytext=offset, textcoords="offset points",
                        color=INK, fontsize=8.3, fontweight="bold",
                        arrowprops={"arrowstyle": "->", "lw": .9, "color": INK},
                        bbox={"facecolor": "white", "edgecolor": GRID, "pad": 2})
    ax.axhline(0, color=INK, lw=.85, ls=(0, (3, 3)))
    decorate(ax, "同计划Cache工期改善 / %")
    ax.set_xlabel("同计划Cache读取字节命中率 / %")
    ax.set_title(f"五核{case_count}图：命中并不等于关键路径收益", fontsize=10.5)
    fig.tight_layout()
    save(fig, "cache_hit_gain_scatter")

    # Five-core hardware-effect counts and the gain distribution within improved cases.
    five_pairs = [pair_index[case, 5] for case in cases]
    improved = [p for p in five_pairs if number(p, "s_hw") > 1 + 1e-12]
    unchanged = [p for p in five_pairs if math.isclose(number(p, "s_hw"), 1.0, abs_tol=1e-12)]
    degraded = [p for p in five_pairs if number(p, "s_hw") < 1 - 1e-12]
    five_core_pair_count = len(five_pairs)
    category_counts = (len(improved), len(unchanged), len(degraded))
    assert sum(category_counts) == five_core_pair_count
    improvement_percent = [
        100 * (
            1 - number(p, "c_same_plan_makespan") / number(p, "b_makespan")
        )
        for p in improved
    ]
    gain_bins = [(0, 1, "<1%"), (1, 3, "1—3%"), (3, 5, "3—5%"),
                 (5, 10, "5—10%"), (10, float("inf"), "≥10%")]
    gain_counts = [sum(lower < value <= upper for value in improvement_percent)
                   for lower, upper, _ in gain_bins]
    assert sum(gain_counts) == len(improved)
    summary["cache_pie"] = {"cores": 5, "improved": len(improved),
                             "unchanged": len(unchanged), "degraded": len(degraded),
                             "gain_bins": {label: count for (_, _, label), count in zip(gain_bins, gain_counts)},
                             "improved_gain_mean_percent": st.mean(improvement_percent),
                             "improved_gain_median_percent": st.median(improvement_percent)}
    fig, (category_ax, detail_ax) = plt.subplots(
        1, 2, figsize=(7.2, 3.45), gridspec_kw={"width_ratios": [1, 1.22]})
    category_bars = category_ax.bar(["改善", "持平", "退化"], category_counts,
                                    color=[PALE_TEAL, PALE_BLUE, PALE_RED],
                                    edgecolor=EDGE, linewidth=1.05, width=.62, zorder=3)
    decorate(category_ax, "图数")
    category_ax.set_ylim(0, max(category_counts) * 1.22)
    category_ax.set_title(f"五核同计划硬件效应（{five_core_pair_count}图）",
                          fontsize=9.5, color=INK)
    add_value_labels(category_ax, category_bars, lambda value: f"{value:.0f}",
                     offset=4, fontsize=8.5)
    detail_labels = [label for _, _, label in gain_bins]
    y = list(range(len(detail_labels)))
    bars = detail_ax.barh(y, gain_counts, color=[PALE_TEAL, PALE_BLUE, PALE_AMBER,
                                                 PALE_AMBER, PALE_RED],
                          edgecolor=EDGE, linewidth=1.05,
                          zorder=3)
    detail_ax.set_yticks(y, detail_labels)
    detail_ax.invert_yaxis()
    detail_ax.set_xlabel(f"改善图数（共{len(improved)}图）", color=INK)
    detail_ax.set_title("改善图的工期降幅", fontsize=9.5, color=INK, pad=8)
    decorate(detail_ax)
    detail_ax.grid(axis="x", color=GRID, linewidth=.6, linestyle=(0, (3, 3)))
    detail_ax.grid(axis="y", visible=False)
    detail_ax.set_xlim(0, max(gain_counts) * 1.28)
    for bar, count in zip(bars, gain_counts):
        detail_ax.annotate(f"{count}", (bar.get_width(), bar.get_y() + bar.get_height() / 2),
                           xytext=(4, 0), textcoords="offset points", va="center",
                           fontsize=8, color=INK)
    fig.subplots_adjust(left=.09, right=.97, top=.87, bottom=.22, wspace=.37)
    fig.text(.09, .07,
             f"改善图工期降幅：均值 {st.mean(improvement_percent):.2f}%，"
             f"中位数 {st.median(improvement_percent):.2f}%",
             fontsize=8, color=INK)
    save(fig, "cache_hw_effect_pie")
    variants = ["cache_capacity_half", "cache_capacity_double", "cache_bandwidth_half", "cache_bandwidth_double"]
    names = ["容量减半", "容量加倍", "带宽减半", "带宽加倍"]
    sensitivity_cases = sorted({r["case"] for r in sensitivity})
    sensitivity_case_count = len(sensitivity_cases)
    assert sensitivity_case_count > 0
    for variant in variants:
        group = [sensitivity_index[case, variant, "fixed_plan"] for case in
                 sorted({r["case"] for r in sensitivity if r["variant"] == variant})]
        assert len(group) == sensitivity_case_count
        optimized = [sensitivity_index[r["case"], variant, "reoptimized"] for r in group]
        assert all(number(f, "default_same_plan_makespan") ==
                   number(pair_index[f["case"], 5], "c_same_plan_makespan") for f in group)
        failures = [r for r in sensitivity_failures if r["variant"] == variant]
        total_hit = sum(number(r, "cache_hit_bytes") for r in group)
        total_read = total_hit + sum(number(r, "cache_miss_bytes") for r in group)
        summary["sensitivity"].append({"variant": variant,
             "fixed_makespan_mean": st.mean(number(r, "variant_makespan") for r in group),
             "reoptimized_makespan_mean": st.mean(number(r, "variant_makespan") for r in optimized),
             "fixed_change_percent": st.mean(100 * (number(r, "variant_makespan") /
                 number(r, "default_same_plan_makespan") - 1) for r in group),
             "fixed_hit_mean": st.mean(number(r, "cache_hit_rate") for r in group),
             "fixed_hit_weighted": total_hit / total_read,
             "reoptimized_hit_mean": st.mean(number(r, "cache_hit_rate") for r in optimized),
             "changed_count": sum(r["changed_from_B_plan"] == "True" for r in optimized),
             "failure_alternatives": len(failures)})
    fig, ax = plt.subplots(figsize=(6.9, 3.15))
    vals = [r["fixed_change_percent"] for r in summary["sensitivity"]]
    bars = ax.bar(names, vals, color=[PALE_BLUE, PALE_TEAL, PALE_AMBER, PALE_RED],
                  edgecolor=EDGE, linewidth=1.05, width=.56, zorder=3)
    ax.axhline(0, color="#646C70", linewidth=.9)
    decorate(ax, "相对默认配置的逐图工期变化 / %")
    ax.set_title(f"{sensitivity_case_count}张代表图：固定计划的参数响应", fontsize=10)
    ax.tick_params(axis="x", labelsize=8.5)
    margin = max(abs(v) for v in vals) * .28
    ax.set_ylim(min(0, min(vals)) - margin, max(0, max(vals)) + margin)
    for bar, value in zip(bars, vals):
        ax.annotate(f"{value:+.3f}%", (bar.get_x() + bar.get_width()/2, value),
                    xytext=(0, 3 if value >= 0 else -14), textcoords="offset points",
                    ha="center", fontsize=7.5, color=INK)
    fig.tight_layout()
    save(fig, "sensitivity_makespan")
    fig, ax = plt.subplots(figsize=(6.9, 3.15))
    bars = ax.bar(names, [100 * r["fixed_hit_mean"] for r in summary["sensitivity"]],
                  color=[PALE_BLUE, PALE_TEAL, PALE_AMBER, PALE_RED],
                  edgecolor=EDGE, linewidth=1.05, width=.56, zorder=3)
    decorate(ax, "逐图字节命中率均值 / %")
    ax.set_title(f"{sensitivity_case_count}张代表图：固定计划的Cache命中", fontsize=10)
    ax.tick_params(axis="x", labelsize=8.5)
    add_value_labels(ax, bars, lambda value: f"{value:.2f}%", offset=2.5,
                     fontsize=7.5)
    fig.tight_layout()
    save(fig, "sensitivity_hit")

    response = [[100 * (number(sensitivity_index[case, variant, "fixed_plan"], "variant_makespan") /
                        number(sensitivity_index[case, variant, "fixed_plan"], "default_same_plan_makespan") - 1)
                 for variant in variants] for case in sensitivity_cases]
    summary["sensitivity_response"] = dict(zip(sensitivity_cases, response))
    plot_sensitivity_case_heatmap(response, sensitivity_cases)
    selected_tables = []
    cache_tables = []
    for k in range(1, 6):
        selected_body, cache_body = [], []
        for case in cases:
            selected_row = [case[-3:]]
            for scene in "ABC":
                r = effective_index[case, k, scene]
                speed = 1 if scene in "AB" and k == 1 else number(r, "speedup_vs_baseline")
                selected_row += [f'{int(number(r, "final_makespan"))}/{speed:.3f}',
                                 str(int(number(r, "final_added_copy_bytes")))]
            selected_body.append(selected_row)
            p = pair_index[case, k]
            hit = number(p, "c_initial_hit_bytes")
            miss = number(p, "c_initial_miss_bytes")
            final_hit = number(p, "c_final_hit_bytes")
            final_miss = number(p, "c_final_miss_bytes")
            cache_body.append([case[-3:], str(int(number(p, "b_makespan"))),
                               str(int(number(p, "c_same_plan_makespan"))), str(int(number(p, "c_final_makespan"))),
                               f'{number(p, "s_hw"):.4f}', f'{number(p, "s_adapt"):.4f}',
                               f'{number(p, "s_opt"):.4f}',
                               f'{100*hit/(hit+miss) if hit+miss else 0:.2f}',
                               f'{100*final_hit/(final_hit+final_miss) if final_hit+final_miss else 0:.2f}'])
        selected_tables.append(latex_table(f"{k}核三问逐例工期/加速比与额外搬运（{case_count}图）", f"tab:detail-{k}",
                 ["图", "$T_A/S_A$", "$D_A$/B", "$T_B/S_B$", "$D_B$/B", "$T_C/S_C$", "$D_C$/B"], selected_body))
        cache_tables.append(latex_table(f"{k}核Cache配对（{pair_count // len(core_values)}图）", f"tab:cache-detail-{k}",
                 ["图", "$T_B$", "$T_C(X_B)$", "$T_C(X_C)$", "$S_{hw}$", "$S_{ad}$", "$S_{opt}$", "$C(X_B)$命中/\\%", "$C(X_C)$命中/\\%"], cache_body))
    if not args.figures_only:
        (GEN / "selected_tables.tex").write_text("\n".join(selected_tables), encoding="utf-8")
        (GEN / "cache_tables.tex").write_text("\n".join(cache_tables), encoding="utf-8")
    sensitivity_body = []
    for r in sorted((r for r in sensitivity if r["mode"] == "fixed_plan"),
                    key=lambda r: (r["case"], r["variant"])):
        opt = sensitivity_index[r["case"], r["variant"], "reoptimized"]
        failed = sum(f["case"] == r["case"] and f["variant"] == r["variant"]
                     for f in sensitivity_failures)
        sensitivity_body.append([r["case"][-3:],
            {"cache_capacity_half":"容量/2", "cache_capacity_double":"容量×2",
             "cache_bandwidth_half":"带宽/2", "cache_bandwidth_double":"带宽×2"}[r["variant"]],
            str(int(number(r, "variant_makespan"))),
            str(int(number(opt, "variant_makespan"))),
            f'{100*number(r,"cache_hit_rate"):.2f}', str(failed)])
    if not args.figures_only:
        (GEN / "sensitivity_table.tex").write_text(latex_table(f"{sensitivity_case_count}张代表图的Cache参数敏感性", "tab:sensitivity-detail",
            ["图", "参数", "固定计划/周期", "重优化/周期", "固定命中/\\%", "失败候选"], sensitivity_body), encoding="utf-8")
    (GEN / "final_evidence_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"coverage": summary["coverage"], "five_core": {s: summary["by_scene"][s][4] for s in "ABC"},
                      "cache_five": summary["cache"][4], "sensitivity": summary["sensitivity"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
