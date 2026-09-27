# 华为杯 A 题最终实验证据索引（2026-09-27）

工作区：`/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据`

## 已计算实验

| 模块 | 状态 | 规模 | 入口 |
|---|---|---:|---|
| 主矩阵 | COMPUTED | 1500 行（100×5×3） | `/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/v7_fast_reports_complete_20260927` |
| 单核基线 | COMPUTED | 100 case | `/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/v7_fast_baseline_equiv_20260927_0030` |
| 消融 | COMPUTED | 96 行 | `/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/v7_fast_controls_report_complete_20260927` |
| 敏感性 | COMPUTED | fixed 24 / reoptimized 37 | `/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/v7_fast_sensitivity_report_complete_20260927` |
| 候选排序 | COMPUTED | 36 cells | `/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/v7_fast_candidate_ranking_complete_20260927_0228` |
| Cache rescue | COMPUTED | 148 jobs，候选级别 11/13 个失败候选已保留并排除，8 个独立备选 | `/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/v7_cache_zero_rescue_clean2_20260927_1120` |

## 审计结果

- evaluator 等价性：`MATCH`，120 组抽样，mismatches=0。
- 主矩阵结构审计：1500 selections，failed full calls=0，B/C 同计划配对=500。
- Cache 零命中：500 个 C rows；最终 selection 命中 326，最终零命中 174；rescue 发现 64 个命中备选。

## 论文使用边界

- 主矩阵是有限候选启发式搜索结果，selection 采用 makespan-first；数据支持候选集内的比较，不支持全局最优证明。
- fast evaluator 经 120 组原始/加速对拍，关键汇总字段 MATCH；主矩阵尾批使用 fast evaluator。
- Apple GPU/MPS 用于候选轻量评分和排序；官方离散事件评估器执行在 CPU。
- Cache rescue 是独立 cache-aware 备选证据，不替换主矩阵 selection；148 个 job 均完成，但浅搜有 11 个、深搜有 13 个候选级别评估失败，均为依赖环变体并已保留/排除。
- 主矩阵与当前 solver 文件存在 source hash drift，已在 audit/report manifest 中逐项记录。

## 关键文件

详细机器索引：`/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/2026华为杯idea冻结工作区/实验数据/v7_final_evidence_manifest_20260927_1130.json`
代码工作区：`/Users/futaoran/Desktop/华为杯2026/华为杯_code/solver_review_v7_20260926`
