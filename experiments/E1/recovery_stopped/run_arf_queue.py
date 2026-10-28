import pathlib as _stop_pathlib
if _stop_pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/RECOVERY_CUTOFF.json').exists():
    raise SystemExit('E1 recovery disabled by user stop; no further E1 jobs')
import os,sys,json,pathlib,subprocess,signal,time,shutil,datetime
base=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
root=base/'project';rec=base/'e1_recovery_20261024'
queue=json.loads((rec/'arf_queue.json').read_text())
state_path=rec/'arf_queue_state.json'
state=json.loads(state_path.read_text()) if state_path.exists() else {}
env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH='benchmark/.deps')
for item in queue:
 method=item['method'];budget=item['budget'];rep=item['repetition']
 key=f'n_{budget}/rep_{rep}/{method}'
 if key in state:continue
 if shutil.disk_usage(base).free < 30*1024**3:
  state[key]={'status':'stopped_disk_headroom'};break
 out=rec/'arf_cells'/method/f'n_{budget}'/f'rep_{rep}'
 out.mkdir(parents=True,exist_ok=True)
 argv=[str(base/'venv/bin/python'),'-u','-m','benchmark.experiments','--experiment','1','--output',str(out/'results'),'--baseline-dir',str(root/'lamost_baseline'),'--budgets',str(budget),'--repetitions','1','--rep-start',str(rep-1),'--methods',method,'--seed','271828','--trial-timeout','600','--memory-limit-gib','10','--resource-profile','native8gib8cores','--prediction-chunk','50000','--resume']
 start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with (out/'run.log').open('ab') as log:
  log.write(('START '+start+' '+json.dumps(argv)+'\n').encode());log.flush()
  proc=subprocess.Popen(argv,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=proc.wait(timeout=7200);timed_out=False
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGTERM)
   try:rc=proc.wait(timeout=15)
   except subprocess.TimeoutExpired:
    os.killpg(proc.pid,signal.SIGKILL);rc=proc.wait()
   timed_out=True
  log.write(('END '+datetime.datetime.now(datetime.timezone.utc).isoformat()+f' returncode={rc} timeout={timed_out}\n').encode())
 cell=out/'results/e1'/f'rep_{rep}'/f'n_{budget}'/method
 manifest=cell/'manifest.json';complete=cell/'complete.json'
 result={'returncode':rc,'outer_timeout':timed_out,'complete':complete.exists(),'manifest_status':json.loads(manifest.read_text()).get('status') if manifest.exists() else None,'output':str(out)}
 original=root/'benchmark/results/e1'/f'rep_{rep}'/f'n_{budget}'/method/'manifest.json'
 if manifest.exists() and original.exists():
  old=json.loads(original.read_text())['roles']['roles'];new=json.loads(manifest.read_text())['roles']['roles']
  result['same_role_membership']=all(old[x]['ids_sha256']==new[x]['ids_sha256'] for x in ['fit','tune','calibration'])
 state[key]=result
 temp=state_path.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2,sort_keys=True)+'\n');temp.replace(state_path)
 print(key,result,flush=True)
print('QUEUE_DONE',len(state),len(queue),flush=True)
