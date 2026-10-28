#!/usr/bin/env python3
"""Data-only E5 direct-RF block audit; never loads models or scores examples."""
from __future__ import annotations
import argparse,csv,datetime as dt,hashlib,json,math,os,pathlib,sqlite3,statistics,subprocess,sys

ROOT=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
R=ROOT/'runtime_20261025'; OUT=R/'reports/e5_direct_rf_block_20261027'
REG=R/'registry.sqlite'
CLASSES=['A','F','G','K','M','GALAXY','QSO']
MECHANISMS=['feature_noise','missingness','label_noise']
RATES=[5,10,20]

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def jread(p): return json.loads(p.read_text())
def writecsv(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 fields=list(dict.fromkeys(k for row in rows for k in row))
 with path.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
def load_rows():
 c=sqlite3.connect('file:'+str(REG)+'?mode=ro',uri=True,timeout=5)
 try:
  c.execute('PRAGMA query_only=ON')
  return [(k,json.loads(raw),hashlib.sha256(raw.encode()).hexdigest()) for k,raw in c.execute(
   "SELECT key,record FROM tasks WHERE key LIKE 'e5/rep_%/eval/direct/random_forest/%' ORDER BY key")]
 finally:c.close()

def validate(rows):
 expected={f'e5/rep_{rep}/eval/direct/random_forest/{cond}' for rep in (1,2,3)
  for cond in ['clean']+[f'{m}_{rate:02d}' for m in MECHANISMS for rate in RATES]}
 if len(rows)!=30 or {k for k,_,_ in rows}!=expected: raise RuntimeError('Expected exactly 30 unique planned E5 direct-RF cells')
 metrics=[]; classes=[]; provenance=[]
 for key,rec,registry_row_sha in rows:
  if (rec.get('status'),rec.get('outcome'),rec.get('validation_state'))!=('validated_terminal','successful','validated'):
   raise RuntimeError(f'Cell is not a validated success: {key}')
  rep=int(key.split('/')[1].split('_')[1]); cond=key.rsplit('/',1)[1]
  isclean=cond=='clean'; mech=None if isclean else next(m for m in MECHANISMS if cond.startswith(m+'_'))
  rate=None if isclean else int(cond.rsplit('_',1)[1])
  if rec.get('experiment')!=5 or rec.get('method')!='random_forest' or rec.get('route')!='direct' or not rec.get('scientific_case'):
   raise RuntimeError(f'Wrong planned-cell metadata for {key}')
  if (rec.get('mechanism'),rec.get('rate'))!=(mech,None if rate is None else rate/100): raise RuntimeError(f'Mechanism/rate does not match cell key: {key}')
  ep=R/'artifacts'/key/'evaluation.json'
  if not ep.is_file(): raise RuntimeError(f'Missing evaluation file: {key}')
  validation=(rec.get('result') or {}).get('validation') or {}
  if validation.get('status')!='validated' or validation.get('task_key')!=key:
   raise RuntimeError(f'Registry validation receipt missing/incorrect: {key}')
  expected_sha=(validation.get('files') or {}).get('evaluation.json'); evsha=sha(ep)
  if not expected_sha or evsha!=expected_sha: raise RuntimeError(f'evaluation.json SHA mismatch: {key}')
  ev=jread(ep)
  if ev.get('task_key')!=key or ev.get('experiment')!=5 or int(ev.get('repetition',-1))!=rep:
   raise RuntimeError(f'Evaluation identity mismatch: {key}')
  if int(ev.get('test_n',-1))!=500000 or int(ev.get('calibration_n',-1))!=10000:
   raise RuntimeError(f'Unexpected calibration/test sizes: {key}')
  cm=ev.get('confusion_matrix')
  if not isinstance(cm,list) or len(cm)!=7 or any(not isinstance(r,list) or len(r)!=7 for r in cm):
   raise RuntimeError(f'Expected 7x7 confusion matrix: {key}')
  cm=[[int(x) for x in row] for row in cm]; supports=[sum(row) for row in cm]
  if sum(supports)!=500000: raise RuntimeError(f'Confusion matrix total differs from fixed test cohort: {key}')
  pc=ev.get('per_class')
  if not isinstance(pc,dict) or set(pc)!={str(i) for i in range(7)}: raise RuntimeError(f'Invalid seven-class per-class fields: {key}')
  recs=[]
  for ci,label in enumerate(CLASSES):
   p=pc[str(ci)]; n=int(p.get('n',-1))
   if n!=supports[ci]: raise RuntimeError(f'Class support mismatch: {key}/{label}')
   recall=cm[ci][ci]/n
   if not math.isclose(recall,float(p['recall']),rel_tol=0,abs_tol=1e-12): raise RuntimeError(f'Confusion/per-class recall mismatch: {key}/{label}')
   recs.append(recall)
   classes.append({'task_key':key,'rep':rep,'condition':cond,'mechanism':mech,'rate_percent':rate,
    'class_index':ci,'class_label':label,'support':n,'recall':float(p['recall']),
    'coverage':float(p['coverage']),'mean_set_size':float(p['set_size']),'evaluation_sha256':evsha})
  ba=sum(recs)/7
  if not math.isclose(ba,float(ev['balanced_accuracy']),rel_tol=0,abs_tol=1e-12):
   raise RuntimeError(f'Balanced accuracy mismatch vs confusion matrix: {key}')
  if ev.get('score_kind')!='probability': raise RuntimeError(f'Unexpected score kind for direct RF: {key}')
  fitkey=ev.get('fit_key')
  if not fitkey: raise RuntimeError(f'Missing fitted pipeline provenance: {key}')
  fitdir=R/'artifacts'/fitkey
  sel=jread(fitdir/'selection.json'); fr=jread(fitdir/'fit_result.json')
  params=sel.get('selected_params') or (fr.get('result') or {}).get('params')
  if not params or fr.get('status')!='successful' or (fr.get('result') or {}).get('status')!='success':
   raise RuntimeError(f'Fit/selection metadata not valid: {key}')
  if int((fr.get('result') or {}).get('training_rows',-1))!=80000: raise RuntimeError(f'Fit is not based on 80k rows: {fitkey}')
  if ev.get('pipeline_sha256')!=fr.get('artifact_sha256'): raise RuntimeError(f'Pipeline SHA disagreement: {key}')
  metric={'task_key':key,'rep':rep,'condition':cond,'mechanism':mech,'rate_percent':rate,
   'outcome':'successful','balanced_accuracy':float(ev['balanced_accuracy']),'coverage':float(ev['coverage']),
   'mean_set_size':float(ev['set_size']),'calibration_n':int(ev['calibration_n']),'test_n':int(ev['test_n']),
   'calibration_fallback_count':int(ev.get('calibration_fallback_count',-1)),
   'test_fallback_count':int(ev.get('test_fallback_count',-1)),'fit_key':fitkey,
   'reused_from':ev.get('reused_from'),'pipeline_sha256':ev.get('pipeline_sha256'),
   'score_kind':ev.get('score_kind'),'threshold':ev.get('threshold'),'evaluation_sha256':evsha,
   'registry_task_row_sha256':registry_row_sha}
  metrics.append(metric)
  provenance.append({'task_key':key,'fit_key':fitkey,'selected_params_json':json.dumps(params,sort_keys=True),
   'selection_sha256':sha(fitdir/'selection.json'),'fit_result_sha256':sha(fitdir/'fit_result.json'),
   'pipeline_sha256':ev.get('pipeline_sha256'),'training_rows':(fr.get('result') or {}).get('training_rows'),
   'training_ids_sha256':(fr.get('result') or {}).get('training_ids_sha256'),
   'registry_task_row_sha256':registry_row_sha})
 # Confirm corrupted RFs retained the exact clean-selected configuration within each repetition.
 by={m['task_key']:m for m in metrics}
 for rep in (1,2,3):
  clean=by[f'e5/rep_{rep}/eval/direct/random_forest/clean']; cfit=R/'artifacts'/clean['fit_key']
  csel=jread(cfit/'selection.json'); cparams=csel.get('selected_params')
  cfr=jread(cfit/'fit_result.json')
  if not cparams: raise RuntimeError(f'Clean selected configuration missing for repetition {rep}')
  for m in metrics:
   if m['rep']!=rep or m['condition']=='clean': continue
   fdir=R/'artifacts'/m['fit_key']; s=jread(fdir/'selection.json'); fr=jread(fdir/'fit_result.json')
   if (s.get('selected_params') or (fr.get('result') or {}).get('params'))!=cparams:
    raise RuntimeError(f'Corrupted RF did not use clean-selected parameters: {m["task_key"]}')
   if m['fit_key']!=f'e5/rep_{rep}/fit/direct/random_forest/{m["condition"]}':
    raise RuntimeError(f'Unexpected E5 corruption fit key: {m["task_key"]}')
   if (fr.get('result') or {}).get('training_ids_sha256')!=(cfr.get('result') or {}).get('training_ids_sha256'):
    raise RuntimeError(f'Fitting IDs differ from matched clean cohort: {m["task_key"]}')
 return metrics,classes,provenance

def paired(metrics,classes):
 by={(r['rep'],r['condition']):r for r in metrics}; pairs=[]
 for rep in (1,2,3):
  clean=by[(rep,'clean')]
  for mech in MECHANISMS:
   for rate in RATES:
    cond=f'{mech}_{rate:02d}';cur=by[(rep,cond)]
    row={'rep':rep,'mechanism':mech,'rate_percent':rate,'condition':cond,'clean_task_key':clean['task_key'],
     'corrupted_task_key':cur['task_key'],'paired_available':True}
    for met in ['balanced_accuracy','coverage','mean_set_size']:
     row[f'clean_{met}']=clean[met];row[f'corrupted_{met}']=cur[met]
     row[f'difference_{met}_corrupted_minus_clean']=cur[met]-clean[met]
    pairs.append(row)
 cb={(r['rep'],r['condition'],r['class_index']):r for r in classes}; cp=[]
 for p in pairs:
  for ci,label in enumerate(CLASSES):
   a=cb[(p['rep'],p['condition'],ci)];b=cb[(p['rep'],'clean',ci)]
   row={'rep':p['rep'],'mechanism':p['mechanism'],'rate_percent':p['rate_percent'],'condition':p['condition'],
    'class_index':ci,'class_label':label,'clean_task_key':b['task_key'],'corrupted_task_key':a['task_key'],'paired_available':True}
   for met in ['recall','coverage','mean_set_size']:
    row[f'clean_{met}']=b[met];row[f'corrupted_{met}']=a[met];row[f'difference_{met}_corrupted_minus_clean']=a[met]-b[met]
   cp.append(row)
 def summary(rows, metrics_to_sum, group_fields):
  groups={}
  for row in rows: groups.setdefault(tuple(row[x] for x in group_fields),[]).append(row)
  out=[]
  for key,rs in sorted(groups.items()):
   s={k:v for k,v in zip(group_fields,key)};s.update(planned_pairs=3,matched_n=len(rs))
   for met in metrics_to_sum:
    vals=[float(x[f'difference_{met}_corrupted_minus_clean']) for x in rs]
    s[f'mean_difference_{met}']=statistics.mean(vals) if vals else None
    s[f'sample_sd_difference_{met}']=statistics.stdev(vals) if len(vals)>1 else None
    s[f'individual_differences_{met}']=';'.join(f'{x["rep"]}:{x[f"difference_{met}_corrupted_minus_clean"]:.12g}' for x in sorted(rs,key=lambda x:x['rep']))
   out.append(s)
  return out
 sums=summary(pairs,['balanced_accuracy','coverage','mean_set_size'],['mechanism','rate_percent','condition'])
 class_sums=summary(cp,['recall','coverage','mean_set_size'],['mechanism','rate_percent','condition','class_index','class_label'])
 return pairs,cp,sums,class_sums

def report_text(sums):
 lines=['# E5 direct random-forest corruption block','',
 'Descriptive results for the direct random-forest route only: three repetitions, one clean control per repetition, and all three fitting-data corruption mechanisms at 5%, 10%, and 20%. This block does not complete E5.',
 '',
 'All 30 planned cells (three clean controls and 27 corrupted cells) are validated. Each corrupted cell is paired with the clean control from the same repetition. Differences are corrupted minus clean. Means and sample SDs use the three paired repetitions; they are descriptive summaries, not confidence intervals. No bootstrap or significance tests were used.',
 '',
 'Class order is A, F, G, K, M, GALAXY, QSO. Each evaluation has 10,000 calibration rows and 500,000 test rows. Balanced accuracy recomputed from the saved seven-by-seven confusion matrices matches the recorded value. Corrupted fits use the repetition-matched clean-selected configuration and fitting IDs; no tuning on corrupted data was used.',
 '',
 '| Mechanism | Rate | Matched n/3 | Change in balanced accuracy | SD | Change in coverage | SD | Change in set size | SD |',
 '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for s in sums:
  lines.append(f"| {s['mechanism']} | {s['rate_percent']}% | {s['matched_n']}/3 | {s['mean_difference_balanced_accuracy']:.6f} | {s['sample_sd_difference_balanced_accuracy']:.6f} | {s['mean_difference_coverage']:.6f} | {s['sample_sd_difference_coverage']:.6f} | {s['mean_difference_mean_set_size']:.6f} | {s['sample_sd_difference_mean_set_size']:.6f} |")
 lines+=['','All individual repetitions and per-class recalls, coverage and set size are in the CSV tables. Interpret set-size changes together with coverage.',
 '',
 '## Limits',
 '',
 'These findings cover only direct random forest under the saved clean-selected configurations and these specified corruption mechanisms. They do not generalize to other classifiers, synthetic routes, or all astronomical measurement errors. The wider E5 grid and its independent global validation remain pending; no overall E5-completion claim follows from this block.',
 '',
 'The analysis read only task records, evaluation JSONs, fit selection/result metadata, and the fixed class-order manifest. It did not load pipelines, fit models, generate predictions, or alter scientific inputs. Per-cell artifact hashes are bound in the output tables and evidence manifest.']
 return '\n'.join(lines)+'\n'

def resource_gate():
 memavail=next(int(x.split()[1])*1024 for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
 c=sqlite3.connect('file:'+str(REG)+'?mode=ro',uri=True,timeout=5);c.execute('PRAGMA query_only=ON')
 running=[json.loads(x[0]) for x in c.execute("SELECT record FROM tasks WHERE json_extract(record,'$.status')='running'")];c.close()
 reserve=sum(int(r.get('admission_reservation_bytes') or 0) for r in running)
 host=max([int((r.get('admission_resource_policy') or {}).get('host_os_harbor_reserve_gib',6)*1024**3) for r in running] or [6*1024**3])
 growth=max([int((r.get('admission_resource_policy') or {}).get('commitment_growth_margin_gib',2)*1024**3) for r in running] or [2*1024**3])
 ids=[]
 for r in running:
  pid=int(r.get('pid') or 0);ticks=int(r.get('process_start_ticks') or -1)
  sp=pathlib.Path(f'/proc/{pid}/stat')
  if not sp.exists(): raise RuntimeError('A registered worker PID is absent; do not plot before a fresh state audit')
  tail=sp.read_text()[sp.read_text().rfind(')')+2:].split()
  if len(tail)<=19 or int(tail[19])!=ticks: raise RuntimeError('Worker PID/start-tick mismatch; do not plot')
  pss=pathlib.Path(f'/proc/{pid}/smaps_rollup')
  pss_kib=next((int(x.split()[1]) for x in pss.read_text().splitlines() if x.startswith('Pss:')),None) if pss.exists() else None
  ids.append({'task_key':r.get('key'),'reservation_bytes':int(r.get('admission_reservation_bytes') or 0),'observed_worker_pss_kib':pss_kib})
 headroom=memavail-reserve-host-growth
 if headroom<805306368: raise RuntimeError('Resource gate denies plots: <0.75 GiB after active worker reservations, host reserve and growth margin')
 for f in [R/'ADMISSION_HOLD.json',R/'admission_hold.json',R/'locks/admission_hold.json']:
  if f.exists(): raise RuntimeError('Explicit admission hold marker exists; do not plot')
 ps=subprocess.run(['ps','-eo','args='],capture_output=True,text=True,check=True).stdout
 busy=[line.strip() for line in ps.splitlines() if any(x in line for x in ['report_cli.py','cold_auto_compactor','cold_store_auditor','audit_selected_models'])]
 busy=[x for x in busy if 'grep ' not in x and 'rg -n' not in x]
 if busy: raise RuntimeError('Report/audit/compaction helper process is active; defer plots')
 return {'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'mem_available_bytes':memavail,'worker_reservations_bytes':reserve,
  'host_reserve_bytes':host,'growth_margin_bytes':growth,'projected_headroom_before_plot_bytes':headroom,
  'plot_memory_ceiling_bytes':805306368,'projected_headroom_after_plot_bytes':headroom-805306368,
  'running_worker_count':len(running),'running_workers':ids,'explicit_admission_hold_marker_found':False,
  'STORAGE_HOLD_treated_as_lock':False}

def plots(metrics):
 gate=resource_gate()
 import numpy as np
 if np.__version__!='2.3.5': raise RuntimeError('Plot gate requires scientific NumPy 2.3.5 imported first')
 sys.path.extend(['/home/ubuntu/.local/lib/python3.12/site-packages','/usr/lib/python3/dist-packages'])
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 if matplotlib.__version__!='3.11.2': raise RuntimeError('Unexpected Matplotlib version')
 by={(m['rep'],m['condition']):m for m in metrics}
 colors=['#2878b5','#e07a1f','#25855a']; x=[0,5,10,20]
 for metric,title,nominal in [('balanced_accuracy','Balanced accuracy',None),('coverage','Overall coverage',.90),('mean_set_size','Mean prediction set size',None)]:
  fig,axs=plt.subplots(1,3,figsize=(12,4),sharey=True)
  vals=[float(m[metric]) for m in metrics]
  low=min(vals);high=max(vals);pad=max((high-low)*.12,.01)
  ymin=max(0,low-pad);ymax=min(7.0 if metric=='mean_set_size' else 1.0,high+pad)
  if nominal is not None:ymin=min(ymin,nominal-.04);ymax=max(ymax,nominal+.04)
  for ax,mech in zip(axs,MECHANISMS):
   repvals=[]
   for rep,color in zip((1,2,3),colors):
    ys=[float(by[(rep,'clean')][metric])]+[float(by[(rep,f'{mech}_{rate:02d}')][metric]) for rate in RATES]
    repvals.append(ys);ax.plot(x,ys,color=color,marker='o',markersize=4,linewidth=1.1,label=f'Rep {rep}')
   mean=np.mean(np.asarray(repvals),axis=0)
   ax.plot(x,mean,color='black',marker='D',markersize=5,linewidth=2,label='Mean (n=3)')
   for xx,yy in zip(x,mean):ax.annotate('n=3',(xx,yy),xytext=(0,8),textcoords='offset points',ha='center',fontsize=7)
   if nominal is not None:ax.axhline(nominal,color='#555',linestyle='--',linewidth=1,label='Nominal 90%' if mech==MECHANISMS[0] else None)
   ax.set_title(mech.replace('_',' ').title());ax.set_xticks(x,labels=['Clean','5%','10%','20%'])
   ax.set_xlabel('Affected fitting rows');ax.grid(axis='y',alpha=.22);ax.set_ylim(ymin,ymax)
  axs[0].set_ylabel(title);handles,labels=axs[0].get_legend_handles_labels()
  fig.legend(handles,labels,loc='lower center',ncol=5,frameon=False,bbox_to_anchor=(.5,-.015))
  fig.suptitle(f'E5 direct random forest: {title} under fitting-data corruption')
  fig.tight_layout(rect=(0,.08,1,.91))
  fig.savefig(OUT/f'E5_DIRECT_RF_{metric.upper()}_CORRUPTION.png',dpi=165,bbox_inches='tight');plt.close(fig)
 (OUT/'plot_resource_gate.json').write_text(json.dumps(gate,indent=2,sort_keys=True)+'\n')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plots',action='store_true');a=ap.parse_args()
 OUT.mkdir(parents=True,exist_ok=True)
 class_order=jread(R/'manifests/authorization_and_decisions.json').get('class_order')
 if class_order!=CLASSES: raise RuntimeError(f'Authoritative class order mismatch: {class_order}')
 rows=load_rows();metrics,classes,prov=validate(rows);pairs,cp,sums,cs=paired(metrics,classes)
 writecsv(OUT/'E5_DIRECT_RF_30_METRICS.csv',metrics)
 writecsv(OUT/'E5_DIRECT_RF_27_PAIRED_CORRUPT_MINUS_CLEAN.csv',pairs)
 writecsv(OUT/'E5_DIRECT_RF_9_CONDITION_SUMMARY.csv',sums)
 writecsv(OUT/'E5_DIRECT_RF_210_PER_CLASS_METRICS.csv',classes)
 writecsv(OUT/'E5_DIRECT_RF_189_PER_CLASS_PAIRED.csv',cp)
 writecsv(OUT/'E5_DIRECT_RF_63_PER_CLASS_SUMMARY.csv',cs)
 writecsv(OUT/'E5_DIRECT_RF_FIT_PROVENANCE.csv',prov)
 (OUT/'E5_DIRECT_RF_BLOCK_REPORT.md').write_text(report_text(sums),encoding='utf-8')
 if a.plots:plots(metrics)
 inputs=[R/'manifests/authorization_and_decisions.json',ROOT/'project/benchmark/protocol_source.txt']
 outfiles={}
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name not in {'evidence_manifest.json'}:
   outfiles[p.name]={'bytes':p.stat().st_size,'sha256':sha(p)}
 rec={'schema':'lamost-e5-direct-rf-block/1','observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
  'scope':'E5 direct random-forest route: three reps, clean controls, feature noise/missingness/label noise at 5%, 10%, 20%',
  'planned_cells':30,'validated_successful_cells':len(metrics),'paired_corrupted_cells':len(pairs),
  'per_class_metric_rows':len(classes),'per_class_paired_rows':len(cp),'summary_rows':len(sums),'per_class_summary_rows':len(cs),
  'registry_selected_rows':len(rows),'registry_database_was_read_only':True,
  'registry_task_row_sha256':{k:rowsha for k,_,rowsha in rows},
  'evaluation_shas_checked_against_registry_validation':True,'balanced_accuracy_recomputed_from_confusion_matrix':True,
  'clean_selected_params_and_fit_ids_verified_for_corruption_fits':True,'fixed_class_order':CLASSES,
  'calibration_n':10000,'test_n':500000,'bootstrap':False,'significance_tests':False,
  'models_loaded':False,'fits_or_predictions_run':False,'plot_requested':bool(a.plots),
  'analysis_script_sha256':sha(pathlib.Path(__file__)),'input_sha256':{str(p):sha(p) for p in inputs},
  'outputs':outfiles}
 (OUT/'evidence_manifest.json').write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':'success','metrics':len(metrics),'paired':len(pairs),'summaries':len(sums),
  'per_class':len(classes),'per_class_pairs':len(cp),'plots':a.plots,'output':str(OUT)},indent=2))
if __name__=='__main__':main()

