# C 场景零命中定向重选审计

本目录只读聚合 `v7_fast_reports_complete_20260927/cache_zero_hit_diagnostics.csv` 与 `v7_cache_zero_rescue_20260927_1100` 的已有官方评估记录，未修改主矩阵。每组仅在给定 makespan 相对预算内选择已有命中候选，策略为最大化 cache_hit_bytes，再最小化 makespan。结果属于策略分析，不能替代标准主矩阵目标函数。

- `cache_tolerant_selection.csv`: 174 个原零命中组合 × 5 个 makespan 预算。
- `cache_tolerant_summary.csv`: 各预算的可切换数量与代价。
- 默认建议审查 `epsilon=0.01` 行；执行正式聚合前需重新确认论文目标函数。
