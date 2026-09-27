# 华为杯 A 题实验交付附件（2026-09-27，完成版）

本目录是可直接交付的实验附件包。`complete_compact.zip` 适合报名系统上传；`complete_full.zip` 保留更多汇总文件，适合本地归档。

## 已完成内容

- 全量 100 图 × 5 核数 × A/B/C 主矩阵：1500/1500 个组合，官方 fast evaluator 失败数为 0。
- 消融实验：48 个已选实验组、96 条候选记录，官方失败数为 0。
- Cache 敏感性实验：24 个固定计划组、24 个重优化组，官方失败数为 0。
- 候选排序：36 个单元格、30 条有效官方评估记录；其余单元格明确标注无可继续测量候选。
- 主报表、论文结果填充数据、图表（PNG/SVG/PDF）、运行清单和提示词均已附带。
- Cache zero-hit rescue（validated clean2）：148 个定向 job 均完成；候选级别有 11 个失败候选（依赖环变体，已保留并排除），发现 64 组有命中候选，按严格 makespan-first 规则有 8 组更快备选。该 rescue 不覆盖主矩阵。旧版 rescue 汇总保留在同级目录作为过程复核证据；另附 32-candidate 深搜（590 条候选、13 个候选级别失败，均为依赖环变体）；新增命中候选多数带来明显 makespan 代价，因此不改变标准选择。
- Cache 容差敏感性：在已有官方记录上评估 ε=0.1%、0.25%、0.5%、1%、2% 的命中优先选择，作为独立策略分析，不修改标准主结果。

## 结果口径

主矩阵是有限候选启发式搜索结果，不构成全局最优证明，也不构成全国排名结论。官方事件评估在 CPU 上执行；Apple MPS 仅用于候选负载排序和轻量评分，不能写成 M4 GPU 直接运行官方事件模拟或 NPU 实机测量。

主矩阵标准路径与尾批 fast-profile rescue 存在来源差异，报告已保留 provenance warning；原始主矩阵标准源码的 `source.sha256/FREEZE/LOCK` 已放在 `provenance/frozen_solver_v3_20260926/`。另有 3 个 B/C 初始计划配对差异（case_054/5core、case_062/4core、case_085/5core），审计文件中已明确记录。

主矩阵 C 场景 500 组中，最终选择有 174 组 `cache_hit_bytes=0`。zero-hit 审计、rescue 汇总和容差敏感性文件均在 `reports/` 与 `experiments/` 中。逐候选 rescue 的大体量原始目录仍保留在本机实验数据目录，没有塞入比赛附件，以控制体积。

## 关键入口

- `main/metrics.csv`：1500 个最终组合汇总。
- `reports/v7_fast_reports_complete_20260927/paper_results.md`：可填入论文的结果段落。
- `reports/v7_fast_controls_report_complete_20260927/`：消融报表和图表。
- `reports/v7_fast_sensitivity_report_complete_20260927/`：敏感性报表和图表。
- `reports/v7_fast_main_audit_20260927/`：主矩阵审计。
- `reports/cache_zero_audit_clean2_20260927_1120/`：validated clean2 的 500 组 C 场景 zero-hit 审计；旧版审计也保留。
- `reports/cache_zero_tolerant_audit_20260927/`：命中优先策略的 makespan 容差敏感性。
- `prompts/论文结果填充与方法对齐.txt`：论文填充提示词。

完整原始候选结果仍在：
`/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/`

候选级失败审计见 `reports/cache_zero_rescue_failure_audit_20260927/`；浅搜 11 条、深搜 13 条，均为 case_062 event_timing 依赖环，已排除且主矩阵未改。
