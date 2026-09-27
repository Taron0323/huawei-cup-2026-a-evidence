"""Build A-topic editions derived from the supplied D-template."""
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parent


def prepare_fonts():
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    count = len(PdfReader(ROOT / "frontmatter.pdf").pages)
    if count not in (2, 3):
        raise ValueError("Official front matter must be a cover plus one or two abstract pages")
    # The cover is unnumbered in the submitted PDF.  Start the contents on
    # page 3 so the two-page abstract occupies pages 1--2 in the manuscript.
    page_start = count + 1
    (ROOT / "frontmatter-count.tex").write_text(f"\\setcounter{{page}}{{{page_start}}}\n", encoding="utf-8")
    (build / "frontpages.tex").write_text(f"\\setcounter{{page}}{{{page_start}}}\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["main-reference", "main-2026", "main-overleaf"])
    parser.add_argument("--figures", action="store_true", help="Rebuild figures and appendices from frozen Final Idea reports")
    args = parser.parse_args()
    if args.figures:
        subprocess.run([os.sys.executable, "scripts/build_final_evidence.py"], cwd=ROOT, check=True)
    prepare_fonts()
    engine = shutil.which("xelatex")
    if not engine:
        candidate = Path.home() / "Library/TinyTeX/bin/universal-darwin/xelatex"
        engine = str(candidate) if candidate.exists() else None
    if not engine:
        raise SystemExit("XeLaTeX is required; install TeX Live / MacTeX with ctex and Fandol")
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    entries = [args.only] if args.only else ["main-reference", "main-2026", "main-overleaf"]
    report = {}
    for entry in entries:
        log = []
        for _ in range(1 if entry == "facsimile" else 2):
            result = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error",
                                     "-output-directory=build", entry + ".tex"], cwd=ROOT,
                                    capture_output=True, text=True)
            log.append(result.stdout + result.stderr)
            (ROOT / "build" / (entry + "-console.log")).write_text("\n".join(log), encoding="utf-8")
            if result.returncode:
                raise SystemExit(f"Compile failed: build/{entry}-console.log")
        source = ROOT / "build" / (entry + ".pdf")
        target = output / (entry + ".pdf")
        if entry == "main-2026":
            combined = PdfWriter()
            combined.append(ROOT / "frontmatter.pdf")
            combined.append(source)
            combined.add_metadata({"/Title": "张量驻留与查询时序驱动的神经网络处理器多核调度", "/Author": ""})
            combined.write(target)
        else:
            shutil.copyfile(source, target)
        reader = PdfReader(target)
        warnings = [line for line in (ROOT / "build" / (entry + ".log")).read_text(errors="replace").splitlines()
                    if any(x in line for x in ["Overfull", "undefined", "Missing character", "multiply defined"])]
        report[entry] = {"pages": len(reader.pages), "bytes": target.stat().st_size, "warnings": warnings}
        print(entry, report[entry])
    path = ROOT / "build/compile-report.json"
    existing = json.loads(path.read_text()) if path.exists() else {}
    existing.update(report)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
