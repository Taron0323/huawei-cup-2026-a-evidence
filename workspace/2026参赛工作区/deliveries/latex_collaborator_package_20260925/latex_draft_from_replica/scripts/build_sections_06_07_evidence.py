"""Recompute graph-scale and B-scene evidence used in Sections 6 and 7."""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

from evidence_data import assert_declared_count, infer_matrix_shape, resolve_data_dir


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[2]
RAW = WORKSPACE / "inputs/raw/A题/附件/data"
DATA = resolve_data_dir(ROOT, None, "data/audited_20260924")
AUDIT_PACKAGE = WORKSPACE / "2026华为杯idea冻结工作区/paper/结果核验与论文填充包_20260924"
FIGURES = ROOT / "figures"
INK = "#1F3345"
GRID = "#C8D4DC"
BLUE = "#215A82"
TEAL = "#2F8B78"
AMBER = "#E09A32"
RED = "#D45555"
PANEL = "#F8FBFC"

sys.path.insert(0, str(ROOT / "support/experiment/src"))
from huawei_code.graph import _compute_ops, _tensor_links, weak_components  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def graph_statistics(expected_cases: tuple[str, ...] | None = None) -> dict:
    files = sorted(RAW.glob("case_???.json"))
    actual_cases = tuple(path.stem for path in files)
    if expected_cases is not None:
        assert actual_cases == expected_cases, "raw graph case coverage differs from main-results CSV"
    samples = []
    source_hashes = []
    for number, path in enumerate(files, 1):
        assert path.name == f"case_{number:03d}.json"
        raw = path.read_bytes()
        graph = json.loads(raw)
        ops = _compute_ops(graph)
        *_, preds, succs = _tensor_links(graph)
        components = weak_components(set(ops), preds, succs)
        samples.append({
            "case": path.stem,
            "compute_ops": len(ops),
            "tensors": len(graph["tensors"]),
            "edges": len(graph["edges"]),
            "weak_components": len(components),
            "largest_component": max(map(len, components)),
        })
        source_hashes.append(hashlib.sha256(raw).hexdigest())
    measures = ("compute_ops", "tensors", "edges", "weak_components", "largest_component")
    summary = {
        key: {
            "min": min(row[key] for row in samples),
            "median": st.median(row[key] for row in samples),
            "max": max(row[key] for row in samples),
            "sum": sum(row[key] for row in samples),
        }
        for key in measures
    }
    summary["graphs_over_20000_compute_ops"] = sum(row["compute_ops"] > 20000 for row in samples)
    summary["source_hash_list_sha256"] = hashlib.sha256("\n".join(source_hashes).encode()).hexdigest()
    summary["samples"] = samples
    return summary


def b_copy_statistics() -> tuple[dict, dict[tuple[str, int, str], dict[str, str]]]:
    rows = read_csv(DATA / "main_results.csv")
    shape = infer_matrix_shape(rows)
    main_count = int(shape["main_rows"])
    cases = tuple(shape["cases"])
    cores = tuple(shape["cores"])
    scenes = tuple(shape["scenes"])
    assert_declared_count(DATA, main_count, "main_rows")
    keys = [(r["case"], int(r["cores"]), r["scene"]) for r in rows]
    assert len(rows) == main_count and len(set(keys)) == main_count
    assert scenes == ("A", "B", "C")
    by_key = dict(zip(keys, rows))
    measures = {
        "original_graph_copy_bytes": "final_original_graph_copy_bytes",
        "partition_added_copy_bytes": "final_partition_added_copy_bytes",
        "spill_added_copy_bytes": "final_spill_added_copy_bytes",
        "scheduled_copy_bytes": "final_scheduled_copy_bytes",
        "added_copy_bytes": "final_added_copy_bytes",
    }
    summary = {}
    for core in cores:
        group = [by_key[(case, core, "B")] for case in cases]
        totals = {name: sum(int(r[field]) for r in group) for name, field in measures.items()}
        for row in group:
            orig, structure, spill, scheduled, added = (int(row[measures[name]]) for name in measures)
            assert scheduled == orig + structure + spill, (row["case"], cores, "scheduled")
            assert added == structure + spill, (row["case"], cores, "added")
            assert row["formal_matrix"] == "True"
        summary[str(core)] = {
            "cases": len(group),
            "nonzero_spill_cases": sum(int(r["final_spill_added_copy_bytes"]) > 0 for r in group),
            "mean_mib": {name: totals[name] / len(group) / 2**20 for name in measures},
            "total_bytes": totals,
        }
    original_totals = {summary[str(core)]["total_bytes"]["original_graph_copy_bytes"] for core in cores}
    assert len(original_totals) == 1
    return summary, by_key


def plot_official_timeline(by_key: dict) -> dict:
    target_case = "case_055" if ("case_055", 5, "B") in by_key else sorted(by_key)[0][0]
    target_core = 5 if (target_case, 5, "B") in by_key else sorted({key[1] for key in by_key if key[0] == target_case})[-1]
    row = by_key[(target_case, target_core, "B")]
    sources = read_csv(DATA / "result_sources.csv")
    source = next(r for r in sources if (r["case"], int(r["cores"]), r["scene"]) ==
                  (target_case, target_core, "B"))
    path = Path(source["final_result_path"])
    if not path.is_absolute():
        candidates = (DATA / path, AUDIT_PACKAGE / path, WORKSPACE / path)
        path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    result = json.loads(path.read_text(encoding="utf-8"))
    makespan = int(row["final_makespan"])
    assert int(result["makespan"]) == makespan
    assert result["scene"] == "B" and result["num_cores"] == target_core

    for name in ("PingFang SC", "Hiragino Sans GB", "STHeiti Medium", "Noto Sans CJK SC", "SimHei", "SimSun"):
        try:
            font_path = font_manager.findfont(name, fallback_to_default=False)
            plt.rcParams.update({"font.family": font_manager.FontProperties(fname=font_path).get_name(),
                                 "axes.unicode_minus": False, "font.size": 9,
                                 "font.weight": "regular", "axes.titleweight": "bold",
                                 "axes.titlecolor": INK, "pdf.fonttype": 42,
                                 "savefig.facecolor": "white", "axes.facecolor": PANEL})
            break
        except ValueError:
            continue
    else:
        raise RuntimeError("A Chinese plotting font is required")

    copy_colors = {"COPY_IN": BLUE, "COPY_OUT": AMBER}
    ink, grid = INK, GRID
    fig, (ax_tasks, ax_ddr) = plt.subplots(
        2, 1, figsize=(8.25, 4.35), sharex=True,
        gridspec_kw={"height_ratios": [2.5, 1], "hspace": 0.11})
    events = defaultdict(int)
    counts = defaultdict(int)
    task_ends = []
    for core in result["per_core_timeline"]:
        core_id = int(core["core_id"])
        for task in core["tasks"]:
            start, end = int(task["start"]), int(task["end"])
            assert 0 <= start < end <= makespan
            ax_tasks.hlines(core_id, start, end, color="#DCEAF0", linewidth=12, zorder=1)
            task_ends.append(end)
        for op in core["ops"]:
            if op["op"] not in copy_colors:
                continue
            start, end = int(op["start"]), int(op["end"])
            assert 0 <= start < end <= makespan
            y = core_id + (0.16 if op["op"] == "COPY_IN" else -0.16)
            ax_tasks.hlines(y, start, end, color=copy_colors[op["op"]], linewidth=2.25, alpha=.9, zorder=3)
            if op["op"] == "COPY_OUT":
                ax_tasks.scatter(start, y, s=7, color=copy_colors["COPY_OUT"],
                                 marker="D", linewidths=0, zorder=4)
            events[start] += 1
            events[end] -= 1
            counts[op["op"]] += 1
    assert max(task_ends) == makespan
    times = sorted(set(events) | {0, makespan})
    active, levels = 0, []
    for time in times:
        active += events[time]
        assert active >= 0
        levels.append(active)
    assert active == 0
    ax_ddr.step(times, levels, where="post", color=TEAL, linewidth=1.75)
    ax_ddr.fill_between(times, levels, step="post", color="#DCEFE9", alpha=.75)
    max_active = max(levels)

    ax_tasks.set_yticks(range(5), [f"核{k}" for k in range(5)])
    ax_tasks.set_ylim(4.65, -0.65)
    ax_tasks.set_ylabel("核级任务与数据搬运")
    ax_ddr.set_ylabel("在途 COPY 数")
    ax_ddr.set_xlabel("官方事件时间 / 周期")
    ax_ddr.set_ylim(0, max_active + 1.2)
    for ax in (ax_tasks, ax_ddr):
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color(ink)
        ax.tick_params(colors=ink, length=3)
        ax.grid(axis="x", color=grid, linestyle=(0, (3, 3)), linewidth=.65)
        ax.axvline(makespan, color="#B94D51", linestyle=(0, (4, 3)), linewidth=1)
        ax.set_xlim(0, makespan * 1.02)
    handles = [
        Line2D([0], [0], color="#DCEAF0", linewidth=8, label="任务区间"),
        Line2D([0], [0], color=copy_colors["COPY_IN"], linewidth=2.5, label="输入搬运"),
        Line2D([0], [0], color=copy_colors["COPY_OUT"], linewidth=2.5,
               marker="D", markersize=4, label="输出搬运"),
    ]
    legend = ax_tasks.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, 1.19),
                             ncol=3, frameon=True, fontsize=8)
    legend.get_frame().set_edgecolor("#A6B7C1")
    legend.get_frame().set_boxstyle("round,pad=0.32,rounding_size=0.10")
    legend.get_frame().set_facecolor("white")
    ax_tasks.text(makespan, 4.58, "完工", ha="right", va="bottom", color="#B94D51", fontsize=8)
    fig.subplots_adjust(left=.12, right=.98, bottom=.13, top=.86)
    FIGURES.mkdir(exist_ok=True)
    stem = FIGURES / "b_case055_official_timeline"
    fig.savefig(stem.with_suffix(".pdf"))
    fig.savefig(stem.with_suffix(".png"), dpi=220)
    plt.close(fig)
    return {"case": target_case, "cores": target_core, "scene": "B", "candidate": row["final_candidate"],
            "makespan_cycles": makespan, "task_count": len(task_ends),
            "copy_op_count": dict(counts), "max_concurrent_copy": max_active,
            "source_result": str(path), "source_result_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="evidence CSV/manifest directory (defaults to PAPER_EVIDENCE_DATA or data/audited_20260924)",
    )
    args = parser.parse_args(argv)
    global DATA
    DATA = resolve_data_dir(ROOT, args.data_dir, "data/audited_20260924")
    if not DATA.is_dir():
        raise FileNotFoundError(f"evidence data directory does not exist: {DATA}")
    report = {"graph_inputs": {}}
    b_copy, by_key = b_copy_statistics()
    expected_cases = tuple(sorted({key[0] for key in by_key}))
    report["graph_inputs"] = graph_statistics(expected_cases)
    report["b_copy"] = b_copy
    report["official_timeline"] = plot_official_timeline(by_key)
    destination = DATA / "sections_06_07_evidence.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(destination)
    print(json.dumps({"graph_inputs": {k: v for k, v in report["graph_inputs"].items() if k != "samples"},
                      "b_copy": report["b_copy"], "official_timeline": report["official_timeline"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
