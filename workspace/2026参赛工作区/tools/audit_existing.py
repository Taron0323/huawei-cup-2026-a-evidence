"""Inventory the pre-existing workspace and verify its two historical packages."""

import csv
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    items = []
    packages = []
    for folder in [PARENT / "华为杯中国研究生数学建模竞赛_流程复盘包_20260913",
                   PARENT / "2026官方资料_截至20260916"]:
        manifest = json.loads((folder / "文件清单.json").read_text())
        entries = manifest["files"] if isinstance(manifest, dict) else manifest
        errors = []
        listed = {e["path"] for e in entries}
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            relative = path.relative_to(folder).as_posix()
            items.append({"path": str(path.relative_to(PARENT)), "bytes": len(data), "sha256": digest(data)})
            if path.suffix == ".json":
                json.loads(data)
            if path.suffix == ".csv":
                rows = list(csv.reader(data.decode("utf-8-sig").splitlines()))
                if rows and any(len(row) != len(rows[0]) for row in rows[1:]):
                    errors.append("CSV column mismatch: " + relative)
            if relative not in listed and relative != "文件清单.json":
                errors.append("unlisted: " + relative)
        for e in entries:
            p = folder / e["path"]
            if not p.is_file() or digest(p.read_bytes()) != e["sha256"] or p.stat().st_size != e["bytes"]:
                errors.append("manifest mismatch: " + e["path"])
        archive_path = folder.with_suffix(".zip")
        with ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                errors.append("ZIP CRC failure")
            zipped = {}
            metadata_entries = 0
            recovered_names = 0
            for name in archive.namelist():
                if name.endswith("/"):
                    continue
                if name.startswith("__MACOSX/"):
                    metadata_entries += 1
                    continue
                decoded = name
                if not archive.getinfo(name).flag_bits & 0x800:
                    try:
                        decoded = name.encode("cp437").decode("utf-8")
                        recovered_names += decoded != name
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                parts = Path(decoded).parts
                if name.startswith("/") or ".." in parts:
                    errors.append("unsafe archive path: " + name)
                rel = Path(*parts[1:]).as_posix() if parts[0] == folder.name else decoded
                zipped[rel] = digest(archive.read(name))
            actual = {p.relative_to(folder).as_posix(): digest(p.read_bytes()) for p in folder.rglob("*") if p.is_file()}
            if zipped != actual:
                errors.append("ZIP and extracted directory differ")
        items.append({"path": archive_path.name, "bytes": archive_path.stat().st_size, "sha256": digest(archive_path.read_bytes())})
        packages.append({"directory": folder.name, "files": len(actual), "manifest_entries": len(entries),
                         "zip_files": len(zipped), "metadata_entries": metadata_entries,
                         "recovered_utf8_names": recovered_names, "errors": errors})
    p = PARENT / "文件夹审查报告_20260916.md"
    items.append({"path": p.name, "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())})
    output = ROOT / "Each Stage Review Work/20260921_01_initial"
    output.mkdir(parents=True, exist_ok=True)
    report = {"scope": "All pre-existing non-OS files; .DS_Store excluded", "files": items, "packages": packages}
    target = output / "reviewed_inventory.json"
    if target.exists():
        old = json.loads(target.read_text())
        if old != report:
            raise SystemExit("Historical files changed; initial evidence not overwritten")
    else:
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"files": len(items), "packages": packages}, ensure_ascii=False, indent=2))
    if any(p["errors"] for p in packages):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
