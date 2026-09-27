"""Render source-paper abstract pages for a compact visual inspection."""

import json
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
stage = root.parents[1] / "Each Stage Review Work/20260921_star_papers"
stage.mkdir(exist_ok=True)
papers = json.loads((root / "来源与校验/2024_论文校验.json").read_text())["selected_papers"]
sheet = Image.new("RGB", (1600, 4 * 580), "#dddddd")
draw = ImageDraw.Draw(sheet)
for i, paper in enumerate(papers):
    key = paper["problem"] + paper["team_id"]
    prefix = stage / key
    with pymupdf.open(root / paper["path"]) as document:
        page = document[1]
        scale = 540 / max(page.rect.width, page.rect.height)
        page.get_pixmap(matrix=pymupdf.Matrix(scale, scale)).save(prefix.with_suffix(".png"))
    image = Image.open(prefix.with_suffix(".png")).convert("RGB")
    x, y = (i % 4) * 400, (i // 4) * 580
    sheet.paste(image, (x + (400 - image.width) // 2, y + 28))
    draw.text((x + 12, y + 8), key, fill="black")
sheet.save(stage / "2024_摘要页检查.png")
print(stage / "2024_摘要页检查.png")
