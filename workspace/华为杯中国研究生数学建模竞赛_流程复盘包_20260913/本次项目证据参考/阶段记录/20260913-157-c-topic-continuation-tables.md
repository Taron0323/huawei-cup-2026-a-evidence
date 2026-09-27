# 第157阶段：表7上移与表8续排

用户指出第18页说明文字后有大段空白，要求把下一页表7提上来，并明确全文允许出现续表。

最终将问题三的购电表和储能表改为longtable：表7第18页先排七行，第19页以“续表7”重复表头、接后三行；表8第19页先排两行，第20页以“续表8”重复表头、接六行。列宽、字号、表题、图号和两表18行全部数据保持原样。已同步总生成器，后续生成仍保留这两张续表。其他已有长表的续页能力保留，短表保留原排法，没有添加强制分页。

本轮先试过全量转换，但长表与已经进入浮动队列的图产生页外溢出；最终采用只调整有空白问题的两张表，其他试验修改全部撤回本阶段before。mathmodel.sty及问题一至四章节与before一致，图件没有重画或缩放。新增追踪的style/章节文件均在编辑前补存到before，其独立来源记录位于evidence/before-additional-sources.json。

交付文件：`output/C题论文_v1.15-续表排版审阅版.pdf`。48页，正文含参考文献29页，摘要1页，附录第30页另起。图8增强版第14页，图13增强版第19页，用户提供的图3矢量原件第7页。

验证：

- `convert_tables.py`仅调用表格包装函数，不导入求解或绘图流程；两表数据行逐字相同，结果见evidence/table-conversion.json。
- 在paper/latex执行`latexmk -xelatex -interaction=nonstopmode -halt-on-error -file-line-error -outdir=build/v1.15-continuation-tables main.tex`，退出码0，最终日志无Overfull vbox。
- 使用bundled Python执行本阶段`verify_pdf.py`，退出码0：19图、14组题面表格需求仍完整，摘要1页、正文29页；第1至30页已渲染，18至20页重点核对续表及图13，无新遮挡或裁切。
- 当前dynamic-optimization、all-figures和paper/latex/main.pdf同步；先前独立命名的图8图13增强审阅PDF保留为上一版。

完整修改前后内容位于before、after，差异见diff.patch。未运行求解器，人工审阅PENDING；支撑材料ZIP按用户要求保持暂停。
