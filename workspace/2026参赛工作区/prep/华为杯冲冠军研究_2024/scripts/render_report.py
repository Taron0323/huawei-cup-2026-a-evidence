#!/usr/bin/env python3
"""Build the full Markdown report and render every PDF page for review.

uv run --with reportlab --with markdown-it-py --with pymupdf --with pillow \
    python scripts/render_report.py
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path

import pymupdf
from markdown_it import MarkdownIt
from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    LongTable,
    PageTemplate,
    Paragraph,
    Spacer,
    TableStyle,
)


BASE = Path(__file__).resolve().parents[1]
FONT_DIR = Path("/System/Library/Fonts")
PAGE_W, PAGE_H = A4
MARGIN = 46
CONTENT_W = PAGE_W - 2 * MARGIN
INK = colors.HexColor("#17282A")
ACCENT = colors.HexColor("#246B66")
MUTED = colors.HexColor("#536567")
DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-"})


def normalized(text):
    return re.sub(r"\s+", "", text.translate(DASHES))


def register_fonts():
    for name, filename in [("ReportCJK", "STHeiti Light.ttc"), ("ReportCJK-Bold", "STHeiti Medium.ttc")]:
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename), subfontIndex=1))
    pdfmetrics.registerFontFamily("ReportCJK", normal="ReportCJK", bold="ReportCJK-Bold", italic="ReportCJK", boldItalic="ReportCJK-Bold")


def make_styles():
    body = ParagraphStyle(
        "Body", fontName="ReportCJK", fontSize=10.3, leading=17,
        textColor=INK, spaceAfter=7, wordWrap="CJK", splitLongWords=True,
        allowWidows=0, allowOrphans=0, alignment=TA_LEFT, rightIndent=14,
    )
    return {
        "body": body,
        "h1": ParagraphStyle("ReportTitle", parent=body, fontName="ReportCJK-Bold", fontSize=24, leading=34, spaceBefore=5, spaceAfter=10, keepWithNext=True),
        "subtitle": ParagraphStyle("Subtitle", parent=body, fontName="ReportCJK-Bold", fontSize=13.2, leading=21, textColor=ACCENT, spaceAfter=13, keepWithNext=True),
        "h2": ParagraphStyle("Section", parent=body, fontName="ReportCJK-Bold", fontSize=15, leading=23, textColor=ACCENT, spaceBefore=17, spaceAfter=9, keepWithNext=True),
        "h3": ParagraphStyle("Subsection", parent=body, fontName="ReportCJK-Bold", fontSize=11.9, leading=19, spaceBefore=12, spaceAfter=6, keepWithNext=True),
        "h4": ParagraphStyle("MinorHeading", parent=body, fontName="ReportCJK-Bold", fontSize=10.8, leading=18, spaceBefore=8, spaceAfter=5, keepWithNext=True),
        "quote": ParagraphStyle("Quote", parent=body, leftIndent=12, rightIndent=8, textColor=MUTED, borderColor=ACCENT, borderWidth=0.6, borderPadding=8, spaceBefore=4, spaceAfter=12),
        "list": ParagraphStyle("List", parent=body, leftIndent=15, firstLineIndent=-12, spaceAfter=6),
        "cell": ParagraphStyle("Cell", parent=body, fontSize=8.7, leading=13.5, spaceAfter=0, rightIndent=0, allowWidows=1, allowOrphans=1),
        "cell_header": ParagraphStyle("CellHeader", parent=body, fontName="ReportCJK-Bold", fontSize=8.7, leading=13.5, textColor=colors.white, spaceAfter=0, rightIndent=0),
        "code": ParagraphStyle("CodeBlock", parent=body, fontSize=9, leading=14, backColor=colors.HexColor("#F1F5F4"), borderPadding=7),
    }


def inline_content(children):
    parts, plain, links = [], [], []
    for token in children or []:
        kind, text = token.type, token.content.translate(DASHES)
        if kind == "text":
            parts.append(html.escape(text))
            plain.append(text)
        elif kind == "code_inline":
            parts.append('<font color="#355A63">' + html.escape(text) + "</font>")
            plain.append(text)
        elif kind in ("strong_open", "strong_close", "em_open", "em_close"):
            parts.append({"strong_open": "<b>", "strong_close": "</b>", "em_open": "<i>", "em_close": "</i>"}[kind])
        elif kind == "link_open":
            href = token.attrGet("href")
            external = href.startswith(("http://", "https://"))
            links.append(external)
            if external:
                parts.append('<link href="' + html.escape(href, quote=True) + '" color="#246B66">')
            else:
                parts.append('<font color="#246B66">')
        elif kind == "link_close":
            parts.append("</link>" if links.pop() else "</font>")
        elif kind in ("softbreak", "hardbreak"):
            parts.append("<br/>" if kind == "hardbreak" else " ")
            plain.append(" ")
        elif kind == "html_inline":
            parts.append(html.escape(text))
            plain.append(text)
        else:
            raise ValueError(f"Unsupported inline token: {kind}")
    return "".join(parts), "".join(plain)


def table_widths(headers):
    first = headers[0]
    if len(headers) == 5:
        proportions = [0.07, 0.24, 0.23, 0.10, 0.36]
    elif len(headers) == 4:
        proportions = [0.17, 0.277, 0.277, 0.276]
    elif first == "论文ID":
        proportions = [0.245, 0.395, 0.36]
    elif first == "任务":
        proportions = [0.16, 0.48, 0.36]
    elif first == "原文可核查问题":
        proportions = [0.42, 0.25, 0.33]
    else:
        proportions = [1 / len(headers)] * len(headers)
    return [CONTENT_W * ratio for ratio in proportions]


def cjk_strong(state, silent):
    # CommonMark's punctuation boundary misses bold text next to Chinese words.
    if not state.src.startswith("**", state.pos):
        return False
    end = state.src.find("**", state.pos + 2)
    if end <= state.pos + 2 or "\n" in state.src[state.pos + 2:end]:
        return False
    if not silent:
        state.push("strong_open", "strong", 1)
        state.md.inline.parse(state.src[state.pos + 2:end], state.md, state.env, state.tokens)
        state.push("strong_close", "strong", -1)
    state.pos = end + 2
    return True


def parse_story(source, styles):
    parser = MarkdownIt("commonmark").enable("table")
    parser.inline.ruler.before("emphasis", "cjk_strong", cjk_strong)
    tokens = parser.parse(source)
    story, units, lists = [], [], []
    heading, quote_depth, prefix = None, 0, ""
    i, table_count = 0, 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == "table_open":
            rows, row, headers = [], [], []
            in_header = False
            i += 1
            while tokens[i].type != "table_close":
                current = tokens[i]
                if current.type == "thead_open":
                    in_header = True
                elif current.type == "thead_close":
                    in_header = False
                elif current.type == "tr_open":
                    row = []
                elif current.type == "inline":
                    markup, text = inline_content(current.children)
                    units.append(text)
                    row.append(Paragraph(markup, styles["cell_header" if in_header else "cell"]))
                    if in_header:
                        headers.append(text)
                elif current.type == "tr_close":
                    rows.append(row)
                i += 1
            table = LongTable(rows, colWidths=table_widths(headers), repeatRows=1, hAlign="LEFT", splitByRow=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6F5")]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, ACCENT),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#D9E4E2")),
            ]))
            story.extend([Spacer(1, 3), table, Spacer(1, 10)])
            table_count += 1
        elif token.type == "heading_open":
            heading = token.tag
        elif token.type == "heading_close":
            heading = None
        elif token.type == "blockquote_open":
            quote_depth += 1
        elif token.type == "blockquote_close":
            quote_depth -= 1
        elif token.type in ("bullet_list_open", "ordered_list_open"):
            lists.append({"ordered": token.type == "ordered_list_open", "number": int(token.attrGet("start") or 1)})
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
        elif token.type == "list_item_open":
            item = lists[-1]
            prefix = f'{item["number"]}. ' if item["ordered"] else "• "
            item["number"] += 1
        elif token.type == "inline":
            markup, text = inline_content(token.children)
            units.append(text)
            if heading:
                key = "subtitle" if heading == "h2" and table_count == 0 and not text.startswith("1.") else heading
                key = key if key in styles else "h4"
            else:
                key = "quote" if quote_depth else "list" if lists else "body"
            para = Paragraph(html.escape(prefix) + markup, styles[key])
            if heading:
                para.outline_title = text
                para.outline_level = max(int(heading[1]) - 1, 0)
            story.append(para)
            if heading == "h1":
                story.append(HRFlowable(width=CONTENT_W, thickness=1.2, color=ACCENT, spaceAfter=9))
            prefix = ""
        elif token.type in ("fence", "code_block"):
            text = token.content.translate(DASHES)
            units.append(text)
            story.append(Paragraph(html.escape(text).replace("\n", "<br/>"), styles["code"]))
        elif token.type == "hr":
            story.append(HRFlowable(width=CONTENT_W, color=ACCENT, spaceBefore=8, spaceAfter=8))
        elif token.type not in ("paragraph_open", "paragraph_close", "list_item_close"):
            raise ValueError(f"Unsupported block token: {token.type}")
        i += 1
    return story, units, table_count


class ReportDocument(BaseDocTemplate):
    def __init__(self, path, total_pages=None):
        super().__init__(str(path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=56, bottomMargin=47, title="华为杯冲冠军报告", author="华为杯论文比较研究")
        self.total_pages = total_pages
        self.outline_index = 0
        frame = Frame(MARGIN, 47, CONTENT_W, PAGE_H - 103, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(PageTemplate(id="Report", frames=frame, onPage=self.decorate))

    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(MUTED)
        canvas.setFont("ReportCJK", 8)
        if doc.page > 1:
            canvas.drawString(MARGIN, PAGE_H - 32, "华为杯冲冠军报告")
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 32, "2024 数模之星论文比较研究")
        canvas.setStrokeColor(colors.HexColor("#D9E4E2"))
        canvas.setLineWidth(0.45)
        canvas.line(MARGIN, 36, PAGE_W - MARGIN, 36)
        canvas.setFont("ReportCJK", 8)
        canvas.drawString(MARGIN, 22, "历史论文证据与可迁移建模方法")
        count = f"{doc.page} / {self.total_pages}" if self.total_pages else str(doc.page)
        canvas.drawRightString(PAGE_W - MARGIN, 22, count)
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if hasattr(flowable, "outline_title"):
            key = f"section-{self.outline_index}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.outline_title, key, level=flowable.outline_level, closed=False)
            self.outline_index += 1


def validate_and_render(output, units, table_count, source_hash, qa_dir):
    qa_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(output)
    extracted = "\n".join(page.get_text() for page in doc)
    flattened = normalized(extracted)
    missing_units = [text for text in units if normalized(text) not in flattened]
    bounds_errors, missing_font_files, embedded_fonts, page_images = [], [], {}, []
    for index, page in enumerate(doc):
        image_path = qa_dir / f"page-{index + 1:02d}.png"
        page.get_pixmap(matrix=pymupdf.Matrix(1.7, 1.7), alpha=False).save(image_path)
        page_images.append(image_path)
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    x0, y0, x1, y1 = span["bbox"]
                    if x0 < MARGIN - 1 or x1 > PAGE_W - MARGIN + 1 or y0 < 15 or y1 > PAGE_H - 10:
                        bounds_errors.append({"page": index + 1, "text": span["text"], "bbox": list(span["bbox"])})
        for font in page.get_fonts():
            if font[0] in embedded_fonts:
                continue
            name, ext, kind, data = doc.extract_font(font[0])
            embedded_fonts[font[0]] = {"name": name, "extension": ext, "type": kind, "bytes": len(data)}
            if "Heiti" in name and not data:
                missing_font_files.append(name)
    for start in range(0, len(page_images), 9):
        sheet = Image.new("RGB", (900, 1335), "#D8DFDE")
        draw = ImageDraw.Draw(sheet)
        for offset, path in enumerate(page_images[start:start + 9]):
            image = Image.open(path)
            image.thumbnail((284, 403))
            x, y = (offset % 3) * 300 + 8, (offset // 3) * 445 + 8
            sheet.paste(image, (x, y))
            draw.text((x, y + 410), f"Page {start + offset + 1}", fill="#263B3B")
        sheet.save(qa_dir / f"contact-sheet-{start // 9 + 1:02d}.png")
    used = set("".join(units)) - set("\n\r\t")
    font_maps = [pdfmetrics.getFont(name).face.charToGlyph for name in ("ReportCJK", "ReportCJK-Bold")]
    missing_glyphs = [f"U+{ord(char):04X} {char}" for char in sorted(used) if any(ord(char) not in mapping for mapping in font_maps)]
    source_counts = Counter(normalized("".join(units)))
    pdf_counts = Counter(flattened)
    missing_characters = dict(source_counts - pdf_counts)
    report = {
        "source_sha256": source_hash, "pdf_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "pages": len(doc), "tables": table_count, "source_text_units": len(units),
        "missing_source_units": missing_units, "missing_character_counts": missing_characters,
        "missing_glyphs": missing_glyphs, "out_of_bounds_spans": bounds_errors,
        "embedded_fonts": list(embedded_fonts.values()), "unembedded_cjk_fonts": missing_font_files,
        "rendered_pages": len(page_images), "visual_review": "pending_contact_sheet_inspection",
    }
    (qa_dir / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (qa_dir / "extracted.txt").write_text(extracted, encoding="utf-8")
    if missing_units or missing_characters or missing_glyphs or bounds_errors or missing_font_files:
        raise SystemExit("PDF verification failed; inspect evidence/report_pdf_qa/verification.json")
    print(json.dumps({"output": str(output), "pages": len(doc), "tables": table_count, "content_units_verified": len(units), "qa": str(qa_dir)}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=BASE / "华为杯冲冠军报告.md")
    parser.add_argument("--output", type=Path, default=BASE / "华为杯冲冠军报告.pdf")
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(args.source.read_bytes()).hexdigest()
    register_fonts()
    styles = make_styles()
    story, units, table_count = parse_story(source, styles)
    ReportDocument(args.output).build(story)
    with pymupdf.open(args.output) as probe:
        total_pages = len(probe)
    story, _, _ = parse_story(source, styles)
    ReportDocument(args.output, total_pages).build(story)
    validate_and_render(args.output, units, table_count, source_hash, BASE / "evidence/report_pdf_qa")


if __name__ == "__main__":
    main()
