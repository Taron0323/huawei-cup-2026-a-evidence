# Final Idea 实验与论文结果重建

本稿采用冻结工作区 2026华为杯idea冻结工作区/实验数据/ 的两个最终报告目录：main_reports_20260924_v2/ 和 sensitivity_20260924_v2/report/。工程内 data/final_idea_v2/ 保存其最终 CSV、报告 manifest 和最终核验文件。旧版 V0.7.1 的结果没有参与本稿计算。

作者程序位于 experiment/src/huawei_code/，运行及报告脚本位于 experiment/scripts/，官方评估器副本位于 experiment/vendor/。experiment/A题_Final_idea_给codex运行.md 的 SHA-256 为 ad20b0248789b58a9e4d5e96c224d105c9672912d43a98301b66ac3b2d29ad72，与实验 manifest 相同。原始100张计算图、配置以及9.4 GB运行细节仍在相邻 华为杯_code/data/raw/A题/data/ 与 华为杯_code/results/，以冻结 manifest 追踪；论文工程不复制这些大文件。

从论文工程目录依次执行：

    python scripts/build_final_evidence.py
    python scripts/update_abstract.py
    python build.py

第一步只读取保存的 CSV，逐组核对100图、1500个唯一组合、500个B/C计划哈希、三段比值乘积及24组敏感性结果，生成图表与完整附录，不重新运行求解器。第二步更新可编辑 Word 和 TeX 摘要；必须将 Word 导出为 frontmatter.pdf 后，第三步才会更新正式 PDF。封面及两个摘要页保留官方母版图标和空白队伍字段。

全量主矩阵各图各核各问最多比较两份官方完整评价候选；A/B由独立四起点生成，C从同图同核的B最终计划开始。Apple MPS仅参与候选负载向量排序；官方核内展开与事件模拟在CPU Python执行。1500个最终结果标记为 AI_VERIFIED，2828份候选官方结果检查通过，程序单元测试为3项通过。六图四变体的24个固定计划均成功；48个重优化候选中36成功、12个依赖环失败，所有组的最终方案均与固定起点相同。

以上是程序输出和记录一致性证据。结果限于有限候选和题设模拟器，未证明全局最优，也不是NPU实机测量。队员人工核验、AI工具精确信息和实际平台提交由队伍另行完成。
