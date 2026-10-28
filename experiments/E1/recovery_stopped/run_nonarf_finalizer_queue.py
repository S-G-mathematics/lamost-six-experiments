import pathlib as _stop_pathlib
if _stop_pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/RECOVERY_CUTOFF.json').exists():
    raise SystemExit('E1 recovery disabled by user stop; no further E1 jobs')
import datetime,json,os,pathlib,signal,subprocess,time
base=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
rec=base/'e1_recovery_20261024'
root=base/'project'
venv=base/'venv/bin/python'
tool=rec/'finalize_saved_pipeline.py'
state_file=rec/'nonarf_finalizer_state.json'
state=json.loads(state_file.read_text()) if state_file.exists() else {}
env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH='benchmark/.deps')
def run(argv,log_path,timeout):
    with log_path.open('ab') as log:
        log.write(('START '+datetime.datetime.now(datetime.timezone.utc).isoformat()+' '+json.dumps(argv)+'\n').encode())
        log.flush()
        p=subprocess.Popen(argv,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            rc=p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try:rc=p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);rc=p.wait()
        log.write(('END '+datetime.datetime.now(datetime.timezone.utc).isoformat()+' returncode='+str(rc)+'\n').encode())
    return rc
validation_source=rec/'nonarf_cells/kde/n_30000/rep_1/results/e1/rep_1/n_30000/kde'
validation_output=rec/'saved_pipeline_validation/kde_n30000_rep1'
argv=[str(venv),'-u',str(tool),'--source-cell',str(validation_source),'--output',str(validation_output),'--baseline',str(root/'lamost_baseline'),'--validate-against-source']
if not (validation_output/'finalization.json').exists():
    rc=run(argv,rec/'saved_pipeline_validation.log',7200)
    if rc!=0:
        raise SystemExit('saved pipeline reproduction failed; finalization queue halted')
checks=json.loads((validation_output/'finalization.json').read_text()).get('validation_checks',{})
if not checks or not all(checks.values()):
    raise SystemExit('saved pipeline reproduction checks not all true')
source_state=json.loads((rec/'nonarf_queue_state.json').read_text())
for key,row in source_state.items():
    if row.get('complete'):
        continue
    budget,rep,method=key.split('/')
    source=pathlib.Path(row['output'])/'results/e1'/rep/budget/method
    manifest=json.loads((source/'manifest.json').read_text())
    if 'TrialTimeout' not in str(manifest.get('error')) or not (source/'pipeline.joblib').exists():
        continue
    if key in state:
        continue
    dest=rec/'finalized_nonarf_cells'/method/budget/rep
    dest.mkdir(parents=True,exist_ok=True)
    argv=[str(venv),'-u',str(tool),'--source-cell',str(source),'--output',str(dest),'--baseline',str(root/'lamost_baseline')]
    rc=run(argv,dest/'run.log',43200)
    result={'returncode':rc,'complete':(dest/'finalization.json').exists(),'output':str(dest)}
    state[key]=result
    temp=state_file.with_suffix('.tmp')
    temp.write_text(json.dumps(state,indent=2,sort_keys=True)+'\n')
    temp.replace(state_file)
    print(key,result,flush=True)
print('FINALIZER_QUEUE_DONE',len(state),flush=True)
