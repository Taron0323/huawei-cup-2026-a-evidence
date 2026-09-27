#!/usr/bin/env python3
"""Materialize the per-case inherited evidence used by the paper.

The audited 2024-09-24 matrix stores one evaluated plan for every
``(case, cores, scene)``.  The paper's inherited result rule chooses, for a
target K, the shortest evaluated plan among 1..K cores and the full-graph
single-core baseline, then embeds a lower-core plan by appending idle cores.

This script makes that derived result explicit on disk.  It writes the
inherited plans, a formal result CSV, a source index, compact result-reference
JSON files, and a manifest containing input/output hashes and validation
counts.  It deliberately does not overwrite the audited package.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PAPER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PAPER_ROOT.parents[3]
DEFAULT_CODE_ROOT = PROJECT_ROOT / "华为杯_code"
DEFAULT_AUDIT_DIR = PAPER_ROOT / "data" / "audited_20260924"
DEFAULT_OUTPUT_DIR = PAPER_ROOT / "data" / "inherited_20260927"
DEFAULT_SOLVER_ROOT = DEFAULT_CODE_ROOT / "solver_review_v7_20260926"
EXCLUDED_COPY_TYPES = {"COPY_IN", "COPY_OUT"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def resolve_code_path(raw: str, code_root: Path) -> Path:
    """Resolve the relative paths recorded by the old audit package."""
    path = Path(raw)
    if path.is_absolute():
        return path
    text = raw.replace("\\", "/")
    if text.startswith("code/"):
        return code_root / text[len("code/"):]
    return code_root / text


def source_rel(path: Path, code_root: Path) -> str:
    try:
        return "code/" + path.resolve().relative_to(code_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def pad_plan(plan: dict[str, Any], target_cores: int) -> dict[str, Any]:
    schedules = [list(map(int, seq)) for seq in plan["core_schedules"]]
    if len(schedules) > target_cores:
        raise ValueError(f"source plan has {len(schedules)} cores but target is {target_cores}")
    schedules.extend([[] for _ in range(target_cores - len(schedules))])
    # Normalize key/value types while preserving subgraph and schedule identity.
    mapping = {str(int(node)): int(group) for node, group in plan["node_to_subgraph"].items()}
    return {"core_schedules": schedules, "node_to_subgraph": mapping}


def validate_plan_shape(plan: dict[str, Any], cores: int) -> tuple[bool, str]:
    schedules = plan.get("core_schedules")
    mapping = plan.get("node_to_subgraph")
    if not isinstance(schedules, list) or len(schedules) != cores:
        return False, "core_schedules length mismatch"
    if not isinstance(mapping, dict):
        return False, "node_to_subgraph is not an object"
    flat = [int(group) for sequence in schedules for group in sequence]
    if len(flat) != len(set(flat)) or set(flat) != {int(v) for v in mapping.values()}:
        return False, "scheduled subgraphs do not match mapping"
    return True, "ok"


def baseline_plan(graph: dict[str, Any]) -> dict[str, Any]:
    """Reproduce vendor/official_evaluator/singlecore_evaluate.py exactly."""
    eligible = sorted(int(op["id"]) for op in graph.get("ops", [])
                      if op.get("op") not in EXCLUDED_COPY_TYPES)
    return {
        "core_schedules": [[0] if eligible else []],
        "node_to_subgraph": {str(op_id): 0 for op_id in eligible},
    }


def numeric(value: Any, default: Any = "") -> Any:
    if value is None or value == "":
        return default
    return value


def as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(float(value))


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(value)


def make_result_ref(case: str, target_k: int, scene: str, source_kind: str,
                    source_result: Path, source_result_rel: str,
                    source_result_sha: str, plan_rel: str, plan_sha: str,
                    summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "materialization_kind": "inherited_result_reference",
        "case": case,
        "cores": target_k,
        "scene": scene,
        "source_kind": source_kind,
        "source_result_path": source_result_rel,
        "source_result_sha256": source_result_sha,
        "materialized_plan_path": plan_rel,
        "materialized_plan_sha256": plan_sha,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-root", type=Path, default=DEFAULT_CODE_ROOT)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--solver-root", type=Path, default=DEFAULT_SOLVER_ROOT)
    parser.add_argument("--verify-sample", type=int, default=9,
                        help="number of deterministic official-evaluator checks")
    parser.add_argument("--force", action="store_true",
                        help="replace an existing output directory")
    args = parser.parse_args()

    audit = args.audit_dir.resolve()
    output = args.output_dir.resolve()
    code_root = args.code_root.resolve()
    solver_root = args.solver_root.resolve()
    if output.exists():
        if not args.force:
            raise SystemExit(f"output exists; pass --force to replace: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    main_path = audit / "main_results.csv"
    sources_path = audit / "result_sources.csv"
    baseline_path = audit / "singlecore_baseline.csv"
    main_rows = read_csv(main_path)
    source_rows = read_csv(sources_path)
    baseline_rows = read_csv(baseline_path)
    source_by_key = {(r["case"], int(r["cores"]), r["scene"]): r for r in source_rows}
    main_by_key = {(r["case"], int(r["cores"]), r["scene"]): r for r in main_rows}
    baseline_by_case = {r["case"]: r for r in baseline_rows}
    cases = sorted({r["case"] for r in main_rows})
    if len(main_rows) != 1500 or len(source_rows) != 1500:
        raise ValueError(f"expected 1500 main/source rows, got {len(main_rows)}/{len(source_rows)}")
    if len(baseline_by_case) != len(cases):
        raise ValueError("single-core baseline does not cover all cases")

    candidate_by_scene: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in main_rows:
        candidate_by_scene[(row["case"], row["scene"])].append(row)

    graph_dir = solver_root / "data" / "raw" / "A题" / "data"
    config_path = graph_dir / "config.txt"
    if not config_path.exists():
        raise FileNotFoundError(config_path)

    inherited_rows: list[dict[str, Any]] = []
    inherited_sources: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    source_counts = Counter()
    shape_counts = Counter()
    plan_checks: list[dict[str, Any]] = []

    for case in cases:
        baseline = baseline_by_case[case]
        baseline_ms = int(float(baseline["makespan"]))
        graph_path = graph_dir / f"{case}.json"
        graph_cache: dict[str, Any] | None = None
        for scene in "ABC":
            candidates = candidate_by_scene[(case, scene)]
            for target_k in range(1, 6):
                eligible = [r for r in candidates if int(r["cores"]) <= target_k]
                if not eligible:
                    raise ValueError(f"no candidate for {case}/{scene}/{target_k}")
                # This is the frozen selection rule: shortest makespan first,
                # then additional movement, then source core count/name.
                best = min(eligible, key=lambda r: (
                    int(float(r["final_makespan"])),
                    int(float(r.get("final_added_copy_bytes") or 0)),
                    int(r["cores"]),
                    r.get("final_candidate", ""),
                ))
                candidate_ms = int(float(best["final_makespan"]))
                # Match the report generator's tie handling: the baseline is
                # selected whenever it attains the minimum value.
                use_baseline = baseline_ms <= candidate_ms
                target_row = dict(main_by_key[(case, target_k, scene)])
                source_kind = "singlecore_baseline" if use_baseline else "evaluated_plan"
                inherited_from = 0 if use_baseline else int(best["cores"])
                if use_baseline:
                    if graph_cache is None:
                        graph_cache = json.loads(graph_path.read_text(encoding="utf-8"))
                    plan = pad_plan(baseline_plan(graph_cache), target_k)
                    source_plan = None
                    source_plan_sha = ""
                    source_candidate = "singlecore_baseline"
                    source_result_raw = baseline["result_path"]
                    source_result = resolve_code_path(source_result_raw, code_root)
                    metrics = {
                        "final_makespan": baseline["makespan"],
                        "final_scheduled_copy_bytes": baseline["scheduled_copy_bytes"],
                        "final_original_graph_copy_bytes": baseline["original_graph_copy_bytes"],
                        "final_added_copy_bytes": baseline["added_copy_bytes"],
                        "final_partition_added_copy_bytes": baseline["partition_added_copy_bytes"],
                        "final_spill_added_copy_bytes": baseline["spill_added_copy_bytes"],
                        "cache_hit_bytes": baseline["cache_hit_bytes"],
                        "cache_miss_bytes": baseline["cache_miss_bytes"],
                        "cache_hit_rate": baseline["cache_hit_rate"],
                    }
                else:
                    source_entry = source_by_key[(case, int(best["cores"]), scene)]
                    source_plan = resolve_code_path(source_entry["final_plan_path"], code_root)
                    if not source_plan.exists():
                        raise FileNotFoundError(source_plan)
                    source_plan_sha = sha256_file(source_plan)
                    plan = pad_plan(json.loads(source_plan.read_text(encoding="utf-8")), target_k)
                    source_candidate = best.get("final_candidate", "")
                    source_result_raw = source_entry["final_result_path"]
                    source_result = resolve_code_path(source_result_raw, code_root)
                    metrics = {key: best[key] for key in (
                        "final_makespan", "final_scheduled_copy_bytes",
                        "final_original_graph_copy_bytes", "final_added_copy_bytes",
                        "final_partition_added_copy_bytes", "final_spill_added_copy_bytes",
                        "cache_hit_bytes", "cache_miss_bytes", "cache_hit_rate")
                        if key in best}

                ok, reason = validate_plan_shape(plan, target_k)
                if not ok:
                    raise ValueError(f"invalid inherited plan {case}/{target_k}/{scene}: {reason}")
                plan_rel_path = Path("data/inherited_v7_20260927/plans") / case / f"{target_k}core" / scene / "inherited_plan.json"
                plan_path = PAPER_ROOT / plan_rel_path
                write_json(plan_path, plan)
                plan_file_sha = sha256_file(plan_path)
                plan_canonical_sha = canonical_hash(plan)
                source_result_sha = sha256_file(source_result) if source_result.exists() else ""
                source_result_rel = source_result_raw
                summary = {
                    "makespan": as_int(metrics["final_makespan"]),
                    "scheduled_copy_bytes": as_int(metrics.get("final_scheduled_copy_bytes", 0)),
                    "original_graph_copy_bytes": as_int(metrics.get("final_original_graph_copy_bytes", 0)),
                    "added_copy_bytes": as_int(metrics.get("final_added_copy_bytes", 0)),
                    "partition_added_copy_bytes": as_int(metrics.get("final_partition_added_copy_bytes", 0)),
                    "spill_added_copy_bytes": as_int(metrics.get("final_spill_added_copy_bytes", 0)),
                    "cache_hit_bytes": as_int(metrics.get("cache_hit_bytes", 0)),
                    "cache_miss_bytes": as_int(metrics.get("cache_miss_bytes", 0)),
                    "cache_hit_rate": as_float(metrics.get("cache_hit_rate", 0)),
                }
                ref_rel_path = Path("data/inherited_v7_20260927/result_refs") / case / f"{target_k}core" / scene / "result_ref.json"
                ref_path = PAPER_ROOT / ref_rel_path
                write_json(ref_path, make_result_ref(case, target_k, scene, source_kind,
                                                     source_result, source_result_rel,
                                                     source_result_sha, plan_rel_path.as_posix(),
                                                     plan_file_sha, summary))

                out_row = target_row
                for key, value in metrics.items():
                    out_row[key] = numeric(value)
                out_row["final_plan_sha256"] = plan_file_sha
                out_row["recorded_final_plan_hash"] = plan_file_sha
                out_row["final_makespan"] = str(summary["makespan"])
                out_row["speedup_vs_baseline"] = f"{baseline_ms / summary['makespan']:.15g}"
                initial_ms = as_float(out_row.get("initial_makespan"), 0.0)
                out_row["initial_to_final_relative_gain"] = (
                    f"{1.0 - summary['makespan'] / initial_ms:.15g}" if initial_ms else ""
                )
                out_row["final_candidate"] = source_candidate
                out_row["final_source"] = "inherited_materialized"
                out_row["inherited_from_cores"] = str(inherited_from)
                out_row["inherited_source_kind"] = source_kind
                out_row["inherited_source_candidate"] = source_candidate
                out_row["inherited_source_plan_path"] = source_entry["final_plan_path"] if not use_baseline else ""
                out_row["inherited_source_plan_sha256"] = source_plan_sha
                out_row["inherited_source_result_path"] = source_result_raw
                out_row["inherited_source_result_sha256"] = source_result_sha
                out_row["inherited_plan_path"] = plan_rel_path.as_posix()
                out_row["inherited_plan_sha256"] = plan_file_sha
                out_row["inherited_plan_canonical_sha256"] = plan_canonical_sha
                out_row["inherited_result_ref_path"] = ref_rel_path.as_posix()
                out_row["inherited_baseline_selected"] = "True" if use_baseline else "False"
                inherited_rows.append(out_row)

                source_out = dict(source_by_key.get((case, target_k, scene), {}))
                source_out.update({
                    "inherited_source_kind": source_kind,
                    "inherited_from_cores": inherited_from,
                    "inherited_source_plan_path": source_entry["final_plan_path"] if not use_baseline else "",
                    "inherited_source_plan_sha256": source_plan_sha,
                    "inherited_source_result_path": source_result_raw,
                    "inherited_source_result_sha256": source_result_sha,
                    "inherited_plan_path": plan_rel_path.as_posix(),
                    "inherited_plan_sha256": plan_file_sha,
                    "inherited_plan_canonical_sha256": plan_canonical_sha,
                    "inherited_result_ref_path": ref_rel_path.as_posix(),
                    # Keep the historical columns useful to consumers that
                    # expect final_plan_path/final_result_path.
                    "final_plan_path": plan_rel_path.as_posix(),
                    "final_result_path": ref_rel_path.as_posix(),
                })
                inherited_sources.append(source_out)
                selections.append({
                    "case": case, "cores": target_k, "scene": scene,
                    "source_kind": source_kind, "source_cores": inherited_from,
                    "makespan": summary["makespan"], "baseline_makespan": baseline_ms,
                    "plan_path": plan_rel_path.as_posix(), "plan_sha256": plan_file_sha,
                })
                source_counts[source_kind] += 1
                shape_counts[target_k] += 1
                plan_checks.append({"case": case, "cores": target_k, "scene": scene,
                                    "status": "PASS", "reason": reason,
                                    "plan_sha256": plan_file_sha})

    main_fields = list(main_rows[0].keys())
    for field in (
        "inherited_from_cores", "inherited_source_kind", "inherited_source_candidate",
        "inherited_source_plan_path", "inherited_source_plan_sha256",
        "inherited_source_result_path", "inherited_source_result_sha256",
        "inherited_plan_path", "inherited_plan_sha256",
        "inherited_plan_canonical_sha256", "inherited_result_ref_path",
        "inherited_baseline_selected",
    ):
        if field not in main_fields:
            main_fields.append(field)
    source_fields = list(source_rows[0].keys())
    for field in (
        "inherited_source_kind", "inherited_from_cores", "inherited_source_plan_path",
        "inherited_source_plan_sha256", "inherited_source_result_path",
        "inherited_source_result_sha256", "inherited_plan_path",
        "inherited_plan_sha256", "inherited_plan_canonical_sha256",
        "inherited_result_ref_path",
    ):
        if field not in source_fields:
            source_fields.append(field)
    write_csv(output / "main_results.csv", inherited_rows, main_fields)
    write_csv(output / "result_sources.csv", inherited_sources, source_fields)
    write_csv(output / "selection_ledger.csv", selections,
              ["case", "cores", "scene", "source_kind", "source_cores",
               "makespan", "baseline_makespan", "plan_path", "plan_sha256"])
    write_csv(output / "plan_checks.csv", plan_checks,
              ["case", "cores", "scene", "status", "reason", "plan_sha256"])

    # Optional official checks are intentionally bounded: the full 1500-row
    # matrix was already evaluated; these checks prove the newly materialized
    # lower-core embedding and generated baseline plans are legal and preserve
    # the stored makespan.
    verify_rows: list[dict[str, Any]] = []
    if args.verify_sample > 0:
        try:
            solver_src = solver_root / "src"
            vendor = solver_root / "vendor" / "official_evaluator"
            sys.path.insert(0, str(solver_src))
            sys.path.insert(0, str(vendor))
            from huawei_code.official import evaluate, load_modules, read_config, summary as eval_summary
            modules = load_modules(vendor)
            config = read_config(modules, config_path)
            # Include each scene and both materialization kinds when present.
            ordered = sorted(selections, key=lambda x: (x["source_kind"], x["scene"], x["case"], x["cores"]))
            # Cover both the generated single-core baseline plans and copied
            # evaluated plans when the requested sample is large enough.
            chosen: list[dict[str, Any]] = []
            seen_pairs: set[tuple[str, str]] = set()
            for item in ordered:
                if len(chosen) >= args.verify_sample:
                    break
                pair = (item["source_kind"], item["scene"])
                if pair not in seen_pairs:
                    chosen.append(item)
                    seen_pairs.add(pair)
            for item in ordered:
                if len(chosen) >= args.verify_sample:
                    break
                if item not in chosen:
                    chosen.append(item)
            for item in chosen:
                graph = json.loads((graph_dir / f"{item['case']}.json").read_text(encoding="utf-8"))
                plan = json.loads((PAPER_ROOT / item["plan_path"]).read_text(encoding="utf-8"))
                result = eval_summary(evaluate(graph, plan, "ABC".index(item["scene"]) + 1,
                                               config, modules))
                expected = int(item["makespan"])
                actual = int(result["makespan"])
                verify_rows.append({**item, "status": "PASS" if actual == expected else "FAIL",
                                    "expected_makespan": expected, "actual_makespan": actual,
                                    "error": ""})
        except Exception as exc:  # preserve the failure as evidence in manifest
            verify_rows.append({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
    write_csv(output / "official_sample_checks.csv", verify_rows,
              sorted({key for row in verify_rows for key in row} or {"status", "error"}))

    manifest = {
        "manifest_name": "INHERITED_EVIDENCE_MANIFEST",
        "manifest_version": 1,
        "status": "COMPUTED",
        "created_by": str(Path(__file__).relative_to(PAPER_ROOT)),
        "selection_rule": "For each case, scene, target K, choose the minimum final_makespan among evaluated cores 1..K and the full-graph single-core baseline; ties select the baseline, then pad lower-core schedules with idle cores.",
        "plan_rule": "Candidate plans are copied from audited final_plan.json and padded with empty core schedules; baseline plans reproduce singlecore_evaluate.build_singlecore_plan and are then padded.",
        "input": {
            "main_results_csv": str(main_path),
            "main_results_sha256": sha256_file(main_path),
            "result_sources_csv": str(sources_path),
            "result_sources_sha256": sha256_file(sources_path),
            "singlecore_baseline_csv": str(baseline_path),
            "singlecore_baseline_sha256": sha256_file(baseline_path),
            "graph_dir": str(graph_dir),
            "config_path": str(config_path),
            "config_sha256": sha256_file(config_path),
        },
        "coverage": {
            "cases": len(cases), "cores": 5, "scenes": 3,
            "expected_combinations": 1500, "materialized_combinations": len(inherited_rows),
            "unique_keys": len({(r["case"], r["cores"], r["scene"]) for r in inherited_rows}),
        },
        "source_counts": dict(source_counts),
        "source_cores_counts": {
            f"{kind}:{cores}": count
            for (kind, cores), count in Counter(
                (x["source_kind"], x["source_cores"]) for x in selections
            ).items()
        },
        "plan_shape_counts": dict(shape_counts),
        "official_sample_checks": {
            "requested": args.verify_sample,
            "rows": len(verify_rows),
            "pass": sum(1 for r in verify_rows if r.get("status") == "PASS"),
            "fail": sum(1 for r in verify_rows if r.get("status") == "FAIL"),
            "error": sum(1 for r in verify_rows if r.get("status") == "ERROR"),
        },
        "outputs": {},
        "notes": [
            "The inherited result is a materialized evidence selection, not a claim of global optimality.",
            "result_refs contain compact pointers and summaries; original full evaluator result JSON files remain in their audited run directories.",
            "The one-core baseline is generated with the byte-preserved official singlecore plan rule.",
        ],
    }
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "INHERITED_EVIDENCE_MANIFEST.json":
            manifest["outputs"][path.relative_to(output).as_posix()] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    write_json(output / "INHERITED_EVIDENCE_MANIFEST.json", manifest)
    print(json.dumps({"status": manifest["status"], "output": str(output),
                      "coverage": manifest["coverage"],
                      "source_counts": manifest["source_counts"],
                      "official_sample_checks": manifest["official_sample_checks"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
