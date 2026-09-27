"""Package authored outputs and textual evidence, verifying every archived byte."""

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "华为杯冲冠军_Skill与报告_2024研究.zip"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def included(p):
    rel = p.relative_to(ROOT)
    if p.name == ".DS_Store" or "__pycache__" in rel.parts:
        return False
    if len(rel.parts) == 1:
        return p.suffix in {".md", ".pdf"}
    if rel.parts[0] in {"huawei-cup-champion", "scripts"}:
        return p.suffix in {".md", ".yaml", ".py", ".mjs"}
    if rel.parts[0] == "evidence":
        return p.suffix in {".md", ".json", ".txt", ".xlsx"}
    return False


required = [
    "华为杯冲冠军报告.md", "华为杯冲冠军报告.pdf", "交付说明.md",
    "huawei-cup-champion/SKILL.md", "huawei-cup-champion/agents/openai.yaml",
    "evidence/共性核对表.json", "evidence/交付验证.md",
    "evidence/independent_review.md", "evidence/skill_behavior_test.md",
]
for rel in required:
    if not (ROOT / rel).is_file():
        raise RuntimeError(f"Missing deliverable: {rel}")
files = sorted(p for p in ROOT.rglob("*") if p.is_file() and included(p))
manifest = []
with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        data = p.read_bytes()
        archive.writestr(f"{ROOT.name}/{rel}", data)
        manifest.append({"path": rel, "bytes": len(data), "sha256": sha256(data)})
with zipfile.ZipFile(OUTPUT) as archive:
    if archive.testzip() is not None:
        raise RuntimeError("ZIP CRC check failed")
    for item in manifest:
        data = archive.read(f"{ROOT.name}/{item['path']}")
        if sha256(data) != item["sha256"]:
            raise RuntimeError(f"ZIP bytes changed: {item['path']}")
result = {
    "status": "PASS", "file_count": len(files), "zip_bytes": OUTPUT.stat().st_size,
    "zip_sha256": sha256(OUTPUT.read_bytes()), "crc_verified": True,
    "all_entry_hashes_verified": True, "files": manifest,
}
verification = OUTPUT.with_suffix(".verification.json")
verification.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "files"}, ensure_ascii=False))
