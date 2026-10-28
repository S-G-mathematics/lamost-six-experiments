#!/usr/bin/env python3
"""Data-only E4 direct KNN block audit; never loads pipelines or held-out arrays."""
from __future__ import annotations
import argparse,csv,datetime as dt,hashlib,json,math,os,pathlib,sqlite3,statistics,sys,time
ROOT=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023');R=ROOT/'runtime_20261025';OUT=R/'reports/e4_direct_knn_block_20261027';REG=R/'registry.sqlite'
CLASSES=['A','F','G','K','M','GALAXY','QSO']; TARGETS=[('A',0),('F',1),('G',2),('K',3),('M',4),('GALAXY',5),('QSO',6)]; SEVERITIES=[('half',0.5),('tenth',0.1)]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def jread(p):return json.loads(pathlib.Path(p).read_text())
def writecsv(path,rows):
 fields=list(dict.fromkeys(k for row in rows for k in row))
 with pathlib.Path(path).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
def read_registry():
 expected=[f'e4/rep_{rep}/eval/direct/knn/control' for rep in (1,2,3)]
 expected += [f'e4/rep_{rep}/eval/direct/knn/{target}_{sev}' for rep in (1,2,3) for target,_ in TARGETS for sev,_ in SEVERITIES]
 c=sqlite3.connect('file:'+str(REG)+'?mode=ro',uri=True,timeout=8);c.execute('PRAGMA query_only=ON')
 try:
  out=[]
  for k in expected:
   row=c.execute('SELECT record FROM tasks WHERE key=?',(k,)).fetchone()
   if row is None:raise RuntimeError('Planned evaluation missing from registry: '+k)
   out.append((k,json.loads(row[0]),hashlib.sha256(row[0].encode()).hexdigest()))
  return out
 finally:c.close()
def trial_history(fitdir,task):
 if task.get('selection_mode')!='tune':return [],None
 cps=sorted((pathlib.Path(fitdir)/'checkpoints').glob('*/trial_history.json'))
 if len(cps)!=1:raise RuntimeError(f'Expected one saved trial history: {fitdir}')
 hist=jread(cps[0]);budget=int(task.get('trials',-1))
 if budget<0 or len(hist)!=budget:raise RuntimeError(f'Trial history count does not match task record: {fitdir}')
 if [int(x.get('number',-1)) for x in hist]!=list(range(budget)):raise RuntimeError(f'Trial history numbers are incomplete: {fitdir}')
 return hist,sha(cps[0])
def validate(rows):
 planned={k for k,_,_ in rows}
 expected={f'e4/rep_{rep}/eval/direct/knn/control' for rep in (1,2,3)}|{f'e4/rep_{rep}/eval/direct/knn/{t}_{s}' for rep in (1,2,3) for t,_ in TARGETS for s,_ in SEVERITIES}
 if len(rows)!=45 or planned!=expected:raise RuntimeError('Direct KNN E4 block must contain exactly 45 unique planned cells')
 order=jread(R/'manifests/authorization_and_decisions.json').get('class_order')
 if order!=CLASSES:raise RuntimeError(f'Class-order manifest mismatch: {order}')
 metrics=[];classes=[];histograms=[];provenance=[];trialrows=[]
 for key,rec,registry_sha in rows:
  if (rec.get('status'),rec.get('outcome'),rec.get('validation_state'))!=('validated_terminal','successful','validated'):raise RuntimeError('Unvalidated/non-success E4 evaluation: '+key)
  rep=int(key.split('/')[1].split('_')[1]);cond=key.rsplit('/',1)[1]
  if cond=='control':target=None;target_idx=None;severity=None;ratio=None
  else:
   target,sev=cond.rsplit('_',1);target_idx=dict((n,i) for n,i in TARGETS)[target];ratio=dict(SEVERITIES)[sev];severity=sev
  if rec.get('experiment')!=4 or rec.get('method')!='knn' or rec.get('route')!='direct' or not rec.get('scientific_case') or rec.get('rep')!=rep:raise RuntimeError('Evaluation registry identity mismatch: '+key)
  if rec.get('condition')!=cond or rec.get('target_class')!=target_idx or rec.get('ratio')!=ratio:raise RuntimeError('Target/severity metadata differs from planned key: '+key)
  ep=R/'artifacts'/key/'evaluation.json'
  if not ep.is_file():raise RuntimeError('Missing evaluation.json: '+key)
  vr=((rec.get('result') or {}).get('validation') or {})
  if vr.get('status')!='validated' or vr.get('task_key')!=key:raise RuntimeError('Registry evaluation validation receipt missing/mismatched: '+key)
  evsha=sha(ep);expected_sha=(vr.get('files') or {}).get('evaluation.json')
  if not expected_sha or evsha!=expected_sha:raise RuntimeError('Evaluation JSON SHA mismatch: '+key)
  ev=jread(ep)
  if ev.get('task_key')!=key or ev.get('experiment')!=4 or int(ev.get('repetition',-1))!=rep:raise RuntimeError('Evaluation file identity mismatch: '+key)
  if int(ev.get('test_n',-1))!=500000 or int(ev.get('calibration_n',-1))!=10000:raise RuntimeError('Unexpected evaluation cohort sizes: '+key)
  if ev.get('score_kind')!='probability':raise RuntimeError('Unexpected KNN score convention: '+key)
  cm=ev.get('confusion_matrix')
  if not isinstance(cm,list) or len(cm)!=7 or any(not isinstance(x,list) or len(x)!=7 for x in cm):raise RuntimeError('Expected seven-class 7x7 confusion matrix: '+key)
  cm=[[int(x) for x in row] for row in cm];support=[sum(row) for row in cm]
  if sum(support)!=500000:raise RuntimeError('Confusion matrix does not total fixed test cohort: '+key)
  pc=ev.get('per_class')
  if not isinstance(pc,dict) or set(pc)!={str(i) for i in range(7)}:raise RuntimeError('Missing seven-class per-class evaluation: '+key)
  recalls=[]
  for ci,label in enumerate(CLASSES):
   z=pc[str(ci)];n=int(z.get('n',-1));recall=cm[ci][ci]/support[ci]
   if n!=support[ci] or not math.isclose(float(z['recall']),recall,rel_tol=0,abs_tol=1e-12):raise RuntimeError(f'Per-class support/recall mismatch: {key}/{label}')
   recalls.append(recall)
   classes.append({'task_key':key,'rep':rep,'condition':cond,'target_class':target or '','severity':severity or '', 'ratio':ratio if ratio is not None else '', 'class_index':ci,'class_label':label,'support':n,'recall':recall,'coverage':float(z['coverage']),'mean_set_size':float(z['set_size']),'evaluation_sha256':evsha})
  ba=sum(recalls)/7
  if not math.isclose(ba,float(ev['balanced_accuracy']),rel_tol=0,abs_tol=1e-12):raise RuntimeError('Balanced accuracy does not reproduce from confusion matrix: '+key)
  fitkey=ev.get('fit_key')
  if not fitkey:raise RuntimeError('Evaluation missing fit provenance: '+key)
  fd=R/'artifacts'/fitkey; fresult=jread(fd/'fit_result.json');sel=jread(fd/'selection.json');fv=jread(fd/'validation.json');pub=jread(fd/'fit_publication.json');fr=fresult.get('result') or {};ft=fresult.get('task') or {};params=sel.get('selected_params') or fr.get('params')
  if fresult.get('status')!='successful' or fr.get('status')!='success' or fv.get('status')!='validated' or fv.get('task_key')!=fitkey:raise RuntimeError('Fit not validly published: '+fitkey)
  pipe=fd/'pipeline.joblib';pipeline_sha=sha(pipe);fit_expected=(fv.get('files') or {}).get('pipeline.joblib')
  if not fit_expected or pipeline_sha!=fit_expected or pipeline_sha!=ev.get('pipeline_sha256') or pipeline_sha!=fresult.get('artifact_sha256') or pipeline_sha!=pub.get('pipeline_sha256'):raise RuntimeError('Pipeline publication/evaluation SHA mismatch: '+fitkey)
  if int(fr.get('training_rows',-1))!=80000 or sum(fr.get('class_counts') or [])!=80000:raise RuntimeError('Fit cohort is not 80k rows: '+fitkey)
  for h in ['training_ids_sha256','training_X_sha256','training_y_sha256','source_sha256']:
   if not fr.get(h):raise RuntimeError(f'Missing {h} role/source identity: {fitkey}')
  if ev.get('fit_key')!=fitkey:raise RuntimeError('Evaluation fit key mismatch: '+key)
  # Exact class histograms come from fit/cohort metadata; no arrays are read.
  counts=[int(x) for x in fr['class_counts']];cohortkey=ft.get('train_key');cohort_meta={};cohort_sha='';cohort_ids_sha=''
  if target is None:
   if fitkey!=f'e4/rep_{rep}/fit/direct/knn/control' or ft.get('selection_mode')!='fixed' or int(ft.get('trials',-1))!=0:raise RuntimeError('Control fit not the matched fixed baseline: '+fitkey)
   impdir=pathlib.Path(ft.get('selection_source') or '');impfile=impdir/'selection.json'
   if not impfile.is_file():raise RuntimeError('Imported frozen E1 selection missing: '+fitkey)
   imp=jread(impfile);src=pathlib.Path(imp.get('source_path') or '')
   if imp.get('source_status')!='complete' or not src.is_file() or sha(src)!=imp.get('source_sha256') or imp.get('selected_params')!=params:raise RuntimeError('Imported E1 KNN selection provenance mismatch: '+fitkey)
   if ft.get('selection_policy')!='import_successful_E1_params_or_tune_if_unavailable':raise RuntimeError('Unexpected control selection policy: '+fitkey)
   hist=[];hist_sha=''; imported_sha=sha(impfile);e1sha=imp.get('source_sha256');e1path=str(src)
  else:
   expected_cohort=f'e4/rep_{rep}/cohort/{cond}'
   if fitkey!=f'e4/rep_{rep}/fit/direct/knn/{cond}' or cohortkey!=expected_cohort:raise RuntimeError('Altered model did not use matching cohort dependency: '+fitkey)
   if ft.get('selection_mode')!='tune' or ft.get('selection_policy')!='tune_on_matching_altered_cohort':raise RuntimeError('Altered fit selection policy mismatch: '+fitkey)
   cp=R/'artifacts'/cohortkey;cohort_meta=jread(cp/'metadata.json');cv=jread(cp/'validation.json');cohort_data=cp/'data.npz';cohort_sha=sha(cohort_data)
   if cv.get('status')!='validated' or cv.get('task_key')!=cohortkey or cohort_sha!=(cv.get('files') or {}).get('data.npz'):raise RuntimeError('Altered cohort data SHA/validation mismatch: '+cohortkey)
   if fr.get('source_sha256')!=cohort_sha:raise RuntimeError('Fit source hash differs from validated altered cohort: '+fitkey)
   if cohort_meta.get('task_key')!=cohortkey or cohort_meta.get('target_class')!=target_idx or cohort_meta.get('ratio')!=ratio or cohort_meta.get('N')!=80000:raise RuntimeError('Cohort metadata target/ratio/size mismatch: '+cohortkey)
   cc=[int(x) for x in cohort_meta.get('realized_counts',[])]
   if cc!=counts or cc!=[int(x) for x in cohort_meta.get('planned_counts',[])]:raise RuntimeError('Fit counts do not match exact validated cohort histogram: '+fitkey)
   hist,hist_sha=trial_history(fd,ft)
   if len(hist)!=int(ft.get('trials',-1)):raise RuntimeError('Actual saved trial count differs from task record: '+fitkey)
   imported_sha='';e1sha='';e1path='';cohort_ids_sha=cohort_meta.get('ids_sha256','')
   for tr in hist:trialrows.append({'fit_key':fitkey,'rep':rep,'condition':cond,'target_class':target,'severity':severity,'trial_number':tr.get('number'),'status':tr.get('status'),'params_json':json.dumps(tr.get('params') or {},sort_keys=True),'tuning_score':tr.get('score'),'recorded_seconds':tr.get('seconds'),'trial_history_sha256':hist_sha})
   if ev.get('fit_key')!=fitkey:raise RuntimeError('Altered evaluation does not use cohort-specific fit: '+key)
  for ci,label in enumerate(CLASSES):histograms.append({'fit_key':fitkey,'task_key':key,'rep':rep,'condition':cond,'target_class':target or '','severity':severity or '', 'ratio':ratio if ratio is not None else '', 'class_index':ci,'class_label':label,'row_count':counts[ci],'class_share':counts[ci]/80000,'total_fit_rows':80000,'cohort_ids_sha256':cohort_ids_sha,'cohort_data_sha256':cohort_sha})
  m={'task_key':key,'rep':rep,'condition':cond,'target_class':target or '','target_class_index':target_idx if target_idx is not None else '', 'severity':severity or '', 'ratio':ratio if ratio is not None else '', 'fit_key':fitkey,'balanced_accuracy':float(ev['balanced_accuracy']),'target_recall':float(pc[str(target_idx)]['recall']) if target_idx is not None else '', 'coverage':float(ev['coverage']),'mean_set_size':float(ev['set_size']),'calibration_n':int(ev['calibration_n']),'test_n':int(ev['test_n']),'calibration_fallback_count':ev.get('calibration_fallback_count'),'test_fallback_count':ev.get('test_fallback_count'),'score_kind':ev.get('score_kind'),'threshold':ev.get('threshold'),'confusion_matrix_total':sum(support),'evaluation_sha256':evsha,'registry_evaluation_row_sha256':registry_sha}
  metrics.append(m)
  t_hist=hist
  status_counts={}
  for x in t_hist:status_counts[x.get('status','unknown')]=status_counts.get(x.get('status','unknown'),0)+1
  provenance.append({'evaluation_key':key,'fit_key':fitkey,'fit_result_sha256':sha(fd/'fit_result.json'),'selection_json_sha256':sha(fd/'selection.json'),'fit_validation_sha256':sha(fd/'validation.json'),'fit_publication_sha256':sha(fd/'fit_publication.json'),'pipeline_sha256':pipeline_sha,'selection_mode':ft.get('selection_mode'),'selection_policy':ft.get('selection_policy'),'selection_key':ft.get('selection_key'),'selection_source':ft.get('selection_source'),'selection_source_sha256':sel.get('source_sha256'),'selected_params_json':json.dumps(params,sort_keys=True),'trial_budget_recorded':ft.get('trials'),'trial_history_rows':len(t_hist),'trial_history_status_counts_json':json.dumps(status_counts,sort_keys=True),'trial_history_sha256':hist_sha,'fit_seconds':fr.get('fit_seconds'),'training_rows':fr.get('training_rows'),'training_class_counts_json':json.dumps(counts),'training_ids_sha256':fr.get('training_ids_sha256'),'training_X_sha256':fr.get('training_X_sha256'),'training_y_sha256':fr.get('training_y_sha256'),'fit_source_sha256':fr.get('source_sha256'),'cohort_key':cohortkey or '', 'cohort_data_sha256':cohort_sha,'cohort_ids_sha256':cohort_ids_sha,'imported_E1_selection_file_sha256':imported_sha,'original_E1_selected_config_sha256':e1sha,'original_E1_selected_config_path':e1path,'engine_code_sha256':fresult.get('engine_code_sha256'),'registry_eval_row_sha256':registry_sha})
 return metrics,classes,histograms,provenance,trialrows

def paired(metrics,classes):
 by={(r['rep'],r['condition']):r for r in metrics};cb={(r['rep'],r['condition'],r['class_index']):r for r in classes};pairs=[];classpairs=[]
 for rep in (1,2,3):
  control=by[(rep,'control')]
  for target,_ in TARGETS:
   for sev,ratio in SEVERITIES:
    cond=f'{target}_{sev}';cur=by[(rep,cond)]
    cr=cb[(rep,cond,dict(TARGETS)[target])];base=cb[(rep,'control',dict(TARGETS)[target])]
    z={'rep':rep,'condition':cond,'target_class':target,'severity':sev,'ratio':ratio,'control_key':control['task_key'],'altered_key':cur['task_key'],'paired_available':True,'n_pairs':1,'target_recall_control':base['recall'],'target_recall_altered':cr['recall'],'target_recall_difference_altered_minus_control':cr['recall']-base['recall']}
    for metric in ['balanced_accuracy','coverage','mean_set_size']:
     z[f'control_{metric}']=control[metric];z[f'altered_{metric}']=cur[metric];z[f'difference_{metric}_altered_minus_control']=cur[metric]-control[metric]
    pairs.append(z)
    for ci,label in enumerate(CLASSES):
     a=cb[(rep,cond,ci)];b=cb[(rep,'control',ci)]
     row={'rep':rep,'condition':cond,'target_class':target,'severity':sev,'ratio':ratio,'class_index':ci,'class_label':label,'control_key':b['task_key'],'altered_key':a['task_key'],'paired_available':True}
     for met in ['recall','coverage','mean_set_size']:
      row[f'control_{met}']=b[met];row[f'altered_{met}']=a[met];row[f'difference_{met}_altered_minus_control']=a[met]-b[met]
     classpairs.append(row)
 def summary(rows,fields,metrics):
  groups={}
  for x in rows:groups.setdefault(tuple(x[k] for k in fields),[]).append(x)
  out=[]
  for key,rs in sorted(groups.items()):
   z={k:v for k,v in zip(fields,key)};z.update(planned_pairs=3,matched_n=len(rs))
   for m in metrics:
    vals=[float(r[f'difference_{m}_altered_minus_control']) for r in rs]
    z[f'mean_difference_{m}']=statistics.mean(vals) if vals else None
    z[f'sample_sd_difference_{m}']=statistics.stdev(vals) if len(vals)>1 else None
    z[f'individual_rep_differences_{m}']=';'.join(f"{x['rep']}:{x[f'difference_{m}_altered_minus_control']:.12g}" for x in sorted(rs,key=lambda y:y['rep']))
   out.append(z)
  return out
 sums=summary(pairs,['target_class','severity','ratio'],['balanced_accuracy','coverage','mean_set_size'])
 # Pair-table target recall uses its special named column.
 for z in sums:
  vals=[]
  for r in pairs:
   if r['target_class']==z['target_class'] and r['severity']==z['severity']:vals.append((r['rep'],r['target_recall_difference_altered_minus_control']))
  z['mean_difference_target_recall']=statistics.mean(v for _,v in vals) if vals else None
  z['sample_sd_difference_target_recall']=statistics.stdev(v for _,v in vals) if len(vals)>1 else None
  z['individual_rep_differences_target_recall']=';'.join(f'{rep}:{v:.12g}' for rep,v in sorted(vals))
 cs=summary(classpairs,['target_class','severity','ratio','class_index','class_label'],['recall','coverage','mean_set_size'])
 return pairs,classpairs,sums,cs

def report_text(metrics,sums,prov):
 direct=[x for x in prov if x['selection_mode']=='tune'];trial_counts={}
 for x in direct:
  for st,n in json.loads(x['trial_history_status_counts_json']).items():trial_counts[st]=trial_counts.get(st,0)+int(n)
 controls=[x for x in prov if x['selection_mode']=='fixed']
 lines=['# E4 direct KNN imbalance block','',
 'Scope: the direct K-nearest-neighbor route only. The block contains three unchanged controls plus seven target classes at half-share and one-tenth-share severity in each of three repetitions. The full E4 restoration grid is not summarized here. This block does not complete E4.','',
 'All 45 planned evaluations validated successfully. Each of the 42 altered-cohort evaluations is paired with the unchanged control from the same repetition. Differences are altered minus control. The condition summaries show n/3, arithmetic means and sample standard deviations across the three paired repetitions. Sample SD is descriptive variability, not a confidence interval. No bootstrap or significance tests were used.','',
 'Class order is A, F, G, K, M, GALAXY, QSO. All evaluations used 10,000 calibration rows and 500,000 fixed test rows. Seven-class confusion-matrix recomputation agrees with recorded balanced accuracy. Overall and classwise conformal coverage and prediction-set sizes are reported together. The nominal 90% target does not imply 90% coverage for every class.','',
 f'Controls: {len(controls)} fixed-configuration E4 fits reused the successful imported E1-selected KNN settings (zero tuning trials). Altered KNN fits were selected on their matching altered fitting cohorts. Actual saved trial-history rows: {sum(int(x["trial_history_rows"]) for x in direct)} across {len(direct)} altered fits; status counts are {json.dumps(trial_counts,sort_keys=True)}. These counts are read from saved task/history records, including duplicate-cached trials; see provenance and trial-history CSVs.','',
 '| Target | Retained share | Matched n/3 | Change target recall | SD | Change balanced accuracy | SD | Change overall coverage | SD | Change set size | SD |',
 '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
 for x in sums:
  vals=[x['mean_difference_target_recall'],x['sample_sd_difference_target_recall'],x['mean_difference_balanced_accuracy'],x['sample_sd_difference_balanced_accuracy'],x['mean_difference_coverage'],x['sample_sd_difference_coverage'],x['mean_difference_mean_set_size'],x['sample_sd_difference_mean_set_size']]
  lines.append(f"| {x['target_class']} | {x['ratio']:.1f} | {x['matched_n']}/3 | {vals[0]:.6f} | {vals[1]:.6f} | {vals[2]:.6f} | {vals[3]:.6f} | {vals[4]:.6f} | {vals[5]:.6f} | {vals[6]:.6f} | {vals[7]:.6f} |".replace(' |',' |',1))
 lines+=['','Severity `0.5` retains half the target class\'s original fitting share; `0.1` retains one-tenth. Exact realized class counts, source histograms, selected parameters and each repetition are in the CSV files. No generated restoration, weighting, oversampling or SMOTE comparisons are included in this direct-method block.','',
 '## Limits','',
 'The findings describe direct KNN for these target/severity/repetition combinations. Per-class recall changes are target-specific; an improvement for one class or severity does not establish a general benefit. E4-wide coverage, failures and other methods are not inferred from this subset. Global E5 q replay validation remains pending. All durations are hardware-dependent.','',
 'Only registry rows, validation receipts, evaluation JSON, fit and cohort metadata, publication receipts, and saved tuning histories were read. Pipelines and held-out arrays were not loaded; no fitting, prediction, or inference was run.']
 return '\n'.join(lines)+'\n'
def resource_gate():
 import zoneinfo
 sys.path.insert(0,str(R/'source'));import cold_auto_compaction as comp;import observe_progress as progress
 comp.verify_instance();c=comp.load_controller();comp.verify_source_set(c);records,meta=comp.records_readonly();allowed,profile=comp.running_worker_profile(c,records);obs=progress.observe(False)
 if not allowed:raise RuntimeError('Reviewed worker-memory admission denies plots')
 if not obs.get('controller_actual_verified') or obs.get('registry_running_unverified_at_observation'):raise RuntimeError('Controller/worker identity observation incomplete')
 if len(obs.get('workers_actual_verified',[]))!=profile.get('running'):raise RuntimeError('Independent worker identity counts disagree')
 before=c.cpu_idle_cores();time.sleep(1);after=c.cpu_idle_cores();idle=max(before,after)
 if idle<1.0:raise RuntimeError('CPU headroom below one idle core')
 disk=os.statvfs(R);free=disk.f_bavail*disk.f_frsize
 if free<2*1024**3:raise RuntimeError('Storage headroom below 2 GiB')
 busy=[]
 for pp in pathlib.Path('/proc').iterdir():
  if not pp.name.isdigit():continue
  try:argv=[x for x in (pp/'cmdline').read_bytes().decode(errors='replace').split('\\0') if x]
  except OSError:continue
  operands={pathlib.Path(x).name for x in argv if '/' in x};found=operands & {'report_cli.py','cold_auto_compactor.py','cold_store_auditor.py','audit_selected_models.py','finalize_project.py'}
  if found:busy.append(sorted(found))
 if busy:raise RuntimeError('Report/audit/compaction helper is active')
 return {'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'memory_available_bytes':profile['available_bytes'],'commitments':profile['commitments'],'helper_reservation_bytes':profile['helper_reservation_bytes'],'host_reserve_bytes':6*1024**3,'growth_margin_bytes':2*1024**3,'memory_admission_passed':True,'running_worker_count':profile['running'],'workers_identity_verified':len(obs.get('workers_actual_verified',[])),'controller_identity_verified':True,'cpu_idle_cores_observed':idle,'storage_free_bytes':free,'active_report_audit_helpers':False,'required_postcommitment_headroom_bytes':805306368,'plot_as_limit_bytes':1024**3}
def plots(sums,pairs):
 gate=resource_gate();import numpy as np
 if np.__version__!='2.3.5':raise RuntimeError('Expected NumPy 2.3.5 from project venv')
 sys.path.extend(['/home/ubuntu/.local/lib/python3.12/site-packages','/usr/lib/python3/dist-packages']);import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 if matplotlib.__version__!='3.11.2':raise RuntimeError('Unexpected Matplotlib version')
 colors=['#2878b5','#e07a1f','#25855a'];labels=[t for t,_ in TARGETS];cond={(x['rep'],x['condition']):x for x in pairs}
 def panel(ax,sev,metric,title):
  ys=[];means=[];sds=[]
  for target in labels:
   condname=f'{target}_{sev}';field='target_recall_difference_altered_minus_control' if metric=='target_recall' else f'difference_{metric}_altered_minus_control';vals=[float(cond[(rep,condname)][field]) for rep in (1,2,3)]
   yi=labels.index(target);ys.append(yi);means.append(statistics.mean(vals));sds.append(statistics.stdev(vals))
   for rep,v in enumerate(vals):ax.scatter(v,yi+(rep-1)*.14,color=colors[rep],s=25,zorder=3,label=f'Rep {rep+1}' if yi==0 else None)
  ax.errorbar(means,ys,xerr=sds,fmt='D',color='black',ecolor='black',capsize=3,markersize=4,label='Mean +/- sample SD (n=3)',zorder=4)
  ax.axvline(0,color='#555',linestyle='--',linewidth=1);ax.set_yticks(range(7),labels=labels);ax.invert_yaxis();ax.set_title(f'{"Half-share" if sev=="half" else "One-tenth-share"}; n=3 paired reps');ax.set_xlabel(title+' change (altered - unchanged)');ax.grid(axis='x',alpha=.2)
 def make_two(metric,title,filename):
  fig,axs=plt.subplots(1,2,figsize=(11,5.4),sharey=True)
  for ax,sev in zip(axs,['half','tenth']):panel(ax,sev,metric,title)
  handles,leg=axs[0].get_legend_handles_labels();fig.legend(handles,leg,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,-.02));fig.suptitle('E4 direct KNN: '+title+' change by target class and severity');fig.tight_layout(rect=(0,.09,1,.92));fig.savefig(OUT/filename,dpi=165,bbox_inches='tight');plt.close(fig)
 make_two('target_recall','Target-class recall','E4_DIRECT_KNN_TARGET_RECALL_CHANGE.png')
 make_two('balanced_accuracy','Balanced accuracy','E4_DIRECT_KNN_BALANCED_ACCURACY_CHANGE.png')
 fig,axs=plt.subplots(2,2,figsize=(12,9),sharey='row')
 for col,sev in enumerate(['half','tenth']):
  panel(axs[0,col],sev,'coverage','Overall coverage');panel(axs[1,col],sev,'mean_set_size','Mean prediction set size')
 handles,leg=axs[0,0].get_legend_handles_labels();fig.legend(handles,leg,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,-.01));fig.suptitle('E4 direct KNN: coverage and set-size changes by target class and severity');fig.tight_layout(rect=(0,.08,1,.93));fig.savefig(OUT/'E4_DIRECT_KNN_COVERAGE_SET_SIZE_EFFECTS.png',dpi=165,bbox_inches='tight');plt.close(fig)
 (OUT/'plot_resource_gate.json').write_text(json.dumps(gate,indent=2,sort_keys=True)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plots',action='store_true');ap.add_argument('--status-only',action='store_true');a=ap.parse_args();rows=read_registry()
 if a.status_only:
  from collections import Counter
  print(json.dumps({'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'planned':len(rows),'states':dict(Counter((x.get('status'),x.get('outcome'),x.get('validation_state')) for _,x,_ in rows))},default=str));return
 metrics,classes,hists,prov,trials=validate(rows);pairs,classpairs,sums,classsums=paired(metrics,classes)
 writecsv(OUT/'E4_DIRECT_KNN_45_METRICS.csv',metrics);writecsv(OUT/'E4_DIRECT_KNN_42_PAIRED_ALTERED_MINUS_CONTROL.csv',pairs);writecsv(OUT/'E4_DIRECT_KNN_14_CONDITION_SUMMARY.csv',sums)
 writecsv(OUT/'E4_DIRECT_KNN_315_PER_CLASS_METRICS.csv',classes);writecsv(OUT/'E4_DIRECT_KNN_294_PER_CLASS_PAIRED.csv',classpairs);writecsv(OUT/'E4_DIRECT_KNN_98_PER_CLASS_SUMMARY.csv',classsums);writecsv(OUT/'E4_DIRECT_KNN_315_CLASS_HISTOGRAM.csv',hists);writecsv(OUT/'E4_DIRECT_KNN_FIT_PROVENANCE.csv',prov);writecsv(OUT/'E4_DIRECT_KNN_TRIAL_HISTORY.csv',trials)
 (OUT/'E4_DIRECT_KNN_BLOCK_REPORT.md').write_text(report_text(metrics,sums,prov),encoding='utf-8')
 if a.plots:plots(sums,pairs)
 inputs=[R/'manifests/authorization_and_decisions.json',ROOT/'project/benchmark/protocol_source.txt']
 outfiles={}
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name not in {'evidence_manifest.json','FINAL_BLOCK_RECEIPT.json'}:outfiles[p.name]={'bytes':p.stat().st_size,'sha256':sha(p)}
 counts={x.get('selection_mode'):sum(1 for z in prov if z.get('selection_mode')==x.get('selection_mode')) for x in prov}
 rec={'schema':'lamost-e4-direct-knn-block/1','observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'scope':'E4 direct KNN: 3 unchanged controls + 7 targets x 2 severities x 3 repetitions','planned_cells':45,'validated_successful_cells':len(metrics),'altered_cells':42,'paired_altered_minus_control_rows':len(pairs),'per_class_rows':len(classes),'per_class_paired_rows':len(classpairs),'condition_summary_rows':len(sums),'per_class_summary_rows':len(classsums),'histogram_rows':len(hists),'fit_provenance_rows':len(prov),'trial_history_rows':len(trials),'selection_mode_counts':counts,'registry_read_only':True,'registry_eval_row_sha256':{k:s for k,_,s in rows},'evaluation_receipt_and_file_sha_verified':True,'pipeline_file_sha_verified_without_loading':True,'class_order':CLASSES,'test_n':500000,'calibration_n':10000,'BA_recomputed_from_confusion_matrices':True,'no_bootstrap':True,'no_significance_tests':True,'models_loaded':False,'heldout_arrays_loaded':False,'fits_or_inference_run':False,'plot_requested':bool(a.plots),'analysis_script_sha256':sha(pathlib.Path(__file__)),'input_sha256':{str(p):sha(p) for p in inputs},'outputs':outfiles}
 (OUT/'evidence_manifest.json').write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':'success','cells':len(metrics),'pairs':len(pairs),'per_class':len(classes),'per_class_pairs':len(classpairs),'summaries':len(sums),'class_summaries':len(classsums),'histograms':len(hists),'trial_history_rows':len(trials),'plots':a.plots,'out':str(OUT)},indent=2))
if __name__=='__main__':main()
