"""Render complete, compact appendix tables from the frozen V0.7.1 CSVs."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/v071_full_20260924_v2"
ANALYSIS = ROOT / "results/v071_full_20260924_v2_analysis"
GENERATED = ROOT / "paper/latex/generated"


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def table(caption, label, header, rows):
    assert len(header) <= 7 and all(len(row) == len(header) for row in rows)
    n = len(header)
    heading = " & ".join(header) + r" \\"
    return "\n".join([
        r"\begin{longtable}{" + "c" + "r" * (n - 1) + "}",
        r"\caption{" + caption + r"}\label{" + label + r"}\\",
        r"\toprule", heading, r"\midrule", r"\endfirsthead",
        r"\multicolumn{" + str(n) + r"}{c}{\tablename\ \thetable\ （续）}\\",
        r"\toprule", heading, r"\midrule", r"\endhead",
        r"\midrule\multicolumn{" + str(n) + r"}{r}{续下页}\\",
        r"\endfoot", r"\bottomrule", r"\endlastfoot",
        *[" & ".join(row) + r" \\" for row in rows],
        r"\end{longtable}", "",
    ])


def main():
    selected_path = ANALYSIS / "selected_summary.csv"
    pair_path = ANALYSIS / "cache_pairs.csv"
    selected = read_csv(selected_path)
    pairs = read_csv(pair_path)
    index = {(r["case"], int(r["cores"]), r["scene"]): r for r in selected}
    pair_index = {(r["case"], int(r["cores"])): r for r in pairs}
    cases = sorted({r["case"] for r in selected})
    assert len(selected) == len(index) == 1425
    assert len(pairs) == len(pair_index) == 475
    assert len(cases) == 95
    assert all(r["status"] == "AI_VERIFIED" for r in selected)
    assert all(r["pair_status"] == "AI_VERIFIED" for r in pairs)

    selected_tables, cache_tables = [], []
    for cores in range(1, 6):
        selected_rows, cache_rows = [], []
        for case in cases:
            row = [case.removeprefix("case_")]
            for scene in "ABC":
                item = index[case, cores, scene]
                makespan = int(item["makespan"])
                speedup = int(item["baseline_makespan"]) / makespan
                row += [f"{makespan}/{speedup:.4f}", item["added_copy_bytes"]]
            selected_rows.append(row)
            pair = pair_index[case, cores]
            no_l2, with_l2 = int(pair["no_l2_makespan"]), int(pair["cache_makespan"])
            hit, miss = int(pair["cache_hit_bytes"]), int(pair["cache_miss_bytes"])
            assert pair["plan_sha256"] == index[case, cores, "C"]["plan_sha256"]
            assert with_l2 == int(index[case, cores, "C"]["makespan"])
            assert int(pair["cache_added_copy_bytes"]) == int(index[case, cores, "C"]["added_copy_bytes"])
            cache_rows.append([case.removeprefix("case_"), str(no_l2), str(with_l2),
                               f"{no_l2/with_l2:.6f}", pair["no_l2_added_copy_bytes"],
                               pair["cache_added_copy_bytes"], f"{100*hit/(hit+miss):.4f}"])
        selected_tables.append(table(
            f"{cores}核下三问的完整结果（95个实例）", f"tab:appendix-selected-{cores}",
            ["实例", r"$T_1/S_1$", r"$Q_1$/B", r"$T_2/S_2$", r"$Q_2$/B", r"$T_3/S_3$", r"$Q_3$/B"],
            selected_rows))
        cache_tables.append(table(
            f"{cores}核下同计划Cache配对结果（95个实例）", f"tab:appendix-cache-{cores}",
            ["实例", r"$T_{\mathrm{off}}$", r"$T_{\mathrm{on}}$", r"$S_{\mathrm{cache}}$",
             r"$Q_{\mathrm{off}}$/B", r"$Q_{\mathrm{on}}$/B", r"$h_{\mathrm{byte}}$/\%"],
            cache_rows))
    GENERATED.mkdir(parents=True, exist_ok=True)
    banner = "% Generated from v071_full_20260924_v2_analysis only.\n"
    selected_output = GENERATED / "writing_selected_appendix.tex"
    cache_output = GENERATED / "writing_cache_appendix.tex"
    selected_output.write_text(banner + "\n".join(selected_tables), encoding="utf-8")
    cache_output.write_text(banner + "\n".join(cache_tables), encoding="utf-8")

    all_cases = json.loads((RUN / "run_manifest.json").read_text())["cases"]
    missing = sorted(set(all_cases) - set(cases))
    assert missing == ["case_014", "case_072", "case_076", "case_087", "case_091"]
    missing_rows = []
    for case in missing:
        graph = json.loads((ROOT / f"inputs/raw/A题/附件/data/{case}.json").read_text())
        view = json.loads((RUN / f"cases/{case}/5core/static_view.json").read_text())
        compute = sum(op["op"] not in {"COPY_IN", "COPY_OUT"} for op in graph["ops"])
        assert compute == view["n_compute"]
        missing_rows.append([case.removeprefix("case_"), str(len(graph["ops"])), str(compute), "1--5"])
    coverage = [banner, r"\begin{tabular}{crrc}", r"\toprule",
                r"实例 & 原图操作数 & 计算操作数 & 待评估核数 \\", r"\midrule"]
    coverage += [" & ".join(row) + r" \\" for row in missing_rows]
    coverage += [r"\bottomrule", r"\end{tabular}", ""]
    (GENERATED / "writing_coverage.tex").write_text("\n".join(coverage), encoding="utf-8")
    print(json.dumps({"selected_records": len(selected), "selected_table_rows": 475,
                      "cache_records": len(pairs), "longtables": 10, "columns_per_longtable": 7,
                      "missing": missing_rows,
                      "sources": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in [selected_path, pair_path]},
                      "checks": "PASS: complete key grid, status, plan pairing, cache result and byte matching"},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
