# 赛前环境复查

读取 common.md、PREP_STATUS.md 和 prep/astra/validation-report.md，按当前任务核验环境。运行 `.venv/bin/python tools/preflight.py` 核对环境、22 个阶段的 Max／Ultra 组合、演练文件哈希、模板、技能安装和最新本地快照。工具或测试源码变化时才加 `--run-tests` 更新针对性验收。工具不会启动模型推理；能力列表确有变化时再用 `tools/codex_probe.py` 核验模型与技能发现。

先检查 practice/astra-skill-validation 中的演练证据与代码、输入哈希；未变化且检查仍覆盖当前目的时复用。需要重验时使用已安装 mathmodel-astra 的 scripts/verify_runtime.py，在 practice 下新目录运行，覆盖数据、求解、CSV、图表、短文、证据及中断恢复。随机性检查按题型判适用，不能给确定性例子凑随机实验。模板编译、Word 镜像和正式打包是否完成分别记录，不从运输演练推断。

重新读取官方入口的近期规则变更，保留访问日期和来源。赛题未发布时不尝试搜索预测答案。账号、报名、队内角色、赛区特别要求按实际获得的信息记录，不冒充已确认。

更新准备验收报告，列出具体通过证据和真正未完成项。准备就绪只表示工具与流程可启动。

工作台损坏恢复另用 `tools/backup.py`；总检通过不等于已有异地副本。用户模板审核、有效报名截止、账号和 Windows 提交客户端等人工事项保留真实状态，具体清单见 `prep/team_checklist.md`。
