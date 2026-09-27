# 2026华为杯A题论文：Final Idea 实验版

## 当前主工作区与阅读入口（2026-09-27）

本目录是以同学修改稿为母稿、同步 v7 新实验后的唯一论文工程。人工审阅 PDF 为 `output/main-2026.pdf`，当前68页；本轮正文、图表、附录表和支撑代码统一使用 `data/v7_fast_20260927/` 中 raw `final_selection` 主矩阵，不使用工程外的逐图继承物化视图。

主矩阵覆盖100张图、1至5核、A/B/C三场景共1500条记录，1500/1500条为 `AI_VERIFIED`，组合键唯一。五核平均速度比为 A=`3.4383`、B=`3.4738`、C=`3.5533`；Cache五核硬件、调度适配和综合效应分别为`1.0146`、`1.0139`和`1.0289`。Cache敏感性实验为24组固定计划全部通过、37条重优化候选全部通过，四种硬件变体各有3/6组改变计划。

同学稿的章节顺序、版式、图表风格、伪代码和正文展开均保留；新数据已同步到 `sections/abstract-prose.tex`、问题一至问题三正文、整体评价、生成长表、图表、支撑索引和附录。封面第一页保持原样，按用户要求最后手动替换；摘要页已经重新编译并与封面合并。

构建命令：`python3 build.py --only main-2026`。结果源、代码快照和敏感性报告分别位于 `data/v7_fast_20260927/`、`support/experiment/v7_fast_20260927/`、`data/v7_fast_sensitivity_20260927/` 和 `data/v7_fast_controls_20260927/`。

## 最新图表版本（2026-09-24）

本版本的图表由 `scripts/build_final_evidence.py` 从 `data/final_idea_v2/` 的冻结 CSV 复现。柱状图使用浅色填充、深色边框、纹理、柱顶数值和灰色虚线网格；三问折线图共用置信带和数值口径，但采用不同的阅读结构：问题一右侧为4至5核局部放大，问题二直接标出4至5核关键拐点，问题三在主图内嵌4至5核窗口。问题三新增 `figures/cache_hw_effect_pie.pdf/png`，展示五核Cache硬件效应的分层立体饼图，并把被突出显示的“改善”扇区按提升幅度继续拆解。该饼图只用二维扇区表示比例，分层厚度是视觉效果，不代表第三维数据。

新增图的数据由脚本断言校验：五核100组中改善54图、持平46图、退化0图；改善幅度五档为`<1%` 36图、`1--3%` 11图、`3--5%` 1图、`5--10%` 3图、`>=10%` 3图。正文引用位于 `sections/08-model-de.tex` 的图8.6。重建前的图表快照保存在 `../Each Stage Review Work/20260924_final_idea_paper_update/figures_before_style/`。

正式阅读入口为 `output/main-2026.pdf`。论文继承指定 2025 年 D 题复刻母版的排版接口，章节次序按本轮 2023 年参照论文调整；数学内容及数值来自 Final Idea 和 2026 年 9 月 24 日冻结的 v2 主矩阵、敏感性报告。

方法题目为《张量驻留与查询时序驱动的神经网络处理器多核调度》。三问依次处理Task边界、核心级驻留与共享只读Cache；C从同图同核的B最终方案出发，按同计划硬件效应、C内调度适配和综合工期比分解收益。实验覆盖100图、1—5核、三问的1500条最终官方模拟；100组整图单核基准、1500组初始/最终比较、500组Cache配对均纳入。六图四变体的24组固定敏感性计算完成。

工程中的主要入口：

- `body.tex` 与 `sections/01-background.tex`、`02-problem.tex`、`03-symbols.tex`、`04-preparation.tex`、`06-model-ab.tex`、`07-model-c.tex`、`08-model-de.tex`、`08-overall-sensitivity.tex`、`09-evaluation.tex`：九章正文。
- sections/source-code.tex、sections/appendices.tex、generated/：9份作者源码的22处关键节选（约680行）、100图逐例表、Cache配对与敏感性。完整作者代码与10份官方评估器保存在支撑目录，官方文件明确标明为赛题附件，不在论文中全文排印。
- data/final_idea_v2/：权威报告CSV及核验文件的副本。
- scripts/build_final_evidence.py：校验配对、重算统计、绘制PDF/PNG及附表。
- scripts/update_abstract.py：从保留四个校徽/标志的官方母版更新Word与TeX摘要。
- support/experiment/：Final Idea、当前算法和官方评估器副本；原始图和全部候选时间线由冻结实验工作区追溯。
- support/REPRODUCE.md：结果来源、程序入口和证据边界。

仅修改正文时，直接运行 `../../.venv/bin/python build.py --only main-2026`。修改摘要时，先运行 `scripts/update_abstract.py` 同步 Word 与 TeX 文字，再用 XeLaTeX 编译 `frontmatter-abstract.tex`，把生成的单页摘要与当前 `frontmatter.pdf` 的第一页封面合并为新的两页 `frontmatter.pdf`，核对中文、加粗、页码及封面后再运行 `build.py`。Word/LibreOffice 导出的摘要会分页成两页，不能直接覆盖当前两页的 `frontmatter.pdf`。`build.py` 不重新运行全量求解；完整构建还可输出 `main-reference.pdf` 与 `main-overleaf.pdf`。

单核A/B曲线点按题面规定为1，但实际单核选中方案工期仍保存在 CSV。Cache 敏感性 24 组固定计划均完成，重优化候选中 36 条通过评价、12 条因依赖环失败；Apple MPS 只用于轻量候选负载排序，工期由 CPU 事件评估程序给出。结果对应有限候选集合，不表述为全局最优或 NPU 实机测量。
