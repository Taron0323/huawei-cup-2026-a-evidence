"""Shared data-directory resolution and manifest-aware count checks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable


DATA_ENV = "PAPER_EVIDENCE_DATA"


def resolve_data_dir(root: Path, cli_value: Path | None, default_relative: str) -> Path:
    """Resolve a data directory while keeping the historical default path."""

    raw = cli_value or os.environ.get(DATA_ENV)
    path = Path(raw).expanduser() if raw else root / default_relative
    return path.resolve()


def _manifest_paths(data_dir: Path) -> Iterable[Path]:
    names = (
        "FINAL_VALIDATION_*.json",
        "EXPERIMENT_MANIFEST_*.json",
        "main_report_manifest.json",
        "merge_manifest.json",
        "audit_summary.json",
        "sensitivity_report_manifest.json",
    )
    seen: set[Path] = set()
    for pattern in names:
        for path in sorted(data_dir.glob(pattern)):
            if path not in seen:
                seen.add(path)
                yield path


def load_manifests(data_dir: Path) -> list[dict]:
    manifests = []
    for path in _manifest_paths(data_dir):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            manifests.append(value)
    return manifests


def _get_path(value: object, path: tuple[str, ...]) -> object | None:
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def declared_count(data_dir: Path, kind: str) -> int | None:
    """Return a declared count when a validation/report manifest provides it."""

    paths: dict[str, tuple[tuple[str, ...], ...]] = {
        "main_rows": (
            ("main_matrix", "rows"),
            ("main_matrix", "expected"),
            ("rows",),
            ("stored_matrix_rows",),
            ("final_combinations",),
        ),
        "cache_pairs": (
            ("cache_pairs", "rows"),
            ("cache_pairs", "expected"),
            ("cache_pairs",),
        ),
        "baseline_rows": (
            ("singlecore_baseline", "rows"),
            ("singlecore_baseline", "expected"),
            ("baseline_rows",),
        ),
        "sensitivity_rows": (
            ("sensitivity", "reoptimized_rows"),
            ("sensitivity", "rows"),
            ("sensitivity_selected_rows",),
        ),
    }
    for manifest in load_manifests(data_dir):
        for path in paths.get(kind, ()):
            value = _get_path(manifest, path)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, float) and value.is_integer():
                return int(value)
    return None


def infer_matrix_shape(main_rows: list[dict[str, str]]) -> dict[str, object]:
    """Infer case/core/scene coverage from the CSV itself."""

    cases = tuple(sorted({row["case"] for row in main_rows}))
    cores = tuple(sorted({int(row["cores"]) for row in main_rows}))
    scenes = tuple(sorted({row["scene"] for row in main_rows}))
    expected_rows = len(cases) * len(cores) * len(scenes)
    keys = {(row["case"], int(row["cores"]), row["scene"]) for row in main_rows}
    if len(keys) != len(main_rows) or len(main_rows) != expected_rows:
        raise AssertionError(
            f"main matrix is not rectangular: rows={len(main_rows)}, "
            f"unique={len(keys)}, expected={expected_rows}"
        )
    return {
        "cases": cases,
        "cores": cores,
        "scenes": scenes,
        "case_count": len(cases),
        "core_count": len(cores),
        "scene_count": len(scenes),
        "main_rows": len(main_rows),
        "expected_rows": expected_rows,
    }


def assert_declared_count(data_dir: Path, actual: int, kind: str) -> int:
    """Assert an optional manifest declaration and return its effective count."""

    declared = declared_count(data_dir, kind)
    if declared is not None and declared != actual:
        raise AssertionError(f"{kind} mismatch: manifest={declared}, csv={actual}")
    return actual if declared is None else declared

