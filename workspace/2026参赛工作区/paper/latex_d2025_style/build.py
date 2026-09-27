"""Build both editable editions, model handbook, and original-page facsimile."""
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
    word = Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts")
    if (word / "STXINWEI.ttf").exists():
        heading = "\\newCJKfontfamily\\xinweifont[AutoFakeBold=2,Path={" + str(word) + "/}]{STXINWEI.ttf}\n"
    else:
        heading = "\\newcommand{\\xinweifont}{\\kaishu}\n"
    if (word / "Simsun.ttc").exists():
        contest = ("\\ifcontest\n\\setCJKmainfont[Path={" + str(word) + "/}]{Simsun.ttc}\n"
                   "\\setCJKsansfont[Path={" + str(word) + "/}]{SimHei.ttf}\n\\fi\n")
    else:
        contest = "\\ifcontest\n\\setCJKmainfont{SimSun}\n\\setCJKsansfont{SimHei}\n\\fi\n"
    (build / "fonts.tex").write_text(heading + contest, encoding="utf-8")
    count = len(PdfReader(ROOT / "frontmatter.pdf").pages)
    if count not in (2, 3):
        raise ValueError("Official front matter must be a cover plus one or two abstract pages")
    (build / "frontpages.tex").write_text(f"\\setcounter{{page}}{{{count}}}\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["main-reference", "main-2026", "models", "facsimile"])
    parser.add_argument("--figures", action="store_true", help="Regenerate illustrative figures (NumPy and Matplotlib)")
    args = parser.parse_args()
    if args.figures:
        subprocess.run([os.sys.executable, "generate_figures.py"], cwd=ROOT, check=True)
    prepare_fonts()
    engine = shutil.which("xelatex")
    if not engine:
        candidate = Path.home() / "Library/TinyTeX/bin/universal-darwin/xelatex"
        engine = str(candidate) if candidate.exists() else None
    if not engine:
        raise SystemExit("XeLaTeX is required; install TeX Live / MacTeX with ctex and Fandol")
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    entries = [args.only] if args.only else ["main-reference", "main-2026", "models", "facsimile"]
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
            combined.add_metadata({"/Title": "2026格式写作模板（2025 D题演练内容）", "/Author": ""})
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
