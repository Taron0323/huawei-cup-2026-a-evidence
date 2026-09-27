"""Deterministic official replay sample; compare complete JSON results."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import sys,json,time,csv,hashlib
ROOT=Path(__file__).resolve().parents[1];CODE=ROOT/'code';sys.path.insert(0,str(CODE/'src'))
from huawei_code.official import load_modules,read_config,evaluate
JOBS=[('case_001',2,s) for s in 'ABC']+[('case_014',5,s) for s in 'ABC']+[('case_100',5,s) for s in 'ABC']+[('case_076',5,'B'),('case_091',5,'C')]
def locate(case,k,scene):
    for name in ['full_main_fast_split_20260924','full_main_fast_20260924','full_main_20260924']:
        for p in sorted((CODE/'results'/name).glob(f'*/cases/{case}/{k}core/{scene}/final_selection.json')):
            sel=json.loads(p.read_text());return p.parent/'candidates'/sel['candidate']
    raise FileNotFoundError((case,k,scene))
def run(job):
    modules=load_modules(CODE/'vendor/official_evaluator');config=read_config(modules,CODE/'data/raw/A题/data/config.txt')
    if len(job)==3:
        case,k,scene=job;folder=locate(*job)
    else:
        case,variant,mode,candidate=job;k=5;scene='C';folder=ROOT/'evidence/sensitivity_raw'/mode/case/variant/candidate
        if variant=='cache_capacity_half':config['cache']['capacity']//=2
        if variant=='cache_capacity_double':config['cache']['capacity']*=2
        if variant=='cache_bandwidth_half':config['cache']['bandwidth']/=2
        if variant=='cache_bandwidth_double':config['cache']['bandwidth']*=2
    graph=json.loads((CODE/f'data/raw/A题/data/{case}.json').read_text());plan=json.loads((folder/'plan.json').read_text())
    started=time.perf_counter();res=evaluate(graph,plan,{'A':1,'B':2,'C':3}[scene],config,modules)
    old=json.loads((folder/'result.json').read_text())
    res=json.loads(json.dumps(res))  # JSON stringifies dictionary keys, as in the stored official result.
    equal=res==old
    out={'job':job,'full_result_equal':equal,'elapsed_seconds':time.perf_counter()-started,'stored_makespan':old['makespan'],'replayed_makespan':res['makespan'],'source':str(folder.relative_to(ROOT)),'different_top_level_keys':[k for k in set(old)|set(res) if old.get(k)!=res.get(k)]}
    return out
if __name__=='__main__':
    for r in csv.DictReader((ROOT/'evidence/sensitivity_raw/fixed_plan.csv').open()):
        if r['case']=='case_051':JOBS.append((r['case'],r['variant'],r['mode'],r['candidate']))
    records=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,j) for j in JOBS]):
            result=f.result();records.append(result);print(json.dumps(result),flush=True)
    report={'jobs':len(records),'full_result_matches':sum(r['full_result_equal'] for r in records),'records':records,'coverage_note':'11 selected main results and 4 sensitivity results; this is a replay sample, not 1500 full replays'}
    (ROOT/'audit/official_replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    assert report['jobs']==report['full_result_matches']
