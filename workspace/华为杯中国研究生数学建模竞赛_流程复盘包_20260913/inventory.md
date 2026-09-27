# 本次数学建模流程事实清单

生成日期：2026-09-13  
项目：CUMCM 2026 C题“小区购电与储能调度”  
用途：为下一届华为杯中国研究生数学建模竞赛建立可复用的工作流程和资产索引。

## 1. 本次项目的真实边界

- 正式题面于2026-09-10接收，研究题号为C；题面原件在 `赛题：CUMCM2026Problems/C题/`，归档入口为 `paper/inputs/`。
- 本次研究区间为2025-02-01至2025-12-31，共334个评价日；2025年1月用于连续预测和储能状态预热。
- 题目包含四问：典型日确定性调度、日前预测与合同、日内信息更新、波动电价下的日前/日内比较。
- 统一对象是光伏、居民负荷、外网购电合同、紧急购电和储能状态；核心约束包括母线电量平衡、储能递推、容量上下界、充放电功率上下界、充放电互斥和跨日状态连续。
- 当前结果入口为 `paper/results/CURRENT.json`，当前主运行是 `paper/results/runs/c-study-20260911-v1.1/`。
- 当前论文主源为 `paper/latex/main.tex`，最终用户交付PDF为 `output/C题论文_v1.15-4.3精简图3随文.pdf`。
- 当前支撑材料提交包为 `output/C题支撑材料_20260913/C题支撑材料_提交用.zip`；完整本地归档为同目录的 `C题支撑材料_完整资料归档.zip`。
- “程序检查通过”与“人工审阅通过”“正式上传完成”在本项目中分开记录；人工审阅和正式上传状态不由自动脚本代填。

## 2. 可迁移的标准流程

下一届华为杯收到题面后，可以沿用以下顺序。每一步都要留下输入、输出、命令和状态。

1. 接收题面：保存原始题面和附件，登记接收时间、文件大小、来源和只读属性。
2. 先读规则：读取全国规则、当年AI使用规定、论文页数/文件大小限制和生效赛区通知；赛区未确定时不能混写地区规则。
3. 建立需求矩阵：把题面逐字要求拆成稳定ID，记录问题、输入、输出、表格、图件、附件和提交文件要求。
4. 建立事实入口：在 `CONTEXT.md` 中记录数据范围、单位、时间窗、术语口径、已确认参数和未决事项。
5. 建立研究方案：在 `IDEA.md` 中写每问的变量、目标、约束、算法、依赖、基线、退出条件和风险兜底。
6. 数据体检：检查表头、行列数、日期、单位、缺失值、重复值、时间对齐、数量级和可用的历史信息边界；清洗结果另写到 `paper/clean/`。
7. 先做最小模型：每问先实现一个可解释基线，验证数量级和可行性，再增加预测、反馈、风险余量或比较方案。
8. 建立求解器：把求解、预测、结果汇总、绘图和核验分开；代码只从相对路径或显式根目录读取输入。
9. 运行正式回放：记录运行ID、参数、数据范围、预热区间、评估区间、随机种子、求解器状态和输出文件。
10. 做独立验证：执行守恒、边界、连续性、账单复算、因果信息边界、小规模对拍和退化情形检查。
11. 建证据链：每个正文数字关联结果文件、代码、运行ID、图表、正文位置和验证文件；没有证据的主张保持待核验。
12. 生成图表：先由真实CSV生成图，再做视觉重制；保留源代码和可编辑源，检查坐标、图例、标注、置信带口径和正文引用。
13. 写论文：以唯一LaTeX主源为准，按题面顺序组织问题重述、模型准备、模型建立、求解、结果、检验和评价；图表放在对应文字后面。
14. 做PDF QA：编译、抽取文字、逐页渲染、检查空白、遮挡、断表、页码、字体、公式、超链接和附录起页。
15. 制作支撑材料：按题面模板导出完整Excel，放入程序、输入、结果、图源、AI使用详情和运行说明；不要只交截图或摘要表。
16. 从解压副本复验：解压ZIP后执行验证和必要的重算；检查路径安全、文件重复、文件大小、工作簿可打开和结果一致。
17. 人工终审与上传：由队伍人工检查论文和Excel，登记正式文件名、匿名性、签名、账号、平台和上传状态；工具不能虚报完成。

## 3. 本次已实际形成的核心项目资产

### 3.1 规则、题面与需求

- `README.md`：根目录交付入口、当前版本和历史阶段索引。
- `AGENTS.md`：本项目的事实、留档、建模、验证、写作和交付约定。
- `数学建模-AI全流程工作法-GPT6-Astra-Max-Ultra版.md`：从赛前准备到正式交付的总工作法。
- `config/competition.json`：年份、题号、时间、论文页数、文件大小和AI披露配置。
- `paper/REQ.md`：题面逐字需求和稳定ID。
- `paper/requirements.csv`：需求状态、来源和交付物映射。
- `paper/CONTEXT.md`：当前题面事实、数据口径、参数、结果和未决风险。
- `paper/IDEA.md`：统一调度模型、各问依赖、选定路线、增量和兜底。
- `paper/reviews/contest-input-review-20260910.md`：正式题面接收与输入审查。
- `references/official/`及`references/regions/`：官方规则和地区规则的分层存档；下一届使用时必须重新核对年份和适用赛区。

### 3.2 代码和运行入口

主要程序位于 `paper/code/`：

- `c_core.py`：储能、购电、母线平衡等核心模型组件。
- `c_forecast.py`：历史同槽均值、滞后信息和岭回归预测组件。
- `run_c_study.py`：全年研究回放主入口，可指定输出目录、评估日、路线和风险分位数。
- `validate_q1.py`：问题一结果及独立复核。
- `verify_c_study.py`：全年槽级物理约束和账单核验。
- `verify_c_study_extended.py`：扩展物理和跨日连续性检查。
- `verify_c_causality.py`：预测信息可见性和因果边界检查。
- `verify_workbooks.py`：五个Excel与结果运行的逐单元格核对。
- `run_c_sensitivity.py`：风险余量/分位数敏感性分析。
- `generate_answer_tables.py`、`build_required_result_tables.py`：正文结果表和题面必需表导出。
- `generate_real_figures.py`、`redesign_figures_v2.py`及各`plot_*.py`：真实数据图生成和重制。
- `build_v11_publication.py`：论文表格、结果宏、图表和LaTeX入口整合。
- `paper/support/support.py`：解压支撑材料后的`unpack`、`verify`、`export`和`reproduce`统一入口。

常用命令（下一届需先替换题面、输入路径、运行ID和参数）：

```bash
# 查看各程序参数
.venv/bin/python paper/code/run_c_study.py --help
.venv/bin/python paper/code/verify_c_study.py --help
.venv/bin/python paper/code/verify_workbooks.py --help

# 按显式输出目录运行正式回放
.venv/bin/python paper/code/run_c_study.py \
  --output-dir paper/results/runs/<run-id> \
  --protocol paper/reviews/<protocol>.json

# 核验指定运行
.venv/bin/python paper/code/verify_c_study.py \
  --output-dir paper/results/runs/<run-id> --eval-days <days>

# 核验工作簿与运行结果
.venv/bin/python paper/code/verify_workbooks.py \
  --result-dir paper/results/<workbooks> \
  --run-dir paper/results/runs/<run-id>

# 支撑材料解压后统一复验
python3 support.py verify
python3 support.py reproduce --output recomputed/main
```

### 3.3 结果和证据

- 选定路线文件：`paper/results/runs/c-study-20260911-v1.1/selected_routes.json`。
- 结果摘要和所有运行元数据：同一运行目录中的`study_summary.json`、`q1_summary.json`及各验证JSON。
- 逐时段、逐日、逐决策输出：`study_slots_*.csv`、`study_daily_*.csv`、`study_decisions_*.csv`。
- 结论证据表：`paper/evidence/claims.csv`。
- 图表证据表：`paper/evidence/figures.csv`。
- 题面必需表覆盖：`paper/evidence/required_table_coverage.csv`。
- 输入来源清单：`paper/evidence/input_manifest.jsonl`。
- 当前数值的权威入口：`paper/results/CURRENT.json`，不要从旧版PDF或聊天记录反抄数字。

本次选定主路线及结果口径为：

- 问题一：典型日线性规划，充放电效率均为0.9，初末储能均为6000 kWh。
- 问题二：`q2_fixed_ridge`，历史信息和岭回归负荷预测。
- 问题三：`q3_updates_frozen_pv_risk`，日内状态反馈、历史正残差风险余量和冻结零点光伏预报。
- 问题四日前方案：`q4_2_variable_risk`。
- 问题四日内方案：`q4_3_updates_frozen_pv_risk`。

这些路线和数字只属于本次C题数据与研究口径。下一届华为杯只能复用建模结构、证据方法和代码组织，不能复制参数、结果或结论。

### 3.4 论文、图表和排版资产

- 唯一正文源：`paper/latex/main.tex`及`paper/latex/sections/`。
- 当前论文PDF：`output/C题论文_v1.15-4.3精简图3随文.pdf`。
- 当前正文含参考文献29页，附录从第30页起；总页数48页。正文页数和附录规则要按下一届官方要求重新计算。
- 当前采用19幅图；正文图源在`paper/figures/`，可编辑图件在`paper/figures/ppt/`和`output/pptx/`。
- 图3采用用户提供的矢量工作流程图；图1和图4曾生成候选版并按用户选择接入正文；图18保留真实效率扫描、局部放大和能量传递小图。
- 图表重制遵循：真实数据先生成，颜色、字体、线宽、标注和局部放大再统一处理；任何不确定性带必须有真实统计量来源。
- 排版经验：图表在解释文字后出现；跨页表使用“续表”并重复表头；不能用强制分页掩盖大段空白；正文图表、表格和结果数字均需在证据表登记。

### 3.5 五个Excel和支撑包

本次题面要求的五个结果工作簿为：

```text
paper/results/result1.xlsx
paper/results/result2.xlsx
paper/results/result3.xlsx
paper/results/result4-2.xlsx
paper/results/result4-3.xlsx
```

已完成的支撑包包括：

- 五本Excel及题面模板对应工作表。
- 题面原始PDF和附件输入的必要副本及来源说明。
- 计算、验证、绘图和工作簿导出代码。
- 论文采用的图件和图表数据。
- `AI工具使用详情.pdf`、`支撑材料说明.pdf`和运行说明。
- 解压副本的工作簿、物理约束、账单和逐时段结果核验。

本次提交包核验记录见 `output/c-topic-support-work-20260913/final-verification.json`；完整归档不等同于下一届正式提交包，下一届必须根据新题面逐项重建。

## 4. 阶段审阅和版本控制经验

### 4.1 留档规则

每一次大编辑都在 `Each Stage Review Work/YYYYMMDD-NN-主题/` 中保存：

- 修改前完整文件或来源快照。
- 修改后完整文件。
- 差异文件和新增/删除文件登记。
- 编译、运行、核验命令及实际输出。
- 来源路径和文件清单。
- 待人工审阅项及人工状态。

阶段索引入口为 `Each Stage Review Work/README.md`。历史阶段不得覆盖，回退必须新建阶段并说明回退来源。

### 4.2 本次关键阶段链

- 正式题面接收与需求建立：2026-09-10至09-11。
- C题Idea V0.1、Pro材料V0.2和融合V1.0：2026-09-11，形成统一模型和四问路线。
- 第一轮正式研究回放：2026-09-11，覆盖334天、24条登记路线和五个结果工作簿。
- 范文式论文初稿和后续正文重写：第17阶段及之后。
- 结果证据入口和路线对账：第121阶段。
- 退回`dynamic-optimization`基线：第125阶段。
- 问题分析文字修订与摘要回退：第128至132阶段。
- 图内说明、分图标题和流程图修订：第133至140阶段。
- 4.3语言、表格续排、图件重制和正文版式：第137至158阶段。
- AI声明与全文表述清理：第139、141、159阶段。
- 五个工作簿、支撑材料、解压重算和逐值核验：第161阶段。
- 4.3压缩和图3随文排版：第162阶段。

阶段名称可能存在历史编号重复或不同日期命名；下届应使用单调递增序号和清楚主题，避免把历史候选误认成当前版本。

## 5. 本次验证得到的可复用检查项

### 数学与数据

- 每个时间槽都有完整负荷、光伏、价格和决策字段。
- 母线电量平衡逐槽复算。
- 储能状态递推逐槽复算，容量和功率边界检查。
- 充放电互斥和“紧急购电时不同时充电”检查。
- 跨日储能连续性检查，含1月至2月边界。
- 费用按普通购电、合同调整和紧急购电独立重算。
- 预测只使用当时可见的历史数据；不能把全年真实价格或未来光伏回填到日前预测。
- 小规模枚举、对偶/原始目标一致性和独立路径复核用于问题一。

### 文件与论文

- 五个Excel工作表、行列数、日期格式、空位和结果数值检查。
- 论文表格与正文数字、结果宏和CSV逐项对账。
- 图表源、图题、页码和正文引用检查。
- PDF编译退出码、页数、附录起页、空白页、Overfull盒子、文字抽取和重点页渲染检查。
- ZIP完整性、条目唯一性、路径安全、大小限制和解压后可运行性检查。
- `AI工具使用详情.pdf`在参考文献前或规则要求位置出现，并如实记录工具用途、提示词、采纳修改和人工核验。

自动PASS只证明对应程序检查通过，不能代替队员对模型含义、数字合理性、论文表达和正式提交文件的人工确认。

## 6. 下一届华为杯的启动模板

收到新题面后，建议复制本目录的结构和方法资产，重新建立一个新项目目录，并执行以下清单：

```text
README.md
AGENTS.md
config/competition.json
paper/
  REQ.md
  CONTEXT.md
  IDEA.md
  STATUS.md
  HANDOFF.md
  inputs/          # 原始题面，只读
  data/            # 原始数据，只读
  clean/           # 清洗结果
  code/            # 求解、验证、绘图
  results/         # 运行结果
  evidence/        # claims、figures、输入清单
  latex/           # 唯一正文源
Each Stage Review Work/
references/official/
references/problem_types/
practice/
output/
```

启动第一天必须完成：规则快照、题面逐字需求、数据体检、最小可行模型、验证命题和阶段留档目录。启动第一轮正式计算前必须确定：评价区间、预热方式、参数来源、随机种子、结果文件命名和失败兜底。准备提交前必须完成：全量结果核验、正文数字对账、五个或题面指定的Excel导出、PDF渲染检查、支撑包解压检查和人工终审登记。

## 7. 不可直接迁移的内容

- C题的负荷、光伏、电价数据和334天区间。
- 充放电效率0.9、容量12000 kWh、功率5000 kW、风险分位数0.8等参数。
- Q2至Q4的路线名称、费用、紧急购电量及论文结论。
- 2026年CUMCM规则、AI规定、文件大小和截止时间。
- 论文页数、图号、表号和当前LaTeX分页。
- 当前用户确认的服务器核验事实；下一届必须有新的实际记录。

下一届复用的是流程、文件边界、验证思想、证据链、图表制作方式和交付检查，不是本次C题的具体答案。

## 8. 交接入口

- 当前状态：`paper/STATUS.md`。
- 恢复信息：`paper/HANDOFF.md`。
- 当前结果：`paper/results/CURRENT.json`。
- 阶段索引：`Each Stage Review Work/README.md`。
- 当前提交用支撑包：`output/C题支撑材料_20260913/C题支撑材料_提交用.zip`。
- 当前完整归档：`output/C题支撑材料_20260913/C题支撑材料_完整资料归档.zip`。

本清单只总结文件中已经存在的流程和产物；下一届正式竞赛开始时，应重新读取当年规则并建立新的事实、需求、结果和审阅记录。
