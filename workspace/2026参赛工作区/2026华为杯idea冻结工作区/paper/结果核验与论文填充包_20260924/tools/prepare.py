from pathlib import Path
import shutil, hashlib, json
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT.parents[3]
CODE=WORK/'华为杯_code'
assert CODE.is_dir(), (WORK,CODE)
def copy(src,dst):
    if src.is_dir():
        shutil.copytree(src,dst,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.DS_Store','*.pyc'))
    else:
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
for name in ['src','scripts','tests','vendor','data/raw','idea','requirements.txt']:
    copy(CODE/name,ROOT/'code'/name)
for name in ['full_main_20260924','full_main_fast_20260924','full_main_fast_split_20260924','full_singlecore_baseline_20260924']:
    copy(CODE/'results'/name,ROOT/'code/results'/name)
    print('copied',name,flush=True)
frozen=ROOT.parents[1]
copy(frozen/'实验数据/sensitivity_20260924_v2',ROOT/'evidence/sensitivity_raw')
copy(frozen/'实验数据/main_reports_20260924_v2',ROOT/'evidence/previous_report')
copy(frozen/'incoming',ROOT/'manuscript/incoming')
copy(frozen/'paper/latex_draft_from_replica',ROOT/'manuscript/latex_draft_from_replica')
for name in ['README.md','STATUS.md','HANDOFF.md']:
    copy(frozen/name,ROOT/'evidence/before'/name)
copy(frozen/'实验数据/FINAL_VALIDATION_20260924.json',ROOT/'evidence/before/FINAL_VALIDATION_20260924.json')
copy(frozen/'实验数据/EXPERIMENT_MANIFEST_20260924.json',ROOT/'evidence/before/EXPERIMENT_MANIFEST_20260924.json')
# Compare the copied official inputs to the registered originals in the active project.
original=WORK/'2026参赛工作区/inputs/raw/A题/附件'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
comparisons=[]
for sub,target in [('data','code/data/raw/A题/data'),('code','code/vendor/official_evaluator')]:
    for p in sorted((original/sub).iterdir()):
        if p.is_file() and p.suffix in ('.json','.txt','.py'):
            q=ROOT/target/p.name
            comparisons.append({'file':str(q.relative_to(ROOT)),'original_sha256':sha(p),'copy_sha256':sha(q),'equal':sha(p)==sha(q)})
(ROOT/'audit').mkdir(exist_ok=True)
(ROOT/'audit/input_identity.json').write_text(json.dumps(comparisons,indent=2,ensure_ascii=False)+'\n')
print('identity',len(comparisons),all(x['equal'] for x in comparisons),flush=True)
