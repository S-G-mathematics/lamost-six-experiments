import json,pathlib,time,datetime,sys
R=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025')
last=None
while True:
 try:
  s=json.loads((R/'status.json').read_text());summary={'observed_utc':s['observed_utc'],'scientific_counts':s['scientific_counts'],'active':[]}
  for a in s.get('active',[]):
   pid=a['pid'];alive=False
   try:
    stat=pathlib.Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()
    alive=stat[19]==str(a['process_start_ticks']) and 'worker.py' in pathlib.Path(f'/proc/{pid}/cmdline').read_bytes().decode()
   except OSError:pass
   entry={'key':a['key'],'actual_process_alive':alive}
   hs=list((R/'artifacts'/a['key']/'checkpoints').glob('*/trial_history.json'))
   if hs:
    try:entry['completed_trials']=len(json.loads(hs[-1].read_text()))
    except Exception:pass
   summary['active'].append(entry)
  for name in ['CODE_CHANGE_HOLD.json','WATCHDOG_START_HOLD.json','STORAGE_HOLD.json','EC2_COMPLETE_DELIVERY_PENDING.json','PROJECT_COMPLETE.json']:
   if (R/name).exists():summary[name]=True
  if s['task_counts'].get('operationally_invalid'):summary['operationally_invalid']=s['task_counts']['operationally_invalid']
  compact=json.dumps(summary,sort_keys=True)
  if compact!=last:print(compact,flush=True);last=compact
  if (R/'PROJECT_COMPLETE.json').exists() or (R/'EC2_COMPLETE_DELIVERY_PENDING.json').exists():break
 except Exception as exc:print('MONITOR_ERROR',type(exc).__name__,str(exc),flush=True)
 time.sleep(30)
