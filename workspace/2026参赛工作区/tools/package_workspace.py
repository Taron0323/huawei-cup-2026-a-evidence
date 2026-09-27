"""Package the prepared workspace, verify its bytes, and test a fresh extraction."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from workspace import ROOT, read_json, record, require, sha, verify_records, write_json


def included(path, excluded):
    rel = path.relative_to(ROOT)
    if any(rel == skip or skip in rel.parents for skip in excluded):
        return False
    if any(p in rel.parts for p in (".venv", "__pycache__", ".git", "private-receipts", "build")):
        return False
    return path.is_file() and path.name not in (".DS_Store", "team.local.json", "package-manifest.json")


def main(target, excluded):
    target = target.resolve()
    require(not target.is_relative_to(ROOT), "Write archive outside the source workspace")
    require(not target.exists(), "Archive already exists; choose a new filename")
    files = sorted(p for p in ROOT.rglob("*") if included(p, excluded))
    manifest = {"scope": "PREPARATION_BACKUP_NOT_CONTEST_SUBMISSION", "files": [record(ROOT, p) for p in files],
                "excluded": [".venv", "__pycache__", "build", "prep/team.local.json", "submission/private-receipts"] + [p.as_posix() for p in excluded]}
    write_json(ROOT / "package-manifest.json", manifest)
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for p in files + [ROOT / "package-manifest.json"]:
            archive.write(p, (Path(ROOT.name) / p.relative_to(ROOT)).as_posix())
    tests = []
    with tempfile.TemporaryDirectory(prefix="huawei2026-portability-") as directory:
        with ZipFile(target) as archive:
            require(archive.testzip() is None, "Archive CRC failed")
            for name in archive.namelist():
                require(not name.startswith("/") and ".." not in Path(name).parts, "Unsafe archive path")
            archive.extractall(directory)
        extracted = Path(directory) / ROOT.name
        verify_records(extracted, manifest["files"])
        for args in (["tools/workspace.py", "check"], ["tools/test_workflow.py"],
                     ["practice/transport/run.py", "--run-id", "portable-check"], ["tools/build_paper.py", "latex"]):
            completed = subprocess.run([sys.executable] + args, cwd=extracted, capture_output=True, text=True)
            tests.append({"command": ["python"] + args, "exit_code": completed.returncode,
                          "output": (completed.stdout + completed.stderr)[-5000:]})
            require(completed.returncode == 0, "Fresh-extraction command failed: " + str(args) + "\n" + tests[-1]["output"])
        original_metric = (ROOT / "practice/transport/runs/rehearsal-01/metrics.csv").read_bytes()
        repeated_metric = (extracted / "practice/transport/runs/portable-check/metrics.csv").read_bytes()
        require(original_metric == repeated_metric, "Fresh-extraction result changed")
    report = {"archive": target.name, "sha256": sha(target), "bytes": target.stat().st_size,
              "entries": len(files) + 1, "crc": "PASS", "extracted_hashes": "PASS",
              "fresh_extraction_commands": tests, "metric_reproducibility": "PASS",
              "environment_note": "Fresh directory on the same machine, using the installed Python/system tools; not a second-machine test"}
    write_json(target.with_suffix(".verification.json"), report)
    print(json.dumps({k: v for k, v in report.items() if k != "fresh_extraction_commands"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--exclude", action="append", type=Path, default=[], help="Exclude an explicitly out-of-scope relative directory")
    args = parser.parse_args()
    main(args.output, args.exclude)
