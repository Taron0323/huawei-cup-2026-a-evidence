# 图3替换为用户提供的v9矢量PDF

本阶段直接使用用户指定的`/Users/futaoran/Desktop/申请/组织结构图-可编辑重建-v9.pdf`。原文件完整复制到`paper/figures/v1.2-visual-redesign/workflow-user-vector-v9.pdf`，未重新绘图、转图或栅格化。

## 修改

- `paper/latex/sections/04_preparation.tex`仅替换图3的`includegraphics`文件名；宽度仍为`\textwidth`，图题、标签、浮动设置及全部正文保持原样。
- `paper/evidence/figures.csv`只更新`fig:workflow`已有记录的原始来源、输出文件和来源状态，清空已不适用的旧转换脚本。
- 新增原文件的项目内副本。原活动图`workflow-user-reference-original.pdf`保留。

## 检查结果

- PDF共1页，页面大小为1768.5×841.5 pt，MediaBox与CropBox一致。
- PDF没有图片对象；包含文本、填充路径和线段，其中有255次文本绘制、1010个直线段，确认为矢量内容。
- 中文字体`HYShuSongErKW`及英文数字字体`TimesNewRomanPSMT`均已嵌入。
- 项目内PDF与用户原文件字节完全一致。
- 独立比较TeX前后文件，唯一变化是图3路径。
- 以95 dpi渲染全页并进行视觉检查，图框、箭头、文字均完整，没有页面边缘裁切。2334×1111像素预览的有效内容距四边分别为72、72、73、72像素。

## 验证命令

```bash
.venv/bin/python 'Each Stage Review Work/20260913-156-c-topic-workflow-vector-v9/archive.py' before
/Users/futaoran/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 'Each Stage Review Work/20260913-156-c-topic-workflow-vector-v9/verify_vector.py'
pdftoppm -f 1 -singlefile -r 95 -png 'paper/figures/v1.2-visual-redesign/workflow-user-vector-v9.pdf' 'Each Stage Review Work/20260913-156-c-topic-workflow-vector-v9/evidence/workflow-v9-preview'
.venv/bin/python 'Each Stage Review Work/20260913-156-c-topic-workflow-vector-v9/archive.py' after
```

以上四条实际执行成功，矢量核验结果为`PASS`，before与after快照均已生成。独立核验细节见`evidence/vector-verification.json`，预览见`evidence/workflow-v9-preview.png`。`before/`、`after/`保存完整相关文件；`diff.patch`保存文字差异；源文件记录在`evidence/before-sources.json`与`evidence/after-sources.json`。

本阶段未编译主论文、修改全局状态或改动模型结果。主任务合并其余正在进行的修改后统一编译并核对论文中的图3。人工审阅状态为`PENDING`。
