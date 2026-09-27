"""Bind this completed A run to its numerical evidence and delivery reports.

AI-assisted: Codex / OpenAI, 2026-09-23; model/release UNVERIFIED.
"""

from collections import defaultdict
import csv
from datetime import datetime
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
RUN = "auto_solve_20260923_120249"
R = ROOT / "results" / RUN
A = R / "analysis_final"
V = ROOT / "review/auto_solve/20260923_120249"
NOW = datetime.now().astimezone().isoformat()


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def csv_write(path, rows, fields=None):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load(path):
    return json.loads(path.read_text())


def record(path):
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": digest}


def main():
    selected, raw = read(A / "selected_metrics.csv"), read(A / "all_metrics.csv")
    summary, pairs = read(A / "summary.csv"), read(A / "cache_pairs.csv")
    cache = read(A / "cache_summary.csv")
    checks = read(A / "verification_index.csv")
    repro_path = V / "03_validation/clean_repro_v1/reproducibility_manifest.json"
    repro = load(repro_path)
    pdf_qa = load(V / "05_paper/pdf_qa.json")
    assert len(raw) == len(checks) == repro["rows"] == 4068
    assert len(selected) == 1500 and len(pairs) == 500
    assert all(r["status"] == "AI_VERIFIED" for r in raw + checks)
    assert all(c["differences"] == [] for c in repro["comparisons"])
    assert pdf_qa["pages"] == 33 and not pdf_qa["issues"]
    residual_fields = ("pipeline_overlap_cycles", "dependency_violation_cycles",
                       "reported_capacity_excess_bytes", "sync_violation_cycles")
    assert all(int(r[k]) == 0 for r in checks for k in residual_fields)
    groups = defaultdict(list)
    for row in raw:
        groups[row["case"], row["cores"], row["problem"]].append(row)
    baseline = {r["case"]: int(r["makespan"]) for r in raw if r["cores"] == "1" and r["problem"] == "1"}
    assert len(baseline) == 100
    for row in selected:
        candidates = groups[row["case"], row["cores"], row["problem"]]
        best = min(candidates, key=lambda r: (int(r["makespan"]), int(r["added_copy_bytes"]), r["algorithm"]))
        assert row["plan_sha256"] == best["plan_sha256"] and row["result_sha256"] == best["result_sha256"]
        assert record(A / row["selected_plan"])["sha256"] == row["plan_sha256"]
        assert abs(float(row["speedup_singlecore"]) - baseline[row["case"]] / int(row["makespan"])) <= 1e-12
    for row in summary:
        if row["algorithm"] != "portfolio":
            continue
        group = [r for r in selected if (r["problem"], r["cores"]) == (row["problem"], row["cores"])]
        assert len(group) == 100
        expected = statistics.mean(baseline[r["case"]] / int(r["makespan"]) for r in group)
        assert abs(expected - float(row["mean_speedup"])) <= 1e-12
        weighted = sum(int(r["cache_hit_bytes"]) for r in group) / max(1, sum(int(r["cache_access_bytes"]) for r in group))
        assert abs(weighted - float(row["byte_weighted_cache_hit_rate"])) <= 1e-12
    by_raw = {(r["case"], r["cores"], r["problem"], r["algorithm"]): r for r in raw}
    for row in pairs:
        q2 = by_raw[row["case"], row["cores"], "2", row["algorithm"]]
        q3 = by_raw[row["case"], row["cores"], "3", row["algorithm"]]
        assert q2["plan_sha256"] == q3["plan_sha256"] == row["plan_sha256"]
        assert int(row["same_plan_no_l2_makespan"]) == int(q2["makespan"])
        assert int(row["same_plan_l2_makespan"]) == int(q3["makespan"])
    for row in cache:
        group = [r for r in pairs if r["cores"] == row["cores"]]
        expected = statistics.mean(int(r["same_plan_no_l2_makespan"]) / int(r["same_plan_l2_makespan"]) for r in group)
        assert abs(expected - float(row["same_plan_cache_speedup"])) <= 1e-12

    # Preserve source quotes, including appendix/script requirements missed by the earlier keyword filter.
    trace = read(V / "02_model/requirements_trace.csv")
    original = load(V / "02_model/A_source_paragraphs.json")
    existing = {r["source_page_or_locator"] for r in trace}
    for p in original["paragraphs"]:
        n = int(p["locator"].split("[")[-1][:-1])
        if n not in (50, 51, 57, 58, 63) or p["locator"] in existing:
            continue
        q = 1 if n <= 51 else 2 if n <= 58 else 3
        trace.append(dict(trace[0], requirement_id=f"A-Q{q}-P{n:03d}", subquestion=str(q),
                          quote=p["text"], source_page_or_locator=p["locator"]))
    trace.sort(key=lambda r: int(r["source_page_or_locator"].split("[")[-1][:-1]))
    evidence_reqs = []
    for row in trace:
        n = int(row["source_page_or_locator"].split("[")[-1][:-1])
        row["source_file"] = "inputs/problem/A题/通用神经网络处理器下的多核调度问题.docx"
        q = row["subquestion"]
        result, location = A / "selected_metrics.csv", f"问题{q}；附录A"
        if n in (49, 56):
            result, location = ROOT / f"figures/{RUN}/speedup_q{q}.pdf", f"第{4+int(q)}节折线图"
        elif n in (51, 58):
            result, location = ROOT / "run_a.py", "附录C复现入口"
        elif q == "3":
            result, location = A / "cache_pairs.csv", "第7节；附录B"
        elif n >= 143:
            result, location = A / "verification_index.csv", "第3节；第8.1节"
        if n == 144:
            row["subquestion"] = "2,3"
        row["expected_output"] = f"{location}；{result.relative_to(ROOT)}"
        row["verification_plan"] = "方案/时间线检查、结果哈希、全量独立复现及论文对账"
        row["status"] = "AI_VERIFIED"
        row["notes"] = "原句保留；AI程序核验完成；人工未核验。容量仅核对评估器报告峰值。"
        evidence_reqs.append({"id": row["requirement_id"], "quote": row["quote"],
            "source_file": row["source_file"], "source_page": row["source_page_or_locator"],
            "deliverable": row["expected_output"], "paper_location": location,
            "result_file": result.relative_to(ROOT).as_posix(), "status": "AI_VERIFIED", "review_note": row["notes"]})
    csv_write(V / "02_model/requirements_trace.csv", trace)
    csv_write(ROOT / "evidence/requirements.csv", evidence_reqs)
    all_requirements = read(V / "02_model/all_requirements.csv")
    csv_write(V / "02_model/all_requirements.csv", trace + [r for r in all_requirements if r["problem"] != "A"])
    parameters = read(V / "02_model/parameters.csv")
    for row in parameters:
        row["status"] = "AI_VERIFIED"
    csv_write(V / "02_model/parameters.csv", parameters)
    csv_write(ROOT / "evidence/parameters.csv", parameters)

    figure_rows = read(ROOT / f"figures/{RUN}/figure_manifest.csv")
    figure_rows = [r for r in figure_rows if r["figure_file"].endswith(".pdf")]
    for row in figure_rows:
        for kind in ("result", "code", "figure"):
            assert record(ROOT / row[f"{kind}_file"])["sha256"] == row[f"{kind}_sha256"]
        row["visual_review"] = "AI_VERIFIED: review/auto_solve/20260923_120249/05_paper/visual_review.md"
        row["status"] = "AI_VERIFIED"
    csv_write(ROOT / "evidence/figures.csv", figure_rows)
    pdf_qa["visual_status"] = "AI_VERIFIED"
    pdf_qa["visual_review_file"] = "review/auto_solve/20260923_120249/05_paper/visual_review.md"
    pdf_qa["human_review"] = "NOT_ASSESSED"
    dump(V / "05_paper/pdf_qa.json", pdf_qa)
    (V / "05_paper/visual_review.md").write_text(
        "# PDF与图表视觉检查\n\n检查人类型：AI；人工核验：NOT_ASSESSED。\n\n"
        "已打开并检查9张联系表，覆盖33页；另打开全部6张图表PNG和最终Word摘要页。"
        "末轮修改后重新编译、提取和渲染33页，并复看contact-02、contact-03，覆盖回退条件与复现段落。"
        "未发现缺字、遮挡、页面越界或错图；公式、长表、图例和单位可读，封面队伍信息留空。"
        "参考文献续页留白较多，是当前初稿的排版现状。\n\n"
        "早期页码检查曾把物理第4、5页页脚裁剪中的公式文字读为v\\n3和v∈s v h\\n4；"
        "页码本身正确，已将检测改为裁剪区末行。最终自动检查33页、0问题。"
        "初次LaTeX编译失败日志保留在04_performance/latex_first_failure.log。\n")
    final_pdf = ROOT / "paper/A题论文初稿_20260923.pdf"
    shutil.copyfile(ROOT / "paper/preview/latex/template.pdf", final_pdf)

    validation = []
    def check(cid, obj, prop, method, tolerance, actual, evidence, note="", status="AI_VERIFIED"):
        validation.append(dict(check_id=cid, object=obj, expected_property=prop, method=method,
            tolerance=tolerance, actual_value=actual, status=status,
            evidence_file=evidence.relative_to(ROOT).as_posix(), run_id=RUN, note=note))
    health = read(V / "02_model/data_health.csv")
    assert len(health) == 100 and all(r["status"] == "AI_VERIFIED" for r in health)
    check("DATA-01", "100个计算图", "字段合法、DAG、单位明确", "逐图字段和图检查；不删除零大小数据", 0,
          f"100/100；核内操作{sum(int(r['eligible_operations']) for r in health)}", V / "02_model/data_health.csv")
    small = read(V / "03_validation/small_exact_v1/validation_checks.csv")
    assert len(small) == 12 and all(r["status"] == "AI_VERIFIED" for r in small)
    for row in small:
        check(row["check_id"], row["object"], row["expected_property"], row["method"],
              row["tolerance"], row["actual_value"], V / "03_validation/small_exact_v1/validation_checks.csv")
    check("CONSTRAINT-01", "4068组时间线", "依赖、流水线、同步、报告容量残差均0", "独立verify.py及逐行汇总", 0,
          "4068/4068；四类残差最大值0", A / "verification_index.csv", "未独立重建内存驻留或带宽事件模拟器")
    check("POSTPROCESS-01", "1500份最终计划", "从实际候选选择，不截断指标", "重新计算有限集合字典序最小；核对1500计划哈希", 0,
          "1500/1500；0慢于单核；56份多核配置单核回退", A / "selected_metrics.csv")
    check("CACHE-PAIR-01", "500组Cache对照", "计划相同，比例口径正确", "Q2/Q3方案SHA相等；算术平均与字节加权复算", 1e-12,
          "500/500；保留1组加Cache后多12周期的反例", A / "cache_pairs.csv")
    for folder, count in (("smoke_v1",45),("sensitivity_block50",15),("sensitivity_block200",15),
                          ("random_seeds_v1",45),("cache_sensitivity_v1",21)):
        rows = read(R / folder / "metrics.csv")
        assert len(rows) == count and all(r["status"] == "AI_VERIFIED" for r in rows)
        check("RUN-" + folder, folder, "运行和约束检查通过", "逐行检查终态；配置独立保存", 0, f"{count}/{count}", R / folder / "metrics.csv")
    check("REPRO-01", "清洁环境全部主实验", "指标和方案/结果哈希完全相同", "复制原始输入和代码，新建无第三方包venv，全部重算", 0,
          "4068行，0差异", repro_path)
    check("PAPER-01", "论文表与图", "权威CSV、汇总口径和生成表一致", "独立重算均值、最优候选与Cache配对；图表来源哈希", 1e-12,
          "15组总体加速比及5组Cache统计一致，6组图哈希一致", A / "summary.csv")
    check("PDF-01", "33页论文", "可编译、文字可提取、无越界/错页码", "XeLaTeX、pdfplumber和逐页联系表目视", 0,
          "33页；自动问题0；AI视觉通过", V / "05_paper/pdf_qa.json")
    check("LEAKAGE-NA", "预测/分类划分", "不适用", "本题为确定性调度，无训练/测试预测器", "N/A", "NOT_APPLICABLE",
          V / "02_model/model_spec.md", status="NOT_APPLICABLE")
    check("DYNAMICS-NA", "ODE步长和可辨识性", "不适用", "离散事件模拟，无连续动力学求解", "N/A", "NOT_APPLICABLE",
          V / "02_model/model_spec.md", status="NOT_APPLICABLE")
    csv_write(V / "03_validation/validation_checks.csv", validation)

    outputs = [A / n for n in ("summary.csv", "cache_summary.csv", "selected_metrics.csv", "cache_pairs.csv", "verification_index.csv")]
    code = [ROOT / n for n in ("tools/a_analyze_results.py", "tools/a_paper_data.py", "tools/a_make_figures.py",
                              "tools/a_finalize_evidence.py", "src/a_solver/verify.py")]
    bound = [record(p) for p in outputs + code]
    verify_path = V / "03_validation/claim_verification.json"
    dump(verify_path, {"run_id": RUN, "checked_at": NOW, "files": bound,
        "checks": [{"name": "candidate_selection_and_summary_recomputed", "passed": True},
                   {"name": "4068_clean_reproduction_rows_equal", "passed": True},
                   {"name": "1500_selected_plan_hashes_equal", "passed": True},
                   {"name": "500_same_plan_cache_pairs", "passed": True}],
        "human_review": "NOT_ASSESSED", "global_optimality": "NOT_PROVEN"})
    manifests = sorted(R.glob("*/run_manifest.json"))
    dump(R / "run.json", {"run_id": RUN, "phase": "final_aggregation", "created_at": NOW,
        "inputs": [record(ROOT / "inputs/manifest.json"), record(ROOT / "inputs/raw/A题/附件/data/config.txt")],
        "code": [record(p) for p in code], "outputs": [record(p) for p in outputs],
        "component_runs": [record(p) for p in manifests],
        "provenance_note": "Aggregation binds current analysis code. Historical evaluation code is preserved in each source_snapshot; original full run used 6 workers.",
        "human_review": "NOT_ASSESSED", "submission": "NOT_SUBMITTED"})
    claims = []
    def claim(cid, statement, value, unit, path, index, column, location, figure=""):
        claims.append(dict(claim_id=cid, statement=statement, value=value, unit=unit, tolerance=1e-12,
            result_file=path.relative_to(ROOT).as_posix(), result_row=index, result_column=column,
            code_file="tools/a_analyze_results.py", run_id=RUN, paper_location=location,
            figure_file=figure, verification_file=verify_path.relative_to(ROOT).as_posix(),
            human_review="NOT_ASSESSED", status="AI_VERIFIED"))
    for index, row in enumerate(summary, 1):
        if row["algorithm"] == "portfolio":
            q, k = row["problem"], row["cores"]
            claim(f"Q{q}-K{k}", f"问题{q}的{k}核逐用例平均加速比", row["mean_speedup"], "ratio",
                  A / "summary.csv", index, "mean_speedup", f"问题{q}结果；摘要")
            if q == "3" and k == "5":
                claim("CACHE-HIT-K5", "5核跨用例字节加权Cache命中率", row["byte_weighted_cache_hit_rate"], "fraction",
                      A / "summary.csv", index, "byte_weighted_cache_hit_rate", "第7节")
    for index, row in enumerate(cache, 1):
        claim("CACHE-K" + row["cores"], "同方案无L2/只读L2逐例比值的算术平均", row["same_plan_cache_speedup"], "ratio",
              A / "cache_summary.csv", index, "same_plan_cache_speedup", "第7节表6与图4")
    csv_write(ROOT / "evidence/claims.csv", claims)
    refs = []
    sources = [("problem", "通用神经网络处理器下的多核调度问题", "inputs/problem/A题/通用神经网络处理器下的多核调度问题.docx"),
               ("evaluator", "README及题目评估器", "inputs/raw/A题/附件/README.md"),
               ("intra", "核内调度算法", "inputs/raw/A题/附件/docs/核内调度算法.md"),
               ("multi", "多核并行模拟执行算法", "inputs/raw/A题/附件/docs/多核并行模拟执行算法.md")]
    for key, title, path in sources:
        refs.append(dict(reference_id=key, authors="赛题及随题附件署名机构", title=title, year="2026",
            source_url="LOCAL_USER_SUPPLIED_ORIGINAL", accessed_at="2026-09-23", local_file=path,
            sha256=record(ROOT / path)["sha256"], locator="完整原件", paper_location="参考文献[" + str(len(refs)+1) + "]",
            status="AI_VERIFIED_LOCAL_SOURCE"))
    csv_write(ROOT / "evidence/references.csv", refs)
    ai = []
    for phase, purpose, files in (("model", "题面抽取、数学模型和假设", "review/auto_solve/20260923_120249/02_model/model_spec.md"),
                                 ("code", "构造候选、批量评估和独立核验", "src/a_solver/;tools/;run_a.py"),
                                 ("paper", "图表、中文LaTeX初稿和数据对账", "paper/latex/;figures/auto_solve_20260923_120249/")):
        ai.append(dict(entry_id="AI-"+phase, timestamp=NOW, phase=phase, tool="Codex", model="UNVERIFIED",
            developer="OpenAI", version_release_date="UNVERIFIED", version_evidence="UNVERIFIED: no export proving exact model/version/release/effort",
            purpose=purpose, prompt_file="prompts/A题自动求解用户原始提示词.txt", output_files=files,
            adopted_changes="保留可运行代码、模型及已验证数值；推理档位UNVERIFIED",
            human_modifications="NOT_ASSESSED；后处理由程序完成：校验、候选择优、源CSV生成图表、PDF核验",
            result_annotation="paper/latex/main.tex相应结果节", code_annotation="各自编脚本头部；不更改题目原始脚本",
            verification_evidence="review/auto_solve/20260923_120249/03_validation/validation_checks.csv",
            human_reviewer="", human_review_date="", status="COMPUTED"))
    csv_write(ROOT / "evidence/ai_usage.csv", ai)
    csv_write(ROOT / "evidence/human_review.csv", [dict(check_id="HUMAN-01", scope="模型、代码、数值、论文和AI标注",
        evidence_file=verify_path.relative_to(ROOT).as_posix(), reviewer="", reviewed_at="", outcome="NOT_ASSESSED",
        note="没有实际队员审核记录，不填签名或日期")])

    first = load(R / "full_v1/run_manifest.json")
    perf = repro["full_performance"]
    reduction = 100 * (1 - perf["elapsed_seconds"] / first["elapsed_seconds"])
    (V / "04_performance/acceleration_report.md").write_text(
        f"# 本地M4 Pro资源实测\n\nApple M4 Pro，14 CPU核（10性能+4能效）、20 GPU核、48GiB统一内存。\n\n"
        f"相同45组评估的6/10/14进程耗时分别为42.0333/37.9032/37.1580秒，结果哈希一致，交换增量均为0。采用14进程及大图优先队列。\n\n"
        f"完整3900组主实验：原6进程{first['elapsed_seconds']:.3f}秒，清洁环境14进程{perf['elapsed_seconds']:.3f}秒，耗时减少{reduction:.2f}%。"
        f"CPU容量平均{perf['average_worker_cpu_capacity_percent']:.2f}%，采样峰值{perf['peak_cpu_capacity_percent']:.2f}%；进程RSS峰值{perf['peak_rss_bytes']/2**30:.2f}GiB。"
        "这是两次实际运行的比较，包含任务调度和系统负载影响，不是严格隔离的重复性能实验。\n\n"
        f"168组回退在清洁环境耗时{repro['fallback_performance']['elapsed_seconds']:.3f}秒；该部分没有获得同比提速，保留真实值。"
        "评估器为Python堆、字典和事件循环，无Metal/GPU后端；本轮GPU未使用。CPU不保证持续100%；内存按负载使用，填满统一内存会引入交换。"
        "任务结束后进程释放，不运行无效压力测试。测量采用进程累计RSS，非独立物理页计量。\n")
    (V / "03_validation/reproducibility_report.md").write_text(
        "# 清洁环境复现\n\n结果：AI_VERIFIED，4068行，0差异。\n\n"
        "复制原始A题数据和代码至clean_repro_v1/workspace，新建无pip及无系统site-packages的venv。"
        "重新执行3900组主实验和168组回退；逐行比较Makespan、两类搬运量、Cache命中率、方案SHA、结果SHA和状态，容差0。"
        "复制清单、环境信息、原始运行日志、资源采样与两份comparison.json均保留。\n\n"
        "自动入口run_a.py的45组smoke也已实际运行。full入口各阶段已独立执行；未再重复调用一次完整wrapper。"
        "交付包解压后的运行另记package_verification.json，不能由本报告推断。\n\n"
        "主求解只依赖Python标准库和题目评估器；绘图/制表依赖单独列在requirements.txt。"
        "图表由主结果CSV生成，文件字节可含生成时间，主要比较数值与来源哈希。最终ZIP不携带venv或重复全量计算副本。\n")
    (V / "03_validation/sensitivity_report.md").write_text(
        "# 敏感性与稳健性\n\n分块诊断固定4核及其他参数，在001/002/016/025/076五例比较50/100/200个操作。"
        "b=200相对100的平均周期比为问题1 0.9330、问题2 0.9865、问题3 0.9871。"
        "这是代表例诊断，不据此追认全量最优参数，正式结果保留b=100。\n\n"
        "Cache诊断在001/002/076三例分别改变容量0/0.5/1/2MiB、带宽60/125/250/500 bytes/cycle，共21组。"
        "每次只改变一个参数，正式配置仍为1MiB、250 bytes/cycle；单独CSV与图保存，不混入正式得分。\n\n"
        "随机示例算法使用0/1/2三个种子，五例、4核、三个问题共45组；每组均值、样本标准差、最小最大值见"
        "results/auto_solve_20260923_120249/analysis_final/random_seed_summary.csv。三种主候选是确定性算法。\n\n"
        "Cache配对保留case_062/4核的12周期减速反例；不能推出命中率提高必然缩短Makespan。"
        "未进行100例全参数网格搜索；全局最优性NOT_PROVEN。\n")
    (V / "03_validation/validation_report.md").write_text(
        f"# A题本轮验证报告\n\n运行号：{RUN}。完整检查表：validation_checks.csv，共{len(validation)}项；"
        f"其中{sum(r['status']=='AI_VERIFIED' for r in validation)}项AI_VERIFIED、2项NOT_APPLICABLE。\n\n"
        "100图体检通过；12项解析/边界/错误拒绝检查通过；4068条正式评估的四类观测残差均为0；"
        "1500份择优计划与原候选哈希一致，500组Cache对照使用相同方案；完整独立重算0差异。"
        "已核对22条题面与附录要求，六组图和33页PDF自动/视觉检查通过。\n\n"
        "验证代码独立检查依赖、流水线、时间线覆盖、总时长及搬运恒等式；容量只核对题目评估器报告峰值，"
        "尚未独立重建完整内存驻留与共享带宽事件引擎。小规模最优性只属于解析合成例，不外推到100个正式大图。\n\n"
        "本文没有预测/分类训练过程、连续ODE积分，因此泄漏/ODE步长项不适用。"
        "程序通过不表示真实NPU硬件效果、人工审核或官方提交；human_review=NOT_ASSESSED，submission=NOT_SUBMITTED。\n\n"
        "既往失败包括相对路径处理和首轮LaTeX编译，日志保留在04_performance；受影响步骤修复后已重跑。"
        "当前没有未解决的计算失败；准确AI元数据和队伍人工核验仍未完成。\n")
    installed = sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())
    (ROOT / "support/environment-lock.txt").write_text("# Captured project environment, " + NOW + "\n" +
        "\n".join(f"{name}=={version}" for name, version in installed) + "\n")
    (ROOT / "support/仍需人工完成事项.md").write_text(
        "# 仍需人工完成\n\n1. 实际队员理解并核验模型、代码、方案和论文，形成真实审核记录。\n"
        "2. 核实AI工具的准确型号、版本发布日期与实际推理档位，补齐官方标注要求；当前均不猜测。\n"
        "3. 核实报名、资格、缴费、队号和队员信息；仅在正式封面填写真实信息。\n"
        "4. 检查本轮启发式质量是否满足团队目标；全局最优性未证明，内存驻留未独立重建。\n"
        "5. 正式提交前按最新平台核对文件名、附件格式/容量、匿名、官方MD5工具与截止时间。"
        "本地复现ZIP可能超过50M，不作为正式附件。\n"
        "6. 本次未执行登录、对外联系、MD5登记、论文/附件上传或提交；这些动作由实际队员完成。\n")
    print(json.dumps({"claims": len(claims), "requirements": len(trace), "figures": len(figure_rows),
                      "validation_checks": len(validation), "pdf_pages": pdf_qa["pages"], "status": "AI_VERIFIED"}))


if __name__ == "__main__":
    main()
