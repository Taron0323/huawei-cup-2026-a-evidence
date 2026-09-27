"""Verify downloaded originals and extract searchable text without editing them."""

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfReader

root = Path(__file__).resolve().parents[1]
sources = json.loads((root / "来源清单.json").read_text())
checks = []
output = root / "04_附件可检索文本"
output.mkdir(exist_ok=True)
namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

for source in sources:
    path = root / source["path"]
    data = path.read_bytes()
    assert len(data) == source["bytes"], path
    assert hashlib.sha256(data).hexdigest() == source["sha256"], path
    if path.parent.name != "02_官方附件":
        continue
    check = {"path": source["path"], "sha256_matches": True, "bytes": len(data)}
    text = ""
    if path.suffix == ".pdf":
        reader = PdfReader(path)
        check["pages"] = len(reader.pages)
        check["encrypted"] = reader.is_encrypted
        chunks = []
        for index, page in enumerate(reader.pages, 1):
            result = subprocess.run(["pdftotext", "-f", str(index), "-l", str(index), "-layout", str(path), "-"], check=True, capture_output=True, text=True)
            chunks.append(f"--- PDF 第 {index} 页 ---\n\n" + result.stdout)
        text = "\n".join(chunks)
        check["empty_text_pages"] = [i + 1 for i, p in enumerate(reader.pages) if len((p.extract_text() or "").strip()) < 10]
    elif path.suffix == ".docx":
        with ZipFile(path) as archive:
            assert archive.testzip() is None
            body = ET.fromstring(archive.read("word/document.xml"))
            paragraphs = ["".join(n.text or "" for n in p.findall(".//w:t", namespace)) for p in body.findall(".//w:p", namespace)]
            text = "\n\n".join(p for p in paragraphs if p.strip())
            check["zip_crc"] = "PASS"
            check["xml"] = "PASS"
    elif path.suffix == ".doc":
        assert data.startswith(bytes.fromhex("d0cf11e0a1b11ae1"))
        result = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)], check=True, capture_output=True, text=True)
        text = result.stdout
        check["ole_magic"] = "PASS"
        check["textutil_read"] = "PASS"
    check["extracted_characters"] = len(text)
    check["status"] = "PASS"
    (output / (path.name + ".txt")).write_text(f"原文件：{source['path']}\n来源：{source['source_url']}\n说明：以下为检索副本；版式与签章以官方原件为准。\n\n{text}")
    checks.append(check)

report = {"source_records_verified": len(sources), "attachment_count": len(checks), "checks": checks}
(root / "采集记录/下载校验报告.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
