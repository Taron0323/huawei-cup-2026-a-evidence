"""Complete only the missing fixed A0/one-core baselines for V0.7.1."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "results/v071_full_20260924_v2"
OUT = ROOT / "results/v071_singlecore_baseline_20260924"
RAW = ROOT / "inputs/raw/A题/附件"
MISSING = [f"case_{n:03d}" for n in [28, 30, 34, 38, 41, 44, 46, 53, 57, 67, 73, 78, 83, 90, 92, 97]]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def worker(case):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "src/a_solver"))
    from verify import check_plan, check_result
    from v071_official_bridge import evaluate_plan, load_official_modules, read_config

    directory = OUT / "cases" / case
    directory.mkdir(parents=True, exist_ok=True)
    source_plan = V2 / f"cases/{case}/1core/candidates/A/A0__0000/plan.json"
    graph_path = RAW / "data" / f"{case}.json"
    shutil.copyfile(source_plan, directory / "plan.json")
    plan = json.loads(source_plan.read_text())
    graph = json.loads(graph_path.read_text())
    assert plan["core_schedules"] == [[0]] and set(plan["node_to_subgraph"].values()) == {0}
    plan_check = check_plan(graph, plan)
    modules = load_official_modules(RAW / "code")
    config = read_config(modules, RAW / "data/config.txt")
    save(directory / "case_manifest.json", {"case": case, "status": "RUNNING", "started_at": now(),
        "problem": 1, "cores": 1, "candidate": "A0", "input_sha256": sha(graph_path),
        "plan_sha256": sha(source_plan), "source_plan": str(source_plan.relative_to(ROOT)), "config": config})
    started = time.perf_counter()
    result = evaluate_plan(graph, plan, 1, config, modules)
    elapsed = time.perf_counter() - started
    result_check = check_result(graph, plan, result)
    save(directory / "result.json", result)
    save(directory / "result_check.json", {"plan_check": plan_check, "result_check": result_check})
    manifest = json.loads((directory / "case_manifest.json").read_text())
    manifest.update({"status": "COMPUTED", "ended_at": now(), "elapsed_evaluation_seconds": elapsed,
                     "makespan": result["makespan"], "result_sha256": sha(directory / "result.json")})
    save(directory / "case_manifest.json", manifest)
    print(json.dumps({"case": case, "status": "COMPUTED", "makespan": result["makespan"],
                      "elapsed_evaluation_seconds": elapsed}), flush=True)


def launch(case):
    directory = OUT / "cases" / case
    directory.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with (directory / "worker.log").open("w", encoding="utf-8") as log:
        try:
            process = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--case", case],
                                     cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=120,
                                     env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            status = "COMPUTED" if process.returncode == 0 else "FAILED"
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
    event = {"case": case, "status": status, "wall_seconds": time.perf_counter() - started, "time": now()}
    if status != "COMPUTED":
        save(directory / "failure.json", {**event, "timeout_seconds": 120, "log": "worker.log"})
    return event


def main():
    if OUT.exists():
        raise SystemExit(f"Output already exists; preserve its evidence: {OUT}")
    OUT.mkdir(parents=True)
    source_files = list(sorted((RAW / "code").glob("*.py"))) + [RAW / "data/config.txt",
        ROOT / "tools/v071_official_bridge.py", ROOT / "src/a_solver/verify.py", Path(__file__).resolve()]
    fingerprints = []
    for path in source_files:
        relative = path.relative_to(ROOT)
        target = OUT / "source_snapshot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        fingerprints.append({"path": str(relative), "sha256": sha(path)})
    manifest = {"run_id": OUT.name, "status": "RUNNING", "started_at": now(), "workers": 4,
                "timeout_seconds_per_case": 120, "fixed_plan": "Existing v2 A0, one subgraph, one core",
                "newly_evaluated_cases": MISSING, "new_search": False, "problem": 1,
                "source_fingerprints": fingerprints, "scientific_validation": "NOT_ASSESSED",
                "human_review": "NOT_ASSESSED"}
    save(OUT / "run_manifest.json", manifest)
    events = []
    with (OUT / "progress.jsonl").open("w", encoding="utf-8") as progress:
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = [pool.submit(launch, case) for case in MISSING]
            for future in as_completed(jobs):
                event = future.result()
                events.append(event)
                progress.write(json.dumps(event, ensure_ascii=False) + "\n")
                progress.flush()
                print(json.dumps({"finished": len(events), "total": len(MISSING), **event}), flush=True)
    with (V2 / "candidate_metrics.csv").open() as stream:
        candidates = [r for r in csv.DictReader(stream) if r["candidate"] == "A0" and r["cores"] == "1" and r["problem"] == "1"]
    complete = []
    for row in sorted(candidates, key=lambda r: r["case"]):
        case = row["case"]
        if row["status"] == "AI_VERIFIED":
            path = V2 / f"cases/{case}/1core/candidates/A/A0__0000/result.json"
            plan_path = path.with_name("plan.json")
            origin = "EXISTING_V2_A0"
            elapsed = float(row["elapsed_seconds"])
        elif case in MISSING and (OUT / f"cases/{case}/case_manifest.json").exists():
            case_manifest = json.loads((OUT / f"cases/{case}/case_manifest.json").read_text())
            if case_manifest["status"] != "COMPUTED":
                continue
            path = OUT / f"cases/{case}/result.json"
            plan_path = path.with_name("plan.json")
            origin = "FIXED_A0_COMPLETION"
            elapsed = case_manifest["elapsed_evaluation_seconds"]
        else:
            continue
        result = json.loads(path.read_text())
        plan = json.loads(plan_path.read_text())
        assert plan["core_schedules"] == [[0]] and set(plan["node_to_subgraph"].values()) == {0}
        assert result["num_cores"] == 1
        move = result["data_movement_bytes"]
        assert move["scheduled_copy_bytes"] == move["original_graph_copy_bytes"] + move["added_copy_bytes"]
        complete.append({"case": case, "baseline_makespan": result["makespan"], "cores": 1, "problem": 1,
                         "subgraphs": 1, "baseline_added_copy_bytes": move["added_copy_bytes"],
                         "baseline_partition_added_copy_bytes": move["partition_added_copy_bytes"],
                         "baseline_spill_added_copy_bytes": move["spill_added_copy_bytes"],
                         "baseline_scheduled_copy_bytes": move["scheduled_copy_bytes"],
                         "origin": origin, "elapsed_evaluation_seconds": elapsed,
                         "result_path": str(path.relative_to(ROOT)), "result_sha256": sha(path),
                         "plan_path": str(plan_path.relative_to(ROOT)), "plan_sha256": sha(plan_path)})
    with (OUT / "wholegraph_baselines.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(complete[0])); writer.writeheader(); writer.writerows(complete)
    assert all(sha(ROOT / x["path"]) == x["sha256"] for x in fingerprints)
    manifest.update({"ended_at": now(), "status": "COMPUTED" if len(complete) == 95 else "PARTIAL",
                     "complete_baselines": len(complete), "existing_baselines": sum(r["origin"] == "EXISTING_V2_A0" for r in complete),
                     "new_baselines": sum(r["origin"] == "FIXED_A0_COMPLETION" for r in complete),
                     "failures": [e for e in events if e["status"] != "COMPUTED"]})
    save(OUT / "run_manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "complete_baselines": len(complete), "failures": manifest["failures"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=MISSING)
    args = parser.parse_args()
    if args.case:
        try:
            worker(args.case)
        except Exception:
            traceback.print_exc()
            raise SystemExit(1)
    else:
        main()
