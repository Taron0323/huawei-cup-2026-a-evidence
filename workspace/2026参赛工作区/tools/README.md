# 工具入口

| 工具 | 实际用途 |
| --- | --- |
| workspace.py env/register/check | 环境、原始输入登记、来源与正式证据引用检查 |
| workspace.py freeze/verify-freeze | 保存和验证最终PDF确切字节；不上传、不改写平台状态 |
| build_paper.py cover/latex | 官方封面与摘要导入、LaTeX正文编译、合并和渲染 |
| check_submission.py | 论文占位、已知身份、支撑清单检查；不替代人工审阅 |
| test_workflow.py | 对原件变更、数字不符、旧代码和冻结文件篡改的回归检查 |
| verify_preparation.py | 本次准备验收证据，依赖保留在父目录的历史资料 |
| package_workspace.py | 准备ZIP、全文件哈希校验、同机全新解压复跑 |
| audit_existing.py | 本次历史盘点；会如实报旧清单的两字节差异，不应强行改旧包让它通过 |
| prepare_word_template.py、set_title_style.py | 本次模板初始化的一次性变更，已有快照时拒绝重跑，避免覆盖后续论文 |
| package_a_author.py | 冻结后审计100图×5核×3场景及100条A0基线；仅完整通过才生成作者复现ZIP |

前三类是比赛期间的日常入口；初始化与历史盘点不属于正式求解流程。官方采集器位于official快照的采集记录中，已有来源清单时拒绝覆盖；更新资料须复制采集器到新日期目录后获取。

package_workspace.py示例：`.venv/bin/python tools/package_workspace.py ../华为杯2026准备包_新版本.zip`。同名ZIP存在时选择新版本名。prep/team.local.json、private-receipts、虚拟环境、缓存及build目录不进入准备包。输出相邻的.verification.json记录ZIP哈希和解压验证结果。

`package_a_author.py`在正式主矩阵、A0基线和同版本1500行报告均完成后使用。`--source-root`指向该次运行的冻结求解工程，`--run-root`指向已完成的主矩阵，`--baseline-root`指向已完成的A0运行，`--evaluator-dir`指向运行实际使用的评估器目录，`--official-workspace`指向含`inputs/manifest.json`的本工作区。省略输出参数只读审计；通过后加`--output`生成含全部原始结果的内部作者ZIP。工具要求run manifest绑定全部`src/**/*.py`和两个主入口脚本，拒绝缺失、重复、混版本、哈希不符、非原版官方评估器、未完成运行及旧报告行；包内`MANIFEST.json`逐文件区分官方原件、作者源码、评估器原始输出和派生报告。可另加`--compact-output`生成精简候选ZIP，仅保留1500份最终计划和原始结果的哈希清单，不含完整事件原始输出，不能代替完整作者包。输出给出确切字节数与是否不超过本届可选附件50M限额，不表示格式已获平台接受或已提交。

只读审计示例（下列路径须替换为同一正式冻结版本）：

```bash
python3 tools/package_a_author.py \
  --source-root /绝对路径/冻结求解工程 \
  --run-root /绝对路径/正式主矩阵 \
  --baseline-root /绝对路径/A0基线 \
  --report-csv /绝对路径/新main_results.csv \
  --official-workspace /Users/futaoran/Desktop/华为杯2026/2026参赛工作区 \
  --evaluator-dir /绝对路径/本次实际使用的官方评估器
```

审计通过后加`--output /绝对路径/作者完整复现包.zip`；需要精简候选包时，再加`--compact-output /绝对路径/作者精简候选包.zip`。
