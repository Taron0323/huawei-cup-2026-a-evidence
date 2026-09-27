"""Extract reference evidence and render contact sheets with pdfplumber/PDFium."""
import collections
import hashlib
import json
import re
from pathlib import Path

import pdfplumber
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent


def main():
    output = ROOT / "inspection"
    output.mkdir(exist_ok=True)
    headings, fonts, pages = [], collections.Counter(), []
    with pdfplumber.open(ROOT / "reference.pdf") as doc:
        for number, page in enumerate(doc.pages, 1):
            text = page.dedupe_chars().extract_text() or ""
            pages.append(f"\n===== PAGE {number} =====\n{text}")
            if number <= 63:
                for line in text.splitlines():
                    if re.match(r"^\d+(?:\.\d+)* [\u4e00-\u9fff]", line):
                        headings.append({"page": number, "heading": line})
                fonts.update((c["fontname"], round(c["size"], 2)) for c in page.chars)
            if (number - 1) % 12 == 0:
                sheet = Image.new("RGB", (1200, 1740), "#dedede")
                draw = ImageDraw.Draw(sheet)
            thumb = page.to_image(resolution=34).original.convert("RGB")
            thumb.thumbnail((280, 397))
            cell = (number - 1) % 12
            x, y = (cell % 4) * 300 + 10, (cell // 4) * 580 + 30
            sheet.paste(thumb, (x, y))
            draw.text((x, y - 20), f"Original page {number}", fill="black")
            if number % 12 == 0 or number == len(doc.pages):
                sheet.save(output / f"contact-{(number - 1) // 12 + 1:02}.jpg", quality=90)
        metadata = {
            "pages": len(doc.pages), "page_size_pt": [doc.pages[0].width, doc.pages[0].height],
            "sha256": hashlib.sha256((ROOT / "reference.pdf").read_bytes()).hexdigest(),
            "fonts": [{"font": f, "size_pt": s, "characters": n} for (f, s), n in fonts.most_common()],
            "headings": headings,
        }
    (ROOT / "reference-readable.txt").write_text("\n".join(pages), encoding="utf-8")
    (ROOT / "layout-evidence.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(pages)} pages; rendered all pages into 10 contact sheets")


if __name__ == "__main__":
    main()
