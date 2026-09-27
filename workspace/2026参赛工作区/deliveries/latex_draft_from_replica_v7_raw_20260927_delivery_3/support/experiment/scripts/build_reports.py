#!/usr/bin/env python3
"""Build full-matrix tables, ablations, cache pairs, and paper figures."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CODE_ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _roots(value: Path | list[Path]) -> list[Path]:
    return value if isinstance(value, list) else [value]


def load_main_rows(roots: Path | list[Path]) -> list[dict]:
    rows = []
    for root_index, root in enumerate(_roots(roots)):
        paths = list(root.glob("batch_*/metrics.csv")) + list(root.glob("case_*_*core/metrics.csv"))
        for path in sorted(paths):
            batch = f"root{root_index + 1}:{path.parent.name}"
            for row in read_csv(path):
                row["batch"] = batch
                row["source_root"] = str(root)
                rows.append(row)
    return rows


def load_baseline_rows(root: Path) -> dict[str, dict]:
    rows = []
    aggregate = root / "metrics.csv"
    if aggregate.exists():
        rows = read_csv(aggregate)
    else:
        for path in sorted(root.glob("batch_*/metrics.csv")):
            rows.extend(read_csv(path))
    return {row["case"]: row for row in rows if row.get("status") == "AI_VERIFIED"}


def numeric(value, default=np.nan):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def selection_info(scene_root: Path, which: str) -> tuple[dict | None, dict | None]:
    selection_path = scene_root / f"{which}_selection.json"
    if not selection_path.exists():
        return None, None
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    result_path = scene_root / "candidates" / selection["candidate"] / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
    return selection, result


def candidate_row(index: dict[tuple, dict], case: str, cores: int, scene: str, candidate: str) -> dict:
    return index.get((case, str(cores), scene, candidate), {})


def iter_scene_roots(main_root: Path, root_index: int):
    """Yield (case, cores, scene, source_batch, scene_root) for both run layouts."""
    standard_batches = [path for path in main_root.glob("batch_*") if path.is_dir()]
    for batch_path in sorted(standard_batches):
        for case_root in sorted((batch_path / "cases").glob("case_*")):
            for core_root in sorted(case_root.glob("*core"), key=lambda p: int(p.name[:-4])):
                for scene_root in sorted(core_root.iterdir()):
                    if scene_root.is_dir() and scene_root.name in {"A", "B", "C"}:
                        yield case_root.name, int(core_root.name[:-4]), scene_root.name, f"root{root_index + 1}:{batch_path.name}", scene_root
    split_jobs = [path for path in main_root.glob("case_*_*core") if path.is_dir()]
    for job_path in sorted(split_jobs):
        for case_root in sorted((job_path / "cases").glob("case_*")):
            for core_root in sorted(case_root.glob("*core"), key=lambda p: int(p.name[:-4])):
                for scene_root in sorted(core_root.iterdir()):
                    if scene_root.is_dir() and scene_root.name in {"A", "B", "C"}:
                        yield case_root.name, int(core_root.name[:-4]), scene_root.name, f"root{root_index + 1}:{job_path.name}", scene_root


def build_main_results(main_roots: list[Path], baseline_root: Path) -> tuple[list[dict], list[dict]]:
    candidate_rows = load_main_rows(main_roots)
    index = {}
    for row in candidate_rows:
        index.setdefault((row.get("case"), row.get("cores"), row.get("scene"), row.get("candidate")), row)
    baselines = load_baseline_rows(baseline_root)
    final_rows = []
    effects = []
    combinations = {}
    for root_index, main_root in enumerate(main_roots):
        for case, cores, scene, batch_name, scene_root in iter_scene_roots(main_root, root_index):
            # A complete result in an earlier root has priority over a partial
            # interrupted directory in a later root; roots are ordered by caller.
            final, final_result = selection_info(scene_root, "final")
            key = (case, cores, scene)
            if key not in combinations or (final is not None and final_result is not None):
                if key not in combinations or combinations[key][3] is False:
                    combinations[key] = (root_index, batch_name, scene_root, final is not None and final_result is not None)
    for (case, cores, scene), (root_index, batch_name, scene_root, _complete) in sorted(combinations.items()):
                    baseline = baselines.get(case, {})
                    initial, initial_result = selection_info(scene_root, "initial")
                    final, final_result = selection_info(scene_root, "final")
                    if final is None or final_result is None:
                        final_rows.append({"case": case, "cores": cores, "scene": scene, "batch": batch_name, "status": "NO_FINAL_RESULT", "baseline_makespan": baseline.get("makespan", "")})
                        continue
                    init_result = initial_result or {}
                    final_move = final_result.get("data_movement_bytes", {})
                    init_move = init_result.get("data_movement_bytes", {})
                    initial_cache = init_result.get("cache_stats") or {}
                    final_cache = final_result.get("cache_stats") or {}
                    base_ms = numeric(baseline.get("makespan"))
                    final_ms = numeric(final_result.get("makespan"))
                    initial_ms = numeric(init_result.get("makespan"))
                    row = {
                        "case": case, "cores": cores, "scene": scene, "batch": batch_name,
                        "status": "AI_VERIFIED",
                        "formal_matrix": not (scene == "A" and cores == 1),
                        "initial_candidate": initial.get("candidate", "") if initial else "",
                        "final_candidate": final.get("candidate", ""),
                        "initial_source": candidate_row(index, case, cores, scene, initial.get("candidate", "") if initial else "").get("source", ""),
                        "final_source": candidate_row(index, case, cores, scene, final.get("candidate", "")).get("source", ""),
                        "initial_plan_sha256": initial.get("plan_sha256", "") if initial else "",
                        "final_plan_sha256": final.get("plan_sha256", ""),
                        "initial_makespan": initial_ms, "final_makespan": final_ms, "baseline_makespan": base_ms,
                        "initial_added_copy_bytes": numeric(init_move.get("added_copy_bytes")), "final_added_copy_bytes": numeric(final_move.get("added_copy_bytes")),
                        "final_scheduled_copy_bytes": numeric(final_move.get("scheduled_copy_bytes")), "final_original_graph_copy_bytes": numeric(final_move.get("original_graph_copy_bytes")),
                        "final_partition_added_copy_bytes": numeric(final_move.get("partition_added_copy_bytes")), "final_spill_added_copy_bytes": numeric(final_move.get("spill_added_copy_bytes")),
                        # Keep the legacy cache_* fields as aliases for the
                        # selected final result.  The explicitly named fields
                        # preserve plan identity for C(X_B) and C(X_C).
                        "initial_cache_hit_bytes": numeric(initial_cache.get("hit_bytes"), 0), "initial_cache_miss_bytes": numeric(initial_cache.get("miss_bytes"), 0), "initial_cache_hit_rate": numeric(initial_cache.get("hit_rate"), 0),
                        "final_cache_hit_bytes": numeric(final_cache.get("hit_bytes"), 0), "final_cache_miss_bytes": numeric(final_cache.get("miss_bytes"), 0), "final_cache_hit_rate": numeric(final_cache.get("hit_rate"), 0),
                        "cache_hit_bytes": numeric(final_cache.get("hit_bytes"), 0), "cache_miss_bytes": numeric(final_cache.get("miss_bytes"), 0), "cache_hit_rate": numeric(final_cache.get("hit_rate"), 0),
                        "initial_to_final_delta_cycles": initial_ms - final_ms, "initial_to_final_relative_gain": (initial_ms - final_ms) / initial_ms if initial_ms else np.nan,
                        "speedup_vs_baseline": base_ms / final_ms if base_ms and final_ms else np.nan,
                        "initial_speedup_vs_baseline": base_ms / initial_ms if base_ms and initial_ms else np.nan,
                        "initial_profile_seconds": numeric(candidate_row(index, case, cores, scene, initial.get("candidate", "") if initial else "").get("profile_seconds")),
                        "final_profile_seconds": numeric(candidate_row(index, case, cores, scene, final.get("candidate", "")).get("profile_seconds")),
                        "final_evaluation_seconds": numeric(candidate_row(index, case, cores, scene, final.get("candidate", "")).get("evaluation_seconds")),
                    }
                    final_rows.append(row)
                    effects.append({"case": case, "cores": cores, "scene": scene, "batch": batch_name, "status": "AI_VERIFIED", "initial_candidate": row["initial_candidate"], "final_candidate": row["final_candidate"], "initial_makespan": initial_ms, "final_makespan": final_ms, "delta_cycles": row["initial_to_final_delta_cycles"], "relative_gain": row["initial_to_final_relative_gain"], "improved": bool(initial_ms > final_ms), "initial_source": row["initial_source"], "final_source": row["final_source"]})
    return final_rows, effects


def build_cache_pairs(main_rows: list[dict]) -> list[dict]:
    index = {(row["case"], int(row["cores"]), row["scene"]): row for row in main_rows if row.get("status") == "AI_VERIFIED"}
    result = []
    for (case, cores, scene), row in sorted(index.items()):
        if scene != "B":
            continue
        c = index.get((case, cores, "C"))
        if not c:
            continue
        b_ms = numeric(row["final_makespan"]); c_initial = numeric(c["initial_makespan"]); c_final = numeric(c["final_makespan"])
        initial_hit = numeric(c.get("initial_cache_hit_bytes"), 0)
        initial_miss = numeric(c.get("initial_cache_miss_bytes"), 0)
        initial_rate = numeric(c.get("initial_cache_hit_rate"), 0)
        final_hit = numeric(c.get("final_cache_hit_bytes"), 0)
        final_miss = numeric(c.get("final_cache_miss_bytes"), 0)
        final_rate = numeric(c.get("final_cache_hit_rate"), 0)
        result.append({"case": case, "cores": cores, "b_plan_sha256": row["final_plan_sha256"], "c_initial_plan_sha256": c["initial_plan_sha256"], "c_final_plan_sha256": c["final_plan_sha256"], "c_starts_from_b": row["final_plan_sha256"] == c["initial_plan_sha256"], "b_makespan": b_ms, "c_initial_makespan": c_initial, "c_same_plan_makespan": c_initial, "c_final_makespan": c_final, "s_hw": b_ms / c_initial if c_initial else np.nan, "s_adapt": c_initial / c_final if c_final else np.nan, "s_opt": b_ms / c_final if c_final else np.nan, "factor_identity_error": (b_ms / c_final) - ((b_ms / c_initial) * (c_initial / c_final)) if b_ms and c_initial and c_final else np.nan, "c_initial_hit_bytes": initial_hit, "c_initial_miss_bytes": initial_miss, "c_initial_hit_rate": initial_rate, "c_final_hit_bytes": final_hit, "c_final_miss_bytes": final_miss, "c_final_hit_rate": final_rate, "c_hit_bytes": final_hit, "c_miss_bytes": final_miss, "c_hit_rate": final_rate})
    return result


def load_static(main_roots: list[Path]) -> dict[str, dict]:
    result = {}
    for root_index, main_root in enumerate(main_roots):
        paths = list(main_root.glob("batch_*/static/case_*.json")) + list(main_root.glob("case_*_*core/static/case_*.json"))
        for path in sorted(paths):
            result.setdefault(path.stem, json.loads(path.read_text(encoding="utf-8")))
    return result


def add_lower_bounds(rows: list[dict], static: dict[str, dict], config_path: Path) -> None:
    config = {}
    section = None
    for raw in config_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line.strip("[]")
        elif line and not line.startswith("#"):
            key, value = line.split(maxsplit=1)
            config[(section, key)] = float(value)
    bandwidth = config[("bandwidth", "bandwidth")]
    for row in rows:
        view = static.get(row["case"])
        if not view or row.get("status") != "AI_VERIFIED":
            continue
        work = view.get("pipe_work", {})
        wm = float(work.get("M", work.get("MTE2", 0)))
        wv = float(work.get("V", work.get("VEC", 0)))
        path = max((float(value) for value in view.get("depth", {}).values()), default=0)
        # The official original graph copy volume is stable for a case; use the
        # successful plan's scheduled/original movement when available in the
        # candidate result summaries if a detailed field was exported.
        qmin = numeric(row.get("final_original_graph_copy_bytes"), 0)
        lb_comp = max(path, wm / row["cores"], wv / row["cores"])
        lb_io = qmin / bandwidth if bandwidth else 0
        lower = max(lb_comp, lb_io)
        row["longest_path_cycles"] = path
        row["pipe_m_cycles"] = wm
        row["pipe_v_cycles"] = wv
        row["compute_lower_bound_comp_cycles"] = lb_comp
        row["compute_lower_bound_io_cycles"] = lb_io
        row["lower_bound_cycles"] = lower
        # Keep the aggregate field for existing tables and expose both components.
        row["lower_bound_ratio"] = numeric(row.get("final_makespan"), 0) / lower if lower else np.nan


def make_figures(out: Path, rows: list[dict], effects: list[dict], pairs: list[dict]) -> None:
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([row for row in rows if row.get("status") == "AI_VERIFIED"])
    if not frame.empty:
        frame["cores"] = frame["cores"].astype(int)
        for scene in ("A", "B", "C"):
            plot = frame[(frame.scene == scene) & ((frame.cores >= 2) if scene == "A" else (frame.cores >= 1))]
            if plot.empty:
                continue
            grouped = plot.groupby("cores")["speedup_vs_baseline"].agg(["mean", "std", "count"]).reset_index()
            fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=160)
            ax.errorbar(grouped["cores"], grouped["mean"], yerr=grouped["std"].fillna(0), marker="o", capsize=3, linewidth=2)
            ax.axhline(1.0, color="#777777", linewidth=1)
            ax.set(title=f"Problem {scene}: official speedup", xlabel="cores", ylabel="baseline makespan / final makespan")
            ax.grid(alpha=.25); fig.tight_layout()
            fig.savefig(fig_dir / f"speedup_{scene}.png"); fig.savefig(fig_dir / f"speedup_{scene}.svg"); plt.close(fig)
        grouped = frame.groupby(["scene", "cores"])["initial_to_final_relative_gain"].mean().reset_index()
        fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=160)
        for scene, part in grouped.groupby("scene"):
            ax.plot(part.cores, 100 * part.initial_to_final_relative_gain, marker="o", label=scene)
        ax.axhline(0, color="#777777", linewidth=1); ax.set(title="Official initial-to-final improvement", xlabel="cores", ylabel="gain (%)"); ax.grid(alpha=.25); ax.legend(); fig.tight_layout()
        fig.savefig(fig_dir / "ablation_initial_vs_final.png"); fig.savefig(fig_dir / "ablation_initial_vs_final.svg"); plt.close(fig)
    if pairs:
        pair_frame = pd.DataFrame(pairs)
        grouped = pair_frame.groupby("cores")[["s_hw", "s_adapt", "s_opt"]].mean().reset_index()
        fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=160)
        for column, label in (("s_hw", "same plan + Cache"), ("s_adapt", "Cache adaptation"), ("s_opt", "optimized B/C")):
            ax.plot(grouped.cores, grouped[column], marker="o", label=label)
        ax.axhline(1.0, color="#777777", linewidth=1); ax.set(title="Problem 3 speedup decomposition", xlabel="cores", ylabel="ratio"); ax.grid(alpha=.25); ax.legend(); fig.tight_layout()
        fig.savefig(fig_dir / "cache_speedup_decomposition.png"); fig.savefig(fig_dir / "cache_speedup_decomposition.svg"); plt.close(fig)


def paper_summary(out: Path, rows: list[dict], effects: list[dict], pairs: list[dict], manifest: dict) -> None:
    frame = pd.DataFrame([row for row in rows if row.get("status") == "AI_VERIFIED"])
    lines = ["# A题全量实验结果摘要", "", f"主矩阵状态：`{manifest.get('status')}`，官方结果行：{manifest.get('rows', '')}。所有均值按成功官方结果的实际样本数计算。", "", "## 主矩阵速度比", "", "| 场景 | 核数 | 成功样本 | 平均速度比 | 中位速度比 |", "|---|---:|---:|---:|---:|"]
    if not frame.empty:
        for (scene, cores), part in frame.groupby(["scene", "cores"]):
            if scene == "A" and int(cores) == 1:
                continue
            values = part["speedup_vs_baseline"].dropna()
            lines.append(f"| {scene} | {cores} | {len(values)} | {values.mean():.4f} | {values.median():.4f} |" if len(values) else f"| {scene} | {cores} | 0 | | |")
    lines += ["", "## 全量消融", "", "| 场景 | 核数 | 样本 | 平均初始到最终改善 | 改善比例 |", "|---|---:|---:|---:|---:|"]
    if effects:
        ef = pd.DataFrame(effects)
        for (scene, cores), part in ef.groupby(["scene", "cores"]):
            values = part["relative_gain"].dropna()
            lines.append(f"| {scene} | {cores} | {len(values)} | {100 * values.mean():.4f}% | {int(part['improved'].sum())}/{len(part)} |")
    lines += ["", "## Cache 三个比值", "", "| 核数 | 样本 | S_hw | S_adapt | S_opt | 恒等式最大误差 |", "|---:|---:|---:|---:|---:|---:|"]
    if pairs:
        pf = pd.DataFrame(pairs)
        for cores, part in pf.groupby("cores"):
            lines.append(f"| {cores} | {len(part)} | {part.s_hw.mean():.4f} | {part.s_adapt.mean():.4f} | {part.s_opt.mean():.4f} | {part.factor_identity_error.abs().max():.3e} |")
    lines += ["", "图文件在 `figures/`；机器可读数据在 `main_results.csv`、`candidate_effects.csv` 和 `cache_pairs.csv`。", ""]
    (out / "paper_results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-root", type=Path)
    parser.add_argument("--main-roots", type=Path, nargs="+")
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--config-path", type=Path,
                        help="配置文件 used for lower-bound diagnostics; defaults to the support workspace path")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    main_roots = [path.resolve() for path in (args.main_roots or ([args.main_root] if args.main_root else []))]
    if not main_roots:
        parser.error("one of --main-root or --main-roots is required")
    out = args.output_root.resolve()
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    out.mkdir(parents=True)
    main_rows, effects = build_main_results(main_roots, args.baseline_root.resolve())
    static = load_static(main_roots)
    config_path = (args.config_path.resolve() if args.config_path else
                   CODE_ROOT / "data/raw/A题/data/config.txt")
    add_lower_bounds(main_rows, static, config_path)
    pairs = build_cache_pairs(main_rows)
    write_csv(out / "main_results.csv", main_rows)
    write_csv(out / "candidate_effects.csv", effects)
    write_csv(out / "cache_pairs.csv", pairs)
    write_csv(out / "timing.csv", load_main_rows(main_roots))
    manifests = []
    for root in main_roots:
        path = root / "run_manifest.json"
        if path.exists():
            manifests.append(json.loads(path.read_text(encoding="utf-8")))
    manifest = {"status": "COMPUTED", "rows": len(main_rows)}
    write_json(out / "report_manifest.json", {"status": "COMPUTED", "main_roots": [str(root) for root in main_roots], "baseline_root": str(args.baseline_root.resolve()), "rows": len(main_rows), "effects": len(effects), "cache_pairs": len(pairs), "source_manifests": manifests})
    make_figures(out, main_rows, effects, pairs)
    paper_summary(out, main_rows, effects, pairs, manifest)
    print(json.dumps({"status": "COMPUTED", "rows": len(main_rows), "effects": len(effects), "cache_pairs": len(pairs), "output": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
