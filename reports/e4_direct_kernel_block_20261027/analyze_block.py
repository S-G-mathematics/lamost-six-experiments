#!/usr/bin/env python3
"""Data-only E4 direct RBF-SVM/KDE block accounting; never loads models or held-out arrays."""
from pathlib import Path
import argparse, ast, csv, datetime as dt, hashlib, json, math, os, sqlite3, statistics, sys
ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023'); R=ROOT/'runtime_20261025'; OUT=R/'reports/e4_direct_kernel_block_20261027'; REG=R/'registry.sqlite'
CLASSES=['A','F','G','K','M','GALAXY','QSO']; METHODS=['rbf_svm','kde']; TARGETS=[('A',0),('F',1),('G',2),('K',3),('M',4),('GALAXY',5),('QSO',6)]; SEVERITIES=[('half',0.5),('tenth',0.1)]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def jread(p): return json.loads(Path(p).read_text())
def writecsv(name,rows,fields=None):
 p=OUT/name
 if fields is None: fields=list(dict.fromkeys(k for r in rows for k in r))
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
 return p
def safe_reason(s):
 if not s:return ('',None,None)
 if s.startswith('phase_timeout: '):
  try:
   d=ast.literal_eval(s.split(': ',1)[1]);return ('phase_timeout',d.get('phase'),float(d.get('seconds')) if d.get('seconds') is not None else None)
  except Exception:return ('phase_timeout','unknown',None)
 if 'scientific_failure' in s:return ('upstream_scientific_failure','dependency',None)
 return ('recorded_reason','',None)
def read_db():
 db=sqlite3.connect('file:'+str(REG)+'?mode=ro',uri=True,timeout=10);db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
 q="SELECT key,record FROM tasks WHERE json_extract(record,'$.experiment')=4 AND json_extract(record,'$.scientific_case')=1 AND json_extract(record,'$.route')='direct' AND json_extract(record,'$.method') IN ('rbf_svm','kde') ORDER BY key"
 records=[]
 for key,blob in db.execute(q): records.append((key,json.loads(blob),hashlib.sha256(blob.encode()).hexdigest()))
 if len(records)!=90 or len({x[0] for x in records})!=90: raise RuntimeError('Expected exactly 90 unique E4 direct-kernel scientific cases')
 return db,records
def status(rec): return rec.get('outcome') or rec.get('status')
def validate():
 db,records=read_db(); rows=[];fitcache={};evalcache={};classmetrics=[]
 counts={m:{} for m in METHODS}; expected=set()
 for rep in (1,2,3):
  for m in METHODS:
   for cond in ['control']+[f'{t}_{s}' for t,_ in TARGETS for s,_ in SEVERITIES]: expected.add(f'e4/rep_{rep}/eval/direct/{m}/{cond}')
 if {k for k,_,_ in records}!=expected: raise RuntimeError('Registry case keys do not match planned 2 x 3 x 15 direct-kernel grid')
 classes=(jread(R/'manifests/authorization_and_decisions.json').get('class_order'))
 if classes!=CLASSES: raise RuntimeError('Class order mismatch')
 for key,rec,recsha in records:
  m=rec['method'];rep=int(rec['rep']);cond=rec['condition']; outcome=status(rec); kind=rec.get('kind')
  if rec.get('validation_state') not in ('validated','validated_terminal_outcome') or rec.get('status')!='validated_terminal': raise RuntimeError('Nonterminal/unvalidated case '+key)
  if m=='kde' and cond=='control':
   if kind!='alias' or outcome!='unavailable_dependency': raise RuntimeError('Expected three KDE control aliases to be unavailable dependencies')
  else:
   if kind!='eval': raise RuntimeError('Expected evaluation task '+key)
   if outcome not in ('successful','scientific_failure','unsupported'): raise RuntimeError('Unexpected terminal state '+key+' '+str(outcome))
  fitkey=rec.get('fit_key')
  source_key=rec.get('source_key') if kind=='alias' else None
  if source_key:
   sr=db.execute('SELECT record FROM tasks WHERE key=?',(source_key,)).fetchone()
   if not sr: raise RuntimeError('Missing aliased source evaluation '+source_key)
   source=json.loads(sr[0]);fitkeys=source.get('dependencies',[])
   if len(fitkeys)!=1: raise RuntimeError('Alias source has no unique fit dependency '+key)
   fitkey=fitkeys[0]
  if not fitkey: raise RuntimeError('No selected fit reference '+key)
  fitrow=db.execute('SELECT record FROM tasks WHERE key=?',(fitkey,)).fetchone()
  if not fitrow: raise RuntimeError('Missing fit task '+fitkey)
  fit=json.loads(fitrow[0]); fitout=status(fit)
  fitpath=R/'artifacts'/fitkey
  frpath=fitpath/'fit_result.json'
  if fitout!='successful' or not frpath.is_file(): raise RuntimeError('Fit was not successfully finalized '+fitkey)
  fitresult=jread(frpath); fresult=fitresult.get('result') or {}; pipeline_sha=fresult.get('pipeline_sha256') or fitresult.get('pipeline_sha256')
  if not pipeline_sha: raise RuntimeError('Missing recorded selected pipeline digest '+fitkey)
  pipeline_path=fitpath/'pipeline.joblib'
  if not pipeline_path.is_file(): raise RuntimeError('Selected model artifact missing '+fitkey)
  fitcache[fitkey]={'record':fit,'result':fitresult,'fit_result_sha256':sha(frpath),'pipeline_sha256':pipeline_sha,'pipeline_bytes':pipeline_path.stat().st_size,'pipeline_mtime_ns':pipeline_path.stat().st_mtime_ns,'fit_seconds':fresult.get('fit_seconds'),'supervised_seconds':(fresult.get('phase_supervision') or {}).get('seconds'),'params':fresult.get('params'),'nominal_trials':fit.get('trials'),'selection_mode':fit.get('selection_mode'),'selection_source':fit.get('selection_source'),'selection_policy':fit.get('selection_policy'),'selection_key':fit.get('selection_key')}
  metric=None; evsha=''; evalpath=R/'artifacts'/key/'evaluation.json'; failure_code=''; failure_phase=''; timeout_elapsed=''
  if outcome=='successful':
   if not evalpath.is_file():raise RuntimeError('Successful cell missing evaluation artifact '+key)
   val=((rec.get('result') or {}).get('validation') or {})
   if val.get('status')!='validated' or val.get('task_key')!=key:raise RuntimeError('Registry validation receipt absent/mismatch '+key)
   evsha=sha(evalpath); expectedsha=((val.get('files') or {}).get('evaluation.json'))
   if not expectedsha or expectedsha!=evsha:raise RuntimeError('Evaluation JSON hash differs from registry validation '+key)
   ev=jread(evalpath)
   if ev.get('task_key')!=key or ev.get('experiment')!=4 or int(ev.get('repetition',-1))!=rep:raise RuntimeError('Evaluation identity mismatch '+key)
   if int(ev.get('test_n',-1))!=500000 or int(ev.get('calibration_n',-1))!=10000:raise RuntimeError('Cohort size mismatch '+key)
   if ev.get('pipeline_sha256')!=pipeline_sha:raise RuntimeError('Evaluation/model identity mismatch '+key)
   if not isinstance(ev.get('confusion_matrix'),list) or len(ev['confusion_matrix'])!=7 or any(len(x)!=7 for x in ev['confusion_matrix']):raise RuntimeError('Confusion matrix shape mismatch '+key)
   cm=[[int(y) for y in x] for x in ev['confusion_matrix']]; supports=[sum(x) for x in cm]
   if sum(supports)!=500000:raise RuntimeError('Confusion matrix support mismatch '+key)
   pc=ev.get('per_class')
   if not isinstance(pc,dict) or set(pc)!={str(i) for i in range(7)}:raise RuntimeError('Missing per-class fields '+key)
   recalls=[]
   for i,label in enumerate(CLASSES):
    d=pc[str(i)]; recall=cm[i][i]/supports[i]
    if int(d.get('n',-1))!=supports[i] or not math.isclose(float(d.get('recall',float('nan'))),recall,rel_tol=0,abs_tol=1e-12):raise RuntimeError('Class support/recall consistency failure '+key+'/'+label)
    classmetrics.append({'task_key':key,'method':m,'rep':rep,'condition':cond,'class_index':i,'class_label':label,'test_support':supports[i],'recall':recall,'coverage':float(d['coverage']),'mean_set_size':float(d['set_size']),'evaluation_sha256':evsha})
    recalls.append(recall)
   ba=sum(recalls)/7
   if not math.isclose(float(ev['balanced_accuracy']),ba,rel_tol=0,abs_tol=1e-12):raise RuntimeError('Balanced accuracy mismatch '+key)
   expected_score='margin' if m=='rbf_svm' else 'probability'
   if ev.get('score_kind')!=expected_score:raise RuntimeError('Unexpected score kind '+key)
   metric={'balanced_accuracy':ba,'coverage':float(ev['coverage']),'mean_set_size':float(ev['set_size']),'target_recall':(recalls[int(rec['target_class'])] if rec.get('target_class') is not None else ''),'score_kind':ev.get('score_kind'),'nonconformity_rule':ev.get('nonconformity_rule'),'prediction_rule':ev.get('prediction_rule'),'test_n':500000,'calibration_n':10000,'calibration_fallback_count':ev.get('calibration_fallback_count'),'test_fallback_count':ev.get('test_fallback_count'),'evaluation_sha256':evsha}
   evalcache[key]=metric
  else:
   failure_code,failure_phase,timeout_elapsed=safe_reason(rec.get('reason'))
   if m=='kde' and cond=='control':
    failure_code='upstream_e3_direct_kde_evaluation_unavailable';failure_phase='evaluate';
  targetname='';severity='';ratio=rec.get('ratio')
  if cond!='control':
   targetname, severity=cond.rsplit('_',1)
  rr={'task_key':key,'method':m,'rep':rep,'kind':kind,'condition':cond,'target_label':targetname,'target_class_index':rec.get('target_class') if targetname else '', 'severity':severity,'target_ratio':ratio if ratio is not None else '', 'outcome':outcome,'validation_state':rec.get('validation_state'),'fit_key':fitkey,'selected_model_available':True,'fit_outcome':fitout,'fit_result_sha256':fitcache[fitkey]['fit_result_sha256'],'pipeline_sha256_recorded':pipeline_sha,'pipeline_bytes':fitcache[fitkey]['pipeline_bytes'],'selection_source':fitcache[fitkey]['selection_source'] or '','fit_seconds_recorded':fitcache[fitkey]['fit_seconds'] if fitcache[fitkey]['fit_seconds'] is not None else '', 'fit_supervised_phase_seconds':fitcache[fitkey]['supervised_seconds'] if fitcache[fitkey]['supervised_seconds'] is not None else '', 'evaluation_sha256':evsha,'score_kind':(metric or {}).get('score_kind',''),'nonconformity_rule':(metric or {}).get('nonconformity_rule',''),'prediction_rule':(metric or {}).get('prediction_rule',''),'balanced_accuracy':(metric or {}).get('balanced_accuracy',''),'coverage':(metric or {}).get('coverage',''),'mean_set_size':(metric or {}).get('mean_set_size',''),'target_recall':(metric or {}).get('target_recall',''),'failure_evidence_type':failure_code,'failure_phase':failure_phase,'timeout_censored_seconds':timeout_elapsed if timeout_elapsed is not None else '', 'reason_reference':(rec.get('reason') or '')[:150] if failure_code.startswith('upstream_') else (f'{failure_code}:{failure_phase}' if failure_code else '')}
  rows.append(rr); counts[m][cond]=outcome
 # enforce method grids
 for m in METHODS:
  if len(counts[m])!=15: raise RuntimeError('Unexpected condition coverage '+m)
 db.close();return rows,classmetrics,fitcache,records

def summary(values):
 if not values:return ('','','',0)
 return (len(values),statistics.mean(values),statistics.stdev(values) if len(values)>1 else '',min(values))
def make_tables(rows,classes,fitcache,records):
 bykey={r['task_key']:r for r in rows}; writecsv('E4_DIRECT_KERNEL_90_OUTCOMES.csv',rows)
 writecsv('E4_DIRECT_KERNEL_18_SUCCESS_METRICS.csv',[r for r in rows if r['outcome']=='successful'])
 writecsv('E4_DIRECT_KERNEL_PER_CLASS_METRICS.csv',classes)
 fits=[]
 for key,d in sorted(fitcache.items()):
  t=d['record']; fits.append({'fit_key':key,'method':t.get('method'),'rep':t.get('rep'),'condition':t.get('condition'),'fit_outcome':t.get('outcome'),'fit_result_sha256':d['fit_result_sha256'],'pipeline_sha256':d['pipeline_sha256'],'pipeline_bytes':d['pipeline_bytes'],'selected_params_json':json.dumps(d['params'],sort_keys=True,separators=(',',':')),'selection_mode':d['selection_mode'],'selection_source':d['selection_source'],'selection_policy':d['selection_policy'],'nominal_trial_budget':d['nominal_trials'],'fit_seconds_recorded':d['fit_seconds'],'supervised_fit_phase_seconds':d['supervised_seconds']})
 writecsv('E4_DIRECT_KERNEL_FIT_PROVENANCE.csv',fits)
 cms={(x['task_key'],x['class_index']):x for x in classes}
 metric_fields=['balanced_accuracy','coverage','mean_set_size','target_recall']
 conds=['control']+[f'{t}_{s}' for t,_ in TARGETS for s,_ in SEVERITIES]
 summaries=[]; pairrows=[]; pairclass=[]
 for method in METHODS:
  for cond in conds:
   selected=[bykey[f'e4/rep_{rep}/eval/direct/{method}/{cond}'] for rep in (1,2,3)]
   success=[r for r in selected if r['outcome']=='successful']
   row={'method':method,'condition':cond,'planned_n':3,'successful_n':len(success),'failure_n':sum(r['outcome']=='scientific_failure' for r in selected),'unavailable_n':sum(r['outcome']=='unavailable_dependency' for r in selected),'unsupported_n':sum(r['outcome']=='unsupported' for r in selected)}
   for f in metric_fields:
    vals=[float(r[f]) for r in success if r.get(f) not in ('',None)]
    n,mean,sd,_=summary(vals);row[f'{f}_n']=n;row[f'{f}_mean']=mean;row[f'{f}_sample_sd']=sd
   summaries.append(row)
  for target,_ in TARGETS:
   for sev,_ in SEVERITIES:
    cond=f'{target}_{sev}'
    for rep in (1,2,3):
     a=bykey[f'e4/rep_{rep}/eval/direct/{method}/{cond}']; c=bykey[f'e4/rep_{rep}/eval/direct/{method}/control']
     available=a['outcome']=='successful' and c['outcome']=='successful'
     pr={'method':method,'rep':rep,'condition':cond,'target_label':target,'severity':sev,'altered_task_key':a['task_key'],'control_task_key':c['task_key'],'altered_status':a['outcome'],'control_status':c['outcome'],'pair_available':available,'unmatched_reason':'' if available else ('altered_'+a['outcome'] if a['outcome']!='successful' else 'control_'+c['outcome'])}
     for f in metric_fields:
      pr[f'{f}_difference_altered_minus_control']=(float(a[f])-float(c[f])) if available and a.get(f) not in ('',None) and c.get(f) not in ('',None) else ''
     pairrows.append(pr)
     for ci,label in enumerate(CLASSES):
      ac=cms.get((a['task_key'],ci)); cc=cms.get((c['task_key'],ci));ok=available and ac is not None and cc is not None
      x={'method':method,'rep':rep,'condition':cond,'target_label':target,'severity':sev,'class_index':ci,'class_label':label,'altered_task_key':a['task_key'],'control_task_key':c['task_key'],'altered_status':a['outcome'],'control_status':c['outcome'],'pair_available':ok,'unmatched_reason':'' if ok else pr['unmatched_reason']}
      for f in ['recall','coverage','mean_set_size']:
       x[f'{f}_difference_altered_minus_control']=(float(ac[f])-float(cc[f])) if ok else ''
      pairclass.append(x)
 writecsv('E4_DIRECT_KERNEL_30_CONDITION_SUMMARY.csv',summaries)
 writecsv('E4_DIRECT_KERNEL_84_PAIRED_ALTERED_MINUS_CONTROL.csv',pairrows)
 writecsv('E4_DIRECT_KERNEL_588_PER_CLASS_PAIRED.csv',pairclass)
 # summarize each planned comparison; n reflects pairs, empty mean/SD when n=0 and SD undefined at n=1.
 ps=[]
 for method in METHODS:
  for target,_ in TARGETS:
   for sev,_ in SEVERITIES:
    cond=f'{target}_{sev}'; group=[x for x in pairrows if x['method']==method and x['condition']==cond]
    row={'method':method,'condition':cond,'target_label':target,'severity':sev,'planned_pairs':3,'matched_pairs':sum(x['pair_available'] for x in group),'unmatched_pairs':sum(not x['pair_available'] for x in group)}
    for f in metric_fields:
     vals=[float(x[f'{f}_difference_altered_minus_control']) for x in group if x['pair_available'] and x[f'{f}_difference_altered_minus_control']!='']
     n,mean,sd,_=summary(vals);row[f'{f}_n']=n;row[f'{f}_mean']=mean;row[f'{f}_sample_sd']=sd
    ps.append(row)
 writecsv('E4_DIRECT_KERNEL_28_PAIRED_SUMMARY.csv',ps)
 pcs=[]
 for method in METHODS:
  for target,_ in TARGETS:
   for sev,_ in SEVERITIES:
    cond=f'{target}_{sev}'
    for ci,label in enumerate(CLASSES):
     group=[x for x in pairclass if x['method']==method and x['condition']==cond and x['class_index']==ci]
     row={'method':method,'condition':cond,'target_label':target,'severity':sev,'class_index':ci,'class_label':label,'planned_pairs':3,'matched_pairs':sum(x['pair_available'] for x in group),'unmatched_pairs':sum(not x['pair_available'] for x in group)}
     for f in ['recall','coverage','mean_set_size']:
      vals=[float(x[f'{f}_difference_altered_minus_control']) for x in group if x['pair_available'] and x[f'{f}_difference_altered_minus_control']!='']
      n,mean,sd,_=summary(vals);row[f'{f}_n']=n;row[f'{f}_mean']=mean;row[f'{f}_sample_sd']=sd
     pcs.append(row)
 writecsv('E4_DIRECT_KERNEL_196_PER_CLASS_PAIR_SUMMARY.csv',pcs)
 return summaries,ps,pcs

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 if any(x.name!='analyze_block.py' for x in OUT.iterdir()): raise RuntimeError('Refusing to overwrite existing block artifacts')
 rows,classes,fitcache,records=validate(); summaries,ps,pcs=make_tables(rows,classes,fitcache,records)
 # Bind every raw input by hash, while never exporting raw registry payloads or process receipts.
 inputs=[]
 for key,rec,recsha in records:
  inputs.append({'task_key':key,'registry_record_sha256':recsha,'outcome':status(rec),'artifact_file':'artifacts/'+key+'/evaluation.json' if status(rec)=='successful' else '', 'artifact_sha256':next((r['evaluation_sha256'] for r in rows if r['task_key']==key),'')})
 writecsv('E4_DIRECT_KERNEL_INPUT_HASHES.csv',inputs)
 counts={m:{o:sum(1 for r in rows if r['method']==m and r['outcome']==o) for o in ['successful','scientific_failure','unavailable_dependency','unsupported']} for m in METHODS}
 # Include the root-owned operational recovery evidence without copying private process details.
 recovery=R/'reports/engineering_audits/BOUNDED_OPERATIONAL_RECOVERY_FINAL_OUTCOMES_20261027.json'; receiptsha=sha(recovery) if recovery.exists() else ''
 op=[]
 if recovery.exists():
  rr=jread(recovery)
  for x in rr.get('records',[]):
   if x.get('evaluation_key')=='e4/rep_3/eval/direct/rbf_svm/K_half': op.append({'evaluation_key':x['evaluation_key'],'evaluation_outcome':x.get('evaluation_outcome'),'evaluation_phase':x.get('evaluation_phase'),'evaluation_censored_seconds':x.get('evaluation_elapsed_seconds'),'fit_key':x.get('fit_key'),'fit_outcome':x.get('fit_outcome'),'public_recovery_receipt_sha256':receiptsha,'interpretation':'An earlier operationally invalid/interrupted fit attempt was retained separately; final selected fit artifact was recovered/validated. The terminal evaluation then reached its ordinary 600s timeout. This does not create a metric or completed evaluation cost.'})
 writecsv('E4_DIRECT_KERNEL_OPERATIONAL_RECOVERY_CONTEXT.csv',op)
 evidence={'schema':'e4-direct-kernel-block-evidence/1','observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'planned_cases':90,'case_counts':counts,'model_dependency_counts':{'rbf_svm':45,'kde_altered':42,'kde_control_aliases':3},'successful_evaluation_count':sum(r['outcome']=='successful' for r in rows),'successful_metric_rows':len([r for r in rows if r['outcome']=='successful']),'per_class_metric_rows':len(classes),'paired_rows':len(ps)*3,'matched_paired_rows':sum(r['matched_pairs'] for r in ps),'model_artifact_hash_rows':len(fitcache),'evidence_input_count':len(inputs),'classes':CLASSES,'cohort_sizes':{'test_n':500000,'calibration_n':10000},'operational_recovery_receipt_sha256':receiptsha,'timing_caveat':'The observed phase time on a 600s timeout is censored deadline evidence, not a completed inference cost. Timed-out cells have no performance metric. Successful fit seconds are recorded phase measurements; queue/interrupted-attempt overhead is not folded into final fit duration.'}
 (OUT/'E4_DIRECT_KERNEL_EVIDENCE.json').write_text(json.dumps(evidence,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'out':str(OUT),'counts':counts,'success_metrics':evidence['successful_metric_rows'],'perclass':len(classes),'matched_pairs':evidence['matched_paired_rows'],'fit_records':len(fitcache),'evidence_sha256':sha(OUT/'E4_DIRECT_KERNEL_EVIDENCE.json')},indent=2))
if __name__=='__main__': main()
