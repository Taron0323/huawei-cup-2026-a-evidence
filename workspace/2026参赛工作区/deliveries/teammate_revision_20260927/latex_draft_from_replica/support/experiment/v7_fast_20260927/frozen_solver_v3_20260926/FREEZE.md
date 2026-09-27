# Final Solver Freeze v3

冻结时间：2026-09-26。

本目录是修复 Cache 候选覆盖和 C 场景最后评估名额后的正式运行副本。它包含原始 A 题数据、Final Idea、官方评估器、求解器源码和定向测试；旧结果不复制到这里。

冻结前验证：

- `PYTHONPATH=src .venv/bin/python -m pytest -q tests`：`12 passed`。
- `PYTHONPATH=src .venv/bin/python -m compileall -q src scripts`：通过。
- `case_001/2core` 的忙核末端候选在轻量 FIFO 代理中出现正命中；官方结果仍以 Problem-3 事件模拟为准。
- 官方评估器未修改；Makespan 是官方 CPU Python 事件模拟结果。
- Apple MPS 仅用于候选负载排序，不是工期测量，也不是 NPU 实机测量。

正式运行期间只写入 `results/`，不得修改本目录的源文件、输入、官方评估器或测试。
