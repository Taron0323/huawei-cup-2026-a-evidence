# A题复现说明

本交付包含100个给定计算图的正式配置结果、三种确定性候选及单核回退、敏感性、随机对照、完整逐例附录和中文论文初稿。程序检查状态与人工审核、平台提交状态分开。没有执行任何账号登录或提交。

## 运行

在复现目录根目录使用Python 3.12或更新的兼容版本。主求解只依赖标准库和保留原字节的题目评估器。图表需要pandas和matplotlib；资源监测需要psutil。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run_a.py --mode smoke --workers 14
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run_a.py --mode full --workers 14
```

每次命令自动产生新运行号，已有目录不会覆盖。smoke模式执行5例、4核、3候选和3问题共45组评估；full模式计算全量3900组、需要的回退、敏感性和随机对照，再从原始结果生成汇总、图和论文数值表。全量预计约20至30分钟，取决于机器、后台任务及随机对照成本；本机独立全量主实验的实测时间见验证报告。

单例输入与计划输出：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/a_solve_case.py --graph 'inputs/raw/A题/附件/data/case_001.json' --cores 4 --problem 2 --output results/example_new
```

该入口评估三种候选和单核占用候选，输出`plan.json`，格式为`node_to_subgraph`和`core_schedules`。它对单例总是包含单核候选；论文批量流程仅对出现多核减速的用例补算，因此候选预算不同。正式论文数值应使用full流程。

## 已有结果

权威运行根目录为`results/auto_solve_20260923_120249/`。`full_v1`含3900组，`fallback_v1`含168组；`analysis_final/selected_metrics.csv`含1500行，`selected_plans/`含1500份计划；`cache_pairs.csv`含500组相同计划的Cache对照。

`smoke_v1`、`sensitivity_block50`、`sensitivity_block200`、`random_seeds_v1`与`cache_sensitivity_v1`保存独立运行。原始日志、方案、完整压缩结果、参数和代码快照一起保留。主图使用固定配置，Cache参数诊断不并入正式成绩。

## 论文重建

`paper/latex/main.tex`是唯一正式正文源。表和数字由`tools/a_paper_data.py`从权威CSV生成；Word封面与摘要来自官方模板的工作副本，队伍信息为空。已导出的`frontmatter.pdf`可直接用于编译，不必安装Word。

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/a_paper_data.py --analysis results/auto_solve_20260923_120249/analysis_final --runs results/auto_solve_20260923_120249
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/build_paper.py latex
```

编译需要XeLaTeX、latexmk、Poppler及合法安装的宋体、黑体。商业字体不随包分发。`tools/a_frontmatter.py`用于再次填充Word摘要，运行它和文档渲染时使用已配置的文档Python环境；中文字体发现配置见`tools/fonts.conf`，其中macOS字体路径仅适用本机。

完整独立环境复现的输入副本、清洁虚拟环境和重复结果留在工作区审查目录；交付包保留复制清单、环境、日志和逐行比较报告，避免再包含相同的重复结果。复制清单与报告不代替重新计算，程序与原始数据均已提供。

## 结论边界

Makespan是题目模拟器返回的周期，不是Mac耗时或真实NPU测试。启发式方案为有限候选中的最好可行解；正式大图全局最优性未证明。容量检查对照评估器报告峰值，尚未独立重建全部内存驻留。精确版本与发布日期、人工审阅、队伍身份和平台要求仍需实际队员核实。复现ZIP不是正式提交附件。
