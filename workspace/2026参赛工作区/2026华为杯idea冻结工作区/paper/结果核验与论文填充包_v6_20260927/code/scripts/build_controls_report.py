#!/usr/bin/env python3
"""Compare the three completed mechanism controls with the v6 main run."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from run_controls import CONTROL_SCENES, REPRESENTATIVE_CASES


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--controls-root", type=Path, required=True)
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    controls_root, main_root, out = (path.resolve() for path in (args.controls_root, args.main_root, args.output_root))
    if out.exists():
        raise SystemExit(f"refusing existing output: {out}")
    out.mkdir(parents=True)

    with (controls_root / "controls.csv").open(newline="", encoding="utf-8") as handle:
        all_rows = list(csv.DictReader(handle))
    selected = [row for row in all_rows if row["selected"] == "True" and row["status"] == "AI_VERIFIED"]
    expected = {(control, case, cores, scene) for control, scenes in CONTROL_SCENES.items() for case in REPRESENTATIVE_CASES for cores in (2, 5) for scene in scenes}
    actual = {(row["control"], row["case"], int(row["cores"]), row["scene"]) for row in selected}
    if len(selected) != len(expected) or actual != expected:
        raise ValueError(f"incomplete control selections: {len(selected)}/{len(expected)}")

    main = {}
    for path in main_root.glob("batch_*/cases/case_*/*core/*/final_selection.json"):
        scene_dir = path.parent
        key = (scene_dir.parent.parent.name, int(scene_dir.parent.name[:-4]), scene_dir.name)
        if any((control, *key) in expected for control in CONTROL_SCENES):
            main[key] = json.loads(path.read_text(encoding="utf-8"))

    detail = []
    for row in sorted(selected, key=lambda item: (item["control"], item["case"], int(item["cores"]), item["scene"])):
        key = (row["case"], int(row["cores"]), row["scene"])
        baseline = main[key]
        control_ms = int(float(row["makespan"]))
        main_ms = int(baseline["makespan"])
        control_move = int(float(row["added_copy_bytes"]))
        main_move = int(baseline["added_copy_bytes"])
        detail.append({
            "control": row["control"], "case": row["case"], "cores": int(row["cores"]), "scene": row["scene"],
            "main_full_calls": int(baseline["full_calls"]), "budget_matched": int(baseline["full_calls"]) <= 2,
            "main_makespan": main_ms, "control_makespan": control_ms,
            "delta_cycles_control_minus_main": control_ms - main_ms,
            "relative_delta_control_minus_main": control_ms / main_ms - 1,
            "main_added_copy_bytes": main_move, "control_added_copy_bytes": control_move,
            "delta_added_copy_bytes": control_move - main_move,
            "main_plan_sha256": baseline["plan_sha256"], "control_plan_sha256": row["plan_sha256"],
            "same_plan": baseline["plan_sha256"] == row["plan_sha256"],
            "control_candidate": row["candidate"], "control_source": row["source"],
        })
    write_csv(out / "controls_comparison.csv", detail)

    groups = defaultdict(list)
    for row in detail:
        groups[(row["control"], row["scene"], row["cores"])].append(row)
    summary = []
    for (control, scene, cores), rows in sorted(groups.items()):
        matched = [row for row in rows if row["budget_matched"]]
        summary.append({
            "control": control, "scene": scene, "cores": cores, "cases": len(rows),
            "budget_matched_cases": len(matched),
            "mean_relative_delta": sum(row["relative_delta_control_minus_main"] for row in rows) / len(rows),
            "matched_mean_relative_delta": sum(row["relative_delta_control_minus_main"] for row in matched) / len(matched) if matched else "",
            "mean_delta_cycles": sum(row["delta_cycles_control_minus_main"] for row in rows) / len(rows),
            "mean_delta_added_copy_bytes": sum(row["delta_added_copy_bytes"] for row in rows) / len(rows),
            "control_slower_cases": sum(row["delta_cycles_control_minus_main"] > 0 for row in rows),
            "control_equal_cases": sum(row["delta_cycles_control_minus_main"] == 0 for row in rows),
            "control_faster_cases": sum(row["delta_cycles_control_minus_main"] < 0 for row in rows),
            "same_plan_cases": sum(row["same_plan"] for row in rows),
        })
    write_csv(out / "controls_summary.csv", summary)

    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=160)
    labels = [f"{row['control'].replace('_', ' ')}\n{row['scene']} / {row['cores']} cores" for row in summary]
    values = [100 * row["matched_mean_relative_delta"] for row in summary]
    colors = ["#2f8061" if value >= 0 else "#c06442" for value in values]
    ax.bar(range(len(summary)), values, color=colors, width=.68)
    ax.axhline(0, color="#555555", linewidth=.9)
    ax.set_xticks(range(len(summary)), labels, rotation=25, ha="right")
    ax.set_ylabel("Matched-budget control minus main makespan (%)")
    ax.grid(axis="y", alpha=.2)
    fig.tight_layout()
    fig.savefig(out / "controls_effect.png")
    fig.savefig(out / "controls_effect.svg")
    fig.savefig(out / "controls_effect.pdf")
    plt.close(fig)

    manifest = {"status": "COMPUTED", "controls_root": str(controls_root), "main_root": str(main_root), "selected_groups": len(detail), "summary_groups": len(summary), "failed_candidate_rows": sum(row["status"] != "AI_VERIFIED" for row in all_rows)}
    (out / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
