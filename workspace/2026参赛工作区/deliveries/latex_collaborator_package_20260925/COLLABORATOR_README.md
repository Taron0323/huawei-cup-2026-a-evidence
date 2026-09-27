# 华为杯 2026 A 题 LaTeX 协作者编辑包

本包中的 `latex_draft_from_replica/` 已被登记为当前论文的主工作区。以后正文、摘要、图表、附表、支撑代码和 PDF 的改动均以这个目录为准；活动工作区的 `paper/latex_draft_from_replica` 是指向它的兼容软链接。正式阅读版为
`latex_draft_from_replica/output/main-2026.pdf`（74页，SHA-256：`78ba1eaf93e66f35aad762f233c06e39d7a91f5877ac253d47eb9baad74e388d`）。本版同步清理了三级标题和相邻过程式二级标题，正文模型、公式、图表和数值不变。本包保留源文件、图表、冻结数据、关键实验代码和可复现脚本，排除了 LaTeX 构建缓存、历史快照和 Python 字节码。

## 编辑入口

1. 进入 `latex_draft_from_replica/`，修改 `main-2026.tex`、`body.tex` 或 `sections/*.tex`。
2. 只修改正文后，在该目录执行：

   ```bash
   python3 build.py --only main-2026
   ```

3. 需要查看 PDF 时打开 `output/main-2026.pdf`。

## 摘要与图表

摘要的可编辑版本为 `frontmatter.docx`，TeX 侧内容为 `sections/abstract-prose.tex`。修改摘要后，先执行：

```bash
python3 scripts/update_abstract.py
```

然后用本机可用的 LibreOffice 将 `frontmatter.docx` 导出为同目录的 `frontmatter.pdf`，再执行：

```bash
python3 build.py --only main-2026
```

若修改了实验数据驱动的图表或附表，先执行：

```bash
python3 scripts/build_final_evidence.py
python3 build.py --only main-2026
```

摘要脚本读取的母版文件已放在包根目录的
`latex_d2025_style/frontmatter.docx`。请保留 `latex_draft_from_replica/` 和
`latex_d2025_style/` 这两个目录的兄弟关系。

## 环境

- Python 依赖见 `latex_draft_from_replica/requirements.txt`：`pypdf`、`numpy`、`matplotlib`、`lxml`。
- LaTeX 构建需要 XeLaTeX、`ctex` 和可用的中文字体。
- 摘要 Word 转 PDF 需要 LibreOffice；当前 macOS 字体配置保存在
  `latex_draft_from_replica/scripts/word-fonts-macos.conf`，其他系统需要按本机字体路径调整。
- `support/experiment/` 保存当前算法和官方评估器副本；论文中的结果不需要重新运行全量求解器即可重建图表和附表。

## 结果边界

- 当前论文使用 Final Idea v2 和 2026-09-24 冻结结果，不应恢复旧 V0.7.1 数字。
- 主结果由 CPU 上运行的题目官方 Python 事件模拟器得到；Apple MPS 只用于轻量候选负载排序。
- 结果对应已评价的有限候选方案，不能改写为 NPU 实机测量，也不能表述为全局最优证明。
- 该包是协作者编辑包，不是正式比赛提交包；队员人工科学审阅、最终定稿和平台提交仍需另行完成。

## 目录说明

- `sections/`：正文、摘要、参考文献、AI 使用说明和附录。
- `figures/`：正文引用的 PNG/PDF 图表。
- `generated/`：由冻结数据生成的附表和统计摘要。
- `data/audited_20260924/`、`data/final_idea_v2/`：结果核验数据副本。
- `support/experiment/`：作者代码、测试、官方评估器和实验支撑材料。
- `output/`：当前 PDF（含 `main-2026.pdf`、`main-overleaf.pdf` 和参考版）。
- `写作对照与验收.md`、`修改说明_20260925.md`：模板映射、验收记录和最近版式修改记录。
