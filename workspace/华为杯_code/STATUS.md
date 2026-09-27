# 当前状态

更新时间：2026-09-24

状态：`COMPUTED`

本工作区由 `idea/A题_Final_idea_给codex运行.md` 驱动，代码和结果均为独立新建；旧 V0.7.1 求解器和旧结果没有作为当前求解器输入。

已完成：

- 新代码单元测试：`3 passed`。
- 代表性运行：`results/fresh_20260924_representative_v3/`。
- 覆盖图：`case_001`、`case_002`、`case_016`、`case_025`、`case_076`。
- 覆盖核数：1、2、3；场景：A、B、C。
- 官方结果行：45；`AI_VERIFIED`：41；`PROFILE_FAILED`：2；`EVALUATION_FAILED`：2。
- 41 个成功结果的独立 `result_check.json` 全部通过。
- 候选轻量排序实际使用 Apple MPS；官方 Python 事件模拟保持 CPU 权威路径。
- 运行 manifest 已保存 Idea SHA-256、官方评估器文件 SHA-256、平台、Python 和 GPU 后端信息。
- 新入口回归：`results/fresh_20260924_case001_v5/` 的 12 个组合全部 `AI_VERIFIED`，12 个结果检查全部通过；C 的首个计划来自同核数 B 的官方选优。
- 失败候选继续尝试回归：`results/fresh_20260924_case002_v5/` 共 18 次尝试，14 个官方成功、3 个官方评估失败、1 个 profile 失败；9 个组合均有最终选优记录。

证据边界：这是基于有限候选的启发式实验，不是全局最优证明，也不是 NPU 实机测量。失败候选仍保留在对应的 `profile_failure.json`、`evaluation_failure.json` 和 `metrics.csv` 中。

全量 100 图矩阵、更多候选、消融、敏感性分析和论文数字尚未完成，不能从当前代表性运行外推。

## 2026-09-27 全量实验交付

- 主矩阵 100×5×3=1500/1500；主矩阵 full-call 失败数 0。
- 消融、敏感性、候选排序、主审计和图表已完成。
- Cache rescue：148 个 job 完成；候选级失败审计为浅搜 11 条、深搜 13 条，均为 case_062 event_timing 依赖环，已保留并排除。
- 交付包：`2026参赛工作区/2026华为杯idea冻结工作区/实验数据/华为杯附件_实验交付_20260927_complete_compact.zip`（提交版）与 `...complete_full.zip`（归档版）。
- 主矩阵仍按 makespan-first；MPS 仅用于轻量排序，官方事件评估在 CPU。
