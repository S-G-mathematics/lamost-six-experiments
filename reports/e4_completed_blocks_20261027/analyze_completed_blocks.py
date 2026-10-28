#!/usr/bin/env python3
"""E4 data-only paired-block analysis. Reads registry/evaluation JSON only; no model access."""
from __future__ import annotations
import csv,datetime as dt,hashlib,json,math,pathlib,sqlite3,statistics,subprocess,sys

ROOT=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
R=ROOT/'runtime_20261025'
REG=R/'registry.sqlite'
OUT=R/'reports/e4_completed_blocks_20261027'
CLASSES=['A','F','G','K','M','GALAXY','QSO']
SUCCESS={'successful'}

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def jread(p):return json.loads(p.read_text())
def writecsv(name,rows):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 fields=list(dict.fromkeys(k for row in rows for k in row))
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
 return p

def fresh_gate():
 # Reproduce the installed controller policy using only stdlib /proc reads:
 # min(before,after) PSS credit; max(before,after) peak; promotion to 10 GiB.
 def start_ticks(pid):
  try:return pathlib.Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()[19]
  except (OSError,IndexError):return None
 def alive(t):
  pid=t.get('pid');ticks=t.get('process_start_ticks')
  try:
   return bool(pid and ticks and start_ticks(pid)==str(ticks) and
       'worker.py' in pathlib.Path(f'/proc/{pid}/cmdline').read_bytes().decode(errors='replace'))
  except OSError:return False
 def process_table():
  out={}
  for proc in pathlib.Path('/proc').iterdir():
   if not proc.name.isdigit():continue
   try:
    rows=(proc/'status').read_text().splitlines()
    parent=int(next(x.split()[1] for x in rows if x.startswith('PPid:')))
    rss=int(next(x.split()[1] for x in rows if x.startswith('VmRSS:')))*1024
    out[int(proc.name)]=(parent,rss)
   except (OSError,StopIteration,ValueError):pass
  return out
 def tree(pid,rows):
  ids={int(pid)}
  for _ in range(12):
   more={p for p,(pp,rss) in rows.items() if pp in ids}
   if more<=ids:break
   ids|=more
  return sum(rows.get(p,(0,0))[1] for p in ids),ids
 def charged(t,rows):
  if not alive(t) or t.get('forced_reason'):return 0
  rss,ids=tree(t['pid'],rows);pss=0
  try:
   for pid in ids:
    data=pathlib.Path('/proc',str(pid),'smaps_rollup').read_text().splitlines()
    pss+=int(next(x.split()[1] for x in data if x.startswith('Pss:')))*1024
  except (OSError,StopIteration,ValueError):return 0
  return min(rss,pss,10*1024**3)
 def available_now():
  for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
   if line.startswith('MemAvailable:'):return int(line.split()[1])*1024
  raise RuntimeError('MemAvailable missing; fail closed')
 cdb=sqlite3.connect('file:'+str(REG)+'?mode=ro',uri=True,timeout=5)
 try:
  cdb.execute('PRAGMA query_only=ON')
  running=[json.loads(raw) for (raw,) in cdb.execute("SELECT record FROM tasks WHERE json_extract(record,'$.status')='running'")]
 finally:cdb.close()
 for t in running:
  if not alive(t):raise RuntimeError('Registry-listed worker identity not alive before memory bracket; fail closed')
 before_rows=process_table()
 before=[max(0,int(charged(t,before_rows) or 0)) for t in running]
 available=available_now()
 after_rows=process_table()
 after=[max(0,int(charged(t,after_rows) or 0)) for t in running]
 for t in running:
  if not alive(t):raise RuntimeError('Worker identity changed during memory bracket; fail closed')
 credits=[min(a,b) for a,b in zip(before,after)]
 peaks=[max(a,b) for a,b in zip(before,after)]
 charges=[]
 for t,credit,peak in zip(running,credits,peaks):
  if t.get('adaptive_promoted_heavy'):base=10*1024**3
  elif t.get('admission_reservation_bytes') is not None:
   base=min(10*1024**3,max(0,int(t['admission_reservation_bytes'])))
  else:raise RuntimeError('Running worker lacks recorded admission reservation; fail closed')
  reservation=10*1024**3 if peak>base else base
  charges.append({'task_key':t.get('key'),'reservation_bytes':reservation,
      'credited_pss_bytes':min(reservation,max(0,credit)),
      'observed_peak_pss_bytes':max(0,peak),'promoted_to_10gib_for_gate':reservation>base})
 candidate=512*1024**2;host=6*1024**3;margin=2*1024**3;floor=8*1024**3
 unused=sum(max(0,x['reservation_bytes']-min(x['reservation_bytes'],x['credited_pss_bytes'])) for x in charges)
 allowed=(available>=floor and available-host-unused-candidate>=margin)
 headroom=available-host-unused-margin
 if not allowed:
  raise RuntimeError(f'Controller memory policy denied 512 MiB analysis reservation: available={available}, unspent_commitments={unused}, host_reserve={host}, growth_margin={margin}')
 for hold in [R/'ADMISSION_HOLD.json',R/'admission_hold.json',R/'locks/admission_hold.json']:
  if hold.exists():raise RuntimeError('Explicit admission hold marker present; fail closed')
 ps=subprocess.run(['ps','-eo','args='],capture_output=True,text=True,check=True).stdout
 busy=[line.strip() for line in ps.splitlines() if any(x in line for x in ['report_cli.py','cold_auto_compaction.py','cold_store_auditor','audit_selected_models'])]
 if busy:raise RuntimeError('Report/audit/compaction helper detected; fail closed')
 return {'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'available_bytes':int(available),
  'running_reservations':charges,'unspent_commitments_bytes':unused,'host_reserve_bytes':host,
  'growth_margin_bytes':margin,'analysis_reservation_bytes':candidate,
  'projected_headroom_before_analysis_bytes':headroom,
  'projected_headroom_after_analysis_bytes':headroom-candidate,'memory_admission_ok':True,
  'minimum_available_floor_bytes':floor,'controller_policy_sha256':sha(R/'source/controller.py'),
  'explicit_admission_hold_found':False,'STORAGE_HOLD_is_lock':False,
  'implementation':'stdlib reproduction of controller.bracketed_worker_memory/memory_admission_ok; no controller import'}

def load_plan():
 # Hold a single read-only SQLite snapshot while selecting only the E4 scientific evaluation rows.
 c=sqlite3.connect('file:'+str(REG)+'?mode=ro',uri=True,timeout=5)
 try:
  c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
  rows=[]
  for key,raw in c.execute("""
   SELECT key,record FROM tasks
   WHERE key LIKE 'e4/rep_%/eval/%'
     AND json_extract(record,'$.scientific_case')=1
   ORDER BY key
  """):
   rec=json.loads(raw);rows.append((key,rec,hashlib.sha256(raw.encode()).hexdigest()))
  return rows
 finally:c.close()

def expected_plan(rows):
 if len(rows)!=1773:raise RuntimeError(f'Expected 1,773 planned E4 evaluation outcomes; got {len(rows)}')
 bykey={k:r for k,r,_ in rows}
 if len(bykey)!=1773:raise RuntimeError('Duplicate E4 scientific evaluation task keys')
 return bykey

def read_successes(rows):
 metrics={};hashes=[]
 auth=jread(R/'manifests/authorization_and_decisions.json')
 if auth.get('class_order')!=CLASSES:raise RuntimeError('Authoritative class order mismatch')
 for key,rec,rowsha in rows:
  if rec.get('outcome') not in SUCCESS:continue
  if rec.get('status')!='validated_terminal' or rec.get('validation_state')!='validated':
   raise RuntimeError(f'Success cell lacks validated terminal state: {key}')
  evpath=R/'artifacts'/key/'evaluation.json'
  if not evpath.is_file():raise RuntimeError(f'Missing evaluation.json for success: {key}')
  validation=(rec.get('result') or {}).get('validation') or {}
  expected=(validation.get('files') or {}).get('evaluation.json')
  actual=sha(evpath)
  if validation.get('status')!='validated' or validation.get('task_key')!=key or not expected or expected!=actual:
   raise RuntimeError(f'Artifact does not match registry validation hash: {key}')
  ev=jread(evpath)
  rep=int(key.split('/')[1].split('_')[1])
  if ev.get('task_key')!=key or int(ev.get('experiment',-1))!=4 or int(ev.get('repetition',-1))!=rep:
   raise RuntimeError(f'Evaluation identity mismatch: {key}')
  if int(ev.get('test_n',-1))!=500000 or int(ev.get('calibration_n',-1))!=10000:
   raise RuntimeError(f'Wrong test/calibration cohort size: {key}')
  cm=ev.get('confusion_matrix')
  if not isinstance(cm,list) or len(cm)!=7 or any(not isinstance(x,list) or len(x)!=7 for x in cm):
   raise RuntimeError(f'Confusion matrix not 7x7: {key}')
  cm=[[int(v) for v in row] for row in cm];support=[sum(x) for x in cm]
  if sum(support)!=500000:raise RuntimeError(f'Confusion matrix total not 500k: {key}')
  pc=ev.get('per_class')
  if not isinstance(pc,dict) or set(pc)!={str(i) for i in range(7)}:raise RuntimeError(f'Invalid per-class class indices: {key}')
  recalls={}
  for i,label in enumerate(CLASSES):
   z=pc[str(i)]
   if int(z.get('n',-1))!=support[i]:raise RuntimeError(f'Class support mismatch: {key}/{label}')
   calc=cm[i][i]/support[i]
   if not math.isclose(calc,float(z['recall']),rel_tol=0,abs_tol=1e-12):raise RuntimeError(f'Recall differs from confusion matrix: {key}/{label}')
   recalls[i]=calc
  ba=sum(recalls.values())/7
  if not math.isclose(ba,float(ev['balanced_accuracy']),rel_tol=0,abs_tol=1e-12):raise RuntimeError(f'Balanced accuracy differs from confusion matrix: {key}')
  metrics[key]={'key':key,'rep':rep,'method':rec.get('method'),'route':rec.get('route'),
   'condition':rec.get('condition'),'target_class':rec.get('target_class'),'ratio':rec.get('ratio'),
   'treatment':rec.get('treatment'),'score_kind':ev.get('score_kind'),
   'balanced_accuracy':float(ev['balanced_accuracy']),'coverage':float(ev['coverage']),
   'mean_set_size':float(ev['set_size']),'test_n':int(ev['test_n']),'calibration_n':int(ev['calibration_n']),
   'calibration_fallback_count':ev.get('calibration_fallback_count'),'test_fallback_count':ev.get('test_fallback_count'),
   'target_recall':None,'target_coverage':None,'target_set_size':None,'evaluation_sha256':actual,
   'registry_task_row_sha256':rowsha,'validation_sha256':expected,
   '_per_class':{str(i):{'recall':float(pc[str(i)]['recall']),'coverage':float(pc[str(i)]['coverage']),'mean_set_size':float(pc[str(i)]['set_size'])} for i in range(7)}}
  if rec.get('target_class') is not None:
   ci=int(rec['target_class']);z=pc[str(ci)]
   metrics[key]['target_recall']=float(z['recall']);metrics[key]['target_coverage']=float(z['coverage'])
   metrics[key]['target_set_size']=float(z['set_size']);metrics[key]['target_class_label']=CLASSES[ci]
  hashes.append({'task_key':key,'registry_task_row_sha256':rowsha,'evaluation_sha256':actual,'validation_sha256':expected})
 return metrics,hashes

def plan_pairs(bykey):
 pairs=[]
 def emit(comparison,arm_key,ref_key,rep,method,target,ratio,treatment):
  arm=bykey.get(arm_key);ref=bykey.get(ref_key)
  row={'comparison':comparison,'rep':rep,'method':method,'target_class':target,
   'target_class_label':CLASSES[int(target)] if target is not None else None,'ratio':ratio,'treatment':treatment,
   'arm_task_key':arm_key,'reference_task_key':ref_key,
   'arm_status':arm.get('status') if arm else 'planned_key_missing','arm_outcome':arm.get('outcome') if arm else 'planned_key_missing',
   'reference_status':ref.get('status') if ref else 'planned_key_missing','reference_outcome':ref.get('outcome') if ref else 'planned_key_missing',
   'pair_available':False}
  pairs.append(row)
 for key,arm in bykey.items():
  if int(arm.get('rep') or 0) not in (1,2,3):raise RuntimeError(f'Unexpected repetition: {key}')
  rep=int(arm['rep']);method=str(arm.get('method'));route=arm.get('route');cond=arm.get('condition')
  if route=='direct' and cond!='control':
   target=arm.get('target_class');ratio=arm.get('ratio')
   refkey=f'e4/rep_{rep}/eval/direct/{method}/control'
   emit('altered_direct_minus_unchanged_control',key,refkey,rep,method,target,ratio,'direct')
  elif route=='treatment':
   target=arm.get('target_class');ratio=arm.get('ratio');treatment=arm.get('treatment')
   untreated=next((k for k,r in bykey.items() if int(r.get('rep') or 0)==rep and r.get('method')==method
      and r.get('route')=='direct' and r.get('condition')!='control'
      and r.get('target_class')==target and r.get('ratio')==ratio),None)
   if untreated is None:raise RuntimeError(f'No matching untreated altered-cohort key for {key}')
   clean=f'e4/rep_{rep}/eval/direct/{method}/control'
   emit('treatment_minus_untreated_altered',key,untreated,rep,method,target,ratio,treatment)
   emit('treatment_minus_unchanged_control',key,clean,rep,method,target,ratio,treatment)
 if len(pairs)!=2730:raise RuntimeError(f'Expected 2,730 planned paired rows, got {len(pairs)}')
 return pairs

def add_metrics(pair_rows,metrics):
 for row in pair_rows:
  a=metrics.get(row['arm_task_key']);b=metrics.get(row['reference_task_key'])
  row['pair_available']=bool(a and b)
  if not (a and b):continue
  if a['rep']!=b['rep']:raise RuntimeError('Pair repetition mismatch')
  for m in ['balanced_accuracy','coverage','mean_set_size']:
   av=a.get(m);bv=b.get(m)
   row[f'arm_{m}']=av;row[f'reference_{m}']=bv
   row[f'difference_{m}_arm_minus_reference']=(av-bv) if av is not None and bv is not None else None
  target=row.get('target_class')
  for outmetric,permetric in [('target_recall','recall'),('target_coverage','coverage'),('target_set_size','mean_set_size')]:
   av=bv=None
   if target is not None:
    av=(a.get('_per_class') or {}).get(str(int(target)),{}).get(permetric)
    bv=(b.get('_per_class') or {}).get(str(int(target)),{}).get(permetric)
   row[f'arm_{outmetric}']=av;row[f'reference_{outmetric}']=bv
   row[f'difference_{outmetric}_arm_minus_reference']=(av-bv) if av is not None and bv is not None else None
  row['arm_score_kind']=a['score_kind'];row['reference_score_kind']=b['score_kind']
  row['arm_evaluation_sha256']=a['evaluation_sha256'];row['reference_evaluation_sha256']=b['evaluation_sha256']

def summarize(pair_rows):
 groups={}
 for r in pair_rows:
  k=(r['comparison'],r['method'],r['target_class'],r['ratio'],r['treatment'])
  groups.setdefault(k,[]).append(r)
 out=[]
 for key,rows in sorted(groups.items(),key=lambda x:tuple('' if v is None else str(v) for v in x[0])):
  rows=sorted(rows,key=lambda x:int(x['rep']))
  if len(rows)!=3 or {int(x['rep']) for x in rows}!={1,2,3}:raise RuntimeError(f'Pair group missing/duplicate repetition: {key}')
  avail=[r for r in rows if r['pair_available']]
  s={'comparison':key[0],'method':key[1],'target_class':key[2],
    'target_class_label':CLASSES[int(key[2])] if key[2] is not None else None,
    'ratio':key[3],'treatment':key[4],'planned_repetitions':3,'matched_n':len(avail),
    'complete_three_rep_pair':len(avail)==3,
    'arm_outcomes_by_rep':';'.join(f"{r['rep']}:{r['arm_outcome']}" for r in rows),
    'reference_outcomes_by_rep':';'.join(f"{r['rep']}:{r['reference_outcome']}" for r in rows)}
  for m in ['balanced_accuracy','coverage','mean_set_size','target_recall','target_coverage','target_set_size']:
   vals=[float(r[f'difference_{m}_arm_minus_reference']) for r in avail if r.get(f'difference_{m}_arm_minus_reference') is not None]
   s[f'n_{m}']=len(vals);s[f'mean_difference_{m}']=statistics.mean(vals) if vals else None
   s[f'sample_sd_difference_{m}']=statistics.stdev(vals) if len(vals)>1 else None
   s[f'individual_differences_{m}']=';'.join(f"{r['rep']}:{float(r[f'difference_{m}_arm_minus_reference']):.12g}" for r in avail if r.get(f'difference_{m}_arm_minus_reference') is not None)
  out.append(s)
 if len(out)!=910:raise RuntimeError(f'Expected 910 E4 paired strata; got {len(out)}')
 return out

def coverage_by_method(rows):
 groups={}
 for _,r,_ in rows:groups.setdefault((r.get('method'),r.get('route'),r.get('treatment')),[]).append(r)
 out=[]
 for key,rs in sorted(groups.items(),key=lambda x:tuple('' if y is None else str(y) for y in x[0])):
  counts={}
  for r in rs:
   state=r.get('outcome') or r.get('status') or 'unknown'
   counts[state]=counts.get(state,0)+1
  out.append({'method':key[0],'route':key[1],'treatment':key[2],'planned_cases':len(rs),
   'successful':counts.get('successful',0),'scientific_failure':counts.get('scientific_failure',0),
   'unsupported':counts.get('unsupported',0),'unavailable_dependency':counts.get('unavailable_dependency',0),
   'waiting_for_dependency':counts.get('waiting_for_dependency',0),
   'running':counts.get('running',0),'other_states_json':json.dumps({k:v for k,v in sorted(counts.items()) if k not in {'successful','scientific_failure','unsupported','unavailable_dependency','waiting_for_dependency','running'}},sort_keys=True)})
 return out

def markdown(summary,coverage,rows,resource):
 bycomp={}
 for row in summary:bycomp.setdefault(row['comparison'],[]).append(row)
 counts={}
 for _,r,_ in rows:
  state=r.get('outcome') or r.get('status') or 'unknown'
  counts[state]=counts.get(state,0)+1
 lines=['# E4 completed paired blocks - descriptive status','',
 f"Observed UTC: {dt.datetime.now(dt.timezone.utc).isoformat()}. This is a bounded E4 snapshot from the SQLite task registry and validated saved evaluation JSONs; E4 was still running during analysis.",
 '',
 f"The 1,773 planned evaluation rows currently include {counts.get('successful',0)} successful, {counts.get('scientific_failure',0)} scientific failures, {counts.get('unsupported',0)} unsupported, {counts.get('unavailable_dependency',0)} unavailable dependencies, and {counts.get('waiting_for_dependency',0)} waiting for dependencies.",
 '',
 'This report includes only three-repetition matched contrasts in its complete-block claims. The CSV summary retains all 910 planned comparison strata, including partial and zero-match rows, and the repetition table retains all 2,730 planned rep-pairs with unmatched states and blank metrics.',
 '',
 '| Comparison | Planned strata | Complete n=3 | Partial n=1-2 | No matched reps |',
 '|---|---:|---:|---:|---:|']
 for name,rs in sorted(bycomp.items()):
  n3=sum(x['matched_n']==3 for x in rs);partial=sum(0<x['matched_n']<3 for x in rs);n0=sum(x['matched_n']==0 for x in rs)
  lines.append(f'| {name} | {len(rs)} | {n3} | {partial} | {n0} |')
 lines+=['',
 '## Full three-repetition comparisons',
 '',
 'All complete strata are enumerated in E4_COMPLETE_THREE_REP_BLOCKS.csv. They report paired changes in balanced accuracy, overall coverage, mean set size, and target-class recall/coverage/set size. Differences are arm minus reference. Values are not pooled across methods, target classes, severities, or treatments; inspect each row with its actual matched n.',
 '',
 '## Planned-cell availability',
 '',
 'The method/route status table shows current coverage by planned method and treatment. Waiting dependencies remain pending; terminal failures and unavailable dependencies are kept separate. No cell was assigned a metric without a validated evaluation JSON.',
 '',
 '| Method | Route | Treatment | Planned | Successful | Scientific failure | Unsupported | Unavailable | Waiting |',
 '|---|---|---|---|---:|---:|---:|---:|---:|']
 for x in coverage:
  lines.append(f"| {x['method']} | {x['route']} | {x['treatment'] or 'none'} | {x['planned_cases']} | {x['successful']} | {x['scientific_failure']} | {x['unsupported']} | {x['unavailable_dependency']} | {x['waiting_for_dependency']} |")
 lines+=['',
 '## Interpretation limits',
 '',
 'This is an available-cell description for the E4 blocks that had validated saved metrics at the observation time; unresolved and failed blocks remain visible in the coverage ledger. It is not the final E4 analysis, and no global calibration-q validation is claimed complete. Conformal set size is interpreted with achieved overall and target-class coverage. Timing/resource feasibility is not inferred from predictive scores. No bootstrap, confidence intervals, significance tests, or test-based selection were used.',
 '',
 'The E4 evaluation score type is retained per arm; numeric conformal thresholds are not compared across probability and native-margin score conventions. Only coverage and set size are used as comparable conformal summaries.',
 '',
 '## Reproduction and evidence',
 '',
 'Run analyze_completed_blocks.py on EC2 with the same runtime. It reads only the E4 scientific-evaluation task rows from registry.sqlite in a read-only transaction and validated evaluation.json files. It does not deserialize pipelines, inspect raw test predictions, or fit/infer. Row and file SHA-256 values are saved in the companion CSV and evidence manifest.',
 '']
 return '\n'.join(lines)+'\n'

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 gate=fresh_gate()
 rows=load_plan();bykey=expected_plan(rows)
 auth=R/'manifests/authorization_and_decisions.json'
 if jread(auth).get('class_order')!=CLASSES:raise RuntimeError('Class order differs from frozen authorization manifest')
 metrics,hashes=read_successes(rows)
 pairs=plan_pairs(bykey);add_metrics(pairs,metrics);summary=summarize(pairs);coverage=coverage_by_method(rows)
 # Expected comparison stratum counts from the frozen E4 design.
 expected={'altered_direct_minus_unchanged_control':238,'treatment_minus_untreated_altered':336,'treatment_minus_unchanged_control':336}
 for k,n in expected.items():
  if sum(x['comparison']==k for x in summary)!=n:raise RuntimeError(f'Unexpected planned block count for {k}')
 writecsv('E4_VALIDATED_EVALUATION_METRICS.csv',[{k:v for k,v in x.items() if not k.startswith('_')} for x in metrics.values()])
 writecsv('E4_PAIRED_REPETITIONS.csv',pairs)
 writecsv('E4_PAIRED_BLOCK_SUMMARY.csv',summary)
 writecsv('E4_COMPLETE_THREE_REP_BLOCKS.csv',[x for x in summary if x['complete_three_rep_pair']])
 writecsv('E4_METHOD_TREATMENT_COVERAGE.csv',coverage)
 writecsv('E4_EVALUATION_INPUT_HASHES.csv',hashes)
 (OUT/'RESOURCE_GATE.json').write_text(json.dumps(gate,indent=2,sort_keys=True)+'\n')
 (OUT/'E4_COMPLETED_BLOCKS_REPORT.md').write_text(markdown(summary,coverage,rows,gate),encoding='utf-8')
 outputs={}
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='EVIDENCE_MANIFEST.json':outputs[p.name]={'bytes':p.stat().st_size,'sha256':sha(p)}
 rowdigest=hashlib.sha256('\n'.join(f'{k}:{h}' for k,_,h in sorted(rows)).encode()).hexdigest()
 inputs={str(auth):sha(auth),str(ROOT/'project/benchmark/protocol_source.txt'):sha(ROOT/'project/benchmark/protocol_source.txt')}
 receipt={'schema':'lamost-e4-completed-paired-blocks/1','observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
  'scope':'E4 validated saved evaluation JSON paired-block description, no plots',
  'planned_evaluation_rows':len(rows),'validated_successful_evaluations':len(metrics),
  'planned_pair_repetition_rows':len(pairs),'paired_summary_strata':len(summary),
  'complete_three_rep_strata':len([x for x in summary if x['complete_three_rep_pair']]),
  'partial_strata':len([x for x in summary if 0<x['matched_n']<3]),
  'zero_match_strata':len([x for x in summary if x['matched_n']==0]),
  'evaluation_hashes_checked_against_registry_validation':True,'confusion_matrix_ba_recomputed':True,
  'class_order':CLASSES,'calibration_n':10000,'test_n':500000,'plots_generated':False,
  'models_loaded':False,'fits_or_inference_run':False,'bootstrap':False,'significance_tests':False,
  'registry_query_scope':'E4 scientific evaluation task rows only; SQLite URI mode=ro, query_only=ON, explicit read transaction',
  'selected_registry_row_count':len(rows),'registry_rows_sha256_concatenation':rowdigest,
  'resource_gate':gate,'analysis_script_sha256':sha(pathlib.Path(__file__)),
  'input_sha256':inputs,'outputs':outputs}
 (OUT/'EVIDENCE_MANIFEST.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':'success','planned':len(rows),'validated_successes':len(metrics),
  'planned_pairs':len(pairs),'summary_strata':len(summary),'complete_n3':receipt['complete_three_rep_strata'],
  'partial':receipt['partial_strata'],'zero_match':receipt['zero_match_strata'],'output':str(OUT)},indent=2))
if __name__=='__main__':main()

