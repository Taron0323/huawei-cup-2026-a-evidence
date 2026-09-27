"""Extract immutable 2024 source papers into page-addressable research copies."""

import hashlib
import json
import shutil
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
SOURCE = ROOT.parent / "数模之星优秀论文_2024-2025"
validation = json.loads((SOURCE / "来源与校验/2024_论文校验.json").read_text())
corpus = ROOT / "evidence/corpus"
corpus.mkdir(parents=True, exist_ok=True)
snapshot = WORKSPACE / "Each Stage Review Work/20260923_champion_skill"
snapshot.mkdir(parents=True, exist_ok=True)
for name in ["STATUS.md", "HANDOFF.md"]:
    target = snapshot / ("before_" + name)
    if not target.exists():
        shutil.copyfile(WORKSPACE / name, target)
records = []
for item in validation["selected_papers"]:
    path = SOURCE / item["path"]
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha == item["sha256"]
    key = item["problem"] + item["team_id"]
    with pymupdf.open(path) as document:
        pages = [{"pdf_page": i + 1, "text": page.get_text(sort=True)} for i, page in enumerate(document)]
    (corpus / f"{key}.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n")
    (corpus / f"{key}.txt").write_text("\n\n".join(f"===== PDF PAGE {page['pdf_page']} =====\n{page['text']}" for page in pages))
    records.append({"id": key, "award": item["award"], "university": item["university"],
                    "problem": item["problem"], "pdf_pages": len(pages), "sha256": sha,
                    "source_path": str(path.relative_to(WORKSPACE)), "text_chars": sum(len(p["text"]) for p in pages)})
(ROOT / "evidence/source_manifest.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(records, ensure_ascii=False, indent=2))
