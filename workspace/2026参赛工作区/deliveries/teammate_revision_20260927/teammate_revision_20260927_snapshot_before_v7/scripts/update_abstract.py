"""Synchronize the official editable cover/abstract and TeX abstract."""

from copy import deepcopy
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
TITLE = "张量驻留与查询时序驱动的神经网络处理器多核调度"
PARAGRAPHS = [
    "神经网络计算图的多核执行能够提高计算并行度，而任务切分带来的跨域搬运、片上容量占用与共享带宽竞争会影响总体工期。",
    "本文研究独立任务、同核复用与共享只读缓存三种场景下的多核切图与调度。首先通过计算依赖提取与弱连通分量分析，构造子图划分与核心分配方案；接着根据张量的消费范围和物理副本生存区间，建立结构搬运与容量约束模型；最后引入 FIFO 缓存事件模型，由题给 Python 事件模拟程序评价 100 张计算图在 1 至 5 核下的调度结果。",
    "针对问题一，建立 Task 驻留域结构搬运模型。首先提取计算依赖及张量的生产、消费关系，按接收 Task 统计输入读入、跨任务搬运与最终写回，并根据同核次序和前驱依赖确定 Task 激活条件。接着以整图分配、分量装箱与拓扑切块生成候选，用静态评分安排评价顺序，再由事件评估程序按 Makespan 优先、额外搬运次之选定方案；对每张图在不超过目标核数的已评价计划及整图基准中取最短工期。相对整图单核基准，五核平均加速比为 3.4132；图 001 的工期由 233110 周期缩短至 47502 周期，新增搬运量为 4608 字节。",
    "针对问题二，建立核心驻留与物理副本容量模型。首先将同核子图合并为核级 Task，按接收核心统计跨核搬运。其次根据物理副本从空间申请至最后读者完成的存活区间，检查 L1、UB 的同时占用，分别核算结构搬运与换出恢复。然后以关键路径优先和释放优先生成拓扑切块候选，结合贪心分核与局部调整，经题给事件评价选定方案。采用逐图继承规则后，五核平均加速比为 3.3862；由四核升至五核时，65 图工期缩短、35 图持平，且没有图慢于整图单核基准。",
    "针对问题三，建立基于查询与完成事件的 FIFO Cache 模型。首先按照发射时查询、读取完成后插入和先进先出淘汰的规则，把命中读与未命中读分别纳入 Cache 和 DDR 的独立带宽服务。接着以问题二最终计划为起点，通过共享输入聚合、迁块和核内调序构造候选。然后固定计划比较有无 Cache 的工期，再在相同 Cache 配置下比较调整前后的计划，区分硬件作用与调度适配。采用同一逐图继承规则后，五核相对整图单核基准的平均加速比为 3.4272；同图同核数的 B/C 综合工期比均值为 1.0136。",
    "最后，进行受控消融与灵敏度分析。固定问题二的五核计划，仅改变 L2 配置，100 张图中 54 图工期缩短、46 图持平，平均硬件效应比为 1.0125；固定 C 配置再调整计划，7 图进一步改善，平均适配比为 1.0011。对六张代表图分别将 Cache 容量与带宽减半、加倍；容量减半与加倍时，逐图相对工期变化的均值分别为 +0.2701% 和 -0.0517%，带宽扰动的工期变化较小，四种配置下重新比较候选后均保留原计划。",
]
KEYWORDS = "多核调度；张量驻留域；拓扑切块；容量约束；FIFO 缓存"
BOLD_SPANS = {
    1: ["计算依赖提取与弱连通分量分析", "FIFO 缓存事件模型"],
    2: ["针对问题一", "Task 驻留域结构搬运模型", "整图分配、分量装箱与拓扑切块", "静态评分", "3.4132", "47502 周期", "4608 字节"],
    3: ["针对问题二", "核心驻留与物理副本容量模型", "关键路径优先", "3.3862", "65 图", "35 图"],
    4: ["针对问题三", "基于查询与完成事件的 FIFO Cache 模型", "同图同核数", "3.4272", "1.0136"],
    5: ["受控消融与灵敏度分析", "54 图", "46 图", "1.0125", "7 图", "1.0011", "+0.2701%", "-0.0517%"],
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
