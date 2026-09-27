"""Fill the title and abstract in the retained official Word template.

AI-assisted: Codex / OpenAI, 2026-09-23; exact model/release UNVERIFIED.
Run with the bundled document Python runtime.
"""

from copy import deepcopy
import json
from pathlib import Path
import zipfile
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def main():
    source = ROOT / "paper/word/working-template.docx"
    output = ROOT / "paper/word/a-frontmatter.docx"
    content = json.loads((ROOT / "paper/latex/generated/abstract.json").read_text())
    with zipfile.ZipFile(source) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
        body = document.find(W+"body")
        paragraphs = body.findall(W+"p")
        assert len(paragraphs) >= 24
        assert "题" in "".join(paragraphs[17].itertext())
        assert "关键词" in "".join(paragraphs[23].itertext())

        def replace(p, value, size=24, bold=False, centered=False):
            props = p.find(W+"pPr")
            props = deepcopy(props) if props is not None else etree.Element(W+"pPr")
            for child in list(p):
                p.remove(child)
            for node in list(props):
                if node.tag in {W+"pageBreakBefore", W+"keepNext", W+"spacing", W+"ind", W+"jc", W+"snapToGrid"}:
                    props.remove(node)
            etree.SubElement(props, W+"snapToGrid").set(W+"val", "0")
            spacing = etree.SubElement(props, W+"spacing")
            spacing.set(W+"line", "240")
            spacing.set(W+"lineRule", "auto")
            spacing.set(W+"after", "100")
            etree.SubElement(props,W+"jc").set(W+"val", "center" if centered else "both")
            if not centered:
                etree.SubElement(props, W+"ind").set(W+"firstLineChars", "200")
            p.append(props)
            run = etree.SubElement(p, W+"r")
            rp = etree.SubElement(run,W+"rPr")
            font = etree.SubElement(rp,W+"rFonts")
            font.set(W+"eastAsia", "黑体" if bold else "宋体")
            font.set(W+"ascii", "Times New Roman")
            font.set(W+"hAnsi", "Times New Roman")
            etree.SubElement(rp,W+"sz").set(W+"val",str(size))
            if bold:
                etree.SubElement(rp,W+"b")
            etree.SubElement(run,W+"t").text = value

        replace(paragraphs[17], "题 目："+content["title"], size=32, bold=True, centered=True)
        for p, value in zip(paragraphs[20:23],content["paragraphs"]):
            replace(p,value)
        replace(paragraphs[23],"关键词："+content["keywords"],bold=True)
        for p in paragraphs[24:]:
            body.remove(p)
        core = etree.fromstring(archive.read("docProps/core.xml"))
        for node in core:
            if etree.QName(node).localname in {"creator","lastModifiedBy"}:
                node.text = ""
        with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as target:
            for item in archive.infolist():
                data = archive.read(item.filename)
                if item.filename == "word/document.xml":
                    data = etree.tostring(document,xml_declaration=True,encoding="UTF-8",standalone=True)
                elif item.filename == "docProps/core.xml":
                    data = etree.tostring(core,xml_declaration=True,encoding="UTF-8",standalone=True)
                target.writestr(item,data)
    print(output)


if __name__ == "__main__":
    main()
