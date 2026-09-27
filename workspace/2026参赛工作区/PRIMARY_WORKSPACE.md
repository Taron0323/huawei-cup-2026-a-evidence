# 当前主工作区

自 2026-09-25 起，华为杯 2026 A 题论文的唯一真实编辑源为：

`/Users/futaoran/Desktop/华为杯2026/2026参赛工作区/deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/`

以后论文正文、摘要、图表、附表、代码节选、PDF 编译和结果驱动的论文更新，都以这个目录为准。`paper/latex_draft_from_replica` 是指向该目录的兼容软链接；从两个入口打开或编译，修改的都是同一份文件。

当前正式阅读版：

`deliveries/latex_collaborator_package_20260925/latex_draft_from_replica/output/main-2026.pdf`

原先的完整工程已完整移入：

`archive/latex_draft_from_replica_before_collaborator_main_20260925/`

该归档只用于追溯，不作为后续编辑来源。`paper/latex_d2025_style/` 仍是只读母版。日期命名的 ZIP 是交给合作者的快照；后续主工作区发生修改后，如需再次交付，应重新生成 ZIP。

从活动工作区根目录编译：

```bash
.venv/bin/python paper/latex_draft_from_replica/build.py --only main-2026
```

从主工作区目录编译：

```bash
python3 build.py --only main-2026
```
