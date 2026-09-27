"""Package the verified A draft and run an extracted, isolated smoke test.

AI-assisted: Codex / OpenAI, 2026-09-23; model/release UNVERIFIED.
"""

import csv
from datetime import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from workspace import check, environment

ROOT = Path(__file__).resolve().parents[1]
RUN = "auto_solve_20260923_120249"
REVIEW = ROOT / "review/auto_solve/20260923_120249/06_delivery"
NAME = "A题自动求解_20260923"


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    deliveries = ROOT / "deliveries"
    deliveries.mkdir(exist_ok=True)
    target = deliveries / NAME
    archive = deliveries / (NAME + ".zip")
    extracted = REVIEW / "extracted"
    if target.exists() or archive.exists() or extracted.exists():
        raise FileExistsError("Delivery exists; preserve it and choose a new dated name before repackaging")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    workspace_result = check(ROOT)
    env_report = environment()
    env_report["system_versions"] = {}
    for executable, flags in (("xelatex", ["--version"]), ("latexmk", ["-version"]),
                              ("pdftotext", ["-v"]), ("clang", ["--version"]), ("soffice", ["--version"])):
        if shutil.which(executable):
            p = subprocess.run([executable, *flags], capture_output=True, text=True, timeout=20)
            env_report["system_versions"][executable] = (p.stdout + p.stderr).strip().splitlines()[:5]
        else:
            env_report["system_versions"][executable] = "NOT_ON_PATH"
    dump(REVIEW / "environment.json", env_report)
    regression = subprocess.run([sys.executable, "tools/test_workflow.py"], cwd=ROOT, env=env,
                                capture_output=True, text=True)
    (REVIEW / "workflow_tests.log").write_text(regression.stdout + regression.stderr)
    assert regression.returncode == 0, "Workflow regression failed; see retained log"
    dump(REVIEW / "final_checks.json", {"checked_at": datetime.now().astimezone().isoformat(),
        "workspace": workspace_result, "workflow_tests_exit_code": regression.returncode,
        "workflow_test_count": 9, "paper_qa": "review/auto_solve/20260923_120249/05_paper/pdf_qa.json",
        "claims": "review/auto_solve/20260923_120249/03_validation/claim_verification.json",
        "human_review": "NOT_ASSESSED", "submission": "NOT_SUBMITTED"})
    stage = ROOT / "Each Stage Review Work/20260923_final_delivery"
    (stage / "after").mkdir(exist_ok=True)
    diffs = []
    for name in ("STATUS.md", "HANDOFF.md", "README.md", "CONTEXT.md", "REQ.md", "IDEA.md", "paper/latex/main.tex", "tools/a_pdf_qa.py"):
        path = ROOT / name
        shutil.copyfile(path, stage / "after" / path.name)
        old = stage / "before" / path.name
        diffs.extend(difflib.unified_diff(old.read_text().splitlines(True), path.read_text().splitlines(True),
                                         fromfile="before/"+name, tofile="after/"+name))
    (stage / "changes.diff").write_text("".join(diffs))
    dump(stage / "validation.json", {"workspace": workspace_result, "workflow_tests": "PASS",
        "scope": "A draft wording, footer QA, evidence, state and reproduction delivery; input bytes preserved"})

    files = set()
    for name in ("AGENTS.md", "README.md", "STATUS.md", "HANDOFF.md", "CONTEXT.md", "REQ.md", "IDEA.md",
                 "requirements.txt", "run_a.py", "paper/A题论文初稿_20260923.pdf", "paper/word/a-frontmatter.docx",
                 "paper/word/working-template.docx", "paper/latex/build/compile.log",
                 "prompts/A题自动求解用户原始提示词.txt"):
        files.add(ROOT / name)
    for name in ("inputs", "src/a_solver", "evidence", "official/20260921", "paper/latex", "support",
                 f"results/{RUN}", "results/entry_check_20260923_1552", f"figures/{RUN}",
                 "review/auto_solve/20260923_110147/00_inventory", "review/auto_solve/20260923_110147/01_selection",
                 "review/auto_solve/20260923_120249", "Each Stage Review Work/20260923_final_delivery"):
        for path in (ROOT / name).rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if any(part in {".venv", "__pycache__", "workspace", "extracted", ".git"} for part in rel.parts):
                continue
            if path.name in {".DS_Store", ".gitkeep", "team.local.json"} or path.suffix == ".pyc":
                continue
            if rel.parts[:3] == ("paper", "latex", "build"):
                continue
            files.add(path)
    files.update((ROOT / "tools").glob("a_*.py"))
    files.update(ROOT / "tools" / n for n in ("workspace.py", "build_paper.py", "test_workflow.py", "check_submission.py", "fonts.conf"))
    target.mkdir()
    manifest = []
    for path in sorted(files):
        assert path.is_file() and not path.is_symlink(), path
        rel = path.relative_to(ROOT)
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        digest = sha(path)
        assert sha(dest) == digest
        manifest.append({"path": rel.as_posix(), "bytes": path.stat().st_size, "sha256": digest})
    dump(target / "FILE_MANIFEST.json", {"files": manifest,
        "manifest_excludes": ["FILE_MANIFEST.json", "SHA256SUMS.csv"],
        "contents": "Read-only A inputs, code, results, paper, evidence and provenance; no private team config, commercial fonts or virtualenv",
        "duplicate_clean_run_outputs": "Excluded; copy manifest, logs, resource traces and exact comparisons retained"})
    with (target / "SHA256SUMS.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=("path", "bytes", "sha256"))
        writer.writeheader()
        writer.writerows(manifest)
    print(json.dumps({"phase": "copied", "files": len(manifest), "uncompressed_bytes": sum(r["bytes"] for r in manifest)}), flush=True)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as z:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                z.write(path, NAME + "/" + path.relative_to(target).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None, "Archive CRC mismatch"
        extracted.mkdir()
        z.extractall(extracted)
    unpacked = extracted / NAME
    expected = {r["path"] for r in manifest} | {"FILE_MANIFEST.json", "SHA256SUMS.csv"}
    actual = {p.relative_to(unpacked).as_posix() for p in unpacked.rglob("*") if p.is_file()}
    assert actual == expected, "Unlisted or missing archive file"
    for row in manifest:
        assert sha(unpacked / row["path"]) == row["sha256"], row["path"]
    unpacked_check = check(unpacked)
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(unpacked / ".venv")], check=True, env=env)
    python = unpacked / ".venv/bin/python"
    command = [str(python), "run_a.py", "--mode", "smoke", "--workers", "14", "--output-root", "results/package_smoke"]
    print("Archive hashes verified; starting 45-evaluation smoke in an isolated extracted environment", flush=True)
    with (REVIEW / "package_smoke.log").open("w") as log:
        result = subprocess.run(command, cwd=unpacked, env=env, stdout=log, stderr=subprocess.STDOUT)
    assert result.returncode == 0, "Unpacked smoke failed; see package_smoke.log"
    original = rows(ROOT / f"results/{RUN}/smoke_v1/metrics.csv")
    rebuilt = rows(unpacked / "results/package_smoke/smoke_v1/metrics.csv")
    key_fields = ("case", "cores", "algorithm", "problem", "seed", "block_size")
    key = lambda r: tuple(r[k] for k in key_fields)
    left, right = {key(r): r for r in original}, {key(r): r for r in rebuilt}
    assert len(left) == len(right) == 45 and left.keys() == right.keys()
    fields = ("makespan", "added_copy_bytes", "scheduled_copy_bytes", "cache_hit_rate", "plan_sha256", "result_sha256", "status")
    differences = [{"key": k, "field": f, "original": left[k][f], "rebuilt": right[k][f]}
                   for k in left for f in fields if left[k][f] != right[k][f]]
    assert not differences, differences[:3]
    report = {"status": "AI_VERIFIED", "completed_at": datetime.now().astimezone().isoformat(),
        "zip_file": str(archive), "zip_sha256": sha(archive), "zip_bytes": archive.stat().st_size,
        "crc": "PASS", "manifest_files": len(manifest), "hash_matches": len(manifest),
        "unlisted_files": [], "browsable_directory": str(target), "unpacked_directory": str(unpacked),
        "unpacked_workspace_check": unpacked_check, "smoke_command": command,
        "smoke_environment": "New venv without pip/system site packages", "smoke_exit_code": result.returncode,
        "smoke_rows": len(rebuilt), "smoke_differences": differences, "comparison_tolerance": 0,
        "human_review": "NOT_ASSESSED", "submission": "NOT_SUBMITTED"}
    dump(deliveries / (NAME + ".verification.json"), report)
    dump(REVIEW / "package_verification.json", report)
    shutil.copyfile(unpacked / "results/package_smoke/smoke_v1/metrics.csv", REVIEW / "package_smoke_metrics.csv")
    print(json.dumps({k: report[k] for k in ("status", "zip_bytes", "manifest_files", "smoke_rows", "smoke_differences")}), flush=True)


if __name__ == "__main__":
    main()
