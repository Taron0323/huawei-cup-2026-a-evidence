"""Render A results; all plotted arrays are exported alongside the figures."""

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src/a_solver"))
from run_batch import sha, save_json, write_csv

LABELS = {"balanced_greedy": "Topological balance", "component_aware": "Component-local",
          "component_packed": "Component packing", "portfolio": "Evaluated portfolio"}
COLORS = ["#555555", "#1b9e77", "#d95f02", "#377eb8"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.analysis = args.analysis.resolve()
    args.runs = args.runs.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "svg.fonttype": "none"})
    summary = pd.read_csv(args.analysis / "summary.csv")
    selected = pd.read_csv(args.analysis / "selected_metrics.csv")
    cache = pd.read_csv(args.analysis / "cache_summary.csv")
    records = []

    def finish(fig, name, data, caption):
        fig.tight_layout()
        data_path = args.output / f"{name}.csv"
        data.to_csv(data_path, index=False)
        for suffix in ("pdf", "png"):
            path = args.output / f"{name}.{suffix}"
            fig.savefig(path, dpi=170, metadata={"CreationDate": None, "ModDate": None} if suffix == "pdf" else None)
            records.append({"figure_id": name, "caption": caption,
                "result_file": str(data_path.relative_to(ROOT)), "result_sha256": sha(data_path),
                "code_file": str(Path(__file__).relative_to(ROOT)), "code_sha256": sha(__file__),
                "figure_file": str(path.relative_to(ROOT)), "figure_sha256": sha(path),
                "run_id": args.runs.name, "paper_location": name, "visual_review": "PENDING", "status": "COMPUTED"})
        plt.close(fig)

    for problem in (1, 2):
        fig, ax = plt.subplots(figsize=(6.9, 3.8))
        data = summary[summary.problem == problem]
        for i, (algorithm, label) in enumerate(LABELS.items()):
            sub = data[data.algorithm == algorithm]
            ax.plot(sub.cores, sub.mean_speedup, marker=["o", "s", "^", "D"][i],
                    linewidth=1.7, label=label, color=COLORS[i])
        ax.set(xlabel="Number of cores", ylabel="Mean speedup over one core", xticks=range(1, 6), ylim=(0, None))
        ax.grid(alpha=.22)
        ax.legend(fontsize=8, frameon=False)
        finish(fig, f"speedup_q{problem}", data, f"问题{problem}：100个用例平均加速比，固定官方配置")
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    axes[0].plot(cache.cores, cache.same_plan_no_l2_makespan / 1e6, "o-", color=COLORS[0], label="No L2, same plan")
    axes[0].plot(cache.cores, cache.same_plan_l2_makespan / 1e6, "s-", color=COLORS[3], label="Read-only L2")
    axes[0].set(xlabel="Number of cores", ylabel="Mean makespan (million cycles)", xticks=range(1, 6))
    axes[1].plot(cache.cores, cache.same_plan_cache_speedup, "o-", label="Same plan", color=COLORS[1])
    axes[1].plot(cache.cores, cache.independently_selected_speedup, "s--", label="Each configuration optimized", color=COLORS[2])
    axes[1].set(xlabel="Number of cores", ylabel="Mean no-L2 / L2 ratio", xticks=range(1, 6))
    for ax in axes:
        ax.legend(frameon=False, fontsize=8)
        ax.grid(alpha=.22)
    finish(fig, "cache_comparison", cache, "问题3：同一方案下Cache收益及分别选优的对照")

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    data = selected[selected.cores == 5]
    for problem, color in zip((1, 2, 3), COLORS[1:]):
        sub = data[data.problem == problem]
        axes[0].plot(sorted(sub.speedup_singlecore), [i / len(sub) for i in range(1, len(sub) + 1)],
                     label=f"Problem {problem}", color=color)
    axes[0].set(xlabel="Five-core speedup", ylabel="Fraction of cases", ylim=(0, 1))
    movement = summary[(summary.cores == 5) & (summary.algorithm == "portfolio")]
    axes[1].bar(movement.problem, movement.mean_added_copy_bytes / 1e6, color=COLORS[1:])
    axes[1].set(xlabel="Problem", ylabel="Mean added DDR traffic (MB)", xticks=[1, 2, 3])
    axes[0].legend(frameon=False)
    finish(fig, "case_distribution", data, "五核逐例加速比分布与平均额外DDR搬运")

    blocks = []
    for folder in ("sensitivity_block50", "smoke_v1", "sensitivity_block200"):
        frame = pd.read_csv(args.runs / folder / "metrics.csv")
        blocks.append(frame[frame.algorithm == "component_packed"])
    block = pd.concat(blocks, ignore_index=True)
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.3))
    normalized = []
    for problem, ax in zip((1, 2, 3), axes):
        for case, group in block[block.problem == problem].groupby("case"):
            group = group.sort_values("block_size").copy()
            ref = group[group.block_size == 100].makespan.iloc[0]
            group["relative_makespan"] = group.makespan / ref
            normalized.append(group)
            ax.plot(group.block_size, group.relative_makespan, "o-", label=case[-3:])
        ax.set(title=f"Problem {problem}", xlabel="Block size (operations)", xticks=[50, 100, 200])
        ax.grid(alpha=.22)
    axes[0].set_ylabel("Makespan / block-100 makespan")
    axes[-1].legend(fontsize=7, title="Case", frameon=False)
    finish(fig, "block_sensitivity", pd.concat(normalized), "分块参数敏感性，固定4核、其他官方参数不变")

    hardware = pd.read_csv(args.runs / "cache_sensitivity_v1/metrics.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.5))
    for case, group in hardware.groupby("case"):
        ref = group[(group.capacity_bytes == 1048576) & (group.bandwidth_bytes_per_cycle == 250)].makespan.iloc[0]
        cap = group[group.bandwidth_bytes_per_cycle == 250].sort_values("capacity_bytes")
        bw = group[group.capacity_bytes == 1048576].sort_values("bandwidth_bytes_per_cycle")
        axes[0].plot(cap.capacity_bytes / 1048576, cap.makespan / ref, "o-", label=case[-3:])
        axes[1].plot(bw.bandwidth_bytes_per_cycle, bw.makespan / ref, "s-", label=case[-3:])
    axes[0].set(xlabel="L2 capacity (MiB)", ylabel="Makespan / official-config makespan")
    axes[1].set(xlabel="L2 bandwidth (bytes/cycle)", ylabel="Makespan / official-config makespan")
    for ax in axes:
        ax.legend(title="Case", frameon=False)
        ax.grid(alpha=.22)
    finish(fig, "cache_sensitivity", hardware, "独立诊断：Cache容量与带宽敏感性，不并入固定配置成绩")
    random = pd.read_csv(args.runs / "random_seeds_v1/metrics.csv")
    random_summary = random.groupby(["case", "problem"]).makespan.agg(["mean", "std", "min", "max"]).reset_index()
    random_summary.to_csv(args.analysis / "random_seed_summary.csv", index=False)
    block.to_csv(args.analysis / "block_sensitivity.csv", index=False)
    write_csv(args.output / "figure_manifest.csv", records)
    save_json(args.output / "source_manifest.json", {str(p.relative_to(ROOT)): sha(p) for p in
              [args.analysis / "summary.csv", args.analysis / "selected_metrics.csv", args.analysis / "cache_summary.csv"]})
    print(json.dumps({"figures": len(records), "output": str(args.output)}))


if __name__ == "__main__":
    main()
