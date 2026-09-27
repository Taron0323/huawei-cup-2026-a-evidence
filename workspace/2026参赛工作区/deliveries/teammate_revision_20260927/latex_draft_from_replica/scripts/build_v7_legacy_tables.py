"""Generate v7 values using the teammate manuscript's existing table filenames/labels.
This keeps sections unchanged while replacing legacy table contents with raw final_selection data.
"""
from __future__ import annotations
import csv, statistics as st, random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/v7_fast_20260927'
SENS=ROOT/'data/v7_fast_sensitivity_20260927'
GEN=ROOT/'generated'

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def num(r,k):return float(r[k])
def tex_table(headers,rows,spec,caption,label):
    n=len(headers); out=[f'\\begin{{longtable}}{{{spec}}}',f'\\caption{{{caption}}}\\label{{{label}}}\\\\',r'\toprule',' & '.join(headers)+r' \\',r'\midrule',r'\endfirsthead',f'\\multicolumn{{{n}}}{{c}}{{续表}}\\\\',r'\toprule',' & '.join(headers)+r' \\',r'\midrule',r'\endhead',f'\\midrule\\multicolumn{{{n}}}{{r}}{{续下页}}\\\\',r'\endfoot',r'\bottomrule',r'\endlastfoot']
    out.extend(' & '.join(row)+r' \\' for row in rows)
    out.append(r'\end{longtable}')
    return '\n'.join(out)+'\n'

rows=read(DATA/'main_results.csv'); by={(r['case'],int(r['cores']),r['scene']):r for r in rows}; cases=sorted({r['case'] for r in rows})
# 100 rows per core, preserving teammate's seven-column layout.
all_detail=[]
for k in range(1,6):
    body=[]
    for c in cases:
        row=[c[-3:]]
        for scene in 'ABC':
            r=by[(c,k,scene)]
            row += [f"{int(num(r,'final_makespan'))}/{num(r,'speedup_vs_baseline'):.3f}",str(int(num(r,'final_added_copy_bytes')))]
        body.append(row)
    all_detail.append(tex_table(['图','$T_A/S_A$','$D_A$/B','$T_B/S_B$','$D_B$/B','$T_C/S_C$','$D_C$/B'],body,'crrrrrr',f'{k}核三问逐例工期/加速比与额外搬运（v7，100图）',f'tab:detail-{k}'))
(GEN/'selected_tables.tex').write_text('\n'.join(all_detail),encoding='utf-8')
# Cache paired 100 rows per core. initial fields are C(X_B), final fields are C(X_C).
pairs=read(DATA/'cache_pairs.csv'); byp={(r['case'],int(r['cores'])):r for r in pairs}
all_cache=[]
for k in range(1,6):
    body=[]
    for c in cases:
        r=byp[(c,k)]
        body.append([c[-3:],str(int(num(r,'b_makespan'))),str(int(num(r,'c_initial_makespan'))),str(int(num(r,'c_final_makespan'))),f"{num(r,'s_hw'):.4f}",f"{num(r,'s_adapt'):.4f}",f"{num(r,'s_opt'):.4f}",f"{num(r,'c_initial_hit_rate')*100:.2f}",f"{num(r,'c_hit_rate')*100:.2f}"])
    all_cache.append(tex_table(['图','$T_B$','$T_C(X_B)$','$T_C(X_C)$','$S_{hw}$','$S_{ad}$','$S_{opt}$','$C(X_B)$/\\%','$C(X_C)$/\\%'],body,'crrrrrrrr',f'{k}核Cache同计划配对（v7，100图）',f'tab:cache-detail-{k}'))
(GEN/'cache_tables.tex').write_text('\n'.join(all_cache),encoding='utf-8')
# Sensitivity detailed table (24 rows) with v7 source.
sens=read(SENS/'sensitivity_summary.csv')
labels={'cache_capacity_half':'容量/2','cache_capacity_double':'容量×2','cache_bandwidth_half':'带宽/2','cache_bandwidth_double':'带宽×2'}
srows=[]
for r in sorted(sens,key=lambda x:(x['case'],x['variant'])):
    srows.append([r['case'].split('_')[-1],labels.get(r['variant'],r['variant']),str(int(float(r['fixed_makespan']))),str(int(float(r['reoptimized_makespan'])),),f"{float(r['fixed_cache_hit_rate'])*100:.2f}",str(int(float(r.get('failure_count',r.get('failure_alternatives','0')))))])
(GEN/'sensitivity_table.tex').write_text(tex_table(['图','参数','固定计划/周期','重优化/周期','固定命中/\\%','失败候选'],srows,'crrrrr','6张代表图的Cache参数敏感性（v7）','tab:sensitivity-detail'),encoding='utf-8')
print('generated',GEN/'selected_tables.tex',GEN/'cache_tables.tex',GEN/'sensitivity_table.tex')
