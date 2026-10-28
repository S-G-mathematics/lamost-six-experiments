#!/usr/bin/env python3
import argparse,collections,datetime,fcntl,hashlib,json,os,pathlib,signal,sqlite3,subprocess,sys,time
ROOT=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
R=ROOT/'runtime_20261025'
OUT=R/'reports/e4_arf_saved_outcome_audit_20261027'
PRIV=R/'logs/operational/e4_arf_saved_outcome_audit_20261027'
SRC=R/'source/audit_artifacts.py'
SRC_SHA='28897e9d8717449a32d16bf500b2633bc509f1ee506c805db84ed1d0d5289be3'
G=1024**3
MAXRSS=512*1024**2
MAXWALL=120
GRACE=5
COLD_OWNER='rf_cold_batch_wrapper_20261026'
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':'),default=str).encode()
def atomic(p,x):
 p.parent.mkdir(parents=True,exist_ok=True); q=p.with_name(p.name+'.tmp')
 q.write_text(json.dumps(x,indent=2,sort_keys=True,default=str)+'\n');os.replace(q,p)
def dbread_evals():
 c=sqlite3.connect('file:'+str(R/'registry.sqlite')+'?mode=ro',uri=True,timeout=5);c.execute('BEGIN')
 try:return [json.loads(x[0]) for x in c.execute("SELECT record FROM tasks WHERE key LIKE 'e4/%/eval/direct/arf/%' ORDER BY key")]
 finally:c.close()
def db_snapshot():
 c=sqlite3.connect('file:'+str(R/'registry.sqlite')+'?mode=ro',uri=True,timeout=5);c.execute('BEGIN')
 try:
  ev=[json.loads(x[0]) for x in c.execute("SELECT record FROM tasks WHERE key LIKE 'e4/%/eval/direct/arf/%' ORDER BY key")]
  selected=[x for x in ev if x.get('kind')=='eval' and x.get('status')=='validated_terminal' and x.get('outcome')=='successful']
  keys=sorted({x.get('fit_key') for x in selected if x.get('fit_key')});fits={}
  for k in keys:
   row=c.execute('SELECT record FROM tasks WHERE key=?',(k,)).fetchone()
   if row is None:raise RuntimeError('selected fit parent missing: '+k)
   fits[k]=json.loads(row[0])
  return ev,selected,fits
 finally:c.close()
def dbread_selected(eval_keys,fit_keys):
 c=sqlite3.connect('file:'+str(R/'registry.sqlite')+'?mode=ro',uri=True,timeout=5);c.execute('BEGIN')
 try:
  def rows(keys):
   out=[]
   for k in sorted(keys):
    r=c.execute('SELECT record FROM tasks WHERE key=?',(k,)).fetchone()
    if r is None:raise RuntimeError('selected registry task missing: '+k)
    out.append(json.loads(r[0]))
   return out
  return rows(eval_keys),{x['key']:x for x in rows(fit_keys)}
 finally:c.close()
def regdigest(e,f):return hashlib.sha256(canon({'selected_evaluations':sorted(e,key=lambda x:x['key']),'selected_fit_parents':{k:f[k] for k in sorted(f)}})).hexdigest()
def coverage_digest(rows):return hashlib.sha256(canon(rows)).hexdigest()

def mem():
 for x in pathlib.Path('/proc/meminfo').read_text().splitlines():
  if x.startswith('MemAvailable:'):return int(x.split()[1])*1024
 return 0
def ticks(p):
 try:return pathlib.Path('/proc',str(p),'stat').read_text().rpartition(')')[2].split()[19]
 except:return None
def argv(p):
 try:return pathlib.Path('/proc',str(p),'cmdline').read_bytes().decode(errors='replace').split('\0')
 except:return []
def uid(p):
 try:return int(next(x.split()[1] for x in pathlib.Path('/proc',str(p),'status').read_text().splitlines() if x.startswith('Uid:')))
 except:return None
def procs():
 d={}
 for p in pathlib.Path('/proc').iterdir():
  if p.name.isdigit():
   try:d[int(p.name)]=int(next(x.split()[1] for x in pathlib.Path(p/'status').read_text().splitlines() if x.startswith('PPid:')))
   except:pass
 return d
def tree(pid,d):
 s={int(pid)}
 for _ in range(12):
  z={p for p,pp in d.items() if pp in s}
  if z<=s:break
  s|=z
 return s
def pss(pid,d):
 n=0
 for p in tree(pid,d):
  try:n+=int(next(x.split()[1] for x in pathlib.Path('/proc',str(p),'smaps_rollup').read_text().splitlines() if x.startswith('Pss:')))*1024
  except:pass
 return n
def rss(pid,d):
 n=0
 for p in tree(pid,d):
  try:n+=int(next(x.split()[1] for x in pathlib.Path('/proc',str(p),'status').read_text().splitlines() if x.startswith('VmRSS:')))*1024
  except:pass
 return n
def idle_cores():
 def snap():
  x=list(map(int,pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:]));return sum(x),x[3]+x[4]
 a,i=snap();time.sleep(.5);b,j=snap();return (os.cpu_count() or 1)*max(0,j-i)/max(1,b-a)
def running():
 c=sqlite3.connect('file:'+str(R/'registry.sqlite')+'?mode=ro',uri=True,timeout=5)
 try:return [json.loads(x[0]) for x in c.execute("SELECT record FROM tasks WHERE json_extract(record,'$.status')='running' ORDER BY key")]
 finally:c.close()
def verify_worker(t):
 p=t.get('pid');ticks0=t.get('process_start_ticks');req=t.get('request_path')
 if not p or not ticks0 or ticks(p)!=str(ticks0):raise RuntimeError('worker PID/start ticks not verifiable')
 a=argv(p)
 if 'worker.py' not in ' '.join(a) or req not in a:raise RuntimeError('worker argv/request does not match registry')
 if uid(p)!=os.getuid():raise RuntimeError('worker UID mismatch')
 cfg=json.loads(pathlib.Path(req).read_text())
 if cfg.get('task',{}).get('key')!=t['key'] or cfg.get('attempt_id')!=t.get('attempts',[])[-1].get('attempt_id'):raise RuntimeError('worker request identity mismatch')
 return a
def resource_gate():
 ts=running(); before={}
 if not ts:raise RuntimeError('no verified controller-owned workers available for admission accounting')
 identities={t['key']:{'pid':t.get('pid'),'start_ticks':t.get('process_start_ticks'),'argv':verify_worker(t),'request_path':t.get('request_path')} for t in ts}
 d=procs()
 for t in ts:before[t['key']]=pss(t['pid'],d)
 available=mem(); d=procs()
 after={t['key']:pss(t['pid'],d) for t in ts}
 unspent=sum(max(0,int(t.get('admission_reservation_bytes') or 10*G)-min(before[t['key']],after[t['key']])) for t in ts)
 coldprocs=procs()
 cold_active=any(any('cold_auto_compaction.py' in z for z in argv(pid)) for pid in coldprocs)
 helper=int(1.5*G) if cold_active else 0
 remain=available-6*G-unspent-2*G-helper-(512*1024**2)-G
 idle=idle_cores()
 if remain<G:raise RuntimeError(f'RAM gate failed, remaining margin {remain}')
 if idle<3:raise RuntimeError(f'CPU gate failed, idle cores {idle:.2f}, require 3')
 for t in ts:
  if ticks(t['pid'])!=str(t['process_start_ticks']):raise RuntimeError('worker identity changed during PSS bracket')
 return {'observed_utc':now(),'mem_available_bytes':available,'running_workers':len(ts),
  'worker_reservations_bytes':sum(int(t.get('admission_reservation_bytes') or 10*G) for t in ts),
  'worker_identity_private':identities,'pss_before_bytes':before,'pss_after_bytes':after,'unspent_reservations_bytes':unspent,
  'host_reserve_bytes':6*G,'growth_margin_bytes':2*G,'compactor_helper_reservation_bytes':helper,
  'audit_reservation_bytes':512*1024**2,'required_residual_bytes':G,'remaining_margin_bytes':remain,
  'idle_cores':idle,'cpu_count':os.cpu_count(),'cpu_reserved':2,'cold_compactor_active':cold_active}
def cold_metadata_note(cold_doc, coldpath, cache_doc):
 archive=pathlib.Path(cold_doc['archive_path']); st=archive.stat(); matched=0; found=0; total=0
 for row in cold_doc.get('members',[]):
  total+=int(row.get('bytes',0)); rel=row.get('logical_path')
  if not rel: continue
  key=str(ROOT/rel); entry=cache_doc.get('files',{}).get(key)
  if entry is None: continue
  found+=1; ident=entry.get('cold_semantic_identity')
  expected={'archive_ctime_ns':st.st_ctime_ns,'archive_sha256':cold_doc.get('archive_sha256'),'backing':'cold_zip','bytes':row.get('bytes'),'crc32':row.get('crc32'),'header_offset':row.get('header_offset'),'member':row.get('archive_member'),'sha256':row.get('sha256')}
  if ident==expected: matched+=1
 return {'observed_utc':now(),'cold_manifest_sha256':sha(coldpath),'auditcache_sha256':sha(R/'auditcache.json'),
  'cold_archive_sha256_from_manifest':cold_doc.get('archive_sha256'),'cold_archive_stat_bytes':st.st_size,'cold_archive_stat_ctime_ns':st.st_ctime_ns,
  'cold_member_count':len(cold_doc.get('members',[])),'cold_logical_model_bytes':total,
  'canonical_auditcache_entries_for_cold_members':found,'cold_semantic_identity_matches_current_manifest':matched,
  'cold_semantic_identity_nonmatches_or_missing':len(cold_doc.get('members',[]))-matched}
def models(e,f,coldnames):
 out=[]
 for t in e:
  if t.get('kind')!='eval' or t.get('status')!='validated_terminal' or t.get('outcome')!='successful':continue
  ft=f.get(t.get('fit_key'))
  if not ft or ft.get('status')!='validated_terminal' or ft.get('outcome')!='successful':raise RuntimeError('evaluation fit parent is not validated successful')
  p=R/'artifacts'/t['fit_key']/'pipeline.joblib'
  if p.is_symlink() or not p.is_file():raise RuntimeError('selected pipeline missing or not regular')
  rel=p.resolve().relative_to(ROOT).as_posix()
  if rel in coldnames:raise RuntimeError('selected pipeline is cold-store member')
  ev=json.loads((R/'artifacts'/t['key']/'evaluation.json').read_text())
  h=sha(p)
  if not isinstance(ev.get('pipeline_sha256'),str) or not ev['pipeline_sha256'] or ev['pipeline_sha256']!=h:raise RuntimeError('pipeline SHA is missing or differs from saved evaluation metadata')
  out.append({'task_key':t['key'],'fit_key':t['fit_key'],'relative_path':rel,'bytes':p.stat().st_size,'sha256_before':h})
 return out
def child(planfile):
 os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
 sys.path.insert(0,str(R/'source'));sys.path.insert(0,str(ROOT/'project'))
 import audit_artifacts
 plan=json.loads(pathlib.Path(planfile).read_text())
 if sha(SRC)!=plan['auditor_sha']:raise RuntimeError('auditor source changed')
 if sha(R/'auditcache.json')!=plan['cache_sha']:raise RuntimeError('global audit cache changed before audit')
 eval_keys=[x['key'] for x in plan['selected_evaluations']];fit_keys=list(plan['selected_fit_parents'])
 cur_e,cur_f=dbread_selected(eval_keys,fit_keys)
 if regdigest(cur_e,cur_f)!=plan['selected_registry_scope_sha']:raise RuntimeError('selected terminal registry records changed after plan freeze')
 e=plan['selected_evaluations'];f=plan['selected_fit_parents']
 coldpath=R/'manifests/cold_model_store_manifest.json';cold=json.loads(coldpath.read_text());names=set()
 for x in cold.get('members',[]):names.update([x.get('logical_path'),*x.get('aliases',[])])
 ms=models(e,f,names)
 if len(ms)!=25:raise RuntimeError('expected 25 raw physical success pipelines')
 expected={x['relative_path']:x for x in plan['model_items']}
 for x in ms:
  if x['relative_path'] not in expected or x['sha256_before']!=expected[x['relative_path']]['sha256_before']:raise RuntimeError('selected model changed after plan freeze')
 bykey={x['key']:x for x in e};bykey.update(f)
 valid={x['key'] for x in e+list(f.values()) if x.get('status')=='validated_terminal' and x.get('outcome')=='successful'}
 auditor=audit_artifacts.Auditor(R,cold_store=None,require_calibration_replay=False)
 auditor.cache={'schema_version':1,'files':{},'tasks':{}};auditor.file_memo={}
 rows=[]
 for t in e:
  _,rec=auditor.evaluation_audit(t,bykey,valid,alias=False)
  iss=[x for x in auditor.issues if x.get('task_key')==t['key']]
  dia=[x for x in auditor.diagnostics if x.get('task_key')==t['key']]
  rows.append({'task_key':t['key'],'fit_key':t['fit_key'],'rep':t.get('rep'),'condition':t.get('condition'),
    'status':rec.get('status'),'test_n':rec.get('test_n'),'calibration_n':rec.get('calibration_n'),
    'issue_checks':[x.get('check') for x in iss],'diagnostic_checks':[x.get('check') for x in dia]})
 after=[]
 for x in ms:
  p=ROOT/x['relative_path'];h=sha(p);after.append({**x,'sha256_after':h,'bytes_after':p.stat().st_size})
  if h!=x['sha256_before'] or p.stat().st_size!=x['bytes']:raise RuntimeError('selected pipeline changed during audit')
 if sha(SRC)!=plan['auditor_sha'] or sha(R/'auditcache.json')!=plan['cache_sha']:raise RuntimeError('source or global cache changed during audit')
 report={'schema_version':'lamost-e4-arf-saved-outcome-audit/1','scope_snapshot_utc':plan['created_utc'],'audit_finished_utc':now(),
  'scope':{'planned_cells':45,'snapshot_state_counts':plan['state_counts'],'coverage_snapshot_sha256':plan['coverage_snapshot_sha256'],
   'coverage_rows':plan['coverage_rows'],'physical_successes_audited':25,'control_alias_successes':3,
   'scientific_failures':2,'unsupported':0,'waiting_for_dependency':15,
   'audited_keys':[x['task_key'] for x in rows],'alias_keys':plan['alias_keys'],'failure_keys':plan['failure_keys'],'pending_keys':plan['pending_keys'],
   'failure_summary':plan['failure_summary']},
  'auditor':{'source_sha256':plan['auditor_sha'],'version':audit_artifacts.VERSION,
   'api':'Auditor.evaluation_audit(t, bykey, validset, alias=False)','full_run_called':False,'global_cache_written':False,
   'model_deserialization_fit_prediction_generation_or_recalibration':False},
  'provenance':{'selected_registry_scope_sha256':plan['selected_registry_scope_sha'],'private_plan_file_sha256':sha(planfile),
   'private_plan_canonical_payload_sha256':plan['private_plan_canonical_sha256'],
   'cold_manifest_sha256_at_plan':plan['cold_manifest_sha'],'cold_member_count_at_plan':plan['cold_member_count'],
   'selected_models_raw_regular_non_symlink_not_cold':True,'selected_model_bytes':sum(x['bytes'] for x in after),
   'selected_model_hashes_before_after':after,'global_auditcache_sha256_before':plan['cache_sha'],'global_auditcache_unchanged':True,
   'cold_cli_deferral_note':plan['cold_cli_deferral_note']},
  'results':{'outcome_rows':len(rows),'rows_with_issues':sum(bool(x['issue_checks']) for x in rows),
   'issue_count':sum(len(x['issue_checks']) for x in rows),'diagnostic_limitation_count':sum(len(x['diagnostic_checks']) for x in rows),'rows':rows},
  'limitations':['Saved artifact, role, metric, and integrity checks only; no selected-model internals, calibration-q replay, or score recomputation.',
   'This does not complete E4 and is not a global artifact audit. Failures and pending cases remain as observed.']}
 atomic(OUT/'E4_ARF_SAVED_OUTCOME_AUDIT_20261027.json',report)
 return 0

def main():
 if len(sys.argv)>1 and sys.argv[1]=='--child':return child(sys.argv[2])
 OUT.mkdir(parents=True,exist_ok=True);PRIV.mkdir(parents=True,exist_ok=True)
 if (OUT/'E4_ARF_SAVED_OUTCOME_AUDIT_20261027.json').exists():raise RuntimeError('scoped audit report already exists; no automatic rerun')
 lock=(PRIV/'audit.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if sha(SRC)!=SRC_SHA:raise RuntimeError('current audit source SHA does not match authorized version')
 guard=R/'tests/run_guarded_tests.py';guard_sha=sha(guard)
 if guard_sha!='9e102435d2bce80c8f071338d2d1d0f1f5fb9bfa8542c59f828f19568308a89c':raise RuntimeError('tested existing guard source changed')
 coverage,selected,fits=db_snapshot();state=dict(collections.Counter(x.get('outcome') or x.get('status') for x in coverage))
 aliases=[x['key'] for x in coverage if x.get('kind')=='alias' and x.get('outcome')=='successful']
 failures=[x['key'] for x in coverage if x.get('status')=='validated_terminal' and x.get('outcome')=='scientific_failure']
 pending=[x['key'] for x in coverage if x.get('status')=='waiting_for_dependency']
 if len(coverage)!=45 or state!={'successful':28,'scientific_failure':2,'waiting_for_dependency':15}:raise RuntimeError(f'unexpected E4 ARF coverage snapshot: {state}')
 selected_keys=[x['key'] for x in selected]
 if len(selected)!=25 or len(fits)!=25 or len(aliases)!=3 or len(failures)!=2 or len(pending)!=15:raise RuntimeError('expected 25 physical success,3 aliases,2 failures,15 pending')
 coverage_rows=[{'task_key':x['key'],'kind':x.get('kind'),'status':x.get('status'),'outcome':x.get('outcome'),
   'fit_key':x.get('fit_key'),'source_key':x.get('source_key'),'rep':x.get('rep'),'condition':x.get('condition')} for x in coverage]
 coverage_sha=coverage_digest(coverage_rows)
 selected_sha=regdigest(selected,fits)
 coldpath=R/'manifests/cold_model_store_manifest.json';cold=json.loads(coldpath.read_text());coldnames=set()
 for x in cold.get('members',[]):coldnames.update([x.get('logical_path'),*x.get('aliases',[])])
 ms=models(selected,fits,coldnames)
 if len(ms)!=25:raise RuntimeError('selected physical pipeline count differs from 25')
 cache_sha=sha(R/'auditcache.json');cold_sha=sha(coldpath);cache_doc=json.loads((R/'auditcache.json').read_text())
 metadata_note=cold_metadata_note(cold,coldpath,cache_doc)
 failure_summary=[
  {'task_key':'e4/rep_1/eval/direct/arf/A_tenth','outcome':'scientific_failure','phase':'evaluation','observed_seconds':600.269992878,'reason':'evaluation phase reached configured 600-second limit; raw operational receipt omitted'},
  {'task_key':'e4/rep_1/eval/direct/arf/K_tenth','outcome':'scientific_failure','phase':'evaluation','observed_seconds':600.194036929,'reason':'evaluation phase reached configured 600-second limit; raw operational receipt omitted'}]
 plan={'created_utc':now(),'selected_evaluations':selected,'selected_fit_parents':fits,'state_counts':state,
   'coverage_rows':coverage_rows,'coverage_snapshot_sha256':coverage_sha,'selected_registry_scope_sha':selected_sha,
   'alias_keys':aliases,'failure_keys':failures,'pending_keys':pending,
   'auditor_sha':SRC_SHA,'cache_sha':cache_sha,'cold_manifest_sha':cold_sha,
   'cold_member_count':len(cold.get('members',[])),'model_items':ms,'failure_summary':failure_summary,
   'cold_cli_deferral_note':{'earlier_global_cli_observation':{'cold_members':127,'cold_logical_model_bytes':29262270392,'matching_cache_identities':0,
    'duration_seconds':295.9,'peak_rss_bytes':296419328,'auditor_source_sha_prefix':'06196d','historical_observation_time':'not captured in this scoped run'},
    'current_metadata_inputs':metadata_note,'current_scoped_source_sha256':SRC_SHA,
    'interpretation':'Global CLI is deferred because its whole-project cold model pass would decode cold artifacts under the global cold-reader lease; this scoped audit accesses selected raw E4 ARF pipelines only.'}}
 plan['private_plan_canonical_sha256']=hashlib.sha256(canon(plan)).hexdigest()
 planfile=PRIV/'frozen_scoped_plan.json';atomic(planfile,plan);plan_file_sha=sha(planfile)
 try:gate=resource_gate()
 except Exception as exc:
  (PRIV/'resource_gate_refusal.json').write_text(json.dumps({'observed_utc':now(),'error_type':type(exc).__name__,'reason':str(exc),
   'planned_cells':45,'selected_eval_count':len(selected),'model_bytes':sum(x['bytes'] for x in ms),'auditor_sha256':SRC_SHA,
   'selected_registry_scope_sha256':selected_sha,'coverage_snapshot_sha256':coverage_sha,'auditcache_sha256':cache_sha,
   'cold_manifest_sha256':cold_sha,'private_plan_file_sha256':plan_file_sha},indent=2,sort_keys=True)+'\n')
  raise
 (PRIV/'preflight_receipt.json').write_text(json.dumps({'observed_utc':now(),'resource_gate':gate,'planned_cells':45,
   'physical_pipeline_count':len(ms),'pipeline_bytes':sum(x['bytes'] for x in ms),'selected_registry_scope_sha256':selected_sha,
   'coverage_snapshot_sha256':coverage_sha,'audit_source_sha256':SRC_SHA,'auditcache_sha256':cache_sha,
   'cold_manifest_sha256':cold_sha,'cold_metadata_note':metadata_note,'guard_script_sha256':guard_sha,
   'private_plan_file_sha256':plan_file_sha},indent=2,sort_keys=True)+'\n')
 env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
 log=PRIV/'guarded_audit.log';started=now();mono=time.monotonic()
 cmd=[sys.executable,str(guard),'--rss-bytes',str(MAXRSS),'--wall-seconds',str(MAXWALL),'--grace-seconds',str(GRACE),
   '--','/usr/bin/nice','-n','19',sys.executable,str(pathlib.Path(__file__).resolve()),'--child',str(planfile)]
 cp=subprocess.run(cmd,cwd=str(ROOT),env=env,capture_output=True,text=True)
 finished=now();wall=time.monotonic()-mono
 log.write_text('STDOUT\n'+cp.stdout+'\nSTDERR\n'+cp.stderr)
 lines=[x for x in cp.stdout.splitlines() if x.strip()]
 guard_result=json.loads(lines[-1]) if lines else None
 if not isinstance(guard_result,dict) or guard_result.get('schema')!='lamost-bounded-test-run/1':
  raise RuntimeError('existing guarded runner returned no valid bounded-run receipt; see private log')
 (PRIV/'supervisor_receipt.json').write_text(json.dumps({'started_utc':started,'finished_utc':finished,
  'wall_seconds_observed':round(wall,3),'guard_script_sha256':guard_sha,'guard_command_argv':cmd,
  'guard_return_code':cp.returncode,'guard_result':guard_result},indent=2,sort_keys=True)+'\n')
 if cp.returncode!=0 or guard_result.get('exit_code')!=0 or guard_result.get('reason') is not None:
  raise RuntimeError('existing guard reports bounded child failure; preserve evidence and do not retry')
 p=OUT/'E4_ARF_SAVED_OUTCOME_AUDIT_20261027.json';report=json.loads(p.read_text())
 report['supervision']={'started_utc':started,'finished_utc':finished,'wall_seconds':guard_result.get('wall_seconds'),
  'peak_process_tree_rss_bytes':guard_result.get('peak_process_tree_rss_bytes'),'rss_cap_bytes':MAXRSS,
  'wall_cap_seconds':MAXWALL,'termination_grace_seconds':GRACE,'guard_source_sha256':guard_sha,
  'guard_reason':guard_result.get('reason'),'exit_code':guard_result.get('exit_code'),'nice':19,'native_threads':1}
 report['resource_preflight_summary']={'mem_available_bytes':gate['mem_available_bytes'],'remaining_margin_bytes':gate['remaining_margin_bytes'],
  'unspent_worker_reservations_bytes':gate['unspent_reservations_bytes'],'helper_reservation_bytes':gate['compactor_helper_reservation_bytes'],
  'audit_reservation_bytes':gate['audit_reservation_bytes'],'idle_cores':gate['idle_cores'],'cpu_reserved':2,
  'cold_compactor_active':gate['cold_compactor_active']}
 atomic(p,report)
 (OUT/'REPRODUCE.md').write_text('# E4 ARF saved-outcome audit\n\nOn EC2, run from the migration root with the frozen venv: /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python runtime_20261025/reports/e4_arf_saved_outcome_audit_20261027/audit_e4_arf_saved_outcomes.py\n\nThis re-snapshots current E4 direct-ARF tasks and refuses if the selected terminal scope, source, selected raw models, or resource admission differs. It calls only Auditor.evaluation_audit and never writes the global audit cache.\n')
 return 0

if __name__=='__main__':
 try:sys.exit(main())
 except Exception as e:print('SCOPED_AUDIT_ABORTED: '+type(e).__name__+': '+str(e),file=sys.stderr);sys.exit(2)

