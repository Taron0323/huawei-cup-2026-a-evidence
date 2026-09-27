"""Build a browsable paper index and verify a portable archive."""

import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "来源与校验"
report = json.loads((EVIDENCE / "2024_论文校验.json").read_text())
papers = report["selected_papers"]
awards_2025 = json.loads((EVIDENCE / "2025_奖项核对.json").read_text())["awards"]
assert len(papers) == 13

# Read every page to detect broken page streams without rewriting source PDFs.
for paper in papers:
    path = ROOT / paper["path"]
    with pymupdf.open(path) as document:
        text = "\n".join(page.get_text() for page in document)
        first_pages = "\n".join(document[i].get_text() for i in range(2))
    assert paper["team_id"] in first_pages
    assert sum("\u4e00" <= ch <= "\u9fff" for ch in first_pages) > 100
    (EVIDENCE / "2024_首页文本" / (paper["problem"] + paper["team_id"] + ".txt")).write_text(first_pages)
    paper["all_pages_text_extraction"] = "PASS"
    paper["extracted_text_bytes"] = len(text.encode())
    paper["text_extraction_engine"] = "PyMuPDF"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == paper["sha256"]

(EVIDENCE / "2024_论文校验.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
missing_dir = ROOT / "2025"
missing_dir.mkdir(exist_ok=True)
missing = ["# 2025 年论文原文待补齐", "", "截至 2026-09-21，本目录没有已下载并核实的 2025 年数模之星论文 PDF。", "",
           "官方名单及颁奖回顾已下载。名单明确标出 12 支答辩入围队伍；回顾明确冠亚季军及 9 支最终提名奖的数量。其余 9 支在本表保留官方名单的答辩入围措辞。", "",
           "| 论文编号 | 高校 | 已核实奖项状态 | 原文 |", "| --- | --- | --- | --- |"]
for row in awards_2025:
    missing.append(f"| {row['problem']}{row['team_id']} | {row['university']} | {row['final_star_award'] or '数模之星答辩入围'} | 未取得 |")
missing += ["", "## 已核查入口", "",
            "- 官网优秀作品链接 https://www.kdocs.cn/l/cv3j79fp8mZY 当前为冠军队 1 页演示海报，不是完整论文。",
            "- https://github.com/xieyouxixi/hwb-math-modeling-skills 提供 2025 年 21 篇本地论文的文件索引，当前公开 Git 文件树未提供这些 PDF 或下载地址。文件索引不能替代实际原文。",
            "- 标称覆盖 2010-2025 的分享 https://pan.baidu.com/s/1_ezm5JXyuNk3x1HkOpeNoA?pwd=1234 实际可见优秀论文目录为 2011-2023，不符合本次年份。",
            "- 部分公开仓库有 2025 普通一、二等奖论文，但未匹配本次 12 支队伍，未计入本目录。",
            "", "可继续依据以上 12 个论文编号核对新的公开来源；不能把海报、获奖名单或未验证的文件标题计为已下载论文。", ""]
(missing_dir / "原文待补齐.md").write_text("\n".join(missing))

readme = ["# 2024-2025 华为杯研究生数学建模竞赛数模之星论文", "",
          "采集日期：2026-09-21。用途：赛前学习资料；当前项目仍为 PREPARATION。", "",
          "**2024：已取得并核对全部 13 篇（冠军、亚军、季军各 1 篇，提名奖 10 篇）。2025：尚未取得论文原文，已保存 12 支答辩入围队伍的官方依据。**", "",
          "## 2024 论文目录", "",
          "论文来自公开第三方分享的《2024年研究生数学建模竞赛优秀论文选.zip》。该包共 24 篇优秀论文；本目录按官方最终获奖名单准确筛选 13 篇数模之星作品。仅文件名增加奖项与高校标签，PDF 字节与压缩包原件一致。", "",
          "| 奖项 | 高校 | 题号及队伍编号 | 页数 | 原文 |", "| --- | --- | --- | --- | --- |"]
order = {"冠军": 0, "亚军": 1, "季军": 2, "提名奖": 3}
for paper in sorted(papers, key=lambda p: (order[p["award"]], p["problem"], p["team_id"])):
    readme.append(f"| {paper['award']} | {paper['university']} | {paper['problem']}{paper['team_id']} | {paper['pages']} | [PDF]({paper['path']}) |")
readme += ["", "## 2025 状态", "",
           "见 [原文待补齐清单](2025/原文待补齐.md)。已核实冠军为中国矿业大学 C25102900037、亚军为东北电力大学 F25101880004、季军为贵州大学 A25106570253。未把普通获奖论文或单页海报当作数模之星论文。", "",
           "## 来源与验证", "",
           "- 2024 官方颁奖回顾：https://cpipc.acge.org.cn/cw/contestPrevious/detail/4/2c908017963932320196b2fd18ea5158?page=0",
           "- 2024 论文分享：https://pan.baidu.com/s/1uxhi5n47ZsLm9fU1xqpS3g?pwd=opr4 ，提取码 opr4，入口由 https://github.com/zhanwen/MathModel 提供。",
           "- 2025 官方获奖公告：https://cpipc.acge.org.cn/cw/contestNews/detail/4/2c9080179ab48607019ab53c045a01a9?page=2",
           "- 2025 官方颁奖回顾：https://cpipc.acge.org.cn/cw/contestPrevious/detail/4/2c9080189e403095019e49ef61582f94?page=0",
           f"- 2024 原始 ZIP 完整性检查通过；13 篇 PDF 共 {report['total_pages']} 页，PDF 结构和逐页文本读取通过。来源压缩包的 SHA-256、每篇文件的 SHA-256、官方工作表位置见 [论文校验记录](来源与校验/2024_论文校验.json)。",
           "- 原始获奖名单保存在 来源与校验/；原论文内容与结果未做科学复现。",
           "- 采集记录/ 中保存本次整理脚本；来源清单记录实际下载网页和官方名单来源。", ""]
(ROOT / "README.md").write_text("\n".join(readme))

with (ROOT / "论文目录.csv").open("w", newline="", encoding="utf-8-sig") as file:
    writer = csv.writer(file)
    writer.writerow(["年份", "题号", "队伍编号", "高校", "奖项状态", "原文状态", "页数", "本地文件"])
    for row in papers:
        writer.writerow([2024, row["problem"], row["team_id"], row["university"], row["award"], "已下载核对", row["pages"], row["path"]])
    for row in awards_2025:
        writer.writerow([2025, row["problem"], row["team_id"], row["university"], row["final_star_award"] or "数模之星答辩入围", "未取得", "", ""])

search_log = Path("/tmp/huawei-2025-search/search_log.json")
if search_log.exists():
    shutil.copyfile(search_log, ROOT / "采集记录/2025_检索记录.json")

manifest = [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(ROOT.rglob("*")) if p.is_file() and p.name not in {"文件清单.json", ".DS_Store"}]
(ROOT / "文件清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
archive_path = ROOT.parent / "数模之星论文_2024已齐13篇_2025待补原文.zip"
with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and p.name != ".DS_Store":
            archive.write(p, Path(ROOT.name) / p.relative_to(ROOT))
with zipfile.ZipFile(archive_path) as archive:
    assert archive.testzip() is None
    for item in manifest:
        raw = archive.read(str(Path(ROOT.name) / item["path"]))
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
print(json.dumps({"archive": str(archive_path), "archive_bytes": archive_path.stat().st_size,
                  "archive_crc": "PASS", "manifest_entries": len(manifest),
                  "papers_2024": len(papers), "pages_2024": report["total_pages"], "papers_2025": 0}, ensure_ascii=False, indent=2))
