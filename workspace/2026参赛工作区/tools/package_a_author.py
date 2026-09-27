"""Audit a frozen A-problem matrix and package its reproducibility evidence.

This tool never evaluates a plan. It only accepts a complete, manifest-bound
100-case run whose selected results used the registered original evaluator.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import zipfile
from decimal import Decimal, InvalidOperation


CASES = {f"case_{number:03d}" for number in range(1, 101)}
COMBOS = {(case, cores, scene) for case in CASES for cores in range(1, 6) for scene in "ABC"}
CASE_RE = re.compile(r"case_\d{3}$")
HASH_RE = re.compile(r"[0-9a-f]{64}$")
LIMIT_BYTES = 50_000_000  # The announcement says 50M; use the conservative decimal reading.


class AuditError(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def read_json(path: Path):
    require(path.is_file() and not path.is_symlink(), f"missing or linked file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise AuditError(f"invalid JSON: {path}: {exc}") from exc


def read_csv(path: Path) -> list[dict[str, str]]:
    require(path.is_file() and not path.is_symlink(), f"missing or linked CSV: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(bool(reader.fieldnames), f"CSV has no header: {path}")
        rows = list(reader)
    return rows


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"missing or linked file: {path}")
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def archived_digest(archive: zipfile.ZipFile, member: str) -> str:
    value = hashlib.sha256()
    with archive.open(member) as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def plan_digest(plan: dict) -> str:
    try:
        normalized = {
            "node_to_subgraph": {str(int(node)): int(group) for node, group in plan["node_to_subgraph"].items()},
            "core_schedules": [[int(group) for group in schedule] for schedule in plan["core_schedules"]],
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise AuditError(f"invalid final plan: {exc}") from exc
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def number(value, label: str) -> int:
    try:
        decimal = Decimal(str(value))
        parsed = int(decimal)
        require(decimal.is_finite() and decimal == parsed, f"non-integral {label}: {value!r}")
    except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
        raise AuditError(f"invalid integer {label}: {value!r}") from exc
    return parsed


def combo(row: dict) -> tuple[str, int, str]:
    case = row.get("case")
    cores = number(row.get("cores"), "cores")
    scene = row.get("scene")
    require(isinstance(case, str) and CASE_RE.fullmatch(case) is not None, f"invalid case: {case!r}")
    require(scene in ("A", "B", "C"), f"invalid scene: {scene!r}")
    return case, cores, scene


def unique_rows(rows: list[dict], keys: set, label: str) -> dict:
    mapped = {}
    for row in rows:
        key = keys(row)
        require(key not in mapped, f"duplicate {label}: {key}")
        mapped[key] = row
    return mapped


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), f"path escapes root: {relative}")
    require(path.is_file() and not path.is_symlink(), f"missing or linked file: {path}")
    return path


def add(files: dict[str, tuple[Path, str]], target: str, path: Path, category: str) -> None:
    require(target not in files, f"duplicate archive path: {target}")
    require(path.is_file() and not path.is_symlink(), f"missing or linked file: {path}")
    files[target] = (path, category)


def audit(args) -> tuple[dict[str, tuple[Path, str]], dict]:
    source = args.source_root.resolve()
    run = args.run_root.resolve()
    baseline = args.baseline_root.resolve()
    official = args.official_workspace.resolve()
    require(len({source, run, baseline, official}) == 4, "input roots must be distinct")
    files: dict[str, tuple[Path, str]] = {}

    registered = read_json(official / "inputs/manifest.json")
    require(isinstance(registered, list), "official input manifest must be a list")
    registered_by_path = unique_rows(registered, lambda row: row["path"], "registered input")
    original_code = {}
    attachment = None
    for rel, entry in registered_by_path.items():
        if rel.startswith("inputs/raw/A题/附件/code/") and rel.endswith(".py"):
            original_code[Path(rel).name] = entry["sha256"]
        if rel.startswith("inputs/raw/A题/") and rel.endswith(".zip"):
            require(attachment is None, "multiple registered A attachments")
            attachment = rel
    require(attachment and original_code, "registered A attachment or original evaluator missing")
    original_config = registered_by_path.get("inputs/raw/A题/附件/data/config.txt")
    require(original_config is not None, "registered original config missing")
    original_paths = [attachment]
    original_paths += [rel for rel in registered_by_path if rel.startswith("inputs/problem/A题/")]
    original_paths += [rel for rel in registered_by_path if rel.startswith("inputs/raw/A题/附件/code/") and rel.endswith(".py")]
    original_paths += [rel for rel in registered_by_path if rel.endswith("/config.txt") and rel.startswith("inputs/raw/A题/附件/data/")]
    for rel in sorted(original_paths):
        path = inside(official, rel)
        entry = registered_by_path[rel]
        require(digest(path) == entry["sha256"] and path.stat().st_size == entry["bytes"],
                f"registered original changed: {rel}")
        add(files, "official_original/" + rel, path, "registered_official_original")
    add(files, "official_original/inputs/manifest.json", official / "inputs/manifest.json", "official_provenance")
    with zipfile.ZipFile(official / attachment) as archive:
        require(archive.testzip() is None, "original A attachment ZIP has bad CRC")
        names = set(archive.namelist())
        require({f"data/{case}.json" for case in CASES}.issubset(names), "original attachment lacks one or more case graphs")
        require("data/config.txt" in names, "original attachment lacks config.txt")
        require(archived_digest(archive, "data/config.txt") == original_config["sha256"],
                "attachment config differs from registered original")
        for filename, expected in original_code.items():
            require(f"code/{filename}" in names and archived_digest(archive, f"code/{filename}") == expected,
                    f"attachment evaluator differs from registered original: {filename}")
        for case in sorted(CASES):
            actual = digest(inside(source, f"data/raw/A题/data/{case}.json"))
            require(actual == archived_digest(archive, f"data/{case}.json"),
                    f"solver input differs from original attachment: {case}")

    root_manifest = read_json(run / "run_manifest.json")
    require(root_manifest.get("status") == "COMPUTED", "main run is not frozen COMPUTED")
    require(set(root_manifest.get("cases", [])) == CASES and root_manifest.get("cores") == [1, 2, 3, 4, 5]
            and root_manifest.get("scenes") == ["A", "B", "C"], "main manifest does not specify the full matrix")
    batches = root_manifest.get("batches")
    require(isinstance(batches, list) and batches, "main manifest has no completed batches")
    source_hashes = root_manifest.get("solver_source_sha256")
    require(isinstance(source_hashes, dict) and source_hashes, "main manifest lacks solver hashes")
    require(HASH_RE.fullmatch(str(root_manifest.get("config_sha256", ""))), "main manifest lacks config hash")
    require(root_manifest["config_sha256"] == original_config["sha256"],
            "main run config differs from registered original")
    add(files, "run/run_manifest.json", run / "run_manifest.json", "run_manifest")
    add(files, "run/metrics.csv", run / "metrics.csv", "candidate_metrics")
    if (run / "case_sizes.json").is_file():
        add(files, "run/case_sizes.json", run / "case_sizes.json", "run_config")
    report_rows = read_csv(args.report_csv)
    require(len(report_rows) == len(COMBOS), f"report has {len(report_rows)} rows, expected 1500")
    report = unique_rows(report_rows, combo, "report combination")
    require(set(report) == COMBOS, f"report combination coverage differs: missing {len(COMBOS - set(report))}, extra {len(set(report) - COMBOS)}")
    add(files, "reports/main_results.csv", args.report_csv, "derived_report")

    seen_cases = set()
    seen_combos = set()
    used_evaluator = None
    idea_hash = None
    batch_count = 0
    for batch in batches:
        index = number(batch.get("batch"), "batch")
        batch_name = f"batch_{index:02d}"
        child_root = run / batch_name
        require(batch.get("status") == "COMPUTED" and batch.get("returncode") == 0,
                f"batch {index} is not completed successfully")
        child = read_json(child_root / "run_manifest.json")
        require(child.get("status") == "COMPUTED", f"child {batch_name} is not COMPUTED")
        require(child.get("solver_source_sha256") == source_hashes, f"mixed solver source in {batch_name}")
        require(child.get("config_sha256") == root_manifest["config_sha256"], f"mixed config in {batch_name}")
        require(child.get("cores") == [1, 2, 3, 4, 5] and child.get("scenes") == ["A", "B", "C"],
                f"incomplete dimensions in {batch_name}")
        child_cases = set(child.get("cases", []))
        require(child_cases == set(batch.get("cases", [])) and not (child_cases & seen_cases),
                f"duplicate or mismatched case assignment in {batch_name}")
        seen_cases |= child_cases
        current_evaluator = child.get("official_code_sha256")
        require(current_evaluator == original_code, f"{batch_name} used evaluator bytes different from registered originals")
        require(used_evaluator is None or current_evaluator == used_evaluator, "mixed evaluators across batches")
        used_evaluator = current_evaluator
        require(idea_hash is None or child.get("idea_sha256") == idea_hash, "mixed Idea across batches")
        idea_hash = child.get("idea_sha256")
        config = inside(source, child["config"])
        idea = inside(source, child["idea"])
        require(digest(config) == root_manifest["config_sha256"], "source config differs from run")
        require(digest(idea) == idea_hash, "source Idea differs from run")
        add(files, f"run/{batch_name}/run_manifest.json", child_root / "run_manifest.json", "run_manifest")
        add(files, f"run/{batch_name}/metrics.csv", child_root / "metrics.csv", "candidate_metrics")
        candidate_rows = read_csv(child_root / "metrics.csv")
        successful = unique_rows(
            [row for row in candidate_rows if row.get("status") == "AI_VERIFIED"],
            lambda row: (*combo(row), row.get("candidate")), "successful candidate")
        for case in child_cases:
            for cores in range(1, 6):
                for scene in "ABC":
                    key = case, cores, scene
                    require(key not in seen_combos, f"duplicate main combination: {key}")
                    seen_combos.add(key)
                    label = f"{case}/{cores}core/{scene}"
                    require(child.get("combination_status", {}).get(label) == "AI_VERIFIED",
                            f"main combination not AI_VERIFIED: {label}")
                    base = child_root / "cases" / case / f"{cores}core" / scene
                    selection = read_json(base / "final_selection.json")
                    plan = read_json(base / "final_plan.json")
                    plan_hash = plan_digest(plan)
                    require(selection.get("plan_sha256") == plan_hash, f"final plan hash mismatch: {label}")
                    candidate = selection.get("candidate")
                    require(isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", candidate),
                            f"invalid selected candidate: {label}")
                    selected = base / "candidates" / candidate
                    require(read_json(selected / "plan.json") == plan, f"selected candidate plan differs: {label}")
                    raw = read_json(selected / "result.json")
                    checked = read_json(selected / "result_check.json")
                    makespan = number(raw.get("makespan"), f"{label} raw makespan")
                    movement = number(raw.get("data_movement_bytes", {}).get("added_copy_bytes"),
                                      f"{label} raw added copy")
                    require(checked.get("status") == "AI_VERIFIED"
                            and number(checked.get("makespan"), f"{label} check makespan") == makespan
                            and number(checked.get("added_copy_bytes"), f"{label} check added copy") == movement,
                            f"selected result check differs: {label}")
                    require(number(selection.get("makespan"), f"{label} selected makespan") == makespan
                            and number(selection.get("added_copy_bytes"), f"{label} selected added copy") == movement,
                            f"final selection differs from raw result: {label}")
                    row = report[key]
                    require(row.get("status") == "AI_VERIFIED" and row.get("final_plan_sha256") == plan_hash
                            and number(row.get("final_makespan"), f"{label} report makespan") == makespan
                            and number(row.get("final_added_copy_bytes"), f"{label} report added copy") == movement,
                            f"report differs from selected raw result: {label}")
                    candidate_row = successful.get((*key, candidate))
                    require(candidate_row is not None and candidate_row.get("plan_sha256") == plan_hash
                            and number(candidate_row.get("makespan"), f"{label} metric makespan") == makespan,
                            f"candidate metrics differ: {label}")
                    for name, category in (("final_plan.json", "author_final_plan"),
                                           ("final_selection.json", "author_selection")):
                        add(files, f"run/{batch_name}/cases/{label}/{name}", base / name, category)
                    for name, category in (("plan.json", "author_selected_candidate_plan"),
                                           ("result.json", "raw_original_evaluator_result"),
                                           ("result_check.json", "author_result_check")):
                        add(files, f"run/{batch_name}/cases/{label}/candidates/{candidate}/{name}",
                            selected / name, category)
        batch_count += 1
    require(seen_cases == CASES and seen_combos == COMBOS, "batch coverage is not the full 100-case matrix")

    for rel, expected in source_hashes.items():
        require(HASH_RE.fullmatch(expected) is not None, f"invalid source hash: {rel}")
        require(digest(inside(source, rel)) == expected, f"solver source changed since run: {rel}")
    source_files = sorted(path for folder in ("src", "scripts", "tests")
                          for path in (source / folder).rglob("*.py") if "__pycache__" not in path.parts)
    require(source_files, "source root has no solver scripts or tests")
    required_source = {"scripts/run_experiment.py", "scripts/run_full_matrix.py"}
    required_source |= {path.relative_to(source).as_posix() for path in source_files
                        if path.relative_to(source).parts[0] == "src"}
    require(required_source.issubset(source_hashes),
            f"run manifest does not bind all solver modules: {sorted(required_source - set(source_hashes))}")
    for path in source_files:
        rel = path.relative_to(source).as_posix()
        add(files, "author_source/" + rel, path,
            "run_manifest_bound_source" if rel in source_hashes else "included_helper_or_test")
    for rel in sorted({*source_hashes, child["config"], child["idea"]}):
        if rel in source_hashes and rel.startswith(("src/", "scripts/", "tests/")):
            continue
        add(files, "author_source/" + rel, inside(source, rel), "run_manifest_bound_source")
    for path in sorted(source.glob("requirements*.txt")):
        add(files, "author_source/" + path.name, path, "dependency_spec")
    for filename, expected in original_code.items():
        evaluator_file = inside(args.evaluator_dir.resolve(), filename)
        require(digest(evaluator_file) == expected, f"selected evaluator differs from registered original: {filename}")
        add(files, "runtime_evaluator/" + filename, evaluator_file, "registered_official_original_used_in_run")

    baseline_manifest = read_json(baseline / "run_manifest.json")
    require(baseline_manifest.get("status") == "COMPUTED", "baseline run is not COMPUTED")
    baseline_rows = read_csv(baseline / "metrics.csv")
    require(len(baseline_rows) == 100, f"baseline has {len(baseline_rows)} rows, expected 100")
    baseline_map = unique_rows(baseline_rows, lambda row: row.get("case"), "baseline case")
    require(set(baseline_map) == CASES, "baseline case coverage differs from 100 cases")
    add(files, "baseline/run_manifest.json", baseline / "run_manifest.json", "baseline_manifest")
    add(files, "baseline/metrics.csv", baseline / "metrics.csv", "baseline_metrics")
    baseline_cases = set()
    for batch in baseline_manifest.get("batches", []):
        index = number(batch.get("batch"), "baseline batch")
        name = f"batch_{index:02d}"
        require(batch.get("status") == "COMPUTED" and batch.get("returncode") == 0,
                f"baseline {name} is not completed successfully")
        child_root = baseline / name
        child = read_json(child_root / "run_manifest.json")
        require(child.get("status") == "COMPUTED" and child.get("official_code_sha256") == original_code,
                f"baseline {name} did not use registered original evaluator")
        cases = set(child.get("cases", []))
        require(cases == set(batch.get("cases", [])) and not (cases & baseline_cases),
                f"duplicate or mismatched baseline cases: {name}")
        baseline_cases |= cases
        add(files, f"baseline/{name}/run_manifest.json", child_root / "run_manifest.json", "baseline_manifest")
        add(files, f"baseline/{name}/metrics.csv", child_root / "metrics.csv", "baseline_metrics")
        child_rows = unique_rows(read_csv(child_root / "metrics.csv"), lambda row: row.get("case"), "baseline batch row")
        require(set(child_rows) == cases, f"baseline batch metrics coverage differs: {name}")
        for case in cases:
            raw_path = child_root / "cases" / case / "result.json"
            raw = read_json(raw_path)
            makespan = number(raw.get("makespan"), f"{case} baseline raw makespan")
            require(baseline_map[case].get("status") == "AI_VERIFIED"
                    and child_rows[case].get("status") == "AI_VERIFIED"
                    and number(baseline_map[case].get("makespan"), f"{case} baseline CSV makespan") == makespan
                    and number(child_rows[case].get("makespan"), f"{case} baseline child makespan") == makespan,
                    f"baseline raw result differs from metrics: {case}")
            add(files, f"baseline/{name}/cases/{case}/result.json", raw_path, "raw_original_evaluator_baseline")
    require(baseline_cases == CASES, "baseline batches do not cover exactly 100 cases")
    require(baseline_manifest.get("official_code_sha256", original_code) == original_code,
            "baseline root evaluator differs from original")
    report = {
        "status": "AUDIT_PASSED",
        "main_combinations": len(seen_combos),
        "baseline_cases": len(baseline_cases),
        "batches": batch_count,
        "source_hashes_checked": len(source_hashes),
        "original_evaluator_hashes_checked": len(original_code),
        "files": len(files),
        "input_bytes": sum(path.stat().st_size for path, _ in files.values()),
        "official_limit_bytes": LIMIT_BYTES,
        "human_scientific_review": "NOT_ASSESSED",
        "platform_submission": "NOT_SUBMITTED",
    }
    return files, report


def package(files: dict[str, tuple[Path, str]], report: dict, output: Path,
            compact: bool = False, full_archive: Path | None = None) -> dict:
    require(not output.exists(), f"refusing existing output: {output}")
    require(output.parent.is_dir(), f"output parent missing: {output.parent}")
    raw_categories = {"raw_original_evaluator_result", "raw_original_evaluator_baseline"}
    omitted = [(rel, path, category) for rel, (path, category) in sorted(files.items())
               if compact and category in raw_categories]
    included = {rel: item for rel, item in files.items() if not (compact and item[1] in raw_categories)}
    records = [{"path": rel, "category": category, "bytes": path.stat().st_size, "sha256": digest(path)}
               for rel, (path, category) in sorted(included.items())]
    recorded_hashes = {record["path"]: record["sha256"] for record in records}
    raw_hash_rows = [{"path": rel, "bytes": path.stat().st_size, "sha256": digest(path)}
                     for rel, path, _ in omitted]
    manifest = {"audit": report, "package_kind": "COMPACT_SUBMISSION_CANDIDATE" if compact else "FULL_AUTHOR_REPRODUCTION",
                "files": records, "omitted_raw_result_count": len(raw_hash_rows)}
    instructions = (
        "# A-problem author reproducibility package\n\n"
        "The registered original attachment is in official_original/; it contains all 100 graphs and the original evaluator. "
        "Unpack it into data/raw/A题/ so that data/raw/A题/data/{case}.json and config.txt exist. "
        "The runnable author code is in author_source/. Copy runtime_evaluator/*.py to vendor/official_evaluator/. "
        "Install author_source/requirements*.txt if present, then run scripts/run_full_matrix.py with a new output directory; "
        "the run manifests record the case partitions, solver settings, environment versions and source hashes.\n\n"
        "run/ stores the frozen manifests, 1500 selected plans, selected candidate plans, "
        "result checks and candidate metrics. baseline/ stores 100 original single-core rows. "
        "reports/main_results.csv is a derived table cross-checked against every selected raw result. "
        "MANIFEST.json classifies every file and records SHA-256. Original official bytes, author source, "
        "raw evaluator outputs and derived reports have separate categories.\n\n"
        "The package is an author evidence bundle, not evidence of human scientific review or platform submission. "
        "The 2026 announcement limits optional uploaded attachments to 50M; check the measured ZIP size in the audit output.\n"
    )
    if compact:
        instructions += (
            "\n## Compact candidate limitation\n\n"
            "This archive omits the 1500 selected raw evaluator event results and 100 raw baseline results. "
            "RAW_RESULT_HASHES.csv records their validated paths, sizes and SHA-256 values. "
            "It is incomplete for full raw-result reproduction. Preserve the frozen run and baseline directories"
            + (f" and the complete internal archive at {full_archive}" if full_archive else " and generate a complete internal archive with --output")
            + ". Being under 50M does not establish that the platform will accept its format or contents.\n"
        )
    else:
        instructions += "\nThe selected raw evaluator event outputs and raw A0 results are included under run/ and baseline/.\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".tmp", dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for rel, (path, _) in sorted(included.items()):
                require(digest(path) == recorded_hashes[rel],
                        f"input changed during packaging: {path}")
                archive.write(path, rel)
            archive.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            archive.writestr("README.md", instructions)
            if compact:
                lines = ["path,bytes,sha256"] + [f'{row["path"]},{row["bytes"]},{row["sha256"]}' for row in raw_hash_rows]
                archive.writestr("RAW_RESULT_HASHES.csv", "\n".join(lines) + "\n")
        with zipfile.ZipFile(temporary) as archive:
            require(archive.testzip() is None, "package CRC failed")
            expected = set(included) | {"MANIFEST.json", "README.md"}
            if compact:
                expected.add("RAW_RESULT_HASHES.csv")
            require(set(archive.namelist()) == expected,
                    "package file list differs from manifest")
        temporary.rename(output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    report = dict(report, package_kind=manifest["package_kind"], archive=str(output), archive_bytes=output.stat().st_size,
                  archive_sha256=digest(output), within_official_50m=output.stat().st_size <= LIMIT_BYTES)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="frozen runnable solver root")
    parser.add_argument("--run-root", type=Path, required=True, help="completed 100-case main matrix")
    parser.add_argument("--baseline-root", type=Path, required=True, help="completed 100-case A0 run")
    parser.add_argument("--report-csv", type=Path, required=True, help="new 1500-row final report")
    parser.add_argument("--official-workspace", type=Path, required=True, help="workspace with registered inputs/manifest.json")
    parser.add_argument("--evaluator-dir", type=Path, required=True, help="exact evaluator directory recorded by the run")
    parser.add_argument("--output", type=Path, help="new author ZIP path; omit for a read-only audit")
    parser.add_argument("--compact-output", type=Path, help="new incomplete 50M submission-candidate ZIP; same full audit required")
    args = parser.parse_args()
    try:
        files, report = audit(args)
        require(args.output is None or args.compact_output is None
                or args.output.resolve() != args.compact_output.resolve(), "full and compact output paths must differ")
        require(args.output is None or not args.output.exists(), f"refusing existing output: {args.output}")
        require(args.compact_output is None or not args.compact_output.exists(),
                f"refusing existing compact output: {args.compact_output}")
        outputs = {}
        if args.output is not None:
            outputs["full"] = package(files, report, args.output.resolve())
        if args.compact_output is not None:
            outputs["compact"] = package(files, report, args.compact_output.resolve(),
                                         compact=True, full_archive=args.output.resolve() if args.output else None)
        if outputs:
            report = dict(report, packages=outputs)
    except (AuditError, OSError, zipfile.BadZipFile, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
