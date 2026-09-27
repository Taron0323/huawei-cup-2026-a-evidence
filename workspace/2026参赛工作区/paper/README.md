# A题当前论文

唯一当前稿：[A题论文V0.1_试验稿_20260924.pdf](A题论文V0.1_试验稿_20260924.pdf)。本轮按2024冠军论文的论证功能重写，不以历史范文的实验和结论替代当前证据。

源稿入口为[latex/main.tex](latex/main.tex)，章节分别为`sections/problem_model.tex`、`sections/questions.tex`、`sections/validation_evaluation.tex`、`sections/appendices.tex`。摘要为`frontmatter_v071.tex`，封面使用原有`official-cover.pdf`。当前共36页。

从活动工作区执行：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/build_v071_writing_evidence.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/build_v071_appendices.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/build_v071_paper.py
```

前两条从既有CSV重建结果表，第三条编译摘要、正文并更新当前PDF，不调用求解器。

数值对应`results/v071_full_20260924_v2/`及同名`_analysis/`。95个完整图用于统计，另外5个大图动态结果缺失。统一加速比基准为各图在问题一选中的单核方案，50例整图单Task、45例含2至5个Task；Cache配对固定问题三最终计划，两侧分别使用有/无L2评估。

完整表保留1425份三问结果及475组Cache配对，额外搬运以字节给出。检验记录见`review/v071_writing_evidence.json`，本轮交付说明见`review/v071_exemplar_rewrite_delivery.md`。队伍身份字段留空，人工核验与提交尚未完成。

9月24日先前P0/P1稿和旧编译预览已移出活动目录，保存在本轮阶段记录中；9月23日已撤销稿不恢复。历史模板、用户提供的优秀论文及原始计算数据保留原用途。
