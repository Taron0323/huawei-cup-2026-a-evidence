"""Rebuild the current V0.7.1 manuscript with the saved official cover."""

import subprocess
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from build_paper import compile_paper

ROOT = Path(__file__).resolve().parents[1]
LATEX = ROOT / "paper/latex"


def main():
    cover = PdfReader(LATEX / "official-cover.pdf").pages[0]
    build = LATEX / "build_frontmatter"
    build.mkdir(exist_ok=True)
    result = subprocess.run(
        ["latexmk", "-xelatex", "-interaction=nonstopmode", "-halt-on-error",
         "-outdir=build_frontmatter", "frontmatter_v071.tex"],
        cwd=LATEX, capture_output=True, text=True,
    )
    (build / "compile.log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    abstract = PdfReader(build / "frontmatter_v071.pdf")
    if len(abstract.pages) not in (1, 2):
        raise ValueError("Expected one or two abstract pages")
    front = PdfWriter()
    front.add_page(cover)
    for page in abstract.pages:
        front.add_page(page)
    front.write(LATEX / "frontmatter.pdf")
    compile_paper()
    source = ROOT / "paper/preview/latex/template.pdf"
    output = ROOT / "paper/A题论文V0.1_试验稿_20260924.pdf"
    output.write_bytes(source.read_bytes())
    count = len(PdfReader(output).pages)
    digits = len(str(count))
    for page in (ROOT / "paper/preview/latex").glob("page-*.png"):
        number = int(page.stem.split("-")[-1])
        if number > count or page.name != f"page-{number:0{digits}d}.png":
            page.unlink()
    print(f"Built {output.relative_to(ROOT)} ({count} pages)")


if __name__ == "__main__":
    main()
