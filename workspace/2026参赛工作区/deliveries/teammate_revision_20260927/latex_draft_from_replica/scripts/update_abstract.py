"""Synchronize the official editable cover/abstract and TeX abstract."""

from copy import deepcopy
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
TITLE = "张量驻留与查询时序驱动的神经网络处理器多核调度"
PARAGRAPHS = [
    "神经网络计算图的多核执行能够提高并行度，但任务切分会同时改变跨域搬运、片上容量占用和共享带宽竞争。本文围绕独立任务、同核复用与共享只读缓存三种场景，建立从计算图切分到事件评价的统一调度方法，并在100张计算图、1至5核上完成可核验实验。",
    "针对问题一，建立Task驻留域结构搬运模型。从生产者—消费者关系提取依赖边，构造整图、弱连通分量装箱和拓扑切块候选，以轻量评分安排评价顺序，再按Makespan优先选择最终方案。相对整图单核基准，五核平均加速比为3.4383；图001的工期由233110周期降至47502周期，新增搬运量为4608字节。",
    "针对问题二，建立核心驻留与物理副本容量模型。将同核子图合并为核级Task，按物理副本从申请到最后读者完成的区间核算L1与UB占用，并把结构搬运、换出恢复和共享DDR排队纳入事件评价。五核平均加速比为3.4738，初始方案到最终方案的平均工期改善为60.3622%；四核增至五核时，98张图的候选工期得到改善或保持。",
    "针对问题三，建立基于查询与完成事件的FIFO Cache模型。按照发射查询、读取完成后插入和先进先出淘汰的时序，将Cache读与DDR读置于独立带宽服务中，并在问题二计划上比较硬件效应和调度适配。五核平均加速比为3.5533。在500组同核计划配对中，五核硬件、调度适配和综合效应比分别为1.0146、1.0139和1.0289。",
    "固定问题二最终计划进行Cache参数敏感性实验：六张代表图的24组固定计划全部通过评价，37条重优化候选全部通过；容量减半、容量加倍、带宽减半和带宽加倍时，重优化工期相对默认配置的均值比分别为0.9900、0.9869、0.9892和0.9885。结果表明，Cache参数变化的影响取决于容量占用、查询时序与关键路径位置的共同作用。",
]
KEYWORDS = "多核调度；张量驻留域；拓扑切块；容量约束；FIFO 缓存"
BOLD_SPANS = {
    1: ["计算图切分到事件评价"],
    2: ["针对问题一", "Task驻留域结构搬运模型", "3.4383", "47502周期", "4608字节"],
    3: ["针对问题二", "核心驻留与物理副本容量模型", "3.4738", "60.3622%", "98张图"],
    4: ["针对问题三", "基于查询与完成事件的FIFO Cache模型", "3.5533", "1.0146", "1.0139", "1.0289"],
    5: ["Cache参数敏感性实验", "24组固定计划全部通过评价", "37条重优化候选全部通过", "0.9900", "0.9869", "0.9892", "0.9885"],
}

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"


def replace_paragraph(template, content, bold_spans=(), *, first_line=False, keep_lines=False):
    paragraph = deepcopy(template)
    ppr = paragraph.find("w:pPr", NS)
    if ppr is None:
        ppr = etree.Element(W + "pPr")
        paragraph.insert(0, ppr)
    if first_line:
        ind = ppr.find("w:ind", NS)
        if ind is None:
            ind = etree.SubElement(ppr, W + "ind")
        ind.set(W + "firstLine", "480")
        spacing = ppr.find("w:spacing", NS)
        if spacing is None:
            spacing = etree.SubElement(ppr, W + "spacing")
        spacing.set(W + "before", "156")
        spacing.set(W + "after", "0")
        spacing.set(W + "line", "300")
        spacing.set(W + "lineRule", "auto")
    if keep_lines:
        if ppr.find("w:keepLines", NS) is None:
            etree.SubElement(ppr, W + "keepLines")
    first_run = paragraph.find("w:r", NS)
    base_style = deepcopy(first_run.find("w:rPr", NS)) if first_run is not None and first_run.find("w:rPr", NS) is not None else None
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)
    locations = []
    for span in bold_spans:
        start = content.find(span)
        if start < 0:
            raise ValueError(f"Bold span missing: {span}")
        locations.append((start, start + len(span)))
    locations.sort()
    assert all(a[1] <= b[0] for a, b in zip(locations, locations[1:]))
    parts = []
    cursor = 0
    for start, end in locations:
        parts.extend([(content[cursor:start], False), (content[start:end], True)])
        cursor = end
    parts.append((content[cursor:], False))
    for value, bold in parts:
        if not value:
            continue
        run = etree.SubElement(paragraph, W + "r")
        style = deepcopy(base_style) if base_style is not None else etree.Element(W + "rPr")
        if bold and style.find("w:b", NS) is None:
            etree.SubElement(style, W + "b")
        run.append(style)
        etree.SubElement(run, W + "t").text = value
    return paragraph


def fill_cover_cell(cell, content, *, paragraph_index=0):
    paragraph = cell.findall("w:p", NS)[paragraph_index]
    first_run = paragraph.find("w:r", NS)
    run_style = deepcopy(first_run.find("w:rPr", NS)) if first_run is not None and first_run.find("w:rPr", NS) is not None else None
    for run in paragraph.findall("w:r", NS):
        paragraph.remove(run)
    run = etree.SubElement(paragraph, W + "r")
    if run_style is not None:
        run.append(run_style)
    etree.SubElement(run, W + "t").text = content


def tex_escape(value):
    placeholder = "CACHEPLANPLACEHOLDER"
    return (value.replace("C(X_B*)", placeholder)
            .replace("%", r"\%").replace("_", r"\_").replace("&", r"\&")
            .replace("2.22×10⁻¹⁶", r"$2.22\times10^{-16}$")
            .replace(placeholder, r"$C(X_B^*)$"))


def tex_bold(value, markers):
    result = tex_escape(value)
    for marker in sorted(markers, key=len, reverse=True):
        result = result.replace(tex_escape(marker), r"\textbf{" + tex_escape(marker) + "}")
    return result


def main():
    template = ROOT.parent / "latex_d2025_style/frontmatter.docx"
    target = ROOT / "frontmatter.docx"
    with ZipFile(template) as archive:
        items = [(info, archive.read(info.filename)) for info in archive.infolist()]
    document = etree.fromstring(dict((info.filename, data) for info, data in items)["word/document.xml"])
    body = document.find("w:body", NS)
    assert body[-1].tag == W + "sectPr" and "摘要" in "".join(body[20].itertext()).replace(" ", "")
    cover_rows = body[6].findall("w:tr", NS)
    for row, value, paragraph_index in (
        (0, "西交利物浦大学", -1),
        (1, "20260079630", 0),
        (2, "1. 傅陶然", 0),
        (3, "2. 王梓谦", 0),
        (4, "3. 史昕轶", 0),
    ):
        fill_cover_cell(cover_rows[row].findall("w:tc", NS)[1], value, paragraph_index=paragraph_index)
    team_cell = cover_rows[1].findall("w:tc", NS)[1]
    vertical_align = team_cell.find("w:tcPr/w:vAlign", NS)
    if vertical_align is None:
        vertical_align = etree.SubElement(team_cell.find("w:tcPr", NS), W + "vAlign")
    vertical_align.set(W + "val", "bottom")
    # The Chinese label and Latin digits have different visible glyph heights.
    # Raise the label to the same visible baseline as the number while keeping
    # the official row height, borders, and 18 pt font size unchanged.
    label_style = cover_rows[1].findall("w:tc", NS)[0].find("w:p/w:r/w:rPr", NS)
    label_position = label_style.find("w:position", NS)
    if label_position is None:
        label_position = etree.SubElement(label_style, W + "position")
    label_position.set(W + "val", "36")
    number_style = team_cell.find("w:p/w:r/w:rPr", NS)
    number_position = number_style.find("w:position", NS)
    if number_position is not None:
        number_style.remove(number_position)
    number_position = etree.SubElement(number_style, W + "position")
    # Latin digits sit lower than the Chinese label under the same lift; the
    # additional vertical raise restores the visible baseline alignment.
    number_position.set(W + "val", "63")
    body.replace(body[18], replace_paragraph(body[18], TITLE))
    prose_style, keyword_style = deepcopy(body[21]), deepcopy(body[-2])
    for child in list(body)[21:-1]:
        body.remove(child)
    for i, paragraph in enumerate(PARAGRAPHS):
        body.insert(len(body) - 1, replace_paragraph(prose_style, paragraph, BOLD_SPANS.get(i, ()),
                     first_line=True))
    keyword = replace_paragraph(keyword_style, "关键词：" + KEYWORDS, ("关键词：",))
    for run in keyword.findall("w:r", NS):
        label = run.find("w:t", NS).text == "关键词："
        style = run.find("w:rPr", NS)
        size = style.find("w:sz", NS)
        if size is None:
            size = etree.SubElement(style, W + "sz")
        size.set(W + "val", "32" if label else "24")
    body.insert(len(body) - 1, keyword)
    body.remove(body[19])
    body.remove(body[17])
    payload = etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone=True)
    temporary = target.with_suffix(".new.docx")
    with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
        for info, data in items:
            archive.writestr(info, payload if info.filename == "word/document.xml" else data)
    temporary.replace(target)
    abstract = r"\noindent\hspace*{2em}" + "\n\n".join(tex_bold(p, BOLD_SPANS.get(i, ())) for i, p in enumerate(PARAGRAPHS))
    (ROOT / "sections/abstract-prose.tex").write_text(abstract + "\n\n" + r"\noindent{\zihao{3}\textbf{关键词：}}" + KEYWORDS + "\n", encoding="utf-8")
    (ROOT / "docs/abstract-content.json").write_text(json.dumps({"title": TITLE, "paragraphs": PARAGRAPHS, "keywords": KEYWORDS}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(PARAGRAPHS)} paragraphs; {sum(map(len, PARAGRAPHS))} characters")


if __name__ == "__main__":
    main()
