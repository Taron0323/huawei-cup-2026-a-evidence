"""Verify frozen metrics and choose the best evaluated feasible A plans."""

import argparse
import collections
import csv
import gzip
import json
import shutil
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src/a_solver"))
from run_batch import now, save_json, sha, write_csv


def read_rows(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--fallback", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.source = args.source.resolve()
    if args.fallback:
        args.fallback = args.fallback.resolve()
    manifest = json.loads((args.source / "run_manifest.json").read_text())
    if manifest["status"] != "COMPUTED" or not manifest["fingerprints_unchanged"]:
        raise ValueError("Full run must be complete and input/code unchanged")
    rows = read_rows(args.source / "metrics.csv")
    assert len(rows) == 3900, "expected all 3900 official evaluations"
    for row in rows:
        row["origin"] = str(args.source.relative_to(ROOT))
    if args.fallback:
        extra = json.loads((args.fallback / "run_manifest.json").read_text())
        assert extra["status"] == "COMPUTED" and extra["fingerprints_unchanged"]
        for row in read_rows(args.fallback / "metrics.csv"):
            row["origin"] = str(args.fallback.relative_to(ROOT))
            rows.append(row)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    grouping = collections.defaultdict(list)
    by_alg = {}
    baseline = {}
    evidence = []
    for row in rows:
        for field in ("cores", "problem", "makespan", "added_copy_bytes", "scheduled_copy_bytes", "seed", "block_size"):
            row[field] = int(row[field])
        result_path = ROOT / row["origin"] / row["result_file"]
        assert sha(result_path) == row["result_sha256"], str(result_path)
        plan_path = result_path.parent / "plan.json"
        assert sha(plan_path) == row["plan_sha256"]
        checks = json.loads((result_path.parent / "checks.json").read_text())
        matching = [c for c in checks if c["problem"] == row["problem"]]
        assert len(matching) == 1 and matching[0]["status"] == "AI_VERIFIED"
        assert matching[0]["result_sha256"] == row["result_sha256"]
        with gzip.open(result_path, "rt", encoding="utf-8") as stream:
            result = json.load(stream)
        assert result["makespan"] == row["makespan"]
        assert result["data_movement_bytes"]["added_copy_bytes"] == row["added_copy_bytes"]
        assert result["bandwidth_bytes_per_cycle"] == 60
        assert result["capacity_bytes"] == {"L1": 524288, "UB": 131072}
        if row["problem"] == 3:
            assert result["cache_capacity_bytes"] == 1048576
            assert result["cache_bandwidth_bytes_per_cycle"] == 250
        row["cache_hit_bytes"] = result.get("cache_stats", {}).get("hit_bytes", 0)
        row["cache_access_bytes"] = sum(result.get("cache_stats", {}).get(key, 0) for key in ("hit_bytes", "miss_bytes"))
        key = row["case"], row["cores"], row["problem"]
        grouping[key].append(row)
        by_alg[(*key, row["algorithm"])] = row
        if row["cores"] == 1 and row["problem"] == 1:
            baseline[row["case"]] = row["makespan"]
        evidence.append({"case": row["case"], "cores": row["cores"], "algorithm": row["algorithm"],
                         "problem": row["problem"], "result_sha256": row["result_sha256"],
                         **{k: v for k, v in matching[0].items() if k not in ("problem", "result_sha256")}})
    assert len(baseline) == 100 and len(grouping) == 1500
    winners, summary = [], []
    for key, choices in sorted(grouping.items()):
        winner = min(choices, key=lambda r: (r["makespan"], r["added_copy_bytes"], r["algorithm"]))
        winner = dict(winner)
        winner["speedup_singlecore"] = baseline[winner["case"]] / winner["makespan"]
        winner["candidate_count"] = len(choices)
        winner["candidate_evaluation_seconds"] = sum(float(r["elapsed_seconds"]) for r in choices)
        plan_file = out / "selected_plans" / f"problem{key[2]}" / key[0] / f"{key[1]}core.json"
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile((ROOT / winner["origin"] / winner["result_file"]).parent / "plan.json", plan_file)
        winner["selected_plan"] = str(plan_file.relative_to(out))
        winners.append(winner)
    for problem in (1, 2, 3):
        for cores in range(1, 6):
            for algorithm in ("portfolio", "balanced_greedy", "component_aware", "component_packed"):
                group = ([r for r in winners if r["problem"] == problem and r["cores"] == cores]
                         if algorithm == "portfolio" else
                         [r for r in rows if r["problem"] == problem and r["cores"] == cores and
                          r["algorithm"] == ("singlecore" if cores == 1 else algorithm)])
                assert len(group) == 100
                speedups = [baseline[r["case"]] / r["makespan"] for r in group]
                if cores == 1 and problem in (1, 2):
                    # Problem 1/2 plots use the specified common one-core anchor.
                    assert all(r["makespan"] == baseline[r["case"]] for r in group)
                summary.append({"problem": problem, "cores": cores, "algorithm": algorithm, "cases": len(group),
                    "mean_speedup": statistics.mean(speedups), "median_speedup": statistics.median(speedups),
                    "min_speedup": min(speedups), "max_speedup": max(speedups),
                    "mean_makespan": statistics.mean(r["makespan"] for r in group),
                    "mean_added_copy_bytes": statistics.mean(r["added_copy_bytes"] for r in group),
                    "mean_cache_hit_rate": statistics.mean(float(r["cache_hit_rate"] or 0) for r in group),
                    "byte_weighted_cache_hit_rate": sum(r["cache_hit_bytes"] for r in group) / max(1, sum(r["cache_access_bytes"] for r in group)),
                    "slower_than_singlecore": sum(s < 1 for s in speedups)})
    winner_index = {(r["case"], r["cores"], r["problem"]): r for r in winners}
    cache_pairs = []
    for row in winners:
        if row["problem"] != 3:
            continue
        paired = by_alg[(row["case"], row["cores"], 2, row["algorithm"])]
        no_l2_best = winner_index[(row["case"], row["cores"], 2)]
        assert paired["plan_sha256"] == row["plan_sha256"]
        cache_pairs.append({"case": row["case"], "cores": row["cores"], "algorithm": row["algorithm"],
            "same_plan_no_l2_makespan": paired["makespan"], "same_plan_l2_makespan": row["makespan"],
            "same_plan_cache_speedup": paired["makespan"] / row["makespan"],
            "independently_selected_no_l2_makespan": no_l2_best["makespan"],
            "independently_selected_speedup": no_l2_best["makespan"] / row["makespan"],
            "no_l2_added_copy_bytes": paired["added_copy_bytes"], "l2_added_copy_bytes": row["added_copy_bytes"],
            "cache_hit_rate": row["cache_hit_rate"], "plan_sha256": row["plan_sha256"]})
    cache_summary = []
    for cores in range(1, 6):
        group = [r for r in cache_pairs if r["cores"] == cores]
        cache_summary.append({"cores": cores, "cases": len(group),
            **{key: statistics.mean(r[key] for r in group) for key in
               ("same_plan_no_l2_makespan", "same_plan_l2_makespan", "same_plan_cache_speedup", "independently_selected_speedup")},
            "cache_slowdown_cases": sum(r["same_plan_cache_speedup"] < 1 for r in group)})
    write_csv(out / "selected_metrics.csv", winners)
    write_csv(out / "summary.csv", summary)
    write_csv(out / "cache_pairs.csv", cache_pairs)
    write_csv(out / "cache_summary.csv", cache_summary)
    write_csv(out / "verification_index.csv", evidence)
    write_csv(out / "all_metrics.csv", rows)
    slowdown = [r for r in winners if r["speedup_singlecore"] < 1 and r["cores"] > 1]
    if slowdown:
        write_csv(out / "slower_than_singlecore.csv", slowdown)
    save_json(out / "analysis_manifest.json", {"created_at": now(), "source": str(args.source),
        "source_manifest_sha256": sha(args.source / "run_manifest.json"), "code_sha256": sha(__file__),
        "rows_verified": len(rows), "selected_rows": len(winners), "cache_pairs": len(cache_pairs),
        "slower_than_singlecore": len(slowdown), "slower_cases": sorted({r["case"] for r in slowdown}),
        "status": "AI_VERIFIED", "human_review": "NOT_ASSESSED", "global_optimality": "NOT_PROVEN"})
    print(json.dumps({"verified_rows": len(rows), "selected_rows": len(winners),
        "slower_cases": sorted({r["case"] for r in slowdown})}, ensure_ascii=False))


if __name__ == "__main__":
    main()
