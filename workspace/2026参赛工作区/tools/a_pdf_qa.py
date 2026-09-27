"""Check PDF text, page geometry and numbering; render contact sheets for review."""

import json
from pathlib import Path
import re
import sys

import pdfplumber
from PIL import Image, ImageDraw
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
pdf = ROOT / "paper/preview/latex/template.pdf"
out = ROOT / "review/auto_solve/20260923_120249/05_paper"
out.mkdir(parents=True, exist_ok=True)
pages, problems = [], []
with pdfplumber.open(pdf) as doc:
    for number, page in enumerate(doc.pages, 1):
        text = page.extract_text() or ""
        outside = [c for c in page.chars if c["x0"] < -1 or c["x1"] > page.width + 1 or c["top"] < -1 or c["bottom"] > page.height + 1]
        margin = [c for c in page.chars if c["x0"] < 45 or c["x1"] > page.width - 45]
        footer = page.crop((0,page.height-50,page.width,page.height)).extract_text() or ""
        footer_lines = footer.strip().splitlines()
        page_number = footer_lines[-1].strip() if footer_lines else ""
        if number > 1 and page_number != str(number-1):
            problems.append({"page":number,"kind":"page_number","value":footer})
        if outside:
            problems.append({"page":number,"kind":"outside_page","count":len(outside)})
        if re.search(r"/Users/|futaoran|待正式题面|待填写真实|待填写问题",text):
            problems.append({"page":number,"kind":"identity_or_stale_template"})
        if number > 1 and len(text) < 20:
            problems.append({"page":number,"kind":"near_empty"})
        pages.append({"page":number,"characters":len(text),"outside_page":len(outside),
                      "outside_45pt_margin":len(margin),"footer":footer.strip(),"page_number":page_number,
                      "fonts":sorted({c["fontname"] for c in page.chars})})
    whole = "\n".join(page.extract_text() or "" for page in doc.pages)
    for value in ("3.2186","3.4921","1.0233","4068","关键词","人工智能工具使用说明"):
        if value not in whole:
            problems.append({"kind":"missing_expected_text","value":value})
    (out / "full_text.txt").write_text(whole)
reader = PdfReader(pdf)
images = sorted((ROOT / "paper/preview/latex").glob("page-*.png"))
images = [ROOT / f"paper/preview/latex/page-{i:0{len(str(len(pages)))}d}.png" for i in range(1,len(pages)+1)]
for start in range(0,len(images),4):
    sheet = Image.new("RGB",(1100,1600),"#dadada")
    draw = ImageDraw.Draw(sheet)
    for i,path in enumerate(images[start:start+4]):
        image = Image.open(path).convert("RGB")
        image.thumbnail((540,760))
        x,y=(i%2)*550,(i//2)*800
        sheet.paste(image,(x+(550-image.width)//2,y+30))
        draw.text((x+10,y+8),f"Page {start+i+1}",fill="black")
    sheet.save(out / f"contact-{start//4+1:02d}.png")
report={"pdf":str(pdf.relative_to(ROOT)),"pages":len(pages),"page_checks":pages,
        "issues":problems,"named_destinations":len(reader.named_destinations),
        "automated_status":"AI_VERIFIED" if not problems else "FAILED", "visual_status":"PENDING"}
(out / "pdf_qa.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"pages":len(pages),"issues":problems,"contacts":(len(pages)+3)//4},ensure_ascii=False))
