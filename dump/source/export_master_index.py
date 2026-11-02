import pathlib,json,hashlib,datetime,collections
R=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def atomic(p,x):
 t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,indent=2,sort_keys=True,default=str)+'\n');t.replace(p)

def _parse_utc(value):
 if value is None:return None
 try:
  if isinstance(value,(int,float)):return datetime.datetime.fromtimestamp(float(value),datetime.timezone.utc)
  text=str(value).strip().replace('Z','+00:00');dt=datetime.datetime.fromisoformat(text)
  return dt.replace(tzinfo=datetime.timezone.utc) if dt.tzinfo is None else dt.astimezone(datetime.timezone.utc)
 except (TypeError,ValueError,OverflowError):return None

def resource_policy_for(task,freeze,attempt=None):
 # Captured attempt metadata is most specific. For older attempts with a start time,
 # history wins over the task's latest admission snapshot so a later admission cannot
 # retroactively change the recorded profile of a prior attempt.
 if isinstance(attempt,dict) and isinstance(attempt.get('resource_profile'),dict):return dict(attempt['resource_profile']),'attempt_snapshot'
 status=str(task.get('status','')).lower()
 current=freeze.get('resource_policy')
 # Planned/waiting work has no current attempt: use prospective policy despite old interrupted metadata.
 if attempt is None and status in {'planned','waiting_for_dependency'} and isinstance(current,dict):return dict(current),'prospective_current_policy'
 if attempt is None and isinstance(task.get('admission_resource_policy'),dict):return dict(task['admission_resource_policy']),'task_admission_snapshot'
 history=list(freeze.get('resource_policy_history') or [])
 current=freeze.get('resource_policy');current_from=freeze.get('resource_policy_effective_from_utc')
 if isinstance(current,dict) and current_from and not any(x.get('effective_from_utc')==current_from and x.get('policy')==current for x in history if isinstance(x,dict)):
  history.append({'effective_from_utc':current_from,'effective_until_utc':None,'policy':current,'reason':'current prospective resource policy'})
 observed=attempt.get('started_utc') if isinstance(attempt,dict) else task.get('started_utc')
 if observed is None and isinstance(attempt,dict):observed=attempt.get('started_epoch')
 if observed is None:observed=task.get('started_utc') or task.get('started_epoch')
 when=_parse_utc(observed)
 if when is not None and history:
  for item in sorted((x for x in history if isinstance(x,dict)),key=lambda x:_parse_utc(x.get('effective_from_utc')) or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)):
   start=_parse_utc(item.get('effective_from_utc'));end=_parse_utc(item.get('effective_until_utc'))
   if start is not None and start<=when and (end is None or when<end) and isinstance(item.get('policy'),dict):return dict(item['policy']),'resource_policy_history_by_attempt_start'
  return None,'started_attempt_outside_recorded_policy_history'
 if isinstance(task.get('admission_resource_policy'),dict):return dict(task['admission_resource_policy']),'task_admission_snapshot'
 if status in {'planned','waiting_for_dependency'} and isinstance(current,dict):return dict(current),'prospective_current_policy'
 if not history and isinstance(current,dict):return dict(current),'single_frozen_policy_no_history'
 return None,'resource_policy_not_evidenced'

def main():
 registry=json.loads((R/'registry.json').read_text());cache=json.loads((R/'cache/cache_manifest.json').read_text());freeze=json.loads((R/'manifests/freeze.json').read_text())
 plan=json.loads((R/'manifests/tasks.json').read_text());defs={t['key']:t for t in plan['tasks']}
 rows=[]
 for t in registry['tasks']:
  d=defs[t['key']];r=dict(t);rep=str(t.get('rep'))
  for k in ['pid','process_start_ticks','request_path','result_path','result','started_epoch','orphan_term_epoch','forced_term_epoch']:r.pop(k,None)
  result=t.get('result') or {}
  profile,profile_source=resource_policy_for(t,freeze)
  r.update(protocol_version=freeze['protocol_version'],dataset_manifest_sha256=cache['baseline_manifest_sha256'],role_hashes=cache['roles'].get(rep,{}).get('id_hashes',{}),configuration_sha256=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest(),frozen_plan_sha256=freeze['plan_sha256'],actual_engine_code_sha256=result.get('engine_code_sha256'),actual_validator_sha256=(result.get('validation') or {}).get('code_sha256'),planned_execution_code_sha256=freeze['source_sha256'] if t['status'] in ['planned','waiting_for_dependency'] else None,resource_profile=profile,resource_profile_source=profile_source,model_provenance=d.get('source_metadata') or {'kind':'later_experiment_owned','fit_key':d.get('fit_key'),'selection_source':d.get('selection_source'),'selection_key':d.get('selection_key')},artifact_paths={'directory':t['artifact_dir']},attempt_identity=result.get('attempt_id'),retry_reason=t.get('reason'))
  exported_attempts=[]
  for a in t.get('attempts',[]):
   q={k:v for k,v in a.items() if k not in ['request_path','result_path','pid','process_start_ticks']}
   ap,aps=resource_policy_for(t,freeze,a)
   if ap is not None:q.setdefault('resource_profile',ap)
   q['resource_profile_source']=aps
   exported_attempts.append(q)
  r['attempts']=exported_attempts
  if result.get('validation'):r['artifact_validation']=result['validation']
  rows.append(r)
 atomic(R/'master_index.json',{'schema_version':1,'observed_utc':registry['observed_utc'],'exported_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'authoritative_state_registry':'registry.sqlite with actual-process controller','resource_policy_history':freeze.get('resource_policy_history',[]),'resource_policy_effective_from_utc':freeze.get('resource_policy_effective_from_utc'),'current_prospective_resource_policy':freeze.get('resource_policy'),'tasks':rows})
 questions={3:'Direct Bayes versus synthetic-only versus real-only under matched real-data access',4:'Reducing support for each class and restoring its original share',5:'Fitting-only feature-noise/missingness/label-noise robustness with frozen clean configurations',6:'Equal and tuning-selected global posterior ensembles'}
 for e in (3,4,5,6):
  tasks=[d for d in defs.values() if d['experiment']==e]
  target=R/'manifests'/f'E{e}_MANIFEST.json'
  immutable={'experiment':e,'question':questions[e],'protocol_version':freeze['protocol_version'],'source_frozen_plan_sha256':freeze['plan_sha256'],'source_authorization':'authorization_and_decisions.json','design_origin':'Export of design, tasks, roles and decisions frozen before new later-experiment test evaluation; export does not change design','original_plan_freeze_utc':freeze['frozen_utc'],'planned_task_count':len(tasks),'planned_scientific_cases':sum(bool(t.get('scientific_case')) for t in tasks),'budgets':[100000],'repetitions':3,'fit_rows':80000,'tuning_rows':10000,'calibration_rows':10000,'test_rows':500000,'features':cache['features'],'label_order':cache['labels'],'role_hashes':cache['roles'],'resource_policy':freeze['resource_policy'],'bootstrap':False,'test_information_history':freeze['test_information_history'],'implementation_defaults':{'E4_100k_budget':True,'E5_100k_budget_and_3repetitions':True,'E6_100k_budget_and_3repetitions_and_weight_search':True,'downstream_preprocessing':'own permitted training source in native predictors','corruption_floor_native_units':1e-12,'target_add_rounding':'nearest integer, half upward','trials':'fixed established domains;10ordinary,5declaredexpensive;3startup;no replacement failures'}}
  if not target.exists():atomic(target,immutable)
 print(json.dumps({'master_index_tasks':len(rows),'observed_utc':registry['observed_utc']}))
if __name__=='__main__':main()
