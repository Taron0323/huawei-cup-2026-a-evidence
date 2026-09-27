"""Small local checks for provenance, evidence, and exact-byte PDF freezing."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import platform
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def local(root, name):
    path = (root / name).resolve()
    require(path.is_relative_to(root.resolve()), "Path outside project: " + name)
    return path


def record(root, path):
    return {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}


def verify_records(root, records):
    seen = set()
    for row in records:
        require(row["path"] not in seen, "Duplicate file record: " + row["path"])
        seen.add(row["path"])
        path = local(root, row["path"])
        require(path.is_file(), "Missing file: " + row["path"])
        require(sha(path) == row["sha256"], "SHA-256 mismatch: " + row["path"])
        if "bytes" in row:
            require(path.stat().st_size == row["bytes"], "Byte count mismatch: " + row["path"])


def inputs(root, register=False):
    target = root / "inputs/manifest.json"
    old = read_json(target)
    verify_records(root, old)
    paths = sorted(p for folder in ("problem", "raw") for p in (root / "inputs" / folder).rglob("*")
                   if p.is_file() and p.name not in (".gitkeep", ".DS_Store"))
    current = [record(root, p) for p in paths]
    if register:
        old_paths = {x["path"] for x in old}
        added = [dict(x, registered_at=datetime.now().astimezone().isoformat()) for x in current if x["path"] not in old_paths]
        write_json(target, old + added)
    else:
        require({x["path"] for x in current} == {x["path"] for x in old}, "Unregistered input files; run register")
    return {"count": len(current), "status": "VERIFIED" if current else "NOT_RECEIVED"}


def csv_rows(path, unique_ids=True):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        require(bool(reader.fieldnames), "Missing CSV header: " + str(path))
        rows = list(reader)
        require(all(None not in row and None not in row.values() for row in rows), "Malformed CSV: " + str(path))
        ids = [row[reader.fieldnames[0]] for row in rows]
        if unique_ids:
            require(all(ids) and len(ids) == len(set(ids)), "Missing/duplicate IDs: " + str(path))
    return rows


def check_claims(root, rows):
    for row in rows:
        for field in ("claim_id", "statement", "result_file", "code_file", "run_id", "paper_location", "verification_file"):
            require(row.get(field), "Missing claim field: " + field)
        result = local(root, row["result_file"])
        code = local(root, row["code_file"])
        verification_path = local(root, row["verification_file"])
        require(code.is_file() and result.is_file() and verification_path.is_file(), "Missing claim evidence")
        if row.get("value"):
            table = csv_rows(result, unique_ids=False)
            index = int(row["result_row"]) - 1
            require(0 <= index < len(table), "Result row out of range")
            value = float(table[index][row["result_column"]])
            claimed, tolerance = float(row["value"]), float(row["tolerance"])
            require(all(math.isfinite(v) for v in (value, claimed, tolerance)) and tolerance >= 0, "Invalid claim numeric value")
            require(abs(value - claimed) <= tolerance, "Claim disagrees with result cell: " + row["claim_id"])
        verification = read_json(verification_path)
        require(verification.get("run_id") == row["run_id"], "Verification run_id mismatch")
        require(verification.get("checks") and all(c.get("passed") is True for c in verification["checks"]), "Missing/failed verification checks")
        linked = verification.get("files", [])
        verify_records(root, linked)
        require({row["result_file"], row["code_file"]}.issubset({x["path"] for x in linked}), "Verification not bound to result and code")
        run = read_json(local(root, "results/" + row["run_id"] + "/run.json"))
        require(run.get("run_id") == row["run_id"], "Run manifest mismatch")
        for field in ("inputs", "code", "outputs"):
            require(run.get(field), "Empty run provenance: " + field)
            verify_records(root, run[field])
        require(row["code_file"] in {x["path"] for x in run["code"]}, "Claim code absent from run")
        require(row["result_file"] in {x["path"] for x in run["outputs"]}, "Claim result absent from run")
        if row.get("figure_file"):
            require(local(root, row["figure_file"]).is_file(), "Missing claim figure")
        if row.get("human_review") == "HUMAN_VERIFIED":
            reviews = csv_rows(root / "evidence/human_review.csv")
            require(any(r["reviewer"] and r["reviewed_at"] and r["outcome"] == "PASS" and
                        r["evidence_file"] == row["verification_file"] for r in reviews), "Human review record missing")


def check(root):
    for name in ("README.md", "AGENTS.md", "REQ.md", "CONTEXT.md", "IDEA.md", "STATUS.md", "HANDOFF.md",
                 "paper/word/working-template.docx", "paper/latex/main.tex", "paper/latex/frontmatter.pdf"):
        require((root / name).is_file(), "Missing workbench file: " + name)
    official = root / "official/20260921"
    records = read_json(official / "来源清单.json")
    verify_records(official, records)
    inp = inputs(root)
    tables = {p.stem: csv_rows(p) for p in sorted((root / "evidence").glob("*.csv"))}
    require(set(tables) == {"requirements", "parameters", "claims", "figures", "ai_usage", "human_review", "references"}, "Missing evidence tables")
    for rows in tables.values():
        for row in rows:
            for key in ("source_file", "result_file", "code_file", "figure_file", "verification_file", "evidence_file", "prompt_file", "source_path", "local_file"):
                if row.get(key):
                    require(local(root, row[key]).is_file(), "Missing evidence reference: " + row[key])
    check_claims(root, tables["claims"])
    for row in tables["figures"]:
        for kind in ("result", "code", "figure"):
            require(sha(local(root, row[kind + "_file"])) == row[kind + "_sha256"], "Figure lineage mismatch")
    for row in tables["ai_usage"]:
        for key in ("tool", "model", "developer", "version_release_date", "version_evidence"):
            require(row[key] and row[key] not in ("PENDING", "待核验"), "Incomplete AI disclosure: " + key)
    return {"software_structure": "PASS", "official_records": len(records), "inputs": inp,
            "evidence_rows": {k: len(v) for k, v in tables.items()},
            "formal_scientific_review": "NOT_ASSESSED", "human_review": "NOT_ASSESSED", "submission": "NOT_SUBMITTED"}


def freeze(pdf, output, problem, team):
    require(problem in "ABCDEF" and len(problem) == 1, "Invalid problem letter")
    require(re.fullmatch(r"[0-9]+", team) is not None, "Team number must be the real numeric team ID")
    data = pdf.read_bytes()
    require(data.startswith(b"%PDF-"), "Not a PDF file")
    output.mkdir(parents=True, exist_ok=False)
    name = problem + team + ".pdf"
    dest = output / name
    dest.write_bytes(data)
    info = {"filename": name, "problem": problem, "team": team, "bytes": len(data),
            "md5": hashlib.md5(data).hexdigest(), "sha256": hashlib.sha256(data).hexdigest(),
            "frozen_at": datetime.now().astimezone().isoformat(),
            "official_tool_crosscheck": "PENDING", "platform_submission": "NOT_SUBMITTED"}
    write_json(output / "freeze.json", info)
    dest.chmod(0o444)
    return info


def verify_freeze(output):
    info = read_json(output / "freeze.json")
    data = local(output, info["filename"]).read_bytes()
    require(len(data) == info["bytes"] and hashlib.sha256(data).hexdigest() == info["sha256"]
            and hashlib.md5(data).hexdigest() == info["md5"], "Frozen PDF bytes changed")
    return {"bytes_verified": True, "md5": info["md5"], "platform_submission": info["platform_submission"]}


def environment():
    packages = {}
    for name in ("numpy", "scipy", "matplotlib", "beautifulsoup4", "python-docx", "pypdf"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
            "packages": packages, "commands": {x: shutil.which(x) for x in ("latexmk", "xelatex", "soffice", "pdftotext", "pdftoppm", "rar")}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("env", "register", "check"):
        sub.add_parser(name)
    f = sub.add_parser("freeze")
    for name in ("pdf", "problem", "team", "tag"):
        f.add_argument("--" + name, required=True)
    sub.add_parser("verify-freeze").add_argument("directory")
    args = p.parse_args()
    if args.cmd == "env":
        result = environment()
    elif args.cmd == "register":
        result = inputs(ROOT, register=True)
    elif args.cmd == "check":
        result = check(ROOT)
    elif args.cmd == "freeze":
        require(re.fullmatch(r"[A-Za-z0-9_-]+", args.tag) is not None, "Invalid freeze tag")
        result = freeze(Path(args.pdf), ROOT / "submission/frozen" / args.tag, args.problem, args.team)
    else:
        result = verify_freeze(Path(args.directory))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        raise SystemExit(1)
