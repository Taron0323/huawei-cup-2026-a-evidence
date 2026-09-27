# 本地 Skill 清点

日期：2026-09-24

## 清点结果

已检查本机两个本地 Skill 根目录：

- `/Users/futaoran/.codex/skills/`
- `/Users/futaoran/.agents/skills/`

共发现 32 个可读 `SKILL.md`，均有可读文件和唯一 Skill 名称。完整路径、文件可读性和当前 SHA-256 已在本次工作区检查中核对；其中系统 Skill 也纳入清点，但不因存在而改变项目门禁。

清单：

`aaai-paper-coach`、`codex-ppt`、`cvm-paper-revision`、`hatch-pet`、`huawei-cup-champion`、`iclr-paper-coach`、`modelviz-skill`、`write`、`ccf-common`、`ccf-experiment-designer`、`ccf-humanization`、`ccf-idea-optimizer`、`ccf-idea-reviewer`、`ccf-integrity-auditor`、`ccf-literature-monitor`、`ccf-literature-searcher`、`ccf-paper-reviewer`、`ccf-paper-to-exemplar`、`ccf-paper-writer`、`ccf-pipeline-orchestrator`、`ccf-project-scaffolder`、`ccf-rebuttal-writer`、`ccf-skill-forger`、`ccf-submission-checker`、`ccf-visual-composer`、`mathmodel-astra`、`imagegen`、`openai-docs`、`plugin-creator`、`review-agent`、`skill-creator`、`skill-installer`。

## 本任务适用路由

- `mathmodel-astra`：管理数学建模项目阶段、输入/结果/验证/交付边界；当前只进入准备阶段。
- `huawei-cup-champion`：提供华为杯建模与论文的证据边界；当前不启动论文或实验。
- `ccf-common`：共享路由、证据、私有材料和产物边界。
- `ccf-paper-writer`：未来确需写作时使用；本阶段不调用。
- `ccf-humanization`：未来已有正文且需要去防御性时使用；本阶段不调用。
- `ccf-integrity-auditor`：未来检查数字、术语和引用时使用；本阶段不调用。
- `ccf-experiment-designer`：未来设计实验证据时使用；本阶段不调用。
- `ccf-paper-reviewer`：未来审稿或版本评估时使用；本阶段不调用。
- `ccf-visual-composer`：未来绘图或表格视觉工作时使用；本阶段不调用。
- `ccf-submission-checker`：未来正式格式与提交包检查时使用；本阶段不调用。

系统 Skill `imagegen`、`openai-docs`、`plugin-creator`、`review-agent`、`skill-creator`、`skill-installer` 已完成存在性与可读性清点；本轮不需要生成图片、查询产品文档、创建插件、安装或修改 Skill。

## 不适用路由

AAAI/ICLR/CVM 论文教练、PPT、宠物、通用写作、ModelViz 等 Skill 与本次冻结准备无直接交付关系，不作为本阶段前置条件。它们的存在不改变当前项目 AGENTS.md 和用户的准备阶段门禁。

## 本阶段结论

Skill 环境就绪。接收 Idea 和提示词后，先做原件登记、版本冲突核对和 canonical 冻结；在用户明确解除门禁前，不创建初稿内容、不运行求解器、不生成图表或结果。
