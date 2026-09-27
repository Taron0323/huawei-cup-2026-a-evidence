# 报告 PDF 排版核验

本次核验对应源 Markdown SHA-256：`dccd1aeb6b7e0a7610133e169cb32e4cf711df2b6935f59441265b04ce5a26ec`。

报告 PDF SHA-256：`93063aff3a7883b1bbf2ab789fd02272e1569b6aa3601f2a05ad6d87f645e608`。

- 共 9 页、6 张表；304 个结构化正文单元全部能够在 PDF 提取文本中找到，没有缺失文字。
- 简体中文字体使用 STHeiti Light/Medium 字体集的简体子字体，6 个实际使用的字体子集均已嵌入，提取的字体文件非空；Helvetica 为未使用的 PDF 基础字体资源。
- 所有正文字符均在两种字体中有对应字形，没有缺字或乱码占位字符。
- 逐页检查文本范围，没有文字越出排版左右边界或页面边界。
- 9 页全部以 PyMuPDF 渲染为 PNG；最终修改后重新检查全部 contact sheet，以及有修改的第 8、9 页大图；排版阶段另放大检查第 1、5、8 页的中文、表格、引用和字体。
- 表格跨页重复表头，行内容完整；分级标题、页眉、总页数和每页页码可读。
- 首轮检测到中文标点悬挂造成轻微右界超出，已通过正文留出标点空间修复；没有通过放宽检查阈值绕过。
- 已修复 CommonMark 中文标点边界导致的加粗星号直出，采用 markdown-it-py 的内联规则扩展；不修改源 Markdown。
- 公开仓库链接已出现在 PDF 的实际超链接注释中：`https://github.com/Taron0323/Huawei-Cup-Mathematical-Modeling-Skill`；目录书签共 29 项。

重复构建命令（研究目录内）：

```bash
uv run --with reportlab --with markdown-it-py --with pymupdf --with pillow python scripts/render_report.py
```

脚本会重新生成 PDF、逐页图像、contact sheet 和 `verification.json`。每次重建后的视觉状态会重置为 pending，须根据该次新图检查后再更新；本文件只适用于上方哈希的版本。
