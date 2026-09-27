# 接续说明

## 2026-09-27 v7 fast 最终交付

实验已完成并停止所有相关进程。主矩阵为 `实验数据/v7_fast_equiv_20260927_0030/`（1500/1500），报告为 `实验数据/v7_fast_reports_complete_20260927/`，结构审计为 `实验数据/v7_fast_main_audit_20260927/`；消融、敏感性和候选排序报告分别位于同名 `v7_fast_*_report_complete_20260927/` 目录。Cache clean2 rescue 结果与 zero-hit 审计位于 `v7_cache_zero_rescue_clean2_20260927_1120/` 和 `v7_cache_zero_audit_clean2_20260927_1120/`。

提交附件优先使用：

`实验数据/华为杯附件_实验交付_20260927_complete_compact.zip`

本地完整归档使用：

`实验数据/华为杯附件_实验交付_20260927_complete_full.zip`

验证：`solver_review_v7_20260926` 的 pytest 为 28/28 通过；两个 ZIP 的 `zipfile.testzip()` 均返回无错误。继续工作时先读取 `实验数据/华为杯附件_实验交付_20260927_complete_compact/FINAL_EVIDENCE_README_20260927_1130.md` 和 `FINAL_EVIDENCE_MANIFEST_20260927_1130.json`，不要重跑或覆盖已冻结的主矩阵。

## 2026-09-26 v6 运行接续

先检查 `实验数据/v6_main_2call_20260926_2230/run_manifest.json`、`实验数据/v6_controls_20260926_2305/run_manifest.json`、`实验数据/v6_sensitivity_20260926_2308/run_manifest.json` 和真实 Python 进程；主矩阵与参数实验仍在运行，不能仅依赖父清单中的 `RUNNING`。单核基准已在 `实验数据/v6_singlecore_baseline_fast_20260926/` 完成 100/100 图，与原版入口逐例十字段等价。新求解器在 `../../华为杯_code/solver_mechanism_v6_20260926/`；报表脚本拒绝不完整的 1500 组合、100 基准和 500 个 B/C 配对，测试为 `21/21`。

23:33 起，后 4 个批次由求解器的 `scripts/accelerate_pending_batches.py` 提前启动，总计 16 个主矩阵子进程；过程清单为 `实验数据/v6_main_2call_20260926_2230/manual_acceleration_manifest.json`。原父进程可能把已存在的后四批目录记成失败并暂时汇总为 `PARTIAL`，加速脚本会等待全部 16 个子清单完成和父进程退出后，保存父清单并重建真实总清单。不要在加速脚本结束前把父清单的 `PARTIAL` 视为子任务失败。

三种真实机制对照已完成 48/48 组；95 次候选评估成功、1 次官方依赖环失败，但该组第二个候选成功。原始清单的 `PARTIAL` 是失败备选状态，组覆盖仍完整。待主矩阵与参数实验结束，核对每个选中计划的 `result.json` 与来源哈希；运行 `scripts/build_reports.py`、`scripts/build_controls_report.py` 和 `scripts/build_sensitivity_report.py`，再与当前论文数字逐项核对。`实验数据/v6_singlecore_baseline_20260926/` 和 `实验数据/v6_singlecore_baseline_parallel_20260926/` 均为主动中断的计时记录。v6 试跑不可作为全量结论。

当前工作区：`2026华为杯idea冻结工作区/`

当前阶段：`RESULTS_AUDITED_PAPER_ALIGNMENT_PENDING`

## 本轮已冻结输入

1. Idea：`incoming/A题_Final_Idea_canonical_20260924.md`，SHA-256 为 `c8878e1ba872f9083b68738bcd178c7df23050ee330341ef4d86535a8edeee35`。
2. 写作提示词：`incoming/提示词_严格按复刻模板写新赛题初稿.txt`，SHA-256 已登记在输入清单。
3. 正式题面与附件：活动项目中登记的 2026 A 题原始目录，只读使用。

## 已完成的接续步骤

1. 已将原件放入 `incoming/`，保持原字节并登记 SHA-256。
2. 已核对版本、题面、结果边界和提示词之间的关系。
3. 已生成唯一 canonical Idea 记录，并写明与 V0.7.1 试验稿的隔离关系。
4. 已在 `paper/latex_draft_from_replica/` 初始化方法初稿源，未写入实验结果。
5. 已把本轮原始结果和核验材料独立归档到 `paper/结果核验与论文填充包_20260924/`，并在同一 `paper/` 下生成 ZIP。

结果字段审计与图表重建已完成。下一步使用 `paper/结果核验与论文填充包_20260924/提示词/论文结果填充与方法对齐.txt` 修订 `paper/latex_draft_from_replica/`：先让方法段符合实际代码，再填可追溯数字，编译并逐项复核。机制移除对照等缺失证据保持未验证；队伍人工复核和正式提交另行记录。


## 当前实验状态（2026-09-24，final idea 已执行）

阶段：`EXPERIMENTS_COMPUTED`

- final idea 已按 SHA-256 固定并执行，代码与结果位于独立 `华为杯_code` 工作区，交付数据位于 `实验数据/`。
- 已保存 1500 个组合，其中正式矩阵 1400 组，另有 A 单核辅助诊断 100 组；核验包数值一致性问题 0 项。
- 官方单核基线：100/100 图完成。
- 首个成功候选与最终选中候选比较：1500 组合，并非机制移除消融。
- Cache 配对分解：500/500 个 B/C 配对。
- Cache 敏感性：6 图 × 4 变体，固定计划 24/24 成功；重优化 24 组均有成功候选，12 个失败备选因官方依赖环保留。
- Apple MPS 的辅助排序未参与最终候选选择；官方事件模拟在 CPU 上执行。
- 15 项官方完整结果抽样复算全部匹配；6 个原始批次清单保留历史 `RUNNING` 状态。
- 结果属于官方评估器验证的有限候选启发式实验，不构成全局最优证明或 NPU 实机测量。

论文数值入口：`paper/结果核验与论文填充包_20260924/核验结论与论文使用边界.md`、`data/`、`tables/`、`audit/`。旧报告仅供对比。


## 2026-09-27 v7 fast 交付接续

主矩阵与配套实验已经收口。优先读取：

1. `实验数据/v7_fast_equiv_20260927_0030/run_manifest.json`
2. `实验数据/v7_fast_reports_complete_20260927/report_manifest.json`
3. `实验数据/v7_fast_main_audit_20260927/audit_manifest.json`
4. `实验数据/v7_fast_controls_report_complete_20260927/report_manifest.json`
5. `实验数据/v7_fast_sensitivity_report_complete_20260927/report_manifest.json`
6. `实验数据/华为杯附件_实验交付_20260927_compact.zip`

主矩阵为 1500/1500，官方评估失败为 0。主报表和审计在生成时保留了源文件 SHA-256 漂移提示；审计中记录的 B/C 初始配对差异为 `case_054/5core`、`case_062/4core`、`case_085/5core`。任何论文表格只能引用报表中的真实字段，并保留有限候选、CPU 官方评估和 MPS 辅助排序的口径。
