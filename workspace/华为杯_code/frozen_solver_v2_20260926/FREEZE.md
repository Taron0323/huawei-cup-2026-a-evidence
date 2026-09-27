# Final Solver Freeze v2

冻结时间：2026-09-26（当前工作区时间）。

本目录保存启动正式主矩阵前使用的求解源文件、题目配置、Final Idea 和定向测试。`source.sha256` 是冻结时的逐文件 SHA-256；正式运行时不得修改这些文件。旧版 `final_freeze_20260926` 保留为历史快照，不与本目录混用。

验证记录：

- `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_cache_proxy.py tests/test_fresh_core.py`：`11 passed`。
- `PYTHONPATH=src .venv/bin/python -m compileall -q src scripts`：`compileall_ok`。
- 官方评估器文件未修改；正式 Makespan 仍由官方 CPU Python 事件模拟器给出。
- Apple MPS 只用于轻量候选负载排序，不作为工期测量或 NPU 实机证据。

正式矩阵的每个子运行 manifest 记录相同的求解源码哈希、配置哈希、Idea 哈希和官方评估器哈希；结果汇总前必须检查这些哈希一致。
