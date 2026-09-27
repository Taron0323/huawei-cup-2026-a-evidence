## 2026-09-27：方案 B 新实验切换记录

当前论文唯一主工程为 `deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/`。本轮采用方案 B：正文算法、图表、附录代码和支撑记录均以 `2026华为杯idea冻结工作区/实验数据/v7_fast_reports_complete_20260927/` 的 `main_results.csv`（final_selection）为正式结果源；候选级 `timing.csv` 不作为主矩阵。主矩阵覆盖100图、1--5核、A/B/C共1500条，全部 `AI_VERIFIED`。五核平均速度比为 A=3.4383、B=3.4738、C=3.5533；Cache五核硬件/适配/综合效应为1.0146/1.0139/1.0289。

正文已删除旧的“评价后逐图继承”主算法口径，改为 mandatory anchors、profile、场景化候选和官方事件评价后的逐组合 final_selection；附录源代码同步到 `support/experiment/v7_fast_20260927/`，逐图表改由 `generated/v7_*` 生成。Cache敏感性采用 `v7_fast_sensitivity_report_complete_20260927`：24组固定计划全部成功，37条重优化候选全部成功，四变体各3/6组改变计划。

证据边界：228个尾部组合来自 fast-profile 补齐；solver文件与主矩阵哈希存在漂移；case_054/5核、case_062/4核、case_085/5核有三个B/C初始计划不一致项。上述事实保留在支撑记录中。当前尚未重新编译本轮PDF。

# 接续说明

## 2026-09-26：最新人工预审 PDF 与接续边界

在 `deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/` 继续编辑；`paper/latex_draft_from_replica` 是兼容软链接。最新可交人工预审的文件是 `output/main-2026.pdf`：76 页，SHA-256 `af841119817b1a35c24d4bd55624a1ad98a04aea90f12f2ab805eba3a9e2adc5`。已落实《华为杯修改意见.docx》八项正文要求，按同题 `.doc` 重写摘要，新增第四章流程图、逐问灵敏度分析，并在第 9.2 节补入分母明确的受控消融表。封面第一页未改，用户将自行替换。重建与证据说明见工程 `README.md`；最终 LaTeX 日志无溢出盒、未定义引用、缺字或致命错误，仍有三条 xeCJK 字体族重定义提示。摘要、流程图和消融表已抽查。

接续科学工作时，先取得与 `3.5101` 同版的问题二逐图结果，再重算折线图、实例重采样区间和相关正文。现有 Cache 消融仍属于 2026-09-24 冻结 B/C 配对矩阵，不得与新版问题二逐图数据混称同一次实验。不要将补充的 v5 必评基线审计并入冻结主矩阵；它超出 Final Idea 每组合两次完整评价的原预算，需另行界定方法和证据。当前 PDF 是人工预审稿，尚非科学终稿或正式提交文件。

## 2026-09-26：摘要渲染修复，封面留待手动替换

原`frontmatter.pdf`的摘要页在渲染时丢失中文字形。当前有效`frontmatter.pdf`由原封面页和 XeLaTeX 生成的`frontmatter-abstract.tex`摘要页组成；摘要文字直接来自`sections/abstract-prose.tex`，内容未改写。第一页封面没有替换，按用户要求留待最终手动替换。

已重新编译`output/main-2026.pdf`（77页，SHA-256：`d4a8b0af28a24e288cfac588ad303f21dae0d5f878cb9a2d105bdbb077d83648`）和`output/main-overleaf.pdf`（77页，SHA-256：`0a6a6f0bc8ea0fafe8d6ecfaff9ff28e61d38c124626c81b52256c90e1f62991`）。摘要页的 PNG 渲染已确认中文和加粗内容完整，原损坏版本与修复日志保留在工程`build`目录中。

## 2026-09-26：三问折线图差异化版式已完成

本次数据更新已将问题二五核平均加速比改为`3.5101`。当前主 PDF 为77页，SHA-256为`10c9f1301006c942a24fd9330f255c2519b2f1be58a6b2660200534393c3a5e1`；原始逐图CSV、问题二折线图及其重采样区间仍待恢复实验完成后重新绑定，当前PDF作为聚合值更新版人工审阅稿。

当前唯一论文源仍为`deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/`，兼容入口为`paper/latex_draft_from_replica`。本轮未重新运行实验，只从冻结结果重建图表并同步正文：问题一采用右侧4至5核局部放大，问题二在主图标出4至5核关键拐点并解释26张图反升，问题三在主图内嵌4至5核窗口并解释17张图反升。三问均保留均值95%实例重采样区间，统计值与主矩阵不变。

最新PDF为`output/main-2026.pdf`，物理页数78，SHA-256为`d561efb93ea9a4df46db9cf126e3e040c2c59f7ea7ee4181798922dfa2c04be5`。`build.py --only main-2026`编译通过，最终日志无`Overfull`、未定义引用、缺字或重复标签；已渲染封面、摘要、目录、三张折线图、参考文献和附录续表页。参考文献8个有 DOI 的条目均在 PDF 中生成蓝色可点击 DOI 链接。xeCJK字体族重定义提示仍为既有非致命提示，未改变输出。

## 2026-09-25：三级标题按参照论文重新修订并完成PDF复编

继续从`deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/`工作；`paper/latex_draft_from_replica`只是兼容软链接。已逐段核对34个三级标题，改为“具体对象＋建立/确定/计算/结果分析”的竞赛论文式短标题，包括“原始计算图与依赖关系”“调度变量与约束条件”“候选起点的构造”“评价指标的计算”“问题一的求解结果”“低速图逐例分析”等；相邻过程式二级标题未改动正文功能。正文模型、结果和数值未改变。参考文献前的两行孤页已通过取消非必要分页消除，AI说明位于参考文献起始处之前。

最新PDF为`output/main-2026.pdf`，74页，SHA-256为`6ae63657eedf5f64a15b21e95d110b3747939740ee81b872b8c2ecc19b977397`。执行验证：`python3 build.py --only main-2026`成功；日志无溢出盒、未定义引用、缺字或重复标签；三级标题清单、目录和第9、23、29、41页渲染页面已复核，标题均保持单行。此前协作者ZIP未包含本轮标题修改，重新打包前以当前主工作区为准；不要运行全量实验或覆盖冻结结果。

## 2026-09-25：审稿意见续改已编译

主工作区 `deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/` 已完成附录去流程化和四项审稿意见的正文修订。最新 `output/main-2026.pdf` 共74页，SHA-256 `c5fea31f652744833531731726abad3686dc34a83ff061397d12615c3cfd8f47`；关键源码约9页。附件不再排印运行/报告脚本、GPU排序代码或 `AI_VERIFIED` 等内部字段；AI说明已压缩并接在正文末页，正文保留统一A0基线、两组同计划对照、算法复杂度/候选级计时和六图L2扰动结果。PDF编译无溢出盒、未定义引用或重复标签。

本轮没有重新运行实验，主矩阵、Cache配对和敏感性数据仍为冻结结果。候选级计时不是整轮端到端墙钟；这一项保持为待补证据，未用其他数值替代。重新打包前应先完成视觉抽查并更新 ZIP 日期版本。

## 2026-09-25：协作者包已设为主工作区

当前唯一真实编辑源为 `deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/`。`paper/latex_draft_from_replica` 是指向该目录的兼容软链接；后续所有论文改动、图表重建和 PDF 编译均服务于此主工作区。原完整工程已保存在 `archive/latex_draft_from_replica_before_collaborator_main_20260925/`，仅供追溯。详细路径与命令见 `PRIMARY_WORKSPACE.md`。

当前主工作区的正式阅读入口为 `deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/output/main-2026.pdf`，76页，SHA-256 `117c07514daf7314ccd37795217cdbad472bd2d45351b0f7f8db7b2e2038c8db`。日期命名 ZIP 是当前快照，不自动跟随主工作区后续修改。

## 2026-09-25：当前论文入口与分页验收

阅读 `paper/latex_draft_from_replica/output/main-2026.pdf`（77页，SHA-256 `2a6786ef3394e0b00dc7143594b3a7bc6e911d1876bb191cca8c0e766787ebbb`）。封面1页、摘要2页；第4--44物理页连续承载九章正文及第44页下半部AI工具说明，12条英文参考文献独占第45页，附件索引第46页。关键代码节选从第47页开始，数据附录在第57页下半部接续，长表以“续表”排至第77页；代码节选不是完整可运行源码，完整作者代码、官方评估器和原始实验结果按工程README与附件索引查找。题面和官方程序的来源仍在正文及附件索引中说明。

本轮摘要改为自然流动，删除正文章节、AI说明及附录内部的非必要强制分页，仅保留参考文献和附录整体起页。源文件扫描只命中这两处允许的 `\clearpage`；最终构建无未定义引文、溢出盒、缺字或重复标签，摘要、章节衔接、参考文献、附件和续表页已渲染复核。改前快照在工程 `build/stage_before_no_forced_pagebreak_20260925/`。人工科学审阅与正式提交未完成，冻结实验的CPU官方模拟结果未改变。以下2026-09-24记录是历史阶段状态。

## 2026-09-24：最新PDF与接续检查

当前唯一源工程为 `paper/latex_draft_from_replica/`，正式PDF为 `paper/latex_draft_from_replica/output/main-2026.pdf`（168页，SHA-256 `3a5a04c23a2cfc359d58a6976f7e9150edd813f16df133caa609ff3c40d555a3`）。封面1页、摘要2页、九章正文40页；AI使用说明在物理第44页，参考文献第45页，附件索引第46页，完整源码附录从第47页开始，数据附录从第148页开始。摘要源统一由 `scripts/update_abstract.py` 生成Word和TeX；修改后按工程README导出 `frontmatter.pdf`，再运行 `../../.venv/bin/python build.py --only main-2026`。源码附录的摘要脚本用行号112--116遮蔽封面身份，若再次调整该脚本行数，须同步核查遮蔽范围及PDF第2页以后的身份扫描。人工科学审阅与正式提交尚未完成。

## 2026-09-24：当前论文接续入口

唯一修订工程为 `paper/latex_draft_from_replica/`；先读该目录 `README.md`、`写作对照与验收.md` 和 `文献核验与正文落位_20260924.md`，再看 `output/main-2026.pdf`。当前 PDF 为67页，封面1页、摘要2页、第4--43物理页九章正文共40页，参考文献在第44页、支撑材料从第45页起。按用户给定的2023年论文重排章节，并借鉴2024年冠军论文的逐步求解语言；原始100图画像和可视化在第四章，问题三有硬件效应与调度适配交叉分类。封面字段为西交利物浦大学、`20260079630`、傅陶然、王梓谦、史昕轶。

接续时从该工程目录执行 `../../.venv/bin/python build.py --only main-2026`；若修改 Word 摘要，先按工程 README 的绝对路径 `FONTCONFIG_FILE` 命令导出 `frontmatter.pdf`，核对三页中文和四个官方标识后再编译。当前构建无溢出盒和未定义引用；封面队号可见字高和顶边已与标签对齐，问题二的大段留白已消除。新增10篇CCF A文献和原4条官方资料均在第44页，正文各有对应引用；出版来源与引用边界见文献核验表。冻结结果包的1500个唯一存储组合含100个问题一单核辅助诊断，正式三问为1400组；CPU官方事件模拟与有限候选的证据边界不变。队员人工科学审阅和平台提交未完成。下方44页、59页和旧运行记录属于历史阶段。

## 2026-09-24：图表美化与Cache硬件效应饼图已接入

当前论文源仍为 `paper/latex_draft_from_replica/`，最新正式 PDF 为 `paper/latex_draft_from_replica/output/main-2026.pdf`（44页）。本轮基于 `data/final_idea_v2/` 的冻结 CSV 重建全部论文图表：柱状图统一国赛风格纹理和柱顶数值，折线图统一标记、置信带、虚线网格和3--5核放大；未修改实验 CSV、模型结论或旧历史结果。

问题三 `sections/08-model-de.tex` 新增 `fig:cache-hardware-pie`。`figures/cache_hw_effect_pie.pdf/png` 左侧为突出“改善”扇区的分层立体饼图，右侧为改善幅度五档拆解。数据校验固定为五核100组：54改善、46持平、0退化；54个改善样本的幅度计数为36/11/1/3/3。改动前图表和脚本快照保存在 `Each Stage Review Work/20260924_final_idea_paper_update/figures_before_style/`。

已执行 `.venv/bin/python scripts/build_final_evidence.py`、`.venv/bin/python build.py`，并渲染正式 PDF 第13--18页检查图表裁切和排版。当前仍需队员完成科学与人工核验、真实封面字段及正式提交；立体饼图只承担视觉层次，不改变二维比例。

## 2026-09-24：当前接续入口为独立 Idea 冻结工作区

新准备区：`2026华为杯idea冻结工作区/`。等待用户上传或指定本轮 Idea 与提示词；接收后先登记原件、核对版本并冻结唯一 canonical 输入。

该准备区不自动继承 `paper/v071_trial/`、`paper/latex*`、`results/v071_*` 或其他历史快照。当前不得写初稿、跑实验、生成图表或把旧结果改写为新稿证据。

## 2026-09-24：V0.7.1论文已迁入指定D题复刻母版

当前论文：**A题 V0.1 复刻模板改写版**，唯一源工程为`paper/latex_draft_from_replica/`，2026格式PDF为`paper/latex_draft_from_replica/output/main-2026.pdf`，59页；原稿风格版76页，Overleaf入口59页。完整交付为`deliveries/A题V0.1_复刻模板版_20260924.zip`，验收记录在新工程`写作对照与验收.md`。

本稿严格使用会话指定V0.7.1、原运行`v071_full_20260924_v2`及16次固定A0补算`v071_singlecore_baseline_20260924`，不采用相邻V1.0或另行Final方案作为既有结果的方法来源。统一95整图单核基准，Q1/Q2正式单核点为1，五核均值1.938640、2.490422、2.543631；475组固定C计划Cache对照，五核均值1.022347。五图014/072/076/087/091动态结果仍缺，人工核验、科学复核与提交未完成。

D题母版和历史模板ZIP的242项保护指纹无变化。此前9月24日36页稿及源工程已移出活动paper目录，保存在本轮阶段记录的superseded目录；9月23日被撤销稿没有恢复。当前重建命令：`.venv/bin/python paper/latex_draft_from_replica/build.py`；绘图和完整附表重建见新工程README。

其余Idea推进与历史阶段记录如下；不同Idea/运行的结果不得混用。

## 当前接续（2026-09-24）：按 Final Idea 接入算法和完整实验

统一研究方案为 [A题_Final_Idea.md](../idea/A题_Final_Idea.md)。Final 已落实用户要求的通俗表达、三问模型与解法、容量及 Cache 时序机制、实验表格、计算预算和可直接入稿的段落。第 11 节逐文件说明现有实现怎样衔接。

直接从 `tools/v071_plan_search.py` 的 `canonical_plan` 开始：规范化只重新编号，保留每核顺序；随后接入前缀域、真实活跃字节、参考执行骨架、容量代表、FIFO 一次回放及 C 三类代表。结果写入新的 `results/final_idea_<运行号>/`。按 Final 第 9.1 节测三档主矩阵任务和六次同计划完整入口复测，再完成 100 图、机制对照和汇总。第 10 节可同步用于起草三问的模型与算法章节，版式沿用 `prompts/09_严格按复刻模板写新赛题初稿.md`。

本轮交付文档与静态核验，没有启动后台求解。旧 `v071_full_20260924_v2` 的 95 图结果仍保留原方法归属；其五个大图在旧运行中完整候选数设为 0，Final 矩阵包含这些图的完整评估。以下历史等待记录按当时任务保留，后续研究使用上面的 Final 入口。

## 当前接续：优秀论文写法修订稿

当前论文为按优秀论文论证结构重写后的 V0.1：`paper/A题论文V0.1_试验稿_20260924.pdf`，唯一主源为`paper/latex/main.tex`，分节源稿在`paper/latex/sections/`。全稿36页：官方封面1页、逐问摘要1页、正文至参考文献14页、完整数值附录20页。重建命令：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/build_v071_paper.py`。

本次修订重新展开模型假设、驻留域搬运推导、实际候选算法、代表方案、逐问结果、检验及评价。纠正旧“100操作切块”描述、输入输出字节差启发式与FIFO语义、字典序筛选及单核基准。**加速比基准是问题一选中的单核方案，其中50例单Task、45例含2至5个Task，不能称为统一整图单核。** 原始结果数值保持不变。

结果仍来自`v071_full_20260924_v2`：95个完整图、1425份选中结果、475组固定C计划Cache对照；5个大图的动态结果尚未补齐。Q1/Q2/Q3五核平均加速比为1.920640、2.466990、2.519783，同计划Cache平均加速比1.022347。本次完成1425份搬运/工期回查及8550条报告容量检查；未新增求解实验，科学复核、队员人工核验和实际提交尚未完成。

修订与验证见`review/v071_exemplar_rewrite_delivery.md`及`Each Stage Review Work/20260924_exemplar_rewrite/`。此前9月24日P0/P1与旧编译预览已移出活动论文目录，历史快照仅供查错；9月23日按用户要求删除的旧稿没有恢复。

下一步若继续实验，应针对未完成机制和五个大图创建新运行号；修改写作只使用当前分节源与统一PDF入口。不要运行旧初稿生成器覆盖本次重写。

## 以下为历史接续


写作提示词入口（2026-09-24）：`prompts/09_严格按复刻模板写新赛题初稿.md`。用户届时提供最终Idea与对应结果后可整段执行，目标工程为`paper/latex_draft_from_replica/`，母版`paper/latex_d2025_style/`保持只读。本轮未启动论文写作或实验，不能把提示词中的执行命令当成本轮已经完成的动作。

## 2026-09-24：旧中文初稿已彻底删除

用户要求删除本任务先前交付的9月23日33页中文初稿。稿件源文件、PDF、摘要、预览、归档/快照正文和旧交付ZIP均已删除，不保留内容备份。数值实验和当前9月24日新版稿件保留；不要根据下方历史路径自动重建旧初稿。删除与保护哈希核验在`review/cleanup_20260924_old_draft/verification.json`。

## 当前接续（2026-09-24）：V0.7.1 实验已完成，V0.1 试验稿已冻结到可复核状态

权威 Idea 为`../idea/A题_Idea_V0.7.1_融合修订.md`，SHA-256：`432f5c9ad8a1b9f413f9faa1a478b4dd551ce874e69bf3d6dda115c1d99434f0`。正式运行目录为`results/v071_full_20260924_v2/`，状态`COMPUTED`，500个case-core单元全部完成、0个候选失败。汇总目录为`results/v071_full_20260924_v2_analysis/`。

当前正式结果口径：候选13,127行，官方完整评估3,318行，PROFILE_ONLY 9,809行，选中1,425行；95个case形成完整均值，case_014、case_072、case_076、case_087、case_091五个大图的25个case-core单元全部profile-only。Q1/Q2/Q3五核逐例平均加速比分别为1.920640、2.466990、2.519783；Q3同方案Cache加速比1.022347、字节加权命中率19.746150%。5核慢于统一整图单核的完整case分别为30/95、7/95、5/95。所有正式选择行`AI_VERIFIED`，但`global_optimality=NOT_PROVEN`、科学验证和人工核验仍为`NOT_ASSESSED`。

论文主源已经从旧稿切换为`paper/latex/main.tex`，生成表位于`paper/latex/generated/`，统一封面/摘要为当前V0.1版本`paper/latex/frontmatter.pdf`，交付试验PDF为`paper/A题论文V0.1_试验稿_20260924.pdf`。9月23日旧稿及其归档已按用户要求删除，不得重建或把旧数字带回新稿。新稿编译、文本扫描和关键页面视觉检查已完成；当前摘要和正文都明确五个大图的PENDING边界。

结果审计见`review/v071_result_summary_20260924.md`与`review/v071_result_audit_20260924.md`；候选实现审计见`review/v071_implementation_audit_20260924.md`。下一步若继续推进，应先补算五个大图或缩小其输入规模并重新登记运行号，然后重生成汇总、图表、claims和论文；之后由队员完成科学与人工核验、真实封面字段和正式规则检查。旧历史段落继续保留，不代表当前状态。

## 当前机制诊断接续（2026-09-24）

独立机制扩展见 `review/v071_mechanism_grid_audit_20260924.md`。已完成 `case_001`、`case_002`、`case_016`、`case_093` 的 2/5 核 A/B/C 共 8 个单元，轻量代理与官方槽内 winner 一致率为 A 7/8、B 5/8、C 6/8。该结果是 `PROXY_ONLY`/`DIAGNOSTIC_ONLY` 证据，不改变 `results/v071_full_20260924_v2/` 的正式结果。

首轮 grid 在 `case_025/2core` 的官方 B profile Step3 长尾等待中断，见 `results/v071_mechanism_grid_20260924_v1/failure_records.json`；没有晋升结果。`case_025/5core`、`case_076` 机制扩展待受控补算。FIFO 代理重加权、完整 V1/V2 状态机、参数诊断和公平候选消融仍未完成，不能把该小样本一致率写成全量性能结论。

## 当前论文接续（2026-09-24）

P0/P1 试验稿已落地到独立副本：`paper/latex/main_p01.tex` 和 `paper/A题论文V0.1_P0P1修订试验稿_20260924.pdf`。最终 PDF 42 页，SHA-256 为 `de6a36dcf53413e7a27732fedb94d3c1937346d68564f86e4025b8124d7d8007`。修订使用已有 v2 证据，补入模型假设、技术路线、逐问小结、题面要求曲线、Q3 双侧搬运附录和复现说明；旧 `main.tex` 与旧 V0.1 PDF 保留原字节。

编译与关键页视觉检查通过，摘要重复已移除，Cache 附录 475 行状态列完整。修订稿仍明确 95 个完整 case 的均值边界、五个大图 `PENDING`、有限候选 `NOT_PROVEN`、科学/人工核验 `NOT_ASSESSED`；没有把机制 smoke 或代理一致率写入正式性能结果。


## 以下均为历史阶段接续（不覆盖上方当前状态）


## 当前接续（2026-09-24）：V1.0 Idea 已定稿，等待 Vibe Paper PDF

交付文件为 `../idea/A题_Idea_V1.0_Astra定稿.md`，SHA-256：`50793fa293dd1dd8286a80da2ebc5600a14c1ac5f21d6e9159ff803d665ef3cd`。权威输入为用户指定的 V0.7.1、当前 A 题 DOCX 和官方附件；本文已收敛为完整 12 节，包含 32 个编号公式、四起点和确定的编辑/评分规则、A/B/C 两槽状态处理、说明性手算、完整预算、论文主线及拟建接口。默认预算为完整调用 3074、独立 profile 7640、计划级展开 10714；墙钟模型计入串行等价工作、实测并发效率与最长 B→C 依赖链。

核验记录在 `Each Stage Review Work/20260924_idea_v1/verification.json`。结构、链接、算术、输入哈希及全文措辞检查通过；原文已定点核对。阶段快照如实保留早期未交付压缩稿及后续纠正，不将该草稿作为交付。此会话未开发算法、运行官方评估或生成论文；性能与 8 小时可达性尚待实际运行。

本次按 08 阶段约定停止，下一步等待用户指定 Vibe Paper PDF 后针对性优化。若用户另行授权实现，按 V1.0 第 11 节接入本版算法，先做第 9 节机制核对与代表图计时，再冻结运行协议；历史算法结果不自动成为本版证据。下面其他任务的等待状态与历史记录保留原文。

## 当前实验接续（2026-09-24）：等待用户final idea

当前实验任务为`EXPERIMENT_PREPARED_AWAITING_FINAL_IDEA`。用户只要求本轮准备；下一步接收用户指定final文本或路径，再实施其算法和实验。不要把V0.7.1自动当作final，也不要据历史段落恢复旧计算。

先读`review/A题实验准备_20260924.md`和`review/experiment_preparation_20260924/`。输入、100图、官方配置、依赖及入口已经检查；项目pandas修复为2.3.3并补齐版本锁。这次没有运行新A题评估，旧结果仅作旧方法对照。

后续复用日志/哈希/新run-id机制，按final接入分场景搜索、profile与预算，并适配B/C校验及汇总矩阵。`run_a.py`无参数默认旧方法full；`a_solver.py`旧CLI可能覆盖同名结果，不直接采用。`a_validate_small.py`含正式case_001评估，本轮未运行。

收到final后：核对版本与模块 → 实现及最小验证 → 代表图测耗时内存 → 正式矩阵和必要对照 → 汇总、图表与复现。普通实现按已有授权推进。当前没有本轮启动的后台求解；阶段证据在`Each Stage Review Work/20260924_experiment_preparation/`。以下其他任务记录保留。

## 最新接续（2026-09-24：初稿写作前准备）

用户要求先准备 A 题论文写作，等待其 final idea 后才开始 V0.1。本轮完成只读核对并新增 `prep/A题初稿写作准备_等待FinalIdea_20260924.md`；阶段快照为 `Each Stage Review Work/20260924_pre_draft_prepare/before/`。没有改动 `paper/latex/main.tex`，没有启动新求解器，没有生成新的论文正文、摘要或结果图。

当前已有 2026-09-23 旧路线 DRAFT_VALIDATED 结果与 33 页论文，只能作为基线材料。收到 final idea 后先建立唯一 canonical 版本，明确 F1 容量候选和 F2 Cache 错峰是否纳入，核对旧结果能否复用，再更新逐问交付表、运行队列和 claims/figures 证据。不得把 V0.6/V0.7 评审分数、旧路线数值或软件检查写成 final idea 的性能、全局最优性、人工核验或提交状态。

接续入口：阅读 `prep/A题初稿写作准备_等待FinalIdea_20260924.md`，等待用户 final idea。用户发送后，按“canonical idea → 公式/算法接口 → 基线与核心改进 → 实测与验证 → 结构写作 → 摘要与交付检查”顺序推进；未验证内容保持 `PENDING`/`NOT_ASSESSED`。

## 最新修订接续（2026-09-24）

用户要求的 V0.7.1 已交付于 `../idea/A题_Idea_V0.7.1_融合修订.md`，并吸收后续要求：参考优秀论文的模型与算法选择、在同一文档给出 V0.7 对照及来源、全文优先可读性。§1—11 为完整方案及实施安排，§12 为来源与进度，§13 为逐项改动，§14 为五篇 2024 原文和 Alpa 的借鉴映射。

两条探索入口已补齐：A/B 容量代表可绕过普通轻量改善；C 的时序、容量和普通代表共用一个局改名额。普通链、官方两槽及原预算保持一致；当前文档为设计完成状态，未启动 V0.7.1 求解任务。复核记录为 `review/A题_Idea_V0.7.1_修订核验说明_20260924.md`；差异、原件哈希、公式与算术检查在 `Each Stage Review Work/20260924_idea_v071/`。后续按用户要求开展实施或论文撰写，沿用 §11 的模块职责和本版直接表达；原稿及官方输入保持原样。下述整体评审与其他算法运行均为此前记录。

## 最新评审接续（2026-09-24）

用户本轮仅要求整体 review V0.6 与 V0.7。报告：`review/A题_Idea_V0.6与V0.7_整体评审_20260924.md`。已核对当前题面、关键构图/FIFO语义与100图静态数据；没有启动 Idea 内的实现或论文指令。建议以V0.7为主稿，优先核对报告F1容量探索和F2错峰候选的轻量准入，二者可在原profile名额内讨论，不需扩充全量矩阵。此次未修改idea及评分记录，无本轮仍运行的求解任务。下一步依用户指令决定是否修订或实施；下述历史计算与交付不证明V0.6/V0.7已经运行。

## 最新接续（2026-09-23）

16:17:57交付核验完成：15160文件哈希与ZIP CRC通过，解压后新venv的45组smoke与原结果完全一致，0失败、0差异。`deliveries/A题自动求解_20260923.verification.json`为实际终态记录。没有需要恢复或重启的活跃计算；后续优先由队员阅读初稿及人工事项清单。

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

## 2026-09-26：当前论文审阅交付

当前人工审阅入口为 `deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/output/main-2026.pdf`。目录采用黑色链接、显示三级标题并独占两页；摘要把问题三的参数检验并入对应段落。PDF 共76页，SHA-256 为 `6034277adc4298a0136107d3959778d0325525690be1b87a17d8ad26b74d3231`，编译日志通过版面和引用检查。队员接下来应重点人工核对摘要措辞、目录页码和新增问题三结果段；实验与提交状态不变。


## 2026-09-27：v7 raw 数据替换与交付完成

当前论文主工程为 `deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/`。已将 v7 raw `final_selection` 主矩阵接入同学稿，正式 PDF 已重新编译为 60 页：`deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/output/main-2026.pdf`。主矩阵为 1500 条唯一组合，五核平均速度比 A/B/C=`3.4383/3.4738/3.5533`；PDF 文本未检出旧结果数字。

可交付压缩包为 `deliveries/latex_draft_from_replica_v7_raw_20260927_delivery_3.zip`，包含当前 LaTeX 源、v7 主数据、图表、支撑代码和 PDF，排除了 inherited 与历史旧结果目录。PDF SHA-256=`ccbe2ae6d1fb295effdfcb09a13df699148df2804bf07921e558900c714db020`；ZIP SHA-256=`554a7a339277f36357db75d640f65676971b74a28276036abde43b4025a4ce9e`。


## 2026-09-27：图2替换完成

用户提供的 `组织结构图-可编辑重建-v9.pdf` 已直接作为 `figures/roadmap.pdf` 嵌入主工程，替换 `sections/04-preparation.tex` 中原图2的 TikZ 图体，保留 `fig:roadmap` 标签和图注。最新 `output/main-2026.pdf` 为60页，图2位于正文第9页，已渲染检查无裁切、无重叠；编译报告无警告。包含图2替换的交付包为 `deliveries/latex_draft_from_replica_v7_raw_figure2_20260927.zip`。
