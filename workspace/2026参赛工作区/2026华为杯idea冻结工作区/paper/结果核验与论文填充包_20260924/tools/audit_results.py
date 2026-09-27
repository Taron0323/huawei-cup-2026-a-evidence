"""Rebuild manuscript tables from archived official results. No solver calls."""
from pathlib import Path
from collections import Counter, defaultdict
import json,csv,hashlib,sys,math
ROOT=Path(__file__).resolve().parents[1]
CODE=ROOT/'code';sys.path.insert(0,str(CODE/'src'))
from huawei_code.plan import plan_key as original_plan_key,validate_plan
def numeric_plan(plan):
    return {**plan,'node_to_subgraph':{int(k):v for k,v in plan['node_to_subgraph'].items()}}
def plan_key(plan):return original_plan_key(numeric_plan(plan))
def recorded_hash_ok(plan,h):return h in {original_plan_key(plan),plan_key(plan)}
from huawei_code.official import summary
OUT=ROOT/'data';OUT.mkdir(exist_ok=True)
AUD=ROOT/'audit';AUD.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text())
def rel(p):return str(p.relative_to(ROOT))
def write(name,rows,folder=OUT):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (folder/name).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
issues=[]
def check(ok,kind,where,detail=''):
    if not ok: issues.append(dict(kind=kind,source=where,detail=str(detail)))
def validate_result(result,where,k,scene,plan=None,view=None):
    if plan is not None:validate_plan(view,plan,k)
    m=result['data_movement_bytes'];ms=result['makespan']
    check(isinstance(ms,int) and ms>0,'makespan',where,ms)
    check(m['added_copy_bytes']==m['partition_added_copy_bytes']+m['spill_added_copy_bytes'],'movement_parts',where,m)
    # Official partition accounting may clamp original boundary differences: check against implementation.
    check(m['scheduled_copy_bytes']-m['original_graph_copy_bytes']==m['added_copy_bytes'],'movement_total',where,m)
    check(result['num_cores']==k,'cores',where)
    check(result['bandwidth_bytes_per_cycle']==60,'ddr_config',where)
    check(result['capacity_bytes']=={'L1':524288,'UB':131072},'capacity_config',where)
    for core,peaks in result['memory_peak_by_core'].items():
        for mem,value in peaks.items():check(value<=result['capacity_bytes'][mem],'memory_peak',where,(core,mem,value))
    max_end=0;per_pipe=defaultdict(list)
    for core in result['per_core_timeline']:
        for op in core['ops']:
            start,end=op['start'],op['end'];max_end=max(max_end,end)
            check(0<=start<=end<=ms,'timeline_bounds',where,op['op_id'])
            check(end-start==op['duration'],'duration',where,op['op_id'])
            per_pipe[(core['core_id'],op['pipe'])].append((start,end))
    check(max_end==ms,'timeline_makespan',where,(max_end,ms))
    for pipe,intervals in per_pipe.items():
        intervals.sort();check(all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:])),'pipe_overlap',where,pipe)
    if scene=='C':
        c=result['cache_stats'];h,n=c['hit_bytes'],c['miss_bytes'];expected=h/(h+n) if h+n else 0
        check(abs(c['hit_rate']-expected)<1e-12,'cache_rate',where)
        check(result['cache_used_bytes_final']<=result['cache_capacity_bytes'],'cache_capacity',where)
        check(result['problem']==3,'problem3',where)
    elif scene=='A':
        check(result['task_same_core_wait_cycles']==100 and result['task_cross_core_wait_cycles']==1000,'a_wait',where)
    elif scene=='B':check(result['cross_core_copy_delay_cycles']==500,'b_wait',where)

names=['full_main_fast_split_20260924','full_main_fast_20260924','full_main_20260924']
roots=[CODE/'results'/n for n in names]
scenes={};static={};logs={};manifest_audit=[]
for root in roots:
    jobs=sorted([p.parent for p in root.glob('*/run_manifest.json')])
    for job in jobs:
        manifest=read(job/'run_manifest.json')
        hash_ok=all(sha(CODE/'vendor/official_evaluator'/name)==h for name,h in manifest['official_code_sha256'].items())
        check(hash_ok,'run_official_hash',rel(job))
        check(manifest['idea_sha256']==sha(CODE/'idea/A题_Final_idea_给codex运行.md'),'run_idea_hash',rel(job))
        manifest_audit.append({'job':rel(job),'official_hash_match':hash_ok,'historical_status':manifest['status']})
        log=root/(job.name+'.console.log');ll={}
        for line in log.read_text().splitlines():
            if line.startswith('{'):
                obj=json.loads(line)
                if 'candidate' in obj:ll[(obj['case'],int(obj['cores']),obj['scene'],obj['candidate'])]=obj
        logs[job]=ll
        for p in (job/'static').glob('*.json'):static.setdefault(p.stem,read(p))
        for p in job.glob('cases/*/*core/*/final_selection.json'):
            sc=p.parent;case=sc.parents[1].name;k=int(sc.parent.name[:-4]);scene=sc.name
            scenes.setdefault((case,k,scene),sc)
expected={(f'case_{i:03d}',k,s) for i in range(1,101) for k in range(1,6) for s in 'ABC'}
check(set(scenes)==expected,'matrix_coverage','main',sorted(expected-set(scenes)))
base={};base_rows=[]
for p in sorted((CODE/'results/full_singlecore_baseline_20260924').glob('batch_*/cases/*/result.json')):
    result=read(p);case=p.parent.name
    validate_result(result,rel(p),1,'baseline')
    base[case]=result['makespan'];base_rows.append({'case':case,'result_path':rel(p),**summary(result)})
check(len(base)==100,'baseline_coverage','baseline',len(base))
legacy=list(csv.DictReader((ROOT/'evidence/previous_report/main_results.csv').open()))
legacy_index={(r['case'],int(r['cores']),r['scene']):r for r in legacy}
rows=[];candidate_rows=[];effects=[];eps_rows=[];failures=[];source_rows=[]
for count,(key,sc) in enumerate(sorted(scenes.items()),1):
    case,k,scene=key;job=sc.parents[3];view=static[case]
    ledger={r['candidate']:r for r in read(sc/'candidate_ledger.json')}
    initial=read(sc/'initial_selection.json');final=read(sc/'final_selection.json')
    valid={}
    for cd in sorted((sc/'candidates').iterdir()):
        result_path=cd/'result.json';plan=read(cd/'plan.json');planhash=plan_key(plan)
        log=logs[job].get((*key,cd.name),{})
        if result_path.exists():
            result=read(result_path);validate_result(result,rel(result_path),k,scene,plan,view)
            valid[cd.name]=(result,plan)
            check(bool(log) and log['status']=='AI_VERIFIED','candidate_log',rel(cd))
            check(recorded_hash_ok(plan,log.get('plan_sha256')),'log_plan_hash',rel(cd))
            for metric,value in summary(result).items():
                if metric in log:check(log[metric]==value,'log_metric',rel(cd),metric)
            rr={'case':case,'cores':k,'scene':scene,'candidate':cd.name,'source':ledger[cd.name]['source'],
                'status':'AI_VERIFIED','plan_sha256':planhash,'result_path':rel(result_path),'plan_path':rel(cd/'plan.json'),
                'profile_seconds':log.get('profile_seconds'),'evaluation_seconds':log.get('evaluation_seconds'),
                'gpu_operation_executed':read(sc/'gpu_rank.json').get('backend'),'gpu_rank_used_for_selection':False,
                **summary(result)}
            candidate_rows.append(rr)
        else:
            fp=cd/'profile_failure.json' if (cd/'profile_failure.json').exists() else cd/'evaluation_failure.json'
            if fp.exists():failures.append({'path':rel(fp),**read(fp)})
    winner=min(valid,key=lambda n:(valid[n][0]['makespan'],valid[n][0]['data_movement_bytes']['added_copy_bytes'],n))
    check(winner==final['candidate'],'winner',rel(sc),(winner,final['candidate']))
    for label,sel in [('initial',initial),('final',final)]:
        res,plan=valid[sel['candidate']]
        check(recorded_hash_ok(plan,sel['plan_sha256']),'selection_hash',rel(sc),label)
        check(recorded_hash_ok(read(sc/(label+'_plan.json')),sel['plan_sha256']),'saved_plan_hash',rel(sc),label)
        check(res['makespan']==sel['makespan'] and res['data_movement_bytes']['added_copy_bytes']==sel['added_copy_bytes'],'selection_metrics',rel(sc),label)
    r,p=valid[final['candidate']];ir,ip=valid[initial['candidate']];m=r['data_movement_bytes'];ms=r['makespan'];ims=ir['makespan']
    # Exact compute-only path/work bounds; omit a shared DDR bound for C because Cache serves some reads.
    finish={};work=defaultdict(int)
    for node in view['topological']:
        op=view['ops'][str(node)];cy=int(op['cycles']);finish[str(node)]=cy+max((finish[str(a)] for a in view['preds'][str(node)]),default=0);work[op['pipe']]+=cy
    path=max(finish.values());wm=work['PIPE_M'];wv=work['PIPE_V'];lb=max(path,wm/k,wv/k)
    check(ms>=lb,'compute_lower_bound',rel(sc),(ms,lb))
    lf=logs[job][(*key,final['candidate'])];li=logs[job][(*key,initial['candidate'])]
    rr={'case':case,'cores':k,'scene':scene,'status':'AUDITED_STORED_RESULT',
        'formal_matrix':not (scene=='A' and k==1),'source_scene_path':rel(sc),'baseline_makespan':base[case],
        'initial_candidate':initial['candidate'],'final_candidate':final['candidate'],
        'initial_source':ledger[initial['candidate']]['source'],'final_source':ledger[final['candidate']]['source'],
        'initial_plan_sha256':plan_key(ip),'final_plan_sha256':plan_key(p),'recorded_initial_plan_hash':initial['plan_sha256'],'recorded_final_plan_hash':final['plan_sha256'],
        'initial_makespan':ims,'final_makespan':ms,'speedup_vs_baseline':base[case]/ms,
        'formal_ab_curve_speedup':1.0 if k==1 and scene in 'AB' else base[case]/ms,
        'initial_to_final_relative_gain':(ims-ms)/ims,'final_evaluation_seconds':lf['evaluation_seconds'],
        'initial_profile_seconds':li['profile_seconds'],'final_profile_seconds':lf['profile_seconds'],
        'compute_path_bound':path,'pipe_m_cycles':wm,'pipe_v_cycles':wv,'compute_lower_bound_cycles':lb,'compute_lower_bound_ratio':ms/lb,
        **{('final_'+x):v for x,v in m.items()}}
    cache=r.get('cache_stats',{})
    rr.update({'cache_hit_bytes':cache.get('hit_bytes',''),'cache_miss_bytes':cache.get('miss_bytes',''),'cache_hit_rate':cache.get('hit_rate',''),
               'cache_service_bytes':cache.get('hit_bytes',''),'ddr_service_bytes':m['scheduled_copy_bytes']-cache.get('hit_bytes',0)})
    old=legacy_index[key]
    for name in ['final_makespan','initial_makespan','baseline_makespan','speedup_vs_baseline','final_added_copy_bytes']:
        check(math.isclose(float(old[name]),rr[name],rel_tol=1e-12),'old_primary_metric',rel(sc),name)
    rows.append(rr)
    effects.append({name:rr[name] for name in ['case','cores','scene','initial_candidate','final_candidate','initial_source','final_source','initial_makespan','final_makespan','initial_to_final_relative_gain']})
    for epsilon in [.005,.01]:
        eligible=[n for n,(res,_) in valid.items() if res['makespan']<=ms*(1+epsilon)]
        en=min(eligible,key=lambda n:(valid[n][0]['data_movement_bytes']['added_copy_bytes'],valid[n][0]['makespan'],n))
        er=valid[en][0];eps_rows.append({'case':case,'cores':k,'scene':scene,'epsilon':epsilon,'candidate':en,'makespan':er['makespan'],'added_copy_bytes':er['data_movement_bytes']['added_copy_bytes'],'changed':en!=final['candidate'],'saved_bytes':m['added_copy_bytes']-er['data_movement_bytes']['added_copy_bytes']})
    source_rows.append({'case':case,'cores':k,'scene':scene,'initial_result_path':rel(sc/'candidates'/initial['candidate']/'result.json'),'final_result_path':rel(sc/'candidates'/final['candidate']/'result.json'),'final_plan_path':rel(sc/'final_plan.json')})
    if count%300==0:print('audited',count,'issues',len(issues),flush=True)
index={(r['case'],r['cores'],r['scene']):r for r in rows};pairs=[]
for case,k,scene in sorted(index):
    if scene!='B':continue
    b=index[(case,k,'B')];c=index[(case,k,'C')]
    check(b['final_plan_sha256']==c['initial_plan_sha256'],'cache_fixed_plan',case,k)
    tb,tc,topt=b['final_makespan'],c['initial_makespan'],c['final_makespan']
    pairs.append({'case':case,'cores':k,'b_makespan':tb,'c_same_plan_makespan':tc,'c_final_makespan':topt,'s_hw':tb/tc,'s_adapt':tc/topt,'s_opt':tb/topt,'factor_residual':tb/topt-(tb/tc)*(tc/topt),'hit_bytes':c['cache_hit_bytes'],'miss_bytes':c['cache_miss_bytes'],'cache_service_bytes':c['cache_service_bytes'],'ddr_service_bytes':c['ddr_service_bytes']})
# Sensitivity: independently check all stored successful results and variant configurations.
sroot=ROOT/'evidence/sensitivity_raw';sens=[];sens_fail=[]
for mode in ['fixed_plan','reoptimized']:
    for rr in csv.DictReader((sroot/(mode+'.csv')).open()):
        folder=sroot/mode/rr['case']/rr['variant']/rr['candidate'];plan=read(folder/'plan.json')
        check(recorded_hash_ok(plan,rr['plan_sha256']),'sensitivity_plan_hash',rel(folder))
        if rr['status']!='AI_VERIFIED':sens_fail.append(rr);continue
        r=read(folder/'result.json');validate_result(r,rel(folder),5,'C',plan,static[rr['case']])
        cap=524288 if rr['variant']=='cache_capacity_half' else 2097152 if rr['variant']=='cache_capacity_double' else 1048576
        bw=125 if rr['variant']=='cache_bandwidth_half' else 500 if rr['variant']=='cache_bandwidth_double' else 250
        check((r['cache_capacity_bytes'],r['cache_bandwidth_bytes_per_cycle'])==(cap,bw),'sensitivity_config',rel(folder))
        for metric,value in summary(r).items():check(math.isclose(float(rr[metric]),value,rel_tol=1e-12,abs_tol=1e-12),'sensitivity_metric',rel(folder),metric)
        check(mode!='fixed_plan' or plan_key(plan)==index[(rr['case'],5,'B')]['final_plan_sha256'],'sensitivity_B_base',rel(folder))
        if mode=='fixed_plan' or rr['selected']=='True':
            default=pairs[[ (p['case'],p['cores']) for p in pairs].index((rr['case'],5))]['c_same_plan_makespan']
            sens.append({'case':rr['case'],'variant':rr['variant'],'mode':mode,'candidate':rr['candidate'],'cache_capacity_bytes':cap,'cache_bandwidth_bytes_per_cycle':bw,'default_same_plan_makespan':default,'variant_makespan':r['makespan'],'default_over_variant':default/r['makespan'],'changed_from_B_plan':plan_key(plan)!=index[(rr['case'],5,'B')]['final_plan_sha256'],'result_path':rel(folder/'result.json'),**summary(r)})
write('main_results.csv',rows);write('singlecore_baseline.csv',base_rows);write('candidate_evaluations.csv',candidate_rows);write('candidate_comparison.csv',effects);write('cache_pairs.csv',pairs);write('epsilon_tradeoffs.csv',eps_rows);write('result_sources.csv',source_rows);write('sensitivity_results.csv',sens);write('sensitivity_failed_candidates.csv',sens_fail);write('main_failed_candidates.csv',failures)
write('consistency_failures.csv',issues,AUD);write('run_hash_checks.csv',manifest_audit,AUD)
monotonic=sum(index[(f'case_{i:03d}',k,s)]['final_makespan']>index[(f'case_{i:03d}',k-1,s)]['final_makespan'] for i in range(1,101) for k in range(2,6) for s in 'AB')
report={'stored_matrix_rows':len(rows),'unique_combinations':len(index),'formal_combinations':sum(r['formal_matrix'] for r in rows),'baseline_rows':len(base),'audited_successful_candidates_in_selected_combinations':len(candidate_rows),'failed_candidates_in_selected_combinations':len(failures),'cache_pairs':len(pairs),'sensitivity_selected_rows':len(sens),'sensitivity_successful_candidates':60,'sensitivity_failed_candidates':len(sens_fail),'sensitivity_selected_changed_plans':sum(r['changed_from_B_plan'] for r in sens if r['mode']=='reoptimized'),'consistency_failures':len(issues),'old_missing_source_rows':sum(not r['final_source'] for r in legacy),'old_missing_timing_rows':sum(r['final_evaluation_seconds'] in ('','nan') for r in legacy),'ab_speedup_below_one':sum(r['speedup_vs_baseline']<1 for r in rows if r['scene'] in 'AB'),'ab_adjacent_core_regressions':monotonic,'scope':'all stored selected-combination results checked; independent replay is reported separately','paper_readiness':'PARTIAL_METHOD_AND_CONTROL_GAPS'}
(AUD/'audit_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False),flush=True)
