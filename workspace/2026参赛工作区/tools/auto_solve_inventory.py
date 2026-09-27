#!/usr/bin/env python3
"""Create a streaming inventory for the six Huawei Cup problem directories."""

from __future__ import annotations

import argparse
import csv
import hashlib
import mimetypes
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def write_inventory(root: Path, output: Path) -> list[dict[str, object]]:
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        stat = path.stat()
        suffix = path.suffix.lower().lstrip(".") or "[no_ext]"
        rows.append(
            {
                "relative_path": rel(path, root),
                "size_bytes": stat.st_size,
                "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "extension": suffix,
                "mime_guess": mimetypes.guess_type(path.name)[0] or "",
                "sha256": sha256_file(path),
            }
        )
    manifest = output / "file_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["relative_path"])
        writer.writeheader()
        writer.writerows(rows)
    sha_manifest = output / "sha256_manifest.csv"
    with sha_manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "sha256", "size_bytes"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in ("relative_path", "sha256", "size_bytes")})
    return rows


def write_duplicates(rows: list[dict[str, object]], output: Path) -> None:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row["sha256"])].append(row)
    duplicate_groups = [items for items in groups.values() if len(items) > 1]
    duplicate_groups.sort(key=lambda items: str(items[0]["relative_path"]))
    with (output / "duplicate_report.md").open("w", encoding="utf-8") as handle:
        handle.write("# Duplicate input report\n\n")
        handle.write(f"Unique SHA-256 values: {len(groups)}\n\n")
        handle.write(f"Duplicate groups: {len(duplicate_groups)}\n\n")
        for index, items in enumerate(duplicate_groups, 1):
            handle.write(f"## Group {index}: `{items[0]['sha256']}`\n\n")
            for item in items:
                handle.write(f"- `{item['relative_path']}` ({item['size_bytes']} bytes)\n")
            handle.write("\n")


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, f"missing executable: {exc.filename}"
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
    return result.returncode, output


def write_archives(root: Path, output: Path) -> None:
    archive_paths = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".zip", ".rar", ".7z"})
    with (output / "archive_report.md").open("w", encoding="utf-8") as handle:
        handle.write("# Archive report\n\n")
        if not archive_paths:
            handle.write("No ZIP/RAR/7Z files found.\n")
            return
        for path in archive_paths:
            handle.write(f"## `{rel(path, root)}`\n\n")
            if path.suffix.lower() == ".zip":
                test_code, test_output = run_command(["unzip", "-tq", str(path)], root)
                list_code, list_output = run_command(["unzip", "-Z1", str(path)], root)
                handle.write(f"- integrity_exit_code: `{test_code}`\n")
                handle.write(f"- integrity_output: `{test_output or '(empty)'}`\n")
                handle.write(f"- listing_exit_code: `{list_code}`\n")
                listing = list_output.splitlines() if list_output else []
                handle.write(f"- member_count: `{len(listing)}`\n")
                if listing:
                    handle.write("- first_members:\n")
                    for member in listing[:20]:
                        handle.write(f"  - `{member}`\n")
            else:
                handle.write("- integrity: `UNVERIFIED` (no 7z/rar tool was assumed)\n")
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"input root is not a directory: {root}")
    rows = write_inventory(root, output)
    write_duplicates(rows, output)
    write_archives(root, output)
    print(f"inventory_files={len(rows)}")
    print(f"inventory_output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
