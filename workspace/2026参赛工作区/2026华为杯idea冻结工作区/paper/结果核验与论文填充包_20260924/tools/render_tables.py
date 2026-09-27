"""Derive tables and PNG/SVG/PDF figures only from audited CSV data."""
from pathlib import Path
import pandas as pd,numpy as np,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data';OUT=ROOT/'tables';OUT.mkdir(exist_ok=True)
FIG=ROOT/'figures';FIG.mkdir(exist_ok=True)
f=pd.read_csv(DATA/'main_results.csv');pairs=pd.read_csv(DATA/'cache_pairs.csv');sens=pd.read_csv(DATA/'sensitivity_results.csv')
summary=[]
for (scene,k),part in f.groupby(['scene','cores']):
    vals=part['speedup_vs_baseline'];formal=part['formal_ab_curve_speedup']
    summary.append(dict(scene=scene,cores=k,n=len(part),mean_speedup=float(formal.mean()) if scene in 'AB' else float(vals.mean()),diagnostic_mean_speedup=float(vals.mean()),median_diagnostic_speedup=float(vals.median()),mean_makespan=float(part.final_makespan.mean()),mean_added_copy_bytes=float(part.final_added_copy_bytes.mean()),below_baseline_count=int((vals<1).sum())))
s=pd.DataFrame(summary);s.to_csv(OUT/'main_summary.csv',index=False)
c=[]
for k,part in pairs.groupby('cores'):
    h=part.hit_bytes.sum();m=part.miss_bytes.sum()
    c.append(dict(cores=k,n=len(part),mean_s_hw=part.s_hw.mean(),mean_s_adapt=part.s_adapt.mean(),mean_s_opt=part.s_opt.mean(),weighted_cache_hit_rate=h/(h+m),mean_per_graph_cache_hit_rate=(part.hit_bytes/(part.hit_bytes+part.miss_bytes)).mean(),max_factor_residual=part.factor_residual.abs().max()))
c=pd.DataFrame(c);c.to_csv(OUT/'cache_summary.csv',index=False)
e=f.groupby(['scene','cores']).agg(n=('case','size'),mean_gain=('initial_to_final_relative_gain','mean'),improved=('initial_to_final_relative_gain',lambda x:(x>0).sum())).reset_index();e.to_csv(OUT/'candidate_comparison_summary.csv',index=False)
st=sens.groupby(['variant','mode']).agg(n=('case','size'),mean_default_over_variant=('default_over_variant','mean'),mean_makespan=('makespan','mean'),hit_bytes=('cache_hit_bytes','sum'),miss_bytes=('cache_miss_bytes','sum'),changed_plans=('changed_from_B_plan','sum')).reset_index();st['weighted_hit_rate']=st.hit_bytes/(st.hit_bytes+st.miss_bytes);st.to_csv(OUT/'sensitivity_summary.csv',index=False)
def tex_table(df,name,caption):
    (OUT/(name+'.tex')).write_text('% Generated from audited data. Requires booktabs.\n\\begin{table}[htbp]\n\\centering\n\\caption{'+caption+'}\n'+df.to_latex(index=False,float_format=lambda x:f'{x:.6f}',escape=True)+'\\end{table}\n')
tex_table(s[['scene','cores','n','mean_speedup','mean_makespan','mean_added_copy_bytes']].rename(columns={'scene':'Scene','cores':'K','mean_speedup':'Mean speedup','mean_makespan':'Mean cycles','mean_added_copy_bytes':'Mean added bytes'}),'main_summary','Official-simulator mean speedup, makespan, and added movement; A/B single-core curve anchors equal 1.')
tex_table(c[['cores','n','mean_s_hw','mean_s_adapt','mean_s_opt','weighted_cache_hit_rate']],'cache_summary','Paired Cache ratios; ratios are averaged per graph. Cache hit rate is weighted by query bytes.')
tex_table(e,'candidate_comparison','First successful candidate versus selected candidate; not a component removal ablation.')
tex_table(st[['variant','mode','n','mean_default_over_variant','weighted_hit_rate','changed_plans']],'sensitivity_summary','Cache sensitivity on six fixed representative graphs.')
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
def save(fig,name):
    fig.tight_layout()
    for ext in ['png','svg','pdf']:fig.savefig(FIG/(name+'.'+ext),dpi=180)
    plt.close(fig)
fig,ax=plt.subplots(figsize=(6.5,4.2))
for scene in 'AB':
    part=s[s.scene==scene];ax.plot(part.cores,part.mean_speedup,'o-',label=scene)
ax.set(xlabel='Cores',ylabel='Mean per-graph speedup vs whole-graph baseline',xticks=range(1,6));ax.legend();ax.grid(alpha=.2);save(fig,'ab_speedup')
fig,ax=plt.subplots(figsize=(6.5,4.2))
for name,label in [('mean_s_hw','Same plan + Cache'),('mean_s_adapt','Candidate adaptation'),('mean_s_opt','B final / C final')]:ax.plot(c.cores,c[name],'o-',label=label)
ax.set(xlabel='Cores',ylabel='Mean paired ratio',xticks=range(1,6));ax.legend();ax.grid(alpha=.2);save(fig,'cache_ratios')
fig,ax=plt.subplots(figsize=(6.5,4.2))
for scene in 'ABC':
    part=e[e.scene==scene];ax.plot(part.cores,100*part.mean_gain,'o-',label=scene)
ax.set(xlabel='Cores',ylabel='Mean first-to-selected gain (%)',xticks=range(1,6));ax.legend();ax.grid(alpha=.2);save(fig,'candidate_comparison')
# Normalized per-graph response: include unchanged official configuration at factor 1.
for param in ['capacity','bandwidth']:
    fig,axs=plt.subplots(1,2,figsize=(10,4))
    for case,part in sens[(sens['mode']=='fixed_plan') & sens.variant.str.contains(param)].groupby('case'):
        lo=part[part.variant.str.endswith('half')].iloc[0];hi=part[part.variant.str.endswith('double')].iloc[0]
        axs[0].plot([.5,1,2],[lo.default_over_variant,1,hi.default_over_variant],'o-',label=case)
        default=f[(f.case==case)&(f.cores==5)&(f.scene=='C')].iloc[0]
        # default hit rate from the C INITIAL result, the same B plan.
        src=pd.read_csv(DATA/'result_sources.csv');rp=ROOT/src[(src.case==case)&(src.cores==5)&(src.scene=='C')].iloc[0].initial_result_path
        dr=json.loads(rp.read_text())['cache_stats']['hit_rate']
        axs[1].plot([.5,1,2],[lo.cache_hit_rate,dr,hi.cache_hit_rate],'o-',label=case)
    for ax in axs:ax.set(xlabel=f'Cache {param} / default',xticks=[.5,1,2]);ax.grid(alpha=.2)
    axs[0].set_ylabel('Default makespan / variant makespan');axs[1].set_ylabel('Byte hit rate');axs[1].legend(fontsize=8)
    save(fig,'sensitivity_'+param)
# Use real rows, not a narrative estimate.
lines=['# 核验后论文数值入口','','A/B 单核正式曲线点按 Idea 定义设为 1；优化后单核速度比单列 diagnostic_mean_speedup。C 的主要 Cache 提升用同核数 B/C 配对，不使用对整图单核的比值替代。','']
for title,frame in [('主结果',s),('Cache 配对与字节加权命中率',c),('首次成功候选与最终候选对比',e),('敏感性',st)]:
    lines += ['## '+title,'','```text',frame.to_string(index=False,float_format=lambda x:f'{x:.6f}'),'```','']
(ROOT/'tables/论文数值汇总.md').write_text('\n'.join(lines))
print('tables and figures generated')
