# 接续说明

## 最新接续（2026-09-23）

当前阶段DRAFT_VALIDATED。A题全部4068组评估已在清洁环境重算并逐项一致，无活动全量计算需要重启。权威结果是`results/auto_solve_20260923_120249/analysis_final/`；论文主源为`paper/latex/main.tex`，交付PDF为`paper/A题论文初稿_20260923.pdf`，33页自动/视觉核验完成。22条需求、21条数值结论和六组图的证据登记完成，完整验证报告在本轮03_validation。

复现入口：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run_a.py --mode smoke --workers 14`，自动生成新run-id。完整重算改为`--mode full`。本轮主要结果已经重算，不必为恢复再次跑全量。

交付目录：`deliveries/A题自动求解_20260923/`及同名ZIP；相邻`.verification.json`记录ZIP CRC、清单哈希和解压后45组smoke对比，必须读取实际终态。打包脚本为`tools/a_package_delivery.py`。人工动作见`support/仍需人工完成事项.md`。准确AI型号/版本/发布日期/推理档位UNVERIFIED，人工核验NOT_ASSESSED，提交NOT_SUBMITTED。

实际CPU优化已完成：14进程，主实验1109.133秒，较首轮减少29.68%，CPU容量平均75.82%、峰值92.01%，进程RSS峰值9.20GiB。GPU无适配后端。详见`review/auto_solve/20260923_120249/03_validation/clean_repro_v1/reproducibility_manifest.json`。

下述原阶段记录保留历史，不能据其中“正在运行”启动重复任务。

当前阶段SOLVING。用户已确定A题，并要求充分使用本地M4 Pro加速。A-F初步比较、A题116份原件登记、100图体检已完成。20260923_120249轮smoke test共45组评估全部通过，12项小规模验证通过。首轮全量`results/auto_solve_20260923_120249/full_v1/`已完成1300份方案、3900组评估，6进程，0失败，耗时1577.305秒，指纹未变。`analysis_preliminary/`已核对3900行并列出14个需要单核回退的用例。

资源测试正在比较6/10/14进程，入口`tools/a_cpu_benchmark.py`，输出`review/auto_solve/20260923_120249/04_performance/worker_benchmark_v1/`。默认批量worker改为os.cpu_count()，此机14；GPU没有兼容评估器后端。测试结束读取benchmark_manifest.json的selected_workers，用相同并行度跑单核回退与清洁环境全量复现，不能凭进程数宣称实测CPU始终100%。恢复时读对应manifest的PID并查真实进程，不重复启动活跃任务。

本轮冻结候选为balanced_greedy、component_aware、component_packed，整数周期与字节残差容差均为0，Cache比例容差1e-12。旧试跑结果在`results/auto_solve_20260923_110147/`，仅保留历史。新快照：`Each Stage Review Work/20260923_120249_06_A_full/`。待办：全量汇总、各问题方案选择、敏感性/随机对照、清洁环境复现、图表、中文LaTeX初稿及复现包。人工核验仍NOT_ASSESSED，提交仍NOT_SUBMITTED。

先读README、STATUS、CONTEXT及review记录。官方资料最新快照official/20260921；9月21日提醒已纳入。A-F原始题目位于上级题目目录，需先计算SHA-256并按输入职责登记，不能直接把副本或清洗数据当作原件。队伍个人信息只在prep/team.local.json，未知字段保持空。

下一条通用检查命令：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/workspace.py check`。评估器的输出路径必须显式指向results，避免默认写入inputs。
演练重跑命令：`.venv/bin/python practice/transport/run.py --run-id resume-check`，已存在时换新编号。
论文编译命令：`.venv/bin/python tools/build_paper.py latex`。

正式开赛入口prompts/01_接收与选题.md；恢复入口prompts/07_恢复.md。按用户最新要求，LaTeX为正文主源；官方Word用于填写封面与统一摘要页，再通过build_paper.py cover导入前2页或3页，正文自动接续编号。用户给出的46页参考PDF在reference，仅借鉴结构，不能覆盖2026规则。AI与支撑材料对照见paper/2026格式与合规对照.md。

待人工动作：报名/审核/缴费实际状态、队号、3名队员信息与分工、真实封面、AI版本证据、官方MD5程序交叉检查、正式论文核验及平台回执。附件.pdf/.rar描述差异须依据具体赛题和系统再核对。

工具验证不代表人工复核或平台提交。当前全量计算是否持续运行以manifest对应PID为准。历史检查器9项回归、演练6项检查已通过。ZIP验证结果以相邻.verification.json为准，不从计划文字推断已执行。

## 数模之星论文下载接续

`prep/数模之星优秀论文_2024-2025/README.md` 是新增学习资料入口；相邻 `数模之星论文_2024已齐13篇_2025待补原文.zip` 已完成 ZIP CRC 和逐文件 SHA-256 核对。2024 年 13 篇原文已齐，共 971 页；第三方原始 24 篇论文包保留在本机 Downloads。2025 年当前只有官方获奖依据，没有已核实原文 PDF，不能报告为两年全部下载完成。下一步可依据 `2025/原文待补齐.md` 的 12 个队号核对新来源，已排除的来源见 `采集记录/2025_检索记录.json`。资料限定用于准备学习，不是本届赛题输入。

## 2025 D题复刻模板接续

用户新增的110页D题参考论文已归档到`reference/d2025_style/`，与此前46页参考论文分开。可编辑模板与四份PDF在`paper/latex_d2025_style/`，详情见其中README、逐章指南及最终验证报告。

构建命令：`.venv/bin/python paper/latex_d2025_style/build.py`。只改某个入口时可加`--only main-reference`等。2026封面和摘要修改该目录`frontmatter.docx`，导出同名PDF后重新构建；摘要不超过两页，正文页码按实际前置页数续接。原稿风格摘要在`sections/abstract-prose.tex`单独维护。

完整验证脚本`verify.py`需要pdfplumber、pypdfium2、numpy、Pillow与pypdf。本机已使用bundled Python完成。打包脚本位于`Each Stage Review Work/20260921_04_d2025_style/package_delivery.py`，重新打包前先完成编译和视觉QA。原件、示意输出与2026正式证据保持区分。

此段为历史模板接续记录；当前已选A题，正式正文沿用paper/latex/main.tex，不把历史题模板冻结提交。2026规则优先于原稿版式，真实AI四字段仍需填写，支撑材料扩展名和题面额外要求仍待系统核对。

## 评阅标准检索接续（2026-09-23）

检索报告：`review/华为杯评阅标准检索报告_20260923.md`。

结论边界：公开官方材料没有逐题评分点、分项权重、百分制评委表、固定奖项分数线或单篇论文评语。能确认的是两阶段评审、摘要和正文均审阅、模型/公式/引用/AI/匿名/查重/格式要求，以及一二三等奖比例上限。2026参赛邀请函提到“数模之星”按集中评审论文得分高者优先，但没有公布该分数的构成。2022年公开的专家70%/大众30%只属于“数模之星”答辩投票，不属于基础论文评阅。

评审成绩公示附件已实际检查：2022-2025压缩包是获奖名单表，字段没有分项分数、评语或评分工作表。GitHub参赛者评审代码和其他数模赛事的评阅要点均保留为非官方线索，不得写进正式规则。

下次追踪：赛后重新检查官网评审公告、获奖附件、培训教师交流会报告正文和可能新增的公开附件。只有取得组委会或评审平台原件，才能更新“官方评分依据”。当前内部审查清单仅作准备自检，仍保持 `PREPARATION`。

## 冲冠军研究与公开Skill接续（2026-09-23）

历史研究入口为`prep/华为杯冲冠军研究_2024/交付说明.md`，包含13篇2024数模之星论文的共性、C/B同题比较、逐篇限制、9页报告及Skill。报告页码均按原PDF物理页码，不按印刷页码。共性存在不等于公平比较、科学复现或获奖因果；2025未纳入研究。

本机Skill：`/Users/futaoran/.codex/skills/huawei-cup-champion/`。公开发布目录：`prep/github/huawei-cup-champion/`，为独立Git仓库；远端`Taron0323/Huawei-Cup-Mathematical-Modeling-Skill`、`main`、提交`f43dc8edb10bd7783ae37aa4891f14af40dd23e6`。后续修改应同步研究源、安装目录与发布副本，重新验证后再推送，勿对整个正式工作区执行Git staging。

校验脚本在研究目录`scripts/`：`build_evidence_index.mjs`验证原件/页数并生成统一表；`render_report.py`构建PDF并生成逐页QA；`verify_publication.mjs`核对远端与本机文件；`package_delivery.py`打包并核对ZIP字节。PDF脚本依赖macOS字体与uv的reportlab、markdown-it-py、pymupdf、pillow。压缩包不包含原始论文PDF和检查PNG，包含页级文本与官方奖项依据。

本项已完成研究、交付和公开Skill发布，不对当前A题正式实验作结论。正式项目仍按本文件顶部的SOLVING接续，不因历史记录中的PREPARATION字样退回准备阶段。
