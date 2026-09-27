"""Hide only the cover footer in the converted official working copy."""

from pathlib import Path
from zipfile import ZipFile

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "paper/word/working-template.docx"
before = ROOT / "Each Stage Review Work/20260921_02_templates/before-working-template.docx"
if before.exists():
    raise SystemExit("One-time conversion already recorded; do not overwrite the working document")
before.write_bytes(path.read_bytes())
ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
with ZipFile(before) as archive:
    parts = {item.filename: (item, archive.read(item.filename)) for item in archive.infolist()}
document = etree.fromstring(parts["word/document.xml"][1])
section = document.find(".//{" + ns + "}sectPr")
title = section.find("{" + ns + "}titlePg")
if title is None:
    title = etree.SubElement(section, "{" + ns + "}titlePg")
title.set("{" + ns + "}val", "true")
for ref in section.findall("{" + ns + "}footerReference"):
    if ref.get("{" + ns + "}type") == "first":
        section.remove(ref)
with ZipFile(path, "w") as archive:
    for name, (item, data) in parts.items():
        archive.writestr(item, etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone=True)
                         if name == "word/document.xml" else data)
print("Updated only word/document.xml; all other package parts preserved")
