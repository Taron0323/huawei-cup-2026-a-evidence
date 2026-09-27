# 当前论文交付包（v7 raw + 图2替换）

本包以同学修改后的 LaTeX 工程为母版，正式实验结果采用 v7 raw `final_selection`，图 2 已替换为 `figures/roadmap.pdf`（用户提供的组织结构图-可编辑重建-v9.pdf）。

- 正式 PDF：`output/main-2026.pdf`
- 主矩阵：`data/v7_fast_20260927/main_results.csv`
- 五核平均速度比：A=`3.4383`，B=`3.4738`，C=`3.5533`
- 图 2 源文件：`figures/roadmap.pdf`
- 图 2 LaTeX 引用：`sections/04-preparation.tex` 中的 `fig:roadmap`
- 编译命令：`../../../.venv/bin/python build.py --only main-2026`

历史 inherited 结果和旧实验目录未放入本交付包。
