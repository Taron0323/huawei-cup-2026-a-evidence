# 正式证据记录

当前CSV仅有表头，没有正式赛题、结论或人工核验记录。准备和演练证据在prep、review与practice中。

路径使用本工作区根目录相对路径。requirements的quote保存题面原句，source_page用原PDF页码。claims的result_row从CSV首个数据行算1，result_column写确切列名；run_id必须指向results下实际运行目录。数值tolerance显式填写。

运行目录保存run.json：phase、run_id、command、environment、inputs、code、outputs、verification；各文件清单条目包含path和sha256。科学检查保存verification.json，记录输入/代码/结果指纹、每项检查方法与误差。不得只写一个PASS。

human_review=PENDING是默认值；HUMAN_VERIFIED必须有真实成员的reviewer、reviewed_at与核验记录。输入、代码、参数或图表变化后重新判断受影响结论。

check工具检查文件引用、数值单元格、哈希绑定和状态，不验证数学推导正确性或人体签名真实性。空表输出NOT_ASSESSED，不产生正式通过结论。

