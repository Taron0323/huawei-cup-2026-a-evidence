#!/usr/bin/env python3
"""Reconstruct the three Problem-3 comparison objects from raw evaluations.

The frozen ``cache_pairs.csv`` stores the final C-plan cache counters.  This
diagnostic keeps the frozen report untouched and adds the missing counters for
the initial C evaluation of the B plan, so that B(X_B), C(X_B), and C(X_C)
can be compared with explicit plan identity.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from evidence_data import assert_declared_count, infer_matrix_shape, resolve_data_dir


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build" / "review_diagnostics_20260925"
COLORS = {"B(X_B)": "#215A82", "C(X_B)": "#E09A32", "C(X_C)": "#2F8B78"}
INK = "#1F3345"
GRID = "#C8D4DC"
PANEL = "#F8FBFC"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def number(value: object) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"non-finite numeric value: {value}")
    return value


def pair_value(row: dict[str, str], *names: str) -> str:
    """Read an audit-enriched field, with aliases for the original frozen CSV."""
    for name in names:
        if name in row and row[name] != "":
            return row[name]
    raise KeyError(f"none of {names!r} found in cache-pair row")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(data_dir: Path, explicit_roots: list[Path] | None) -> list[Path]:
    if explicit_roots:
        return [path.resolve() for path in explicit_roots]
    manifest = data_dir / "main_report_manifest.json"
    if not manifest.exists():
        manifest = data_dir / "merge_manifest.json"
    value = json.loads(manifest.read_text(encoding="utf-8"))
    roots = [Path(path).expanduser() for path in value.get("main_roots", [])]
    if not roots and value.get("merged_root"):
        roots = [Path(value["merged_root"]).expanduser()]
    if not roots:
        raise ValueError(f"no main_roots in {manifest}")
    return [path.resolve() for path in roots]


def scene_root(main_roots: list[Path], batch: str, case: str, cores: int) -> Path:
    prefix, batch_name = batch.split(":", 1)
    index = int(prefix.removeprefix("root")) - 1
    if index < 0 or index >= len(main_roots):
        raise ValueError(f"invalid source root prefix: {batch}")
    path = main_roots[index] / batch_name / "cases" / case / f"{cores}core"
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def selected_result(scene: Path, which: str, expected_candidate: str,
                    expected_plan: str) -> tuple[dict, Path]:
    selection_path = scene / f"{which}_selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("candidate") != expected_candidate:
        raise AssertionError(
            f"{selection_path}: candidate {selection.get('candidate')} != {expected_candidate}"
        )
    if selection.get("plan_sha256") != expected_plan:
        raise AssertionError(f"{selection_path}: plan hash does not match report")
    result_path = scene / "candidates" / expected_candidate / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("makespan") is None:
        raise AssertionError(f"missing makespan: {result_path}")
    return result, result_path


def result_fields(result: dict, *, require_cache: bool) -> dict[str, float]:
    output = {"makespan": number(result["makespan"])}
    cache = result.get("cache_stats")
    if require_cache and not isinstance(cache, dict):
        raise AssertionError("C result is missing cache_stats")
    if cache is None:
        return output
    output.update({
        "hit_bytes": number(cache.get("hit_bytes", 0)),
        "miss_bytes": number(cache.get("miss_bytes", 0)),
        "hit_rate": number(cache.get("hit_rate", 0)),
    })
    total = output["hit_bytes"] + output["miss_bytes"]
    expected_rate = output["hit_bytes"] / total if total else 0.0
    if not math.isclose(expected_rate, output["hit_rate"], abs_tol=1e-10):
        raise AssertionError("cache_stats hit_rate is inconsistent with hit/miss bytes")
    output["query_bytes"] = total
    return output


def build_rows(root: Path, explicit_roots: list[Path] | None = None,
               data_dir: Path | None = None) -> tuple[list[dict[str, object]], dict[str, int], list[Path]]:
    data_dir = (data_dir or resolve_data_dir(root, None, "data/final_idea_v2")).resolve()
    main_path = data_dir / "main_results.csv"
    pair_path = data_dir / "cache_pairs.csv"
    main = read_csv(main_path)
    frozen_pairs = read_csv(pair_path)
    main_index = {(r["case"], int(r["cores"]), r["scene"]): r for r in main}
    if len(main_index) != len(main):
        raise AssertionError("duplicate main-results key")
    shape = infer_matrix_shape(main)
    case_count = int(shape["case_count"])
    core_count = int(shape["core_count"])
    expected_pairs = case_count * core_count
    assert_declared_count(data_dir, len(main), "main_rows")
    assert_declared_count(data_dir, len(frozen_pairs), "cache_pairs")
    if len(frozen_pairs) != expected_pairs:
        raise AssertionError(f"expected {expected_pairs} frozen pairs, found {len(frozen_pairs)}")
    seen: set[tuple[str, int]] = set()
    main_roots = load_manifest(data_dir, explicit_roots)
    rows: list[dict[str, object]] = []
    checked_final_fields = 0
    for frozen in frozen_pairs:
        case = frozen["case"]
        cores = int(frozen["cores"])
        key = (case, cores)
        if key in seen:
            raise AssertionError(f"duplicate pair key: {key}")
        seen.add(key)
        b = main_index[case, cores, "B"]
        c = main_index[case, cores, "C"]
        if b["batch"] != c["batch"]:
            raise AssertionError(f"B/C source batch differs for {key}")
        if b["final_plan_sha256"] != c["initial_plan_sha256"]:
            raise AssertionError(f"B plan does not seed C for {key}")
        if frozen["b_plan_sha256"] != b["final_plan_sha256"]:
            raise AssertionError(f"frozen B hash mismatch for {key}")
        if frozen["c_initial_plan_sha256"] != c["initial_plan_sha256"]:
            raise AssertionError(f"frozen C-initial hash mismatch for {key}")
        if frozen.get("c_starts_from_b", "True").lower() != "true":
            raise AssertionError(f"pair does not start from B plan for {key}")

        batch_root = scene_root(main_roots, b["batch"], case, cores)
        b_result, b_path = selected_result(
            batch_root / "B", "final", b["final_candidate"], b["final_plan_sha256"]
        )
        c_xb_result, c_xb_path = selected_result(
            batch_root / "C", "initial", c["initial_candidate"], c["initial_plan_sha256"]
        )
        c_xc_result, c_xc_path = selected_result(
            batch_root / "C", "final", c["final_candidate"], c["final_plan_sha256"]
        )
        b_fields = result_fields(b_result, require_cache=False)
        c_xb = result_fields(c_xb_result, require_cache=True)
        c_xc = result_fields(c_xc_result, require_cache=True)
        checks = (
            (b_fields["makespan"], number(pair_value(frozen, "b_makespan")), "B(X_B) makespan"),
            (c_xb["makespan"], number(pair_value(frozen, "c_initial_makespan", "c_same_plan_makespan")), "C(X_B) makespan"),
            (c_xc["makespan"], number(pair_value(frozen, "c_final_makespan")), "C(X_C) makespan"),
            (c_xc["hit_bytes"], number(pair_value(frozen, "c_final_hit_bytes", "c_hit_bytes", "hit_bytes")), "C(X_C) hit bytes"),
            (c_xc["miss_bytes"], number(pair_value(frozen, "c_final_miss_bytes", "c_miss_bytes", "miss_bytes")), "C(X_C) miss bytes"),
        )
        for observed, expected, label in checks:
            if not math.isclose(observed, expected, abs_tol=1e-9):
                raise AssertionError(f"{label} mismatch for {key}: {observed} != {expected}")
        # The enriched audit table is accepted only when its newly separated
        # C(X_B) counters agree with the raw official result as well.
        for field, observed, label in (
            ("c_initial_hit_bytes", c_xb["hit_bytes"], "C(X_B) hit bytes"),
            ("c_initial_miss_bytes", c_xb["miss_bytes"], "C(X_B) miss bytes"),
        ):
            if field in frozen and frozen[field] != "" and not math.isclose(number(frozen[field]), observed, abs_tol=1e-9):
                raise AssertionError(f"{label} mismatch for {key}: {frozen[field]} != {observed}")
        checked_final_fields += 1
        b_time, xb_time, xc_time = b_fields["makespan"], c_xb["makespan"], c_xc["makespan"]
        rows.append({
            "case": case, "cores": cores, "batch": b["batch"],
            "b_plan_sha256": b["final_plan_sha256"],
            "c_initial_plan_sha256": c["initial_plan_sha256"],
            "c_final_plan_sha256": c["final_plan_sha256"],
            "b_makespan": b_time, "c_xb_makespan": xb_time, "c_xc_makespan": xc_time,
            "c_xb_hit_bytes": c_xb["hit_bytes"], "c_xb_miss_bytes": c_xb["miss_bytes"],
            "c_xb_hit_rate": c_xb["hit_rate"], "c_xb_query_bytes": c_xb["query_bytes"],
            "c_xc_hit_bytes": c_xc["hit_bytes"], "c_xc_miss_bytes": c_xc["miss_bytes"],
            "c_xc_hit_rate": c_xc["hit_rate"], "c_xc_query_bytes": c_xc["query_bytes"],
            "s_hw": b_time / xb_time, "s_adapt": xb_time / xc_time,
            "s_opt": b_time / xc_time,
            "hardware_gain_percent": 100 * (1 - xb_time / b_time),
            "adaptation_gain_percent": 100 * (1 - xc_time / xb_time),
            "overall_gain_percent": 100 * (1 - xc_time / b_time),
            "b_result_path": str(b_path), "c_xb_result_path": str(c_xb_path),
            "c_xc_result_path": str(c_xc_path),
        })
    if len(seen) != expected_pairs:
        raise AssertionError(f"expected {expected_pairs} unique pairs, found {len(seen)}")
    return rows, {"checked_final_fields": checked_final_fields, "pairs": len(rows),
                  "cases": case_count, "cores": core_count}, main_roots


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def bootstrap_interval(values: list[float], seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    samples = [st.mean(rng.choices(values, k=len(values))) for _ in range(2000)]
    samples.sort()
    return samples[49], samples[1949]


def set_font() -> None:
    for name in ("PingFang SC", "Hiragino Sans GB", "STHeiti Medium", "Noto Sans CJK SC", "SimHei", "SimSun"):
        try:
            path = font_manager.findfont(name, fallback_to_default=False)
        except ValueError:
            continue
        plt.rcParams.update({
            "font.family": font_manager.FontProperties(fname=path).get_name(),
            "axes.unicode_minus": False, "font.size": 9,
            "font.weight": "regular", "axes.titleweight": "bold", "axes.titlecolor": INK,
            "pdf.fonttype": 42, "savefig.facecolor": "white", "axes.facecolor": PANEL,
        })
        return
    raise RuntimeError("Chinese font unavailable")


def plot_direct_comparison(out: Path, rows: list[dict[str, object]]) -> dict:
    set_font()
    xs = np.arange(1, 6)
    case_count = len({str(r["case"]) for r in rows})
    means: dict[str, list[float]] = {name: [] for name in COLORS}
    cis: dict[str, list[tuple[float, float]]] = {name: [] for name in COLORS}
    ratios: dict[str, list[float]] = {"B/C(X_B)": [], "B/C(X_C)": []}
    ratio_cis: dict[str, list[tuple[float, float]]] = {name: [] for name in ratios}
    for core in range(1, 6):
        part = [r for r in rows if int(r["cores"]) == core]
        for name, field in (("B(X_B)", "b_makespan"), ("C(X_B)", "c_xb_makespan"), ("C(X_C)", "c_xc_makespan")):
            values = [float(r[field]) / 1e6 for r in part]
            means[name].append(st.mean(values))
            cis[name].append(bootstrap_interval(values, 20260925 + core * 10 + len(name)))
        for name, values in {
            "B/C(X_B)": [float(r["s_hw"]) for r in part],
            "B/C(X_C)": [float(r["s_opt"]) for r in part],
        }.items():
            ratios[name].append(st.mean(values))
            ratio_cis[name].append(bootstrap_interval(values, 20260925 + core * case_count + len(name)))

    fig, axes = plt.subplots(1, 2, figsize=(7.3, 3.45), gridspec_kw={"width_ratios": [1.35, 1]})
    ax, bx = axes
    for name, color in COLORS.items():
        y = np.asarray(means[name])
        lo = np.asarray([v[0] for v in cis[name]])
        hi = np.asarray([v[1] for v in cis[name]])
        ax.fill_between(xs, lo, hi, color=color, alpha=.14)
        ax.plot(xs, y, marker="o", linewidth=1.9, markersize=4.2, color=color,
                markerfacecolor="white", markeredgewidth=1.0, label=name)
    ax.set_xticks(xs)
    ax.set_xlabel("核数")
    ax.set_ylabel("平均工期 / 百万 cycle")
    ax.set_title("三份评价对象的直接比较", fontsize=10.5, color=INK)
    ax.grid(axis="y", color=GRID, linestyle=(0, (3, 3)), linewidth=.65)
    ax.spines[["top", "right"]].set_visible(False)
    legend = ax.legend(frameon=True, fontsize=7.8, loc="best")
    legend.get_frame().set_facecolor("white")
    legend.get_frame().set_edgecolor("#A6B7C1")
    legend.get_frame().set_boxstyle("round,pad=0.30,rounding_size=0.10")
    for name, color in (("B/C(X_B)", COLORS["C(X_B)"]), ("B/C(X_C)", COLORS["C(X_C)"])):
        y = np.asarray(ratios[name])
        lo = np.asarray([v[0] for v in ratio_cis[name]])
        hi = np.asarray([v[1] for v in ratio_cis[name]])
        bx.fill_between(xs, lo, hi, color=color, alpha=.14)
        bx.plot(xs, y, marker="o", linewidth=1.9, markersize=4.2, color=color,
                markerfacecolor="white", markeredgewidth=1.0, label=name)
    bx.axhline(1, color=INK, linewidth=.75, linestyle=(0, (3, 3)))
    bx.set_xticks(xs)
    bx.set_xlabel("核数")
    bx.set_ylabel("相对 B(X_B) 的工期比")
    bx.set_title("相对 B 的逐例平均比值", fontsize=10.5, color=INK)
    bx.grid(axis="y", color=GRID, linestyle=(0, (3, 3)), linewidth=.65)
    bx.spines[["top", "right"]].set_visible(False)
    legend = bx.legend(frameon=True, fontsize=7.8, loc="best")
    legend.get_frame().set_facecolor("white")
    legend.get_frame().set_edgecolor("#A6B7C1")
    legend.get_frame().set_boxstyle("round,pad=0.30,rounding_size=0.10")
    fig.text(.01, .01, f"阴影为按图重采样的95%经验区间；每个核数含{case_count}张图。", fontsize=7.2, color="#66777B")
    fig.tight_layout(rect=(0, .045, 1, 1))
    for ext in ("png", "pdf", "svg"):
        fig.savefig(out / f"cache_direct_comparison.{ext}", dpi=260 if ext == "png" else None,
                    bbox_inches="tight", pad_inches=.08)
    plt.close(fig)
    return {"mean_makespan_mcycle": means, "mean_ratio": ratios}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="evidence CSV/manifest directory (defaults to PAPER_EVIDENCE_DATA or data/final_idea_v2)",
    )
    parser.add_argument("--main-roots", type=Path, nargs="*")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    root = args.root.resolve()
    data_dir = resolve_data_dir(root, args.data_dir, "data/final_idea_v2")
    if not data_dir.is_dir():
        raise FileNotFoundError(f"evidence data directory does not exist: {data_dir}")
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing non-empty output directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    rows, checks, main_roots = build_rows(root, args.main_roots or None, data_dir)
    write_csv(out / "cache_pair_diagnostic.csv", rows)
    figure_summary = plot_direct_comparison(out, rows)
    summary = {
        "status": "DIAGNOSTIC_VERIFIED",
        "pairs": len(rows),
        "cores": {str(k): sum(int(r["cores"]) == k for r in rows) for k in range(1, 6)},
        "c_xb_xc_cache_fields_differ": sum(
            r["c_xb_hit_bytes"] != r["c_xc_hit_bytes"] or r["c_xb_miss_bytes"] != r["c_xc_miss_bytes"]
            for r in rows
        ),
        "c_xb_xc_plan_hashes_differ": sum(r["c_initial_plan_sha256"] != r["c_final_plan_sha256"] for r in rows),
        "source_sha256": {
            name: sha256(data_dir / name)
            for name in ("main_results.csv", "cache_pairs.csv")
        },
        "main_roots": [str(path) for path in main_roots],
        "checks": checks,
        "figure": figure_summary,
    }
    (out / "diagnostic_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": summary["status"], "output": str(out), **checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
