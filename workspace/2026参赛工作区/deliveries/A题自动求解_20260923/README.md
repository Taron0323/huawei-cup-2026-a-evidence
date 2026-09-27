# 华为杯2026参赛工作区

状态：DRAFT_VALIDATED。用户已确定A题，116份原始输入已登记，100图体检、45组smoke test、12项小规模检查及4068组全量/回退评估已完成。清洁环境重算4068组，0差异；六组图和33页中文论文初稿已生成并核验。复现目录及ZIP的核验终态见交付包相邻verification.json。

本轮入口：[论文PDF](paper/A题论文初稿_20260923.pdf)、[复现说明](support/A题复现说明.md)、[验证报告](review/auto_solve/20260923_120249/03_validation/validation_report.md)、[选题意见与更正](review/auto_solve/20260923_120249/01_selection/problem_comparison.md)。快速运行：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run_a.py --mode smoke --workers 14`。人工核验未完成，未正式提交。

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

最新写作准备入口：[2025 D题原稿风格与2026格式LaTeX模板](paper/latex_d2025_style/README.md)。包含44页可编辑原稿风格版、39页2026格式版、8页模型备选及110页影印版，另有逐章写作指南、执行提示词与验证记录。该目录供历史题练习和版式准备，尚未指定为正式2026论文。独立交付：[模板ZIP](2025D论文复刻与2026LaTeX模板_20260922.zip)。
