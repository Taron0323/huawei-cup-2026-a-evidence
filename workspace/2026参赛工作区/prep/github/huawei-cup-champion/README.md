# 华为杯数学建模skill

面向“华为杯”中国研究生数学建模竞赛的 Codex Skill，辅助建模取舍、实验验证、论文修改和数模之星答辩准备。

基于2024年数模之星冠军、亚军、季军与10篇提名论文的比较研究，共13篇、971个PDF页面。重点是把题目要求转成有领域含义、有可比证据、有具体输出的计算链。

## 安装

在尚未安装同名Skill的环境中运行：

```bash
git clone https://github.com/Taron0323/Huawei-Cup-Mathematical-Modeling-Skill.git ~/.codex/skills/huawei-cup-champion
```

随后新开一个Codex任务，通过 `$huawei-cup-champion` 调用。自动发现默认开启，实际加载以客户端显示为准。已经以Git方式安装的版本，可以在该目录运行 `git pull --ff-only` 更新；其他安装方式应保留本地自定义内容后再同步。

## 使用示例

```text
使用 $huawei-cup-champion，基于当前题面、模型和结果，找出最影响竞争力的三个问题，先完成最关键的一项改进与验证，再更新结论。沿用现有项目状态和目录。
```

```text
使用 $huawei-cup-champion，审查这份摘要和实验表。只修正口径、证据和表达，保留真实结果，不添加未执行的实验。
```

```text
使用 $huawei-cup-champion，根据已有论文准备数模之星答辩主线和证据索引，按当年官方答辩规则组织。
```

短请求直接完成。已有项目从当前瓶颈继续，没有正式赛题时用于准备或演练。可独立使用，也可与 `mathmodel-astra` 配合，由后者维护项目状态与文件管理。

## 文件

| 文件 | 内容 |
| --- | --- |
| [SKILL.md](SKILL.md) | 任务范围、建模决策与按需读取入口 |
| [2024-patterns.md](references/2024-patterns.md) | 历史样本、页码证据和可迁移经验 |
| [execution.md](references/execution.md) | 比较协议、题型验证、取舍与停止规则 |
| [paper-and-defense.md](references/paper-and-defense.md) | 摘要、正文、图表、一致性与答辩 |
| [openai.yaml](agents/openai.yaml) | 显示名称、默认提示和自动发现设置 |

## 研究边界

- 历史指标均为原作者报告，未重跑原始作者实验。获奖身份不证明每项实验都可靠。
- 三项全样本共性是跨问衔接、实际候选/前后对照、具体输出；它们表示结构存在，不等于比较公平或结论正确。
- 本Skill不提供官方评分权重、分数线或获奖概率，也不保证冠军。赛事格式、AI使用和答辩要求以当年官方原件为准。
- 论文PDF和正式参赛数据不随Skill分发；源案例按论文ID与PDF物理页码定位。奖项依据见[2024官方最终名单](https://cpipc.acge.org.cn/sysFile/downFile.do?fileId=fe3fbf1ace87488c9d97c8d88260aa39)。

## 已做的验证

Skill格式与内部引用已检查。三项独立前向行为案例覆盖不同单位/拆分的指标比较、无偏好信息的多目标最优表述，以及仅要一段短建议的范围控制。案例通过不代表真实比赛效果，也不代表所有客户端已自动发现本Skill。
