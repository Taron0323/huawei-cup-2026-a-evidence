"""Report unfinished paper/support items; never infer platform or human approval."""

import argparse
import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

from workspace import ROOT, csv_rows, local, read_json, sha


def check_paper(pdf, team):
    reader = PdfReader(pdf)
    texts = [p.extract_text() or "" for p in reader.pages]
    issues = []
    if len(texts) < 3:
        issues.append("Missing cover/abstract/body pages")
    placeholders = ("待填写", "待核验", "赛前模板", "尚未取得正式赛题")
    for i, text in enumerate(texts, 1):
        if any(x in text for x in placeholders):
            issues.append("Unfilled preparation content on PDF page " + str(i))
    identities = [team.get("team_number"), team.get("school"), team.get("school_code")]
    identities += [v for m in team.get("members", []) for v in (m.get("name"), m.get("student_id"))]
    identities = [str(v) for v in identities if v]
    for i, text in enumerate(texts[1:], 2):
        compact = re.sub(r"\s+", "", text)
        if any(re.sub(r"\s+", "", token) in compact for token in identities):
            issues.append("Known team identity found on PDF page " + str(i))
    if not identities:
        issues.append("Team identity fields unavailable; anonymity token check NOT_ASSESSED")
    metadata = str(reader.metadata or {})
    if any(token in metadata for token in identities):
        issues.append("Known team identity found in PDF metadata")
    return {"pages": len(texts), "issues": issues,
            "manual_checks": ["four official logos and accurate cover", "abstract at most two pages", "fonts and all figures", "identities inside images", "citations and AI annotations at each actual use"]}


def check_support(root):
    folder = root / "support"
    rows = csv_rows(folder / "MANIFEST.csv")
    files = sorted(p for dirname in ("code", "data", "results") for p in (folder / dirname).rglob("*")
                   if p.is_file() and p.name not in (".gitkeep", ".DS_Store"))
    actual = {p.relative_to(folder).as_posix() for p in files}
    declared = {r["path"] for r in rows}
    issues = []
    if actual != declared:
        issues.append("Manifest differs from actual files: " + str(sorted(actual ^ declared)))
    for row in rows:
        path = local(folder, row["path"])
        if not path.is_file() or sha(path) != row["sha256"]:
            issues.append("Missing/changed support file: " + row["path"])
        if not all(row[k] for k in ("role", "question", "paper_location")):
            issues.append("Incomplete paper mapping: " + row["path"])
        if path.suffix.lower() in (".py", ".m", ".r", ".jl", ".txt", ".md", ".csv", ".json") and path.exists():
            text = path.read_text(errors="replace")
            if "/Users/" in text or re.search(r"[A-Za-z]:\\+Users\\+", text):
                issues.append("Private absolute path in: " + row["path"])
    size = sum(p.stat().st_size for p in files)
    if size > 50_000_000:
        issues.append("Uncompressed support files exceed 50,000,000 bytes; final archive size must be checked separately")
    return {"status": "NOT_PREPARED" if not rows else ("ISSUES_FOUND" if issues else "MANIFEST_VERIFIED"),
            "files": len(files), "uncompressed_bytes": size, "issues": issues,
            "archive_format": "CONFIRM_WITH_CURRENT_PROBLEM_AND_PLATFORM", "official_archive_size_limit_bytes": 50_000_000}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=ROOT / "paper/preview/latex/template.pdf")
    parser.add_argument("--final", action="store_true", help="Fail on unresolved paper issues; does not certify scientific correctness")
    args = parser.parse_args()
    team_path = ROOT / "prep/team.local.json"
    team = read_json(team_path) if team_path.exists() else read_json(ROOT / "prep/team.example.json")
    result = {"paper": check_paper(args.pdf, team), "support": check_support(ROOT),
              "human_review": "NOT_ASSESSED", "platform_submission": "NOT_ASSESSED"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.final and (result["paper"]["issues"] or result["support"]["issues"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
