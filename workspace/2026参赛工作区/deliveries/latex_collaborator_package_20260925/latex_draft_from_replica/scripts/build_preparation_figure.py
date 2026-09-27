"""Plot the structure of the 100 registered A-problem input graphs."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt

from build_final_evidence import (AMBER, BLUE, GRID, INK, PALE_BLUE,
                                  TEAL, decorate, save, set_font)
from graph_structure import measure

PAPER = Path(__file__).resolve().parents[1]
WORKSPACE = PAPER.parents[2]
HEALTH = WORKSPACE / "review/auto_solve/20260923_120249/02_model/data_health.csv"
RAW = WORKSPACE / "inputs/raw/A题/附件/data"


def verified_rows():
    with HEALTH.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected = {f"case_{i:03d}" for i in range(1, 101)}
    if {row["case"] for row in rows} != expected or len(rows) != 100:
        raise ValueError("The graph-profile source must contain exactly 100 unique cases")
    for row in rows:
        path = RAW / f'{row["case"]}.json'
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["sha256"]:
            raise ValueError(f'{row["case"]}: source graph hash differs from the registered profile')
        graph = json.loads(payload)
        actual = {
            "eligible_operations": sum(op["op"] not in {"COPY_IN", "COPY_OUT"}
                                       for op in graph["ops"]),
            "tensors": len(graph["tensors"]),
            "edges": len(graph["edges"]),
        }
        if row["status"] != "AI_VERIFIED" or any(int(row[key]) != value
                                                  for key, value in actual.items()):
            raise ValueError(f'{row["case"]}: profile fields do not match the original graph')
    return rows


def main():
    rows = verified_rows()
    set_font()
    operations = [int(row["eligible_operations"]) for row in rows]
    components = [int(row["components"]) for row in rows]
    spans = {row["case"]: measure(RAW / f'{row["case"]}.json') for row in rows}
    available_parallelism = [spans[row["case"]]["work_over_span"] for row in rows]
    limits = [0, 1000, 5000, 10000, 20000, float("inf")]
    counts = [sum(left <= value < right for value in operations)
              for left, right in zip(limits, limits[1:])]

    fig, (scale_ax, structure_ax) = plt.subplots(
        1, 2, figsize=(7.2, 3.15), gridspec_kw={"width_ratios": [1, 1.26]})
    bars = scale_ax.bar(range(5), counts, width=.67, color=PALE_BLUE,
                        edgecolor=BLUE, linewidth=1.15, zorder=3)
    decorate(scale_ax, "原始图数量 / 张")
    scale_ax.set_xticks(range(5), ["<1千", "1千~5千", "5千~1万", "1万~2万", "≥2万"])
    scale_ax.set_xlabel("非COPY操作数 / 个")
    scale_ax.set_ylim(0, 50)
    scale_ax.set_title("(a) 计算图规模", fontsize=10, color=INK, fontweight="bold")
    for bar in bars:
        scale_ax.annotate(str(int(bar.get_height())),
                          (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                          xytext=(0, 3), textcoords="offset points",
                          ha="center", va="bottom", fontsize=8, color=INK)

    structure_ax.scatter(components, available_parallelism, s=29, facecolor=TEAL,
                         edgecolor="white", linewidth=.5, alpha=.82, zorder=3)
    for case, offset, label in (("case_016", (8, -10), "016"),
                                ("case_062", (8, 6), "062")):
        index = next(i for i, row in enumerate(rows) if row["case"] == case)
        structure_ax.scatter(components[index], available_parallelism[index],
                             s=72, facecolor=AMBER, edgecolor=INK,
                             linewidth=.8, zorder=4)
        structure_ax.annotate(label, (components[index], available_parallelism[index]),
                              xytext=offset, textcoords="offset points",
                              fontsize=7.5, color=INK, fontweight="bold", zorder=5)
    structure_ax.set_xscale("log")
    structure_ax.set_yscale("log")
    structure_ax.set_xlim(.75, 4000)
    structure_ax.set_ylim(1, 10000)
    structure_ax.set_xticks([1, 10, 100, 1000], ["1", "10", "100", "1000"])
    structure_ax.set_yticks([1, 10, 100, 1000, 10000], ["1", "10", "100", "1000", "10000"])
    decorate(structure_ax, "总工作量/加权最长路")
    structure_ax.set_xlabel("弱连通分量数 / 个（对数轴）")
    structure_ax.set_title("(b) 依赖约束与可释放并行度", fontsize=10, color=INK, fontweight="bold")
    structure_ax.text(.55, .05,
                      "016：最长路 655140，层宽 12\n"
                      "        W/L=11.8\n"
                      "062：最长路 3120，层宽 2181\n"
                      "        W/L=965.1",
                      transform=structure_ax.transAxes, fontsize=7.2, color=INK,
                      va="bottom", bbox={"facecolor": "white", "edgecolor": GRID,
                                         "pad": 2.4}, zorder=5)
    fig.tight_layout(w_pad=1.15)
    save(fig, "graph_structure_profile")
    print(json.dumps({"graphs": len(rows), "bin_counts": counts,
                      "single_component": sum(value == 1 for value in components),
                      "over_100_components": sum(value > 100 for value in components),
                      "input_dir": str(RAW)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
