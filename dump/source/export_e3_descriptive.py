#!/usr/bin/env python3
"""Data-only E3 descriptive exporter; never loads a model or predicts."""
import argparse, csv, datetime, hashlib, json, math, re, statistics
from pathlib import Path
from zoneinfo import ZoneInfo
from cold_report_access import inspect_pipeline, ArtifactIdentityError

LABELS=['A','F','G','K','M','GALAXY','QSO']
METRICS=('balanced_accuracy','coverage','set_size')
OFFLINE_PARTIAL_PROJECTION={}
OFFLINE_PARTIAL_PROJECTION_USED_KEYS=set()

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def read_json(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def csv_rows(p):
 with Path(p).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def write_csv(p,rows,fields):
 with Path(p).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def parse_time(value):
 if not value:return None
 return datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
def elapsed(a,b):
 x,y=parse_time(a),parse_time(b)
 return max(0.0,(y-x).total_seconds()) if x and y else None
def fmt(x):return '' if x is None else format(float(x),'.12g')
def mean(vals):return statistics.mean(vals) if vals else None
def sd(vals):return statistics.stdev(vals) if len(vals)>1 else None

def trial_accounting(selection_path):
 if not selection_path.exists():
  return {'state':'selection_history_unavailable','slot_n':None,'physical_duration_n':0,'physical_duration_missing_n':None,'physical_seconds':None,'cached_slot_n':0,'cached_elapsed_seconds':None}
 try:obj=read_json(selection_path)
 except Exception:
  return {'state':'selection_history_unreadable','slot_n':None,'physical_duration_n':0,'physical_duration_missing_n':None,'physical_seconds':None,'cached_slot_n':0,'cached_elapsed_seconds':None}
 slots=obj.get('trials',[]);physical=[];cached=[];missing=0
 for tr in slots:
  value=None
  if 'seconds' in tr:
   try:value=float(tr['seconds'])
   except Exception:pass
  if value is None:
   err=str(tr.get('error',''))
   m=re.search(r"['\"]seconds['\"]\s*:\s*([0-9]+(?:\.[0-9]+)?)",err)
   if m:value=float(m.group(1))
  if tr.get('status')=='duplicate_cached':
   if value is not None:cached.append(value)
  elif value is None:missing+=1
  else:physical.append(value)
 state='duration_limited_lower_bound' if missing else ('observed' if physical else 'no_physical_trial_duration_observed')
 return {'state':state,'slot_n':len(slots),'physical_duration_n':len(physical),'physical_duration_missing_n':missing,'physical_seconds':sum(physical) if physical else None,'cached_slot_n':sum(1 for tr in slots if tr.get('status')=='duplicate_cached'),'cached_elapsed_seconds':sum(cached) if cached else None}

def artifact_dir_for(task,runtime):
 key=task.get('key')
 if not key:raise ValueError('artifact path remapping requires a task key')
 rt=Path(runtime).resolve();expected=(rt/'artifacts'/key).resolve()
 try:expected.relative_to(rt)
 except ValueError:raise ValueError('task artifact key escapes runtime')
 raw=task.get('artifact_dir')
 if raw:
  source=Path(raw)
  if source.is_absolute():
   source_parts=source.parts
  else:
   source_parts=(rt/source).parts
  try:i=max(i for i,part in enumerate(source_parts) if part=='artifacts')
  except ValueError:raise ValueError('artifact path lacks artifacts component for '+str(key))
  suffix=Path(*source_parts[i+1:])
  if suffix.as_posix()!=str(key):raise ValueError('artifact path/key mismatch for '+str(key))
 return expected


def policy_at(ts,freeze):
 t=parse_time(ts)
 if not t:return 'unknown'
 for item in freeze.get('resource_policy_history',[]):
  start=parse_time(item.get('effective_from_utc'));end=parse_time(item.get('effective_until_utc'))
  if start and t>=start and (end is None or t<end):
   pol=item.get('policy',{})
   if pol.get('max_workers')==2:return 'initial_two_worker_policy'
   if pol.get('queue_packing'):return 'adaptive_peak_safe_queue_packing'
   return 'adaptive_cpu_memory_policy'
 return 'policy_history_unmatched'
def task_start(t):
 attempts=t.get('attempts') or []
 return (attempts[-1].get('started_utc') if attempts else None) or t.get('started_utc')
def task_result(t):
 return (t.get('result') or {}).get('result') or {}
def safe_json(x):return json.dumps(x,separators=(',',':'),sort_keys=True)
def phase_observation(task,stage,rt,cost_index):
 result=task.get('result') or {};engine_id=result.get('attempt_id')
 if not engine_id:
  return {'seconds':None,'peak_tree_rss_kib':None,'exit_code':None,'reason':'not_started_unavailable_dependency' if task.get('outcome')=='unavailable_dependency' else 'engine_attempt_id_unavailable','source':'not_observed'}
 logical='calibration' if stage=='calibration' else 'test_inference'
 phase_name='calibrate' if stage=='calibration' else 'evaluate'
 path=artifact_dir_for(task,rt)/'attempts'/str(engine_id)/f'phase_{phase_name}_result.json'
 key=(task['key'],str(engine_id),logical);row=cost_index.get(key)
 if path.is_file():
  obj=read_json(path)
  if obj.get('phase')!=phase_name:raise SystemExit(f'phase receipt name mismatch {task["key"]} {stage}')
  sec=float(obj['seconds']) if obj.get('seconds') is not None else None
  peak=int(obj['peak_tree_rss_kib']) if obj.get('peak_tree_rss_kib') is not None else None
  if row and row.get('phase_seconds') not in (None,'') and sec is not None and not math.isclose(float(row['phase_seconds']),sec,rel_tol=1e-10,abs_tol=1e-8):raise SystemExit(f'cost table/phase receipt duration mismatch {task["key"]} {stage}')
  if row and row.get('peak_tree_rss_kib') not in (None,'') and peak is not None and int(float(row['peak_tree_rss_kib']))!=peak:raise SystemExit(f'cost table/phase receipt RSS mismatch {task["key"]} {stage}')
  return {'seconds':sec,'peak_tree_rss_kib':peak,'exit_code':obj.get('exit_code'),'reason':obj.get('reason'),'source':'attempt_phase_receipt:'+str(path),'engine_attempt_id':str(engine_id)}
 if row and row.get('phase_observation_status')=='observed' and row.get('phase_seconds') not in (None,''):
  return {'seconds':float(row['phase_seconds']),'peak_tree_rss_kib':int(float(row['peak_tree_rss_kib'])) if row.get('peak_tree_rss_kib') else None,'exit_code':int(row['phase_exit_code']) if row.get('phase_exit_code') else None,'reason':row.get('phase_reason') or None,'source':'validated_costs.csv_exact_attempt_key','engine_attempt_id':str(engine_id)}
 return {'seconds':None,'peak_tree_rss_kib':None,'exit_code':None,'reason':'phase_receipt_and_cost_table_row_unavailable','source':'not_observed','engine_attempt_id':str(engine_id)}



def verified_cutoff_trial_history(task,cutoff,runtime):
 rt=Path(runtime).resolve();key=task.get('key')
 if cutoff.get('task_key')!=key:raise ValueError('terminal cutoff task key mismatch')
 attempts=task.get('attempts') or []
 if not attempts or attempts[-1].get('attempt_id')!=cutoff.get('attempt_id'):
  raise ValueError('terminal cutoff does not match latest controller attempt for '+str(key))
 if cutoff.get('source_file_hashes_unchanged')!='True':raise ValueError('cutoff source hashes were not stable for '+str(key))
 before=json.loads(cutoff.get('source_file_sha256_before') or '{}')
 after=json.loads(cutoff.get('source_file_sha256_after') or '{}')
 if not before or before!=after:raise ValueError('cutoff before/after hash maps differ for '+str(key))
 verified=0
 for rel,digest in before.items():
  q=(rt/rel).resolve()
  try:q.relative_to(rt)
  except ValueError:raise ValueError('cutoff evidence path escapes runtime for '+str(key))
  if not q.is_file() or sha(q)!=digest:raise ValueError('cutoff evidence hash mismatch for '+str(key)+' '+str(rel))
  verified+=1
 hist_rel=cutoff.get('trial_history_path')
 if not hist_rel:raise ValueError('cutoff lacks retained trial history path for '+str(key))
 hist=(rt/hist_rel).resolve()
 try:hist.relative_to(rt)
 except ValueError:raise ValueError('trial history path escapes runtime for '+str(key))
 if not hist.is_file():raise ValueError('retained trial history is missing for '+str(key))
 rel=hist.relative_to(rt).as_posix()
 if rel not in before or sha(hist)!=before[rel]:raise ValueError('retained trial history hash does not match cutoff evidence for '+str(key))
 engine_id=cutoff.get('artifact_attempt_id')
 if not engine_id:raise ValueError('cutoff lacks engine attempt identity for '+str(key))
 attempt_json=rt/'artifacts'/key/'attempts'/engine_id/'attempt.json'
 if not attempt_json.is_file() or read_json(attempt_json).get('attempt_id')!=engine_id:
  raise ValueError('cutoff engine attempt identity does not match its attempt artifact for '+str(key))
 obj=read_json(hist);trials=obj.get('trials',[])
 try:indices=json.loads(cutoff.get('completed_trial_indices') or '[]')
 except Exception:raise ValueError('invalid completed trial index list for '+str(key))
 if len(trials)!=int(cutoff.get('completed_trial_count') or -1) or indices!=list(range(len(trials))):
  raise ValueError('partial history trial slots do not match cutoff completed indices for '+str(key))
 try:reported_statuses=json.loads(cutoff.get('completed_trial_statuses') or '{}')
 except Exception:raise ValueError('invalid completed trial status summary for '+str(key))
 actual_statuses={status:sum(1 for x in trials if x.get('status')==status) for status in sorted({x.get('status') for x in trials})}
 if reported_statuses!=actual_statuses:raise ValueError('partial history status counts do not match cutoff for '+str(key))
 aborted=cutoff.get('aborted_trial_index')
 if aborted not in (None,'') and int(aborted)<len(trials):raise ValueError('aborted trial incorrectly appears as a completed slot for '+str(key))
 if cutoff.get('not_attempted_trial_number_assigned') not in ('False',False):raise ValueError('cutoff assigned a number to an unattempted slot for '+str(key))
 account=trial_accounting(hist)
 account['state']='verified_terminal_cutoff_partial_history'
 account['history_sha256']=sha(hist);account['history_provenance']='verified_terminal_cutoff_partial_history'
 account['completed_slot_n']=len(trials);account['aborted_trial_index']=int(aborted) if aborted not in (None,'') else None
 account['aborted_trial_last_observed_seconds']=float(cutoff['aborted_trial_last_observed_elapsed_seconds']) if cutoff.get('aborted_trial_last_observed_elapsed_seconds') not in (None,'') else None
 account['unattempted_slot_n']=len(json.loads(cutoff.get('unattempted_nominal_slot_indices') or '[]'))
 account['verified_cutoff_evidence_file_n']=verified
 return account

def trial_accounting_for_fit(task,runtime,cutoff_by_task):
 if task and task.get('key') in OFFLINE_PARTIAL_PROJECTION:
  from offline_projection_adapter import accounting_from_projection
  projection=OFFLINE_PARTIAL_PROJECTION[task['key']]
  cutoff=cutoff_by_task.get(task.get('key'))
  evidence=projection.get('raw_evidence_files') or []
  private=[x for x in evidence if re.fullmatch(r'phase_trial_\d+_(?:result|state)\.json',Path(x['runtime_relative_path']).name) or Path(x['runtime_relative_path']).name=='request.json']
  private_present=[(Path(runtime)/x['runtime_relative_path']).is_file() for x in private]
  if any(private_present):
   if not all(private_present):raise SystemExit('partial raw private phase evidence present; strict live gate required and projection fallback refused for '+str(task.get('key')))
   if not cutoff:raise SystemExit('raw private evidence exists but terminal cutoff is unavailable; projection fallback refused')
   live=verified_cutoff_trial_history(task,cutoff,runtime)
   if live.get('history_sha256')!=projection.get('selection_source_sha256'):
    raise SystemExit('live raw selection differs from archived projection source')
   before=json.loads(cutoff.get('source_file_sha256_before') or '{}')
   ev=[{'runtime_relative_path':k,'source_sha256':v} for k,v in sorted(before.items())]
   digest=hashlib.sha256(json.dumps(ev,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
   if digest!=projection.get('raw_evidence_set_sha256'):raise SystemExit('live raw evidence set differs from archived projection')
   return live
  OFFLINE_PARTIAL_PROJECTION_USED_KEYS.add(task['key'])
  return accounting_from_projection(projection,runtime,task,cutoff)
 if not task:return {'state':'dependency_unavailable','slot_n':None,'completed_slot_n':None,'physical_duration_n':0,'physical_duration_missing_n':None,'physical_seconds':None,'cached_slot_n':0,'cached_elapsed_seconds':None,'history_sha256':'','history_provenance':'unavailable'}
 path=artifact_dir_for(task,runtime)/'selection.json'
 if path.is_file():
  a=trial_accounting(path);a['state']='published_selection_history' if a['state']=='observed' else a['state']
  a['history_sha256']=sha(path);a['history_provenance']='published_selection_history';a['completed_slot_n']=a['slot_n'];a['aborted_trial_index']=None;a['aborted_trial_last_observed_seconds']=None;a['unattempted_slot_n']=0
  return a
 cutoff=cutoff_by_task.get(task.get('key'))
 if cutoff:return verified_cutoff_trial_history(task,cutoff,runtime)
 a=trial_accounting(path);a['history_sha256']='';a['history_provenance']=a['state'];a['completed_slot_n']=0;a['aborted_trial_index']=None;a['aborted_trial_last_observed_seconds']=None;a['unattempted_slot_n']=0
 return a

def public_reasons(task, fit):
 outcome=task.get('outcome') or task.get('status') or 'unknown'
 if outcome=='successful': return '', ''
 raw=str(task.get('reason') or '').lower()
 fit_outcome=(fit or {}).get('outcome') or (fit or {}).get('status') or ''
 fit_raw=str((fit or {}).get('reason') or '').lower()
 fit_reason=''
 if fit and fit_outcome!='successful':
  if 'memory policy exceeded' in fit_raw or 'memory limit' in fit_raw:
   fit_reason='fixed worker process-tree memory limit exceeded during fitting'
  elif 'timeout' in fit_raw:
   fit_reason='fixed fitting or tuning timeout reached'
  elif fit_outcome=='unsupported':
   fit_reason='method unsupported under the recorded implementation'
  else:
   fit_reason='fit dependency ended as '+str(fit_outcome)
 if outcome=='unavailable_dependency':
  dep=(task.get('dependencies') or [task.get('fit_key') or 'required fit'])[0]
  return 'required model dependency did not complete; evaluation unavailable ('+str(dep)+')', fit_reason
 if 'phase_timeout' in raw or 'timeout' in raw:
  return 'evaluation phase timed out at the fixed 600-second limit', fit_reason
 if 'memory policy exceeded' in raw or 'memory limit' in raw:
  return 'worker process-tree memory limit exceeded during evaluation', fit_reason
 if outcome=='unsupported': return 'method unsupported under the recorded implementation', fit_reason
 return 'evaluation ended as '+str(outcome), fit_reason

def write_table(rows,out,report):
 rt=out.parent.parent
 project=report.parent.parent.parent/'project'
 # CLI supplies absolute paths; these are replaced below in main.

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--runtime',type=Path,required=True);ap.add_argument('--project',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--partial-projection',type=Path)
 a=ap.parse_args();rt=a.runtime.resolve();project=a.project.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 global OFFLINE_PARTIAL_PROJECTION,OFFLINE_PARTIAL_PROJECTION_USED_KEYS
 OFFLINE_PARTIAL_PROJECTION_USED_KEYS=set()
 if a.partial_projection: OFFLINE_PARTIAL_PROJECTION=read_json(a.partial_projection).get('partials',{})
 registry=read_json(rt/'registry.json');freeze=read_json(rt/'manifests/freeze.json');manifest=read_json(rt/'manifests/E3_MANIFEST.json')
 plan=json.loads((rt/'manifests/tasks.json').read_text(encoding='utf-8'));plan_tasks=plan.get('tasks',plan) if isinstance(plan,dict) else plan
 plan_e3={t['key']:t for t in plan_tasks if int(t.get('experiment',0) or 0)==3}
 reg_e3={t['key']:t for t in registry['tasks'] if int(t.get('experiment',0) or 0)==3}
 cases={k:t for k,t in plan_e3.items() if t.get('scientific_case')}
 reg_cases={k:t for k,t in reg_e3.items() if t.get('scientific_case')}
 if len(plan_e3)!=153 or len(cases)!=69 or len(reg_e3)!=153 or set(reg_cases)!=set(cases):raise SystemExit('E3 plan/registry keys or counts mismatch')
 if any(t.get('status')!='validated_terminal' for t in reg_e3.values()):raise SystemExit('E3 plan still has nonterminal dependencies')
 nonterminal=[(k,t.get('status')) for k,t in reg_cases.items() if t.get('status')!='validated_terminal']
 if nonterminal:raise SystemExit('E3 has nonterminal planned cases: '+repr(nonterminal[:5]))
 all_fits={k:t for k,t in reg_e3.items() if t.get('kind')=='fit'}
 all_gens={k:t for k,t in reg_e3.items() if t.get('kind')=='generate'}
 reuse_component=csv_rows(rt/'reports/E3_REUSED_E2_PREDICTIVE_COMPONENTS.csv')
 reuse_scores=csv_rows(rt/'reports/E3_REUSED_E2_CLASSIFICATION_CONSISTENCY.csv')
 terminal_cutoff_rows=[x for x in csv_rows(rt/'reports/terminal_trial_cutoffs.csv') if x.get('experiment')=='3']
 cutoff_by_task={x['task_key']:x for x in terminal_cutoff_rows if x.get('task_key')}
 reuse_component_by={(int(x['repetition']),x['method']):x for x in reuse_component}
 cost_rows=[x for x in csv_rows(rt/'reports/costs.csv') if x.get('experiment')=='3']
 cost_index={(x.get('task_key',''),x.get('attempt_id',''),x.get('logical_stage','')):x for x in cost_rows if x.get('task_key') and x.get('attempt_id')}
 by_eval={};case_rows=[]
 for key,task in sorted(reg_cases.items()):
  parts=key.split('/');rep=int(task.get('rep') or parts[1].split('_')[-1]);route=str(task.get('route') or parts[3])
  if route=='direct':gen=str(task.get('condition') or task.get('generator') or parts[4]);learner='direct_bayes'
  elif route=='synthetic':gen=str(task.get('generator') or parts[5]);learner=str(task.get('method') or parts[4])
  elif route=='real':gen='shared';learner=str(task.get('method') or parts[4])
  else:raise SystemExit('unexpected E3 route in '+key)
  outcome=task.get('outcome');ev=None
  if outcome=='successful':
   ep=artifact_dir_for(task,rt)/'evaluation.json'
   if not ep.is_file():raise SystemExit('successful E3 eval lacks evaluation.json: '+key)
   ev=read_json(ep)
   if ev.get('task_key')!=key or int(ev.get('test_n',-1))!=500000:raise SystemExit('evaluation identity/test size mismatch: '+key)
   rr=task_result(task)
   for f in ('balanced_accuracy','coverage','set_size','threshold'):
    if f in rr and f in ev and rr[f]!=ev[f]:raise SystemExit('registry/evaluation metric mismatch '+key+' '+f)
   if int(ev.get('calibration_n',-1))!=10000:raise SystemExit('calibration size mismatch '+key)
   by_eval[(route,gen,learner,rep)]=ev
  fit_key=(ev.get('fit_key') if ev else task.get('fit_key')) or (task.get('dependencies') or [''])[0]
  fit=all_fits.get(fit_key,{})
  fres=task_result(fit);fit_dir=artifact_dir_for(fit,rt) if fit else Path('/nonexistent')
  if fit and fit.get('outcome')=='successful' and not fit_dir.exists():raise SystemExit('fit artifact dir missing '+fit_key)
  fit_seconds=fres.get('fit_seconds')
  tuning=trial_accounting_for_fit(fit,rt,cutoff_by_task) if fit and not fres.get('reused') else {'state':'reused_pipeline_no_E3_trials' if fit else 'dependency_unavailable','slot_n':None,'completed_slot_n':None,'physical_duration_n':0,'physical_duration_missing_n':None,'physical_seconds':None,'cached_slot_n':0,'cached_elapsed_seconds':None,'history_sha256':'','history_provenance':'reused_or_unavailable','aborted_trial_index':None,'aborted_trial_last_observed_seconds':None,'unattempted_slot_n':0}
  tuning_seconds=tuning['physical_seconds']
  reused_audit=reuse_component_by.get((rep,gen)) if fres.get('reused') else None
  pipeline_sha=fres.get('pipeline_sha256') or fres.get('artifact_sha256') or (reused_audit.get('e3_file_sha256','') if reused_audit else '')
  if ev and ev.get('pipeline_sha256'):pipeline_sha=ev.get('pipeline_sha256')
  role=manifest.get('role_hashes',{}).get(str(rep),{})
  role_ids=role.get('id_hashes',{})
  gen_task=None;generation_seconds=None;generation_hash=''
  if route=='synthetic':
   gkey=f'e3/rep_{rep}/generate/{gen}';gen_task=all_gens.get(gkey)
   if not gen_task or gen_task.get('outcome')!='successful':raise SystemExit('synthetic evaluation lacks successful generator dataset '+key)
   gres=task_result(gen_task)
   if int(gres.get('n_rows',0))!=400000 or sum(gres.get('class_counts',[]))!=400000:raise SystemExit('generated dataset volume/counts invalid '+gkey)
   expected_counts=[int(n)*5 for n in manifest['role_hashes'][str(rep)]['fit_counts']]
   if gres.get('class_counts')!=expected_counts:raise SystemExit('generation class counts differ from exact five-times real fit counts '+gkey)
   generation_hash=gres.get('data_sha256','')
   generation_seconds=(gres.get('phase_supervision') or {}).get('seconds')
  elif route=='direct':
   gkey=f'e3/rep_{rep}/fit/{gen}'
  if ev and fit and fit.get('outcome')=='successful' and pipeline_sha and ev.get('pipeline_sha256')!=pipeline_sha:raise SystemExit('eval pipeline identity mismatch '+key)
  if fit and fit.get('outcome')=='successful':
   fitted_n=sum(fres.get('class_counts',[])) if fres.get('reused') else int(fres.get('training_rows',0))
   if fitted_n not in (80000,400000):raise SystemExit('unexpected E3 fit row count '+fit_key)
  policy=policy_at(task_start(task),freeze)
  fit_policy=policy_at(task_start(fit),freeze) if fit else 'not_applicable'
  eval_wall=elapsed(task_start(task),task.get('finished_utc'))
  calphase=phase_observation(task,'calibration',rt,cost_index)
  inferphase=phase_observation(task,'test_inference',rt,cost_index)
  engine_attempt_id=(task.get('result') or {}).get('attempt_id','')
  engine_result_path=artifact_dir_for(task,rt)/'eval_result.json'
  if engine_result_path.is_file() and engine_attempt_id:
   engine_result=read_json(engine_result_path)
   if str(engine_result.get('attempt_id'))!=str(engine_attempt_id):raise SystemExit('engine eval_result attempt ID differs from current registry result '+key)
  generator_fit=fit if route=='direct' else (all_fits.get(f'e3/rep_{rep}/fit/{gen}',{}) if route=='synthetic' else {})
  genfitres=task_result(generator_fit);genfitdir=artifact_dir_for(generator_fit,rt) if generator_fit else Path('/nonexistent')
  genfitseconds=None if genfitres.get('reused') else genfitres.get('fit_seconds')
  gen_tuning=trial_accounting_for_fit(generator_fit,rt,cutoff_by_task) if generator_fit and not genfitres.get('reused') else {'state':'reused_pipeline_no_E3_trials' if generator_fit else 'not_applicable','slot_n':None,'completed_slot_n':None,'physical_duration_n':0,'physical_duration_missing_n':None,'physical_seconds':None,'cached_slot_n':0,'cached_elapsed_seconds':None,'history_sha256':'','history_provenance':'reused_or_unavailable','aborted_trial_index':None,'aborted_trial_last_observed_seconds':None,'unattempted_slot_n':0}
  genfittuning=gen_tuning['physical_seconds']
  genfitwall=elapsed(task_start(generator_fit),generator_fit.get('finished_utc')) if generator_fit else None
  genfitpolicy=policy_at(task_start(generator_fit),freeze) if generator_fit else 'not_applicable'
  genfitprovenance='E2_reconstructed_pipeline_reused' if genfitres.get('reused') else ('new_E3_generator_fit' if generator_fit else 'not_applicable')
  fit_wall=elapsed(task_start(fit),fit.get('finished_utc')) if fit else None
  cal_n=ev.get('calibration_n') if ev else None
  cm=safe_json(ev.get('confusion_matrix')) if ev else ''
  per=ev.get('per_class',{}) if ev else {}
  public_reason,public_fit_reason=public_reasons(task,fit)
  pipeline_info=inspect_pipeline(fit,rt) if fit and fit.get('outcome')=='successful' else {'available':False,'backing':'unavailable_dependency','logical_path':'','sha256':'','size_bytes':None,'cache_identity':None}
  row={'task_key':key,'repetition':rep,'route':route,'generator':gen,'learner':learner,'status':task.get('status'),'outcome':outcome or '', 'reason':public_reason, 'fit_key':fit_key,'fit_outcome':fit.get('outcome',''),'fit_reason':public_fit_reason, 'fit_provenance':'E2_reconstructed_pipeline_reused' if fres.get('reused') else ('new_E3_fit' if fit and fit.get('route')=='generator' else ('E3_downstream_fit' if fit else 'unavailable_dependency')), 'fit_cost_role':'generator_fit' if route=='direct' else ('synthetic_learner_fit' if route=='synthetic' else 'real_learner_fit'), 'fit_source':fres.get('source',''),'fit_pipeline_sha256':pipeline_sha,'fit_pipeline_available':pipeline_info['available'],'fit_pipeline_backing':pipeline_info['backing'],'fit_pipeline_logical_path':pipeline_info['logical_path'],'fit_pipeline_size_bytes':pipeline_info['size_bytes'] if pipeline_info['size_bytes'] is not None else '', 'fit_pipeline_cache_identity':safe_json(pipeline_info['cache_identity']) if pipeline_info['cache_identity'] else '', 'fit_selected_params':safe_json(fres.get('params')) if fres.get('params') is not None else '', 'fit_seed':fres.get('seed',''),'fit_training_rows':fres.get('training_rows',''),'fit_training_ids_sha256':fres.get('training_ids_sha256',''),'fit_trial_budget':fit.get('trials','') if fit else '', 'fit_model_seconds':fmt(fit_seconds),'fit_trial_seconds_sum':fmt(tuning_seconds),'fit_trial_cost_state':tuning['state'],'fit_trial_history_provenance':tuning['history_provenance'],'fit_trial_history_sha256':tuning['history_sha256'],'fit_trial_slots_n':tuning['slot_n'] if tuning['slot_n'] is not None else '', 'fit_trial_completed_slots_n':tuning['completed_slot_n'] if tuning['completed_slot_n'] is not None else '', 'fit_trial_aborted_slot_index':tuning['aborted_trial_index'] if tuning['aborted_trial_index'] is not None else '', 'fit_trial_aborted_last_observed_seconds_excluded':fmt(tuning['aborted_trial_last_observed_seconds']), 'fit_trial_unattempted_slot_n':tuning['unattempted_slot_n'], 'fit_trial_physical_duration_n':tuning['physical_duration_n'],'fit_trial_duration_missing_n':tuning['physical_duration_missing_n'] if tuning['physical_duration_missing_n'] is not None else '', 'fit_trial_cached_slot_n':tuning['cached_slot_n'],'fit_trial_cached_elapsed_seconds':fmt(tuning['cached_elapsed_seconds']),'fit_task_wall_seconds':fmt(fit_wall),'fit_resource_policy':fit_policy,'generator_fit_key':generator_fit.get('key',''),'generator_pipeline_info':inspect_pipeline(generator_fit,rt) if generator_fit and generator_fit.get('outcome')=='successful' else {'available':False,'backing':'unavailable_dependency','logical_path':'','sha256':'','size_bytes':None,'cache_identity':None},'generator_fit_provenance':genfitprovenance,'generator_fit_model_seconds':fmt(genfitseconds),'generator_fit_trial_seconds_sum':fmt(genfittuning),'generator_fit_trial_cost_state':gen_tuning['state'],'generator_fit_trial_history_provenance':gen_tuning['history_provenance'],'generator_fit_trial_history_sha256':gen_tuning['history_sha256'],'generator_fit_trial_slots_n':gen_tuning['slot_n'] if gen_tuning['slot_n'] is not None else '', 'generator_fit_trial_completed_slots_n':gen_tuning['completed_slot_n'] if gen_tuning['completed_slot_n'] is not None else '', 'generator_fit_trial_aborted_slot_index':gen_tuning['aborted_trial_index'] if gen_tuning['aborted_trial_index'] is not None else '', 'generator_fit_trial_aborted_last_observed_seconds_excluded':fmt(gen_tuning['aborted_trial_last_observed_seconds']), 'generator_fit_trial_unattempted_slot_n':gen_tuning['unattempted_slot_n'], 'generator_fit_trial_physical_duration_n':gen_tuning['physical_duration_n'],'generator_fit_trial_duration_missing_n':gen_tuning['physical_duration_missing_n'] if gen_tuning['physical_duration_missing_n'] is not None else '', 'generator_fit_trial_cached_slot_n':gen_tuning['cached_slot_n'],'generator_fit_trial_cached_elapsed_seconds':fmt(gen_tuning['cached_elapsed_seconds']),'generator_fit_task_wall_seconds':fmt(genfitwall),'generator_fit_resource_policy':genfitpolicy,'role_source_sha256':role.get('source_sha256',''),'role_fit_ids_sha256':role_ids.get('fit_ids',''),'role_tuning_ids_sha256':role_ids.get('tuning_ids',''),'role_calibration_ids_sha256':role_ids.get('calibration_ids',''),'generation_task_key':gkey if route=='synthetic' else '', 'generation_rows':400000 if route=='synthetic' else '', 'generation_class_counts':safe_json(task_result(gen_task).get('class_counts')) if gen_task else '', 'generation_seed':task_result(gen_task).get('generation_seed','') if gen_task else '', 'generation_data_sha256':generation_hash,'generation_seconds':fmt(generation_seconds),'evaluation_task_wall_seconds':fmt(eval_wall),'evaluation_resource_policy':policy,'engine_attempt_id':engine_attempt_id,'calibration_seconds':fmt(calphase.get('seconds')),'calibration_peak_tree_rss_kib':calphase.get('peak_tree_rss_kib') or '', 'calibration_phase_exit_code':calphase.get('exit_code') if calphase.get('exit_code') is not None else '', 'calibration_phase_reason':calphase.get('reason') or '', 'calibration_timing_source':calphase.get('source',''),'inference_seconds':fmt(inferphase.get('seconds')),'inference_peak_tree_rss_kib':inferphase.get('peak_tree_rss_kib') or '', 'inference_phase_exit_code':inferphase.get('exit_code') if inferphase.get('exit_code') is not None else '', 'inference_phase_reason':inferphase.get('reason') or '', 'inference_timing_source':inferphase.get('source',''),'calibration_and_inference_timing':'separate phase wall time; includes model/pipeline load and output work, not pure kernel time','balanced_accuracy':fmt(ev.get('balanced_accuracy')) if ev else '', 'coverage':fmt(ev.get('coverage')) if ev else '', 'mean_set_size':fmt(ev.get('set_size')) if ev else '', 'threshold':fmt(ev.get('threshold')) if ev else '', 'calibration_n':cal_n if cal_n is not None else '', 'test_n':ev.get('test_n','') if ev else '', 'calibration_fallback_count':ev.get('calibration_fallback_count','') if ev else '', 'test_fallback_count':ev.get('test_fallback_count','') if ev else '', 'confusion_matrix_rows_true_cols_pred':cm,'class_order':safe_json(LABELS)}
  for i,label in enumerate(LABELS):
   c=per.get(str(i),{})
   row['recall_'+label]=fmt(c.get('recall')) if c else '';row['coverage_'+label]=fmt(c.get('coverage')) if c else '';row['set_size_'+label]=fmt(c.get('set_size')) if c else '';row['test_support_'+label]=c.get('n','') if c else ''
  gp=row.pop('generator_pipeline_info')
  row.update({'generator_pipeline_available':gp['available'],'generator_pipeline_backing':gp['backing'],'generator_pipeline_logical_path':gp['logical_path'],'generator_pipeline_sha256':gp['sha256'],'generator_pipeline_size_bytes':gp['size_bytes'] if gp['size_bytes'] is not None else '', 'generator_pipeline_cache_identity':safe_json(gp['cache_identity']) if gp['cache_identity'] else ''})
  case_rows.append(row)

 ledger_fields=list(case_rows[0].keys());write_csv(out/'E3_FINAL_CELL_LEDGER_69.csv',case_rows,ledger_fields)
 # Build route-by-repetition rows with explicit denominators and paired differences.
 combos=[]
 combos.extend(('direct',g,'direct_bayes') for g in ['gmm','copula','arf','kde','chow_liu'])
 combos.extend(('synthetic',g,l) for g in ['gmm','copula','arf','kde','chow_liu'] for l in ['logistic','random_forest','hist_gb'])
 combos.extend(('real','shared',l) for l in ['logistic','random_forest','hist_gb'])
 route_rows=[]
 def stat_for(items,metric):return mean([x[metric] for x in items if x is not None])
 for route,gen,learner in combos:
  reps=[]
  for rep in (1,2,3):
   key=(route,gen,learner,rep);ev=by_eval.get(key)
   if ev:reps.append(ev)
  row={'route':route,'generator':gen,'learner':learner,'planned_repetitions':3,'successful_repetitions':len(reps),'balanced_accuracy_mean':fmt(stat_for(reps,'balanced_accuracy')),'balanced_accuracy_sample_sd':fmt(sd([x['balanced_accuracy'] for x in reps])),'coverage_mean':fmt(stat_for(reps,'coverage')),'coverage_sample_sd':fmt(sd([x['coverage'] for x in reps])),'mean_set_size_mean':fmt(stat_for(reps,'set_size')),'mean_set_size_sample_sd':fmt(sd([x['set_size'] for x in reps]))}
  relevant=[x for x in case_rows if x['route']==route and x['generator']==gen and x['learner']==learner]
  for name,field in [('mean_fit_model_seconds','fit_model_seconds'),('mean_fit_trial_seconds_sum','fit_trial_seconds_sum'),('mean_generator_fit_seconds','generator_fit_model_seconds'),('mean_generator_fit_trial_seconds_sum','generator_fit_trial_seconds_sum'),('mean_generation_seconds','generation_seconds'),('mean_calibration_phase_seconds','calibration_seconds'),('mean_test_inference_phase_seconds','inference_seconds'),('mean_evaluation_task_wall_seconds','evaluation_task_wall_seconds')]:
   vals=[]
   for x in relevant:
    try:
     if x[field]!='':vals.append(float(x[field]))
    except (TypeError,ValueError):pass
   row[name]=fmt(mean(vals));row[name+'_n']=len(vals)
  for rep in (1,2,3):
   ev=by_eval.get((route,gen,learner,rep));row[f'rep{rep}_outcome']='successful' if ev else next((t.get('outcome') for t in reg_cases.values() if int(t.get('rep',0))==rep and t.get('route')==route and ((route=='direct' and (t.get('condition') or t.get('method'))==gen) or (route=='synthetic' and t.get('generator')==gen and t.get('method')==learner) or (route=='real' and t.get('method')==learner))), 'missing')
   for metric in METRICS:row[f'rep{rep}_{metric}']=fmt(ev.get(metric)) if ev else ''
  # Delta columns are populated on synthetic rows; all are per-repetition matched contrasts.
  for comp in ('synthetic_minus_real','synthetic_minus_direct','real_minus_direct'):
   deltas=[]
   for rep in (1,2,3):
    syn=by_eval.get(('synthetic',gen,learner,rep));real=by_eval.get(('real','shared',learner,rep));direct=by_eval.get(('direct',gen,'direct_bayes',rep))
    left,right=(syn,real) if comp=='synthetic_minus_real' else ((syn,direct) if comp=='synthetic_minus_direct' else (real,direct))
    d=(left['balanced_accuracy']-right['balanced_accuracy']) if left and right else None
    row[f'{comp}_rep{rep}_ba_delta']=fmt(d)
    if d is not None:deltas.append(d)
   row[f'{comp}_paired_n']=len(deltas) if route=='synthetic' else '';row[f'{comp}_ba_delta_mean']=fmt(mean(deltas)) if route=='synthetic' else '';row[f'{comp}_ba_delta_sample_sd']=fmt(sd(deltas)) if route=='synthetic' else ''
   if route!='synthetic':
    for rep in (1,2,3):row[f'{comp}_rep{rep}_ba_delta']=''
  route_rows.append(row)
 route_fields=list(route_rows[0].keys());write_csv(out/'E3_FINAL_ROUTE_REPETITIONS.csv',route_rows,route_fields)

 # Exact task counts and denominator validation.
 counts={}
 for t in reg_cases.values():counts[t.get('outcome') or t.get('status')]=counts.get(t.get('outcome') or t.get('status'),0)+1
 if counts!={'successful':64,'scientific_failure':3,'unavailable_dependency':2}:raise SystemExit('E3 outcome counts differ from reviewed current ledger '+repr(counts))
 fitcounts={}
 for t in all_fits.values():fitcounts[t.get('outcome') or t.get('status')]=fitcounts.get(t.get('outcome') or t.get('status'),0)+1
 if fitcounts!={'successful':67,'scientific_failure':2}:raise SystemExit('E3 fit dependency counts differ '+repr(fitcounts))
 gen_counts={}
 for t in all_gens.values():gen_counts[t.get('outcome') or t.get('status')]=gen_counts.get(t.get('outcome') or t.get('status'),0)+1
 if gen_counts!={'successful':15}:raise SystemExit('E3 generation counts differ '+repr(gen_counts))

 # Unique selected-fit trial accounting: duplicate_cached slots are budgeted slots, not physical fits.
 new_fit_tasks=[t for t in all_fits.values() if not task_result(t).get('reused')]
 trial_histories=[]
 for t in new_fit_tasks:
  trial_histories.append((t,trial_accounting_for_fit(t,rt,cutoff_by_task)))
 partial_details=[]
 for t,x in trial_histories:
  if x['history_provenance'] in ('verified_terminal_cutoff_partial_history','derived_validated_projection_raw_gate_verified_before_archiving'):
   partial_details.append({'task_key':t['key'],'history_provenance':x['history_provenance'],'history_sha256':x['history_sha256'],'completed_slot_n':x['completed_slot_n'],'physical_duration_n':x['physical_duration_n'],'physical_completed_trial_seconds':x['physical_seconds'],'duplicate_cached_slot_n':x['cached_slot_n'],'duplicate_cached_elapsed_seconds_excluded':x['cached_elapsed_seconds'],'aborted_trial_index':x['aborted_trial_index'],'aborted_trial_last_observed_seconds_excluded':x['aborted_trial_last_observed_seconds'],'unattempted_slot_n':x['unattempted_slot_n'],'cutoff_evidence_file_n':x['verified_cutoff_evidence_file_n']})
 trial_cost_summary={
  'new_fit_dependencies':len(new_fit_tasks),
  'published_selection_history_files':sum(x['history_provenance']=='published_selection_history' for _,x in trial_histories),
  'verified_terminal_cutoff_partial_history_files':sum(x['history_provenance']=='verified_terminal_cutoff_partial_history' for _,x in trial_histories),
  'curated_projection_partial_history_files':sum(x['history_provenance']=='derived_validated_projection_raw_gate_verified_before_archiving' for _,x in trial_histories),
  'new_fit_dependencies_without_any_history':sum(x['history_provenance'] in ('selection_history_unavailable','selection_history_unreadable') for _,x in trial_histories),
  'completed_trial_slots_recorded':sum((x['completed_slot_n'] if x['completed_slot_n'] is not None else (x['slot_n'] or 0)) for _,x in trial_histories),
  'physical_trial_durations_recorded':sum(x['physical_duration_n'] for _,x in trial_histories),
  'physical_trial_durations_missing_within_retained_histories':sum(x['physical_duration_missing_n'] or 0 for _,x in trial_histories),
  'physical_completed_trial_seconds_recorded':sum(x['physical_seconds'] or 0 for _,x in trial_histories) if any(x['physical_seconds'] is not None for _,x in trial_histories) else None,
  'duplicate_cached_slots':sum(x['cached_slot_n'] for _,x in trial_histories),
  'duplicate_cached_elapsed_seconds_excluded':sum(x['cached_elapsed_seconds'] or 0 for _,x in trial_histories) if any(x['cached_elapsed_seconds'] is not None for _,x in trial_histories) else None,
  'aborted_trial_last_observed_seconds_excluded':sum(x['aborted_trial_last_observed_seconds'] or 0 for _,x in trial_histories) if any(x['aborted_trial_last_observed_seconds'] is not None for _,x in trial_histories) else None,
  'unattempted_trial_slots_not_costed':sum(x['unattempted_slot_n'] for _,x in trial_histories),
  'partial_history_details':partial_details,
  'physical_tuning_total_is_complete':all(x['history_provenance']=='published_selection_history' and x['state']!='duration_limited_lower_bound' for _,x in trial_histories),
  'duplicate_cached_slots_consume_fixed_trial_budget':True,
 }

 # Calculate report summaries from saved CSV/evaluation JSON only.
 direct_summary=[]
 for g in ['gmm','copula','arf','kde','chow_liu']:
  es=[by_eval[( 'direct',g,'direct_bayes',rep)] for rep in (1,2,3) if ('direct',g,'direct_bayes',rep) in by_eval]
  direct_summary.append((g,len(es),mean([x['balanced_accuracy'] for x in es]),mean([x['coverage'] for x in es]),mean([x['set_size'] for x in es])))
 syn_real=[]
 for g in ['gmm','copula','arf','kde','chow_liu']:
  for l in ['logistic','random_forest','hist_gb']:
   ds=[];sizes=[];covs=[]
   for rep in (1,2,3):
    syn=by_eval.get(('synthetic',g,l,rep));real=by_eval.get(('real','shared',l,rep))
    if syn and real:
     ds.append(syn['balanced_accuracy']-real['balanced_accuracy']);sizes.append(syn['set_size']-real['set_size']);covs.append(syn['coverage']-real['coverage'])
   syn_real.append((g,l,len(ds),mean(ds),mean(sizes),mean(covs)))

 # Deduplicated phase totals use exact task/engine-attempt/stage keys from the validated cost ledger.
 phase_cost_summary={}
 for stage,field in [('calibration','calibration_seconds'),('test_inference','inference_seconds')]:
  vals=[float(x[field]) for x in case_rows if x.get(field) not in ('',None)]
  phase_cost_summary[stage]={'observed_n':len(vals),'sum_seconds':sum(vals),'mean_seconds':mean(vals),'successful_phase_n':sum(1 for x in case_rows if x.get(field) not in ('',None) and str(x.get('calibration_phase_exit_code' if stage=='calibration' else 'inference_phase_exit_code'))=='0'),'non_success_or_timed_out_phase_n':sum(1 for x in case_rows if x.get(field) not in ('',None) and x.get('calibration_phase_exit_code' if stage=='calibration' else 'inference_phase_exit_code') not in ('0',0))}

 # Selected generator provenance and primary reuse audit.
 gen_fit_tasks=[t for t in all_fits.values() if t.get('route')=='generator']
 reuse=[t for t in gen_fit_tasks if task_result(t).get('reused')]
 newfit=[t for t in gen_fit_tasks if not task_result(t).get('reused')]
 if len(reuse)!=9 or len(newfit)!=6:raise SystemExit('Expected 9 reused and 6 new E3 generator fits')
 if len(reuse_component)!=9 or any(x['all_predictive_components_equal']!='True' for x in reuse_component):raise SystemExit('E2/E3 reused predictive-component check incomplete/failed')
 if len(reuse_scores)!=9 or any(x['exact_float_score_match']!='True' or x['model_or_prediction_identity_inferred']!='False' for x in reuse_scores):raise SystemExit('E2/E3 reused score consistency audit invalid')

 now=datetime.datetime.now(datetime.timezone.utc);local=now.astimezone(ZoneInfo('Asia/Kolkata'))
 lines=['# Experiment 3: final descriptive report','',f'Observed: {now.strftime("%Y-%m-%d %H:%M:%S UTC")} ({local.strftime("%Y-%m-%d %H:%M:%S %Z")}).','', ('**Status:** all 69 planned E3 evaluation cells are terminal and accounted for. This is an E3 descriptive reproduction from validated curated history; the original scientific metrics review applies, while the offline provenance rendering itself was not separately reviewed. It does not declare the six-experiment project complete. E1 and E2 records were not rewritten; no model was loaded, fitted, tuned, or predicted during this export.' if OFFLINE_PARTIAL_PROJECTION_USED_KEYS else '**Status:** all 69 planned E3 evaluation cells are terminal and accounted for. This is the reviewed E3 descriptive report, not a declaration that the six-experiment project is complete. Root semantic and figure review passed for this E3 descriptive package; the full six-experiment project remains in progress. E1 and E2 records were not rewritten; no model was loaded, fitted, tuned, or predicted during this export.'),'', '## Question and frozen design','', 'E3 compares direct Bayes classification from a fitted class-conditional generator, a discriminative learner trained on generated examples, and the same learner trained on real fitting data. The design was frozen before E3 test evaluation. It uses five generator families (GMM, Gaussian copula, ARF/FORDE, KDE, Chow-Liu), one 100,000-row development cohort in each of three repetitions (80,000 fit, 10,000 tune, 10,000 calibration), and the fixed 500,000-source test cohort. Six predictors and class order are recorded in the E3 manifest.','', 'Each successful generator condition produced 400,000 synthetic fitting rows, five times its 80,000 real fitting rows, allocated by deterministic largest remainder from real-fit class proportions. All three synthetic learners in a generator/repetition use the same saved synthetic dataset. Synthetic-only means the learner is fit only on synthetic rows; the pipeline still learns the generator from real fit data and uses real tuning and calibration data. The real-only baselines are shared once per learner/repetition. No real-plus-synthetic arm was run.','', f'Role IDs are the frozen E1 100k repetition memberships copied into the E3 manifest; fit, tune and calibration hashes are present for all three repetitions. Each successful evaluation used calibration n=10,000 and test n=500,000. The test cohort is fixed and its E1/E2 outcomes were already observed; these are not prospective untouched test results.','', '## Planned outcomes and coverage','', '| Planned E3 evaluation cells | Successful | Scientific failures | Unavailable dependency | Pending |','|---:|---:|---:|---:|---:|',f'| 69 | 64 | 3 | 2 | 0 |','', '| Route group | Planned | Successful | Failed | Unavailable |','|---|---:|---:|---:|---:|','| Direct Bayes (5 generators x 3 reps) | 15 | 12 | 3 | 0 |','| Synthetic-only (5 generators x 3 learners x 3 reps) | 45 | 43 | 0 | 2 |','| Real-only shared (3 learners x 3 reps) | 9 | 9 | 0 | 0 |','', 'All 153 E3 planned tasks are terminal: 69 evaluation cases, 69 fit dependencies and 15 generation dependencies. Fit dependencies: 67 successful and 2 terminal 10 GiB process-tree-limit failures. All 15 generator datasets were successfully produced (6,000,000 generated rows counted across the 15 saved datasets; these are repeated draws from estimated distributions, not independent evidence about real-world diversity).','', 'The three direct-KDE evaluation cases hit the declared 600-second phase limit; each saved no classification or conformal score. The two synthetic-RF cases unavailable by dependency are GMM/rep 2 and KDE/rep 2, because those learner fit dependencies exceeded the 10 GiB per-process-tree limit. These two unavailable evaluations are not new evaluation failures. Nothing here calls the two resource-limited fits an algorithmic or accuracy failure.','', '## Selected-generator provenance and reuse','', 'Nine generator fits (GMM, copula and Chow-Liu, each across three repetitions) reused the corresponding E2 reconstructed selected pipelines, with matching role identities, preprocessing, fitted predictive components and selection parameters. The independent component audit reports all nine component sets equal. Pipeline file bytes differ because E3 adds/updates root provenance metadata; that does not indicate a fitted-component change. E2 and E3 balanced-accuracy floats match exactly for all nine direct comparisons. Exact score equality alone is not model or prediction identity; identity claims are grounded in the component audit, and these nine remain explicitly E2-reconstructed provenance.','', 'The six ARF/KDE generator fits were new E3 dependencies fitted on their permitted 80,000 fitting rows with tuning-only selection. They do not repair or alter E1/E2 outcomes. All six selected generator fits completed. Their fit task and selected pipeline provenance is in the cell ledger and original registry. Two later downstream RF fits (GMM/KDE rep 2) exceeded the fixed 10 GiB limit.','', '## Descriptive results','', '| Direct Bayes generator | Successful reps / 3 | Mean balanced accuracy | Mean marginal coverage | Mean set size |','|---|---:|---:|---:|---:|']
 for g,n,ba,cov,ss in direct_summary:lines.append(f'| {g} | {n}/3 | {fmt(ba) if ba is not None else "NA"} | {fmt(cov) if cov is not None else "NA"} | {fmt(ss) if ss is not None else "NA"} |')
 lines+=['','KDE direct has no valid mean because all three planned direct evaluation phases timed out. No score was imputed. The full per-repetition route table and 69-cell ledger preserve individual outcomes and denominators. Synthetic RF has 2/3 successful repetitions for GMM and KDE; it has 3/3 for copula, ARF and Chow-Liu. Logistic and histogram-gradient-boosting synthetic routes each have 3/3 for every family.','', '| Generator | Learner | Paired synthetic - real n | Mean delta balanced accuracy | Mean delta set size | Mean delta coverage |','|---|---|---:|---:|---:|---:|']
 for g,l,n,dba,dss,dcov in syn_real:lines.append(f'| {g} | {l} | {n} | {fmt(dba) if dba is not None else "NA"} | {fmt(dss) if dss is not None else "NA"} | {fmt(dcov) if dcov is not None else "NA"} |')
 lines+=['','These are descriptive paired differences among repetitions where both routes completed; n ranges from 2 to 3. They do not estimate a population effect or support significance claims. Direct-versus-synthetic and direct-versus-real matched contrasts are also tabulated per generator/learner in the route CSV, with exact matched n.','', 'Class-specific coverage can diverge sharply from marginal coverage. For Chow-Liu synthetic-only logistic, the three repetition-level marginal coverages are 0.8907, 0.9042 and 0.9004 (mean 0.8984), while class-A coverage is 0.0089, 0.0341 and 0.0334 (mean 0.0255); class-A recall is 0 in each. The full per-route/per-repetition ledger retains every class recall, coverage, set size and support. This example illustrates that marginal 90% coverage does not guarantee 90% classwise coverage.','', '## Conformal method and evaluation','', 'The saved evaluations use probability nonconformity 1 - p_true, the finite-sample split-conformal order statistic k = ceil((n+1) x 0.90) = 9,001 for n=10,000, and include a label when 1 - p_class <= threshold. Thresholds were selected from the permitted calibration cohort and were not changed after test evaluation. No bootstrap or test-based method selection was performed. The ledger includes calibration n, threshold, fallback counts, 500,000-row confusion matrices and all per-class metrics.','', '## Resource and cost accounting','', 'The cell ledger and route table report selected model-fit time, tuning-trial time, generator-fit time, generation time, calibration-phase wall time, test-inference-phase wall time, peak phase RSS and evaluation-worker wall time separately when recorded. Calibration and test inference measurements were recovered from exact engine-attempt phase receipts and cross-checked against `reports/costs.csv` by task key, engine attempt ID and stage. Phase wall durations include pipeline/model loading and result I/O; they are not pure kernel timings. Among the 69 planned evaluation cases, calibration phase time is recorded for 67 (64 scored cases plus the three direct-KDE cases that calibrated before evaluation timeout); inference phase time is recorded for those same 67, including the three 600-second KDE timeouts. The two unavailable RF evaluations never started and have blank phase cost fields with explicit reasons. Unique E3 evaluation-phase totals, deduplicated by task key/engine attempt/stage, are calibration n=67, sum 353.1662 seconds, and test inference n=67, sum 3951.3304 seconds. The route CSV attributes shared generator-fit and generation costs to each corresponding synthetic learner row; do not sum those repeated attribution values as physical totals. Use unique `(task_key, attempt_id, stage)` records in `costs.csv` for deduplicated phase totals. Reused E2 generator fits have blank E3 fit/trial durations because no E3 model refit/tune time was measured; E3 reuse validation task wall time remains recorded.','', f"Trial-history accounting covers {trial_cost_summary['new_fit_dependencies']} newly fitted dependencies: {trial_cost_summary['published_selection_history_files']} published selection histories, {trial_cost_summary['verified_terminal_cutoff_partial_history_files']} exact-attempt terminal-cutoff partial histories verified from raw receipts during live export, and {trial_cost_summary['curated_projection_partial_history_files']} curated partial-history projections whose raw receipt gate was verified before archive creation; {trial_cost_summary['new_fit_dependencies_without_any_history']} dependencies lack retained history. The histories contain {trial_cost_summary['completed_trial_slots_recorded']} selection slots with recorded terminal outcomes (including duplicate_cached budget slots); {trial_cost_summary['duplicate_cached_slots']} `duplicate_cached` slots carried copied elapsed values totaling {fmt(trial_cost_summary['duplicate_cached_elapsed_seconds_excluded'])} seconds and are excluded from physical tuning time while remaining consumed slots in the fixed search budget. The recorded non-cached completed-trial subtotal is {fmt(trial_cost_summary['physical_completed_trial_seconds_recorded'])} seconds across {trial_cost_summary['physical_trial_durations_recorded']} durations. For the two failed RF fits, raw histories were validated before archiving against exact attempt identity and before/after source hashes; offline regeneration validates the projection SHA and preserves original source/evidence hashes, but cannot rerun the raw private-receipt gate. Their active trial's last observed elapsed values ({fmt(trial_cost_summary['aborted_trial_last_observed_seconds_excluded'])} seconds total) are reported separately and excluded from completed-trial time; {trial_cost_summary['unattempted_trial_slots_not_costed']} unattempted slots have no assigned duration. This remains a lower bound, not the full tuning cost. Partial selection-file hashes and the cutoff-ledger hash are recorded in the receipt; no raw process receipt payload is reproduced. Any missing duration remains blank rather than being treated as zero.",'', 'Resource policy history records an initial two-worker, 10 GiB policy (04:46 UTC to 16:56 UTC), then user-authorized adaptive CPU/RAM scheduling, followed by peak-safe queue packing from 17:12 UTC. Per-task policy labels are derived from each latest attempt start timestamp and that history. Trial/phase limits remained 600 seconds, process-tree memory cap remained 10 GiB, nested threads remained one, host/Harbor reserve was 6 GiB, and new workers used nice +10 after the concurrency amendment. Wall-clock timings are hardware/load dependent, with concurrent unrelated Harbor use; do not compare them as portable algorithmic cost benchmarks.','', 'Observed ARF fit attempt selection histories include fixed-budget trial timeouts before a successful selected trial in completed repetitions; these are preserved in the original fit artifacts, not replaced or hidden.','', '## Limits and provenance','', 'Results are conditional on the fitted generators and selected downstream configurations, observed test cohort, and successful cells. Resource-limited fits, direct-KDE timeouts and unavailable dependencies make route coverage uneven. Comparisons must use the paired n in the route CSV; survivorship can favor settings whose difficult cases completed. Do not call the best successful route universally superior.','', 'The historical E1 pipelines and per-test-row predictions omitted from compact migration remain omitted. E3 reuse depended on available E2 reconstruction artifacts; this report does not claim restoration of historical E1 models or predictions. Preserve the known seven auxiliary E1 tuning-history discrepancies and E2 reconstruction limitations from the project report. Previously verified E1 completion metrics are not invalidated by those auxiliary-history caveats.','', 'The three final E3 figures were reviewed against the corrected descriptive results; root figure-hash bindings and semantic review are recorded in `engineering_audits/E3_DESCRIPTIVE_ROOT_REVIEW_PASSED_20261026.json`. The receipt covers E3 descriptive outputs only and does not complete the independent full selected-model audit required during final project validation.','', '## Files and reproduction','', '- `E3_FINAL_CELL_LEDGER_69.csv`: one row per planned evaluation; includes terminal outcome/reason, fit and generation provenance, resource policy, timing fields, all seven class recalls/coverages/set sizes/supports, confusion matrices and calibration/test counts.','- `E3_FINAL_ROUTE_REPETITIONS.csv`: route means/sample SDs with actual n, individual repetition scores, separate recorded cost summaries and matched route differences with paired n.','- Generator fits, selection histories, generated datasets, model fits and evaluation artifacts remain under the EC2 runtime artifacts tree; source hashes and full manifest/registry hashes are in the receipt.','- Rebuild the descriptive CSV/report on EC2: `python3 /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/source/export_e3_descriptive.py --runtime /home/ubuntu/lamost_e1_migration_20261025/runtime_20261025 --project /home/ubuntu/lamost_e1_migration_20261023/project --output /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/reports`. No fits/model loads/inference occur.','']
 # Correct reproduction command typo by construction from resolved root.
 lines[-2]='- Rebuild from an extracted package root on EC2: `cd <extraction-root>; python3 runtime_20261025/source/export_e3_descriptive.py --runtime runtime_20261025 --project project --output runtime_20261025/reports --partial-projection runtime_20261025/reports/E3_PARTIAL_HISTORY_VALIDATED_PROJECTION_20261026.json`. Artifact paths are resolved from task keys under the supplied runtime, so the current working directory and historical host absolute paths are not used. If exact archived phase receipts are absent, phase costs fall back only to exact task/attempt/stage matches in the included validated `reports/costs.csv`. The exporter reads metadata/evaluation JSON and audit tables only; it performs no model load, fitting, tuning, generation, calibration, or inference.'
 report='\n'.join(lines)+'\n';report_path=out/'E3_FINAL_DESCRIPTIVE_REPORT.md';report_path.write_text(report,encoding='utf-8',newline='\n')
 # Hash the inputs/outputs and capture actual observation time.
 inputs=[rt/'registry.json',rt/'manifests/tasks.json',rt/'manifests/freeze.json',rt/'manifests/E3_MANIFEST.json',project/'benchmark/protocol_source.txt',rt/'reports/costs.csv',rt/'reports/terminal_trial_cutoffs.csv',rt/'reports/E3_REUSED_E2_CLASSIFICATION_CONSISTENCY.csv',rt/'reports/E3_REUSED_E2_PREDICTIVE_COMPONENTS.csv',rt/'reports/engineering_audits/E3_DESCRIPTIVE_ROOT_REVIEW_PASSED_20261026.json',Path(__file__)]
 if a.partial_projection: inputs.extend([a.partial_projection.resolve(),Path(__file__).with_name('offline_projection_adapter.py')])
 input_hashes={str(x):sha(x) for x in inputs}
 visual_review={'E3_balanced_accuracy_route_comparison.png':'b6d707b3df3e88f7e46846ec17bf3206919c14c44bdc5c11be7e9d4bff9a4775','E3_coverage_route_comparison.png':'d5f9f3daffe81f4cbda3840a4b7c1805cea9ead09851dd40633ec954fbd7cdaf','E3_set_size_route_comparison.png':'213b580602d405074ada24c2ff6558aec669c8df61ea489f3571218c5ae92bfb'}
 for name,digest in visual_review.items():
  if sha(out/name)!=digest: raise SystemExit('root-reviewed E3 figure hash changed: '+name)
 output_files=[out/'E3_FINAL_CELL_LEDGER_69.csv',out/'E3_FINAL_ROUTE_REPETITIONS.csv',report_path]
 rec={'experiment':3,'status':'all 69 planned evaluation cases are validated terminal; 64 scored, 3 scientific failures, 2 unavailable dependencies','publication_status':('reproduced_from_validated_curated_history' if OFFLINE_PARTIAL_PROJECTION_USED_KEYS else 'reviewed_descriptive_terminal'),'observed_utc':now.strftime('%Y-%m-%dT%H:%M:%SZ'),'observed_asia_kolkata':local.isoformat(),'registry_observed_utc':registry.get('observed_utc'),'protocol_version':manifest.get('protocol_version'),'original_plan_freeze_utc':manifest.get('original_plan_freeze_utc'),'plan_tasks':153,'scientific_cells':69,'outcomes':counts,'fit_dependencies':fitcounts,'generation_dependencies':gen_counts,'generator_provenance':{'reused_e2_reconstructed':len(reuse),'new_e3_fits':len(newfit),'reused_predictive_components_equal':sum(x['all_predictive_components_equal']=='True' for x in reuse_component),'e2_e3_exact_float_accuracy_matches':sum(x['exact_float_score_match']=='True' for x in reuse_scores),'identity_inferred_from_score':False},'generation_rows':{'datasets':15,'rows_per_dataset':400000,'total_dataset_rows_counted':6000000,'class_allocation':'largest remainder from matching repetition real-fit proportions'},'conformal':{'score':'1-p_true','calibration_n':10000,'nominal':0.9,'k':9001,'threshold_membership':'1-p_class <= threshold','bootstrap':False},'resource_policy_history':manifest.get('resource_policy_history'),'phase_cost_summary_unique_task_attempt_stage':phase_cost_summary,'unique_fit_trial_cost_summary':trial_cost_summary,'publication_review':{'status':('reproduced_from_validated_curated_history' if OFFLINE_PARTIAL_PROJECTION_USED_KEYS else 'reviewed_descriptive_terminal'),'root_semantic_review':('original_metrics_review_only' if OFFLINE_PARTIAL_PROJECTION_USED_KEYS else 'pass'),'root_visual_review':('original_figures_hash_matched' if OFFLINE_PARTIAL_PROJECTION_USED_KEYS else 'pass'),'figures':{'E3_balanced_accuracy_route_comparison.png':'b6d707b3df3e88f7e46846ec17bf3206919c14c44bdc5c11be7e9d4bff9a4775','E3_coverage_route_comparison.png':'d5f9f3daffe81f4cbda3840a4b7c1805cea9ead09851dd40633ec954fbd7cdaf','E3_set_size_route_comparison.png':'213b580602d405074ada24c2ff6558aec669c8df61ea489f3571218c5ae92bfb'}},'files':{'report':str(report_path),'ledger':str(output_files[0]),'route_repetitions':str(output_files[1])},'input_sha256':input_hashes,'output_sha256':{str(x):sha(x) for x in output_files},'actions':{'model_loads':0,'fits':0,'tuning':0,'generation':0,'calibration':0,'test_inference':0,'bootstrap':0}}
 receipt_path=out/'E3_FINAL_REPORT_RECEIPT_20261025.json';receipt_path.write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 print(json.dumps({'report':str(report_path),'cells':len(case_rows),'routes':len(route_rows),'receipt':str(receipt_path),'outcomes':counts,'input_sha256':input_hashes,'output_sha256':{str(x):sha(x) for x in output_files+[receipt_path]}},indent=2))
if __name__=='__main__':main()
