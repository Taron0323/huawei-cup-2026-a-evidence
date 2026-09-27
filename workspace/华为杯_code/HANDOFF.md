# 交接记录

## 当前入口

- 工作区：`/Users/futaoran/Desktop/华为杯2026/华为杯_code`
- 运行脚本：`scripts/run_experiment.py`
- 代表性结果：`results/fresh_20260924_representative_v3/`
- 指标表：`results/fresh_20260924_representative_v3/metrics.csv`
- 运行清单：`results/fresh_20260924_representative_v3/run_manifest.json`

## 已验证事实

1. `PYTHONPATH=src .venv/bin/python -m pytest -q tests` 返回 `3 passed`。
2. 代表性运行状态为 `COMPUTED`，共 45 个组合。
3. 41 个官方成功结果均通过新代码的结果检查；4 个候选因官方依赖环被拒绝，失败原因已保存。
4. 45 行的 `gpu_backend` 都是 `mps`；官方评估仍在 CPU 上运行。
5. C 场景从同一核数下已官方评估的 B 方案继续，结果与计划哈希已记录在指标表和候选目录。
6. `fresh_20260924_case001_v5` 回归了新的多候选入口：失败候选继续尝试，C 的 B 方案依赖和最终选优均已验证。
7. `fresh_20260924_case002_v5` 覆盖了依赖环失败路径；失败候选之后仍能选出官方成功方案，且 C 继续使用 B 的最终方案。

## 继续运行示例

```bash
cd /Users/futaoran/Desktop/华为杯2026/华为杯_code
PYTHONPATH=src OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python scripts/run_experiment.py \
  --output-root results/fresh_<new-run-id> \
  --cases 001,002,016,025,076 \
  --cores 1,2,3 \
  --scenes A,B,C \
  --full-candidates 2 \
  --workers 1
```

每次必须使用新的 `--output-root`。正式扩大到 100 图前，应先估计官方事件模拟时间，并继续保留失败候选与运行清单。

## 2026-09-27 全量实验交付

- 主矩阵 100×5×3=1500/1500；主矩阵 full-call 失败数 0。
- 消融、敏感性、候选排序、主审计和图表已完成。
- Cache rescue：148 个 job 完成；候选级失败审计为浅搜 11 条、深搜 13 条，均为 case_062 event_timing 依赖环，已保留并排除。
- 交付包：`2026参赛工作区/2026华为杯idea冻结工作区/实验数据/华为杯附件_实验交付_20260927_complete_compact.zip`（提交版）与 `...complete_full.zip`（归档版）。
- 主矩阵仍按 makespan-first；MPS 仅用于轻量排序，官方事件评估在 CPU。
