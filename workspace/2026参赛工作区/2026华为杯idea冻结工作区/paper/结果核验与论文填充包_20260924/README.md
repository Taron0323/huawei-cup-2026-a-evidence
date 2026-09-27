# A题结果核验与论文填充包

本包随当前带占位结果的论文工程放在同一个 `paper/` 目录。`manuscript/latex_draft_from_replica/` 是论文源的交付快照；`code/`、`data/` 和 `evidence/` 保存可独立读取的代码、原始输入、评估器、逐候选官方输出及失败记录。解压后不依赖工作区中的符号链接。

## 从这里开始

1. 阅读 `核验结论与论文使用边界.md`，确认可填的数值和暂不能宣称的机制。
2. 阅读 `tables/论文数值汇总.md` 和 `data/result_sources.csv`；每个数字都可以定位到候选的 `result.json` 和 `plan.json`。
3. 在 `提示词/论文结果填充与方法对齐.txt` 中取得完整的论文填充任务提示词。该提示词要求先修正方法描述，再将核验后的表、图和摘要数字写入占位论文。
4. `audit/` 包含 111 份官方输入身份比对、1500 组合一致性核验、原始运行哈希核对、Idea 差异、论文占位位置和官方抽样重算记录。

## 数值状态

100 图正式组合为 A 的 2–5 核 400 组、B 的 1–5 核 500 组、C 的 1–5 核 500 组，合计 1400 组。另保存 A 的 1 核 100 组辅助诊断，因此原始矩阵为 1500 组。单核基准有 100 组。每个组合的首个成功候选和最终选中候选都有官方结果；这不是三个机制移除实验。

Cache B/C 同计划配对 500 组。敏感性实验为 6 图 × 4 变体：24 个固定 B 方案评估和 24 个重优化组均有成功结果。重优化共评估 48 个候选，其中 12 个因官方展开依赖环失败；24 组最终均保留 B 方案。

`data/main_results.csv`、`data/cache_pairs.csv` 和 `tables/*.tex` 是论文数值入口。原 `evidence/previous_report/` 仅供对比，其候选来源、耗时列有 1047 行缺失，计算下界还使用了不匹配的 Pipe 字段名。不要把它作为新的论文表来源。

## 复核

在包根目录安装 `code/requirements.txt` 后运行 `PYTHONPATH=code/src python tools/audit_results.py`，可重建审计 CSV；运行 `python tools/render_tables.py` 可重建汇总表和 PNG/SVG/PDF 图。`tools/replay_checks.py` 是 15 项官方结果抽样重算，不等同于全量 1500 项重算。逐文件清单与哈希在包内 `audit/package_manifest.json`，ZIP 哈希与全成员验证结论在 ZIP 旁的 `结果核验与论文填充包_20260924.verification.json`。

这份包提供可核实的数值材料和论文填充任务，不表示所有原 Idea 机制已实现，也不表示人工复核或正式提交已完成。
