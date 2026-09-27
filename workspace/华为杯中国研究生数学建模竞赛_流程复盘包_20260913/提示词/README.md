# 提示词入口

在 Codex 中以项目根目录为工作目录。日常推进选择 GPT-6 Astra 的 Max 档，关键建模和最终审查选择 Ultra 档。档位来自客户端设置，不来自提示词文字。

最省操作的入口是 `00_controller.md`：直接让 Codex 读取并执行它。已有明确任务时使用下表。每条阶段提示词均与 `common.md` 和相应 `modes/` 一起读取。`tools/start_astra.py --stage 0 --effort max --dry-run` 可查看组合和启动参数，`--print` 输出完整提示词，`--launch` 才实际启动 CLI 任务。Python 命令使用 `.venv/bin/python`；桌面客户端内的模型与档位仍由客户端设置。

| 阶段 | 文件 | 建议档位 | 完成标志 |
| --- | --- | --- | --- |
| 总控与自动续接 | 00_controller.md | Max | 找到实际阶段并完成下一项可执行任务 |
| 题面接收与需求抽取 | 01_intake.md | Max | 题面、哈希、REQ、数据事实清单 |
| 选题 | 02_selection.md | Max，关键分歧用 Ultra | 同口径可行性表与推荐理由 |
| 数据体检与清洗方案 | 03_data_audit.md | Max | 全文件体检、异常解释、处理记录 |
| 文献与评阅逆向 | 04_research.md | Max | 可核对来源及明确标记的内部自查项 |
| 数学抽象与候选路线 | 05_routes.md | Ultra | 不同数学结构、最小试跑、退出条件 |
| 建模决策审查 | 06_idea.md | Ultra | IDEA、关键决策、参数与风险清单 |
| 论文框架与图表 | 07_outline.md | Max | 各章节论证任务、图表证据映射 |
| 基线与逐问实现 | 08_implementation.md | Max | 程序、CSV、运行元数据与小算例 |
| 正确性六关 | 09_verification.md | Max，异常用 Ultra | 实际核验记录与问题清单 |
| 灵敏度与对比实验 | 10_experiments.md | Max | 预登记实验、独立重复、完整结果 |
| 统计图与路线图 | 11_figures.md | Max | 可复现矢量图和可编辑路线图 |
| 正文写作 | 12_writing.md | Max | 按证据完成 LaTeX 正文并编译 |
| 摘要专项 | 13_abstract.md | Max | 合适结构、保义表达、逐句证据对账 |
| 多视角评审 | 14_review.md | Ultra | 真实缺陷、优先级和修复验收 |
| 一致性与语言终检 | 15_consistency.md | Max | 数字、符号、引用、需求逐项检查 |
| 文献核验 | 16_references.md | Max | 存在性、元数据与语义支持记录 |
| 正式交付准备 | 17_delivery.md | Max，核心科学审查用 Ultra | 论文、支撑材料、AI 详情、检查报告 |
| 中断续接 | 18_resume.md | Max | 核实文件和活跃进程后继续 |
| 卡住与止损 | 19_recovery.md | Max，数学或证据冲突用 Ultra | 定位失败、限定预算修复或切换兜底 |
| 赛前再检查 | 20_preflight.md | Max | 当前机器的环境、模板、备份通过 |
| 新增范文学习 | 21_learn_examples.md | Max | 逐页学习笔记、来源哈希与可迁移写法更新 |
| C题人工意见修订 | goal-c-topic-v1.1-human-review-revision.md | Max，关键图表/数学冲突用 Ultra | 摘要、章节、图表、表格、实验、文献和 PDF 按最新人工意见完成并留档 |

`reviews/` 提供四种审查视角。若有独立任务／子代理工具且用户授权，可分配隔离评审；否则依次执行并如实标注同模型同会话局限，不能声称实现了多模型独立验证。
