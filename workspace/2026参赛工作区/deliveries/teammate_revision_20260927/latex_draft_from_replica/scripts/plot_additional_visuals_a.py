"""Plot two evidence-bound views of the frozen B/C Cache comparisons."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.lines import Line2D

from evidence_data import assert_declared_count, resolve_data_dir


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = resolve_data_dir(ROOT, None, "data/final_idea_v2")
SOURCE = DATA_DIR / "cache_pairs.csv"
FIGURES = ROOT / "figures"
BLUE = "#215A82"
TEAL = "#2F8B78"
AMBER = "#E09A32"
INK = "#1F3345"
GRID = "#C8D4DC"
PALE = "#DCE4E8"
PANEL = "#F8FBFC"
EPS = 1e-10


def set_font() -> None:
    for name in ("PingFang SC", "Hiragino Sans GB", "STHeiti Medium", "Noto Sans CJK SC", "SimHei", "SimSun"):
        try:
            path = font_manager.findfont(name, fallback_to_default=False)
        except ValueError:
            continue
        plt.rcParams.update({
            "font.family": font_manager.FontProperties(fname=path).get_name(),
            "axes.unicode_minus": False,
            "font.size": 9,
            "font.weight": "regular",
            "axes.titleweight": "bold",
            "axes.titlecolor": INK,
            "pdf.fonttype": 42,
            "savefig.facecolor": "white",
            "axes.facecolor": PANEL,
        })
        return
    raise RuntimeError("A Chinese font is required for paper figures")


def load_pairs(data_dir: Path | None = None) -> list[dict]:
    source = (data_dir or DATA_DIR) / "cache_pairs.csv"
    with source.open(encoding="utf-8-sig", newline="") as stream:
        raw = list(csv.DictReader(stream))
    pair_count = assert_declared_count(source.parent, len(raw), "cache_pairs")
    seen: set[tuple[str, int]] = set()
    pairs = []
    for row in raw:
        case, core = row["case"], int(row["cores"])
        key = (case, core)
        assert key not in seen and 1 <= core <= 5
        seen.add(key)
        assert row["b_plan_sha256"] == row["c_initial_plan_sha256"]
        b_time = float(row["b_makespan"])
        c_same = float(row["c_initial_makespan"])
        c_final = float(row["c_final_makespan"])
        # The hardware-effect view is tied to C(X_B), not to the final
        # rescheduled C(X_C) plan.  The repaired CSV retains both fields.
        hit = float(row["c_initial_hit_bytes"])
        miss = float(row["c_initial_miss_bytes"])
        assert min(b_time, c_same, c_final) > 0
        assert hit >= 0 and miss >= 0
        hit_rate = hit / (hit + miss) if hit + miss else 0.0
        assert math.isclose(hit_rate, float(row["c_initial_hit_rate"]), abs_tol=1e-9)
        assert math.isclose(b_time / c_same, float(row["s_hw"]), abs_tol=1e-9)
        assert math.isclose(c_same / c_final, float(row["s_adapt"]), abs_tol=1e-9)
        assert math.isclose(b_time / c_final, float(row["s_opt"]), abs_tol=1e-9)
        assert c_same <= b_time + EPS and c_final <= c_same + EPS
        pairs.append({
            "case": case,
            "core": core,
            "hit_percent": 100 * hit_rate,
            "gain_percent": 100 * (1 - c_same / b_time),
            "hardware": c_same < b_time - EPS,
            "adaptation": c_final < c_same - EPS,
            "overall": c_final < b_time - EPS,
        })
    assert len(seen) == pair_count
    case_count = len({p["case"] for p in pairs})
    cores = sorted({p["core"] for p in pairs})
    assert all(sum(p["core"] == core for p in pairs) == case_count for core in cores)
    return pairs


def save(fig: plt.Figure, stem: str) -> None:
    FIGURES.mkdir(exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(FIGURES / f"{stem}.{ext}", dpi=280 if ext == "png" else None,
                    bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def plot_coverage_bars(pairs: list[dict]) -> dict[str, list[int]]:
    case_count = len({p["case"] for p in pairs})
    cores = sorted({p["core"] for p in pairs})
    assert cores == list(range(1, len(cores) + 1))
    labels = ("hardware", "adaptation", "overall")
    counts = {label: [sum(p["core"] == core and p[label] for p in pairs)
                      for core in cores] for label in labels}
    assert all(len(values) == len(cores) for values in counts.values())
    fig, ax = plt.subplots(figsize=(7.2, 3.35))
    x = np.arange(len(cores))
    width = .23
    for offset, label, title, color in (
        (-width, "hardware", "同计划硬件", BLUE),
        (0, "adaptation", "C 内调度适配", AMBER),
        (width, "overall", "综合改善", TEAL),
    ):
        values = [100 * count / case_count for count in counts[label]]
        bars = ax.bar(x + offset, values, width=width, label=title,
                      color=color, edgecolor="white", linewidth=.7, zorder=3)
        ax.bar_label(bars, labels=[f"{value:.0f}" for value in values],
                     padding=2, fontsize=7.2, color=INK)
    ax.set_ylim(0, max(max(values) for values in counts.values()) * 120 / case_count)
    ax.set_xticks(x, [f"{core} 核" for core in cores])
    ax.set_ylabel("工期严格缩短的图占比 / %", color=INK)
    ax.set_title(f"同核 {case_count} 图的 Cache 收益覆盖率", color=INK, fontsize=10.5)
    ax.grid(axis="y", color=GRID, linestyle=(0, (3, 3)), linewidth=.75)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(colors=INK)
    ax.legend(loc="upper left", ncol=3, frameon=False, fontsize=8.1)
    fig.tight_layout()
    save(fig, "cache_effect_coverage_radar")
    return counts


def plot_hit_gain_facets(pairs: list[dict]) -> dict[str, int]:
    beneficial = [p for p in pairs if p["hardware"]]
    hit_unchanged = [p for p in pairs if p["hit_percent"] > 0 and not p["hardware"]]
    no_hit = [p for p in pairs if p["hit_percent"] == 0]
    counts = {"beneficial": len(beneficial), "hit_unchanged": len(hit_unchanged),
              "no_hit": len(no_hit)}
    assert sum(counts.values()) == len(pairs)
    assert all(not p["hardware"] for p in no_hit)

    cores = sorted({p["core"] for p in pairs})
    assert len(cores) == 5
    no_hit_by_core = Counter(p["core"] for p in no_hit)
    fig, axes = plt.subplots(2, 3, figsize=(7.5, 4.8), sharex=True, sharey=True)
    for ax, core in zip(axes.flat, cores):
        improved = [p for p in beneficial if p["core"] == core]
        unchanged = [p for p in hit_unchanged if p["core"] == core]
        ax.scatter([p["hit_percent"] for p in improved],
                   [p["gain_percent"] for p in improved], s=19, color=TEAL,
                   edgecolors="white", linewidths=.35, alpha=.8, zorder=3)
        ax.scatter([p["hit_percent"] for p in unchanged],
                   [p["gain_percent"] for p in unchanged], s=19,
                   facecolors="white", edgecolors=AMBER, linewidths=.8,
                   alpha=.85, zorder=3)
        ax.scatter([0], [0], s=28, color=PALE, edgecolors=INK,
                   linewidths=.6, zorder=4)
        ax.text(.97, .93, f"零命中 {no_hit_by_core[core]} 图",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=7.2, color=INK)
        ax.set_title(f"{core} 核", fontsize=9.2, color=INK)
        ax.set_xlim(-3, 80)
        ax.set_ylim(-1, 29)
        ax.set_xticks([0, 20, 40, 60, 80])
        ax.set_yticks([0, 10, 20, 30])
        ax.grid(color=GRID, linewidth=.6, linestyle=(0, (3, 3)))
        ax.tick_params(labelsize=7.2, colors=INK)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    legend_ax = axes.flat[-1]
    legend_ax.axis("off")
    legend_ax.legend(handles=[
        Line2D([], [], marker="o", linestyle="none", color=TEAL,
               label=f"工期缩短 {len(beneficial)} 组"),
        Line2D([], [], marker="o", linestyle="none", markerfacecolor="white",
               markeredgecolor=AMBER, color=AMBER,
               label=f"命中但工期不变 {len(hit_unchanged)} 组"),
        Line2D([], [], marker="o", linestyle="none", color=PALE,
               markeredgecolor=INK, label=f"零命中 {len(no_hit)} 组"),
    ], loc="center left", frameon=False, fontsize=8.2)
    fig.suptitle(f"{len(pairs)} 组同计划 B/C 配对：Cache 命中与工期收益",
                 fontsize=10.5, color=INK)
    fig.supxlabel("C(X_B) 字节命中率 / %", fontsize=8.5, color=INK)
    fig.supylabel("同计划工期降幅 / %", fontsize=8.5, color=INK)
    fig.subplots_adjust(left=.10, right=.98, bottom=.14, top=.89, wspace=.24, hspace=.36)
    save(fig, "cache_hit_gain_3d")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="evidence CSV/manifest directory (defaults to PAPER_EVIDENCE_DATA or data/final_idea_v2)",
    )
    args = parser.parse_args()
    global DATA_DIR, SOURCE
    DATA_DIR = resolve_data_dir(ROOT, args.data_dir, "data/final_idea_v2")
    if not DATA_DIR.is_dir():
        raise FileNotFoundError(f"evidence data directory does not exist: {DATA_DIR}")
    SOURCE = DATA_DIR / "cache_pairs.csv"
    set_font()
    pairs = load_pairs(DATA_DIR)
    print(json.dumps({"coverage_counts": plot_coverage_bars(pairs),
                      "scatter_counts": plot_hit_gain_facets(pairs)},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
