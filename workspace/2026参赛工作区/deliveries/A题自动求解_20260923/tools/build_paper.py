"""Build the LaTeX body using official Word front matter."""

import argparse
import subprocess
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper/latex"


def frontmatter(source, pages):
    reader = PdfReader(source)
    if pages not in (2, 3) or len(reader.pages) < pages:
        raise ValueError("Front matter must contain one cover plus one or two abstract pages")
    writer = PdfWriter()
    for page in reader.pages[:pages]:
        writer.add_page(page)
    writer.write(PAPER / "frontmatter.pdf")
    cover = PdfWriter()
    cover.add_page(reader.pages[0])
    cover.write(PAPER / "official-cover.pdf")


def compile_paper():
    count = len(PdfReader(PAPER / "frontmatter.pdf").pages)
    if count not in (2, 3):
        raise ValueError("Expected official cover plus <=2 abstract pages")
    build = PAPER / "build"
    build.mkdir(exist_ok=True)
    font_dir = Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts")
    if (font_dir / "Simsun.ttc").exists() and (font_dir / "SimHei.ttf").exists():
        fonts = ("\\setCJKmainfont[Path={" + font_dir.as_posix() + "/}]{Simsun.ttc}\n"
                 "\\setCJKsansfont[Path={" + font_dir.as_posix() + "/}]{SimHei.ttf}\n")
    else:
        fonts = "\\setCJKmainfont{SimSun}\n\\setCJKsansfont{SimHei}\n"
    (build / "settings.tex").write_text(fonts + "\\newcommand{\\frontmatterpages}{" + str(count) + "}\n")
    command = ["latexmk", "-xelatex", "-interaction=nonstopmode", "-halt-on-error", "-outdir=build", "main.tex"]
    result = subprocess.run(command, cwd=PAPER, capture_output=True, text=True)
    (build / "compile.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit("Compile failed; see paper/latex/build/compile.log")
    preview = ROOT / "paper/preview/latex"
    preview.mkdir(parents=True, exist_ok=True)
    combined = PdfWriter()
    combined.append(PAPER / "frontmatter.pdf")
    combined.append(build / "main.pdf")
    combined.write(preview / "template.pdf")
    subprocess.run(["pdftotext", "-layout", str(preview / "template.pdf"), str(preview / "template.txt")], check=True)
    subprocess.run(["pdftoppm", "-r", "110", "-png", str(preview / "template.pdf"), str(preview / "page")], check=True)
    print("Built paper/preview/latex/template.pdf")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("latex")
    cover = sub.add_parser("cover", help="Import cover AND unified abstract from exported official Word PDF")
    cover.add_argument("pdf", type=Path)
    cover.add_argument("--pages", type=int, default=2)
    args = parser.parse_args()
    if args.cmd == "latex":
        compile_paper()
    else:
        frontmatter(args.pdf, args.pages)
