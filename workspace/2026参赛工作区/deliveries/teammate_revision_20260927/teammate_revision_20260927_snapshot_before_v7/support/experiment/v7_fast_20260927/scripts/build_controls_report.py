#!/usr/bin/env python3
"""Compare completed mechanism controls with the same v7 main snapshot."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evidence_contract import (  # noqa: E402
    check_companion, main_signature, official_hashes, read_complete_manifest,
    selected_scene,
)
from scripts.run_controls import CONTROL_SCENES, REPRESENTATIVE_CASES  # noqa: E402


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--controls-root", type=Path, required=True)
    parser.add_argument("--main-root", type=Path)
    parser.add_argument("--main-roots", type=Path, nargs="+")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--allow-provenance-mismatch", action="store_true")
    args = parser.parse_args()
    controls_root, out = args.controls_root.resolve(), args.output_root.resolve()
    main_roots = [path.resolve() for path in (args.main_roots or ([args.main_root] if args.main_root else []))]
    if not main_roots:
        parser.error("one of --main-root or --main-roots is required")
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    signature = main_signature(main_roots, check_files=False)
    control_manifest = read_complete_manifest(controls_root / "run_manifest.json")
    if not args.allow_provenance_mismatch:
        check_companion(control_manifest, signature, cases=REPRESENTATIVE_CASES)
    if official_hashes(Path(control_manifest["official_evaluator_dir"])) != control_manifest["official_code_sha256"]:
        raise ValueError("control evaluator changed since run")

    with (controls_root / "controls.csv").open(newline="", encoding="utf-8") as handle:
        all_rows = list(csv.DictReader(handle))
    selected = [row for row in all_rows if row["selected"] == "True" and row["status"] == "AI_VERIFIED"]
    expected = {(control, case, cores, scene) for control, scenes in CONTROL_SCENES.items() for case in REPRESENTATIVE_CASES for cores in (2, 5) for scene in scenes}
    actual = {(row["control"], row["case"], int(row["cores"]), row["scene"]) for row in selected}
    if len(selected) != len(expected) or actual != expected:
        raise ValueError(f"incomplete control selections: {len(selected)}/{len(expected)}")

    detail = []
    for row in sorted(selected, key=lambda item: (item["control"], item["case"], int(item["cores"]), item["scene"])):
        key = (row["case"], int(row["cores"]), row["scene"])
        _main_dir, baseline, _main_plan, main_result = selected_scene(main_roots, *key)
        control_selection = json.loads((controls_root / row["control"] / row["case"] / f"{row['cores']}core" / row["scene"] / "final_selection.json").read_text(encoding="utf-8"))
        if control_selection["plan_sha256"] != row["plan_sha256"] or int(control_selection["makespan"]) != int(float(row["makespan"])):
            raise ValueError(f"control CSV disagrees with final selection: {key}")
        if int(baseline["makespan"]) != int(main_result["makespan"]):
            raise ValueError(f"main final selection disagrees with official result: {key}")
        control_ms = int(float(row["makespan"]))
        main_ms = int(baseline["makespan"])
        control_move = int(float(row["added_copy_bytes"]))
        main_move = int(baseline["added_copy_bytes"])
        main_calls, control_calls = int(baseline["full_calls"]), int(control_selection["full_calls"])
        detail.append({
            "control": row["control"], "case": row["case"], "cores": int(row["cores"]), "scene": row["scene"],
            "main_full_calls": main_calls, "control_full_calls": control_calls,
            "official_full_calls_matched": main_calls == control_calls,
            "main_makespan": main_ms, "control_makespan": control_ms,
            "delta_cycles_control_minus_main": control_ms - main_ms,
            "relative_delta_control_minus_main": control_ms / main_ms - 1,
            "main_added_copy_bytes": main_move, "control_added_copy_bytes": control_move,
            "delta_added_copy_bytes": control_move - main_move,
            "main_plan_sha256": baseline["plan_sha256"], "control_plan_sha256": row["plan_sha256"],
            "same_plan": baseline["plan_sha256"] == row["plan_sha256"],
            "control_candidate": row["candidate"], "control_source": row["source"],
        })
    groups = defaultdict(list)
    for row in detail:
        groups[(row["control"], row["scene"], row["cores"])].append(row)
    summary = []
    for (control, scene, cores), rows in sorted(groups.items()):
        matched = [row for row in rows if row["official_full_calls_matched"]]
        summary.append({
            "control": control, "scene": scene, "cores": cores, "cases": len(rows),
            "official_full_calls_matched_cases": len(matched),
            "mean_relative_delta": sum(row["relative_delta_control_minus_main"] for row in rows) / len(rows),
            "matched_mean_relative_delta": sum(row["relative_delta_control_minus_main"] for row in matched) / len(matched) if matched else "",
            "mean_delta_cycles": sum(row["delta_cycles_control_minus_main"] for row in rows) / len(rows),
            "mean_delta_added_copy_bytes": sum(row["delta_added_copy_bytes"] for row in rows) / len(rows),
            "control_slower_cases": sum(row["delta_cycles_control_minus_main"] > 0 for row in rows),
            "control_equal_cases": sum(row["delta_cycles_control_minus_main"] == 0 for row in rows),
            "control_faster_cases": sum(row["delta_cycles_control_minus_main"] < 0 for row in rows),
            "same_plan_cases": sum(row["same_plan"] for row in rows),
        })
    out.mkdir(parents=True)
    write_csv(out / "controls_comparison.csv", detail)
    write_csv(out / "controls_summary.csv", summary)
    matched_summary = [row for row in summary if row["official_full_calls_matched_cases"]]
    if matched_summary:
        fig, ax = plt.subplots(figsize=(9, 4.8), dpi=160)
        labels = [f"{row['control'].replace('_', ' ')}\n{row['scene']} / {row['cores']} cores" for row in matched_summary]
        values = [100 * row["matched_mean_relative_delta"] for row in matched_summary]
        colors = ["#2f8061" if value >= 0 else "#c06442" for value in values]
        ax.bar(range(len(matched_summary)), values, color=colors, width=.68)
        ax.axhline(0, color="#555555", linewidth=.9)
        ax.set_xticks(range(len(matched_summary)), labels, rotation=25, ha="right")
        ax.set_ylabel("Equal official full calls: control minus main (%)")
        ax.grid(axis="y", alpha=.2)
        fig.tight_layout()
        fig.savefig(out / "controls_effect.png")
        fig.savefig(out / "controls_effect.svg")
        fig.savefig(out / "controls_effect.pdf")
        plt.close(fig)

    manifest = {"status": "COMPUTED", "controls_root": str(controls_root), "main_roots": [str(root) for root in main_roots], "source_signature": signature, "selected_groups": len(detail), "summary_groups": len(summary), "equal_full_call_groups": sum(row["official_full_calls_matched_cases"] for row in summary), "budget_note": "Equality counts official full evaluator calls only; profile and candidate-generation work is not matched.", "failed_candidate_rows": sum(row["status"] != "AI_VERIFIED" for row in all_rows), "provenance_warning": "Current solver files differ from the original main-matrix hashes; controls remain linked to their own recorded snapshot." if args.allow_provenance_mismatch else None}
    (out / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
