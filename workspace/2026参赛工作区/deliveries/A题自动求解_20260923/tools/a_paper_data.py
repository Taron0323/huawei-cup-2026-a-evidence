"""Generate every numerical paper table and abstract from verified A results.

AI-assisted: Codex / OpenAI, 2026-09-23; exact model/release UNVERIFIED.
"""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src/a_solver"))
from run_batch import save_json, sha, write_csv


def read(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "paper/latex/generated")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary = read(args.analysis / "summary.csv")
    selected = read(args.analysis / "selected_metrics.csv")
    cache = read(args.analysis / "cache_summary.csv")
    pairs = read(args.analysis / "cache_pairs.csv")
    all_rows = read(args.analysis / "all_metrics.csv")
    assert len(selected) == 1500 and len(pairs) == 500
    idx = {(int(r["problem"]), int(r["cores"]), r["algorithm"]): r for r in summary}
    best = lambda q, k, field: float(idx[q, k, "portfolio"][field])
    title = "基于组件保留与组批的多核计算图调度"
    abstract = [
        "针对共享DDR带宽与私有缓存约束下的多核计算图调度，建立以总完工周期为主、额外搬运量为辅的有限候选搜索模型。利用操作依赖图的组件结构，联合确定子图划分、核心分配与执行顺序，并由题目评估器展开换入换出和多核事件模拟。",
        f"针对问题一，构造拓扑均衡基线、组件同核保留和独立组件组批三种方案，以实际评估择优；对劣于单核的情况补算单核占用回退。2至5核的平均加速比分别为{best(1,2,'mean_speedup'):.4f}、{best(1,3,'mean_speedup'):.4f}、{best(1,4,'mean_speedup'):.4f}、{best(1,5,'mean_speedup'):.4f}。问题二通过同核子图合并复用私有缓存，2至5核平均加速比分别为{best(2,2,'mean_speedup'):.4f}、{best(2,3,'mean_speedup'):.4f}、{best(2,4,'mean_speedup'):.4f}、{best(2,5,'mean_speedup'):.4f}。平均值均为逐用例加速比的算术平均。",
        f"针对问题三，在相同方案上配对比较无L2与1MiB只读FIFO Cache，5核平均Cache加速比为{float(cache[-1]['same_plan_cache_speedup']):.4f}，跨用例字节加权命中率为{best(3,5,'byte_weighted_cache_hit_rate')*100:.2f}%。进一步考察分块规模、Cache容量与带宽，并报告随机对照的多种子波动。完成{len(all_rows)}组固定配置评估及独立时间线检查，小规模16种分配与解析最优值一致。所给结果为候选集合中的最好可行解，完整逐例结果、计划与复现代码随附。",
    ]
    save_json(out / "abstract.json", {"title": title, "paragraphs": abstract,
        "keywords": "多核调度；计算图划分；共享带宽；组件组批；只读缓存"})
    macros = {"QOneFive": best(1,5,"mean_speedup"), "QTwoFive": best(2,5,"mean_speedup"),
              "QThreeFive": best(3,5,"mean_speedup"),
              "CacheFive": float(cache[-1]["same_plan_cache_speedup"]),
              "CacheHitFive": 100 * best(3,5,"byte_weighted_cache_hit_rate")}
    values = "\n".join(
        "\\newcommand{\\" + name + "}{" + f"{value:.4f}" + "}" for name, value in macros.items()) + "\n"
    integers = {"EvalCount":len(all_rows), "PlanCount":len(selected), "PairCount":len(pairs),
                "FallbackCount":sum(r["algorithm"] == "singlecore" and int(r["cores"]) > 1 for r in selected),
                "CacheSlowCount":sum(float(r["same_plan_cache_speedup"]) < 1 for r in pairs)}
    values += "\n".join("\\newcommand{\\"+name+"}{"+str(value)+"}" for name,value in integers.items()) + "\n"
    (out / "numbers.tex").write_text(values)
    adverse = [r for r in pairs if float(r["same_plan_cache_speedup"]) < 1]
    (out / "cache_adverse.tex").write_text("\n".join(
        f"用例{r['case'][-3:]}在{r['cores']}核下，无L2为{r['same_plan_no_l2_makespan']}周期，启用L2后为{r['same_plan_l2_makespan']}周期，增加{int(r['same_plan_l2_makespan'])-int(r['same_plan_no_l2_makespan'])}周期。"
        for r in adverse) + "\n")
    for q in (1, 2, 3):
        lines = []
        for k in range(1, 6):
            vals = [float(idx[q,k,a]["mean_speedup"]) for a in
                    ("balanced_greedy", "component_aware", "component_packed", "portfolio")]
            lines.append(f"{k} & " + " & ".join(f"{x:.4f}" for x in vals) + r" \\")
        (out / f"speedup_q{q}.tex").write_text("\n".join(lines) + "\n")
    (out / "cache_summary.tex").write_text("\n".join(
        f"{r['cores']} & {float(r['same_plan_no_l2_makespan']):.2f} & {float(r['same_plan_l2_makespan']):.2f} & {float(r['same_plan_cache_speedup']):.4f} & {float(r['independently_selected_speedup']):.4f} & {r['cache_slowdown_cases']}" + r" \\"
        for r in cache) + "\n")
    alg_short = {"balanced_greedy":"T", "component_aware":"C", "component_packed":"P", "singlecore":"S"}
    win_lines = []
    for q in (1,2,3):
        count = Counter(r["algorithm"] for r in selected if int(r["problem"]) == q and int(r["cores"]) > 1)
        win_lines.append(f"{q} & " + " & ".join(str(count[a]) for a in alg_short) + r" \\")
    (out / "winner_counts.tex").write_text("\n".join(win_lines)+"\n")
    index = {(r["case"], int(r["cores"]), int(r["problem"])):r for r in selected}
    lines = [r"\begingroup\footnotesize\setlength{\tabcolsep}{3pt}",
             r"\begin{longtable}{ccrrrrrr}",
             r"\caption{全部用例的已选方案指标。$M$为周期，$D$为额外搬运字节。}\label{tab:allcases}\\",
             r"\toprule 用例 & 核数 & $M_1$ & $D_1$ & $M_2$ & $D_2$ & $M_3$ & $D_3$\\\midrule\endfirsthead",
             r"\toprule 用例 & 核数 & $M_1$ & $D_1$ & $M_2$ & $D_2$ & $M_3$ & $D_3$\\\midrule\endhead",
             r"\midrule\multicolumn{8}{r}{续下页}\endfoot\bottomrule\endlastfoot"]
    for case in sorted({r["case"] for r in selected}):
        for k in range(1,6):
            vals = [index[case,k,q][field] for q in (1,2,3) for field in ("makespan","added_copy_bytes")]
            lines.append(case[-3:] + f" & {k} & " + " & ".join(vals) + r" \\")
    lines += [r"\end{longtable}\endgroup"]
    (out / "all_cases.tex").write_text("\n".join(lines)+"\n")
    lines = [r"\begingroup\footnotesize\setlength{\tabcolsep}{3pt}", r"\begin{longtable}{cccrrrrrr}",
             r"\caption{同方案Cache配对结果。命中率$H$按字节计算；T、C、P、S对应四类候选。}\label{tab:cachecases}\\",
             r"\toprule 用例 & 核 & 候选 & 无L2周期 & L2周期 & 无L2额外字节 & L2额外字节 & 比值 & $H$\\\midrule\endfirsthead",
             r"\toprule 用例 & 核 & 候选 & 无L2周期 & L2周期 & 无L2额外字节 & L2额外字节 & 比值 & $H$\\\midrule\endhead",
             r"\midrule\multicolumn{9}{r}{续下页}\endfoot\bottomrule\endlastfoot"]
    for r in sorted(pairs, key=lambda r:(r["case"],int(r["cores"]))):
        lines.append(f"{r['case'][-3:]} & {r['cores']} & {alg_short[r['algorithm']]} & {r['same_plan_no_l2_makespan']} & {r['same_plan_l2_makespan']} & {r['no_l2_added_copy_bytes']} & {r['l2_added_copy_bytes']} & {float(r['same_plan_cache_speedup']):.5f} & {float(r['cache_hit_rate']):.5f}" + r" \\")
    lines += [r"\end{longtable}\endgroup"]
    (out / "cache_cases.tex").write_text("\n".join(lines)+"\n")
    blocks = []
    for name in ("smoke_v1", "sensitivity_block50", "sensitivity_block200"):
        blocks += [r for r in read(args.runs / name / "metrics.csv") if r["algorithm"] == "component_packed"]
    blockref = {(r["case"],r["problem"]):int(r["makespan"]) for r in blocks if r["block_size"] == "100"}
    sensitivity = []
    for q in (1,2,3):
        for b in (50,100,200):
            group = [int(r["makespan"])/blockref[r["case"],r["problem"]] for r in blocks if int(r["problem"]) == q and int(r["block_size"]) == b]
            sensitivity.append({"problem":q, "block":b, "cases":len(group),
                                "mean_ratio":statistics.mean(group), "min_ratio":min(group), "max_ratio":max(group)})
    write_csv(args.analysis / "block_sensitivity_summary.csv", sensitivity)
    (out / "sensitivity.tex").write_text("\n".join(f"{r['problem']} & {r['block']} & {r['mean_ratio']:.4f} & {r['min_ratio']:.4f} & {r['max_ratio']:.4f}" + r" \\" for r in sensitivity)+"\n")
    counts = Counter((int(r["problem"]), r["algorithm"]) for r in selected if int(r["cores"]) > 1)
    diagnostics = {"fixed_evaluations":len(all_rows), "selected_plans":len(selected), "cache_pairs":len(pairs),
        "fallback_selected":sum(r["algorithm"] == "singlecore" and int(r["cores"])>1 for r in selected),
        "slower_than_singlecore":sum(float(r["speedup_singlecore"])<1 for r in selected),
        "cache_slowdown_pairs":sum(float(r["same_plan_cache_speedup"])<1 for r in pairs),
        "counts":{f"Q{q}_{a}":n for (q,a),n in counts.items()}, "macros":macros}
    save_json(args.analysis / "paper_diagnostics.json", diagnostics)
    save_json(out / "source_manifest.json", {str(p.relative_to(ROOT)):sha(p) for p in
        [args.analysis.resolve()/"summary.csv", args.analysis.resolve()/"selected_metrics.csv", args.analysis.resolve()/"cache_pairs.csv"]})
    print(json.dumps(diagnostics, ensure_ascii=False))


if __name__ == "__main__":
    main()
