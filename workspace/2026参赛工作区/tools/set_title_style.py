"""Apply the explicit 2026 title formatting to the editable abstract title slot."""

from pathlib import Path
from zipfile import ZipFile

from lxml import etree

root = Path(__file__).resolve().parents[1]
path = root / "paper/word/working-template.docx"
before = root / "Each Stage Review Work/20260921_03_latex_compliance/before-title-style.docx"
if before.exists():
    raise SystemExit("Title style already prepared; do not overwrite later writing")
before.write_bytes(path.read_bytes())
ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
w = "{" + ns["w"] + "}"
with ZipFile(path) as archive:
    parts = [(info, archive.read(info.filename)) for info in archive.infolist()]
doc = etree.fromstring(next(data for info, data in parts if info.filename == "word/document.xml"))
paragraph = next(p for p in doc.findall(".//w:body/w:p", ns) if "题 目：" in "".join(p.itertext()))
properties = paragraph.find(w + "pPr")
if properties is None:
    properties = etree.Element(w + "pPr")
    paragraph.insert(0, properties)
jc = properties.find(w + "jc")
if jc is None:
    jc = etree.SubElement(properties, w + "jc")
jc.set(w + "val", "center")
for run in paragraph.findall("w:r", ns):
    props = run.find(w + "rPr")
    if props is None:
        props = etree.Element(w + "rPr")
        run.insert(0, props)
    fonts = props.find(w + "rFonts")
    if fonts is None:
        fonts = etree.SubElement(props, w + "rFonts")
    for name in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(w + name, "SimHei")
    size = props.find(w + "sz")
    if size is None:
        size = etree.SubElement(props, w + "sz")
    size.set(w + "val", "32")
with ZipFile(path, "w") as archive:
    for info, data in parts:
        archive.writestr(info, etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
                         if info.filename == "word/document.xml" else data)
print("Abstract title slot set to SimHei, 16pt, centered; logos and other package parts preserved")
