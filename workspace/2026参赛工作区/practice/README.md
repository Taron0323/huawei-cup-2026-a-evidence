# 合成演练

transport是2个供给点、3个需求点的合成运输问题，数据不是官方赛题。使用SciPy/HiGHS线性规划求解，另用整数枚举独立核对。运输约束矩阵的整数性使本例的整数枚举可核验线性规划最优值；不能把这一性质任意套用到其他模型。

运行 `.venv/bin/python practice/transport/run.py --run-id rehearsal-02`。结果写入transport/runs的新目录，旧目录不覆盖。每次生成CSV、验证JSON、运行清单、图表和可编译的演练报告PDF。运行必须有SciPy、NumPy、Matplotlib、XeLaTeX。

AI辅助编程来源见prep/ai_preparation.json；精确模型版本与发布日期未核验。本演练不作为正式提交代码或正式披露记录。
