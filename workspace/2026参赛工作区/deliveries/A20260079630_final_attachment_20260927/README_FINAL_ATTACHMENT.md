# A20260079630 最终附件说明

本包按 A 题“可复现的 Python 程序脚本”要求整理，并按用户指定将压缩包控制在 20 MB 以内。包内包含官方 A 题输入图与配置、官方评估器、参赛方 v7 raw `final_selection` 求解器源代码以及最终结果汇总。没有放入 LaTeX/PDF、历史 inherited 结果、运行日志、候选台账、`__pycache__` 或身份信息。

## 文件结构

- `code/`：题面随附的官方命令行评估程序和示例入口。
- `data/raw/A题/data/`：官方 100 张输入计算图与 `config.txt`。
- `src/huawei_code/`：参赛方 v7 raw 求解器模块。
- `scripts/run_experiment.py`：单批次候选生成、官方 profile 和正式评价入口。
- `scripts/run_full_matrix.py`：100 图、1--5 核、A/B/C 矩阵入口。
- `vendor/official_evaluator/`：求解器调用的官方评估器副本。
- `results/final_v7_raw/`：论文使用的最终汇总 CSV、manifest 和敏感性结果。
- `idea/`：运行清单所需的算法说明，不包含个人信息。

## 官方评估器示例

```bash
python code/stub_multicore_cut_and_schedule.py data/raw/A题/data/case_001.json -n 4
python code/multicore_cut_evaluate_problem_1.py data/raw/A题/data/case_001.json data/raw/A题/data/case_001_multicore_res.json --config data/raw/A题/data/config.txt
```

## 参赛方求解器示例

```bash
PYTHONPATH=src python scripts/run_experiment.py --output-root /tmp/a_case001 --cases case_001 --cores 1,2 --scenes A,B,C --full-candidates 2 --workers 1
```

全量矩阵入口为 `scripts/run_full_matrix.py`。完整运行会产生较大的中间候选与事件报告；论文交付使用的压缩结果保存在 `results/final_v7_raw/`。

## 结果口径

主矩阵为 100 张图 × 1--5 核 × A/B/C，共 1500 条唯一组合；五核平均速度比为 A=`3.4383`、B=`3.4738`、C=`3.5533`。结果来自官方 CPU 事件评估器与有限候选选择，不表述为全局最优或 NPU 实机测量。

人工智能工具使用与后处理见 `AI_USAGE_DISCLOSURE.md`。
