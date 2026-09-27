# 冻结与提交

本目录当前没有正式作品。所有平台动作由队长执行并保留实际回执。

1. 完成真实封面、匿名、题目输出、科学验证、AI标注及队员复核，导出最终PDF。
2. 执行：`python3 tools/workspace.py freeze --pdf 实际PDF路径 --problem A --team 实际队号 --tag final-v1`。工具复制到submission/frozen/final-v1，记录MD5、SHA-256及字节数，并将副本设为只读。题号必须是实际选题。
3. 执行：`python3 tools/workspace.py verify-freeze submission/frozen/final-v1`。本地校验只证明字节一致，不等于已使用官方指定工具或已提交。
4. 使用官方指定工具读取同一PDF，人工核对哈希及题号，再在指定窗口提交MD5并保存回执。
5. PDF上传窗口仍上传冻结副本，点击提交并检查平台确认；不要重新导出PDF或更新PDF属性。
6. 附件按具体题目和系统规则准备、检查匿名与容量；当前.pdf/.rar表述差异见CONTEXT，不能自行用ZIP替代。
7. 回执可保存本目录private-receipts，公开打包排除该目录。状态由队长依据实际回执更新。

准备工具没有自动上传、登录、缴费或发信功能。失误修订只能生成新的冻结版本，旧证据保留；已提交MD5后不能私自换用新PDF。

