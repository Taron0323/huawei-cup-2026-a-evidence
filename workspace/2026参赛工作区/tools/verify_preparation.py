"""Record preparation checks without marking any formal contest step complete."""

import hashlib
import importlib.metadata
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote
from zipfile import ZipFile

from docx import Document
from PIL import Image, ImageChops
import numpy as np
from pypdf import PdfReader

from workspace import ROOT, check, environment, read_json, record, require, sha, verify_records, write_json


def main():
    report = {"workbench": check(ROOT), "environment": environment()}
    stage = ROOT / "Each Stage Review Work/20260921_01_initial"
    initial = read_json(stage / "original_inventory.json")
    verify_records(ROOT.parent, initial["files"])
    report["historical_preservation"] = {"files": len(initial["files"]), "all_unchanged_this_turn": True}
    old_root = ROOT.parent / "2026官方资料_截至20260916"
    old = {x["source_url"]: x for x in read_json(old_root / "来源清单.json") if x["kind"] == "original_attachment"}
    current_root = ROOT / "official/20260921"
    current = read_json(current_root / "来源清单.json")
    changed = [x["path"] for x in current if x["kind"] == "original_attachment" and x["source_url"] in old and x["sha256"] != old[x["source_url"]]["sha256"]]
    report["official"] = {"source_records": len(current), "attachment_changes_since_0916": changed,
                          "pages": len(list((current_root / "01_官方网页").glob("*.html"))),
                          "attachments": len(list((current_root / "02_官方附件").iterdir()))}
    historical_goal = ROOT.parent / "华为杯中国研究生数学建模竞赛_流程复盘包_20260913/下一届总控Goal提示词.md"
    manifest = read_json(historical_goal.parent / "文件清单.json")
    expected = next(x for x in manifest["files"] if x["path"] == historical_goal.name)
    data = historical_goal.read_bytes()
    whitespace_only = len(data) == expected["bytes"] + 2 and hashlib.sha256(data[:-2]).hexdigest() == expected["sha256"] and data[-2:] == b"\n\n"
    report["historical_manifest_drift"] = {"file": str(historical_goal.relative_to(ROOT.parent)), "two_appended_newlines_only": whitespace_only,
                                           "expected_sha256": expected["sha256"], "actual_sha256": sha(historical_goal)}
    before = ROOT / "Each Stage Review Work/20260921_02_templates/before-working-template.docx"
    after = ROOT / "paper/word/working-template.docx"
    with ZipFile(before) as a, ZipFile(after) as b:
        require(set(a.namelist()) == set(b.namelist()), "DOCX package parts changed")
        differences = [n for n in a.namelist() if a.read(n) != b.read(n)]
    require(differences == ["word/document.xml"], "Unexpected DOCX package edits")
    doc = Document(after)
    require(len(doc.inline_shapes) == 4, "Expected four official logos")
    image_checks = []
    for number in range(1, 5):
        reference = Image.open(ROOT / f"paper/preview/reference/page-{number}.png").convert("RGB")
        working = Image.open(ROOT / f"paper/preview/word/page-{number}.png").convert("RGB")
        if number == 1:
            reference = reference.crop((0, 0, reference.width, int(reference.height * .9)))
            working = working.crop((0, 0, working.width, int(working.height * .9)))
        elif number == 2:
            reference = reference.crop((0, 0, reference.width, int(reference.height * .26)))
            working = working.crop((0, 0, working.width, int(working.height * .26)))
        require(reference.size == working.size, "Page dimensions changed")
        difference = np.asarray(ImageChops.difference(reference, working))
        mean_delta = float(difference.mean())
        changed_fraction = float((difference.max(axis=2) > 20).mean())
        identical = not bool(difference.any())
        # DOC-to-DOCX conversion slightly changes raster interpolation of logos.
        require(identical or (number == 1 and mean_delta < .2 and changed_fraction < .002),
                "Unexpected template visual change on page " + str(number))
        image_checks.append({"page": number, "scope": "above cover footer" if number == 1 else ("official abstract header" if number == 2 else "entire page"),
                             "pixels_identical": identical, "mean_channel_delta": mean_delta, "changed_fraction_over_20": changed_fraction})
    word = PdfReader(ROOT / "paper/preview/word/working-template.pdf")
    latex = PdfReader(ROOT / "paper/preview/latex/template.pdf")
    require(len(word.pages) == 4 and len(latex.pages) >= 4, "Unexpected template page count")
    def page_text(pdf, number):
        return subprocess.run(["pdftotext", "-layout", "-f", str(number), "-l", str(number), str(pdf), "-"],
                              capture_output=True, text=True, check=True).stdout.strip()
    require(not page_text(ROOT / "paper/preview/word/working-template.pdf", 1).endswith("0"), "Cover still numbered 0")
    require(page_text(ROOT / "paper/preview/word/working-template.pdf", 2).endswith("1"), "Abstract numbering wrong")
    require(page_text(ROOT / "paper/preview/latex/template.pdf", 3).endswith("2"), "LaTeX body numbering wrong")
    require("人工智能工具使用说明" in "".join(p.extract_text() for p in latex.pages), "AI disclosure section missing")
    report["templates"] = {"word_pages": 4, "latex_pages": len(latex.pages), "logos": 4, "changed_package_parts": differences,
                           "visual_fidelity": image_checks, "page_numbers": "cover unnumbered, abstract 1, body 2"}
    run_root = ROOT / "practice/transport/runs/rehearsal-01"
    run = read_json(run_root / "run.json")
    for kind in ("inputs", "code", "outputs"):
        verify_records(ROOT, run[kind])
    verification = read_json(run_root / "verification.json")
    require(verification["passed"] and all(c["passed"] for c in verification["checks"]), "Practice checks failed")
    report["practice"] = {"checks": len(verification["checks"]), "passed": True, "formal_result": False}
    tests = subprocess.run([sys.executable, str(ROOT / "tools/test_workflow.py")], capture_output=True, text=True)
    (ROOT / "review/test_workflow.log").write_text(tests.stdout + tests.stderr)
    require(tests.returncode == 0, "Workflow regression failed")
    report["regressions"] = {"exit_code": tests.returncode, "log": "review/test_workflow.log"}
    draft = subprocess.run([sys.executable, str(ROOT / "tools/check_submission.py"), "--final"], capture_output=True, text=True)
    require(draft.returncode == 1, "Unfilled template incorrectly passed the final-paper check")
    write_json(ROOT / "review/submission-precheck.json", {"expected_exit_code": 1, "actual_exit_code": draft.returncode,
               "report": __import__("json").loads(draft.stdout)})
    report["unfilled_template_rejected"] = True
    fonts = []
    for i, page in enumerate(latex.pages, 1):
        for font in page["/Resources"].get("/Font", {}).values():
            obj = font.get_object()
            fonts.append({"page": i, "name": str(obj.get("/BaseFont", ""))})
    report["pdf_fonts"] = fonts
    require(any("SimSun" in f["name"] for f in fonts if f["page"] >= 3), "Body SimSun not present")
    require(any("SimHei" in f["name"] for f in fonts if f["page"] >= 3), "Heading SimHei not present")
    broken = []
    for file in ROOT.rglob("*.md"):
        if any(p in file.parts for p in (".venv", "official", "Each Stage Review Work")):
            continue
        for href in re.findall(r"\]\(([^)]+)\)", file.read_text()):
            if "://" in href or href.startswith("#"):
                continue
            target = unquote(href.split("#")[0].strip("<>"))
            if not (file.parent / target).exists():
                broken.append({"file": str(file.relative_to(ROOT)), "target": href})
    require(not broken, "Broken Markdown links: " + str(broken))
    report["local_document_links"] = "PASS"
    report["limits"] = ["formal inputs not received", "no actual registration/payment confirmation", "no human or platform approval"]
    write_json(ROOT / "review/environment.json", report["environment"])
    write_json(ROOT / "review/preparation-validation.json", report)
    packages = ["numpy", "scipy", "matplotlib", "beautifulsoup4", "python-docx", "pypdf", "lxml", "pillow", "contourpy", "cycler", "fonttools", "kiwisolver", "packaging", "pyparsing", "python-dateutil", "six", "soupsieve", "typing_extensions"]
    (ROOT / "requirements-lock.txt").write_text("\n".join(p + "==" + importlib.metadata.version(p) for p in packages) + "\n")
    print("Preparation checks passed; formal scientific and submission states remain NOT_ASSESSED/NOT_SUBMITTED")


if __name__ == "__main__":
    main()
