# AI 工具使用详情模板

`AI工具使用详情.pdf` 是一页赛前填写模板，明确标记没有正式比赛记录。正式日志位于 `paper/evidence/ai_usage.csv`，目前只有表头。不要把准备、演练或虚构的人工审核填进正式比赛记录。

记录每次有实质采纳的使用，也保留与关键建模有关但最终未采纳的输出。提示与过程说明单独保存为 UTF-8 文本，由 `prompt_file` 指向；使用的是典型交互时在该文件中如实说明范围。多个输出或核验文件在 CSV 单元格内用英文分号分隔，路径相对于 `paper/`。

主要字段含工具、版本或型号、时间、阶段、实际用途、提示文件、输出文件、采纳内容、人工修改、核验证据、内部审核人、审核日期与状态。工具不是大语言模型时，`model` 写实际版本，`effort` 可留空。审核人只在队内 CSV 保存，导出的 PDF 不显示其姓名；输出正文仍须检查是否包含身份信息。

状态可先记 `PENDING`。确已由队员核验后，填写真实记录并改为 `HUMAN_REVIEWED`。仅用于语言润色时可用 `LANGUAGE_ONLY`，同时 `purpose` 必须准确填写“语言润色”；不能把建模、代码或数据处理记成这一类以跳过审核。

在项目根目录使用文档运行环境导出：

```sh
.venv/bin/python tools/export_ai_usage.py
```

默认输出为 `paper/support/AI工具使用详情.pdf` 和同名 `AI工具使用详情.record.json`。后者记录来源 CSV、引用文件与 PDF 的哈希，供交付工具检查是否过期。记录尚有缺项时仍可生成队内核对稿，但 `complete_for_submission` 为 `false`，正式交付检查不会将其放行。空记录则直接拒绝普通导出。

程序不会覆盖已有导出。记录更新后，先保留旧版，再用新目录导出：

```sh
"$MM_DOC_PY" tools/export_ai_usage.py --output 'paper/support/ai-v2/AI工具使用详情.pdf'
```

在 `paper/submission.json` 的 `support_files` 中改用新版 PDF 与 `record.json` 的路径。最终文件名保持 `AI工具使用详情.pdf`。导出后逐页检查，不能仅凭字段和哈希检查认定人工核验或论文提交已经完成。

生成准备模板用 `--template`，且要求记录表为空。更换电脑后先通过工作区依赖工具定位文档 Python；脚本需要 `reportlab`，可用 `--font-dir` 指向有合法使用权的宋体、黑体字体目录。本机使用已安装 Word 的字体，没有复制或安装系统字体。
