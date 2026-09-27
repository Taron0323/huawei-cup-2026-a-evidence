"""Inspect chapter coverage, fonts, rendering and source-page reproduction."""
import collections
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pdfplumber
from PIL import Image, ImageChops, ImageDraw
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
QA = ROOT / "qa"
QA.mkdir(exist_ok=True)


def structure():
    titles, chapters = {}, []
    counters = [0, 0, 0]
    files = sorted((ROOT / "sections").glob("0[1-9]-*.tex"))
    for file in files:
        text = file.read_text()
        for kind, title in re.findall(r"\\(section|subsection|subsubsection)\{([^}]+)\}", text):
            level = ["section", "subsection", "subsubsection"].index(kind)
            counters[level] += 1
            counters[level+1:] = [0] * (2-level)
            number = ".".join(map(str,counters[:level+1]))
            titles[number] = {"title": title, "file": str(file.relative_to(ROOT))}
        chapters.append({"file": file.name, "chinese_characters": len(re.findall(r"[\u4e00-\u9fff]",text)),
                         "figures": len(re.findall(r"\\(?:samplefigure|auxfigure)\{",text)),
                         "tables": text.count("\\begin{table}"), "equations": text.count("\\begin{equation}")+text.count("\\begin{align}")})
    evidence = json.loads((ROOT / "sources/layout-evidence.json").read_text())
    source = {}
    for item in evidence["headings"]:
        number, title = item["heading"].split(" ",1)
        if int(number.split(".")[0])<=9:
            source.setdefault(number, {"title":title,"page":item["page"]})
    source["8.3.4"]={"title":"模型验证与优化流程（原稿标题损坏）","page":57}
    rows=[]
    for number, item in source.items():
        dest=titles.get(number)
        rows.append({"number":number,"source_page":item["page"],"source_title":item["title"],
                     "template_title":dest["title"] if dest else "MISSING", "file":dest["file"] if dest else "MISSING"})
    with (QA / "structure.csv").open("w",newline="",encoding="utf-8-sig") as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    body="\n".join(file.read_text() for file in files)
    assert all(row["file"]!="MISSING" for row in rows), "Missing source sections"
    assert all(c["figures"]>=1 and c["tables"]>=1 and c["chinese_characters"]>=100 for c in chapters)
    assert body.count("\\samplefigure{")==24, "Expected 24 original numbered figure slots"
    assert len(re.findall(r"\\caption\{",body))-body.count("\\begin{algorithm}")==16, "Expected 16 original numbered tables"
    return {"source_headings":len(source),"template_headings":len(titles),"chapters":chapters,
            "numbered_figures":24,"numbered_tables":16,"model_cards":(ROOT/"models.tex").read_text().count("\\modelcard{")}


def render(name):
    dest=QA/name;dest.mkdir(exist_ok=True)
    extracted,issues,fonts,footers=[],[],collections.Counter(),[]
    with pdfplumber.open(ROOT/"output"/(name+".pdf")) as doc:
        for index,page in enumerate(doc.pages):
            number=index+1
            text=page.extract_text() or ""
            extracted.append(f"\nPAGE {number}\n{text}")
            fonts.update((c["fontname"],round(c["size"],2)) for c in page.chars)
            outside=[c["text"] for c in page.chars if c["x0"] < -1 or c["x1"] > page.width+1 or c["top"] < -1 or c["bottom"] > page.height+1]
            if outside:issues.append({"page":number,"outside_page":outside[:15]})
            footer="".join(c["text"] for c in page.chars if c["top"]>page.height-65 and page.width/2-15<c["x0"]<page.width/2+15)
            footers.append(footer)
            img=page.to_image(resolution=100).original.convert("RGB")
            img.save(dest/f"page-{number:03}.png")
            if index%12==0:
                sheet=Image.new("RGB",(1200,1320),"#dddddd");draw=ImageDraw.Draw(sheet)
            thumb=img.copy();thumb.thumbnail((280,397))
            cell=index%12;x=(cell%4)*300+10;y=(cell//4)*440+24
            sheet.paste(thumb,(x,y));draw.text((x,y-17),f"{name} / {number}",fill="black")
            if number%12==0 or number==len(doc.pages):
                sheet.save(dest/f"contact-{index//12+1:02}.jpg",quality=90)
        report={"pages":len(doc.pages),"page_boundary_issues":issues,"footers":footers,
                "fonts":[{"font":f,"size_pt":s,"count":n} for (f,s),n in fonts.most_common(16)]}
    (QA/(name+".txt")).write_text("\n".join(extracted),encoding="utf-8")
    assert not issues,f"Content outside paper: {name}"
    return report


def facsimile():
    rows=[]
    with pdfplumber.open(ROOT/"sources/reference.pdf") as original, pdfplumber.open(ROOT/"output/facsimile.pdf") as replica:
        assert len(original.pages)==len(replica.pages)==110
        for i,(source,dest) in enumerate(zip(original.pages,replica.pages),1):
            a=source.to_image(resolution=72).original.convert("RGB")
            b=dest.to_image(resolution=72).original.convert("RGB")
            if a.size!=b.size:
                rows.append({"page":i,"size_mismatch":[a.size,b.size]});continue
            aa=np.asarray(a,dtype=np.int16);bb=np.asarray(b,dtype=np.int16)
            difference=np.abs(aa-bb)
            rows.append({"page":i,"mean_abs_channel_difference":round(float(difference.mean()),6),
                         "changed_pixel_fraction":round(float(np.any(difference>0,axis=2).mean()),6)})
    (QA/"facsimile-pixel-comparison.json").write_text(json.dumps(rows,indent=2))
    return {"pages_compared":len(rows),"resolution_dpi":72,
            "all_pixels_equal":all(r.get("changed_pixel_fraction")==0 for r in rows),
            "max_mean_difference":max(r.get("mean_abs_channel_difference",255) for r in rows),
            "max_changed_pixel_fraction":max(r.get("changed_pixel_fraction",1) for r in rows)}


def merged_links(frontpages):
    source = PdfReader(ROOT / "build/main-2026.pdf")
    merged = PdfReader(ROOT / "output/main-2026.pdf")
    problems = []
    for name, destination in source.named_destinations.items():
        target = merged.named_destinations.get(name)
        expected = source.get_destination_page_number(destination) + frontpages
        if target is None or merged.get_destination_page_number(target) != expected:
            problems.append(name)
    before = sum(len(page["/Annots"]) for page in source.pages if "/Annots" in page)
    after = sum(len(page["/Annots"]) for page in merged.pages if "/Annots" in page)
    assert before == after and not problems, (before, after, problems)
    return {"annotations_before":before,"annotations_after":after,
            "named_destinations_checked":len(source.named_destinations),"incorrect_targets":problems}


def main():
    report={"structure":structure()}
    for name in ["main-reference","main-2026","models"]:
        report[name]=render(name)
    report["facsimile"]=facsimile()
    # Both editions must have exactly two abstract pages before their body.
    with pdfplumber.open(ROOT/"output/main-reference.pdf") as doc:
        assert "研究背景及问题重述" in doc.pages[2].extract_text()
    with pdfplumber.open(ROOT/"frontmatter.pdf") as doc:
        frontpages=len(doc.pages)
        assert 2 <= frontpages <= 3
        assert all(len(page.extract_text() or "") > 100 for page in doc.pages[1:])
    assert report["main-2026"]["footers"]==[""]+[str(n) for n in range(1,report["main-2026"]["pages"])], report["main-2026"]["footers"]
    report["merged_links"]=merged_links(frontpages)
    (QA/"validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"structure":report["structure"],"facsimile":report["facsimile"]},ensure_ascii=False))


if __name__=="__main__":
    main()
