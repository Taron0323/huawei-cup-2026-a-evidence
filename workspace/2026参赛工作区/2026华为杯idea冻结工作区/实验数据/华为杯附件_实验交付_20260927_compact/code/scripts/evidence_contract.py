"""Check that post-run evidence belongs to one completed solver snapshot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/A题/data"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def official_hashes(code_dir: Path) -> dict[str, str]:
    paths = sorted(code_dir.glob("*.py"))
    if not paths:
        raise ValueError(f"official evaluator has no Python files: {code_dir}")
    return {path.name: sha256(path) for path in paths}


def solver_hashes(*extra: Path) -> dict[str, str]:
    paths = [ROOT / "scripts/run_experiment.py", ROOT / "scripts/run_full_matrix.py"]
    paths.extend(sorted((ROOT / "src").rglob("*.py")))
    paths.extend(extra)
    return {str(path.relative_to(ROOT)): sha256(path) for path in paths}


def read_complete_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "COMPUTED":
        raise ValueError(f"run is not COMPUTED: {path}")
    return manifest


def main_manifests(roots: list[Path]) -> list[dict]:
    manifests = []
    for root in roots:
        parent = read_complete_manifest(root / "run_manifest.json")
        if "official_code_sha256" in parent:
            children = [parent]
        else:
            child_dirs = sorted(root.glob("batch_*")) + sorted(root.glob("case_*_*core"))
            children = [read_complete_manifest(path / "run_manifest.json") for path in child_dirs if path.is_dir()]
            if not children:
                raise ValueError(f"no completed child manifests: {root}")
        manifests.extend(children)
    return manifests


def main_signature(roots: list[Path], *, check_files: bool = True) -> dict:
    manifests = main_manifests(roots)
    required = ("solver_source_sha256", "official_code_sha256", "config_sha256", "idea_sha256", "case_graph_sha256")
    for manifest in manifests:
        missing = [key for key in required if not manifest.get(key)]
        if missing:
            raise ValueError(f"main manifest lacks provenance {missing}: {manifest.get('run_id')}")
    reference = manifests[0]
    graphs = {}
    for manifest in manifests:
        for key in required[:-1]:
            if manifest[key] != reference[key]:
                raise ValueError(f"main runs differ in {key}: {manifest.get('run_id')}")
        for case, digest in manifest["case_graph_sha256"].items():
            if case in graphs and graphs[case] != digest:
                raise ValueError(f"main runs differ in graph bytes: {case}")
            graphs[case] = digest
    if check_files:
        for relative, digest in reference["solver_source_sha256"].items():
            if sha256(ROOT / relative) != digest:
                raise ValueError(f"solver source changed since main run: {relative}")
        if sha256(DATA / "config.txt") != reference["config_sha256"]:
            raise ValueError("config changed since main run")
        if sha256(ROOT / "idea/A题_Final_idea_给codex运行.md") != reference["idea_sha256"]:
            raise ValueError("idea changed since main run")
        for case, digest in graphs.items():
            if sha256(DATA / f"{case}.json") != digest:
                raise ValueError(f"graph changed since main run: {case}")
        code_dir = Path(reference["official_evaluator_dir"])
        if official_hashes(code_dir) != reference["official_code_sha256"]:
            raise ValueError("official evaluator changed since main run")
    return {key: reference[key] for key in required[:-1]} | {"case_graph_sha256": graphs}


def check_companion(manifest: dict, signature: dict, *, cases: list[str] | None = None) -> None:
    for key in ("official_code_sha256", "config_sha256", "idea_sha256"):
        if manifest.get(key) != signature[key]:
            raise ValueError(f"companion run differs from main in {key}")
    source = manifest.get("solver_source_sha256", {})
    for relative, digest in signature["solver_source_sha256"].items():
        if source.get(relative) != digest:
            raise ValueError(f"companion run differs from main in solver source: {relative}")
    for relative, digest in source.items():
        if sha256(ROOT / relative) != digest:
            raise ValueError(f"companion source changed since run: {relative}")
    graphs = manifest.get("case_graph_sha256", {})
    for case in cases or graphs:
        if graphs.get(case) != signature["case_graph_sha256"].get(case):
            raise ValueError(f"companion run differs from main in graph bytes: {case}")


def check_baseline(root: Path, signature: dict) -> None:
    manifest = read_complete_manifest(root / "run_manifest.json")
    if manifest.get("official_code_sha256") != signature["official_code_sha256"]:
        raise ValueError("single-core baseline uses different official evaluator bytes")
    if manifest.get("config_sha256") != signature["config_sha256"]:
        raise ValueError("single-core baseline uses different config bytes")
    graphs = manifest.get("case_graph_sha256", {})
    if graphs != signature["case_graph_sha256"]:
        raise ValueError("single-core baseline graph set or bytes differ from main")
    for batch in manifest.get("batches", []):
        child = read_complete_manifest(Path(batch["output_root"]) / "run_manifest.json")
        for key in ("official_code_sha256", "config_sha256"):
            if child.get(key) != signature[key]:
                raise ValueError(f"single-core baseline batch differs in {key}")
        for case, digest in child.get("case_graph_sha256", {}).items():
            if signature["case_graph_sha256"].get(case) != digest:
                raise ValueError(f"single-core baseline batch differs in graph bytes: {case}")


def scene_dirs(roots: list[Path], case: str, cores: int, scene: str) -> list[Path]:
    found = []
    for root in roots:
        for pattern in (
            f"cases/{case}/{cores}core/{scene}",
            f"batch_*/cases/{case}/{cores}core/{scene}",
            f"case_*_*core/cases/{case}/{cores}core/{scene}",
        ):
            found.extend(sorted(root.glob(pattern)))
    return found


def selected_scene(roots: list[Path], case: str, cores: int, scene: str, which: str = "final") -> tuple[Path, dict, dict, dict]:
    matches = []
    for directory in scene_dirs(roots, case, cores, scene):
        selection_path = directory / f"{which}_selection.json"
        if not selection_path.exists():
            continue
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        candidate = directory / "candidates" / selection["candidate"]
        plan = json.loads((candidate / "plan.json").read_text(encoding="utf-8"))
        result = json.loads((candidate / "result.json").read_text(encoding="utf-8"))
        matches.append((directory, selection, plan, result))
    if not matches:
        raise ValueError(f"missing {which} official result: {case}/{cores}/{scene}")
    if len({(item[1].get("plan_sha256"), item[1].get("makespan")) for item in matches}) != 1:
        raise ValueError(f"conflicting {which} results: {case}/{cores}/{scene}")
    return matches[0]
