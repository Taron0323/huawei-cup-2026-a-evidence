"""Render the six selected paper figures from the v7 raw final-selection data.

The script intentionally has no table or prose side effects.  It reads only
``data/v7_fast_20260927`` and writes the figure names used by the current
LaTeX source into ``figures``.  PDF, SVG and PNG are all emitted so the paper
uses the vector copy while collaborators can inspect the PNG previews.
"""

from __future__ import annotations

import csv
import random
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "v7_fast_20260927"
FIG = ROOT / "figures"

BLUE = "#1F5A80"
TEAL = "#2A8C7A"
AMBER = "#D88B22"
CORAL = "#C95050"
INK = "#1F3447"
GRID = "#C9D7DF"
PANEL = "#F7FAFB"
PALE_BLUE = "#DDEAF3"
PALE_TEAL = "#DDF0EB"
PALE_AMBER = "#F7E7C9"
PALE_CORAL = "#F5DFDF"


def read(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float:
    return float(row[key])


def set_font() -> None:
    for name in ("PingFang SC", "Hiragino Sans GB", "STHeiti Medium",
                 "Noto Sans CJK SC", "SimHei", "SimSun"):
        try:
            path = font_manager.findfont(name, fallback_to_default=False)
        except ValueError:
            continue
        plt.rcParams.update({
            "font.family": font_manager.FontProperties(fname=path).get_name(),
            "axes.unicode_minus": False,
            "font.size": 9.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        })
        return
    raise RuntimeError("No Chinese font is available for the paper figures")


def decorate(ax, ylabel: str | None = None, grid_axis: str = "y") -> None:
    ax.set_facecolor(PANEL)
    for side in ("top", "right"):
        ax.spines[side].set_color("#A6B7C0")
        ax.spines[side].set_linewidth(.8)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK)
        ax.spines[side].set_linewidth(1.0)
    ax.grid(axis=grid_axis, color=GRID, lw=.72, ls=(0, (3, 3)), zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK, labelsize=8.2, length=3, width=.75)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)
    ax.xaxis.label.set_fontweight("bold")
    ax.yaxis.label.set_fontweight("bold")
    if ylabel:
        ax.set_ylabel(ylabel, color=INK, fontweight="bold")


def legend(ax, **kwargs):
    leg = ax.legend(frameon=True, **kwargs)
    frame = leg.get_frame()
    frame.set_facecolor("white")
    frame.set_edgecolor("#A6B7C0")
    frame.set_linewidth(.8)
    frame.set_boxstyle("round,pad=.30,rounding_size=.08")
    frame.set_alpha(.96)
    for text in leg.get_texts():
        text.set_color(INK)
    return leg


def save(fig, stem: str, *aliases: str) -> None:
    FIG.mkdir(exist_ok=True)
    for name in (stem, *aliases):
        fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight", pad_inches=.07)
        fig.savefig(FIG / f"{name}.png", dpi=260, bbox_inches="tight", pad_inches=.07)
        fig.savefig(FIG / f"{name}.svg", bbox_inches="tight", pad_inches=.07)
    plt.close(fig)


def bootstrap(values: list[float], repetitions: int = 1500) -> tuple[float, float]:
    """Return the same deterministic instance-resampling interval as the paper tables."""
    rng = random.Random(20260927 + len(values))
    means = sorted(st.mean(rng.choices(values, k=len(values))) for _ in range(repetitions))
    return means[int(.025 * repetitions)], means[int(.975 * repetitions) - 1]


def speedup_figure(by: dict[tuple[str, int, str], dict[str, str]], scene: str) -> None:
    cases = sorted({key[0] for key in by})
    xs = list(range(1, 6))
    stats = []
    for k in xs:
        values = [number(by[case, k, scene], "speedup_vs_baseline") for case in cases]
        low, high = bootstrap(values)
        stats.append((st.mean(values), st.median(values), low, high))
    means = [row[0] for row in stats]
    medians = [row[1] for row in stats]
    low = [row[2] for row in stats]
    high = [row[3] for row in stats]
    span = max(high) - min(low)
    colors = {"A": (BLUE, AMBER, PALE_BLUE),
              "B": (TEAL, CORAL, PALE_TEAL),
              "C": (AMBER, BLUE, PALE_AMBER)}
    primary, secondary, band = colors[scene]
    delta = means[-1] - means[-2]
    slow = sum(number(by[case, 5, scene], "final_makespan") >
               number(by[case, 4, scene], "final_makespan") for case in cases)

    def draw(ax, xvals, means_, medians_, low_, high_, compact=False):
        decorate(ax, "对整图单核基准的加速比")
        ax.fill_between(xvals, low_, high_, color=band, alpha=.70, edgecolor="none",
                        label="均值95%实例重采样区间", zorder=1)
        ax.plot(xvals, low_, color=primary, lw=.55, alpha=.48,
                ls=(0, (2, 2)), zorder=2)
        ax.plot(xvals, high_, color=primary, lw=.55, alpha=.48,
                ls=(0, (2, 2)), zorder=2)
        ax.errorbar(xvals, means_, yerr=[[m - lo for m, lo in zip(means_, low_)],
                                         [hi - m for m, hi in zip(means_, high_)]],
                    fmt="none", ecolor=primary, elinewidth=.75, capsize=2.7,
                    alpha=.55, zorder=3)
        ax.plot(xvals, means_, "o-", color=primary, lw=2.25 if not compact else 1.95,
                ms=5.8 if not compact else 4.9, markerfacecolor="white",
                markeredgewidth=1.35, label="逐例比值均值", zorder=5)
        ax.plot(xvals, medians_, "s--", color=secondary, lw=1.60 if not compact else 1.35,
                ms=5.0 if not compact else 4.1, markerfacecolor="white",
                markeredgewidth=1.05, label="中位数", zorder=5)
        ax.axhline(1, color="#6D7C82", lw=.9, ls=(0, (3, 2)), zorder=2)
        ax.set_xticks(xvals)
        ax.set_xlabel("核数")
        ax.set_ylim(min(low) - .08 * span, max(high) + .20 * span)

    if scene == "A":
        fig, (ax, zoom) = plt.subplots(1, 2, figsize=(7.28, 3.22),
                                       gridspec_kw={"width_ratios": (2.08, 1.0)})
        draw(ax, xs, means, medians, low, high)
        legend(ax, loc="upper left", fontsize=7.9)
        # A clean connector and an independent crop keep the key 4-to-5 points readable.
        zoom_values = low[3:] + high[3:] + means[3:] + medians[3:]
        crop_low, crop_high = min(zoom_values) - .08, max(zoom_values) + .10
        ax.axvspan(3.72, 5.20, color=PALE_AMBER, alpha=.16, zorder=0)
        draw(zoom, xs[3:], means[3:], medians[3:], low[3:], high[3:], compact=True)
        zoom.set_xlim(3.72, 5.28)
        zoom.set_ylim(crop_low, crop_high)
        zoom.set_title("4→5核局部放大", fontsize=9.1, color=INK, pad=5, weight="bold")
        zoom.set_xlabel("关键区间", fontsize=7.7)
        zoom.tick_params(labelsize=7.3)
        zoom.text(.96, .06, f"均值 {means[-2]:.2f}→{means[-1]:.2f}\n"
                  f"Δ {delta:+.2f}；{slow} 图反升", transform=zoom.transAxes,
                  ha="right", va="bottom", fontsize=6.75, color=INK,
                  bbox={"facecolor": "white", "edgecolor": GRID,
                        "boxstyle": "round,pad=.30", "alpha": .96})
        zoom.legend_.remove() if zoom.legend_ else None
        fig.suptitle("问题一：100图加速比（均值、中位数与95%实例区间）",
                     fontsize=10.8, color=INK, weight="bold", y=1.02)
        fig.tight_layout(w_pad=1.35)
    elif scene == "B":
        fig, ax = plt.subplots(figsize=(7.28, 3.35))
        draw(ax, xs, means, medians, low, high)
        ax.axvspan(3.72, 5.18, color=PALE_CORAL, alpha=.25, zorder=0)
        ax.axvline(4.5, color=secondary, lw=.95, ls=(0, (3, 2)), alpha=.78, zorder=2)
        legend(ax, loc="upper left", fontsize=7.9)
        ax.annotate(f"4→5核：{means[-2]:.2f}→{means[-1]:.2f}\n"
                    f"Δ {delta:+.2f}；{slow} 张图反升",
                    xy=(5, means[-1]), xycoords="data", xytext=(.96, .13),
                    textcoords="axes fraction", ha="right", va="bottom",
                    fontsize=7.0, color=INK,
                    bbox={"facecolor": "white", "edgecolor": secondary,
                          "boxstyle": "round,pad=.36", "alpha": .96},
                    arrowprops={"arrowstyle": "-", "lw": .8, "color": secondary,
                                "shrinkA": 5, "shrinkB": 4}, zorder=7)
        fig.suptitle("问题二：100图加速比（4→5核关键拐点）",
                     fontsize=10.8, color=INK, weight="bold", y=1.01)
        fig.tight_layout()
    else:
        fig, ax = plt.subplots(figsize=(7.28, 3.35))
        draw(ax, xs, means, medians, low, high)
        legend(ax, loc="upper left", fontsize=7.9)
        # Inline focus window, with the source point and interval kept visible.
        zoom = ax.inset_axes([.59, .57, .35, .36])
        draw(zoom, xs[3:], means[3:], medians[3:], low[3:], high[3:], compact=True)
        zoom.set_xlim(3.72, 5.28)
        zoom_values = low[3:] + high[3:] + means[3:] + medians[3:]
        crop_low, crop_high = min(zoom_values) - .08, max(zoom_values) + .10
        zoom.set_ylim(crop_low, crop_high)
        zoom.set_title("4→5核", fontsize=8.0, color=INK, pad=2)
        zoom.set_xlabel("")
        zoom.set_ylabel("")
        zoom.tick_params(labelsize=6.3)
        zoom.legend_.remove() if zoom.legend_ else None
        zoom.text(.95, .06, f"Δ {delta:+.2f}\n{slow} 图反升", transform=zoom.transAxes,
                  ha="right", va="bottom", fontsize=6.3, color=INK,
                  bbox={"facecolor": "white", "edgecolor": GRID,
                        "boxstyle": "round,pad=.24", "alpha": .95})
        # The inset itself is the focus cue.  Avoid connector lines crossing
        # the fifth-core marker or leaving the figure bounding box at print
        # scale; the shared 4→5 x-range already makes the mapping explicit.
        for spine in zoom.spines.values():
            spine.set_edgecolor(secondary)
            spine.set_linewidth(.9)
        fig.suptitle("问题三：100图加速比（主图内嵌4→5核局部窗口）",
                     fontsize=10.8, color=INK, weight="bold", y=1.01)
        fig.tight_layout()
    save(fig, f"speedup_{scene}")


def cache_decomposition(pairs: list[dict[str, str]]) -> None:
    xs = list(range(1, 6))
    labels = [("s_hw", "硬件变化", BLUE, "o"),
              ("s_adapt", "调度适配", AMBER, "s"),
              ("s_opt", "综合", TEAL, "^")]
    values = {field: [st.mean(number(row, field) for row in pairs
                               if int(row["cores"]) == k) for k in xs]
              for field, *_ in labels}
    fig, ax = plt.subplots(figsize=(7.28, 3.45))
    for field, name, color, marker in labels:
        ax.plot(xs, values[field], marker + "-", color=color, lw=2.15, ms=5.4,
                markerfacecolor="white", markeredgewidth=1.1, label=name, zorder=4)
    ax.axhline(1, color="#6D7C82", lw=.8, ls=(0, (3, 2)))
    decorate(ax, "逐例比值的算术平均")
    ax.set_xticks(xs)
    ax.set_xlabel("核数")
    legend(ax, loc="upper left", ncol=3, fontsize=7.7)
    ax.set_ylim(.999, 1.041)
    # Explain the visible 4-core turning points directly on the curves.
    ax.annotate("4核：硬件效应达到峰值\n1.0164，5核回落至1.0146",
                xy=(4, values["s_hw"][3]), xycoords="data",
                xytext=(3.15, 1.037), textcoords="data", ha="left", va="top",
                fontsize=6.9, color=BLUE,
                bbox={"facecolor": "white", "edgecolor": BLUE,
                      "boxstyle": "round,pad=.28", "alpha": .96},
                arrowprops={"arrowstyle": "-", "lw": .8, "color": BLUE,
                            "shrinkA": 4, "shrinkB": 3})
    ax.annotate("4核：调度适配暂降至1.0092；\n5核恢复至1.0139，综合比值升至1.0289",
                xy=(4, values["s_adapt"][3]), xycoords="data",
                xytext=(2.65, 1.004), textcoords="data", ha="left", va="bottom",
                fontsize=6.9, color=AMBER,
                bbox={"facecolor": "white", "edgecolor": AMBER,
                      "boxstyle": "round,pad=.28", "alpha": .96},
                arrowprops={"arrowstyle": "-", "lw": .8, "color": AMBER,
                            "shrinkA": 4, "shrinkB": 3})
    fig.suptitle("问题三：同计划硬件效应、调度适配及综合比值",
                 fontsize=10.8, color=INK, weight="bold", y=1.01)
    fig.tight_layout()
    # The current section calls this file ``cache_speedup_decomposition``;
    # retain the shorter stem for older snapshots as a byte-identical alias.
    save(fig, "cache_speedup_decomposition", "cache_decomposition")


def ablation_figure(rows: list[dict[str, str]]) -> None:
    """Show the candidate-selection ablation with a compact Chinese layout."""
    xs = list(range(1, 6))
    scenes = [("A", "问题一", BLUE), ("B", "问题二", TEAL), ("C", "问题三", AMBER)]
    gains = {
        scene: [100 * st.mean(number(row, "relative_gain") for row in rows
                              if row["scene"] == scene and int(row["cores"]) == k)
                for k in xs]
        for scene, *_ in scenes
    }
    fig, (ax, cax) = plt.subplots(
        1, 2, figsize=(7.28, 3.45), gridspec_kw={"width_ratios": (1.72, 1.0)})
    width = .30
    for offset, (scene, label, color) in zip((-width / 2, width / 2), scenes[:2]):
        bars = ax.bar([x + offset for x in xs], gains[scene], width=width,
                      color=color, alpha=.88, edgecolor="white", linewidth=.7,
                      label=label, zorder=3)
        ax.bar_label(bars, labels=[f"{v:.1f}" for v in gains[scene]],
                     padding=2, fontsize=6.2, color=INK)
    ax.axhline(0, color="#6D7C82", lw=.85)
    decorate(ax, "平均工期改善 / %")
    ax.set_xticks(xs, [f"{k}核" for k in xs])
    ax.set_xlabel("核数")
    ax.set_ylim(0, 67)
    ax.yaxis.set_major_locator(plt.MaxNLocator(6))
    legend(ax, loc="upper left", ncol=2, fontsize=7.9)
    ax.axvspan(4.58, 5.42, color=PALE_AMBER, alpha=.22, zorder=0)
    c_bars = cax.bar(xs, gains["C"], width=.54, color=AMBER, alpha=.9,
                     edgecolor="white", linewidth=.7, zorder=3)
    cax.bar_label(c_bars, labels=[f"{v:.1f}" for v in gains["C"]],
                  padding=2, fontsize=6.2, color=INK)
    cax.axhline(0, color="#6D7C82", lw=.85)
    decorate(cax, "平均工期改善 / %")
    cax.set_xticks(xs, [f"{k}核" for k in xs])
    cax.set_xlabel("核数")
    cax.set_ylim(0, 1.65)
    cax.yaxis.set_major_locator(plt.MaxNLocator(5))
    cax.set_title("问题三低幅区间", fontsize=8.7, color=INK, weight="bold", pad=5)
    cax.axvspan(4.58, 5.42, color=PALE_AMBER, alpha=.22, zorder=0)
    fig.suptitle("候选消融：初始方案到最终选择的平均工期改善（分面刻度）",
                 fontsize=10.8, color=INK, weight="bold", y=1.01)
    fig.tight_layout(w_pad=1.15)
    save(fig, "ablation_initial_vs_final")


def ab_tradeoff_figure(by: dict[tuple[str, int, str], dict[str, str]]) -> None:
    """Keep the auxiliary A/B scatter synchronized with the raw v7 matrix."""
    cases = sorted({key[0] for key in by})
    changed, same = [], []
    for case in cases:
        a, b = by[case, 5, "A"], by[case, 5, "B"]
        x = (number(b, "final_added_copy_bytes") -
             number(a, "final_added_copy_bytes")) / 2**20
        y = number(b, "final_makespan") / number(a, "final_makespan")
        (same if x == 0 and y == 1 else changed).append((case, x, y))
    fig, ax = plt.subplots(figsize=(7.05, 3.55))
    for _, x, y in changed:
        ax.scatter(x, y, s=35, facecolor=TEAL if y < 1 else AMBER,
                   edgecolor="white", linewidth=.75, alpha=.9, zorder=4)
    ax.scatter([0], [1], s=185, marker="D", facecolor=PALE_BLUE,
               edgecolor=BLUE, linewidth=1.2, zorder=5)
    ax.annotate(f"{len(same)}图两项相同", (0, 1), xytext=(11, -24),
                textcoords="offset points", fontsize=8.2, color=BLUE,
                arrowprops={"arrowstyle": "-", "color": BLUE, "lw": .9})
    for case, offset in (("case_053", (-92, -25)), ("case_055", (18, 22))):
        point = next((row for row in changed if row[0] == case), None)
        if point is not None:
            _, x, y = point
            ax.annotate(case[-3:], (x, y), xytext=offset, textcoords="offset points",
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
    ax.set_title("五核逐图：核心驻留改变搬运与工期的对应关系", fontsize=10.5,
                 color=INK, weight="bold")
    ax.text(.98, .06, "青：B更快  ·  橙：B更慢", transform=ax.transAxes,
            ha="right", fontsize=8, color=INK)
    fig.tight_layout()
    save(fig, "ab_tradeoff_scatter")


VARIANTS = [
    ("cache_capacity_half", "容量减半", BLUE, PALE_BLUE),
    ("cache_capacity_double", "容量加倍", TEAL, PALE_TEAL),
    ("cache_bandwidth_half", "带宽减半", AMBER, PALE_AMBER),
    ("cache_bandwidth_double", "带宽加倍", CORAL, PALE_CORAL),
]


def sensitivity_figures(rows: list[dict[str, str]]) -> None:
    cases = sorted({row["case"] for row in rows})
    case_labels = [case[-3:] for case in cases]
    by = {(row["variant"], row["case"]): row for row in rows}

    # Figure 11: paired fixed/reoptimized makespan trajectories for all six graphs.
    fig, axes = plt.subplots(2, 2, figsize=(7.28, 4.85), sharex=True, sharey=False)
    axes = axes.ravel()
    for ax, (variant, title, color, pale) in zip(axes, VARIANTS):
        fixed = [number(by[variant, case], "fixed_makespan") / 1e6 for case in cases]
        opt = [number(by[variant, case], "reoptimized_makespan") / 1e6 for case in cases]
        x = list(range(len(cases)))
        ax.fill_between(x, fixed, opt, color=pale, alpha=.65, zorder=1)
        for xi, f, o in zip(x, fixed, opt):
            ax.plot([xi, xi], [f, o], color="#A6B7C0", lw=1.05, zorder=2)
        ax.plot(x, fixed, "o-", color=color, lw=1.8, ms=4.2,
                markerfacecolor="white", markeredgewidth=1.0, label="固定计划", zorder=3)
        ax.plot(x, opt, "D--", color=INK, lw=1.45, ms=3.6,
                markerfacecolor="white", markeredgewidth=.9, label="重优化计划", zorder=3)
        decorate(ax, "工期 / $10^6$ cycle")
        ax.set_title(title, fontsize=8.9, color=INK, weight="bold", pad=5)
        ax.set_xticks(x, case_labels)
        ax.tick_params(axis="x", labelsize=7.5)
        ax.grid(axis="x", visible=False)
        changed = sum(o < f - 1e-12 for f, o in zip(fixed, opt))
        ax.text(.96, .93, f"{changed}/6 图改变计划", transform=ax.transAxes,
                ha="right", va="top", fontsize=6.8, color=INK,
                bbox={"facecolor": "white", "edgecolor": GRID,
                      "boxstyle": "round,pad=.22", "alpha": .92})
    axes[2].set_xlabel("代表图编号")
    axes[3].set_xlabel("代表图编号")
    axes[0].legend(loc="upper left", fontsize=6.7, ncol=2, frameon=False)
    fig.suptitle("Cache扰动下六图固定计划与重优化计划的工期",
                 fontsize=11.0, color=INK, weight="bold", y=.995)
    fig.text(.02, .50, "每条连线表示同一代表图的重优化变化", rotation=90,
             va="center", ha="center", fontsize=7.1, color="#60757D")
    fig.tight_layout(rect=(.04, .03, 1, .95), h_pad=1.25, w_pad=1.1)
    save(fig, "sensitivity_makespan")

    # Figure 12: same layout, but with hit-rate on a common percentage scale.
    fig, axes = plt.subplots(2, 2, figsize=(7.28, 4.85), sharex=True, sharey=True)
    axes = axes.ravel()
    for ax, (variant, title, color, pale) in zip(axes, VARIANTS):
        fixed = [100 * number(by[variant, case], "fixed_cache_hit_rate") for case in cases]
        opt = [100 * number(by[variant, case], "reoptimized_cache_hit_rate") for case in cases]
        x = list(range(len(cases)))
        ax.fill_between(x, fixed, opt, color=pale, alpha=.68, zorder=1)
        for xi, f, o in zip(x, fixed, opt):
            ax.plot([xi, xi], [f, o], color="#A6B7C0", lw=1.05, zorder=2)
        ax.plot(x, fixed, "o-", color=color, lw=1.8, ms=4.2,
                markerfacecolor="white", markeredgewidth=1.0, label="固定计划", zorder=3)
        ax.plot(x, opt, "D--", color=INK, lw=1.45, ms=3.6,
                markerfacecolor="white", markeredgewidth=.9, label="重优化计划", zorder=3)
        decorate(ax, "字节命中率 / %")
        ax.set_title(title, fontsize=8.9, color=INK, weight="bold", pad=5)
        ax.set_xticks(x, case_labels)
        ax.set_ylim(-1.2, 26.5)
        ax.tick_params(axis="x", labelsize=7.5)
        ax.grid(axis="x", visible=False)
        ax.text(.96, .93, f"重优化均值 {st.mean(opt):.2f}%",
                transform=ax.transAxes, ha="right", va="top", fontsize=6.8, color=INK,
                bbox={"facecolor": "white", "edgecolor": GRID,
                      "boxstyle": "round,pad=.22", "alpha": .92})
    axes[2].set_xlabel("代表图编号")
    axes[3].set_xlabel("代表图编号")
    axes[0].legend(loc="upper left", fontsize=6.7, ncol=2, frameon=False)
    fig.suptitle("Cache扰动下六图固定计划与重优化计划的命中率",
                 fontsize=11.0, color=INK, weight="bold", y=.995)
    fig.text(.02, .50, "连线方向表示重优化后的命中率变化", rotation=90,
             va="center", ha="center", fontsize=7.1, color="#60757D")
    fig.tight_layout(rect=(.04, .03, 1, .95), h_pad=1.25, w_pad=1.1)
    # The current section requests sensitivity_hit_rate; keep sensitivity_hit
    # as a compatibility alias for older snapshots.
    save(fig, "sensitivity_hit_rate", "sensitivity_hit")


def main() -> None:
    set_font()
    main_rows = read("main_results.csv")
    assert len(main_rows) == 1500
    by = {(row["case"], int(row["cores"]), row["scene"]): row for row in main_rows}
    assert len(by) == 1500
    assert {row["status"] for row in main_rows} == {"AI_VERIFIED"}
    for scene in "ABC":
        speedup_figure(by, scene)
    pair_rows = read("cache_pairs.csv")
    assert len(pair_rows) == 500
    cache_decomposition(pair_rows)
    ablation_figure(read("candidate_effects.csv"))
    ab_tradeoff_figure(by)
    sensitivity_rows = read("sensitivity_summary.csv")
    assert len(sensitivity_rows) == 24
    assert {row["variant"] for row in sensitivity_rows} == {v[0] for v in VARIANTS}
    assert len({(row["variant"], row["case"]) for row in sensitivity_rows}) == 24
    sensitivity_figures(sensitivity_rows)
    print("rendered", ", ".join([
        "speedup_A", "speedup_B", "cache_decomposition", "speedup_C",
        "sensitivity_makespan", "sensitivity_hit_rate", "sensitivity_hit",
    ]))


if __name__ == "__main__":
    main()
