"""Preserve award evidence and select downloaded papers by verified team ID."""

import hashlib
import json
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
EVIDENCE = ROOT / "来源与校验"
SOURCE_ZIP = Path.home() / "Downloads/2024年研究生数学建模竞赛优秀论文选.zip"
SHARE_URL = "https://pan.baidu.com/s/1uxhi5n47ZsLm9fU1xqpS3g?pwd=opr4"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prepare_evidence():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    snapshot = WORKSPACE / "Each Stage Review Work/20260921_star_papers"
    snapshot.mkdir(exist_ok=True)
    for name in ["STATUS.md", "HANDOFF.md"]:
        source = WORKSPACE / name
        target = snapshot / ("before_" + name)
        if source.exists() and not target.exists():
            shutil.copyfile(source, target)

    records = []
    for year, suffix in [(2024, "xlsx"), (2025, "rar")]:
        source_dir = Path(f"/tmp/huawei-{year}-search")
        source = source_dir / f"{year}-final-awards.{suffix}"
        target = EVIDENCE / f"{year}_官方获奖名单.{suffix}"
        shutil.copyfile(source, target)
        data = json.loads((source_dir / "verified_awards.json").read_text())
        assert digest(target) == data["source_sha256"]
        data["source_file_local"] = str(target.relative_to(ROOT))
        if year == 2025:
            for record in data.get("extracted_source_files", []):
                item = Path(record["path"])
                local = EVIDENCE / "2025_官方获奖名单解包" / item.name
                local.parent.mkdir(exist_ok=True)
                shutil.copyfile(item, local)
                record["path"] = str(local.relative_to(ROOT))
            for row in data["awards"]:
                row["source_file"] = str(Path("来源与校验/2025_官方获奖名单解包") / Path(row["source_file"]).name)
        write_json(EVIDENCE / f"{year}_奖项核对.json", data)
        records.append({"path": str(target.relative_to(ROOT)), "source_url": data["source_file_url"],
                        "parent_page": data["source_page_url"], "sha256": digest(target),
                        "bytes": target.stat().st_size, "kind": "official_awards_original"})
        pages = {"获奖来源网页": data["source_page_url"]}
        if year == 2025:
            pages["颁奖回顾"] = data["official_awards_review_url"]
        for name, url in pages.items():
            target = EVIDENCE / f"{year}_{name}.html"
            if not target.exists():
                target.write_bytes(urlopen(url, timeout=30).read())
            records.append({"path": str(target.relative_to(ROOT)), "source_url": url,
                            "sha256": digest(target), "bytes": target.stat().st_size,
                            "kind": "official_html"})
    write_json(EVIDENCE / "来源清单.json", {"archived_at": datetime.now().astimezone().isoformat(), "records": records})
    print("Award evidence preserved", flush=True)


def extract_2024():
    if not SOURCE_ZIP.exists():
        print("2024 source ZIP is still downloading", flush=True)
        return
    awards = json.loads((EVIDENCE / "2024_奖项核对.json").read_text())["awards"]
    output = ROOT / "2024"
    output.mkdir(exist_ok=True)
    report = []
    with zipfile.ZipFile(SOURCE_ZIP) as archive:
        assert archive.testzip() is None, "Source ZIP CRC failure"
        entries = archive.infolist()
        for row in awards:
            key = row["problem"] + row["team_id"]
            matches = [x for x in entries if key.lower() in x.filename.lower() and x.filename.lower().endswith(".pdf")]
            assert len(matches) == 1, (key, len(matches))
            entry = matches[0]
            raw = archive.read(entry)
            assert raw.startswith(b"%PDF-"), key
            target = output / f"{row['star_award']}_{row['university']}_{key}.pdf"
            if target.exists():
                assert target.read_bytes() == raw
            else:
                target.write_bytes(raw)
            info = subprocess.run(["pdfinfo", str(target)], capture_output=True, text=True, check=True)
            pages = next(int(line.split(":", 1)[1]) for line in info.stdout.splitlines() if line.startswith("Pages:"))
            text = subprocess.run(["pdftotext", "-f", "1", "-l", "2", str(target), "-"], capture_output=True, text=True, check=True).stdout
            text_path = EVIDENCE / "2024_首页文本" / (key + ".txt")
            text_path.parent.mkdir(exist_ok=True)
            text_path.write_text(text)
            report.append({"path": str(target.relative_to(ROOT)), "team_id": row["team_id"],
                           "problem": row["problem"], "university": row["university"], "award": row["star_award"],
                           "pages": pages, "bytes": len(raw), "sha256": digest(target),
                           "archive_entry": entry.filename, "source_url": SHARE_URL,
                           "team_id_visible_on_first_pages": row["team_id"] in text,
                           "official_award_sheet": row["sheet"], "official_award_row": row["row"]})
            print("VERIFIED", target.name, pages, "pages", flush=True)
    write_json(EVIDENCE / "2024_论文校验.json", {"source_archive": str(SOURCE_ZIP),
               "source_share_url": SHARE_URL, "source_archive_sha256": digest(SOURCE_ZIP),
               "source_archive_bytes": SOURCE_ZIP.stat().st_size, "source_zip_crc": "PASS",
               "source_pdf_count": sum(x.filename.lower().endswith(".pdf") for x in entries),
               "selected_papers": report, "count": len(report), "total_pages": sum(x["pages"] for x in report)})


if __name__ == "__main__":
    prepare_evidence()
    extract_2024()
