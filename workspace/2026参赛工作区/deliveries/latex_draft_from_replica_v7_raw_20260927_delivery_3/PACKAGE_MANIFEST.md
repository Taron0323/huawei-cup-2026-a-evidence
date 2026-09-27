# 当前论文交付包（v7 raw final_selection）

本包以同学修改后的 LaTeX 工程为母版，仅将正式实验数据、图表、生成表和摘要中的结果替换为 v7 raw `final_selection` 口径。

- 正式 PDF：`output/main-2026.pdf`
- 主矩阵：`data/v7_fast_20260927/main_results.csv`
- 主矩阵：100 张图 × 1--5 核 × A/B/C，共 1500 条唯一组合，全部 `AI_VERIFIED`
- 五核平均速度比：A=`3.4383`，B=`3.4738`，C=`3.5533`
- Cache 五核三段效应：`1.0146 / 1.0139 / 1.0289`
- 编译命令：`../../../.venv/bin/python build.py --only main-2026`（从本工程目录运行）

历史 inherited 结果和旧实验目录未放入本交付包，以免与当前正式口径混用。
