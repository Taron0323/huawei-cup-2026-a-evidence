# A题 V0.7.1 试验稿复现说明

本说明对应 `v071_full_20260924_v2`，与旧路线运行和旧论文分开。程序检查状态、科学验证、人工审核和平台提交状态分别记录；没有执行账号登录或提交。

## 权威结果

运行清单为 `results/v071_full_20260924_v2/run_manifest.json`，结果汇总为 `results/v071_full_20260924_v2_analysis/`。运行覆盖100个计算图、1–5核和三个问题，500/500个case-core单元完成，候选失败0。候选记录13,127行，官方完整评估3,318行，PROFILE_ONLY 9,809行，选中1,425行。

95个case完成官方动态评估；`case_014`、`case_072`、`case_076`、`case_087`、`case_091`的25个case-core单元全部为PROFILE_ONLY，不能填入Makespan或加速比均值。95个完整case的5核逐例平均加速比分别为问题一1.920640、问题二2.466990、问题三2.519783；问题三同方案Cache加速比1.022347，字节加权命中率19.746150%。有限候选的全局最优性为`NOT_PROVEN`。

## 复核与重建

依赖环境由项目 `.venv` 提供。当前结果不应在原运行目录上覆盖；补算或修改协议必须使用新的 run-id。

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/workspace.py check
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/build_paper.py latex
```

结果汇总入口只读运行输出并生成新的分析目录，不能把PROFILE_ONLY行升级为动态结果：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/run_v071.py \
  --output-root results/<new_run_id> --cores 1,2,3,4,5 \
  --problems 1,2,3 --workers 14 --full-candidates 2 \
  --long-graph-full-candidates 0
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/a_summarize_v071.py \
  --run-root results/<new_run_id> \
  --output results/<new_run_id>_analysis --long-tail-seconds 60
```

`<new_run_id>`必须是新的目录名；补算五个大图时应调整参数并重新登记运行号。当前v2运行不覆盖、不补填，分析汇总和论文只能从真实CSV重新生成。

活动论文主源为 `paper/latex/main.tex`，试验稿为 `paper/A题论文V0.1_试验稿_20260924.pdf`。活动图表位于 `figures/v071_full_20260924_v2/`，证据登记位于 `evidence/`。行数、配对和守恒检查见 `review/v071_claim_verification_20260924.json`；post-run provenance 为 `results/v071_full_20260924_v2/run.json`，它不替代原始 `run_manifest.json`。

## 结论边界

Makespan是题目模拟器返回的周期，不是Mac耗时或真实NPU测试。当前结果是有限候选中的最好可行解；五个大图只完成profile，不能从profile推断Makespan、加速比或Cache收益。程序级检查通过不等于科学验证或人工核验完成。容量峰值、科学有效性和人工复核仍为`NOT_ASSESSED`，正式提交仍为`NOT_SUBMITTED`。旧路线主源、旧结果和旧PDF保存在 `archive/old_baseline_20260923/`，仅用于历史追溯。
