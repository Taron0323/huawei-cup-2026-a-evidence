"""Build compact paper tables from the frozen V0.7.1 run, without evaluations."""

import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/v071_full_20260924_v2"
ANALYSIS = ROOT / "results/v071_full_20260924_v2_analysis"
GENERATED = ROOT / "paper/latex/generated"
REPORT = ROOT / "review/v071_writing_evidence.json"
SCENES = {"A": 1, "B": 2, "C": 3}


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def source_record(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest()}


def write_table(name, columns, header, rows):
    text = ["% Generated from the frozen V0.7.1 v2 results; do not edit values.",
            r"\begin{tabular}{" + columns + "}", r"\toprule",
            " & ".join(header) + r" \\", r"\midrule"]
    text += [" & ".join(row) + r" \\" for row in rows]
    text += [r"\bottomrule", r"\end{tabular}", ""]
    (GENERATED / name).write_text("\n".join(text), encoding="utf-8")


def integer(value):
    return f"{value:,}".replace(",", r"\,")


def main():
    GENERATED.mkdir(parents=True, exist_ok=True)
    selected = csv_rows(ANALYSIS / "selected_summary.csv")
    pairs = csv_rows(ANALYSIS / "cache_pairs.csv")
    existing = csv_rows(ANALYSIS / "core_summary.csv")
    assert len(selected) == 1425 and len(pairs) == 475
    cases = sorted({row["case"] for row in selected})
    assert len(cases) == 95
    index = {(r["case"], int(r["cores"]), r["scene"]): r for r in selected}
    pair_index = {(r["case"], int(r["cores"])): r for r in pairs}
    assert len(index) == len(selected) and len(pair_index) == len(pairs)
    baseline_tasks = {}
    for case in cases:
        plan = json.loads((RUN / f"cases/{case}/1core/selected_A_plan.json").read_text())
        baseline_tasks[case] = len(set(plan["node_to_subgraph"].values()))
        baseline = int(index[case, 1, "A"]["makespan"])
        assert all(int(row["baseline_makespan"]) == baseline for row in selected if row["case"] == case)

    summary, main_rows = [], []
    for scene, problem in SCENES.items():
        for cores in range(1, 6):
            rows = [index[case, cores, scene] for case in cases]
            ratios = [int(r["baseline_makespan"]) / int(r["makespan"]) for r in rows]
            old = next(r for r in existing if int(r["problem"]) == problem and int(r["cores"]) == cores)
            entry = {"problem": problem, "cores": cores, "n": len(rows),
                     "mean_speedup": statistics.mean(ratios),
                     "median_speedup": statistics.median(ratios),
                     "slower_than_singlecore": sum(int(r["makespan"]) > int(r["baseline_makespan"]) for r in rows),
                     "mean_makespan_cycles": statistics.mean(int(r["makespan"]) for r in rows)}
            assert math.isclose(entry["mean_speedup"], float(old["mean_speedup"]), rel_tol=1e-10)
            assert math.isclose(entry["median_speedup"], float(old["median_speedup"]), rel_tol=1e-10)
            summary.append(entry)
            main_rows.append([str(problem), str(cores), f'{entry["mean_speedup"]:.4f}',
                              f'{entry["median_speedup"]:.4f}', str(entry["slower_than_singlecore"])])
    write_table("writing_mainresults.tex", "ccrrr",
                ["问题", "核数", "平均加速比", "中位加速比", "慢于单核的实例数"], main_rows)

    five_pairs = [r for r in pairs if int(r["cores"]) == 5]
    cache_groups = {}
    cache_rows = []
    for name, sign in [("缩短", -1), ("不变", 0), ("延长", 1)]:
        rows = [r for r in five_pairs if (int(r["cache_makespan"]) > int(r["no_l2_makespan"]))
                - (int(r["cache_makespan"]) < int(r["no_l2_makespan"])) == sign]
        cache_groups[name] = {"n": len(rows), "cases": sorted(r["case"] for r in rows),
                              "mean_same_plan_speedup": statistics.mean(int(r["no_l2_makespan"]) / int(r["cache_makespan"]) for r in rows)}
        cache_rows.append([name, str(len(rows)), f"{100 * len(rows) / len(five_pairs):.2f}\\%",
                           f'{cache_groups[name]["mean_same_plan_speedup"]:.6f}'])
    write_table("writing_cache_pairs.tex", "lrrr",
                ["启用 L2 后的工期", "实例数", "比例", "组内平均加速比"], cache_rows)
    worst_cache = sorted(five_pairs, key=lambda r: int(r["no_l2_makespan"]) / int(r["cache_makespan"]))[:2]
    negative_rows = []
    for row in worst_cache:
        no_l2, cache = int(row["no_l2_makespan"]), int(row["cache_makespan"])
        hit, miss = int(row["cache_hit_bytes"]), int(row["cache_miss_bytes"])
        negative_rows.append([row["case"].removeprefix("case_"), integer(no_l2), integer(cache),
                              integer(cache - no_l2), f"{no_l2/cache:.6f}", f"{100*hit/(hit+miss):.4f}\\%"])
    write_table("writing_cache_negative.tex", "crrrrr",
                ["实例", "无 L2/周期", "有 L2/周期", "增加/周期", "加速比", "字节命中率"], negative_rows)

    # Select explanatory extremes by explicit rules; they are not representative averages.
    improvement = max(cases, key=lambda c: int(index[c, 5, "A"]["makespan"]) / int(index[c, 5, "B"]["makespan"]))
    regression = min(cases, key=lambda c: int(index[c, 5, "C"]["baseline_makespan"]) / int(index[c, 5, "C"]["makespan"]))
    cache_gain = max(five_pairs, key=lambda r: int(r["no_l2_makespan"]) / int(r["cache_makespan"]))["case"]
    representative_cases = [improvement, regression, cache_gain]
    extra_cases = ["case_001", "case_016", "case_093"]
    case_evidence, representative_rows = [], []
    for case in dict.fromkeys(representative_cases + extra_cases):
        for scene, problem in SCENES.items():
            row = index[case, 5, scene]
            plan_path = RUN / f"cases/{case}/5core/selected_{scene}_plan.json"
            plan_raw = plan_path.read_bytes()
            plan = json.loads(plan_raw)
            counts = [len(seq) for seq in plan["core_schedules"]]
            pair = pair_index[case, 5] if scene == "C" else None
            record = {"case": case, "problem": problem, "cores": 5,
                      "makespan_cycles": int(row["makespan"]),
                      "baseline_makespan_cycles": int(row["baseline_makespan"]),
                      "speedup": int(row["baseline_makespan"]) / int(row["makespan"]),
                      "added_copy_bytes": int(row["added_copy_bytes"]),
                      "partition_added_copy_bytes": int(row["partition_added_copy_bytes"]),
                      "spill_added_copy_bytes": int(row["spill_added_copy_bytes"]),
                      "subgraph_count": len(set(plan["node_to_subgraph"].values())),
                      "core_sequence_count": len(counts), "nonempty_core_sequence_count": sum(n > 0 for n in counts),
                      "subgraphs_per_core": counts, "selected_candidate": row["candidate"],
                      "plan_source": source_record(plan_path, plan_raw),
                      "selected_summary_row": row, "same_plan_cache_pair": pair}
            assert sum(counts) == record["subgraph_count"]
            case_evidence.append(record)
            if case in representative_cases:
                representative_rows.append([case.removeprefix("case_"), str(problem), integer(record["makespan_cycles"]),
                                            f'{record["speedup"]:.4f}', f'{record["added_copy_bytes"]/2**20:.3f}',
                                            str(record["subgraph_count"]), ",".join(map(str, counts))])
    write_table("writing_representative.tex", "ccrrrcr",
                ["实例", "问题", "工期/周期", "加速比", "额外搬运/MiB", "子图数", "各核子图数"], representative_rows)

    checks = []
    aggregate = {"results": 0, "movement_identity_pass": 0, "added_identity_pass": 0,
                 "summary_fields_match": 0, "timeline_makespan_match": 0,
                 "capacity_result_pass": 0, "capacity_core_pool_checks": 0,
                 "capacity_core_pool_pass": 0, "max_reported_peak_bytes": {"L1": 0, "UB": 0},
                 "sum_movement_bytes": {key: 0 for key in ["original_graph_copy_bytes", "scheduled_copy_bytes",
                                                         "added_copy_bytes", "partition_added_copy_bytes", "spill_added_copy_bytes"]},
                 "capacity_violations": []}
    for row in selected:
        path = RUN / f'cases/{row["case"]}/{row["cores"]}core/selected_{row["scene"]}_result.json'
        raw = path.read_bytes()
        result = json.loads(raw)
        movement = result["data_movement_bytes"]
        movement_ok = movement["scheduled_copy_bytes"] == movement["original_graph_copy_bytes"] + movement["added_copy_bytes"]
        added_ok = movement["added_copy_bytes"] == movement["partition_added_copy_bytes"] + movement["spill_added_copy_bytes"]
        summary_ok = result["makespan"] == int(row["makespan"]) and all(movement[k] == int(row[k]) for k in
                     ["scheduled_copy_bytes", "added_copy_bytes", "partition_added_copy_bytes", "spill_added_copy_bytes"])
        end = max(op["end"] for core in result["per_core_timeline"] for op in core["ops"])
        timeline_ok = end == result["makespan"]
        capacity_checks = []
        for core, peaks in result["memory_peak_by_core"].items():
            for pool in ["L1", "UB"]:
                peak, limit = peaks[pool], result["capacity_bytes"][pool]
                ok = 0 <= peak <= limit
                capacity_checks.append(ok)
                aggregate["capacity_core_pool_checks"] += 1
                aggregate["capacity_core_pool_pass"] += ok
                aggregate["max_reported_peak_bytes"][pool] = max(aggregate["max_reported_peak_bytes"][pool], peak)
                if not ok:
                    aggregate["capacity_violations"].append({"case": row["case"], "cores": int(row["cores"]),
                         "scene": row["scene"], "core": core, "pool": pool, "peak_bytes": peak, "capacity_bytes": limit})
        aggregate["results"] += 1
        for key, ok in [("movement_identity_pass", movement_ok), ("added_identity_pass", added_ok),
                        ("summary_fields_match", summary_ok), ("timeline_makespan_match", timeline_ok),
                        ("capacity_result_pass", all(capacity_checks))]:
            aggregate[key] += ok
        for key in aggregate["sum_movement_bytes"]:
            aggregate["sum_movement_bytes"][key] += movement[key]
        checks.append({"case": row["case"], "cores": int(row["cores"]), "scene": row["scene"],
                       "source": source_record(path, raw), "movement_identity": movement_ok,
                       "added_identity": added_ok, "summary_fields_match": summary_ok,
                       "timeline_makespan_match": timeline_ok, "reported_capacity_peaks_within_limit": all(capacity_checks),
                       "memory_peak_by_core": result["memory_peak_by_core"], "capacity_bytes": result["capacity_bytes"]})
    n = aggregate["results"]
    validation_rows = [[r"$Q_{\mathrm{total}}=Q_{\mathrm{original}}+Q_{\mathrm{added}}$", str(n), str(aggregate["movement_identity_pass"])],
                       [r"$Q_{\mathrm{added}}=Q_{\mathrm{partition}}+Q_{\mathrm{spill}}$", str(n), str(aggregate["added_identity_pass"])],
                       ["工期等于时间线最晚结束时刻", str(n), str(aggregate["timeline_makespan_match"])],
                       ["汇总工期与搬运量对应原始结果", str(n), str(aggregate["summary_fields_match"])],
                       ["各核 L1、UB 报告峰值不超容量", str(aggregate["capacity_core_pool_checks"]), str(aggregate["capacity_core_pool_pass"])]]
    write_table("writing_validation.tex", "lrr", ["检查关系", "检查数", "一致数"], validation_rows)

    hit = sum(int(r["cache_hit_bytes"]) for r in five_pairs)
    miss = sum(int(r["cache_miss_bytes"]) for r in five_pairs)
    evidence = {"run_id": RUN.name, "evidence_scope": "95 complete cases; all 1--5 core selected results; no new evaluations",
                "excluded_profile_only_cases": ["case_014", "case_072", "case_076", "case_087", "case_091"],
                "sources": [source_record(ANALYSIS / name) for name in ["selected_summary.csv", "core_summary.csv", "cache_pairs.csv"]]
                           + [source_record(RUN / "run_manifest.json")],
                "interpretation": {"speedup": "Arithmetic mean of per-case selected problem-1 single-core makespan / selected makespan. The baseline is not uniformly a whole-graph single task.",
                                   "cache": "Selected C plan evaluated with and without L2; no-L2 side is not the selected B optimum.",
                                   "checks": "Programmatic consistency of official evaluator reports and summaries; not independent scientific or human validation.",
                                   "capacity": "Each reported per-core L1 and UB memory peak is compared with the corresponding reported capacity; no independent memory-lifetime replay.",
                                   "sample_selection": {improvement: "Largest selected A makespan / selected B makespan at five cores.",
                                                        regression: "Lowest selected C single-core speedup at five cores.",
                                                        cache_gain: "Largest same-plan Cache speedup at five cores."}},
                "baseline": {"definition": "selected problem-1 single-core plan for each case", "n": len(baseline_tasks),
                             "single_task_plans": sum(n == 1 for n in baseline_tasks.values()),
                             "multiple_task_plans": sum(n > 1 for n in baseline_tasks.values()),
                             "task_counts_by_case": baseline_tasks},
                "core_summary": summary, "representative_cases": representative_cases,
                "case_results": case_evidence, "cache_five_core": {"groups": cache_groups,
                    "mean_same_plan_speedup": statistics.mean(int(r["no_l2_makespan"]) / int(r["cache_makespan"]) for r in five_pairs),
                    "weighted_hit_rate": hit / (hit + miss), "hit_bytes": hit, "miss_bytes": miss, "worst_two": worst_cache},
                "consistency_summary": aggregate, "result_checks": checks,
                "scientific_validation": "NOT_ASSESSED", "human_review": "NOT_ASSESSED"}
    REPORT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(REPORT.relative_to(ROOT)), "representative_cases": representative_cases,
                      "consistency": aggregate}, ensure_ascii=False))


if __name__ == "__main__":
    main()
