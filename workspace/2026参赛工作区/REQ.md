# 项目需求与验收

本轮写作验收已完成：指定D母版迁移、真实数字与附录、Word摘要同步、三个PDF入口及便携复现包；逐项证据见`paper/latex_draft_from_replica/写作对照与验收.md`。全部测试用例要求仍有5个大图未完成，不将写作完成视为全量科学实验完成。

当前已选A题。正式逐问原文在`evidence/requirements.csv`，V0.7.1模型与结果边界见`paper/latex_draft_from_replica/`、`review/v071_result_audit_20260924.md`和`review/v071_implementation_audit_20260924.md`。下表保留此前准备验收，不替代正式赛题需求。

正式验收：在当前95个完整case口径下，统计问题1、2、3的1至5核平均加速比、各用例Makespan、额外搬运和问题3 Cache配对；另外5个大图只登记profile并保持`PENDING/NOT_ASSESSED`。V0.7.1运行500个case-core单元，候选13,127行，选中1,425行，失败候选0；证据表、审计、六幅图、36页V0.1重写稿和post-run provenance已登记。`global_optimality=NOT_PROVEN`、`scientific_validation=NOT_ASSESSED`、`human_review=NOT_ASSESSED`、`submission=NOT_SUBMITTED`均保持原状态。

| ID | 需求 | 验收证据 |
| --- | --- | --- |
| PREP-01 | 审查所有原有资料并保留修改 | 初始与最终原件哈希对照、ZIP对照、审查报告 |
| PREP-02 | 获取当前官方资料与更新 | official/20260921来源、覆盖、下载校验记录 |
| PREP-03 | 建立可执行比赛工作区 | 目录职责、当前提示词、路径检查、空正式证据表 |
| PREP-04 | 补齐Word和LaTeX模板 | 实际文件、编译日志、逐页渲染、官方封面与摘要 |
| PREP-05 | 提供可验证工具 | 输入哈希、证据引用、冻结后篡改拒绝、环境检查 |
| PREP-06 | 演练端到端流程 | 合成运输求解与独立枚举一致、图表和演练报告 |
| PREP-07 | 核对比赛操作准备 | 清单覆盖个人信息、账号、MD5、附件与备份 |
| PREP-08 | 交付可浏览和便携包 | 文件清单、ZIP完整性、全新解压复跑 |

上表只表示历史准备项。真实题面接收和本轮模型结果已由正式输入及运行记录证明；报名/缴费、人工复核和上传不能靠程序验收置为完成。
