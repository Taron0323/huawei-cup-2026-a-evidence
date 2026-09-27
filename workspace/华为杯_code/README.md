# 华为杯_code

这是根据 `idea/A题_Final_idea_给codex运行.md` 从零建立的 A 题实验工作区。这里的算法代码、运行数据和结果不复用旧 `2026参赛工作区` 的求解器或结果；官方 A 题附件只作为 `data/raw/A题/data` 和 `vendor/official_evaluator` 下的只读输入。

## 结构

- `src/huawei_code/graph.py`：图索引、驻留域相关张量关系、H/R/D 拓扑序。
- `src/huawei_code/plan.py`：方案生成、规范化和提交协议检查；规范化保留每个核心列表的相对顺序。
- `src/huawei_code/scoring.py`：A/B/C 轻量评分、结构搬运、容量压力和 Cache 查询代理。
- `src/huawei_code/candidates.py`：四类起点、普通迁移、容量合并、C 聚合/分散/时序候选。
- `src/huawei_code/official.py`：官方 Step1-3/事件模拟桥接；官方结果是最终 Makespan 和搬运权威。
- `src/huawei_code/gpu_score.py`：候选轻量负载批量排序；本机检测到 Apple MPS 时实际使用 GPU。
- `scripts/run_experiment.py`：新运行入口，每次要求新的结果目录，保存 Idea/官方代码哈希、候选账本、profile、结果和检查记录。
- `tests/test_fresh_core.py`：新代码的静态图、计划顺序和 GPU/CPU 后端测试。
- `results/`：本工作区的新运行数据。

## 运行

```bash
.venv/bin/python -m pytest -q tests
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py \
  --output-root results/fresh_<run-id> \
  --cases 001,002,016,025,076 \
  --cores 1,2,3 \
  --scenes A,B,C \
  --full-candidates 2 \
  --workers 1
```

`--full-candidates` 控制每个场景进入官方完整模拟的候选数。候选轻量排序会记录 `gpu_backend`；官方评估器是 Python 事件模拟，因此仍在 CPU 上执行。结果不能称为全局最优，除非另有数学证明或完整求解器证据。

每个组合按轻量排序顺序尝试候选；profile 或官方评估失败会记录并继续尝试，成功结果按官方 Makespan、额外搬运和候选名选择。C 先使用同一图、同一核数下 B 的官方选优计划；若 B 没有成功结果，C 会记录 `SKIPPED_NO_B_RESULT`。每次输出目录必须是新的路径。

本工作区的当前代码版本是 `fresh_final_idea_v0.1`。全量 100 图矩阵、消融、敏感性和论文结果要以新的运行 manifest 为准，不能把旧目录里的数值混入本工作区。
