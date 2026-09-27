"""Archive public 2026 contest notices and their directly linked attachments."""

import hashlib
import json
import re
from datetime import datetime
from email.message import Message
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://cpipc.acge.org.cn/"
records = []
coverage = []
downloaded = {}


def safe_name(value):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip()[:150]


def fetch(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (public document archival)"})
    with urlopen(request, timeout=45) as response:
        data = response.read()
        return data, response.url, response.headers


def save(data, relative, url, resolved, headers, kind, parent=None):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    record = {
        "path": str(relative), "kind": kind, "source_url": url,
        "resolved_url": resolved, "parent_page": parent,
        "retrieved_at": datetime.now().astimezone().isoformat(),
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "content_type": headers.get("Content-Type"),
        "content_disposition": headers.get("Content-Disposition"),
    }
    records.append(record)
    return record


def attachment(url, parent, label, folder="02_官方附件"):
    if url in downloaded:
        return downloaded[url]
    data, resolved, headers = fetch(url)
    message = Message()
    message["Content-Disposition"] = headers.get("Content-Disposition", "")
    name = unquote(message.get_filename() or Path(urlparse(resolved).path).name)
    if not Path(name).suffix:
        if data.startswith(b"%PDF-"):
            name = safe_name(label) + ".pdf"
        elif data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            name = safe_name(label) + ".doc"
        else:
            raise ValueError(f"Unrecognized attachment: {url}")
    if data.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise ValueError(f"HTML returned instead of attachment: {url}")
    relative = Path(folder) / safe_name(name)
    if (ROOT / relative).exists() and (ROOT / relative).read_bytes() != data:
        relative = relative.with_stem(relative.stem + "_" + hashlib.sha256(data).hexdigest()[:8])
    record = save(data, relative, url, resolved, headers, "original_attachment", parent)
    record["link_label"] = label
    downloaded[url] = str(relative)
    print("DOWNLOADED", relative, len(data), flush=True)
    return str(relative)


def page(url, title, folder="01_官方网页", get_assets=True):
    data, resolved, headers = fetch(url)
    soup = BeautifulSoup(data, "html.parser")
    base_tag = soup.find("base", href=True)
    base = urljoin(resolved, base_tag["href"]) if base_tag else resolved
    article = soup.select_one(".articleContent")
    heading = soup.select_one(".con > .top > .h")
    if heading:
        title = heading.get_text(" ", strip=True)
    stem = safe_name(title)
    save(data, Path(folder) / (stem + ".html"), url, resolved, headers, "original_html")
    content = article or soup.select_one(".content") or soup
    text = f"# {title}\n\n来源：{url}\n\n采集时间：{datetime.now().astimezone().isoformat()}\n\n"
    date = soup.select_one(".con > .top > .p")
    if date:
        text += date.get_text(" ", strip=True) + "\n\n"
    # Keep table rows intact and remove decorative navigation from extracted text.
    for element in content.select("script,style,svg"):
        element.decompose()
    blocks = content.find_all(["p", "tr", "h1", "h2", "h3", "li"])
    text += "\n\n".join(b.get_text("", strip=True) for b in blocks if b.get_text(strip=True)) if blocks else content.get_text("\n", strip=True)
    links = []
    if get_assets:
        for a in content.select("a[href]"):
            link = urljoin(base, a["href"])
            if "sysFile/downFile.do" in link or re.search(r"\.(pdf|docx?|xlsx?|zip|rar)(?:\?|$)", link, re.I):
                label = a.get_text(" ", strip=True)
                local = attachment(link, url, label)
                links.append({"label": label, "url": link, "local_path": local})
        if article:
            for image in article.select("img[src]"):
                link = urljoin(base, image["src"])
                if link.startswith("https://cpipc.acge.org.cn/"):
                    local = attachment(link, url, image.get("alt", "网页内嵌图"), "03_网页内嵌图片")
                    links.append({"label": "网页内嵌图片", "url": link, "local_path": local})
    if links:
        text += "\n\n## 原文附件及图片\n\n" + "\n".join(f"- [{x['label']}]({x['url']})；本地：`{x['local_path']}`" for x in links)
    save(text.encode("utf-8"), Path(folder) / (stem + ".md"), url, resolved, headers, "extracted_text")
    coverage.append({"title": title, "url": url, "status": "DOWNLOADED", "attachments": links})
    print("PAGE", title, flush=True)


def main():
    first = urljoin(BASE, "cw/contestNews/list/4/1")
    data, resolved, headers = fetch(first)
    soup = BeautifulSoup(data, "html.parser")
    listings = {first}
    listings.update(urljoin(BASE, a["href"]) for a in soup.select('a[href]') if re.fullmatch(r"cw/contestNews/list/4/\d+", a["href"]))
    notices = {}
    for url in sorted(listings):
        raw, final, hdr = fetch(url)
        number = urlparse(url).path.rsplit("/", 1)[1]
        save(raw, Path("采集记录/通知列表快照") / f"page-{number}.html", url, final, hdr, "discovery_html")
        document = BeautifulSoup(raw, "html.parser")
        entries = []
        for a in document.select('#notice_list_container a[href]'):
            if "contestNews/detail/4/" not in a["href"]:
                continue
            text = a.get_text(" ", strip=True)
            link = urljoin(BASE, a["href"]).split("?")[0]
            relevant = "2026-" in text[:30] or "第二十三届" in text[:150]
            entries.append({"url": link, "excerpt": text[:160], "selected": relevant})
            if relevant:
                notices[link] = text[:100]
        coverage.append({"url": url, "kind": "notice_listing", "entries": entries})
        print("SCANNED", number, len(entries), flush=True)
    page(urljoin(BASE, "cw/hp/4"), "2026年数学建模竞赛官网首页", get_assets=False)
    for path, title in [("cw/contestIntrol/4", "赛事介绍"), ("cw/contestData/4/12", "组织架构"), ("cw/contestData/4/3", "常见问题"), ("cw/contestData/4/4", "联系我们")]:
        page(urljoin(BASE, path), title)
    for url, title in notices.items():
        page(url, title)


try:
    main()
finally:
    (ROOT / "来源清单.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "采集记录/检索覆盖.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
