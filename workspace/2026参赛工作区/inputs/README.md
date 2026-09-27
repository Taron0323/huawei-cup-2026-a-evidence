# 正式输入

problem放题面与赛题说明，raw放原始数据及原始压缩包。A题DOCX、原始ZIP及解压材料共116份已登记到manifest.json。A-F完整来源目录保持不动；未选题只保留审查资料。登记命令为python3 tools/workspace.py register；登记不会修改原文件，发现已有文件哈希变化会拒绝覆盖旧记录。清洗写data/processed。运行评估器须禁用字节码并显式指定results输出，不得向inputs写运行结果。
