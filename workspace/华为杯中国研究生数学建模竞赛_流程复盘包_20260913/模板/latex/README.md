# 数学建模 LaTeX 模板

模板以用户指定的 `2024数模国赛C 题-猫猫范文.pdf` 为主要字体与版式参考。当前为 **v3 待用户审核**，尚未冻结。格式学习不代表已验证范文的获奖身份、公式或代码。

## 使用入口

- `main.tex`：可直接填写的论文骨架，正文按 `sections/` 分文件组织。
- `demo.tex`：带真实可核对的小算例的样式演示，不是赛题结果。
- `mathmodel.sty`：统一导言区；通常只需编辑各节正文。
- `build/main.pdf`：骨架预览；`build/demo.pdf`：样式预览。
- 交付 ZIP 内的现成预览位于 `preview/`；`STYLE_REVIEW.md` 列出字体对照与待审核项。
- 正式项目已部署到根目录的 `paper/latex/`，以该目录作为唯一正文主源。

在此目录执行 `latexmk main.tex` 或 `latexmk demo.tex`。也可在工作台根目录运行：

```sh
.venv/bin/python tools/build_paper.py
.venv/bin/python tools/build_paper.py templates/latex/demo.tex
```

编译器选择 **XeLaTeX**。Overleaf 上传本目录源码后，在菜单中选择 XeLaTeX，并将 `main.tex` 或 `demo.tex` 设为主文档。演示图已包含，正常编译无须先安装 Python。

## 仿照的格式

猫猫范文：宋体正文、宋体加粗题名、黑体居中的一级标题、楷体二级标题、宋体加粗三级标题，阿拉伯数字层级 `1.`、`1.1.`、`1.1.1.`。采用它的三线表、楷体图题表题、居中页码和连续正文组织。保留适量重点加粗，不照搬编号错位、跨题文字或所有装饰图。

其他范文只用于参考建模表达和章节组织。研赛 C 的身份页、两页摘要、目录和正文篇幅不迁移到当前国赛模板。

## 具体排版

A4，四边 25 mm；正文宋体 12 pt，基本行距 15.6 pt；摘要正文行距约 17.15 pt；题名宋体加粗 16 pt；一级黑体 14 pt 居中；二级楷体 14 pt 左对齐；三级宋体加粗 12 pt 左对齐；图表标题楷体 12 pt；段首缩进两字。数字和英文使用 Times New Roman，公式统一使用 Latin Modern Math（Computer Modern 的标准 LaTeX 数学字体）。这里的 pt 按 PDF 点计，TeX 中用 `bp` 明确指定。这些参数根据参考 PDF 的字体与字符坐标提取；标题间距做了少量统一。

本机直接读取已安装 Word 中的 SimSun、SimHei、KaiTi，以及系统的 Times New Roman，没有修改系统字体。模板不会打包分发这些专有字体。`fonts.tex` 优先检测模板自有 `fonts/`、本机 Word、系统字体；数学公式始终使用开源的 Latin Modern Math，中文字体缺少时回退到 Fandol、数字英文回退到 TeX Gyre Termes。Overleaf 上预期可用 XeLaTeX 编译；中文回退版字形与参考有差异。自备字体时文件名按 `fonts.tex` 指定的大小写命名。

如需在不同电脑上统一使用开源替代字体，将主文件中的 `\usepackage{mathmodel}` 改为 `\usepackage[portablefonts]{mathmodel}`。该选项强制使用 Fandol、TeX Gyre Termes 和 Latin Modern Math，便于复现。此模式在本机 XeLaTeX 环境检查；未登录 Overleaf 做云端实测。

字号、行距属于对范文的仿照选择，2026 全国格式规范没有统一要求这些项目；赛区另有要求时优先按赛区调整。摘要页码按 2026 官方要求从 1 开始，与参考论文正文才从 1 开始的做法不同。

表题在上、图题在下，页脚中央连续页码，不设装饰页眉。公式使用 `equation`、`aligned` 和 `\eqref`，图表使用 `\label`、`\ref`，文献用 `\cite`；正文用 `[htbp]` 浮动，避免把所有图强行固定而造成大块空白。TikZ 技术路线中的文字、框和箭头均可编辑。

## 填写与交付

题目未到，所有 `\placeholder{...}` 都是有意保留的待办。按实际问题数量增删 `04_models.tex` 的小节。`demo.tex` 的算例与数字仅用于检查版式，不能移入正式结果。

摘要含题目和关键词占一页。当前电子版无承诺页、编号页和目录；正文不超过 30 页，附录页数不限。AI 声明位于参考文献之前，支撑材料使用准确文件名 `AI工具使用详情.pdf`。这些要求已按 `references/official/` 中 2026 规则核对。

完整源代码可用 `\lstinputlisting` 插入。中文注释较多的代码需要检查字符显示；不得用代码截图替代可运行源文件。文献条目采用手工顺序编码，填写真实来源并在正文引用。本模板不依赖 `cumcmthesis` 或外部 Python 执行，因此无需 shell-escape。

提交前删除全部待填写内容，修改 PDF 题名，逐页审查，核对页数、匿名、声明、正文与结果证据。可编译不等于可提交。纸质承诺书等按比赛系统提供的当年原件另行处理。
