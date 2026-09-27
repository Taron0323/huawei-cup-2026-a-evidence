# A题最终实验数据

本目录是本轮 final idea 的独立实验交付目录。代码仍位于 `/Users/futaoran/Desktop/华为杯2026/华为杯_code`，原始官方输入和评估器保持只读。

## 2026-09-26 v6 重算

- `v6_main_2call_20260926_2230/`：100 图 A/B/C 主矩阵运行中，最终 1500 个组合须以完整清单和逐例原始文件核验。
- `v6_singlecore_baseline_fast_20260926/`：100/100 图单核基准已完成；`original_fast_equivalence_audit.json` 记录与原版入口十字段逐例 0 不一致。
- `v6_controls_20260926_2305/`：三种机制消融 48/48 组均有最终选择；一条失败备选保留在原始结果中。
- `v6_sensitivity_20260926_2308/`：按五核 B 计划就绪逐图运行的 Cache 容量/带宽固定与重优化实验。

上述 v6 结果未完成最终汇总前，不以旧 v2 数据填补缺失组合。

## 已完成数据

- `main_reports_20260924_v2/`：100 图 × 5 核 × A/B/C 的 1500 个官方验证组合；包含主表、初始/最终消融表、Cache 分解表、速度图和论文 Markdown 摘要。
- `full_singlecore_baseline_20260924`：100 图官方单核基线原始结果（符号链接）。
- `sensitivity_20260924_v2/`：6 图、4 个 Cache 变体、固定计划/重优化原始结果。
- `sensitivity_20260924_v2/report/`：敏感性汇总 CSV、失败候选清单、Markdown 和 PNG/SVG 图。
- `full_main_fast_20260924`、`full_main_fast_split_20260924`、`full_main_20260924`：主矩阵原始运行目录（符号链接），保留成功、失败和中断证据。
- `EXPERIMENT_MANIFEST_20260924.json`：输入哈希、运行根目录、计数和证据边界。

## 结果边界

主矩阵和敏感性数值来自官方 Python 评估器；Apple MPS 只用于轻量候选负载排序。结果是有限候选启发式实验，不能写成全局最优证明或 NPU 实机测量。敏感性中 12 个重优化备选因官方依赖环失败，已保留在 `sensitivity_failures.csv`；每个变体均有至少一个成功候选。
