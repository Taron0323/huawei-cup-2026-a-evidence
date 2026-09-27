#!/usr/bin/env python3
"""Summarize a V0.7.1 run without touching its input directory.

The V0.7.1 runner writes candidate_metrics.csv and selected_metrics.csv.  This
script only reads those files (and the optional run_manifest.json), computes
arithmetic summaries, and writes a new analysis directory.  It does not run an
official evaluator and does not infer missing scientific results.

Missing values are written as ``PENDING``.  The generated claims.csv and
figures.csv are evidence drafts: figures are never marked visually reviewed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PENDING = "PENDING"
SUCCESS_STATUSES = {"AI_VERIFIED", "VERIFIED", "COMPUTED", "SUCCESS", "OK"}
FAIL_STATUSES = {"FAILED", "FAIL", "ERROR", "TIMEOUT", "CANCELLED"}
SCENE_TO_PROBLEM = {"A": 1, "B": 2, "C": 3}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, PENDING) for field in fields})


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def status_of(row: dict[str, Any]) -> str:
    return text(row.get("status")).upper()


def is_failed(row: dict[str, Any]) -> bool:
    status = status_of(row)
    error = text(row.get("error"))
    return status in FAIL_STATUSES or (bool(error) and error.upper() != PENDING)


def is_verified(row: dict[str, Any]) -> bool:
    return status_of(row) in SUCCESS_STATUSES


def as_float(value: Any) -> float | None:
    raw = text(value)
    if not raw or raw.upper() == PENDING:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    if number is None:
        return None
    return int(number)


def fmt_number(value: Any) -> Any:
    """Keep CSV values readable while retaining PENDING for absent values."""
    if value is None:
        return PENDING
    if isinstance(value, float):
        if not math.isfinite(value):
            return PENDING
        return f"{value:.12g}"
    return value


def mean(values: Iterable[float]) -> Any:
    values = list(values)
    return fmt_number(statistics.mean(values)) if values else PENDING


def median(values: Iterable[float]) -> Any:
    values = list(values)
    return fmt_number(statistics.median(values)) if values else PENDING


def percentile(values: Iterable[float], quantile: float) -> Any:
    values = sorted(values)
    if not values:
        return PENDING
    index = max(0, min(len(values) - 1, math.ceil(quantile * len(values)) - 1))
    return fmt_number(values[index])


def numeric_values(rows: Iterable[dict[str, Any]], field: str) -> list[float]:
    return [number for number in (as_float(row.get(field)) for row in rows) if number is not None]


def relative_display(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def metric_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (text(row.get("case")), text(row.get("cores")), text(row.get("problem")),
            text(row.get("candidate")), text(row.get("plan_sha256")))


def choose_candidate(index: dict[tuple[str, str, str, str, str], list[dict[str, Any]]],
                     loose: dict[tuple[str, str, str, str], list[dict[str, Any]]],
                     row: dict[str, Any], problem: int) -> tuple[dict[str, Any] | None, str]:
    exact = index.get((text(row.get("case")), text(row.get("cores")), str(problem),
                      text(row.get("candidate")), text(row.get("plan_sha256"))), [])
    if len(exact) == 1:
        return exact[0], "exact"
    candidates = loose.get((text(row.get("case")), text(row.get("cores")), str(problem),
                           text(row.get("candidate"))), [])
    if len(candidates) == 1:
        return candidates[0], "candidate"
    return None, "missing" if not candidates else "ambiguous"


def derived_cache_rate(row: dict[str, Any]) -> tuple[Any, str]:
    direct = as_float(row.get("cache_hit_rate"))
    if direct is not None:
        return fmt_number(direct), "reported"
    hit, miss = as_float(row.get("cache_hit_bytes")), as_float(row.get("cache_miss_bytes"))
    if hit is not None and miss is not None and hit + miss > 0:
        return fmt_number(hit / (hit + miss)), "derived_from_bytes"
    return PENDING, PENDING


def build_selected_summary(selected: list[dict[str, Any]], candidates: list[dict[str, Any]],
                           long_tail_seconds: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidate_index: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    loose_index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        candidate_index[metric_key(row)].append(row)
        loose_index[(text(row.get("case")), text(row.get("cores")), text(row.get("problem")),
                     text(row.get("candidate")))].append(row)

    # The common one-core anchor is the selected problem-1 row.  It is kept as
    # a lookup rather than filled with a default, so absent baselines remain
    # explicitly PENDING.
    baseline: dict[str, float] = {}
    for row in selected:
        problem = as_int(row.get("problem")) or SCENE_TO_PROBLEM.get(text(row.get("scene")))
        if problem == 1 and text(row.get("cores")) == "1":
            makespan = as_float(row.get("makespan"))
            if makespan is None:
                candidate, _ = choose_candidate(candidate_index, loose_index, row, 1)
                makespan = as_float(candidate.get("makespan")) if candidate else None
            if makespan is not None:
                baseline[text(row.get("case"))] = makespan

    summaries: list[dict[str, Any]] = []
    cache_pairs: list[dict[str, Any]] = []
    for index, selected_row in enumerate(selected, 1):
        scene = text(selected_row.get("scene")).upper()
        problem = as_int(selected_row.get("problem")) or SCENE_TO_PROBLEM.get(scene)
        if problem is None:
            problem_value: Any = PENDING
        else:
            problem_value = problem
        candidate, match = choose_candidate(candidate_index, loose_index, selected_row, problem or -1)
        merged = dict(selected_row)
        if candidate:
            for field, value in candidate.items():
                if not text(merged.get(field)) and text(value):
                    merged[field] = value
        cache_rate, cache_rate_source = derived_cache_rate(merged)
        makespan = as_float(merged.get("makespan"))
        base = baseline.get(text(merged.get("case")))
        speedup = base / makespan if base is not None and makespan and makespan > 0 else None
        elapsed = as_float(merged.get("elapsed_seconds"))
        if elapsed is None:
            tail_flag: Any = PENDING
        else:
            tail_flag = int(elapsed >= long_tail_seconds)
        verified = bool(candidate and is_verified(candidate))
        if not candidate and is_verified(selected_row):
            verified = True
        status = "AI_VERIFIED" if verified else ("FAILED" if is_failed(merged) else PENDING)
        out = {
            "selected_row": index,
            "case": text(merged.get("case")) or PENDING,
            "cores": text(merged.get("cores")) or PENDING,
            "problem": problem_value,
            "scene": scene or PENDING,
            "candidate": text(merged.get("candidate")) or PENDING,
            "source": text(merged.get("source")) or PENDING,
            "candidate_match": match,
            "status": status,
            "error": text(merged.get("error")) or (PENDING if status != "FAILED" else PENDING),
            "makespan": fmt_number(makespan),
            "baseline_makespan": fmt_number(base),
            "speedup_singlecore": fmt_number(speedup),
            "added_copy_bytes": fmt_number(as_float(merged.get("added_copy_bytes"))),
            "scheduled_copy_bytes": fmt_number(as_float(merged.get("scheduled_copy_bytes"))),
            "partition_added_copy_bytes": fmt_number(as_float(merged.get("partition_added_copy_bytes"))),
            "spill_added_copy_bytes": fmt_number(as_float(merged.get("spill_added_copy_bytes"))),
            "cache_hit_rate": cache_rate,
            "cache_rate_source": cache_rate_source,
            "cache_hit_bytes": fmt_number(as_float(merged.get("cache_hit_bytes"))),
            "cache_miss_bytes": fmt_number(as_float(merged.get("cache_miss_bytes"))),
            "elapsed_seconds": fmt_number(elapsed),
            "long_tail_threshold_seconds": fmt_number(long_tail_seconds),
            "long_tail_flag": tail_flag,
            "plan_sha256": text(merged.get("plan_sha256")) or PENDING,
            "global_optimality": text(merged.get("global_optimality")) or "NOT_PROVEN",
        }
        if problem == 3 and candidate and not is_failed(candidate):
            # The runner names the paired no-L2 result after the selected C
            # candidate and labels it paired_no_l2.  Match the plan as well,
            # because candidate names can be reused by different plans.
            pair = None
            for other in candidates:
                if (text(other.get("case")) == out["case"]
                        and text(other.get("cores")) == out["cores"]
                        and text(other.get("problem")) == "2"
                        and text(other.get("source")) == "paired_no_l2"
                        and text(other.get("plan_sha256")) == out["plan_sha256"]):
                    pair = other
                    break
            cache_makespan = makespan
            no_l2 = as_float(pair.get("makespan")) if pair else None
            out["no_l2_makespan"] = fmt_number(no_l2)
            out["same_plan_cache_speedup"] = (fmt_number(no_l2 / cache_makespan)
                                               if no_l2 is not None and cache_makespan else PENDING)
            cache_pairs.append({
                "case": out["case"], "cores": out["cores"], "candidate": out["candidate"],
                "plan_sha256": out["plan_sha256"], "cache_makespan": fmt_number(cache_makespan),
                "no_l2_makespan": fmt_number(no_l2),
                "same_plan_cache_speedup": fmt_number(no_l2 / cache_makespan)
                if no_l2 is not None and cache_makespan else PENDING,
                "cache_added_copy_bytes": out["added_copy_bytes"],
                "no_l2_added_copy_bytes": fmt_number(as_float(pair.get("added_copy_bytes"))) if pair else PENDING,
                "cache_hit_rate": out["cache_hit_rate"],
                "cache_hit_bytes": out["cache_hit_bytes"],
                "cache_miss_bytes": out["cache_miss_bytes"],
                "pair_status": "AI_VERIFIED" if pair and is_verified(pair) and is_verified(candidate) else PENDING,
            })
        else:
            out["no_l2_makespan"] = PENDING
            out["same_plan_cache_speedup"] = PENDING
        summaries.append(out)
    return summaries, cache_pairs


def build_core_summary(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        grouped[(text(row.get("problem")), text(row.get("cores")))].append(row)
    result: list[dict[str, Any]] = []
    for (problem, cores), rows in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        successful = [row for row in rows if as_float(row.get("makespan")) is not None and not is_failed(row)]
        verified = [row for row in rows if row.get("status") == "AI_VERIFIED"]
        speeds = numeric_values(successful, "speedup_singlecore")
        makespans = numeric_values(successful, "makespan")
        copies = numeric_values(successful, "added_copy_bytes")
        rates = numeric_values(successful, "cache_hit_rate")
        pair_speeds = numeric_values(successful, "same_plan_cache_speedup")
        elapsed = numeric_values(rows, "elapsed_seconds")
        hit_bytes = numeric_values(successful, "cache_hit_bytes")
        miss_bytes = numeric_values(successful, "cache_miss_bytes")
        weighted_cache = (sum(hit_bytes) / (sum(hit_bytes) + sum(miss_bytes))
                          if hit_bytes and miss_bytes and sum(hit_bytes) + sum(miss_bytes) > 0 else None)
        result.append({
            "problem": problem or PENDING, "cores": cores or PENDING,
            "selected_rows": len(rows), "successful_rows": len(successful),
            "verified_rows": len(verified), "failed_rows": sum(is_failed(row) for row in rows),
            "mean_makespan": mean(makespans), "median_makespan": median(makespans),
            "min_makespan": fmt_number(min(makespans)) if makespans else PENDING,
            "max_makespan": fmt_number(max(makespans)) if makespans else PENDING,
            "mean_speedup": mean(speeds), "median_speedup": median(speeds),
            "min_speedup": fmt_number(min(speeds)) if speeds else PENDING,
            "max_speedup": fmt_number(max(speeds)) if speeds else PENDING,
            "mean_added_copy_bytes": mean(copies),
            "mean_cache_hit_rate": mean(rates),
            "byte_weighted_cache_hit_rate": fmt_number(weighted_cache),
            "mean_same_plan_cache_speedup": mean(pair_speeds),
            "p95_elapsed_seconds": percentile(elapsed, 0.95),
            "max_elapsed_seconds": fmt_number(max(elapsed)) if elapsed else PENDING,
            "long_tail_rows": sum(as_float(row.get("long_tail_flag")) == 1 for row in rows),
            "status": "AI_VERIFIED" if rows and all(row.get("status") == "AI_VERIFIED" for row in rows) else PENDING,
            "global_optimality": "NOT_PROVEN",
        })
    return result


def build_source_summary(candidates: list[dict[str, Any]], long_tail_seconds: float) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        grouped[(text(row.get("problem")), text(row.get("cores")), text(row.get("source")) or PENDING)].append(row)
    result: list[dict[str, Any]] = []
    for (problem, cores, source), rows in sorted(grouped.items()):
        good = [row for row in rows if as_float(row.get("makespan")) is not None and not is_failed(row)]
        elapsed = numeric_values(rows, "elapsed_seconds")
        makespans = numeric_values(good, "makespan")
        copies = numeric_values(good, "added_copy_bytes")
        result.append({
            "problem": problem or PENDING, "cores": cores or PENDING, "source": source,
            "candidate_rows": len(rows), "successful_rows": len(good),
            "failed_rows": sum(is_failed(row) for row in rows),
            "verified_rows": sum(is_verified(row) for row in rows),
            "best_makespan": fmt_number(min(makespans)) if makespans else PENDING,
            "mean_makespan": mean(makespans), "mean_added_copy_bytes": mean(copies),
            "p95_elapsed_seconds": percentile(elapsed, 0.95),
            "max_elapsed_seconds": fmt_number(max(elapsed)) if elapsed else PENDING,
            "long_tail_rows": sum(value >= long_tail_seconds for value in elapsed),
            "status": "AI_VERIFIED" if rows and all(is_verified(row) for row in rows) else PENDING,
        })
    return result


def build_failures(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(candidates, 1):
        if not is_failed(row):
            continue
        rows.append({
            "candidate_row": index, "case": text(row.get("case")) or PENDING,
            "cores": text(row.get("cores")) or PENDING, "problem": text(row.get("problem")) or PENDING,
            "candidate": text(row.get("candidate")) or PENDING, "source": text(row.get("source")) or PENDING,
            "status": status_of(row) or "FAILED", "error": text(row.get("error")) or PENDING,
            "elapsed_seconds": fmt_number(as_float(row.get("elapsed_seconds"))),
            "plan_sha256": text(row.get("plan_sha256")) or PENDING,
        })
    return rows


def build_long_tail(candidates: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(candidates, 1):
        elapsed = as_float(row.get("elapsed_seconds"))
        if elapsed is None or elapsed < threshold:
            continue
        rows.append({
            "candidate_row": index, "case": text(row.get("case")) or PENDING,
            "cores": text(row.get("cores")) or PENDING, "problem": text(row.get("problem")) or PENDING,
            "candidate": text(row.get("candidate")) or PENDING, "source": text(row.get("source")) or PENDING,
            "elapsed_seconds": fmt_number(elapsed), "threshold_seconds": fmt_number(threshold),
            "makespan": fmt_number(as_float(row.get("makespan"))),
            "status": status_of(row) or PENDING,
        })
    return rows


def output_path(path: Path, run_root: Path) -> Path:
    path = path.resolve()
    if path == run_root or path.is_relative_to(run_root):
        raise ValueError("--output must be outside --run-root; input run directories are read-only")
    if path.exists():
        raise ValueError(f"output exists: {path}")
    path.mkdir(parents=True)
    return path


def claim_row(claim_id: str, statement: str, value: Any, unit: str, result_file: Path,
              result_row: Any, result_column: str, code_file: Path, run_id: str,
              paper_location: str, status: str, figure_file: Any = "") -> dict[str, Any]:
    return {
        "claim_id": claim_id, "statement": statement, "value": fmt_number(value), "unit": unit,
        # This summarizer does not establish a scientific tolerance.  Keep
        # the evidence field explicit instead of inventing one for aggregates.
        "tolerance": PENDING,
        "result_file": relative_display(result_file), "result_row": result_row,
        "result_column": result_column, "code_file": relative_display(code_file), "run_id": run_id,
        "paper_location": paper_location, "figure_file": figure_file,
        "verification_file": PENDING, "human_review": "NOT_ASSESSED", "status": status,
    }


def build_claims(core: list[dict[str, Any]], source: list[dict[str, Any]], failures: list[dict[str, Any]],
                 long_tail: list[dict[str, Any]], output: Path, code_file: Path, run_id: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    summary_path = output / "core_summary.csv"
    for index, row in enumerate(core, 1):
        problem, cores = row["problem"], row["cores"]
        def metric_status(field: str) -> str:
            return "AI_VERIFIED" if row.get("status") == "AI_VERIFIED" and row.get(field) != PENDING else PENDING

        prefix = f"V071-Q{problem}-K{cores}"
        claims.append(claim_row(prefix + "-SPEEDUP", f"V0.7.1问题{problem}在{cores}核下的当前选择集逐例平均加速比",
                                 row["mean_speedup"], "ratio", summary_path, index, "mean_speedup", code_file, run_id,
                                 f"问题{problem}结果；V0.1待定", metric_status("mean_speedup")))
        claims.append(claim_row(prefix + "-MAKESPAN", f"V0.7.1问题{problem}在{cores}核下的当前选择集平均Makespan",
                                 row["mean_makespan"], "cycles", summary_path, index, "mean_makespan", code_file, run_id,
                                 f"问题{problem}结果；V0.1待定", metric_status("mean_makespan")))
        claims.append(claim_row(prefix + "-COPY", f"V0.7.1问题{problem}在{cores}核下的当前选择集平均额外搬运量",
                                 row["mean_added_copy_bytes"], "bytes", summary_path, index, "mean_added_copy_bytes", code_file, run_id,
                                 f"问题{problem}结果；V0.1待定", metric_status("mean_added_copy_bytes")))
        if problem == "3":
            claims.append(claim_row(prefix + "-CACHE-HIT", f"V0.7.1问题3在{cores}核下的当前选择集字节加权Cache命中率",
                                     row["byte_weighted_cache_hit_rate"], "fraction", summary_path, index,
                                     "byte_weighted_cache_hit_rate", code_file, run_id, "问题3结果；V0.1待定",
                                     metric_status("byte_weighted_cache_hit_rate")))
            claims.append(claim_row(prefix + "-CACHE-SPEEDUP", f"V0.7.1问题3在{cores}核下的同计划Cache平均加速比",
                                     row["mean_same_plan_cache_speedup"], "ratio", summary_path, index,
                                     "mean_same_plan_cache_speedup", code_file, run_id, "问题3结果；V0.1待定",
                                     metric_status("mean_same_plan_cache_speedup")))
    for index, row in enumerate(source, 1):
        source_name = row["source"].replace(" ", "_")
        claims.append(claim_row(f"V071-SOURCE-P{row['problem']}-K{row['cores']}-{source_name}",
                                 f"V0.7.1问题{row['problem']}在{row['cores']}核来源{row['source']}的候选成功数",
                                 row["successful_rows"], "count", output / "candidate_sources.csv", index,
                                 "successful_rows", code_file, run_id, "搜索过程；V0.1待定", row["status"]))
    claims.append(claim_row("V071-FAILURES", "V0.7.1候选评估失败条数", len(failures), "count",
                             output / "failures.csv", "summary", "candidate_row", code_file, run_id,
                             "验证与失败分析；V0.1待定", "AI_VERIFIED"))
    claims.append(claim_row("V071-LONGTAIL", "V0.7.1超过预设长尾阈值的候选条数", len(long_tail), "count",
                             output / "long_tail.csv", "summary", "candidate_row", code_file, run_id,
                             "运行分析；V0.1待定", "AI_VERIFIED"))
    return claims


def build_figures(core: list[dict[str, Any]], output: Path, code_file: Path, run_id: str) -> list[dict[str, Any]]:
    code_sha = sha_file(code_file)
    plans = [
        ("v071_speedup_q1", "V0.7.1问题1：逐核平均加速比（草案）", "core_summary.csv", "问题1结果；V0.1待定"),
        ("v071_speedup_q2", "V0.7.1问题2：逐核平均加速比（草案）", "core_summary.csv", "问题2结果；V0.1待定"),
        ("v071_speedup_q3", "V0.7.1问题3：逐核平均单核加速比（草案）", "core_summary.csv", "问题3结果；V0.1待定"),
        ("v071_cache_q3", "V0.7.1问题3：同计划Cache加速比与命中率（草案）", "cache_pairs.csv", "问题3结果；V0.1待定"),
        ("v071_candidate_sources", "V0.7.1候选来源计数（草案）", "candidate_sources.csv", "搜索过程；V0.1待定"),
        ("v071_failure_longtail", "V0.7.1失败与长尾候选（草案）", "failures.csv", "验证与失败分析；V0.1待定"),
    ]
    rows: list[dict[str, Any]] = []
    for figure_id, caption, result_name, location in plans:
        result_path = output / result_name
        rows.append({
            "figure_id": figure_id, "caption": caption,
            "result_file": relative_display(result_path),
            "result_sha256": sha_file(result_path) if result_path.exists() else PENDING,
            "code_file": relative_display(code_file), "code_sha256": code_sha,
            "figure_file": PENDING, "figure_sha256": PENDING, "run_id": run_id,
            "paper_location": location, "visual_review": PENDING, "status": PENDING,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True,
                        help="Completed or partial run_v071 directory containing candidate_metrics.csv")
    parser.add_argument("--output", type=Path, required=True,
                        help="New analysis directory outside --run-root; it must not already exist")
    parser.add_argument("--long-tail-seconds", type=float, default=60.0,
                        help="Absolute elapsed_seconds threshold for long_tail.csv (default: 60)")
    args = parser.parse_args()
    run_root = args.run_root.resolve()
    if args.long_tail_seconds < 0:
        parser.error("--long-tail-seconds must be non-negative")
    candidate_path, selected_path = run_root / "candidate_metrics.csv", run_root / "selected_metrics.csv"
    if not candidate_path.is_file() or not selected_path.is_file():
        parser.error("--run-root must contain candidate_metrics.csv and selected_metrics.csv")
    try:
        output = output_path(args.output, run_root)
    except ValueError as exc:
        parser.error(str(exc))

    candidates = read_csv(candidate_path)
    selected = read_csv(selected_path)
    manifest_path = run_root / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    run_id = text(manifest.get("run_id")) or run_root.name
    code_file = Path(__file__).resolve()

    selected_summary, cache_pairs = build_selected_summary(selected, candidates, args.long_tail_seconds)
    core_summary = build_core_summary(selected_summary)
    source_summary = build_source_summary(candidates, args.long_tail_seconds)
    failures = build_failures(candidates)
    long_tail = build_long_tail(candidates, args.long_tail_seconds)

    selected_fields = [
        "selected_row", "case", "cores", "problem", "scene", "candidate", "source", "candidate_match",
        "status", "error", "makespan", "baseline_makespan", "speedup_singlecore", "added_copy_bytes",
        "scheduled_copy_bytes", "partition_added_copy_bytes", "spill_added_copy_bytes", "cache_hit_rate",
        "cache_rate_source", "cache_hit_bytes", "cache_miss_bytes", "elapsed_seconds", "long_tail_threshold_seconds",
        "long_tail_flag", "no_l2_makespan", "same_plan_cache_speedup", "plan_sha256", "global_optimality",
    ]
    core_fields = list(core_summary[0]) if core_summary else ["problem", "cores", "status"]
    source_fields = list(source_summary[0]) if source_summary else ["problem", "cores", "source", "status"]
    cache_fields = list(cache_pairs[0]) if cache_pairs else ["case", "cores", "candidate", "plan_sha256", "pair_status"]
    write_csv(output / "selected_summary.csv", selected_summary, selected_fields)
    write_csv(output / "core_summary.csv", core_summary, core_fields)
    write_csv(output / "candidate_sources.csv", source_summary, source_fields)
    write_csv(output / "cache_pairs.csv", cache_pairs, cache_fields)
    write_csv(output / "failures.csv", failures)
    write_csv(output / "long_tail.csv", long_tail)

    claims = build_claims(core_summary, source_summary, failures, long_tail, output, code_file, run_id)
    figures = build_figures(core_summary, output, code_file, run_id)
    claim_fields = ["claim_id", "statement", "value", "unit", "tolerance", "result_file", "result_row",
                    "result_column", "code_file", "run_id", "paper_location", "figure_file",
                    "verification_file", "human_review", "status"]
    figure_fields = ["figure_id", "caption", "result_file", "result_sha256", "code_file", "code_sha256",
                     "figure_file", "figure_sha256", "run_id", "paper_location", "visual_review", "status"]
    write_csv(output / "claims.csv", claims, claim_fields)
    write_csv(output / "figures.csv", figures, figure_fields)

    numeric_candidate_rows = sum(as_float(row.get("makespan")) is not None and not is_failed(row) for row in candidates)
    manifest_out = {
        "created_at": now(), "run_id": run_id, "source_run_root": str(run_root),
        "candidate_metrics": relative_display(candidate_path), "selected_metrics": relative_display(selected_path),
        "candidate_metrics_sha256": sha_file(candidate_path), "selected_metrics_sha256": sha_file(selected_path),
        "source_manifest_sha256": sha_file(manifest_path) if manifest_path.is_file() else PENDING,
        "code_file": relative_display(code_file), "code_sha256": sha_file(code_file),
        "long_tail_seconds": args.long_tail_seconds, "candidate_rows": len(candidates),
        "selected_rows": len(selected), "numeric_candidate_rows": numeric_candidate_rows,
        "failure_rows": len(failures), "long_tail_rows": len(long_tail), "cache_pairs": len(cache_pairs),
        "status": "AI_VERIFIED" if candidates and all(is_verified(row) or is_failed(row) for row in candidates) else PENDING,
        "scientific_validation": "NOT_ASSESSED", "human_review": "NOT_ASSESSED",
        "global_optimality": "NOT_PROVEN", "figures_rendered": False,
        "missing_value_policy": PENDING,
    }
    write_json(output / "analysis_manifest.json", manifest_out)
    print(json.dumps({
        "run_id": run_id, "output": str(output), "candidate_rows": len(candidates),
        "selected_rows": len(selected), "numeric_candidate_rows": numeric_candidate_rows,
        "failure_rows": len(failures), "long_tail_rows": len(long_tail), "cache_pairs": len(cache_pairs),
        "status": manifest_out["status"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
