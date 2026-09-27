# 交付文件准备

读取 common.md、官方规则、赛区通知与 paper/evidence/human_checks.csv。确认题面需求全部覆盖、主结果证据闭合、代码可复现、人工核验按实际情况记录。

编译最终论文，逐页检查摘要、分页、图表、公式、文献与附录。电子版不得含承诺书和编号页，无目录；摘要单页，正文不超过已核实页限。检查元数据、路径、图片水印和代码注释中的身份信息。

从 ai_usage.csv 生成真实 AI 使用详情 PDF，在参考文献前生成实际使用声明。人工核验未发生的条目不能写成已完成。

本工作台已提供 `tools/export_ai_usage.py`，用文档 Python 运行；字段与状态见 `templates/ai/README.md`。将最新详情 PDF 和同名 record.json 同时列入支撑清单。已有导出不覆盖，按新版本路径导出并更新清单。

准备支撑材料清单，含可运行源程序、依赖、运行说明、必要外部数据和结果；按官方规定处理题面自带数据、大小和文件名。填写 `paper/submission.json` 后运行 `.venv/bin/python tools/check_project.py --mode submission`，通过后用 `.venv/bin/python tools/package_submission.py --mode submission` 生成本地交付文件。证据路径约定见 `paper/evidence/README.md`。准备模式只能生成明确标记的准备材料；正式题面和结果为空时不能打正式提交包。纯理论、无程序或完全未使用 AI 的例外按官方规则另行审查，不编造记录迎合检查器。

交付可审查的论文与支撑包及其哈希。账号、签名、队内最终确认、上传和回执逐项保留真实状态；没有回执不声称提交成功。
