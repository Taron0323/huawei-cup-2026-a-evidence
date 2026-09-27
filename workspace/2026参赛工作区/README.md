## 2026-09-27：方案 B 新实验切换记录

当前论文唯一主工程为 `deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/`。本轮采用方案 B：正文算法、图表、附录代码和支撑记录均以 `2026华为杯idea冻结工作区/实验数据/v7_fast_reports_complete_20260927/` 的 `main_results.csv`（final_selection）为正式结果源；候选级 `timing.csv` 不作为主矩阵。主矩阵覆盖100图、1--5核、A/B/C共1500条，全部 `AI_VERIFIED`。五核平均速度比为 A=3.4383、B=3.4738、C=3.5533；Cache五核硬件/适配/综合效应为1.0146/1.0139/1.0289。

正文已删除旧的“评价后逐图继承”主算法口径，改为 mandatory anchors、profile、场景化候选和官方事件评价后的逐组合 final_selection；附录源代码同步到 `support/experiment/v7_fast_20260927/`，逐图表改由 `generated/v7_*` 生成。Cache敏感性采用 `v7_fast_sensitivity_report_complete_20260927`：24组固定计划全部成功，37条重优化候选全部成功，四变体各3/6组改变计划。

证据边界：228个尾部组合来自 fast-profile 补齐；solver文件与主矩阵哈希存在漂移；case_054/5核、case_062/4核、case_085/5核有三个B/C初始计划不一致项。上述事实保留在支撑记录中。当前尚未重新编译本轮PDF。

# 华为杯2026参赛工作区

清理记录（2026-09-24）：用户已撤销9月23日33页中文初稿，其源稿、PDF、摘要、预览、归档/正文快照和旧交付ZIP均已删除。当前9月24日稿件与实验资料保留。详见[删除核验](review/cleanup_20260924_old_draft/verification.json)。

当前论文为依据 Final Idea 和冻结 v2 实验结果撰写的 A 题稿，唯一源工程是`deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/`，阅读入口为该目录下的`output/main-2026.pdf`。2026-09-25最终版共74页：封面1页、摘要2页，第4--44物理页连续承载九章正文，AI工具说明与参考文献自然衔接，附件索引和关键代码连续接续，数据附录按“续表”排版。附录选取9份作者源码的22处关键片段；完整源码和10份官方评估器仍在支撑目录。参考文献现为10篇英文会议/期刊论文和2篇英文博士论文，题面及官方附件的来源在正文和附件索引中说明；来源和支撑边界见新工程`文献核验与正文落位_20260924.md`。摘要与正文不插入非必要强制分页，仅附录整体保留起页。

2026-09-25 起，实际主工作区已切换为 `deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/`；`paper/latex_draft_from_replica` 是指向它的兼容软链接。完整切换记录见 [PRIMARY_WORKSPACE](PRIMARY_WORKSPACE.md)。

本文数字以冻结实验数据的100张图、1500个唯一存储组合（含100个A单核辅助诊断）、500组B/C同计划配对和24组Cache固定计划敏感性为准。工期来自CPU运行的官方Python事件模拟和有限候选选择，不代表全局最优或NPU实机测量。V0.7.1的95图、475组和旧速度比仅保留在下方历史阶段记录，不进入当前论文。队员人工科学审阅与正式提交未完成。

当前重建命令：`.venv/bin/python paper/latex_draft_from_replica/build.py --only main-2026`；绘图和完整附表重建见新工程README。9月23日被撤销的33页旧稿没有恢复。

## 从这里开始

1. 阅读 [STATUS](STATUS.md)、[赛前清单](prep/赛前清单.md) 和 [官方规则与时间表](CONTEXT.md)。
2. 核实队伍报名、审核、缴费状态。9月21日17:00缴费截止已过，不能从本地文件推断成功缴费。
3. A题和附件已经接收、登记并完成本轮求解；队伍编号、登录与指定MD5工具由实际队员核实。
4. 比赛开始使用 [正式启动提示词](prompts/01_接收与选题.md)，中断后使用 [恢复提示词](prompts/07_恢复.md)。

完整准备提示词：[00_准备与审查Goal](prompts/00_准备与审查Goal.md)。本轮结论见 [审查与准备报告](review/审查与准备报告_20260921.md)。

## 目录职责

| 目录或文件 | 用途 |
| --- | --- |
| official/20260921 | 当天官方网页、原附件、可检索文本与来源记录 |
| inputs/problem、inputs/raw | 正式题面和原始数据，登记后保留原字节 |
| data/processed | 清洗与派生数据，必须可从原件重建 |
| src、results、figures | 正式代码、带运行号的计算和验证结果、结果图表 |
| paper | LaTeX正文主源、官方Word封面与摘要、模板预览 |
| support | 本轮复现说明、环境锁定及待人工完成事项；正式附件未冻结 |
| reference | 用户参考论文及结构借鉴说明，不进入正式附件 |
| evidence | 正式需求、参数、结论、图表、AI、人工检查证据表 |
| practice | 合成运输问题演练，不能作为本届结果 |
| prep | 队伍信息空表、时间安排、赛前清单 |
| prompts | 当前规则下的实际执行提示词 |
| tools | 环境、登记、证据、冻结、编译和打包工具 |
| review | 审查、环境与验证结果 |
| Each Stage Review Work | 阶段输入快照、渲染证据和变更说明 |
| submission | 将来冻结的确切PDF字节与平台回执，目前无正式提交物 |
| REQ / CONTEXT / IDEA | 准备验收、事实规则、候选路线，职责分开 |
| STATUS / HANDOFF | 真实状态与接续命令 |

## 可运行命令

从本工作区根目录执行。当前机器已准备本地 `.venv`；交付ZIP不携带机器专属虚拟环境。

```bash
.venv/bin/python tools/workspace.py env
.venv/bin/python tools/workspace.py check
.venv/bin/python practice/transport/run.py --run-id local-check
.venv/bin/python tools/build_paper.py latex
```

新电脑先创建环境，再安装依赖：
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

XeLaTeX、latexmk、宋体/黑体、LibreOffice和Poppler属于系统工具，见 [环境说明](prep/环境说明.md)。Python标准库工具不依赖建模库。已存在的run-id不会覆盖，应使用新编号。

收到正式文件后执行 `.venv/bin/python tools/workspace.py register` 登记输入；之后的 `check` 会检查已登记文件是否被改动。冻结步骤见 [提交手册](submission/README.md)。

本地ZIP是准备备份，不是正式附件。当前官方附件格式描述存在待核对项，不能用准备ZIP冒充正式提交。

用户最新指定LaTeX为正文主源。严格格式与AI、支撑材料对应关系见 [2026格式与合规对照](paper/2026格式与合规对照.md)。提交检查命令：`.venv/bin/python tools/check_submission.py`。当前模板应报告未填写项；加`--final`时应失败，防止将准备模板误作成稿。

## 2025 D题复刻模板（2026-09-22）

最新写作准备入口：[2025 D题原稿风格与2026格式LaTeX模板](paper/latex_d2025_style/README.md)。包含44页可编辑原稿风格版、39页2026格式版、8页模型备选及110页影印版，另有逐章写作指南、执行提示词与验证记录。该目录为保留的只读母版；本次正式A题写作副本位于`paper/latex_draft_from_replica/`。独立交付：[模板ZIP](2025D论文复刻与2026LaTeX模板_20260922.zip)。
