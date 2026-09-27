# 华为杯 A 题实验交付附件（2026-09-27）

## 体积

compact ZIP 约 2.7 MB，按保守的 20 MB 附件目标整理；正式系统若公布不同上限，以当年报名系统页面为准。

## 内容

- `main/metrics.csv`：100 张图 × 5 核数 × A/B/C 的 1500 个最终组合汇总。
- `main/final_plans/` 与 `main/final_selections/`：1500 个最终方案及其选择元数据。
- `reports/`：主结果表、图表、主矩阵结构审计、消融比较和敏感性报告。
- `experiments/`：消融 96 条候选记录/48 个已选组、敏感性 24 个固定计划组与 24 个重优化组、候选排序 36 个单元格、单核等价性审计。
- `code/`：本轮求解器源代码、脚本、fast evaluator 和配置文件。
- `prompts/`：论文结果填充与方法对齐提示词。

## 结果口径

主矩阵在官方 fast evaluator 上完成 1500/1500，`evaluation_failure.json=0`。Apple MPS 仅用于候选负载排序和轻量评分；官方事件评估仍在 CPU 上执行。所有选择属于有限候选启发式搜索，不构成全局最优证明，也不构成 NPU 实机测量。

主矩阵中尾批使用了 `fast_profile=True` 的细粒度补算路径并按 `case/core/scene` 去重合并。当前工作区源文件相对最初主矩阵清单存在 SHA-256 漂移，报表和审计输出保留了该 provenance warning。主矩阵有 3 个 B/C 初始计划配对差异：`case_054/5core`、`case_062/4core`、`case_085/5core`；这些差异均已写入审计文件和报表说明，未被静默修正。

主矩阵的 500 个 C 配对中，最终选择有 174 个 `cache_hit_bytes=0`；其中 26 个存在命中候选但其官方 makespan 更慢。最终选择按官方 makespan 优先，零命中诊断已放在 `reports/v7_fast_reports_complete_20260927/cache_zero_hit_diagnostics.csv`。

## 完整原始数据位置

逐候选 `result.json`、时间线和 trace 仍保留在本机：

`/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/`

其中主矩阵原始目录约 14 GB，消融、敏感性和候选排序原始目录分别约 458 MB、285 MB 和 139 MB。为满足比赛附件体积限制，本 ZIP 只放最终方案、汇总证据和可复现代码；没有删除原始数据。

## 使用

先阅读 `reports/*/report_manifest.json`、`reports/v7_fast_main_audit_20260927/audit_manifest.json` 和本说明，再使用 `main/metrics.csv` 填论文表格。论文中不得写成全局最优、NPU 实测或硬件实测 GPU 加速；GPU 证据仅支持 MPS 候选排序。
