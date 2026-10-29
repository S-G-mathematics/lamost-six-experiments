#!/usr/bin/env python3
"""Terminal-gated descriptive report and ZIP64 delivery finalizer. No model fitting."""
from __future__ import annotations
import argparse,ast,collections,csv,datetime,fcntl,hashlib,io,json,math,os,shutil,signal,subprocess,sys,tempfile,time,uuid,zipfile
from dataclasses import dataclass
from finalization_safety import (PortableBundleError,PortableTestFailure,portable_bundle_snapshot,finalization_fingerprint,begin_finalization_attempt,finish_finalization_attempt,run_portable_test_bundle,portable_receipt_matches,portable_pass_receipt_path,is_resource_backoff,clear_finalization_latch)
from pathlib import Path,PurePosixPath
R=Path(__file__).resolve().parents[1]; ROOT=R.parent; PACKAGES=ROOT/'packages'; REPORTS=R/'reports'
EXPECTED={'3':69,'4':1773,'5':960,'6':21}; CONDITION_FINDINGS_INPUTS=('E4_CONTROL_TREATMENT_PAIRED.csv','E4_CONTROL_TREATMENT_PAIRED_SUMMARY.csv','E5_clean_corrupted_paired_metrics.csv','E5_clean_corrupted_paired_metrics_summary.csv','E5_per_class_paired_differences.csv','E5_per_class_paired_summary.csv','per_repetition_metrics.csv','per_class_metrics.csv','experiment_outcome_coverage.csv','planned_case_ledger.csv','costs.csv','cost_summary.csv','resource_failure_ledger.csv','E4_class_histograms.csv','E5_corruption_realization_summary.csv','label_transition_counts.csv'); OUTCOMES={'successful','scientific_failure','unsupported','unavailable_dependency','user_stopped'}; LABELS=['A','F','G','K','M','GALAXY','QSO']
SKIPDIRS={'.git','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','node_modules','venv','.venv','attempts','logs'}
SENSITIVE=('credential','secret','private_key','private-key','id_rsa','id_ed25519','aws_access','token')
class GatePending(RuntimeError):pass
class EvidenceError(RuntimeError):pass
class InsufficientSpace(RuntimeError):
 def __init__(self,need,free):super().__init__(f'insufficient full-archive space: need {need} bytes, have {free}');self.need=need;self.free=free
@dataclass(frozen=True)
class Entry:
 source:object; member:str; category:str='project'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def stamp():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def atomic_json(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+f'.tmp.{os.getpid()}')
 with t.open('w',encoding='utf-8') as f:json.dump(d,f,indent=2,sort_keys=True,ensure_ascii=False,default=str);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def sha_file(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def _out(t):
 x=t.get('outcome');return x.get('status') or x.get('outcome') if isinstance(x,dict) else x
def verify_terminal(root=ROOT,runtime=R):
 plan=load(runtime/'manifests/tasks.json');freeze=load(runtime/'manifests/freeze.json');reg=load(runtime/'registry.json')
 if freeze.get('plan_sha256')!=sha_file(runtime/'manifests/tasks.json'):raise EvidenceError('tasks.json SHA differs from frozen controller plan')
 ps=plan.get('tasks',[]);rs=reg.get('tasks',[]);pm={t['key']:t for t in ps};rm={t['key']:t for t in rs if isinstance(t,dict) and t.get('key')}
 if len(ps)!=6270 or len(pm)!=6270:raise EvidenceError(f'expected 6,270 unique tasks; found {len(pm)}')
 if set(pm)!=set(rm):raise GatePending(f'registry/plan keys differ ({len(rm)} versus {len(pm)})')
 pending=[];bad=[];counts=collections.defaultdict(collections.Counter);n=collections.Counter()
 for k,t in rm.items():
  o=_out(t)
  if t.get('status')!='validated_terminal':pending.append((k,t.get('status'),o));continue
  if o not in OUTCOMES:bad.append((k,o))
  if t.get('scientific_case'):
   e=str(t.get('experiment'));n[e]+=1;counts[e][str(o)]+=1
   if o=='successful' and t.get('validation_state') not in {'validated','valid','passed','success'}:bad.append((k,'success lacks validation'))
 if pending:raise GatePending(f'{len(pending)} planned tasks not validated terminal; examples={pending[:5]}')
 if bad:raise EvidenceError(f'{len(bad)} task outcomes invalid; examples={bad[:5]}')
 if dict(n)!=EXPECTED:raise EvidenceError(f'scientific plan counts changed: {dict(n)}')
 return {'plan_sha256':plan.get('plan_sha256'),'plan_file_sha256':sha_file(runtime/'manifests/tasks.json'),'total_tasks':len(pm),'scientific_counts':dict(n),'outcomes':{k:dict(v) for k,v in counts.items()},'registry_observed_utc':reg.get('observed_utc')}
def verify_frozen(root=ROOT,runtime=R):
 startup=load(runtime/'manifests/startup_audit.json');master=load(root/'project/benchmark/results/master_run_config.json');src=master.get('benchmark_python_source_sha256',{})
 if len(src)!=19:raise EvidenceError(f'E1 source manifest expected 19 hashes, got {len(src)}')
 bad=[]
 for name,h in src.items():
  p=root/'project/benchmark'/name
  if not p.is_file() or sha_file(p)!=h:bad.append(str(name))
 if bad:raise EvidenceError('frozen E1 source hashes changed: '+', '.join(bad[:5]))
 e1=root/'project/benchmark/results/e1_report_validated_no_bootstrap.json';want=startup.get('documents',{}).get('project/benchmark/results/e1_report_validated_no_bootstrap.json')
 if not e1.is_file() or (want and sha_file(e1)!=want):raise EvidenceError('validated frozen E1 report is missing or changed')
 cc=load(e1).get('cell_counts',{});su=int(cc.get('successful_test_evaluation',0));rf=int(cc.get('resource_failure',0));sf=int(cc.get('supervisor_terminal_failure_without_cell_completion',0));un=int(cc.get('scientific_model_or_support_failure',0))
 if (su,rf+sf,un)!=(674,81,10):raise EvidenceError(f'frozen E1 counts changed: {su}/{rf+sf}/{un}')
 led=root/'e1_wrapup_20261024/E1_frozen_cells_765.csv'
 with led.open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
 lc=collections.Counter(x['classification'] for x in rows);expected={'successful_test_evaluation':674,'resource_failure':55,'supervisor_terminal_failure_without_cell_completion':26,'scientific_model_or_support_failure':10}
 if len(rows)!=765 or dict(lc)!=expected:raise EvidenceError(f'E1 frozen ledger changed: {len(rows)} rows, {dict(lc)}')
 receipt=load(root/'packages/LAMOST_E1_WRAPUP_20261024T080232_571618+0000.receipt.json');arc=Path(receipt['archive'])
 if not arc.is_absolute():arc=root/arc
 if not arc.is_file() or arc.stat().st_size!=int(receipt['archive_bytes']) or sha_file(arc)!=startup.get('e1_archive_sha256') or receipt.get('archive_sha256')!=startup.get('e1_archive_sha256') or receipt.get('zip_crc_passed') is not True:raise EvidenceError('E1 archive size/SHA/CRC receipt validation failed')
 ledger_sha=sha_file(led)
 with zipfile.ZipFile(arc) as z:
  ms=[x.filename for x in z.infolist() if x.filename.endswith('E1_frozen_cells_765.csv')]
  if len(ms)!=1:raise EvidenceError(f'expected one frozen ledger in E1 ZIP, found {len(ms)}')
  h=hashlib.sha256()
  with z.open(ms[0]) as f:
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
  if h.hexdigest()!=ledger_sha:raise EvidenceError('current 765-cell ledger differs from archived E1 copy')
 rec=load(root/'e1_recovery_20261024/recovery_index.json');rc=rec.get('status_counts',{})
 if rc!={'successful_test_evaluation':24,'failed':10,'user_stopped':2,'not_attempted_user_stopped':55} or rec.get('stopped_early_at_user_request') is not True:raise EvidenceError('stopped E1 recovery cutoff changed')
 e2=root/'e2_20261024'; docs=startup.get('documents',{})
 for rel in ('E2_CURRENT_REPORT.md','E2_RECONSTRUCTION_AMENDMENT.md','E2_missing_primary_42.csv','E2_INTEGRITY_AUDIT.json'):
  p=e2/rel;key='e2_20261024/'+rel
  if not p.is_file() or (docs.get(key) and sha_file(p)!=docs[key]):raise EvidenceError('accepted E2 evidence changed: '+rel)
 text=(e2/'E2_CURRENT_REPORT.md').read_text(encoding='utf-8')
 for v in ('108/150','42 primary cells','120/120','4/30','210 are flagged low precision'):
  if v not in text:raise EvidenceError('accepted E2 report claim absent: '+v)
 audit=load(e2/'E2_INTEGRITY_AUDIT.json')
 if audit.get('evaluated_cells')!=228 or audit.get('integrity_errors')!=[] or audit.get('class_valid_low_precision')!=210:raise EvidenceError('E2 integrity audit is inconsistent')
 with (e2/'E2_missing_primary_42.csv').open(newline='',encoding='utf-8') as f:missing=list(csv.DictReader(f))
 if len(missing)!=42:raise EvidenceError(f'E2 missing-primary table has {len(missing)} rows')
 return {'e1_source_hashes_verified':19,'e1_ledger':{'rows':765,'successful':su,'failed':rf+sf,'resource_failures':rf,'supervisor_terminal_started_manifests':sf,'unsupported':un,'sha256':ledger_sha},'e1_archive':{'path':str(arc),'bytes':arc.stat().st_size,'sha256':startup['e1_archive_sha256'],'crc_receipt_passed':True,'ledger_member':ms[0]},'e1_recovery_counts':rc,'e2':{'primary_evaluated':108,'primary_planned':150,'unavailable':42,'classical_evaluated':120,'classical_planned':120,'complete_five_family_strata':4,'total_strata':30,'audit_cells':228,'class_reports':1596,'low_precision':210,'integrity_errors':0,'exact_reconstruction_gates':154,'accuracy_differences':31}}
def csvrows(p):
 p=Path(p)
 if not p.exists():return []
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def write_csv(p,rows):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);fields=list(dict.fromkeys(k for r in rows for k in r)) or ['empty']
 with p.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def pair(a,b,an,bn,base):
 d={'comparison':an+' minus '+bn,**base}
 for m in ('balanced_accuracy','coverage','set_size'):
  try:d['paired_'+m+'_difference_a_minus_b']=float(a[m])-float(b[m]) if a.get(m) not in ('',None) and b.get(m) not in ('',None) else None
  except Exception:d['paired_'+m+'_difference_a_minus_b']=None
 return d
def expanded_pairs(rd):
 rows=csvrows(rd/'planned_case_ledger.csv');by={x.get('key'):x for x in rows};e3=[];e4=[];e5=[];e6=[]
 pc_rows=csvrows(rd/'per_class_metrics.csv');pc={(str(x.get('key')),str(x.get('class_id'))):x for x in pc_rows}
 def get(k):return by.get(k,{})
 def target_pair(a,b,an,bn,base):
  d=pair(a,b,an,bn,base);label=base.get('target_label');ci=LABELS.index(label) if label in LABELS else None
  av=pc.get((str(a.get('key')),str(ci))) if ci is not None else None;bv=pc.get((str(b.get('key')),str(ci))) if ci is not None else None
  for field,source in (('recall','target_class_recall'),('coverage','target_class_coverage')):
   try:va=float(av[field]) if av and av.get(field) not in ('',None) else None
   except (TypeError,ValueError):va=None
   try:vb=float(bv[field]) if bv and bv.get(field) not in ('',None) else None
   except (TypeError,ValueError):vb=None
   d[source+'_a']=va;d[source+'_b']=vb;d['paired_'+source+'_difference_a_minus_b']=va-vb if va is not None and vb is not None else None
  return d
 gens=('gmm','copula','arf','kde','chow_liu'); learners=('logistic','random_forest','hist_gb'); methods=('gaussian_nb','shared_diagonal','lda','qda','gmm','copula','arf','kde','chow_liu','logistic','linear_svm','rbf_svm','knn','cart','random_forest','extra_trees','hist_gb')
 for r in (1,2,3):
  for g in gens:
   d=get(f'e3/rep_{r}/eval/direct/{g}')
   for l in learners:
    real=get(f'e3/rep_{r}/eval/real/{l}');syn=get(f'e3/rep_{r}/eval/synthetic/{l}/{g}');base={'rep':r,'generator':g,'learner':l}
    if d and real:e3.append(pair(d,real,'direct_bayes','real_only',base))
    if syn and real:e3.append(pair(syn,real,'synthetic_only','real_only',base))
    if d and syn:e3.append(pair(d,syn,'direct_bayes','synthetic_only',base))
 for r in (1,2,3):
  for m in methods:
   clean=get(f'e4/rep_{r}/eval/direct/{m}/control')
   for cls in LABELS:
    for tag,ratio in (('half',.5),('tenth',.1)):
     cond=f'{cls}_{tag}'; altered=get(f'e4/rep_{r}/eval/direct/{m}/{cond}')
     if clean and altered:e4.append(target_pair(altered,clean,'altered_direct','unchanged_control',{'rep':r,'method':m,'target_label':cls,'ratio':ratio,'condition':cond}))
  for cls in LABELS:
   for tag,ratio in (('half',.5),('tenth',.1)):
    cond=f'{cls}_{tag}'
    for learner in learners:
     base=get(f'e4/rep_{r}/eval/direct/{learner}/{cond}')
     unchanged=get(f'e4/rep_{r}/eval/direct/{learner}/control')
     for treatment in ('weighted','ros','smote')+tuple('generated_'+g for g in gens):
      treat=get(f'e4/rep_{r}/eval/treatment/{learner}/{cond}_{treatment}')
      if base and treat:e4.append(target_pair(treat,base,treatment,'untreated_altered',{'rep':r,'method':learner,'target_label':cls,'ratio':ratio,'condition':cond,'treatment':treatment}))
      if unchanged and treat:e4.append(target_pair(treat,unchanged,treatment,'unchanged_control',{'rep':r,'method':learner,'target_label':cls,'ratio':ratio,'condition':cond,'treatment':treatment,'control_comparison':'unchanged'}))
 for x in rows:
  if str(x.get('experiment'))!='5' or x.get('mechanism') in (None,'','None','clean'):continue
  clean=[y for y in rows if str(y.get('experiment'))=='5' and y.get('condition')=='clean' and y.get('rep')==x.get('rep') and y.get('method')==x.get('method') and y.get('route')==x.get('route') and y.get('generator')==x.get('generator')]
  for y in clean:e5.append(pair(x,y,'corrupted','clean',{'rep':x.get('rep'),'method':x.get('method'),'route':x.get('route'),'generator':x.get('generator'),'mechanism':x.get('mechanism'),'rate':x.get('rate')}))
 for r in (1,2,3):
  ens_tasks={mode:get(f'e6/rep_{r}/ensemble/{mode}') for mode in ('equal','learned')}
  members={g:get(f'e6/rep_{r}/eval/member/{g}') for g in gens}
  for mode,ens in ens_tasks.items():
   for g,mem in members.items():
    if ens and mem:e6.append(pair(ens,mem,'ensemble_'+mode,'member_'+g,{'rep':r,'mode':mode,'member':g,'comparison_type':'all_members'}))
   best=(ens or {}).get('tuning_best_member')
   if best in members and ens and members[best]:
    e6.append(pair(ens,members[best],'ensemble_'+mode,'tuning_best_member',{'rep':r,'mode':mode,'member':best,'comparison_type':'tuning_best_member','weight_selection_source':'tuning balanced accuracy only'}))
 out={'E3_SHARED_REAL_PAIRED.csv':e3,'E4_CONTROL_TREATMENT_PAIRED.csv':e4,'E5_CLEAN_CORRUPTED_PAIRED.csv':e5,'E6_ENSEMBLE_MEMBER_PAIRED.csv':e6}
 for n,d in out.items():write_csv(rd/n,d)
 return {n:len(v) for n,v in out.items()}
def frozen_e1_e2_figure_records(rd):
 rd=Path(rd)
 specs=[(1,'E1_frozen_all_budget_summary.png',765,674,'Frozen E1: 765 planned; 674 successful'),(2,'E2_primary_availability_and_strata.png',150,108,'E2 primary plotted panel: 108/150; classical 120/120 is separate and not plotted')]
 out=[]
 for e,name,planned,success,note in specs:
  p=rd/'frozen_e1_e2_figures'/name
  if not p.is_file(): continue
  if p.stat().st_size<512 or not p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'): raise EvidenceError('missing/invalid frozen E1/E2 figure '+str(p))
  out.append({'experiment':e,'path':name,'source_path':str(p),'figure_kind':'validated_frozen_E1_E2_figure','planned_unique_case_denominator':planned,'successful_BA_evaluation_denominator':success,'denominator_scope':note,'bytes':p.stat().st_size,'sha256':sha_file(p)})
 return out

def small_report_files(rd):
 rd=Path(rd);exts={'.csv','.png','.html','.svg','.md','.json'};out=[]
 for p in iterfiles(rd):
  rel=p.relative_to(rd)
  if p.suffix.lower() not in exts or p.name=='report.lock': continue
  # Keep current main E1/E2 images, but keep pre-revision engineering PNGs in full archive only.
  if rel.parts and rel.parts[0]=='engineering_audits' and p.suffix.lower()=='.png': continue
  out.append(p)
 return out

def figure_denominators(rd):
 rd=Path(rd)
 _activate_reporting_site_overlay(rd.resolve().parents[1])
 import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 ledger=csvrows(rd/'planned_case_ledger.csv');res=load(rd/'report_result.json') if (rd/'report_result.json').exists() else {};paths=res.get('figure_paths',[]);out=[]
 by_exp={e:[] for e in (3,4,5,6)}
 for item in paths:
  raw=item.get('path') if isinstance(item,dict) else item
  if not raw:continue
  path=Path(raw);name=path.name
  import re
  m=re.match(r'E([3-6])_',name)
  if m:by_exp[int(m.group(1))].append(path)
 for e,title in ((3,'E3 route comparison'),(4,'E4 target restoration'),(5,'E5 fitting-data corruption'),(6,'E6 ensemble comparison')):
  rs=[x for x in ledger if str(x.get('experiment'))==str(e)];ok=sum(x.get('outcome')=='successful' and x.get('balanced_accuracy') not in ('',None) for x in rs);user_stopped=sum(x.get('outcome')=='user_stopped' for x in rs)
  actual=by_exp[e]
  if not actual and ok:
   raise EvidenceError(f'E{e} has {ok} successful evaluations but report_result has no validated figure path')
  if not actual and not ok:
   path=rd/f'E{e}_NO_SUCCESS_PLACEHOLDER.png'
   fig,ax=plt.subplots(figsize=(9,3.5));ax.axis('off');ax.text(.5,.62,f'{title}\nNo validated successful test evaluations',ha='center',va='center',fontsize=14);ax.text(.5,.30,f'Planned unique cases={len(rs)}; successful BA evaluations=0',ha='center',va='center',fontsize=11);fig.tight_layout();fig.savefig(path,dpi=130);plt.close(fig);actual=[path]
  for path in actual:
   if not path.is_absolute():path=(rd/path).resolve()
   if not path.is_file() or path.stat().st_size<512 or not path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):raise EvidenceError('missing/invalid report_result figure '+str(path))
   record={'experiment':e,'path':path.name,'source_path':str(path),'figure_kind':'validated_report_figure' if path.name not in {f'E{i}_NO_SUCCESS_PLACEHOLDER.png' for i in (3,4,5,6)} else 'zero_success_placeholder','planned_unique_case_denominator':len(rs),'successful_BA_evaluation_denominator':ok,'bytes':path.stat().st_size,'sha256':sha_file(path)}
   if any(x.get('outcome')=='user_stopped' for x in ledger):record['user_stopped_scientific_case_denominator']=user_stopped
   out.append(record)
 out.extend(frozen_e1_e2_figure_records(rd))
 write_csv(rd/'figure_denominators.csv',out);return out
def _m(row,name):
 v=row.get(name+'_mean');s=row.get(name+'_sample_sd');n=row.get(name+'_n','0')
 try:return f'{float(v):.4f}'+(f' ± {float(s):.4f}' if s not in ('',None) else '')+f' (n={n})'
 except Exception:return f'— (n={n})'
def _group(row):
 parts=[]
 for k in ('method','condition','route','mode','target_class','ratio','treatment','mechanism','rate','generator'):
  v=row.get(k)
  if v in (None,'','None'):continue
  if k=='target_class':
   try:v=f'{v}:{LABELS[int(float(v))]}'
   except Exception:pass
  parts.append(f'{k}={v}')
 return '; '.join(parts) or '—'
def _summary(rows,e):
 rows=[r for r in rows if str(r.get('experiment'))==str(e)]
 if not rows:return '_No outcome summary is available._'
 amended=bool(rows and 'user_stopped' in rows[0])
 if amended:z=['| Group | successful / planned | BA mean ± SD | coverage mean ± SD | set size mean ± SD | failure | unsupported | unavailable | user stopped | pending/active |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
 else:z=['| Group | successful / planned | BA mean ± SD | coverage mean ± SD | set size mean ± SD | failure | unsupported | unavailable |','|---|---:|---:|---:|---:|---:|---:|---:|']
 for r in rows:
  base=f"| {_group(r)} | {r.get('successful',0)}/{r.get('planned',0)} | {_m(r,'balanced_accuracy')} | {_m(r,'coverage')} | {_m(r,'set_size')} | {r.get('failed_or_interrupted',0)} | {r.get('unsupported',0)} | {r.get('unavailable_dependency',0)} |"
  z.append(base+f" {r.get('user_stopped',0)} | {r.get('pending_or_active',0)} |" if amended else base)
 return '\n'.join(z)
def _paired_numeric_findings(rd):
 def summarize(rows,group_keys,label_fields,extra_metrics=()):
  groups=collections.defaultdict(list)
  for row in rows:
   try:
    if any(row.get(f'paired_{metric}_difference_a_minus_b') not in ('',None) for metric in ('balanced_accuracy','coverage','set_size','target_class_recall','target_class_coverage')):groups[tuple(row.get(k) for k in group_keys)].append(row)
   except Exception:pass
  lines=[]
  for key,rs in sorted(groups.items(),key=lambda kv:tuple('' if x is None else str(x) for x in kv[0])):
   label='; '.join(f'{k}={v}' for k,v in zip(label_fields,key) if v not in (None,'')) or 'all matched pairs';parts=[]
   metric_titles=(('balanced_accuracy','BA'),('coverage','coverage'),('set_size','set size'))+tuple(extra_metrics)
   for metric,title in metric_titles:
    col=f'paired_{metric}_difference_a_minus_b';vals=[]
    for row in rs:
     try:
      v=float(row.get(col));
      if __import__('math').isfinite(v):vals.append(v)
     except (TypeError,ValueError):pass
    if not vals:parts.append(f'{title} Δ unavailable (n=0)');continue
    mu=sum(vals)/len(vals);sd=(sum((x-mu)**2 for x in vals)/(len(vals)-1))**.5 if len(vals)>1 else None
    parts.append(f'{title} Δ {mu:+.4f}'+(f' ± {sd:.4f}' if sd is not None else '')+f' (n={len(vals)})')
   lines.append((label,'; '.join(parts)))
  return lines
 out={}
 out[3]=summarize(csvrows(rd/'E3_SHARED_REAL_PAIRED.csv'),('comparison','generator','learner'),('comparison','generator','learner'))
 e4=csvrows(rd/'E4_CONTROL_TREATMENT_PAIRED.csv');e4a=[r for r in e4 if r.get('comparison','').endswith('minus unchanged_control')];e4b=[r for r in e4 if r.get('comparison','').endswith('minus untreated_altered')]
 e4extra=(('target_class_recall','target recall'),('target_class_coverage','target coverage'))
 e4keys=('comparison','method','target_label','ratio','treatment')
 out['4_control']=summarize(e4a,e4keys,e4keys,e4extra);out['4_treatment']=summarize(e4b,e4keys,e4keys,e4extra)
 out[5]=summarize(csvrows(rd/'E5_CLEAN_CORRUPTED_PAIRED.csv'),('mechanism','rate','method','route','generator'),('mechanism','rate','method','route','generator'))
 out[6]=summarize(csvrows(rd/'E6_ENSEMBLE_MEMBER_PAIRED.csv'),('mode','comparison_type','member'),('mode','comparison_type','member'))
 return out

def _admission_reservation_disclosures(freeze):
    """Describe recorded scheduler estimates, keeping them separate from worker caps."""
    lines=[]
    entries=freeze.get('admission_reservation_history',[])
    if not isinstance(entries,list): return lines
    for item in entries:
        if not isinstance(item,dict) or not isinstance(item.get('scope_conditions'),dict): continue
        scope=item['scope_conditions'];reservation=item.get('new_profile_reservation_gib')
        if reservation is None: continue
        reps=scope.get('repetitions') or [];count=scope.get('condition_count')
        scope_text=item.get('scope') or f"E{scope.get('experiment')} {scope.get('route')} {scope.get('method')} {scope.get('kind')} tasks"
        if count is not None and reps: scope_text+=f" ({count} conditions × {len(reps)} repetitions)"
        if scope.get('never_attempted_only'): scope_text+='; never-attempted matching cells only'
        if scope.get('exact_cohort_train_key_required'): scope_text+='; exact cohort training-key match required'
        text=(f"Additional admission estimate ({item.get('profile_id','unnamed profile')}): {reservation} GiB reservation for {scope_text}. "
              "This is scheduler admission only, not a process-memory cap. ")
        default=item.get('default_heavy_reservation_gib')
        if default is not None: text+=f"Default heavy-task reservation remains {default} GiB outside this scope. "
        if scope.get('never_attempted_only'): text+='Existing attempts retain their recorded reservations. '
        hard=item.get('scientific_hard_limits_unchanged')
        if isinstance(hard,dict):
            limits=[(hard.get('worker_memory_gib'),'GiB worker hard limit'),(hard.get('trial_seconds'),'s tuning-trial limit'),(hard.get('phase_seconds'),'s phase limit'),(hard.get('native_threads'),'native thread(s)')]
            values=[f'{v} {label}' for v,label in limits if v is not None]
            if values: text+='Scientific limits remain '+', '.join(values)+'. '
        text+='Tasks outside the exact scope, including larger cohorts and synthetic or treatment routes, retain existing profiles. '
        if item.get('parent_validation_memory')=='not separately measured; do not infer a bound': text+='Parent-side validation memory was not separately measured; no bound is inferred.'
        lines.append(text.strip())
    return lines

def _et4_execution_disclosure(runtime,freeze):
    """Readable provenance for the separately qualified ET4 fit execution."""
    pointer=freeze.get('et4_execution_policy_sha256')
    if pointer is None:
        return []
    if not isinstance(pointer,str) or len(pointer)!=64 or any(c not in '0123456789abcdef' for c in pointer.lower()):
        raise EvidenceError('ET4 execution policy pointer is malformed')
    path=Path(runtime)/'manifests'/'EXTRA_TREES4_EXECUTION_POLICY_20261029.json'
    if not path.is_file() or path.is_symlink() or sha_file(path)!=pointer:
        raise EvidenceError('ET4 execution policy manifest is missing or differs from frozen SHA')
    policy=load(path)
    scope=policy.get('scope')
    expected_scope={'experiments':[4,5],'kind':'fit','methods':['extra_trees'],'never_attempted':True,'reuse_pipeline':False}
    expected={'schema':'lamost-later-et4-execution-policy/1','status':'qualified','policy_id':'et4-fit_n_jobs4-v1',
              'fit_n_jobs':4,'prediction_n_jobs':1,'native_threads':1,'worker_memory_limit_gib':10,
              'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30}
    if any(policy.get(k)!=v for k,v in expected.items()) or scope!=expected_scope:
        raise EvidenceError('ET4 execution policy is not the reviewed qualified E4/E5 ExtraTrees fit policy')
    return [
      f"ET4 ExtraTrees fit execution amendment: the separately qualified policy {policy['policy_id']} (manifest SHA-256 {pointer}) applies only to newly attempted E4/E5 ExtraTrees fits. It uses four estimator fit jobs, one prediction job, and one native-library thread, with the existing 10 GiB worker hard limit, 600-second tuning-trial and supervised-phase limits, and 30-second termination grace. The frozen search domains, seeds, trial count, and task plan are unchanged. This prospective policy does not imply every planned ExtraTrees fit has completed under it; each attempt's captured profile is authoritative, and older attempts without a snapshot retain their evidenced earlier profile.",
      "The ET4 execution group is a separate feasibility condition from the frozen ET1 controls, which remain unchanged and were not refit under ET4. A fixed-configuration parity check does not establish identical tuning completion or selected parameters under the 600-second trial limit; observed timing differences are not an isolated speed comparison. After the user's explicit removal of the fixed two-worker ceiling, three Random Forest fits were observed concurrently during the adaptive period; this is an observed peak, not a universal cap. See the ET4 execution policy manifest and its qualification/limitations evidence."
    ]

def _resource_failure_disclosure(runtime,report_dir):
    rd=Path(report_dir);runtime=Path(runtime);lines=[]
    freeze_path=runtime/'manifests/freeze.json';freeze=load(freeze_path) if freeze_path.exists() else {}
    history=[x for x in freeze.get('resource_policy_history',[]) if isinstance(x,dict) and isinstance(x.get('policy'),dict)]
    current=freeze.get('resource_policy');effective=freeze.get('resource_policy_effective_from_utc')
    if isinstance(current,dict) and effective and not any(x.get('effective_from_utc')==effective and x.get('policy')==current for x in history):
        history.append({'effective_from_utc':effective,'effective_until_utc':None,'policy':current,'reason':'current prospective policy'})
    def limits(p):
        return {'memory':p.get('worker_memory_limit_gib',p.get('worker_memory_gib')),'trial':p.get('trial_timeout_seconds',p.get('trial_seconds')),'phase':p.get('phase_timeout_seconds',p.get('phase_seconds')),'grace':p.get('termination_grace_seconds'),'threads':p.get('nested_threads',p.get('native_threads')),'chunk':p.get('prediction_chunk_rows')}
    def ceiling(p):
        n=p.get('worker_count_ceiling',p.get('max_workers'))
        if n=='cpu-derived':return f"CPU-derived adaptive admission (reserve {p.get('cpu_reserve_cores','?')} CPU cores)"
        return f"at most {n} concurrent fitting workers" if n is not None else 'worker ceiling not recorded'
    if history:
        lines.append('Resource-policy history: task/attempt snapshots take precedence; older attempts without snapshots are mapped from their evidenced start timestamps. Planned and waiting tasks use the prospective current policy. This distinguishes the initial fixed-worker period from the later user-authorized adaptive CPU/RAM admission period; policy ceilings are not observed simultaneous-worker counts.')
        for h in sorted(history,key=lambda x:str(x.get('effective_from_utc',''))):
            p=h['policy'];lo=h.get('effective_from_utc','start unknown');hi=h.get('effective_until_utc') or 'current/open';lim=limits(p)
            desc=(f"{lo} to {hi}: {ceiling(p)}; per-worker process-tree cap {lim['memory']} GiB; tuning trial {lim['trial']} s; supervised phase {lim['phase']} s; termination grace {lim['grace']} s; nested threads {lim['threads']}; prediction chunk {lim['chunk']:,} rows")
            if p.get('worker_admission_reservation_gib_by_class'):
                desc+=f"; scheduler admission reservations {p['worker_admission_reservation_gib_by_class']} GiB by class"
            if p.get('host_os_harbor_reserve_gib') is not None:
                desc+=f"; retain {p['host_os_harbor_reserve_gib']} GiB for host/Harbor"
            if p.get('admission_pause_below_gib') is not None:
                desc+=f"; pause new admissions below {p['admission_pause_below_gib']} GiB available RAM"
            if p.get('commitment_growth_margin_gib') is not None:
                desc+=f"; commitment-growth guard {p['commitment_growth_margin_gib']} GiB"
            if p.get('reclaim_condition') is not None:
                reclaim=p['reclaim_condition']
                if not isinstance(reclaim,str):reclaim=json.dumps(reclaim,sort_keys=True,separators=(',',':'))
                desc+=f"; reclaim condition: {reclaim}"
            if h.get('reason'):desc+=f"; recorded reason: {h['reason']}"
            lines.append('- '+desc+'.')
        norm=[limits(h['policy']) for h in history]
        fixed_keys=('memory','trial','phase','grace','threads','chunk')
        if norm and all(all(x.get(k)==norm[0].get(k) for k in fixed_keys) for x in norm[1:]):
            q=norm[0];lines.append(f"Across these periods, the per-worker {q['memory']} GiB limit, {q['trial']} s tuning-trial timeout, {q['phase']} s phase timeout, {q['grace']} s termination grace, {q['threads']} nested thread, and {q['chunk']:,}-row prediction chunk stayed unchanged. The adaptive scheduler's memory reservations govern admission estimates and do not raise the per-worker process-tree limit.")
    else:
        policies=[]
        for e in (3,4,5,6):
            p=runtime/'manifests'/f'E{e}_MANIFEST.json'
            try:policies.append((e,load(p).get('resource_policy',{})))
            except Exception:policies.append((e,{}))
        unique={json.dumps(x,sort_keys=True) for _,x in policies if x}
        if len(unique)==1 and policies and all(x for _,x in policies):
            policy=json.loads(next(iter(unique)))
            policy_text=(f"Recorded E3–E6 resource policy: {ceiling(policy)}, "
                         f"{policy.get('worker_memory_limit_gib',policy.get('worker_memory_gib'))} GiB per worker, "
                         f"{policy.get('trial_timeout_seconds',policy.get('trial_seconds'))} s per tuning trial, "
                         f"{policy.get('phase_timeout_seconds',policy.get('phase_seconds'))} s per supervised phase, and "
                         f"{policy.get('termination_grace_seconds')} s termination grace.")
        else:policy_text='Resource limits are recorded separately in each E3–E6 manifest; a single policy history is not available.'
        lines.append(policy_text)
    lines.extend(_admission_reservation_disclosures(freeze))
    lines.extend(_et4_execution_disclosure(runtime,freeze))
    rows=csvrows(rd/'resource_failure_summary.csv');lines.append('Failure evidence is classified only from saved explicit reasons/phase receipts. A timeout remains a timeout unless the receipt explicitly records a memory/RSS limit. Trial events are kept separate from terminal cell failures; a failed trial is not counted as a failed fit cell when the final fit succeeded. See `resource_failure_ledger.csv`, `resource_failure_summary.csv`, and phase timing/RSS records in `costs.csv`.')
    lines.append('Observed costs are hardware- and load-dependent. Compare resource outcomes with the per-task/per-attempt policy profile and period. Outcomes from the adaptive period are not directly comparable in feasibility to the initial fixed two-worker period unless this difference is stated.')
    cutoff_rows=csvrows(rd/'terminal_trial_cutoffs.csv')
    for c in cutoff_rows:
        if c.get('task_key')=='e3/rep_2/fit/synthetic/random_forest/gmm':
            lines.append(f"Terminal tuning cutoff: downstream Random Forest on GMM synthetic examples in E3 rep 2 failed at the recorded {c.get('peak_tree_rss_bytes')} byte process-tree RSS peak under the 10 GiB worker policy. Trials 0-7 are retained with their saved outcomes; trial 8 was terminated before scoring (last state RUNNING), trial 9 was only an unattempted nominal budget slot with no Optuna trial number. The final fit did not start and no pipeline was published. Source history/request/state file hashes before and after reporting are recorded unchanged in terminal_trial_cutoffs.csv/json. This is not a GMM generator failure, and no OS-level OOM is inferred. See terminal_trial_cutoffs.csv/json and model_selection_ledger.csv.")
    incident_path=runtime/'manifests/incidents/serialization_validation_20261025/incident.json'
    incident=load(incident_path) if incident_path.exists() else None
    if incident and incident.get('classification')=='operationally_invalid_post_save_validation_memory_duplication':
        lines.append(f"Operational incident overlay: {incident.get('task_key')} had a post-save validation RSS termination at {incident.get('invalid_validation_peak_rss_kib')} KiB after model serialization; the single-copy validation of the same pipeline passed at {incident.get('single_copy_validation_peak_rss_kib')} KiB in {incident.get('single_copy_validation_seconds')} seconds. No model was refit. The original phase and cost remain in the ledgers as operationally invalid and are excluded from scientific resource-feasibility counts.")
    if not rows:lines.append('No supported failure events are present in the saved ledger.')
    else:
        lines += ['', '| Experiment | Evidence type | Event scope | Events | Unique tasks | Terminal cell-failure tasks | Successful fit tasks with failed trials |','|---|---|---|---:|---:|---:|---:|']
        for r in rows:lines.append(f"| E{r.get('experiment')} | {r.get('failure_evidence_type')} | {r.get('event_scope')} | {r.get('failure_event_count')} | {r.get('unique_task_count')} | {r.get('terminal_cell_failure_task_count')} | {r.get('successful_fit_tasks_with_failed_trial_count')} |")
    return lines

SCOPE_AMENDMENT_REL='manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json'
SCOPE_APPLICATION_REL='reports/SINGLE_EVAL_SCOPE_APPLICATION_20261029.json'
SCOPE_AMENDMENT_SCHEMA='lamost-user-single-evaluation-scope-amendment/1'
SCOPE_APPLICATION_SCHEMA='lamost-user-scope-amendment-application/1'
_SCOPE_COUNTS={'selected_pending_scientific':45,'user_stopped_scientific':168,'selected_pending_tasks':90,'user_stopped_tasks':334}
_SCOPE_BY_EXPERIMENT={'4':(14,67),'5':(31,101)}
_REPORT_GROUP_FIELDS=('experiment','method','condition','route','mode','target_class','ratio','treatment','mechanism','rate','generator')
def _scope_value(value):return '' if value is None or value=='' else str(value)
def _scope_key(task,axes):
 return tuple(_scope_value(task.get(k)) for k in axes)
def _scope_amendment_info(runtime,terminal,ledger=None):
 runtime=Path(runtime);ap=runtime/SCOPE_AMENDMENT_REL;pp=runtime/SCOPE_APPLICATION_REL
 if not ap.exists() and not pp.exists():return None
 if not ap.is_file() or not pp.is_file():raise EvidenceError('user scope amendment/application pair is incomplete')
 amendment=load(ap);application=load(pp);amendment_sha=sha_file(ap)
 if amendment.get('schema')!=SCOPE_AMENDMENT_SCHEMA or application.get('schema')!=SCOPE_APPLICATION_SCHEMA or application.get('status')!='applied_and_verified':
  raise EvidenceError('user scope amendment or application schema/status is not verified')
 if amendment.get('original_plan_sha256')!=terminal.get('plan_sha256') or application.get('original_plan_sha256')!=terminal.get('plan_sha256'):
  raise EvidenceError('user scope amendment is not bound to the original frozen plan')
 if amendment.get('original_task_count')!=6270 or amendment.get('original_scientific_count')!=2823:
  raise EvidenceError('user scope amendment changed the original planned denominators')
 if amendment.get('no_metric_values_read') is not True or amendment.get('preserves_all_prior_outcomes') is not True:
  raise EvidenceError('user scope amendment lacks score-blind selection or prior-outcome preservation proof')
 selected=amendment.get('selected_evaluation_keys');stopped=amendment.get('user_stopped_scientific_keys')
 closure=amendment.get('selected_dependency_closure');pending_closure=amendment.get('selected_pending_dependency_closure_keys')
 excluded=amendment.get('excluded_nonterminal_task_keys')
 if not isinstance(selected,list) or len(selected)!=45 or len(set(selected))!=45 or not isinstance(stopped,list) or len(stopped)!=168 or len(set(stopped))!=168:
  raise EvidenceError('user scope amendment selected/stopped scientific key counts differ')
 if (not isinstance(closure,list) or len(set(closure))!=len(closure)
     or not isinstance(pending_closure,list) or len(pending_closure)!=90 or len(set(pending_closure))!=90
     or amendment.get('pending_dependency_closure_count')!=90
     or not isinstance(excluded,list) or len(excluded)!=334 or len(set(excluded))!=334
     or amendment.get('excluded_nonterminal_task_count')!=334
     or amendment.get('user_stopped_scientific_count')!=168):
  raise EvidenceError('user scope amendment dependency/stopped task closure counts differ')
 if set(selected)&set(stopped):raise EvidenceError('user scope amendment selects and stops the same case')
 if not set(selected).issubset(pending_closure) or not set(pending_closure).issubset(closure):
  raise EvidenceError('selected evaluations are not in the pending dependency closure')
 if set(closure)&set(excluded) or not set(stopped).issubset(excluded):
  raise EvidenceError('pending dependency closure and excluded nonterminal keys overlap or omit stopped cases')
 plan=load(runtime/'manifests/tasks.json');tasks=plan.get('tasks',[]);taskmap={x.get('key'):x for x in tasks if isinstance(x,dict)}
 referenced=selected+stopped+closure+pending_closure+excluded
 if len(taskmap)!=6270 or any(k not in taskmap for k in referenced):raise EvidenceError('user scope amendment references a missing task-plan key')
 selected_tasks=[taskmap[k] for k in selected]
 if any(not t.get('scientific_case') or str(t.get('experiment')) not in {'4','5'} or '/eval/' not in str(t.get('key','')) for t in selected_tasks):
  raise EvidenceError('user scope amendment selected a non-E4/E5 scientific evaluation')
 axes=amendment.get('group_axes',amendment.get('axes'))
 if not isinstance(axes,list) or not {'experiment','method','condition','route'}.issubset(set(axes)) or 'rep' in axes:
  raise EvidenceError('scope amendment group axes are missing or include repetition')
 if len({_scope_key(t,axes) for t in selected_tasks})!=45:raise EvidenceError('selected evaluations do not represent 45 unique amended groups')
 if not set(selected+stopped).issubset(set(closure+excluded)):
  raise EvidenceError('user scope amendment task closure omits selected or stopped evaluation keys')
 if application.get('amendment_sha256')!=amendment_sha:
  raise EvidenceError('scope application receipt does not bind the amendment bytes')
 declared_path=application.get('amendment_path')
 allowed_paths={SCOPE_AMENDMENT_REL,'runtime_20261025/'+SCOPE_AMENDMENT_REL,str(ap)}
 path_ok=declared_path in allowed_paths
 if not path_ok and isinstance(declared_path,str):
  try:path_ok=Path(declared_path).is_absolute() and Path(declared_path).resolve()==ap.resolve()
  except OSError:path_ok=False
 if not path_ok:raise EvidenceError('scope application receipt names an unexpected amendment path')
 if any(application.get(k) is not True for k in ('original_plan_unchanged','existing_terminal_unchanged','only_closure_pending_proof')):
  raise EvidenceError('scope application receipt does not prove unchanged prior plan/results and dependency closure')
 if application.get('counts')!=_SCOPE_COUNTS:raise EvidenceError('scope application counts differ from the approved 45/168/90/334 cut')
 byexp=application.get('by_experiment',{})
 for e,(sel,stop) in _SCOPE_BY_EXPERIMENT.items():
  row=byexp.get(e,{})
  if row.get('selected_pending_scientific')!=sel or row.get('user_stopped_scientific')!=stop:
   raise EvidenceError('scope application per-experiment scientific counts differ')
 amend_byexp=amendment.get('counts_by_experiment',{})
 for e,(sel,stop) in _SCOPE_BY_EXPERIMENT.items():
  ar=amend_byexp.get(e,{})
  if ar.get('selected_pending_scientific')!=sel or ar.get('user_stopped_scientific')!=stop:
   raise EvidenceError('amendment and application per-experiment scientific counts differ')
 out={'amendment_path':runtime.name+'/'+SCOPE_AMENDMENT_REL,'amendment_sha256':amendment_sha,
      'application_path':runtime.name+'/'+SCOPE_APPLICATION_REL,'application_sha256':sha_file(pp),
      'selected_count':len(selected),'stopped_count':len(stopped),'selected_by_experiment':{e:v[0] for e,v in _SCOPE_BY_EXPERIMENT.items()},
      'stopped_by_experiment':{e:v[1] for e,v in _SCOPE_BY_EXPERIMENT.items()},
      'counts':dict(_SCOPE_COUNTS),'selected_outcomes':{}}
 if ledger is not None:
  bykey={str(r.get('key')):r for r in ledger}
  if len(bykey)!=2823 or any(k not in bykey for k in selected+stopped):raise EvidenceError('final scientific ledger does not cover amended selected/stopped cases')
  if any(bykey[k].get('outcome')!='user_stopped' for k in stopped):raise EvidenceError('a scope-excluded repeated case is not recorded user_stopped')
  extra=[str(r.get('key')) for r in ledger if r.get('outcome')=='user_stopped' and str(r.get('key')) not in set(stopped)]
  if extra:raise EvidenceError('ledger contains user_stopped cases outside the amendment')
  valid_selected={'successful','scientific_failure','unsupported','unavailable_dependency'}
  if any(bykey[k].get('outcome') not in valid_selected for k in selected):raise EvidenceError('selected single-evaluation cases do not have an allowed terminal outcome')
  counts=collections.Counter(str(bykey[k].get('outcome')) for k in selected)
  out['selected_outcomes']={k:counts.get(k,0) for k in ('successful','scientific_failure','unsupported','unavailable_dependency')}
  if sum(out['selected_outcomes'].values())!=45:raise EvidenceError('selected outcome accounting does not cover all 45 amended cases')
  stopped_by_exp=collections.Counter(str(bykey[k].get('experiment')) for k in stopped)
  if dict(stopped_by_exp)!={'4':67,'5':101}:raise EvidenceError('ledger user-stopped counts differ from applied amendment')
 return out

def _scope_group_tuple(row):return tuple(_scope_value(row.get(k)) for k in _REPORT_GROUP_FIELDS)
def _split_user_stopped_coverage(runtime,terminal):
 runtime=Path(runtime);rd=runtime/'reports';ledger=csvrows(rd/'planned_case_ledger.csv')
 scope=_scope_amendment_info(runtime,terminal,ledger)
 if scope is None:
  if any(r.get('outcome')=='user_stopped' for r in ledger):raise EvidenceError('user_stopped outcomes require the applied scope amendment receipt')
  if terminal.get('outcomes') and any(c.get('user_stopped',0) for c in terminal['outcomes'].values()):raise EvidenceError('terminal user_stopped outcomes require the applied scope amendment receipt')
  return None
 counts=collections.Counter(_scope_group_tuple(r) for r in ledger if r.get('outcome')=='user_stopped')
 summary=csvrows(rd/'experiment_outcome_coverage.csv')
 if not summary:raise EvidenceError('outcome coverage is empty for amended-scope report')
 if 'user_stopped' in summary[0]:
  for row in summary:
   expected=counts.get(_scope_group_tuple(row),0)
   if int(row.get('user_stopped') or 0)!=expected:raise EvidenceError('user-stopped outcome coverage was already written with different counts')
 else:
  for row in summary:
   stopped=counts.get(_scope_group_tuple(row),0);pending=int(row.get('pending_or_active') or 0)
   if pending<stopped:raise EvidenceError('pending/active count is below actual user-stopped count')
   row['user_stopped']=stopped;row['pending_or_active']=pending-stopped
  write_csv(rd/'experiment_outcome_coverage.csv',summary)
 return scope

def _availability_line(summary,e):
 rs=[r for r in summary if str(r.get('experiment'))==str(e)]
 total=lambda key:sum(int(r.get(key) or 0) for r in rs)
 planned=total('planned');success=total('successful');failed=total('failed_or_interrupted');unsupported=total('unsupported');unavailable=total('unavailable_dependency');pending=total('pending_or_active')
 if any('user_stopped' in r for r in rs):pending_text=f"{total('user_stopped')} user-stopped; {pending} pending/active"
 else:pending_text=f"{pending} pending/active"
 return f'Availability: {success}/{planned} successful; {failed} failed or interrupted; {unsupported} unsupported; {unavailable} unavailable by dependency; {pending_text}. Paired estimates include only successful matched cases.'

def _finding_lines(items):
 if not items:return ['No matched pair with both valid scores is currently available.']
 return [f'- {label}: paired differences: {value}.' for label,value in items]

def _e6_reporting_text(ledger):
 rows=[r for r in ledger if str(r.get('experiment'))=='6']
 members=[r for r in rows if r.get('condition')=='member_reference' or r.get('route')=='member_reference']
 ensembles=[r for r in rows if r.get('route')=='posterior_ensemble' or r.get('mode') in {'equal','learned'}]
 success=lambda r:r.get('outcome')=='successful' and r.get('balanced_accuracy') not in ('',None)
 member_success=sum(success(r) for r in members); ensemble_success=sum(success(r) for r in ensembles)
 unavailable=sum(r.get('outcome')=='unavailable_dependency' for r in ensembles)
 prefix=(f"Ledger accounting: {member_success}/{len(members)} member-reference evaluations have scores; "
         f"{ensemble_success}/{len(ensembles)} primary ensemble cases have scores; {unavailable}/{len(ensembles)} primary ensemble cases are unavailable dependencies.")
 if ensembles and ensemble_success==0 and unavailable==len(ensembles):
  return prefix+" The all-five-member preflight gate left every primary ensemble unavailable before posterior generation or weight search. No tuning-best-member selection, frozen ensemble weights, candidate results, or ensemble test metrics were produced. Member-reference scores alias E3 direct evaluations and are not E6 ensemble results."
 if ensemble_success:
  selected=sum(bool(str(r.get('tuning_best_member') or '').strip()) for r in ensembles if success(r))
  suffix=(f" A tuning-best member is recorded for {selected} successful ensemble cells; selection is based on tuning data only, never test accuracy." if selected else " No tuning-best-member selection is recorded in the successful ensemble rows.")
  return prefix+suffix+" Interpret only saved, validated weights and candidate ledgers as executed search evidence."
 return prefix+" No successful ensemble metric is available; report only the terminal reasons and any explicitly saved tuning/weight artifacts."

def _e3_cost_detail_note(runtime):
 p=Path(runtime)/'reports'/'E3_FINAL_DESCRIPTIVE_REPORT.md'
 if not p.is_file(): return None
 return ('E3 timing and tuning-history details are in `E3_FINAL_DESCRIPTIVE_REPORT.md`. That report separates measured phase costs, exact completed-trial history, partial histories, duplicate cached budget slots, and last-observed active trial time; its tuning subtotal is explicitly a lower bound where trials were cut off. Missing durations remain blank, and timing remains hardware/load dependent.')

def _e3_rep1_publication_disclosure(runtime):
    p=Path(runtime)/'reports'/'E3_RF_REP1_PUBLICATION_LIMITATION.md'
    if not p.is_file():
        raise EvidenceError('E3 RF rep1 publication provenance note is missing')
    note=p.read_text(encoding='utf-8')
    required=('has no fit_publication.json',
              'does not by itself invalidate the recorded successful E3 evaluation',
              'No receipt has been reconstructed')
    if not all(token in note for token in required):
        raise EvidenceError('E3 RF rep1 publication provenance note lacks required evidence')
    return ('E3 real-only Random Forest repetition 1 has no fit_publication.json. '
            'The saved note records the selected pipeline, configuration, fit result, '
            'and validation record as present and hash-consistent; the recorded successful '
            'E3 evaluation and its metrics remain in the E3 ledger. The missing publication '
            'receipt is an artifact-provenance limitation and no receipt was reconstructed. '
            'See E3_RF_REP1_PUBLICATION_LIMITATION.md.')

def _insert_e3_rep1_publication_disclosure(lines,runtime):
    disclosure=_e3_rep1_publication_disclosure(runtime)
    e4_index=next((i for i,line in enumerate(lines)
                   if isinstance(line,str) and line.startswith('## Experiment 4')),None)
    if e4_index is None:
        raise EvidenceError('cannot place E3 RF publication disclosure before E4')
    lines[e4_index:e4_index]=['',disclosure,'']
    return lines

def _single_eval_scope_report_lines(scope):
 lines=['## User-directed amended repetition scope','',
  'The frozen design specified three repetitions per condition. After observing earlier outcomes, the user directed one evaluation per unique method/condition group and no further repetition of already-covered groups. The amendment selected one E4/E5 evaluation for each of 45 uncovered groups without reading scores; all prior terminal outcomes were preserved. The original 6,270-task DAG and 2,823 scientific-case denominator remain unchanged.',
  f"The applied amendment stopped {scope['counts']['user_stopped_tasks']} unstarted task records outside the selected closure, including {scope['stopped_count']} scientific evaluation cases marked `user_stopped` (E4: {scope['stopped_by_experiment']['4']}; E5: {scope['stopped_by_experiment']['5']}). These administrative stops are distinct from scientific failures and unavailable dependencies. The amendment retains 90 pending selected-closure tasks (45 evaluations and 45 pending fit dependencies) within a 167-key full dependency closure that also includes completed supporting dependencies.",
  f"The 45 selected cases reached terminal outcomes as follows: {scope['selected_outcomes'].get('successful',0)} successful, {scope['selected_outcomes'].get('scientific_failure',0)} scientific failures, {scope['selected_outcomes'].get('unsupported',0)} unsupported, and {scope['selected_outcomes'].get('unavailable_dependency',0)} unavailable by dependency. The three-repetition grid was not fully executed; newly selected groups contribute one evaluation each and do not establish replication-based uncertainty. Paired summaries include only actual matched successful repetitions; no bootstrap is used.",'',
  '| Experiment | Rep | Successful | Scientific failure | Unsupported | Unavailable dependency | User stopped |','|---|---:|---:|---:|---:|---:|---:|']
 return lines

def _repetition_outcome_rows(ledger):
 counts=collections.Counter((str(r.get('experiment')),str(r.get('rep')),str(r.get('outcome'))) for r in ledger)
 rows=[]
 for e in ('3','4','5','6'):
  reps=sorted({r.get('rep') for r in ledger if str(r.get('experiment'))==e},key=lambda x:int(x) if str(x).isdigit() else 999)
  for rep in reps:
   rows.append((e,str(rep),*[counts[(e,str(rep),state)] for state in ('successful','scientific_failure','unsupported','unavailable_dependency','user_stopped')]))
 return rows

def make_final_report(root,runtime,terminal,evidence):
 rd=runtime/'reports';summary=csvrows(rd/'experiment_outcome_coverage.csv');per=csvrows(rd/'per_repetition_metrics.csv');ledger=csvrows(rd/'planned_case_ledger.csv');pairs=expanded_pairs(rd);figs=figure_denominators(rd);findings=_paired_numeric_findings(rd);resource_disclosure=_resource_failure_disclosure(runtime,rd)
 e1=(root/'e1_wrapup_20261024/E1_WRAPUP.md').read_text();e2=(root/'e2_20261024/E2_CURRENT_REPORT.md').read_text();am=(root/'e2_20261024/E2_RECONSTRUCTION_AMENDMENT.md').read_text();p=load(runtime/'manifests/tasks.json');freeze=load(runtime/'manifests/freeze.json')
 lines=['# LAMOST DR10 v2 — final six-experiment report','',f'Generated UTC: {now()}',f"Plan SHA-256: `{p['plan_sha256']}`; frozen task file SHA-256: `{terminal['plan_file_sha256']}`; execution protocol: {freeze.get('protocol_version')}.",'', '## Data and information history','', 'The study uses the frozen cleaned LAMOST DR10 v2 baseline, six predictors (Pan-STARRS g, r, i, z, y; Gaia G), seven labels (A, F, G, K, M, GALAXY, QSO), saved source identities/roles, and a fixed 500,000-row test cohort. IDs, labels, spectral information, and audit metadata are not predictors. E1/E2 test outcomes were observed before E3–E6; later tests are not prospective untouched-test evaluations. E3–E6 plans were frozen before their new test evaluations; fitting, tuning, calibration, and test roles stayed separated.', '', 'Bootstrap was dropped. Results are descriptive, repetition matched, and report individual observations, actual successful denominators, means, sample standard deviations, and paired differences. No significance claims are made. Failures and unavailable cells remain in the ledger and are never given fabricated scores.', '', '## Terminal outcome coverage','', '| Experiment | Planned | Successful | Scientific failure | Unsupported | Unavailable dependency | Other terminal |','|---|---:|---:|---:|---:|---:|---:|']
 scope=_scope_amendment_info(runtime,terminal,ledger)
 if scope is not None:
  idx=lines.index('## Terminal outcome coverage')
  lines[idx:idx]=_single_eval_scope_report_lines(scope)+[f'| E{e} | {rep} | {su} | {fail} | {unsup} | {unavail} | {stopped} |' for e,rep,su,fail,unsup,unavail,stopped in _repetition_outcome_rows(ledger)]+['']
  h=lines.index('| Experiment | Planned | Successful | Scientific failure | Unsupported | Unavailable dependency | Other terminal |')
  lines[h]='| Experiment | Planned | Successful | Scientific failure | Unsupported | Unavailable dependency | User stopped | Other terminal |'
  lines[h+1]='|---|---:|---:|---:|---:|---:|---:|---:|'
 for e in ('3','4','5','6'):
  c=terminal['outcomes'].get(e,{})
  if scope is not None:
   other=sum(v for k,v in c.items() if k not in {'successful','scientific_failure','unsupported','unavailable_dependency','user_stopped'});lines.append(f"| E{e} | {EXPECTED[e]} | {c.get('successful',0)} | {c.get('scientific_failure',0)} | {c.get('unsupported',0)} | {c.get('unavailable_dependency',0)} | {c.get('user_stopped',0)} | {other} |")
  else:
   other=sum(v for k,v in c.items() if k not in {'successful','scientific_failure','unsupported','unavailable_dependency'});lines.append(f"| E{e} | {EXPECTED[e]} | {c.get('successful',0)} | {c.get('scientific_failure',0)} | {c.get('unsupported',0)} | {c.get('unavailable_dependency',0)} | {other} |")
 lines += ['',f"All {len(ledger)} unique scientific outcomes are in `planned_case_ledger.csv`; successful repetition rows are in `per_repetition_metrics.csv`; all 6,270 planned DAG tasks and their terminal states are in `all_task_ledger.csv`.",'', '## Shared conformal evaluation\n\nEach evaluated route uses its recorded score type and calibration nonconformity. Probability routes use 1 - p_true; linear and RBF SVM routes use the negative native class margin. The conformal threshold is the finite-sample k = ceil((n_cal + 1) * 0.90) order statistic of calibration nonconformities (threshold +infinity if k exceeds n_cal), with a candidate class included when its nonconformity is at most that threshold. Predictions use the route’s fixed class-order argmax rule. Probability and margin thresholds are on different scales and are not comparable across methods; achieved coverage and set size are the comparable test summaries. A nominal 90% target does not imply 90% coverage for every class. E3 downstream learners and native generative routes retain their probability score rules.\n\n## Experiment 1 — frozen benchmark','', 'Question: compare the frozen classifier/model families and training budgets on balanced accuracy, conformal coverage/set size, and resource feasibility. Frozen outcomes remain 765/765 terminal: 674 successful, 81 failed (55 resource failures and 26 supervisor-terminal cells whose manifests remained started), and 10 unsupported. The complete 765-cell ledger, method-by-budget summary, learning curve, and validated report remain unchanged. Recovery is a separate supplement stopped early at user request; its outcomes are not substituted into frozen E1.', '', e1.strip(), '', 'The seven auxiliary tuning-history discrepancies, omitted historical fitted models/per-test-row predictions, conditional-on-success summaries, and hardware-dependent timing limitations remain disclosed. The staged ARF min-leaf variant was not run; saved-pipeline finalization did not pass its reproduction gate.', '', '## Experiment 2 — generator fidelity versus direct classification','', 'Question: whether class-conditional statistical fidelity diagnostics track direct classification performance. SDMetrics Quality Reports use six predictors, matched diagnostic sample sizes, and equal averaging across seven classes; Spearman comparisons are within budget/repetition, not pooled across budgets.', '', e2.strip(), '', '### E2 reconstruction amendment','', am.strip(), '', '## Experiment 3 — direct Bayes, synthetic-only, and real-only learning','', 'Question: for the same estimated class-conditional generator, compare direct Bayes prediction, a downstream learner trained only on synthetic rows, and that learner trained on real fitting rows.', '', 'Design/defaults: GMM, Gaussian copula, ARF/FORDE, KDE, and continuous Chow–Liu; 100,000-row development cohort; three repetitions; 80k/10k/10k fit/tune/calibration roles; 500k fixed test cohort. Logistic regression, random forest, and histogram gradient boosting are downstream learners. Each generator creates 400,000 fitting examples using deterministic largest-remainder allocation from the fitting-role class histogram. E3-owned missing generator fits tune only on tuning roles; validated E2 reconstructed GMM/copula/Chow–Liu pipelines retain reconstructed provenance and their own measured classification results. Real-only fits are shared across generators within each learner/repetition; synthetic and real routes each use ten trials.', '', 'Planned outcomes: 69 unique (15 direct, 45 synthetic-only, 9 shared real-only).', '', '### E3 outcome summary','', _summary(summary,3),_availability_line(summary,3),'', 'Expanded shared-real matched comparisons are in `E3_SHARED_REAL_PAIRED.csv` (rows: '+str(pairs['E3_SHARED_REAL_PAIRED.csv'])+'). They compare direct, synthetic-only, and real-only scores at each generator/repetition/learner without duplicating the real-only fit. Condition-specific paired results grouped by comparison, generator, and downstream learner; each n is matched successful repetitions (balanced-accuracy difference, A minus B):', '', *_finding_lines(findings[3]), '', _e3_cost_detail_note(runtime) or '', '', '## Experiment 4 — class imbalance and restoration','', 'Question: how halving or reducing one class’s fitting share to one tenth affects classification and conformal prediction, and how weighting, random oversampling, SMOTE, and generated restoration compare. The design has one unchanged control and 14 altered conditions (seven target classes × two severities) in each of three paired repetitions. Tune/calibration identities are reserved before altered cohorts; test cohorts keep the population distribution.', '', 'Seventeen direct methods are evaluated per condition. Logistic regression, random forest, and histogram gradient boosting additionally compare weighting, ROS, SMOTE, and restoration from five generators. Restoration returns target support to the original class share. All addition treatments have the same final histogram; generators see only the altered fitting cohort. SMOTE uses `min(5,n_target−1)` and is unsupported below two target rows. Each treatment is tuned separately on the same frozen tuning role with ten trials per learner. These treatment fits are separate from the untreated direct fit.', '', 'Planned outcomes: 1,773 unique test outcomes (765 direct and 1,008 treatment). Forty-two altered-cohort nodes, 126 shared base-treatment data nodes, and 210 generated append nodes are non-evaluation dependencies.', '', '### E4 outcome summary','', _summary(summary,4),_availability_line(summary,4),'', 'Paired altered-versus-unchanged-control, treatment-versus-untreated-altered, and treatment-versus-unchanged-control differences are in `E4_CONTROL_TREATMENT_PAIRED.csv` (rows: '+str(pairs['E4_CONTROL_TREATMENT_PAIRED.csv'])+'). Claims remain specific to target class, severity, method, and repetition. Condition-specific paired means and sample SDs are grouped by comparison, method, target class, severity ratio, and treatment; each n is matched successful repetitions. No pooling across targets or severities is used.', '', *_finding_lines(findings['4_control']+findings['4_treatment']), '', '## Experiment 5 — fitting-data corruption','', 'Question: whether direct and synthetic-data pipelines suppress, preserve, or amplify controlled corruption of fitting rows. The clean control is paired with feature noise, missingness, and label noise at 5%, 10%, and 20% for three repetitions. Only fitting data are corrupted; tuning, calibration, and test stay clean. Masks are nested across rates and shared across methods. No missingness indicator is added. Feature-noise scale is fitting-data IQR/1.349 with specified fallbacks; label changes are forced and logged.', '', 'Seventeen direct methods and fifteen generator/downstream routes are compared. Clean-selected configurations and matching seeds are carried to corrupted refits without retuning; synthetic-only routes keep the five-times-fitting sample count. These controlled mechanisms do not represent every astronomical measurement error.', '', 'Planned outcomes: 960 (510 direct and 450 synthetic-only). Exact perturbations, changed cells, missing cells, and label-transition records are preserved.', '', '### E5 outcome summary','', _summary(summary,5),_availability_line(summary,5),'', 'Matched corrupted-minus-clean values are in `E5_CLEAN_CORRUPTED_PAIRED.csv` (rows: '+str(pairs['E5_CLEAN_CORRUPTED_PAIRED.csv'])+'). Failed methods remain in the coverage denominator. Condition-specific paired means and sample SDs grouped by corruption mechanism, rate, method, route, and generator; each n is matched successful repetitions:', '', *_finding_lines(findings[5]), '', '## Experiment 6 — generative posterior ensembles','', 'Planned question: whether five-generator posterior ensembles improve classification or conformal set efficiency versus individual members. The comparison applies only to repetitions with all five validated member references. Members must have compatible roles/class order and normalized seven-class probabilities; the ensemble averages posteriors, not raw densities.', '', 'For eligible repetitions, the protocol specifies equal 0.2 weights and one global simplex vector selected on tuning balanced accuracy. The search uses five vertices, 1,000 seeded Dirichlet candidates, top-ten refinements at transfers 0.10/0.05/0.01, up to 2,000 candidates, and deterministic ties by distance to equal weights then order. Any selected weights freeze before calibration/test. All five members are required for a primary ensemble; partial ensembles are not primary.', '', _e6_reporting_text(ledger), '', '### E6 outcome summary','', _summary(summary,6),_availability_line(summary,6),'', 'Ensemble-to-member matched comparisons are in `E6_ENSEMBLE_MEMBER_PAIRED.csv` (rows: '+str(pairs['E6_ENSEMBLE_MEMBER_PAIRED.csv'])+').', '', *_finding_lines(findings[6]), '', '## Cross-experiment evidence and limits','', 'Predictive performance, statistical fidelity, resource feasibility, and artifact reproducibility answer different questions. E1/E2 remain frozen prior evidence. New E3–E6 models do not repair E1 failures or fill unavailable E2 primary cells. Interpretations are conditional on generator, learner, class, severity, mechanism, rate, repetition, and artifact availability. Survivor bias and missing dependencies constrain comparisons. Timing varies with hardware, libraries, concurrency, and system load. No test-based selection, bootstrap, or report-friendly subset was introduced. E2 contains no TSTR; E3 declared synthetic-only training routes are retained, with no additional TSTR arm outside that established design.', '', '## Resource feasibility and failure taxonomy','', *resource_disclosure, '', '## Main tables and figures','', f"The validated report has {len(per)} successful per-repetition rows and {len(csvrows(rd/'per_class_metrics.csv'))} per-class rows. Group means/sample SDs: `experiment_outcome_coverage.csv`; individual observations: `per_repetition_metrics.csv`; paired outcomes: `matched_paired_differences.csv` and `matched_paired_summary.csv`; class-level recall/coverage/set size: `per_class_metrics.csv`; all planned cells: `planned_case_ledger.csv`.",'', '| Figure | Planned denominator | Successful BA rows | Denominator scope |','|---|---:|---:|---|']
 if scope is not None:
  h=lines.index('| Figure | Planned denominator | Successful BA rows | Denominator scope |')
  lines[h]='| Figure | Planned denominator | Successful BA rows | User-stopped cases | Denominator scope |'
  lines[h+1]='|---|---:|---:|---:|---|'
 for x in figs:
  if scope is not None:lines.append(f"| `{x['path']}` | {x['planned_unique_case_denominator']} | {x['successful_BA_evaluation_denominator']} | {x.get('user_stopped_scientific_case_denominator',0)} | {x.get('denominator_scope','E'+str(x['experiment'])+' planned cases')} |")
  else:lines.append(f"| `{x['path']}` | {x['planned_unique_case_denominator']} | {x['successful_BA_evaluation_denominator']} | {x.get('denominator_scope','E'+str(x['experiment'])+' planned cases')} |")
 if scope is not None:
  for i,line in enumerate(lines):
   if line.startswith('Question: how halving or reducing one class'):
    lines[i]=line+' The original three-repetition grid was not completed after the user-directed scope amendment.'
   if line.startswith('Question: whether direct and synthetic-data pipelines suppress'):
    lines[i]=line+' The original three-repetition grid was not completed after the user-directed scope amendment.'
 lines += condition_findings_reference_lines(load(rd/'report_result.json').get('condition_findings'))
 lines += ['', '## Reproduction','', 'See `RUN_RESUME_REPRODUCE.md`, frozen manifests, source/dependency files, the verified E1 wrap-up archive (curated as direct archive members; the earlier ZIP is not nested), and the E2 provenance directory. Restore content-deduplicated paths with `python3 restore_archive_aliases.py`. Historical E1 models/prediction arrays omitted from the compact migration are not claimed as restored.']
 lines=_insert_e3_rep1_publication_disclosure(lines,runtime)
 p=rd/'FINAL_SCIENTIFIC_REPORT.md';p.write_text('\n'.join(lines)+'\n',encoding='utf-8');return p
def _reporting_site_overlay(root):
 root=Path(root).resolve()
 return [root/'venv'/'lib'/'python3.12'/'site-packages',
  Path('/home/ubuntu/.local/lib/python3.12/site-packages'),
  Path('/usr/lib/python3/dist-packages')]

def _activate_reporting_site_overlay(root):
 overlay=[str(p) for p in _reporting_site_overlay(root)]
 sys.path[:]=overlay+[p for p in sys.path if p not in overlay]

def _reporting_python_and_env(root):
 root=Path(root).resolve();py=root/'venv'/'bin'/'python'
 if not py.is_file():raise EvidenceError('recorded project venv Python is missing: '+str(py))
 overlay=_reporting_site_overlay(root)
 env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(str(p) for p in overlay)
 for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):env[name]='1'
 env['MPLBACKEND']='Agg'
 return py,env

def validate_e5_label_noise_source_class_rates(path,report_result):
 rows=csvrows(path)
 if len(rows)!=63:raise EvidenceError(f'E5 label-noise source-class rate table must contain 63 rows, found {len(rows)}')
 counts=report_result.get('evidence_table_counts') if isinstance(report_result,dict) else None
 count=counts.get('E5_label_noise_source_class_rate_rows') if isinstance(counts,dict) else None
 if type(count) is not int or count!=63:raise EvidenceError(f'report_result E5 label-noise source-class rate count must be 63, found {count!r}')
 labels=('A','F','G','K','M','GALAXY','QSO')
 expected_rates={0.05:4000,0.1:8000,0.2:16000}
 groups=collections.defaultdict(list);seen=set()
 for row in rows:
  try:
   rep=int(row['rep']);rate=float(row['planned_corruption_rate']);class_id=int(row['source_class_id'])
   original=int(row['original_source_class_count']);affected=int(row['affected_source_class_count']);changed=int(row['changed_label_count'])
   realized=float(row['realized_source_class_corruption_rate'])
  except (KeyError,TypeError,ValueError,OverflowError) as e:raise EvidenceError(f'malformed E5 label-noise source-class rate row: {e}') from e
  if rep not in (1,2,3) or rate not in expected_rates or class_id not in range(7):raise EvidenceError('E5 label-noise source-class rate has a foreign repetition, rate, or class')
  rate_suffix={0.05:'05',0.1:'10',0.2:'20'}[rate]
  task_key=f'e5/rep_{rep}/corruption/label_noise_{rate_suffix}'
  if row.get('task_key')!=task_key or row.get('source_class_label')!=labels[class_id]:raise EvidenceError('E5 label-noise source-class task/label identity is inconsistent')
  key=(rep,rate,class_id)
  if key in seen:raise EvidenceError('duplicate E5 label-noise source-class rate row')
  seen.add(key)
  if row.get('rate_status')!='available' or original<=0 or affected<0 or changed<0 or changed>affected or affected>original:
   raise EvidenceError('E5 label-noise rate row lacks available full-support counts or has invalid counts')
  if not math.isfinite(realized) or not math.isclose(realized,changed/original,rel_tol=0.0,abs_tol=1e-12):
   raise EvidenceError('E5 label-noise realized source-class rate does not equal changed/full original support')
  if row.get('realized_corruption_rate') in ('',None):raise EvidenceError('E5 label-noise realized overall corruption rate is missing')
  try:overall=float(row['realized_corruption_rate'])
  except (TypeError,ValueError,OverflowError) as e:raise EvidenceError('E5 label-noise realized overall corruption rate is malformed') from e
  if not math.isfinite(overall) or not math.isclose(overall,rate,rel_tol=0.0,abs_tol=1e-12):raise EvidenceError('E5 label-noise realized overall corruption rate differs from planned rate')
  groups[(rep,rate)].append((class_id,original,changed))
 if len(seen)!=63:raise EvidenceError('E5 label-noise source-class rate grid is incomplete')
 for rep in (1,2,3):
  for rate,total_changed in expected_rates.items():
   group=groups.get((rep,rate),[])
   if sorted(x[0] for x in group)!=list(range(7)):raise EvidenceError('E5 label-noise source-class grid is missing or duplicates a class')
   if sum(x[1] for x in group)!=80000:raise EvidenceError('E5 label-noise original class supports do not sum to 80,000')
   if sum(x[2] for x in group)!=total_changed:raise EvidenceError('E5 label-noise changed-label count differs from the fixed affected-row budget')
 return len(rows)

def _current_e6_v2_tasks(runtime, registry_tasks):
 runtime=Path(runtime).resolve()
 if isinstance(registry_tasks,dict): registry_tasks=list(registry_tasks.values())
 if not isinstance(registry_tasks,list): raise EvidenceError('E6-v2 applicability requires a valid registry task list')
 freeze_path=runtime/'manifests'/'freeze.json'
 freeze=None
 if freeze_path.is_file():
  try: freeze=load(freeze_path)
  except Exception as exc: raise EvidenceError('authoritative freeze manifest is malformed') from exc
  if not isinstance(freeze,dict): raise EvidenceError('authoritative freeze manifest is malformed')
 overlay_sha=freeze.get('e6_execution_overlay_sha256') if freeze is not None else None
 if overlay_sha is not None:
  if not isinstance(overlay_sha,str) or len(overlay_sha)!=64 or any(c not in '0123456789abcdef' for c in overlay_sha.lower()):
   raise EvidenceError('declared E6 execution overlay SHA is malformed')
  overlay_path=runtime/'manifests'/'E6_EXECUTION_OVERLAY_V2.json'
  if not overlay_path.is_file() or overlay_path.is_symlink() or sha_file(overlay_path)!=overlay_sha:
   raise EvidenceError('declared E6-v2 execution overlay is missing or changed')
  try: overlay=load(overlay_path)
  except Exception as exc: raise EvidenceError('declared E6-v2 execution overlay is malformed') from exc
  if not isinstance(overlay,dict) or overlay.get('protocol_version')!='E6-v2' or overlay.get('schema_version')!='lamost-e6-execution-overlay/2':
   raise EvidenceError('declared E6-v2 execution overlay has an unsupported schema or protocol')
  expected=overlay.get('tasks')
  if not isinstance(expected,list) or len(expected)!=6:
   raise EvidenceError('declared E6-v2 overlay must contain exactly six primary task definitions')
  keys=[]
  for row in expected:
   if not isinstance(row,dict) or row.get('e6_protocol_version')!='E6-v2' or not isinstance(row.get('task_key'),str) or not row['task_key']:
    raise EvidenceError('declared E6-v2 overlay task key/version is missing or malformed')
   keys.append(row['task_key'])
  if len(set(keys))!=6: raise EvidenceError('declared E6-v2 overlay task keys are not unique')
  by_key={}
  for row in registry_tasks:
   if not isinstance(row,dict): continue
   key=row.get('key')
   if key in set(keys):
    if key in by_key: raise EvidenceError('duplicate E6-v2 registry task key: '+str(key))
    by_key[key]=row
  if set(by_key)!=set(keys): raise EvidenceError('registry E6-v2 primary keys differ from the published execution overlay')
  if any(by_key[k].get('e6_protocol_version')!='E6-v2' for k in keys):
   raise EvidenceError('registry E6-v2 task tags are missing or malformed relative to the published overlay')
  return [by_key[k] for k in keys]
 tagged=[]
 for row in registry_tasks:
  if not isinstance(row,dict) or str(row.get('experiment'))!='6' or row.get('kind')!='ensemble' or not row.get('scientific_case'): continue
  version=row.get('e6_protocol_version')
  if version=='E6-v2': tagged.append(row)
  elif version not in (None,''): raise EvidenceError('unsupported E6 ensemble protocol-version tag: '+str(version))
 return tagged

E6_V2_REQUIRED_OUTPUTS={
 'E6_V2_MAIN_CELL_LEDGER_21.csv','E6_V2_AVAILABILITY.csv',
 'E6_V2_ENSEMBLE_REPETITIONS.csv','E6_V2_MEMBER_COMPARISONS.csv',
 'E6_V2_PAIRED_COMPARISONS.csv','E6_V2_PAIRED_SUMMARY.csv',
 'E6_V2_WEIGHTS.csv','E6_V2_PHASE_COSTS.csv','E6_V2_PARTIAL_TUNING_EVIDENCE.csv',
 'E6_V2_TUNING_WEIGHT_STABILITY.csv','E6_SUPERSEDED_AVAILABILITY_GATE_HISTORY.csv'
}

def validate_e6_v2_export(runtime, output_dir):
 runtime=Path(runtime).resolve();out=Path(output_dir).resolve()
 try: out.relative_to((runtime/'reports').resolve())
 except ValueError: raise EvidenceError('E6-v2 export is outside the reports directory')
 if not out.is_dir() or not out.name.startswith('E6_V2_FINAL_'):raise EvidenceError('current E6-v2 export directory is missing or misnamed')
 receipt_path=out/'E6_V2_REPORT_RECEIPT.json'
 if not receipt_path.is_file():raise EvidenceError('current E6-v2 export receipt is missing')
 receipt=load(receipt_path);regpath=runtime/'registry.json';registry=load(regpath)
 if receipt.get('schema_version')!='lamost-e6-v2-descriptive-export/1' or receipt.get('status')!='descriptive_outputs_only_not_project_completion':raise EvidenceError('unsupported E6-v2 descriptive receipt')
 old_ledger=runtime/'reports'/'history'/'E6_v1_superseded_before_v2_20261027'/'E6_FINAL_CELL_LEDGER_21.csv'
 if receipt.get('inputs',{}).get('registry_sha256')!=sha_file(regpath) or receipt.get('registry_observed_utc')!=registry.get('observed_utc'):raise EvidenceError('E6-v2 export is stale relative to current registry')
 if not old_ledger.is_file() or receipt.get('inputs',{}).get('superseded_ledger_sha256')!=sha_file(old_ledger):raise EvidenceError('E6-v2 export did not bind the preserved superseded history ledger')
 actions=receipt.get('actions',{})
 if any(actions.get(k) is not False for k in ('fitting','model_loading','posterior_generation','calibration_or_test_inference','bootstrap')):raise EvidenceError('E6-v2 exporter receipt reports disallowed scientific computation')
 tasks=registry.get('tasks')
 if not isinstance(tasks,list):raise EvidenceError('current registry task list is missing')
 e6=_current_e6_v2_tasks(runtime,tasks)
 if len(e6)!=6 or len({t.get('key') for t in e6})!=6:raise EvidenceError('current E6-v2 primary plan must contain six unique ensemble tasks')
 if any(t.get('status')!='validated_terminal' or _out(t) not in OUTCOMES for t in e6):raise GatePending('corrected E6-v2 ensemble tasks are not all terminal')
 output_hashes=receipt.get('outputs_sha256')
 if not isinstance(output_hashes,dict) or not E6_V2_REQUIRED_OUTPUTS.issubset(output_hashes):raise EvidenceError('E6-v2 export is missing required current outputs')
 for name,digest in output_hashes.items():
  member=PurePosixPath(name)
  if member.is_absolute() or any(x in {'','.','..'} for x in member.parts):raise EvidenceError('unsafe E6-v2 output name: '+str(name))
  f=(out/Path(*member.parts)).resolve()
  try:f.relative_to(out)
  except ValueError:raise EvidenceError('E6-v2 output escapes its report directory')
  if not f.is_file() or not isinstance(digest,str) or sha_file(f)!=digest:raise EvidenceError('E6-v2 output hash mismatch: '+name)
 for name in E6_V2_REQUIRED_OUTPUTS:
  if not (out/name).is_file():raise EvidenceError('E6-v2 required output absent: '+name)
 with (out/'E6_V2_MAIN_CELL_LEDGER_21.csv').open(newline='',encoding='utf-8') as f:ledger=list(csv.DictReader(f))
 if len(ledger)!=21:raise EvidenceError('E6-v2 main ledger must contain 15 historical references and six primary ensemble rows')
 historical=[r for r in ledger if r.get('cell_kind')=='member_reference' and r.get('provenance_group')=='historical_E3_direct_reference_not_E6_scoring']
 primary=[r for r in ledger if r.get('cell_kind')=='primary_ensemble' and r.get('provenance_group')=='E6_v2_primary_ensemble']
 if len(historical)!=15 or len(primary)!=6:raise EvidenceError('E6-v2 ledger provenance groups are not 15 historical references plus six primary ensembles')
 expected={t['key']:t for t in e6}
 if {r.get('task_key') for r in primary}!=set(expected):raise EvidenceError('E6-v2 ledger primary keys differ from current registry')
 for row in primary:
  task=expected[row['task_key']]
  for col,key in (('status','status'),('outcome','outcome'),('validation_state','validation_state')):
   if str(row.get(col) or '')!=str(task.get(key) or ''):raise EvidenceError('E6-v2 ledger state differs from current registry: '+row['task_key'])
  success=_out(task)=='successful'
  if (row.get('evaluation_present','').lower()=='true')!=success:raise EvidenceError('E6-v2 metric presence differs from terminal outcome: '+row['task_key'])
  if not success and any(row.get(k) not in ('',None) for k in ('balanced_accuracy','coverage','mean_set_size')):raise EvidenceError('E6-v2 non-success row contains fabricated performance metrics')
 with (out/'E6_V2_AVAILABILITY.csv').open(newline='',encoding='utf-8') as f:availability=list(csv.DictReader(f))
 if len(availability)!=6 or {r.get('task_key') for r in availability}!=set(expected):raise EvidenceError('E6-v2 availability table does not cover six current primary tasks')
 for row in availability:
  task=expected[row['task_key']]
  if str(row.get('outcome') or '')!=str(_out(task) or ''):raise EvidenceError('E6-v2 availability outcome differs from registry')
  if row.get('outcome')!='successful' and row.get('member_comparison_present','').lower()=='true':raise EvidenceError('failed/unavailable E6 task claims member comparisons')
 with (out/'E6_V2_PARTIAL_TUNING_EVIDENCE.csv').open(newline='',encoding='utf-8') as f:partial=list(csv.DictReader(f))
 if len(partial)!=6 or {r.get('task_key') for r in partial}!=set(expected):raise EvidenceError('E6-v2 partial tuning evidence must account for all six primary tasks')
 for row in partial:
  task=expected[row['task_key']];success=_out(task)=='successful'
  if str(row.get('task_outcome') or '')!=str(_out(task) or '') or row.get('performance_metrics_included','').lower()!='false':raise EvidenceError('E6 partial tuning record outcome/metric scope is invalid')
  if (row.get('test_evaluation_present','').lower()=='true')!=success:raise EvidenceError('E6 partial tuning record misstates test evaluation presence')
  valid=row.get('evidence_state')=='validated_frozen_tuning_evidence'
  frozen=row.get('frozen_weights_archive_path') or ''
  ledger=row.get('candidate_ledger_archive_path') or ''
  if valid and (not frozen or frozen not in output_hashes):raise EvidenceError('valid E6 frozen tuning weights are not preserved in versioned export')
  if valid and task.get('mode')=='learned' and (not ledger or ledger not in output_hashes):raise EvidenceError('valid learned E6 candidate ledger is not preserved in versioned export')
  if not valid and (frozen or ledger):raise EvidenceError('invalid/unvalidated E6 tuning evidence is presented as preserved valid evidence')
 source_hashes=receipt.get('source_sha256')
 source_paths={'exporter_sha256':runtime/'source'/'export_e6_v2_descriptive.py',
               'helper_sha256':runtime/'source'/'e6_v2_reporting.py'}
 if not isinstance(source_hashes,dict) or set(source_hashes)!=set(source_paths):raise EvidenceError('E6-v2 exporter source provenance is missing or unexpected')
 for name,path in source_paths.items():
  if not path.is_file() or sha_file(path)!=source_hashes[name]:raise EvidenceError('E6-v2 exporter source hash mismatch: '+name)
 return {'path':str(out),'receipt_sha256':sha_file(receipt_path),'registry_sha256':sha_file(regpath),'historical_member_references':15,'primary_ensemble_cases':6,'primary_outcomes':dict(collections.Counter(str(_out(t)) for t in e6))}

def refresh_e6_v2_export(root,runtime,py,env):
 root=Path(root).resolve();runtime=Path(runtime).resolve();rd=runtime/'reports';regpath=runtime/'registry.json'
 if not regpath.is_file():
  freeze_path=runtime/'manifests'/'freeze.json'
  if freeze_path.is_file():
   try: freeze=load(freeze_path)
   except Exception as exc: raise EvidenceError('authoritative freeze manifest is malformed') from exc
   if isinstance(freeze,dict) and freeze.get('e6_execution_overlay_sha256') is not None:
    raise EvidenceError('declared E6-v2 overlay cannot be checked because authoritative registry is missing')
  return None
 reg=load(regpath);registry_tasks=reg.get('tasks') if isinstance(reg,dict) else None
 if not isinstance(registry_tasks,list): raise EvidenceError('authoritative registry task list is malformed')
 v2=_current_e6_v2_tasks(runtime,registry_tasks)
 if not v2:return None
 registry_sha=sha_file(regpath);prefix=registry_sha[:12]
 base=rd/f'E6_V2_FINAL_{prefix}'
 if base.exists():
  try:return validate_e6_v2_export(runtime,base)
  except (EvidenceError,GatePending):pass
 output=base
 index=1
 while output.exists():output=rd/f'E6_V2_FINAL_{prefix}_{index}';index+=1
 old=rd/'history'/'E6_v1_superseded_before_v2_20261027'/'E6_FINAL_CELL_LEDGER_21.csv'
 exporter=runtime/'source'/'export_e6_descriptive.py'
 if not exporter.is_file() or not old.is_file():raise EvidenceError('E6-v2 exporter or preserved superseded ledger is missing')
 proc=subprocess.run([str(py),str(exporter),'--e6-v2','--runtime',str(runtime),'--superseded-ledger',str(old),'--output',str(output)],capture_output=True,text=True,timeout=600,env=env)
 if proc.returncode:raise EvidenceError('E6-v2 descriptive export failed: '+proc.stderr[-2500:])
 return validate_e6_v2_export(runtime,output)

def report_cli_and_validate(root,runtime,terminal):
 py,env=_reporting_python_and_env(root)
 proc=subprocess.run([str(py),str(runtime/'source/report_cli.py')],capture_output=True,text=True,timeout=1800,env=env)
 if proc.returncode:raise EvidenceError('report_cli failed: '+proc.stderr[-3000:])
 e6_export=refresh_e6_v2_export(root,runtime,py,env)
 rd=runtime/'reports';scope=_split_user_stopped_coverage(runtime,terminal);result=load(rd/'report_result.json')
 if scope is not None:
  result['user_scope_amendment']={k:v for k,v in scope.items() if k!='user_stopped_by_group'};atomic_json(rd/'report_result.json',result)
 if result.get('status')!='success' or result.get('planned_scientific_cases')!=sum(EXPECTED.values()):raise EvidenceError('report_cli did not cover all planned cases')
 required=('all_task_ledger.csv','planned_case_ledger.csv','experiment_outcome_coverage.csv','per_repetition_metrics.csv','per_class_metrics.csv','matched_paired_differences.csv','matched_paired_summary.csv','dataset_inventory.csv','E4_class_histograms.csv','E5_corruption_realization_summary.csv','label_transition_counts.csv','E5_label_noise_source_class_rates.csv','model_selection_ledger.csv','evaluation_support_fallbacks.csv','evaluation_support_fallbacks_per_class.csv','E6_weights.csv','E6_candidate_ledger.csv','resource_failure_ledger.csv','resource_failure_summary.csv','terminal_trial_cutoffs.csv','terminal_trial_cutoffs.json')
 for n in required:
  if not (rd/n).is_file() or (rd/n).stat().st_size==0:raise EvidenceError('required report artifact absent/empty: '+n)
  try:
   if n.endswith('.json'):load(rd/n)
   else:csvrows(rd/n)
  except Exception as e:raise EvidenceError(f'required report artifact is malformed: {n}: {e}') from e
 rows=csvrows(rd/'planned_case_ledger.csv')
 if len(rows)!=sum(EXPECTED.values()):raise EvidenceError('planned case ledger row count wrong')
 for e,n in EXPECTED.items():
  x=[t for t in rows if str(t.get('experiment'))==e]
  if len(x)!=n or any(t.get('outcome') in {'planned','waiting_for_dependency','running','operationally_invalid','operationally_interrupted','packaging_pending'} for t in x):raise EvidenceError(f'E{e} outcome ledger is unresolved/incomplete')
 label_rate_rows=validate_e5_label_noise_source_class_rates(rd/'E5_label_noise_source_class_rates.csv',result)
 figs=figure_denominators(rd);pairs=expanded_pairs(rd)
 for n in ('figure_denominators.csv','E3_SHARED_REAL_PAIRED.csv','E4_CONTROL_TREATMENT_PAIRED.csv','E5_CLEAN_CORRUPTED_PAIRED.csv','E6_ENSEMBLE_MEMBER_PAIRED.csv'):
  if not (rd/n).is_file() or (rd/n).stat().st_size==0:raise EvidenceError('paired/figure denominator report absent: '+n)
 return {'report_result':result,'required_csvs':list(required),'figures':figs,'expanded_pairing_rows':pairs,'validated_E5_label_noise_source_class_rate_rows':label_rate_rows,'e6_v2_export':e6_export}

def _condition_findings_expected_counts():
 return {'E4_summary_strata':910,'E4_pair_rows':2730,'E4_comparison_strata':{'altered_direct_minus_unchanged_control':238,'treatment_minus_untreated_altered':336,'treatment_minus_unchanged_control':336},'E5_overall_summary_strata':288,'E5_overall_pair_rows':864,'E5_class_summary_strata':2016,'E5_class_pair_rows':6048}

def _verify_condition_findings_artifacts(runtime,info):
 runtime=Path(runtime);rd=runtime/'reports';builder=runtime/'source'/'build_condition_findings.py'
 if info.get('builder_path')!=(runtime.name+'/source/build_condition_findings.py') or not builder.is_file() or sha_file(builder)!=info.get('builder_sha256'):raise EvidenceError('condition-findings builder missing, mislocated, or changed')
 if info.get('status')!='descriptive_appendices_built' or info.get('project_state')!='terminal_snapshot_requires_final_validation':raise EvidenceError('condition-findings appendix is not a terminal descriptive snapshot')
 if info.get('counts')!=_condition_findings_expected_counts():raise EvidenceError('condition-findings grid counts differ from the complete planned grid')
 if set(info.get('input_sha256',{}))!=set(CONDITION_FINDINGS_INPUTS):raise EvidenceError('condition-findings input hash inventory is incomplete or unexpected')
 for name in CONDITION_FINDINGS_INPUTS:
  p=rd/name
  if not p.is_file() or sha_file(p)!=info['input_sha256'][name]:raise EvidenceError('condition-findings source CSV changed or is missing: '+name)
 manifest_path=rd/'CONDITION_FINDINGS_MANIFEST.json'
 if not manifest_path.is_file() or str(manifest_path.relative_to(runtime.parent))!=info.get('manifest_path') or sha_file(manifest_path)!=info.get('manifest_sha256'):
  raise EvidenceError('condition-findings manifest path or SHA differs')
 manifest=load(manifest_path)
 if manifest.get('status')!=info['status'] or manifest.get('project_state')!=info['project_state'] or manifest.get('counts')!=info['counts'] or manifest.get('input_sha256')!=info['input_sha256']:
  raise EvidenceError('condition-findings manifest contents differ from report_result binding')
 outputs=info.get('outputs',{})
 names={'E4_CONDITION_FINDINGS.md','E5_CONDITION_FINDINGS.md','CONDITION_FINDINGS_INDEX.md','CONDITION_FINDINGS_MANIFEST.json'}
 if set(outputs)!=names:raise EvidenceError('condition-findings output inventory is incomplete')
 for name,record in outputs.items():
  p=rd/name
  if record.get('path')!=str(p.relative_to(runtime.parent)) or not p.is_file() or p.stat().st_size!=int(record.get('bytes',-1)) or sha_file(p)!=record.get('sha256'):
   raise EvidenceError('condition-findings output changed or is missing: '+name)
  if name!='CONDITION_FINDINGS_MANIFEST.json' and manifest.get('outputs',{}).get(name)!=record.get('sha256'):
   raise EvidenceError('condition-findings output is not bound by its manifest: '+name)
 if not manifest.get('input_sha256') or manifest.get('created_from_existing_csvs_only') is not True:
  raise EvidenceError('condition-findings manifest lacks its data-only input provenance')
 return info

def validate_condition_findings(runtime,expected=None):
 runtime=Path(runtime);result=load(runtime/'reports'/'report_result.json');observed=result.get('condition_findings')
 if not isinstance(observed,dict):raise EvidenceError('report_result is missing condition-findings binding')
 if expected is not None and observed!=expected:raise EvidenceError('cached condition-findings binding differs from report_result')
 return _verify_condition_findings_artifacts(runtime,observed)

def build_condition_findings(runtime):
 runtime=Path(runtime).resolve();rd=runtime/'reports';builder=runtime/'source'/'build_condition_findings.py'
 if not builder.is_file():raise EvidenceError('condition-findings builder is not installed in runtime/source')
 import importlib.util
 spec=importlib.util.spec_from_file_location('_lamost_condition_findings_builder',builder)
 if spec is None or spec.loader is None:raise EvidenceError('condition-findings builder cannot be loaded')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 manifest=module.build(rd,rd)
 if not isinstance(manifest,dict):raise EvidenceError('condition-findings builder returned malformed output')
 mpath=rd/'CONDITION_FINDINGS_MANIFEST.json'
 if not mpath.is_file():raise EvidenceError('condition-findings builder did not save its manifest')
 if manifest.get('manifest_sha256')!=sha_file(mpath):raise EvidenceError('condition-findings builder returned a manifest hash mismatch')
 outputs={}
 for name in ('E4_CONDITION_FINDINGS.md','E5_CONDITION_FINDINGS.md','CONDITION_FINDINGS_INDEX.md','CONDITION_FINDINGS_MANIFEST.json'):
  p=rd/name
  if not p.is_file():raise EvidenceError('condition-findings output missing: '+name)
  outputs[name]={'path':p.relative_to(runtime.parent).as_posix(),'bytes':p.stat().st_size,'sha256':sha_file(p)}
 info={'status':manifest.get('status'),'project_state':manifest.get('project_state'),'counts':manifest.get('counts'),'input_sha256':manifest.get('input_sha256'),'builder_path':builder.relative_to(runtime.parent).as_posix(),'builder_sha256':sha_file(builder),'manifest_path':mpath.relative_to(runtime.parent).as_posix(),'manifest_sha256':sha_file(mpath),'outputs':outputs}
 _verify_condition_findings_artifacts(runtime,info)
 return info

def prepare_report_phase(root,runtime,terminal):
 info=report_cli_and_validate(root,runtime,terminal)
 condition=build_condition_findings(runtime)
 result=load(runtime/'reports'/'report_result.json');result['condition_findings']=condition
 atomic_json(runtime/'reports'/'report_result.json',result)
 info['report_result']=result;info['condition_findings']=condition;info['report_result_sha256']=sha_file(runtime/'reports'/'report_result.json')
 return info

def bind_condition_findings_after_review(runtime,report_info,expected_hashes):
 runtime=Path(runtime).resolve();info=(report_info or {}).get('condition_findings')
 if info is None:raise EvidenceError('reviewed report candidate lacks condition-level findings')
 info=validate_condition_findings(runtime,info)
 result_path=runtime/'reports'/'report_result.json';expected_hashes=expected_hashes or {}
 if expected_hashes.get(str(result_path.resolve()))!=sha_file(result_path):raise EvidenceError('report-review candidate did not bind report_result.json with condition-findings metadata')
 for record in info['outputs'].values():
  path=(runtime.parent/record['path']).resolve()
  if not path.is_file() or sha_file(path)!=record['sha256']:raise EvidenceError('condition-findings output changed after review: '+str(path))
  expected_hashes[str(path)]=record['sha256']
 return expected_hashes

def condition_findings_reference_lines(info):
 if not isinstance(info,dict):raise EvidenceError('final report lacks condition-findings links')
 counts=info.get('counts',{})
 if counts!=_condition_findings_expected_counts():raise EvidenceError('final report condition-findings denominators are incomplete')
 return ['', '## E4/E5 condition-level paired appendices', '', 'The complete condition-level appendices retain every planned E4 and E5 stratum, including rows with zero matched repetitions. Means and sample standard deviations use the available matched repetitions; no significance tests, bootstrap intervals, or cross-condition pooling are used.', '', f"Coverage: {counts.get('E4_summary_strata')} E4 condition strata and {counts.get('E4_pair_rows')} repetition rows; {counts.get('E5_overall_summary_strata')} E5 overall strata and {counts.get('E5_overall_pair_rows')} repetition rows; {counts.get('E5_class_summary_strata')} E5 per-class strata and {counts.get('E5_class_pair_rows')} per-class repetition rows.", '', 'See the [condition findings index](CONDITION_FINDINGS_INDEX.md), [E4 condition findings](E4_CONDITION_FINDINGS.md), and [E5 condition findings](E5_CONDITION_FINDINGS.md). The CSV inputs, their hashes, builder source hash, and appendix output hashes are recorded in `report_result.json` and `CONDITION_FINDINGS_MANIFEST.json`.']

def sanitize_operational_json(obj):
 banned={'pid','pgid','process_start_ticks','worker_pid','controller_pid','owner_pid','request_path','result_path','worker_log_path','stdout','stderr','phase_supervision','private_process_receipt','process_inventory','worker_inventory','verified_workers','processes','cmdline','command_line','argv','env','environ','environment_variables','env_vars','hold_nonce','nonce'}
 def clean(x):
  if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if str(k).lower() not in banned and 'pid' not in str(k).lower()}
  if isinstance(x,list):return [clean(v) for v in x]
  if isinstance(x,str):
   from reason_text_curation import sanitize_reason_text
   safe=sanitize_reason_text(x)
   if safe is not None:x=safe
   if 'phase_timeout:' in x:return sanitize_operational_json(x)
   return x
  return x
 if isinstance(obj,str) and 'phase_timeout:' in obj:
  import re
  match=re.search(r'phase_timeout:\s*(\{.*\})',obj)
  if match:
   try:
    receipt=ast.literal_eval(match.group(1));receipt=clean(receipt)
    # Keep scientific timeout reason, elapsed seconds, memory use, exit status, and timestamp.
    keep={'phase','exit_code','seconds','peak_tree_rss_kib','reason','finished_at'}
    receipt={k:v for k,v in receipt.items() if k in keep}
    return obj[:match.start(1)]+json.dumps(receipt,sort_keys=True)
   except Exception:pass
  return re.sub(r'(?i)(?:\s*[,{]\s*)[\'\"]?(?:pid|pgid|worker_pid|controller_pid|owner_pid)[\'\"]?\s*[:=]\s*[^,}]+,?', '', obj)
 return clean(obj)
def archive_json_entry(path,member,category,archive_root,expected_source_sha256=None):
 path=Path(path)
 try:
  raw=path.read_bytes();doc=json.loads(raw)
 except (UnicodeDecodeError,json.JSONDecodeError):return ent(path,member,category,archive_root)
 source_hash=sha_bytes(raw);expected=(expected_source_sha256 or {}).get(str(path.resolve()))
 if expected and source_hash!=expected:raise EvidenceError('reviewed JSON source changed before archive view creation: '+str(path))
 cleaned=sanitize_operational_json(doc)
 if cleaned==doc:return ent(path,member,category,archive_root)
 if isinstance(cleaned,dict):cleaned['_archive_sanitization']={'view':'derived privacy-curated JSON','source_sha256':source_hash,'removed':'process identifiers, ownership nonces, phase-supervision receipts, process inventories and private process paths'}
 else:cleaned={'archive_sanitization':{'view':'derived privacy-curated JSON','source_sha256':source_hash},'data':cleaned}
 payload=(json.dumps(cleaned,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()
 return Entry(payload,member,category)
def _sanitize_reason_text(value):
 from reason_text_curation import sanitize_reason_text
 result=sanitize_reason_text(value)
 return value if result is None else result

def _report_csv_archive_entries(path,member,category,root,expected_source_sha256=None):
 path=Path(path);raw=path.read_bytes();source_sha=sha_bytes(raw)
 expected=(expected_source_sha256 or {}).get(str(path.resolve()))
 if expected and source_sha!=expected:raise EvidenceError('reviewed report CSV source changed before archive curation: '+str(path))
 try:text=raw.decode('utf-8')
 except UnicodeDecodeError as e:raise EvidenceError('report CSV is not UTF-8: '+str(path)) from e
 rows=list(csv.reader(io.StringIO(text,newline='')))
 if not rows:return [Entry(raw,member,category)]
 header=rows[0];changes=[]
 for rownum,row in enumerate(rows[1:],start=2):
  for colnum,value in enumerate(row):
   safe=_sanitize_reason_text(value)
   if safe!=value:
    row[colnum]=safe
    changes.append({'row':rownum,'column':header[colnum] if colnum<len(header) else str(colnum+1),'original_cell_sha256':sha_bytes(value.encode('utf-8')),'sanitized_cell_sha256':sha_bytes(safe.encode('utf-8'))})
 if not changes:return [Entry(raw,member,category)]
 stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerows(rows)
 view=stream.getvalue().encode('utf-8');view_sha=sha_bytes(view)
 side={'schema_version':'lamost-report-csv-privacy-view/1','source_member':path.relative_to(root).as_posix(),'archive_member':member,'source_sha256':source_sha,'view_sha256':view_sha,'changed_cell_count':len(changes),'changed_cells':changes,'curation_note':'Only changed string cells were sanitized. Original CSV remains unchanged on EC2; cell contents are represented by hashes to avoid copying private process receipt text into this sidecar.'}
 side_bytes=(json.dumps(side,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()
 return [Entry(view,member,category+'_derived_privacy_view'),Entry(side_bytes,member+'.curation.json',category+'_privacy_view_provenance')]

def scrub_registry(obj):
 banned={'pid','pgid','process_start_ticks','worker_pid','controller_pid','owner_pid','request_path','result_path','worker_log_path','stdout','stderr','phase_supervision','private_process_receipt','process_inventory','processes','cmdline','command_line','argv'}
 def f(x):
  if isinstance(x,dict):
   out={}
   for k,v in x.items():
    lk=str(k).lower()
    if lk in banned or 'pid' in lk:continue
    if lk=='artifact_dir' and x.get('key'):out[k]='runtime_20261025/artifacts/'+x['key'];continue
    if lk=='attempts' and isinstance(v,list):
     keep=[]
     for a in v:
      if isinstance(a,dict):keep.append({kk:f(vv) for kk,vv in a.items() if kk in {'attempt_id','started_utc','finished_utc','observed_utc','reason','status','outcome','validation_state','resource_profile','peak_tree_rss_bytes','attempt_number'}})
     out[k]=keep;continue
    out[k]=f(v)
   return out
  if isinstance(x,list):return [f(v) for v in x]
  return sanitize_operational_json(x) if isinstance(x,str) else x
 y=f(obj);y['sanitization']={'process IDs/start ticks, request/result paths, private process receipts and worker/controller logs removed':True,'attempt identities, reasons, outcome validation, resource profiles and scientific results preserved':True};return y
E6_PRIVATE_PHASE_RECEIPT_NAMES={'e6_phase_tune.json','e6_phase_cal.json','e6_phase_test.json','e6_phase_events.jsonl'}
E6_PRIVATE_PHASE_RECEIPT_MANIFEST='runtime_20261025/manifests/e6_private_phase_receipt_exclusions.json'

def _is_private_e6_phase_receipt(path):
 p=Path(path)
 return p.name.lower() in E6_PRIVATE_PHASE_RECEIPT_NAMES

def e6_private_phase_receipt_manifest(runtime, registry_records=None):
 runtime=Path(runtime).resolve()
 registry_path=runtime/'registry.json';public_path=runtime/'public_registry.json'
 tasks=None;source_kind='unavailable';source_sha=None
 if registry_path.is_file():
  try: reg=load(registry_path)
  except Exception as exc: raise EvidenceError('authoritative registry is malformed; refusing public fallback') from exc
  if not isinstance(reg,dict) or not isinstance(reg.get('tasks'),list): raise EvidenceError('authoritative registry lacks a valid task list; refusing public fallback')
  tasks=reg['tasks'];source_kind='authoritative_registry';source_sha=sha_file(registry_path)
 elif registry_records is not None:
  tasks=registry_records.get('tasks') if isinstance(registry_records,dict) else registry_records
  source_kind='caller_supplied_task_projection'
 elif public_path.is_file():
  reg=load(public_path);tasks=reg.get('tasks') if isinstance(reg,dict) else None
  source_kind='sanitized_public_registry_projection';source_sha=sha_file(public_path)
 rows=[];seen=set();complete=isinstance(tasks,list)
 if complete:
  for task in tasks:
   if not isinstance(task,dict) or str(task.get('experiment'))!='6' or task.get('kind')!='ensemble': continue
   key=task.get('key')
   if not isinstance(key,str) or not key or PurePosixPath(key).is_absolute() or any(x in {'','.','..'} for x in PurePosixPath(key).parts): raise EvidenceError('unsafe E6 task key in phase receipt curation')
   art=(runtime/'artifacts'/key).resolve()
   try: art.relative_to((runtime/'artifacts').resolve())
   except ValueError: raise EvidenceError('E6 artifact path escapes runtime')
   attempts=art/'attempts'
   if not attempts.exists(): continue
   if attempts.is_symlink() or not attempts.is_dir(): raise EvidenceError('unsafe E6 attempts directory')
   attempt_dirs=sorted((d for d in attempts.iterdir() if d.is_dir() and not d.is_symlink()),key=lambda d:d.name)
   attempt_ordinals={d.resolve():i+1 for i,d in enumerate(attempt_dirs)}
   for dirpath,dirs,files in os.walk(attempts,followlinks=False):
    base=Path(dirpath)
    dirs[:]=sorted(d for d in dirs if not (base/d).is_symlink())
    for name in sorted(files):
     src=base/name
     if not _is_private_e6_phase_receipt(src): continue
     if src.is_symlink() or not src.is_file(): raise EvidenceError('unsafe private E6 phase receipt')
     rel=src.relative_to(art)
     if rel.parts[0]!='attempts' or any(x in {'','.','..'} for x in rel.parts): raise EvidenceError('unsafe E6 receipt relative path')
     digest=sha_file(src);size=src.stat().st_size
     attempt_root=(art/'attempts'/rel.parts[1]).resolve() if len(rel.parts)>1 else None
     ordinal=attempt_ordinals.get(attempt_root)
     if ordinal is None: raise EvidenceError('E6 phase receipt is not inside a recognized attempt directory')
     rows.append({'task_key':key,'attempt_ordinal':ordinal,'receipt_name':rel.name,'bytes':size,'sha256':digest})
 rows.sort(key=lambda r:(r['task_key'],r['attempt_ordinal'],r['receipt_name'],r['sha256']))
 return (json.dumps({'schema_version':'lamost-e6-private-phase-receipt-exclusions/1',
   'source_snapshot_kind':source_kind,'source_snapshot_sha256':source_sha,
   'receipt_inventory_complete':complete,'raw_receipts_included':False,'raw_receipts_remain_on_ec2':True,
   'receipt_count':len(rows),'receipts':rows,
   'curation':'Private E6 tune/cal/test phase receipts and event streams are excluded; this manifest records only task, attempt ordinal, receipt kind, size and SHA-256. If no registry projection was available, the receipt inventory is explicitly incomplete.'},
   indent=2,sort_keys=True)+'\n').encode()

def sensitive(p):
 n=p.name.lower()
 return _is_private_e6_phase_receipt(p) or p.suffix.lower() in {'.pyc','.pyo','.tmp','.swp','.pem','.p12','.pfx'} or n=='.env' or n.endswith('.env') or any(x in n for x in SENSITIVE) or n in {'phase_result.json','phase_exception.json'} or (n.startswith('phase_') and (n.endswith('_state.json') or n.endswith('_result.json') or n.endswith('.stdout.log') or n.endswith('.stderr.log') or n.endswith('.json')))
def iterfiles(base,skip_logs=False):
 base=Path(base)
 if not base.exists():return
 for dp,dirs,files in os.walk(base,followlinks=False):
  d=Path(dp);dirs[:]=sorted(x for x in dirs if x not in SKIPDIRS and not sensitive(Path(x)))
  for name in sorted(files):
   p=d/name
   if sensitive(p) or (skip_logs and p.suffix.lower() in {'.log','.out','.err'}):continue
   if p.is_file():yield p
def ent(path,member,cat,root):
 path=Path(path);Path(member)
 try:path.resolve().relative_to(root.resolve())
 except ValueError:raise ValueError('source outside migration root: '+str(path))
 pp=PurePosixPath(member)
 if pp.is_absolute() or any(x in ('','..','.') for x in pp.parts) or '\\' in member:raise ValueError('unsafe archive member '+member)
 return Entry(path,pp.as_posix(),cat)
def curated_tree_entries(base, member_prefix, category, archive_root, allow_e1_supervisor=False, expected_source_sha256=None):
 base=Path(base);archive_root=Path(archive_root);out=[]
 for f in iterfiles(base):
  rel=f.relative_to(base);parts=[x.lower() for x in rel.parts];name=f.name.lower()
  if any(x in {'operations','process_receipts','private_process_receipts','watchers','watcher'} for x in parts):continue
  if name in {'migration_receipt.json','supervisor_state.json','controller_state.json','finalizer_state.json'}:continue
  if any(x in name for x in ('process_receipt','cleanup_receipt','private_receipt','watcher')) or name.endswith('.receipt.json'):continue
  if f.suffix.lower() in {'.pid','.lock','.out','.err'}:continue
  scientific_supervisor=(allow_e1_supervisor and name=='supervisor.log' and len(parts)>=5 and parts[0:2]==['benchmark','results'] and parts[2]=='e1')
  if f.suffix.lower()=='.log' and not scientific_supervisor:continue
  if name.endswith('.pre_stop_copy'):continue
  member=PurePosixPath(member_prefix,*rel.parts).as_posix()
  out.append(archive_json_entry(f,member,category,archive_root,expected_source_sha256) if f.suffix.lower()=='.json' else ent(f,member,category,archive_root))
 return out


E1_ARCHIVED_PAYLOAD_LOCATOR='e1_recovery_20261024/ARCHIVED_PAYLOAD_LOCATORS_20261028.json'
E1_ARCHIVED_PAYLOAD_LOCATOR_SHA256='2cf76877a14c8f3e8e3b243c346545a1b6d6fd17d913560f3ef6970c81b83783'
E1_ARCHIVED_PAYLOAD_RECEIPT_SHA256='931e73b91998dab23b8773312e91accdf4e53bdba8a26bd029eb4e25a518b446'
E1_ARCHIVED_PAYLOAD_ARCHIVE_NAME='LAMOST_E1_WRAPUP_20261024T080232_571618+0000.zip'
E1_ARCHIVED_PAYLOAD_ARCHIVE_SHA256='bd4834a15d491844203ff7baf07b3b21dcdf972de97af68a744d8d2c042e7d34'
E1_ARCHIVED_PAYLOAD_ARCHIVE_STAT5=(66305,2441647,4976984354,1792829285346854837,1792829285346854837)
E1_ARCHIVED_PAYLOAD_COUNTS={'.joblib':24,'.npz':24}
E1_ARCHIVED_PAYLOAD_FILE_COUNT=48
E3_RESTORE_MANIFEST='runtime_20261025/manifests/incidents/e3_original_npz_container_restoration_20261025.json'
E3_RESTORE_MANIFEST_SHA256='97d89b0c744c870abfe6c6a487a907c597c9d47dbf034066e15b827dae1e1c81'
SERIALIZATION_INCIDENT='runtime_20261025/manifests/incidents/serialization_validation_20261025/incident.json'
SERIALIZATION_INCIDENT_SHA256='5c75adc4c8de1859a0283bd9caece41c69278a1fb5671eb09335ca733e7b555a'

def _relative_member(value,root):
 if not value:return None
 try:return Path(value).resolve().relative_to(Path(root).resolve()).as_posix()
 except ValueError:return None

def _curated_npz_restoration(path,root,expected_sha256=None):
 path=Path(path);raw=path.read_bytes();source_sha=sha_bytes(raw)
 if expected_sha256 and source_sha!=expected_sha256:raise EvidenceError('E3 NPZ restoration provenance source SHA mismatch: '+str(path))
 doc=json.loads(raw);files=[]
 for f in doc.get('files',[]):
  av=f.get('array_validation',{})
  files.append({'task_key':f.get('task_key'),'current_member':_relative_member(f.get('current_path'),root),'current_sha256':f.get('current_sha256'),'restored_member':_relative_member(f.get('restored_path'),root),'restored_sha256':f.get('restored_sha256'),'source_candidate_member':_relative_member(f.get('source_candidate_path'),root),'source_candidate_sha256':f.get('source_candidate_sha256'),'support_baseline_member':_relative_member(f.get('support_diagnostic_baseline_path'),root),'support_baseline_sha256':f.get('support_diagnostic_baseline_sha256'),'classification':f.get('classification'),'array_validation':{k:av.get(k) for k in ('old_zip_crc','current_zip_crc','fallback_mask_omitted_only','fallback_mask_shape','fallback_true_count','member_order_preserved','original_members','current_members','arrays') if k in av}})
 out={'schema_version':'lamost-e3-npz-restoration-provenance/curated-1','source_manifest_sha256':source_sha,'created_utc':doc.get('created_utc'),'experiment':doc.get('experiment'),'audit_sha256':doc.get('audit_sha256'),'engine_code_sha256':doc.get('engine_code_sha256'),'restoration_code_sha256':doc.get('restoration_code_sha256'),'restoration_rule':doc.get('restoration_rule'),'scope':doc.get('scope'),'fit_predict_calibrate_generate_performed':doc.get('fit_predict_calibrate_generate_performed'),'live_artifacts_modified':doc.get('live_artifacts_modified'),'models_loaded':doc.get('models_loaded'),'issues_csv_member':_relative_member(doc.get('issues_csv_path'),root),'issues_csv_sha256':doc.get('issues_csv_sha256'),'files':files,'curation_note':'Derived allowlisted scientific provenance view. Absolute operational request/result paths, process receipts, and unrelated operational fields are excluded; retained source SHA-256 identifies the exact original manifest.'}
 return (json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()

def _curated_serialization_incident(path,root,expected_sha256=None):
 path=Path(path);raw=path.read_bytes();source_sha=sha_bytes(raw)
 if expected_sha256 and source_sha!=expected_sha256:raise EvidenceError('serialization incident source SHA mismatch: '+str(path))
 d=json.loads(raw);allow=('incident_id','observed_utc','classification','invalid_phase','invalid_phase_elapsed_seconds','invalid_validation_peak_rss_kib','model_fit_completed_and_artifact_saved_before_invalid_validation','models_refitted_for_recovery','selected_trial','selected_trial_peak_rss_kib','single_copy_validation_status','single_copy_validation_seconds','single_copy_validation_peak_rss_kib','test_predictions_generated_during_repair','resource_policy_changed','trial_budgets_domains_seeds_memberships_changed','source_db_checkpoints_preserved','checkpoint_summary_fields','checkpoint_summary_metadata_completed_from_independently_validated_model','other_task_completed_trial0_scientific_rss_failure_preserved','other_task_resume_pending_trial_number','original_pipeline_sha256','repair','validation','affected_dependent_unavailability_states_superseded','other_affected_task','task_key')
 out={'schema_version':'lamost-serialization-validation-incident/curated-1','source_incident_sha256':source_sha,**{k:d[k] for k in allow if k in d}}
 migrations=path.parent/d.get('checkpoint_migrations','')
 if migrations.is_file():out['checkpoint_migrations_sha256']=sha_file(migrations)
 out['curation_note']='Allowlisted scientific/resource and validation facts retained. Process identifiers, private receipts, worker paths, dequeue/cleanup records, and non-public process inventory are excluded.'
 return (json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()

def _e3_incident_expected(root,overrides=None):
 expected={E3_RESTORE_MANIFEST:E3_RESTORE_MANIFEST_SHA256,SERIALIZATION_INCIDENT:SERIALIZATION_INCIDENT_SHA256}
 if overrides:expected.update(overrides)
 return expected

def _small_e3_incident_summary(root,overrides=None):
 expected=_e3_incident_expected(root,overrides);rpath=Path(root)/E3_RESTORE_MANIFEST;ipath=Path(root)/SERIALIZATION_INCIDENT
 if not rpath.is_file() and not ipath.is_file():return None
 rdoc=json.loads(_curated_npz_restoration(rpath,root,expected[E3_RESTORE_MANIFEST]).decode()) if rpath.is_file() else None
 idoc=json.loads(_curated_serialization_incident(ipath,root,expected[SERIALIZATION_INCIDENT]).decode()) if ipath.is_file() else None
 return (json.dumps({'schema_version':'lamost-e3-incident-provenance-summary/1','npz_restoration':rdoc,'serialization_validation_incident':idoc},indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()


def _curated_e4_weight_schema(path,expected_source_sha256=None):
 path=Path(path);raw=path.read_bytes();source_sha=sha_bytes(raw)
 if expected_source_sha256 and expected_source_sha256.get(str(path.resolve())) not in (None,source_sha):raise EvidenceError('E4 weight-schema provenance source SHA mismatch: '+str(path))
 d=json.loads(raw);a=d.get('amendment',{})
 allow=('amendment_id','observed_utc','scope','reason','affected_cohort_helpers_to_regenerate','dependent_unavailability_records_reset','invalid_fit_attempt_tasks_to_supersede','invalid_terminal_fit_failures_superseded','original_frozen_utc_unchanged','science_and_phase_worker_engine_sha256_unchanged','source_before_sha256','source_after_sha256','task_plan_sha256_unchanged','unaffected_weighted_ros_smote_helpers_retained','validation')
 out={'schema_version':'lamost-e4-weight-schema-incident/curated-1','source_manifest_sha256':source_sha,'observed_utc':d.get('observed_utc'),'bootstrap':d.get('bootstrap'),'amendment':{k:a[k] for k in allow if k in a},'cohort_container_supersessions':d.get('cohort_container_supersessions',[]),'dependent_unavailability_reset_keys':d.get('dependent_unavailability_reset_keys',[]),'invalid_fit_keys':d.get('invalid_fit_keys',[]),'scientific_trial_history_row_count':d.get('scientific_trial_history_rows'),'curation_note':'Allowlisted scientific correction and evidence hashes. Raw private evidence path and operational receipts are intentionally omitted and retained on EC2.'}
 return (json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()

def _curated_svm_incident(path,expected_source_sha256=None):
 path=Path(path);raw=path.read_bytes();source_sha=sha_bytes(raw)
 if expected_source_sha256 and expected_source_sha256.get(str(path.resolve())) not in (None,source_sha):raise EvidenceError('SVM incident source SHA mismatch: '+str(path))
 d=json.loads(raw)
 allow=('incident_id','observed_utc','classification','error_signature','scientific_method_definition','SVM_source_sha256','newSVM_engine_sha256','nonSVM_engine_sha256_unchanged','affected_invalid_control_evaluations','affected_invalid_fit_tasks','requeued_keys','ordinary_terminal_tasks_requeued','E1_orE2fits_started','scientific_workers_signaled','resource_limits_unchanged','original_freeze_utc_unchanged','plan_sha256_unchanged','valid_control_models_preserved_sha256','auditor_sha256','validation')
 out={'schema_version':'lamost-svm-margin-api-incident/curated-1','source_manifest_sha256':source_sha,**{k:d[k] for k in allow if k in d},'curation_note':'Scientific defect, affected comparisons, validation, and code/model hashes retained; private process receipts are excluded.'}
 return (json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()

PUBLIC_RESOURCE_REVIEW_SHA256={
 'runtime_20261025/staging/e4_rf_fit_reservation_review_20261026/E4_RF_FIT_RESERVATION_RESOURCE_REVIEW_20261026.json':'2e6356dac0be320eb5e57c3537b3c4dff01e8943d5f1490424f117e4b332e1b6',
 'runtime_20261025/staging/resource_followup_e5_e4_rf_20261026/E5_E4_RF_RESOURCE_FOLLOWUP_20261026.json':'9884af26a84d04e5be913d651d36f9b055dda7613a8e2f95b73a137626de4754',
 'runtime_20261025/staging/nonrf_heavy_resource_readiness_20261026/HEAVY_METHOD_RESOURCE_READINESS_AUDIT_20261026.json':'b3530fd93a17095fa6d3e8b7071b4df943cceea829ecad4415513ac06bf11c49',
}
RESOURCE_REVIEW_PRIVATE_KEYS={'pid','pgid','argv','cmdline','startticks','processstartticks','workerpid','controllerpid','ownerpid','auth','authorization','cleanup','cleanupreceipt','requestpath','resultpath','logpath','processreceipt'}
def _assert_public_resource_review(raw,source_path):
 try:doc=json.loads(raw)
 except Exception as exc:raise EvidenceError('public resource review is not valid JSON: '+str(source_path)) from exc
 def walk(value):
  if isinstance(value,dict):
   for key,item in value.items():
    normalized=''.join(ch for ch in str(key).lower() if ch.isalnum())
    if normalized in RESOURCE_REVIEW_PRIVATE_KEYS:raise EvidenceError('resource review contains excluded operational key '+str(key))
    walk(item)
  elif isinstance(value,list):
   for item in value:walk(item)
 walk(doc)
 return doc

def _add_resource_review_evidence(root,out,expected_source_sha256=None,records=None,required=False):
 root=Path(root);expected_source_sha256=expected_source_sha256 or {}
 records=records if records is not None else []
 for relative,pinned_sha in PUBLIC_RESOURCE_REVIEW_SHA256.items():
  member_path=PurePosixPath(relative)
  if len(member_path.parts)<2 or member_path.parts[0]!='runtime_20261025':raise EvidenceError('unsafe pinned resource-review member path')
  path=root.joinpath(*member_path.parts)
  if not path.is_file():
   if required:raise EvidenceError('required pinned public resource review is missing: '+str(path))
   continue
  raw=path.read_bytes();observed=sha_bytes(raw)
  if observed!=pinned_sha:raise EvidenceError('pinned public resource review changed: '+str(path))
  reviewed=expected_source_sha256.get(str(path.resolve()))
  if reviewed not in (None,observed):raise EvidenceError('reviewed public resource review SHA mismatch: '+str(path))
  _assert_public_resource_review(raw,path)
  out.append(Entry(raw,member_path.as_posix(),'public_scientific_resource_admission_review'))
  records.append({'source_member':member_path.as_posix(),'archive_member':member_path.as_posix(),'source_sha256':observed,'archive_sha256':observed,'bytes':len(raw),'curation':'exact_bytes_pinned_public_scientific_resource_review'})
 return records

def _add_public_provenance(root,runtime,out,expected_source_sha256=None):
 records=[]
 def add_raw(path,member,category):
  path=Path(path);source_sha=sha_file(path)
  if expected_source_sha256 and expected_source_sha256.get(str(path.resolve())) not in (None,source_sha):raise EvidenceError('reviewed public provenance source SHA mismatch: '+str(path))
  bound=dict(expected_source_sha256 or {});bound[str(path.resolve())]=source_sha
  entry=archive_json_entry(path,member,category,root,bound);out.append(entry)
  payload=entry.source if isinstance(entry.source,bytes) else Path(entry.source).read_bytes()
  records.append({'source_member':path.relative_to(root).as_posix(),'archive_member':member,'source_sha256':source_sha,'archive_sha256':sha_bytes(payload),'curation':'archive_json_entry'})
 def add_curated(path,member,category,fn):
  path=Path(path);source_sha=sha_file(path)
  if expected_source_sha256 and expected_source_sha256.get(str(path.resolve())) not in (None,source_sha):raise EvidenceError('reviewed incident source SHA mismatch: '+str(path))
  bound=dict(expected_source_sha256 or {});bound[str(path.resolve())]=source_sha
  data=fn(path,bound);out.append(Entry(data,member,category))
  records.append({'source_member':path.relative_to(root).as_posix(),'archive_member':member,'source_sha256':source_sha,'curation':'allowlisted_source_sha_bound_projection','archive_sha256':sha_bytes(data)})
 mf=runtime/'manifests'
 _add_resource_review_evidence(root,out,expected_source_sha256,records,required=(runtime/'source'/'admission_evidence.py').is_file())
 for name in ('baseline_identity_boundary_audit.json','concurrency_user_authorization_20261025.json'):
  path=mf/name
  if path.is_file():add_raw(path,'runtime_20261025/manifests/'+name,'public_scientific_provenance')
 for path in sorted(mf.glob('freeze_before_*.json')):
  add_raw(path,'runtime_20261025/manifests/'+path.name,'frozen_scientific_policy_history')
 e4=mf/'incidents/e4_weight_schema_20261025.json'
 if e4.is_file():add_curated(e4,'runtime_20261025/manifests/incidents/e4_weight_schema_20261025_summary.json','curated_E4_weight_schema_incident',_curated_e4_weight_schema)
 svm=mf/'incidents/svm_native_margin_api_20261026.json'
 if svm.is_file():add_curated(svm,'runtime_20261025/manifests/incidents/svm_native_margin_api_20261026_summary.json','curated_SVM_native_margin_incident',_curated_svm_incident)
 omitted={'scope':'Only the three hash-pinned public scientific resource-review JSONs listed in included are selected from runtime staging; all other staging files, operational incident holds, service/process receipts, and private logs are retained on EC2 and excluded from the public archive.','examples':['staging/** except the three explicit public resource-review members','incidents/*_hold*.json','incidents/serialization_validation_20261025/dequeue_hold_resolved.json','logs/operational/**']}
 manifest={'schema_version':'lamost-public-execution-provenance/1','included':records,'retained_only_omissions':omitted}
 out.append(Entry((json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode(),'runtime_20261025/manifests/public_scientific_provenance_manifest.json','public_scientific_provenance_inventory'))

def collect_full(root,runtime,readme,public,review_proof=None,expected_source_sha256=None,incident_hash_overrides=None,cold_store=None,registry_records=None,review_manifest=None):
 out=[]
 out.extend(curated_tree_entries(root/'project','project','verified_frozen_project',root,allow_e1_supervisor=True,expected_source_sha256=expected_source_sha256))
 out.extend(curated_tree_entries(root/'e1_wrapup_20261024','e1_wrapup_20261024','frozen_E1_final_tables_report',root,expected_source_sha256=expected_source_sha256))
 out.extend(curated_tree_entries(root/'e1_recovery_20261024','e1_recovery_20261024','stopped_early_E1_recovery_supplement',root,expected_source_sha256=expected_source_sha256))
 from cold_finalizer_adapter import e1_locator_archive_entries
 e1_payload_entries,e1_payload_provenance=e1_locator_archive_entries(
  __import__(__name__),root,root/E1_ARCHIVED_PAYLOAD_LOCATOR,
  E1_ARCHIVED_PAYLOAD_LOCATOR_SHA256,E1_ARCHIVED_PAYLOAD_ARCHIVE_SHA256,
  E1_ARCHIVED_PAYLOAD_ARCHIVE_STAT5,E1_ARCHIVED_PAYLOAD_RECEIPT_SHA256,
  E1_ARCHIVED_PAYLOAD_ARCHIVE_NAME,expected_file_count=E1_ARCHIVED_PAYLOAD_FILE_COUNT,
  expected_extension_counts=E1_ARCHIVED_PAYLOAD_COUNTS)
 out.extend(e1_payload_entries)
 out.append(Entry(e1_payload_provenance,'runtime_20261025/manifests/e1_recovery_archived_payload_provenance.json','E1_recovery_archived_payload_provenance'))
 from frozen_e1_primary_archive import primary_e1_archive_entries, LOCATOR_REL, LOCATOR_SHA256
 locator_path=runtime/LOCATOR_REL
 locator_bytes=locator_path.read_bytes()
 if sha_bytes(locator_bytes)!=LOCATOR_SHA256:raise EvidenceError('frozen E1 primary locator bytes differ from pinned SHA')
 primary_entries,primary_provenance=primary_e1_archive_entries(__import__(__name__),root,runtime)
 out.extend(primary_entries)
 out.append(Entry(primary_provenance,'runtime_20261025/manifests/e1_primary_archive_provenance.json','frozen_E1_primary_archive_availability'))
 out.append(Entry(locator_bytes,'runtime_20261025/'+LOCATOR_REL,'frozen_E1_primary_archive_locator'))
 for p in iterfiles(root/'e2_20261024',skip_logs=True):out.append(archive_json_entry(p,'e2_20261024/'+p.relative_to(root/'e2_20261024').as_posix(),'E2_original_reconstructed_diagnostics',root,expected_source_sha256) if p.suffix.lower()=='.json' else ent(p,'e2_20261024/'+p.relative_to(root/'e2_20261024').as_posix(),'E2_original_reconstructed_diagnostics',root))
 for n in ('freeze.json','startup_audit.json','authorization_and_decisions.json','tasks.json','plan_summary.json','plan_amendments.json','E3_MANIFEST.json','E4_MANIFEST.json','E5_MANIFEST.json','E6_MANIFEST.json','COLD_VERIFIER_HISTORY_20261028.json'): 
  p=runtime/'manifests'/n
  if p.is_file():out.append(ent(p,'runtime_20261025/manifests/'+n,'frozen_execution_manifest',root))
 _add_public_provenance(root,runtime,out,expected_source_sha256)
 incident_expected=_e3_incident_expected(root,incident_hash_overrides)
 restoration_path=root/E3_RESTORE_MANIFEST
 if restoration_path.is_file():out.append(Entry(_curated_npz_restoration(restoration_path,root,incident_expected[E3_RESTORE_MANIFEST]),E3_RESTORE_MANIFEST,'curated_E3_container_restoration_provenance'))
 serialization_path=root/SERIALIZATION_INCIDENT
 if serialization_path.is_file():out.append(Entry(_curated_serialization_incident(serialization_path,root,incident_expected[SERIALIZATION_INCIDENT]),'runtime_20261025/manifests/incidents/serialization_validation_20261025/incident_summary.json','curated_serialization_validation_incident'))
 add=lambda p,m,c:out.append(ent(p,m,c,root)) if Path(p).is_file() else None
 if review_proof and review_proof.get('master_index_snapshot_path'):add(review_proof['master_index_snapshot_path'],'runtime_20261025/master_index.json','immutable_reviewed_master_index')
 else:add(runtime/'master_index.json','runtime_20261025/master_index.json','derived_master_index')
 for p in iterfiles(runtime/'review_audit'):add(p,'runtime_20261025/review_audit/'+p.relative_to(runtime/'review_audit').as_posix(),'internal_report_review_evidence')
 for n in ('REPORT_READY_FOR_AUDIT.json','REPORT_AUDIT_RECEIPT.json'):add(runtime/n,'runtime_20261025/'+n,'internal_report_review_evidence')
 for p in iterfiles(runtime/'manifests/imported_selections'):add(p,'runtime_20261025/manifests/imported_selections/'+p.relative_to(runtime/'manifests/imported_selections').as_posix(),'imported_E1_selected_parameters')
 for base,member_prefix,label in ((runtime/'source','source','source'),(runtime/'tests','tests','engineering_checks'),(runtime/'cache','cache','roles_and_test_cache'),(runtime/'artifacts','artifacts','scientific_models_data_outcomes_trials')):
  for p in iterfiles(base):
   if _is_private_e6_phase_receipt(p): continue
   member='runtime_20261025/'+member_prefix+'/'+p.relative_to(base).as_posix()
   out.append(archive_json_entry(p,member,label,root,expected_source_sha256) if p.suffix.lower()=='.json' else ent(p,member,label,root))
 out.append(Entry(e6_private_phase_receipt_manifest(runtime,registry_records),E6_PRIVATE_PHASE_RECEIPT_MANIFEST,'curated_private_E6_phase_receipt_exclusion_manifest'))
 # Replace cold-stored runtime model paths with logical ZIP-member sources. The archived
 # model bytes remain in the existing BUILDING ZIP and are represented by verified aliases.
 cold_projection_bytes=None
 if cold_store is not None:
  from cold_finalizer_adapter import cold_artifact_entries
  cold_entries,cold_projection_bytes=cold_artifact_entries(__import__(__name__),root,runtime,cold_store,registry_records,expected_source_sha256,review_manifest)
  cold_members=set(cold_entries)
  out=[e for e in out if e.member not in cold_members]
  out.extend(cold_entries.values())
  out.append(Entry(cold_projection_bytes,'runtime_20261025/manifests/cold_archived_artifact_members.json','immutable_cold_model_membership_snapshot'))
 # Recover scientific selection histories otherwise hidden under private attempt trees.
 from archive_scientific_histories import collect_scientific_attempt_entries
 history_entries,history_manifest=collect_scientific_attempt_entries(root,runtime,json.loads(public)['tasks'],archive_json_entry,Entry,sanitize_operational_json,expected_source_sha256)
 out.extend(history_entries)
 out.append(Entry(history_manifest,'runtime_20261025/scientific_attempt_archive_manifest.json','scientific_attempt_history_manifest'))
 for p in iterfiles(runtime/'reports',skip_logs=True):
  if p.name in {'report.lock','finalize.lock','PORTABLE_TEST_RUN_RECEIPT.json'} or p.name.endswith('.tmp'):continue
  if {'portable_test_history','finalization_attempt_history'} & set(p.relative_to(runtime/'reports').parts):continue
  member='runtime_20261025/reports/'+p.relative_to(runtime/'reports').as_posix()
  if p.suffix.lower()=='.json':out.append(archive_json_entry(p,member,'validated_reports_tables_figures',root,expected_source_sha256))
  elif p.suffix.lower()=='.csv':out.extend(_report_csv_archive_entries(p,member,'validated_reports_tables_figures',root,expected_source_sha256))
  else:add(p,member,'validated_reports_tables_figures')
 for n in ('AIRBAG_STATE.md','AIRBAG_OPERATIONS.md','RUN_RESUME_REPRODUCE.md','FINAL_REVIEW_RUNBOOK.md','FINAL_COMPLETION_EVIDENCE_CHECKLIST.md'):add(runtime/n,'runtime_20261025/'+n,'resume_reproduce')
 out.append(Entry(public,'runtime_20261025/public_registry.json','sanitized_registry'));out.append(Entry(public,'runtime_20261025/registry.json','sanitized_terminal_report_registry'));out.append(Entry(readme,'README_ARCHIVE.md','archive_readme'))
 return out

RESTORE=r'''#!/usr/bin/env python3
import errno,hashlib,json,os,shutil,tempfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
LINK_FALLBACK_ERRNOS={errno.EXDEV,errno.EPERM,errno.EACCES,getattr(errno,'ENOTSUP',errno.EPERM),getattr(errno,'EOPNOTSUPP',errno.EPERM),getattr(errno,'EMLINK',errno.EPERM),getattr(errno,'ENOSYS',errno.EPERM)}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def safe(n):
 p=PurePosixPath(n)
 if p.is_absolute() or any(x in ('','..','.') for x in p.parts) or '\\' in n:raise ValueError('unsafe archive path')
 q=(ROOT/Path(*p.parts)).resolve()
 if ROOT.resolve() not in q.parents:raise ValueError('path escaped extraction root')
 return q
def restore_one(src,dst,size,digest):
 if dst.exists():
  if dst.is_file() and dst.stat().st_size==size and sha(dst)==digest:return 'already_present'
  raise FileExistsError('will not overwrite different alias')
 try:
  os.link(src,dst)
 except OSError as exc:
  if exc.errno not in LINK_FALLBACK_ERRNOS:raise
  fd,tmp=tempfile.mkstemp(dir=dst.parent,prefix='.restore_alias_')
  try:
   with os.fdopen(fd,'wb') as out,src.open('rb') as inp:shutil.copyfileobj(inp,out,4*1024*1024);out.flush();os.fsync(out.fileno())
   if sha(Path(tmp))!=digest or Path(tmp).stat().st_size!=size:raise ValueError('restored copy SHA check failed')
   if dst.exists():
    if dst.is_file() and dst.stat().st_size==size and sha(dst)==digest:return 'already_present'
    raise FileExistsError('will not overwrite different alias')
   os.replace(tmp,dst)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
  mode='copied'
 else:mode='hardlinked'
 if not dst.is_file() or dst.stat().st_size!=size or sha(dst)!=digest:
  if dst.exists() and os.path.samefile(src,dst):dst.unlink()
  raise ValueError('restored alias SHA check failed')
 return mode
def main():
 d=json.loads((ROOT/'archive_aliases.json').read_text());done=[];hardlinked=0;copied=0
 for a in d.get('aliases',[]):
  src=safe(a['canonical_path']);dst=safe(a['alias_path']);size=int(a['bytes']);h=a['sha256']
  if not src.is_file() or src.stat().st_size!=size or sha(src)!=h:raise ValueError('canonical SHA check failed')
  dst.parent.mkdir(parents=True,exist_ok=True)
  mode=restore_one(src,dst,size,h);hardlinked+=mode=='hardlinked';copied+=mode=='copied';done.append(a['alias_path'])
 print(json.dumps({'restored_aliases':len(done),'hardlinked_aliases':hardlinked,'copied_aliases':copied},indent=2))
if __name__=='__main__':main()
'''

def size(e):return len(e.source) if isinstance(e.source,bytes) else Path(e.source).stat().st_size
def hashent(e):return sha_bytes(e.source) if isinstance(e.source,bytes) else sha_file(e.source)
def stream(e):return io.BytesIO(e.source) if isinstance(e.source,bytes) else Path(e.source).open('rb')
def dedup(entries,expected_source_sha256=None):
 paths=set();hashes={};physical=[];aliases=[];expected_source_sha256=expected_source_sha256 or {}
 for e in sorted(entries,key=lambda x:x.member):
  if e.member in paths:raise ValueError('duplicate ZIP member '+e.member)
  paths.add(e.member);n=size(e);h=hashent(e)
  source_path=None if isinstance(e.source,bytes) else str(Path(e.source).resolve())
  if source_path in expected_source_sha256 and h!=expected_source_sha256[source_path]:raise EvidenceError('reviewed source changed before packaging: '+source_path)
  k=(n,h)
  if k in hashes:aliases.append({'alias_path':e.member,'canonical_path':hashes[k],'bytes':n,'sha256':h,'category':e.category})
  else:hashes[k]=e.member;physical.append((e,n,h))
 return physical,aliases
def compression(n):return zipfile.ZIP_STORED if Path(n).suffix.lower() in {'.zip','.npz','.npy','.parquet','.joblib','.png','.jpg','.jpeg','.gz','.sqlite3'} else zipfile.ZIP_DEFLATED
def prepare(entries,generated,omissions,expected_source_sha256=None,review_proof=None):
 phys,aliases=dedup(entries,expected_source_sha256);ad={'schema_version':'lamost-aliases/1','aliases':aliases,'restore':'extract then run python3 restore_archive_aliases.py; hashes verified and output confined to extraction root'};ab=(json.dumps(ad,indent=2,sort_keys=True)+'\n').encode()
 generated=[*generated,Entry(ab,'archive_aliases.json','alias_manifest'),Entry(RESTORE.encode(),'restore_archive_aliases.py','safe_alias_restorer')]
 if review_proof is not None:generated.append(Entry((json.dumps(review_proof,indent=2,sort_keys=True)+'\n').encode(),'REPORT_REVIEW_PROOF.json','internal_report_review_proof'))
 gp,ga=dedup(generated)
 if ga:raise RuntimeError('unexpected duplicate generated member')
 allp=phys+gp;manifest={'schema_version':'lamost-member-manifest/1','created_utc':now(),'unique_physical_members':[{'path':e.member,'bytes':n,'sha256':h,'category':e.category} for e,n,h in allp],'alias_manifest_sha256':sha_bytes(ab),'alias_count':len(aliases),'alias_bytes_elided':sum(x['bytes'] for x in aliases),'omissions':omissions,'report_review_proof':review_proof,'self_reference':'manifest covers all physical members preceding itself; archive size/SHA/CRC are in external receipt'}
 mb=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode();allp.append((Entry(mb,'archive_member_manifest.json','member_manifest'),len(mb),sha_bytes(mb)))
 if len({x[0].member for x in allp})!=len(allp):raise ValueError('archive member collision')
 return allp,aliases,manifest
def zipwrite(path,entries,generated,omissions,min_free=512*1024*1024,expected_source_sha256=None,review_proof=None):
 members,aliases,manifest=prepare(entries,generated,omissions,expected_source_sha256,review_proof);need=sum(n for _,n,_ in members)+min_free;free=shutil.disk_usage(path.parent).free
 if free<need:raise InsufficientSpace(need,free)
 tmp=path.with_name(path.name+f'.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}')
 try:
  with tmp.open('xb') as raw:
   with zipfile.ZipFile(raw,'w',allowZip64=True) as z:
    for e,n,h in members:
     info=zipfile.ZipInfo(e.member,date_time=(2026,10,25,0,0,0));info.compress_type=compression(e.member);info.external_attr=(0o100644&0xffff)<<16
     copied=0;digest=hashlib.sha256()
     with stream(e) as src,z.open(info,'w',force_zip64=True) as dst:
      for chunk in iter(lambda:src.read(4*1024*1024),b''):
       copied+=len(chunk);digest.update(chunk);dst.write(chunk)
     if copied!=n or digest.hexdigest()!=h:raise EvidenceError('archive source mutated during streaming: '+e.member)
   raw.flush();os.fsync(raw.fileno())
  with zipfile.ZipFile(tmp) as z:
   if z.testzip() is not None:raise EvidenceError('ZIP CRC failure')
   required={'archive_member_manifest.json','archive_aliases.json','restore_archive_aliases.py'}
   if review_proof is not None:required.add('REPORT_REVIEW_PROOF.json')
   if not required.issubset(z.namelist()):raise EvidenceError('ZIP manifest/restore/review files missing')
   if review_proof is not None and json.loads(z.read('REPORT_REVIEW_PROOF.json'))!=review_proof:raise EvidenceError('embedded review proof differs from accepted proof')
  h=sha_file(tmp);n=tmp.stat().st_size
  if path.exists():raise FileExistsError(str(path))
  os.link(tmp,path);tmp.unlink();st=path.stat()
  return {'path':str(path),'bytes':n,'sha256':h,'mtime_ns':st.st_mtime_ns,'zip_crc_passed':True,'member_count':len(members),'alias_count':len(aliases),'alias_bytes_elided':sum(x['bytes'] for x in aliases),'uncompressed_bytes':sum(n for _,n,_ in members),'member_manifest_sha256':sha_bytes((json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()),'report_review_proof':review_proof}
 except Exception:
  try:tmp.unlink()
  except FileNotFoundError:pass
  raise
def _small_entries(root,runtime,full,blocker,small_path,review_proof=None,incident_hash_overrides=None,expected_source_sha256=None):
 e=[];add=lambda p,m,c:e.append(ent(p,m,c,root)) if Path(p).is_file() else None;rd=runtime/'reports'
 for p in small_report_files(rd):
  if _is_private_e6_phase_receipt(p): continue
  member='reports/'+p.relative_to(rd).as_posix()
  if p.suffix.lower()=='.json':e.append(archive_json_entry(p,member,'reports_tables_figures',root,expected_source_sha256))
  elif p.suffix.lower()=='.csv':e.extend(_report_csv_archive_entries(p,member,'reports_tables_figures',root,expected_source_sha256))
  else:add(p,member,'reports_tables_figures')
 e.append(Entry(e6_private_phase_receipt_manifest(runtime),E6_PRIVATE_PHASE_RECEIPT_MANIFEST,'curated_private_E6_phase_receipt_exclusion_manifest'))
 for n in ('E1_WRAPUP.md','E1_frozen_cells_765.csv','E1_method_budget_summary_153.csv','E1_recovery_cutoff_91.csv','E1_learning_curves_all_budgets.html'):add(root/'e1_wrapup_20261024'/n,'E1/'+n,'frozen_E1_report_tables')
 for p in iterfiles(root/'e2_20261024',skip_logs=True):
  if p.suffix.lower() in {'.csv','.md','.html','.png','.json','.txt'} and (p.parent==root/'e2_20261024' or p.name=='E2_RECONSTRUCTION_AMENDMENT.md'):add(p,'E2/'+p.relative_to(root/'e2_20261024').as_posix(),'E2_report_tables')
 for n in ('freeze.json','plan_summary.json','startup_audit.json','authorization_and_decisions.json','plan_amendments.json','E3_MANIFEST.json','E4_MANIFEST.json','E5_MANIFEST.json','E6_MANIFEST.json'):add(runtime/'manifests'/n,'manifests/'+n,'execution_manifest')
 if review_proof and review_proof.get('master_index_snapshot_path'):add(review_proof['master_index_snapshot_path'],'master_index.json','immutable_reviewed_master_index')
 else:add(runtime/'master_index.json','master_index.json','derived_master_index')
 if review_proof:
  add(review_proof.get('review_manifest_path',''),'REPORT_REVIEW_MANIFEST.json','internal_report_review_manifest')
  add(runtime/'REPORT_AUDIT_RECEIPT.json','REPORT_AUDIT_RECEIPT.json','internal_report_review_receipt')
  add(runtime/'REPORT_READY_FOR_AUDIT.json','REPORT_READY_FOR_AUDIT.json','internal_report_review_state')
 add(runtime/'FINAL_REVIEW_RUNBOOK.md','FINAL_REVIEW_RUNBOOK.md','internal_review_runbook')
 add(runtime/'FINAL_COMPLETION_EVIDENCE_CHECKLIST.md','FINAL_COMPLETION_EVIDENCE_CHECKLIST.md','completion_evidence_checklist')
 incident_summary=_small_e3_incident_summary(root,incident_hash_overrides)
 if incident_summary is not None:e.append(Entry(incident_summary,'E3_INCIDENT_PROVENANCE_SUMMARY.json','curated_E3_incident_provenance'))
 for rel in ('project/benchmark/results/master_run_config.json','project/benchmark/dependencies.freeze.txt','project/benchmark/protocol_source.txt'):add(root/rel,'frozen_E1/'+Path(rel).name,'protocol_config_summary')
 if full:
  loc = (
   f"Full archive on EC2: {full['path']}\n"
   f"Size: {full['bytes']} bytes\n"
   f"SHA-256: {full['sha256']}\n"
   "ZIP CRC verification: passed.\n\n"
   "From laptop PowerShell, copy this compact ZIP using:\n"
   f'scp w7-ec2:{small_path} "D:\\LAMOST_Overall_EC2_Handoff_20261023"\n\n'
   "The overall project remains delivery-pending until this laptop copy is verified.\n"
  )
 else:
  loc = f"Full archive not built: {blocker or 'unknown blocker'}. Compact reports remain on EC2. See EC2_COMPLETE_DELIVERY_PENDING.json.\n"
 e.append(Entry(loc.encode(),'FULL_ARCHIVE_LOCATION.md','full_archive_location'))
 reproduce = """# Reproduce and resume

**Archive safety:** This extracted package is a read-only scientific reproduction snapshot. Its registry.json and public_registry.json files are sanitized terminal report projections, not the controller database. Do not initialize, watchdog, or resume the experiment controller from an extracted archive, and do not rerun terminal cells from it. Descriptive report regeneration is supported from the extraction root. Operational resume applies only to the original EC2 project directory, using its retained controller SQLite state, verified ownership lock, and live-process checks.

The full archive includes the verified frozen E1 project tree and baseline, final E1 report/tables, curated stopped recovery supplement, E2 original/reconstructed provenance, and all available E3-E6 runtime artifacts. The original E1 ZIP remains preserved on EC2 with its verified SHA-256 but is not embedded because it contains excluded operational receipts. From the extracted archive root, run python3 restore_archive_aliases.py to restore deduplicated paths with hash and extraction-root checks. The restorer prefers same-filesystem hardlinks; it falls back to a verified copy only when links are unsupported, and refuses to overwrite a different existing file. runtime_20261025/registry.json is a sanitized terminal report projection used for descriptive regeneration; it is not the original live controller registry or SQLite database. On EC2, from the extraction root, regenerate descriptive tables by running `export PYTHONPATH="$PWD/venv/lib/python3.12/site-packages:/home/ubuntu/.local/lib/python3.12/site-packages:/usr/lib/python3/dist-packages"` followed by `"$PWD/venv/bin/python" runtime_20261025/source/report_cli.py`; this does not fit, generate, or evaluate models. Runtime source, tests, cache, and artifacts are stored at their native runtime_20261025/source, runtime_20261025/tests, runtime_20261025/cache, and runtime_20261025/artifacts paths; no rename map is needed.

The E3 NPZ restoration manifest and serialization-validation incident are included as allowlisted, privacy-curated provenance with source SHA-256 values. The compact incident summary records all nine current/restored container hashes, array/CRC checks, and the validation resource history; operational request/result receipts are omitted. Restored original E3 NPZ containers are under runtime_20261025/artifacts/_restored_original_e3_containers/. The included final report and costs.csv/cost_summary.csv are validated historical observations. Private phase-supervision receipts and phase JSON were excluded or curated, so regenerating from this archive may not reconstruct every historical phase cost byte-for-byte. The calibration replay raw phase ledger and private beacon contain process IDs/start ticks and remain only under EC2 logs/operational; the archive carries the sanitized supervision receipt and qualification with the ledger SHA and measured per-fit evidence. Preserve the supplied validated reports and cost tables; if regenerating, work on an extraction copy. E1/E2 fixed-test outcomes were already observed before E3-E6. No bootstrap or significance test was used. The omitted historical E1 fitted classifiers and per-test-row prediction arrays are not restored. Read reports/FINAL_SCIENTIFIC_REPORT.md, manifests/freeze.json, manifests/tasks.json, and included source/dependency instructions.
"""
 e.append(Entry(reproduce.encode(),'RUN_RESUME_REPRODUCE.md','reproduction_instructions'))
 return e
def unique_path(directory,prefix,stamp,suffix):
 p=directory/f'{prefix}_{stamp}{suffix}';i=1
 while p.exists():p=directory/f'{prefix}_{stamp}_{i}{suffix}';i+=1
 return p
def package_readme(path,evidence,cold_models=False):
 return (f"""# LAMOST six-experiment project archive

Created {now()}. Full archive EC2 path: {path}.

**Archive safety:** This extracted package is a read-only scientific reproduction snapshot. Its registry.json and public_registry.json files are sanitized terminal report projections, not the controller database. Do not initialize, watchdog, or resume the experiment controller from an extracted archive, and do not rerun terminal cells from it. Descriptive report regeneration is supported from the extraction root. Operational resume applies only to the original EC2 project directory, using its retained controller SQLite state, verified ownership lock, and live-process checks.

Terminal closeout first runs the portable test bundle whose exact manifest, runner, source, test, resource-proof, and environment hashes are recorded in the validated report. A prior passing receipt is reused only for that unchanged bundle. The private retry latch at `runtime_20261025/logs/operational/finalization_retry_latch.json` and its attempt history under `runtime_20261025/logs/operational/finalization_attempt_history/` are excluded from the archive; only a filtered `FINALIZATION_REVIEW_REQUIRED.json` status marker can be public. A content-addressed, immutable passing-test receipt is retained under `runtime_20261025/reports/`. The finalizer keeps bounded attempts: at most two deterministic attempts per unchanged code/configuration/terminal-registry fingerprint, with operational storage or memory holds recorded separately and backed off. When the bound is reached it writes `FINALIZATION_REVIEW_REQUIRED.json` instead of repeatedly running expensive audits. On the original EC2 only, a reviewed correction can be recorded with `python runtime_20261025/source/finalize_project.py --clear-failure-latch --reason "<at least 20 characters describing the reviewed correction>"`; this preserves the attempt history and does not authorize scientific retries.

All available project artifacts for E1-E6 are included. Frozen E1: 674 successful, 81 failed (55 resource, 26 supervisor-terminal), 10 unsupported. The recovery supplement remains separate and stopped early at user request. E2 primary coverage is 108/150 with 42 unavailable; classical references are 120/120. Later experiments are fully accounted for by terminal state. Bootstrap was dropped.

The original E1 wrap-up ZIP remains preserved on EC2 at {evidence['e1_archive']['path']} (SHA-256 {evidence['e1_archive']['sha256']}) and was verified as a gate; it is intentionally not embedded because it contains excluded operational receipts. Instead, this archive includes the verified frozen project tree, final E1 wrap-up tables/report, and curated stopped recovery tree directly. Historical E1 fitted models and per-test-row predictions omitted from the compact migration remain unavailable; this archive does not claim they were restored.

Content-identical artifacts are stored once. {('Previously cold-stored selected E3-E6 random-forest pipelines remain as verified pre-existing ZIP members in this same archive; their native runtime artifact paths are hash-checked aliases restored by the included restorer. The finalizer appends the other full-archive files to that same ZIP and does not create a second full archive copy. ' if cold_models else '')}From the extracted archive root, run python3 restore_archive_aliases.py to restore aliases; it checks hashes and confines writes to the extraction root. It uses hardlinks when available and a verified copy fallback when linking is unsupported, without overwriting conflicting files. runtime_20261025/registry.json is a privacy-curated terminal report projection, not the original live controller database. To regenerate descriptive tables on EC2 from the extraction root, run `export PYTHONPATH="$PWD/venv/lib/python3.12/site-packages:/home/ubuntu/.local/lib/python3.12/site-packages:/usr/lib/python3/dist-packages"` and then `"$PWD/venv/bin/python" runtime_20261025/source/report_cli.py`; no model fitting or inference occurs. E3 NPZ restoration and serialization-validation evidence is included as privacy-curated, source-hash-bound provenance; see runtime_20261025/manifests/incidents/ and E3_INCIDENT_PROVENANCE_SUMMARY.json. The nine original container SHA values, array/CRC results, and validation resource facts are retained; private request/result receipts are omitted. Restored original containers are under runtime_20261025/artifacts/_restored_original_e3_containers/. The included FINAL_SCIENTIFIC_REPORT.md, costs.csv, and cost_summary.csv are validated historical observations. Private phase-supervision receipts and phase JSON were excluded or curated, so regenerating the report may not reconstruct every historical phase cost byte-for-byte. The calibration replay raw phase ledger and private beacon contain process IDs/start ticks; they remain under EC2 operational logs and are excluded from the archive. The sanitized supervision receipt and qualification preserve the ledger SHA, per-fit identity bindings, durations, sampled RSS, and cap outcome. Preserve these supplied validated outputs and regenerate only on an extraction copy. archive_member_manifest.json lists file paths, byte sizes, SHA-256 hashes, aliases, and explicit omissions. After extraction, source/tests/cache/artifacts retain their native runtime_20261025/ paths; no directory-renaming step is needed. Main report: runtime_20261025/reports/FINAL_SCIENTIFIC_REPORT.md.
""").encode()
def public_registry(runtime):
 reg=load(runtime/'registry.json');
 from reason_text_curation import _PRIVATE_PROCESS_FIELDS
 private_process_fields=set(_PRIVATE_PROCESS_FIELDS)|{'hold_nonce','nonce','phase_supervision'}
 def scrub(x):
  if isinstance(x,dict):
   o={}
   for k,v in x.items():
    kl=str(k).strip().lower().replace('-','_')
    if 'pid' in kl or kl in private_process_fields:continue
    if kl=='artifact_dir' and x.get('key'):o[k]='runtime_20261025/artifacts/'+x['key'];continue
    if kl=='attempts' and isinstance(v,list):o[k]=[{kk:scrub(vv) for kk,vv in a.items() if kk in {'attempt_id','started_utc','finished_utc','observed_utc','reason','status','outcome','validation_state','resource_profile','peak_tree_rss_bytes','attempt_number'}} for a in v if isinstance(a,dict)];continue
    o[k]=scrub(v)
   return o
  if isinstance(x,list):return [scrub(y) for y in x]
  return sanitize_operational_json(x) if isinstance(x,str) else x
 d=scrub(reg);d['sanitization']={'private process IDs/receipts/paths/logs removed':True,'scientific attempt identities/reasons/resource profiles/validation/outcomes preserved':True};return (json.dumps(d,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()
def _active_project_processes():
 found=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:a=(p/'cmdline').read_bytes().decode(errors='replace').replace('\0',' ')
  except Exception:continue
  if any(x in a for x in ('source/controller.py','source/worker.py','source/phase_worker.py')):found.append({'pid':int(p.name),'role':'project_controller_or_worker'})
 return found
def restore_aliases(extract_root):
 root=Path(extract_root).resolve();doc=load(root/'archive_aliases.json');done=[]
 def safe(n):
  p=PurePosixPath(n)
  if p.is_absolute() or any(x in ('','..','.') for x in p.parts) or '\\' in n:raise ValueError('unsafe alias path')
  q=(root/Path(*p.parts)).resolve()
  if root not in q.parents:raise ValueError('alias path escapes extraction root')
  return q
 for a in doc.get('aliases',[]):
  src=safe(a['canonical_path']);dst=safe(a['alias_path']);n=int(a['bytes']);h=a['sha256']
  if not src.is_file() or src.stat().st_size!=n or sha_file(src)!=h:raise ValueError('canonical file hash check failed')
  dst.parent.mkdir(parents=True,exist_ok=True)
  if dst.exists():
   if dst.is_file() and dst.stat().st_size==n and sha_file(dst)==h:done.append(a['alias_path']);continue
   raise FileExistsError('refuse conflicting alias overwrite')
  try:os.link(src,dst)
  except OSError as exc:
   import errno
   allowed={errno.EXDEV,errno.EPERM,errno.EACCES,getattr(errno,'ENOTSUP',errno.EPERM),getattr(errno,'EOPNOTSUPP',errno.EPERM),getattr(errno,'EMLINK',errno.EPERM),getattr(errno,'ENOSYS',errno.EPERM)}
   if exc.errno not in allowed:raise
   fd,tmp=tempfile.mkstemp(prefix='.restore_alias_',dir=dst.parent)
   try:
    with os.fdopen(fd,'wb') as target,src.open('rb') as source:shutil.copyfileobj(source,target,4*1024*1024);target.flush();os.fsync(target.fileno())
    if Path(tmp).stat().st_size!=n or sha_file(Path(tmp))!=h:raise ValueError('restored copy failed validation')
    if dst.exists():
     if dst.is_file() and dst.stat().st_size==n and sha_file(dst)==h:done.append(a['alias_path']);continue
     raise FileExistsError('refuse conflicting alias overwrite')
    os.replace(tmp,dst)
   finally:
    if os.path.exists(tmp):os.unlink(tmp)
  if not dst.is_file() or dst.stat().st_size!=n or sha_file(dst)!=h:
   if dst.exists() and os.path.samefile(src,dst):dst.unlink()
   raise ValueError('restored alias failed validation')
  done.append(a['alias_path'])
 return {'restored_aliases':len(done),'paths':done}

def self_test():
 with tempfile.TemporaryDirectory(prefix='lamost_finalizer_test_') as td:
  root=Path(td);s=root/'src';(s/'nested').mkdir(parents=True);(s/'a.txt').write_text('same');(s/'nested/b.txt').write_text('same');(s/'nested/secret.pem').write_text('exclude');(s/'nested/x.tmp').write_text('exclude');(s/'attempts').mkdir();(s/'attempts/private.json').write_text('{}')
  got={p.relative_to(s).as_posix() for p in iterfiles(s)}
  assert got=={'a.txt','nested/b.txt'},got
  z=root/'test.zip';res=zipwrite(z,[Entry(s/'a.txt','a/a.txt'),Entry(s/'nested/b.txt','b/b.txt')],[],['test omissions'],0)
  assert res['alias_count']==1 and res['zip_crc_passed'] and sha_file(z)==res['sha256'] and z.stat().st_size==res['bytes']
  out=root/'extract';out.mkdir()
  with zipfile.ZipFile(z) as f:
   assert f.testzip() is None;f.extractall(out);m=json.loads(f.read('archive_member_manifest.json'));a=json.loads(f.read('archive_aliases.json'));assert m['alias_count']==1 and a['aliases'][0]['alias_path']=='b/b.txt'
  rr=restore_aliases(out);assert rr['restored_aliases']==1 and (out/'a/a.txt').read_bytes()==(out/'b/b.txt').read_bytes() and os.path.samefile(out/'a/a.txt',out/'b/b.txt')
  original_stream=stream;mutated=root/'mutated.zip'
  def mutate_source(e):return io.BytesIO(b'changed') if e.member=='mutated.bin' else original_stream(e)
  try:
   globals()['stream']=mutate_source
   try:zipwrite(mutated,[Entry(b'original','mutated.bin')],[],['mutation fixture'],0)
   except EvidenceError as ex:assert 'mutated during streaming' in str(ex)
   else:raise AssertionError('source mutation during ZIP streaming was not detected')
  finally:globals()['stream']=original_stream
  assert not mutated.exists() and not list(root.glob('mutated.zip.tmp.*'))
  (out/'restore_archive_aliases.py').write_text(RESTORE,encoding='utf-8')
  subprocess.run([sys.executable,str(out/'restore_archive_aliases.py')],check=True,capture_output=True,text=True)
  assert (out/'b/b.txt').read_bytes()==b'same'
  sanitized=scrub_registry({'tasks':[{'key':'e3/rep_1','pid':123,'request_path':'/secret','attempts':[{'attempt_id':'a1','reason':'timeout','worker_pid':99,'status':'scientific_failure'}]}]})
  encoded=json.dumps(sanitized).lower();assert '123' not in encoded and '/secret' not in encoded and 'worker_pid' not in encoded and 'a1' in encoded and 'timeout' in encoded
  nested=scrub_registry({'result':{'balanced_accuracy':0.61,'phase_supervision':{'pid':2240885,'seconds':600.08,'peak_tree_rss_kib':3697924},'worker_pid':95}});ne=json.dumps(nested);assert '2240885' not in ne and 'worker_pid' not in ne and '0.61' in ne
  timeout_view=sanitize_operational_json({'trial_error':"phase_timeout: {'phase':'trial_0','pid':2240885,'pgid':2240885,'exit_code':-15,'seconds':600.08,'peak_tree_rss_kib':3697924,'reason':'timeout','stdout':'raw','stderr':'raw','finished_at':'2026-10-25T11:00:00Z'}"});te=timeout_view['trial_error'];assert '2240885' not in te and 'stdout' not in te and '600.08' in te and '3697924' in te and 'timeout' in te
  jf=s/'fit_result.json';jf.write_text(json.dumps({'result':{'balanced_accuracy':0.61,'phase_supervision':{'pid':2240885,'seconds':600.08},'worker_pid':95}}));raw_sha=sha_file(jf);je=archive_json_entry(jf,'fit_result.json','fixture',root,{str(jf.resolve()):raw_sha});jd=json.loads(je.source);assert '2240885' not in json.dumps(jd) and jd['result']['balanced_accuracy']==0.61 and jd['_archive_sanitization']['source_sha256']==raw_sha
  try:archive_json_entry(jf,'fit_result.json','fixture',root,{str(jf.resolve()):'0'*64})
  except EvidenceError as ex:assert 'reviewed JSON source changed' in str(ex)
  else:raise AssertionError('changed JSON source was not rejected against review hash')
  pub=scrub_registry({'tasks':[{'result':{'accuracy':0.61,'trial_error':"phase_timeout: {'phase':'trial_0','pid':2240885,'pgid':2240885,'seconds':600.08,'peak_tree_rss_kib':3697924,'reason':'timeout','stdout':'raw'}"}}]});pubtext=json.dumps(pub);assert '2240885' not in pubtext and 'stdout' not in pubtext and '600.08' in pubtext and '0.61' in pubtext
  tree=root/'tree';(tree/'project/lamost_baseline/data').mkdir(parents=True);(tree/'project/benchmark/results/e1/rep_1/n_3/gmm').mkdir(parents=True);(tree/'project/operations').mkdir();(tree/'project/benchmark/results/e1/rep_1/n_3/gmm/supervisor.log').write_text('scientific completed status');(tree/'project/lamost_baseline/data/source.parquet').write_bytes(b'baseline');(tree/'project/operations/migration_receipt.json').write_text('{"private":true}');(tree/'project/benchmark/results/supervisor_state.json').write_text('{"pid":42}');(tree/'project/watcher.log').write_text('private watcher log');(tree/'project/final.receipt.json').write_text('{"private":true}')
  tree_entries=curated_tree_entries(tree/'project','project','test',tree,allow_e1_supervisor=True);members={x.member for x in tree_entries};assert 'project/lamost_baseline/data/source.parquet' in members and 'project/benchmark/results/e1/rep_1/n_3/gmm/supervisor.log' in members and not any('migration_receipt' in x or 'supervisor_state' in x or 'watcher.log' in x or x.endswith('final.receipt.json') for x in members)
  # Reproduction path fixture: build a tiny full archive tree using collect_full, extract,
  # restore aliases, and execute a path-only stub from the native runtime/source location.
  fr=root/'path_fixture';rt=fr/'runtime_20261025';fr.mkdir();
  for d in ('project','e1_wrapup_20261024','e1_recovery_20261024','e2_20261024'): (fr/d).mkdir(parents=True,exist_ok=True)
  (rt/'source').mkdir(parents=True);(rt/'tests').mkdir();(rt/'cache').mkdir();(rt/'artifacts').mkdir();(rt/'reports').mkdir();(rt/'manifests').mkdir()
  for d in ('source','tests','cache','artifacts'):(rt/d/'fixture.txt').write_text('native-'+d)
  # Copy the local import closure needed by descriptive report regeneration.  The cold
  # reader may load the cold model API dynamically, so include that optional pair when
  # present as well; collect_full uses the same source tree and preserves these paths.
  source_root=Path(__file__).resolve().parent
  copied_source_names=set()
  for source_name in ('finalize_project.py','cold_finalizer_adapter.py','archive_scientific_histories.py','final_review.py','reporting.py','reason_text_curation.py','cold_report_access.py','cold_model_storage.py','cold_storage_safety.py','build_condition_findings.py'):
   source_path=source_root/source_name
   if source_path.is_file():shutil.copy2(source_path,rt/'source'/source_name);copied_source_names.add(source_name)
  probe=rt/'source/path_probe.py';probe.write_text("from pathlib import Path\nr=Path(__file__).resolve().parents[1]\nassert (r/'tests/fixture.txt').read_text()=='native-tests'\nassert (r/'cache/fixture.txt').read_text()=='native-cache'\nassert (r/'artifacts/fixture.txt').read_text()=='native-artifacts'\nprint('native paths ok')\n")
  (rt/'registry.json').write_text(json.dumps({'observed_utc':'fixture','tasks':[{'key':'e3/rep_1/eval/direct/gmm','experiment':3,'rep':1,'kind':'eval','scientific_case':True,'status':'validated_terminal','outcome':{'status':'successful','evaluation':{'balanced_accuracy':0.5}},'validation_state':'validated','result':{'worker_pid':123,'phase_supervision':{'pid':456}},'attempts':[{'attempt_id':'a','reason':'scientific failure of an earlier trial','status':'scientific_failure','worker_pid':789}]}]}));public_fixture=public_registry(rt);(fr/E3_RESTORE_MANIFEST).parent.mkdir(parents=True,exist_ok=True)
  (fr/E3_RESTORE_MANIFEST).write_text(json.dumps({'created_utc':'fixture','experiment':'E3','audit_sha256':'audit-sha','engine_code_sha256':'engine-sha','restoration_code_sha256':'restore-sha','restoration_rule':'copy exact original NPZ bytes','scope':'diagnostic only','fit_predict_calibrate_generate_performed':False,'live_artifacts_modified':False,'models_loaded':False,'issues_csv_path':str(fr/'runtime_20261025/reports/issues.csv'),'issues_csv_sha256':'issues-sha','files':[{'task_key':'e3/rep_1/eval/direct/gmm','current_path':str(fr/'runtime_20261025/artifacts/e3/current.npz'),'current_sha256':'c'*64,'restored_path':str(fr/'runtime_20261025/artifacts/_restored_original_e3_containers/e3/original.npz'),'restored_sha256':'o'*64,'source_candidate_path':str(fr/'runtime_20261025/artifacts/e3/candidate.npz'),'source_candidate_sha256':'o'*64,'support_diagnostic_baseline_path':str(fr/'runtime_20261025/artifacts/e3/support.json'),'support_diagnostic_baseline_sha256':'s'*64,'initial_request_path':'/private/request.json','initial_worker_result_path':'/private/worker_result.json','array_validation':{'old_zip_crc':'ok','current_zip_crc':'ok','fallback_mask_omitted_only':True,'fallback_mask_shape':[500000],'fallback_true_count':65,'member_order_preserved':True,'original_members':['sample_id','y_pred'],'current_members':['sample_id','y_pred','fallback_mask'],'arrays':[{'name':'sample_id','shape':[500000],'dtype':'int64','values_exact':True}]}}]}))
  (fr/SERIALIZATION_INCIDENT).parent.mkdir(parents=True,exist_ok=True)
  (fr/SERIALIZATION_INCIDENT).write_text(json.dumps({'incident_id':'serialization_validation_20261025','observed_utc':'fixture','classification':'operationally_invalid_post_save_validation_memory_duplication','task_key':'e3/rep_1/fit/synthetic/random_forest/copula','other_affected_task':'e3/rep_1/fit/synthetic/random_forest/gmm','invalid_phase':'final_fit','invalid_phase_elapsed_seconds':520.65,'invalid_validation_peak_rss_kib':10616732,'model_fit_completed_and_artifact_saved_before_invalid_validation':True,'models_refitted_for_recovery':0,'selected_trial':4,'selected_trial_peak_rss_kib':4178128,'single_copy_validation_status':'validated','single_copy_validation_seconds':16.49,'single_copy_validation_peak_rss_kib':7583592,'test_predictions_generated_during_repair':0,'resource_policy_changed':False,'trial_budgets_domains_seeds_memberships_changed':False,'repair':'Release fitted in-memory model before reload verification','validation':'independent model comparison passed','worker_pid':33,'private_process_receipt':'secret','checkpoint_migrations':'checkpoint_migrations.json'}))
  ((fr/SERIALIZATION_INCIDENT).parent/'checkpoint_migrations.json').write_text('{\"migrations\": []}')
  incident_hash_overrides={E3_RESTORE_MANIFEST:sha_file(fr/E3_RESTORE_MANIFEST),SERIALIZATION_INCIDENT:sha_file(fr/SERIALIZATION_INCIDENT)}
  entries=collect_full(fr,rt,b'# fixture readme',public_fixture,incident_hash_overrides=incident_hash_overrides);pzip=fr/'fixture_archive.zip';zipwrite(pzip,entries,[],['path fixture'],0);dest=fr/'extracted';dest.mkdir()
  with zipfile.ZipFile(pzip) as zf:assert zf.testzip() is None;zf.extractall(dest)
  assert restore_aliases(dest)['restored_aliases']>=0
  registry_doc=json.loads((dest/'runtime_20261025/registry.json').read_text());registry_raw=(dest/'runtime_20261025/registry.json').read_text();assert len(registry_doc['tasks'])==1 and registry_doc['tasks'][0]['outcome']['evaluation']['balanced_accuracy']==0.5 and 'scientific failure of an earlier trial' in registry_raw and 'worker_pid' not in registry_raw and 'phase_supervision' not in registry_raw and '123' not in registry_raw and '456' not in registry_raw and '789' not in registry_raw
  assert (dest/'runtime_20261025/public_registry.json').read_bytes()==(dest/'runtime_20261025/registry.json').read_bytes()
  restored_prov=json.loads((dest/E3_RESTORE_MANIFEST).read_text());prov_text=(dest/E3_RESTORE_MANIFEST).read_text();assert restored_prov['source_manifest_sha256']==incident_hash_overrides[E3_RESTORE_MANIFEST] and restored_prov['files'][0]['restored_sha256']=='o'*64 and 'initial_request_path' not in prov_text and '/private/' not in prov_text
  incident_path=dest/'runtime_20261025/manifests/incidents/serialization_validation_20261025/incident_summary.json';incident_doc=json.loads(incident_path.read_text());incident_text=incident_path.read_text();assert incident_doc['source_incident_sha256']==incident_hash_overrides[SERIALIZATION_INCIDENT] and incident_doc['models_refitted_for_recovery']==0 and incident_doc['invalid_validation_peak_rss_kib']==10616732 and 'worker_pid' not in incident_text and 'private_process_receipt' not in incident_text
  small_path=fr/'small_reports.zip';small_entries=_small_entries(fr,rt,None,'fixture',str(small_path),incident_hash_overrides=incident_hash_overrides);small_doc_entry=next(x for x in small_entries if x.member=='E3_INCIDENT_PROVENANCE_SUMMARY.json');small_doc=json.loads(small_doc_entry.source);assert len(small_doc['npz_restoration']['files'])==1 and small_doc['npz_restoration']['source_manifest_sha256']==incident_hash_overrides[E3_RESTORE_MANIFEST] and small_doc['serialization_validation_incident']['source_incident_sha256']==incident_hash_overrides[SERIALIZATION_INCIDENT];small_result=_small_zip(small_path,small_entries,{'fixture':True},None,0);small_extract=fr/'small_extract';small_extract.mkdir()
  with zipfile.ZipFile(small_path) as sz:assert sz.testzip() is None;sz.extractall(small_extract)
  assert (small_extract/'E3_INCIDENT_PROVENANCE_SUMMARY.json').is_file() and 'E3_INCIDENT_PROVENANCE_SUMMARY.json' not in {x.name for x in dest.iterdir()}
  loader=dest/'runtime_20261025/source/report_loader_probe.py';loader.write_text("import json,sys\nfrom pathlib import Path\nr=Path(__file__).resolve().parents[1]\nsys.path.insert(0,str(r/'source'))\nimport reporting\nt=json.loads((r/'registry.json').read_text())['tasks'][0]\ne=reporting._find_eval(r,t)\nassert e['balanced_accuracy']==0.5\nprint('report loader metric',e['balanced_accuracy'])\n")
  expected={'runtime_20261025/registry.json','runtime_20261025/public_registry.json','runtime_20261025/source/path_probe.py','runtime_20261025/source/report_loader_probe.py','runtime_20261025/tests/fixture.txt','runtime_20261025/cache/fixture.txt','runtime_20261025/artifacts/fixture.txt'}|{'runtime_20261025/source/'+name for name in copied_source_names}
  assert {'reporting.py','reason_text_curation.py'}.issubset(copied_source_names)
  if 'cold_report_access.py' in copied_source_names:assert (dest/'runtime_20261025/source/cold_report_access.py').is_file()
  assert expected.issubset({x.relative_to(dest).as_posix() for x in dest.rglob('*') if x.is_file()})
  subprocess.run([sys.executable,str(dest/'runtime_20261025/source/path_probe.py')],check=True,capture_output=True,text=True)
  loader_result=subprocess.run([sys.executable,str(dest/'runtime_20261025/source/report_loader_probe.py')],cwd=dest,check=False,capture_output=True,text=True);assert loader_result.returncode==0 and '0.5' in loader_result.stdout,loader_result.stderr[-2000:]
  assert not any('migration_receipt' in x or 'supervisor_state' in x or 'watcher.log' in x or x.endswith('final.receipt.json') for x in {x.relative_to(dest).as_posix() for x in dest.rglob('*') if x.is_file()})
  gate_rt=root/'gate_runtime';gate_rt.mkdir();mf=gate_rt/'candidate.json';mf.write_text('{"candidate_id":"fixture"}');atomic_json(gate_rt/'REPORT_READY_FOR_AUDIT.json',{'candidate_id':'fixture','manifest_path':str(mf),'manifest_sha256':sha_file(mf)})
  original_scan=globals()['_active_project_processes'];globals()['_active_project_processes']=lambda:(_ for _ in ()).throw(AssertionError('cached wait ran process scan'))
  try:wait_result=finalize(root,gate_rt)
  finally:globals()['_active_project_processes']=original_scan
  assert wait_result['status']=='report_ready_for_internal_audit'
  reviewed=root/'manual_final_report.md';reviewed.write_text('reviewed manual text');rb=reviewed.read_bytes();proof={'candidate_id':'fixture-pass'};atomic_json(gate_rt/'finalizer_state.json',{'phase':'awaiting_report_audit','review_candidate_id':'fixture-pass','final_report_path':str(reviewed),'final_report_sha256':sha_file(reviewed)})
  resumed=_resume_reviewed_report_state(gate_rt,proof);assert resumed is None and reviewed.read_bytes()==rb
  archive_rt=root/'archive_runtime';archive_rt.mkdir();prior=root/'prior_reviewed.zip'
  with zipfile.ZipFile(prior,'w') as zz:zz.writestr('REPORT_REVIEW_PROOF.json',json.dumps(proof))
  pst=prior.stat();pr={'path':str(prior),'bytes':pst.st_size,'mtime_ns':pst.st_mtime_ns,'sha256':sha_file(prior),'zip_crc_passed':True,'report_review_proof':proof};atomic_json(archive_rt/'finalizer_state.json',{'full_archive':pr});atomic_json(Path(str(prior)+'.receipt.json'),pr)
  assert _resume_full(archive_rt,proof)==pr and _resume_full(archive_rt,{'candidate_id':'other'}) is None
  return {'status':'self_test_passed','excluded':['private.pem','x.tmp','attempts/private.json','operations/migration_receipt.json','supervisor_state.json','raw watcher log','operational receipt JSON'],'included':['baseline source fixture','scientific E1 supervisor log'],'content_deduplicated':True,'embedded_restorer_executes_and_hash_validates':True,'registry_sanitization_preserves_attempt_reason':True,'zip_crc_passed':True,'zip_size_and_sha_validated':True,'source_mutation_during_stream_detected':True,'cached_report_wait_skips_process_scan_and_report_regeneration':True,'legacy_review_cache_missing_condition_findings_is_rejected_without_report_overwrite':True,'same_review_full_archive_checkpoint_reuses':True,'manifest_validated':True,'full_collect_extract_restore_native_runtime_paths':True,'harmless_relative_path_probe_passed':True,'no_directory_rename_map_required':True,'sanitized_report_registry_restored_nonempty':True,'report_metrics_status_and_attempt_reason_preserved':True,'registry_private_receipts_absent':True,'actual_reporting_find_eval_loader_passed':True,'restoration_manifest_curated_source_sha_bound':True,'serialization_incident_allowlisted_and_sanitized':True,'compact_incident_summary_included':True,'small_zip_incident_summary_crc_and_restore_passed':True}


def _small_zip(path,entries,metadata,expected_source_sha256=None,review_proof=None):
 metadata=dict(metadata);metadata['report_review']=review_proof
 generated=[Entry((json.dumps(metadata,indent=2,sort_keys=True)+'\n').encode(),'small_delivery_manifest.json','small_report_manifest')]
 return zipwrite(path,entries,generated,['Small delivery excludes raw full-size datasets/models; use the full archive at the path in FULL_ARCHIVE_LOCATION.md.'],16*1024*1024,expected_source_sha256,review_proof)

def _resume_reviewed_report_state(runtime,review_proof):
 state_path=Path(runtime)/'finalizer_state.json'
 if not state_path.is_file():return None
 try:state=load(state_path)
 except Exception:return None
 allowed={'awaiting_report_audit','archive_packaging','full_archive','delivery_pending_on_laptop'}
 if state.get('phase') not in allowed or state.get('review_candidate_id')!=review_proof.get('candidate_id'):return None
 report=Path(state.get('final_report_path',''))
 if not report.is_file() or sha_file(report)!=state.get('final_report_sha256'):return None
 try:
  validate_condition_findings(runtime,state.get('report_validation',{}).get('condition_findings'))
  audit=state.get('artifact_audit',{})
  if audit.get('full_calibration_replay_pass') is not True: return None
  _calibration_replay_validation(runtime,audit.get('calibration_replay'))
 except Exception:return None
 return state

def _resume_full(runtime,review_proof=None):
 p=runtime/'finalizer_state.json'
 if not p.exists():return None
 try:
  state=load(p);d=state.get('full_archive')
  if not d or not d.get('path') or d.get('report_review_proof')!=review_proof:return None
  f=Path(d['path']);st=f.stat();receipt=load(Path(str(f)+'.receipt.json'))
  if not f.is_file() or st.st_size!=int(d['bytes']) or (d.get('mtime_ns') and st.st_mtime_ns!=int(d['mtime_ns'])):return None
  if receipt.get('sha256')!=d.get('sha256') or receipt.get('report_review_proof')!=review_proof or receipt.get('zip_crc_passed') is not True:return None
  with zipfile.ZipFile(f) as z:
   if json.loads(z.read('REPORT_REVIEW_PROOF.json'))!=review_proof:return None
  return d
 except Exception:return None

def _valid_pending(p,runtime):
 if not p.exists():return None
 try:
  from final_review import quick_wait,verify_report_files
  d=load(p);proof=d.get('report_review')
  if not proof or proof.get('decision')!='pass' or quick_wait(runtime) is not None:return None
  ready=load(runtime/'REPORT_READY_FOR_AUDIT.json')
  state=load(runtime/'finalizer_state.json')
  validate_condition_findings(runtime,state.get('report_validation',{}).get('condition_findings'))
  audit=state.get('artifact_audit',{})
  if audit.get('full_calibration_replay_pass') is not True:return None
  _calibration_replay_validation(runtime,audit.get('calibration_replay'))
  if ready.get('candidate_id')!=proof.get('candidate_id') or ready.get('manifest_sha256')!=proof.get('manifest_sha256'):return None
  review_manifest=load(ready['manifest_path'])
  if not verify_report_files(runtime,ROOT,review_manifest):return None
  files=[d.get('full_archive'),d.get('small_delivery_zip')]
  if any(not x or not x.get('path') or x.get('report_review_proof')!=proof for x in files):return None
  for x in files:
   f=Path(x['path']);st=f.stat();receipt=load(Path(str(f)+'.receipt.json'))
   if st.st_size!=int(x['bytes']) or (x.get('mtime_ns') and st.st_mtime_ns!=int(x['mtime_ns'])):return None
   if receipt.get('path')!=x.get('path') or receipt.get('bytes')!=x.get('bytes') or receipt.get('sha256')!=x.get('sha256') or receipt.get('report_review_proof')!=proof or receipt.get('zip_crc_passed') is not True:return None
   with zipfile.ZipFile(f) as z:
    if json.loads(z.read('REPORT_REVIEW_PROOF.json'))!=proof:return None
  return d
 except Exception:return None
def _write_review_required_marker(runtime,result):
 payload={'schema_version':'lamost-finalization-review-required-public/1','status':'FINALIZATION_REVIEW_REQUIRED','observed_utc':result.get('observed_utc',now()),'project_complete':False,
  'fingerprint_sha256':result.get('fingerprint_sha256') if isinstance(result.get('fingerprint_sha256'),str) and len(result.get('fingerprint_sha256'))==64 else None,
  'failure_count':result.get('failure_count'),'operational_hold_count':result.get('operational_hold_count'),
  'instruction':'Review private finalization attempt receipts under logs/operational before clearing the latch.'}
 atomic_json(Path(runtime)/'FINALIZATION_REVIEW_REQUIRED.json',payload)
 return payload

def _portable_test_gate_summary(runtime,gate):
 receipt=gate['receipt'];path=Path(gate['receipt_path'])
 return {'schema_version':'lamost-portable-test-gate-binding/1','receipt_path':path.relative_to(Path(runtime).resolve()).as_posix(),
  'receipt_sha256':gate['receipt_sha256'],'bundle_fingerprint_sha256':receipt['bundle_fingerprint_sha256'],
  'manifest_sha256':receipt['manifest_sha256'],'runner_sha256':receipt['runner_sha256'],
  'source_hashes':receipt['source_hashes'],'test_hashes':receipt['test_hashes'],'resource_proofs':receipt['resource_proofs'],
  'environment_policy_sha256':receipt['environment_policy_sha256'],'expected_test_count':receipt['expected_test_count'],
  'passed_test_count':receipt['passed_test_count']}

def _verify_portable_test_gate(root,runtime,summary,expected_hashes=None):
 from finalization_safety import portable_bundle_snapshot,portable_pass_receipt_path
 snapshot=portable_bundle_snapshot(root,runtime);path=portable_pass_receipt_path(runtime,snapshot)
 if summary.get('receipt_path')!=path.relative_to(Path(runtime).resolve()).as_posix():raise EvidenceError('reviewed portable pass receipt path is not the immutable content-addressed path')
 if not path.is_file():raise EvidenceError('portable test pass receipt is missing after final report validation')
 receipt=load(path)
 if not portable_receipt_matches(receipt,snapshot):raise EvidenceError('portable test receipt is stale or does not match current bundle/source/test hashes')
 expected=_portable_test_gate_summary(runtime,{'receipt':receipt,'receipt_path':path,'receipt_sha256':sha_file(path),'reused':False})
 if summary!=expected:raise EvidenceError('reviewed report_result portable test binding differs from current receipt')
 expected_hashes=expected_hashes or {}
 expected_hashes[str(path.resolve())]=sha_file(path)
 return expected_hashes

def _check_freeze(runtime):
 fr=load(runtime/'manifests/freeze.json');bad=[]
 for n,h in fr.get('source_sha256',{}).items():
  p=runtime/'source'/n
  if not p.is_file() or sha_file(p)!=h:bad.append(n)
 if bad:raise EvidenceError('runtime source differs from frozen execution code: '+', '.join(bad))
 return {'protocol_version':fr.get('protocol_version'),'source_files_verified':len(fr.get('source_sha256',{})),'freeze_sha256':sha_file(runtime/'manifests/freeze.json')}
def _export_master_index(runtime):
 py=Path('/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python3');p=runtime/'source/export_master_index.py'
 if not p.exists():raise EvidenceError('master-index exporter is missing')
 proc=subprocess.run([str(py),str(p)],capture_output=True,text=True,timeout=600)
 if proc.returncode:raise EvidenceError(f'master-index export failed: {proc.stderr[-2000:]}')
 index=load(runtime/'master_index.json')
 if len(index.get('tasks',[]))!=6270:raise EvidenceError('derived master index does not contain 6,270 task rows')
 freeze=load(runtime/'manifests/freeze.json')
 manifests={}
 for e,n in EXPECTED.items():
  p=runtime/'manifests'/f'E{e}_MANIFEST.json';d=load(p)
  if d.get('source_frozen_plan_sha256')!=freeze.get('plan_sha256') or d.get('planned_scientific_cases')!=n:raise EvidenceError(f'E{e} manifest is not derived from the frozen current plan')
  manifests[p.name]={'sha256':sha_file(p),'bytes':p.stat().st_size,'planned_scientific_cases':n}
 return {'master_index_sha256':sha_file(runtime/'master_index.json'),'master_index_rows':len(index['tasks']),'experiment_manifests':manifests}
OVERALL_CASE_INDEX_GROUP_ROWS={'E1_frozen':765,'E1_recovery_stopped_early_user_request':91,'E2_primary':150,'E2_classical_reference':120,'E3_later_experiment':69,'E4_later_experiment':1773,'E5_later_experiment':960,'E6_later_experiment':21}
OVERALL_CASE_INDEX_E1={'successful':674,'scientific_failure':81,'unsupported':10}
OVERALL_CASE_INDEX_RECOVERY={'successful':24,'scientific_failure':10,'user_stopped':2,'not_attempted_user_stopped':55}
def _atomic_bytes(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp.'+uuid.uuid4().hex)
 with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def _inside(path,base):
 p=Path(path).resolve();b=Path(base).resolve()
 try:p.relative_to(b)
 except ValueError as e:raise EvidenceError('overall case-index path escaped its report root') from e
 if Path(path).is_symlink():raise EvidenceError('overall case-index path is a symlink')
 return p
def validate_overall_case_index(root,runtime,output):
 root=Path(root).resolve();runtime=Path(runtime).resolve();base=runtime/'reports'/'overall_case_index';output=_inside(output,base)
 builder=runtime/'source'/'build_overall_case_index.py';helper=runtime/'source'/'case_index_helpers.py'
 if not builder.is_file() or not helper.is_file():raise EvidenceError('overall case-index publisher/helper missing')
 ready_path=output/'READY.json';csv_path=output/'OVERALL_SCIENTIFIC_CASE_INDEX.csv';summary_path=output/'OVERALL_SCIENTIFIC_CASE_INDEX_SUMMARY.json';current_path=base/'CURRENT.json'
 ready=load(ready_path);summary=load(summary_path);current=load(current_path)
 if ready.get('status')!='ready' or Path(ready.get('output_directory','')).resolve()!=output:raise EvidenceError('overall case-index READY marker does not name its version directory')
 if current.get('current_ready_path')!=ready_path.relative_to(base).as_posix() or current.get('ready_sha256')!=sha_file(ready_path):raise EvidenceError('overall case-index CURRENT pointer differs from READY marker')
 csv_sha=sha_file(csv_path);summary_sha=sha_file(summary_path);ready_sha=sha_file(ready_path);current_sha=sha_file(current_path)
 if ready.get('csv_sha256')!=csv_sha or ready.get('summary_sha256')!=summary_sha or ready.get('builder_script_sha256')!=sha_file(builder):raise EvidenceError('overall case-index READY hashes differ from published files/source')
 if summary.get('schema')!='lamost-overall-case-index/2' or summary.get('builder_script_sha256')!=sha_file(builder) or summary.get('builder_helper_sha256')!=sha_file(helper):raise EvidenceError('overall case-index schema or builder source hashes differ')
 if summary.get('combined_rows')!=3949 or summary.get('main_scientific_case_rows')!=3858 or summary.get('separate_E1_recovery_supplement_rows')!=91 or summary.get('planned_later_rows_by_experiment')!={'3':69,'4':1773,'5':960,'6':21}:raise EvidenceError('overall case-index summary counts differ from frozen design')
 groups=summary.get('counts_by_group') or {}
 if {k:sum(int(x) for x in v.values()) for k,v in groups.items()}!=OVERALL_CASE_INDEX_GROUP_ROWS:raise EvidenceError('overall case-index group rows are missing or changed')
 if groups.get('E1_frozen')!=OVERALL_CASE_INDEX_E1 or groups.get('E1_recovery_stopped_early_user_request')!=OVERALL_CASE_INDEX_RECOVERY:raise EvidenceError('overall case-index E1/recovery dispositions changed')
 if groups.get('E2_primary',{}).get('successful')!=108 or groups.get('E2_primary',{}).get('unavailable_dependency')!=42 or groups.get('E2_classical_reference',{}).get('successful')!=120:raise EvidenceError('overall case-index E2 coverage changed')
 row_counts=collections.Counter();keys=set();rows=0
 with csv_path.open(newline='',encoding='utf-8-sig') as f:
  reader=csv.DictReader(f)
  if not {'index_key','provenance_group','experiment','status_normalized'}.issubset(reader.fieldnames or []):raise EvidenceError('overall case-index CSV schema missing required identity columns')
  for row in reader:
   rows+=1;g=row['provenance_group'];row_counts[g]+=1
   if not row.get('index_key') or row['index_key'] in keys:raise EvidenceError('overall case-index key is empty or duplicated')
   keys.add(row['index_key'])
 if rows!=3949 or dict(row_counts)!=OVERALL_CASE_INDEX_GROUP_ROWS or summary.get('output_csv',{}).get('row_count')!=rows or summary.get('output_csv',{}).get('sha256')!=csv_sha:raise EvidenceError('overall case-index CSV and summary rows/hashes disagree')
 sources=summary.get('input_sources') or {}
 for v in sources.values():
  path=Path(v.get('path','')).resolve()
  if not path.is_file() or sha_file(path)!=v.get('sha256'):raise EvidenceError('overall case-index source hash is stale: '+str(path))
 if summary.get('master_index',{}).get('source_file_sha256')!=sha_file(runtime/'master_index.json'):raise EvidenceError('overall case-index is not paired with the refreshed master index')
 rel=lambda q:Path(q).resolve().relative_to(root).as_posix()
 return {'schema_version':'lamost-overall-case-index-binding/1','version_directory':rel(output),'ready_path':rel(ready_path),'ready_sha256':ready_sha,'current_path':rel(current_path),'current_sha256':current_sha,'csv_path':rel(csv_path),'csv_sha256':csv_sha,'summary_path':rel(summary_path),'summary_sha256':summary_sha,'total_rows':rows,'main_scientific_case_rows':3858,'separate_E1_recovery_rows':91,'group_rows':OVERALL_CASE_INDEX_GROUP_ROWS,'builder_path':rel(builder),'builder_sha256':sha_file(builder),'helper_path':rel(helper),'helper_sha256':sha_file(helper)}
def publish_overall_case_index(root,runtime):
 root=Path(root).resolve();runtime=Path(runtime).resolve();builder=runtime/'source'/'build_overall_case_index.py';helper=runtime/'source'/'case_index_helpers.py'
 if not builder.exists() and not helper.exists():return None
 if not builder.is_file() or not helper.is_file():raise EvidenceError('overall case-index publisher is only partially installed')
 base=runtime/'reports'/'overall_case_index';base.mkdir(parents=True,exist_ok=True);tag=stamp();out=base/f'snapshot_{tag}';i=1
 while out.exists():out=base/f'snapshot_{tag}_{i}';i+=1
 py=Path('/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python3')
 proc=subprocess.run([str(py),str(builder),'--root',str(root),'--runtime',str(runtime),'--output',str(out)],capture_output=True,text=True,timeout=1800)
 if proc.returncode:raise EvidenceError(f'overall case-index builder failed: {proc.stderr[-2500:]}')
 try:result=json.loads(proc.stdout)
 except Exception as e:raise EvidenceError('overall case-index builder returned malformed output') from e
 info=validate_overall_case_index(root,runtime,out)
 # Final-review inventories all top-level report CSVs; this exact companion table is included.
 source_csv=root/info['csv_path'];table=runtime/'reports'/'OVERALL_SCIENTIFIC_CASE_INDEX.csv'
 _atomic_bytes(table,source_csv.read_bytes())
 info['reviewed_table_path']=table.relative_to(root).as_posix();info['reviewed_table_sha256']=sha_file(table)
 if info['reviewed_table_sha256']!=info['csv_sha256']:raise EvidenceError('top-level reviewed case-index table differs from versioned output')
 info['builder_result']={'rows':result.get('rows'),'ready_path':result.get('ready_path'),'csv_sha256':result.get('csv_sha256')}
 return info
def bind_overall_case_index_report(runtime,info):
 if info is None:return None
 path=Path(runtime)/'reports'/'report_result.json';result=load(path)
 if result.get('status')!='success' or result.get('planned_scientific_cases')!=2823:raise EvidenceError('cannot bind case index to an invalid scientific report result')
 result['overall_scientific_case_index']=info;atomic_json(path,result)
 return {'path':path,'sha256':sha_file(path)}
def append_overall_case_index_report(report_path,info):
 if info is None:return
 p=Path(report_path)
 with p.open('a',encoding='utf-8') as f:
  f.write('\n## Companion overall case index\n\n')
  f.write(f"The versioned companion index contains {info['total_rows']} records: {info['main_scientific_case_rows']} E1-E6 main scientific cases and {info['separate_E1_recovery_rows']} separately labeled stopped-recovery records. It includes all six experiments, the separate E1 recovery supplement, and the distinct E2 primary/classical groups. See {info['csv_path']} (SHA-256 {info['csv_sha256']}) and {info['summary_path']} (SHA-256 {info['summary_sha256']}). The immutable READY/CURRENT and builder/helper hashes are recorded in report_result.json and the report-review candidate.\n")
def append_calibration_replay_report(report_path,proof):
 if not isinstance(proof,dict) or proof.get('complete') is not True or proof.get('independent_q_recomputed') is not True:raise EvidenceError('final report cannot claim incomplete calibration replay')
 counts=proof.get('counts',{})
 p=Path(report_path)
 with p.open('a',encoding='utf-8') as f:
  f.write('\n## Independent calibration replay\n\n')
  f.write(f"The final integrity audit independently recomputed the finite-sample calibration threshold from each of {counts.get('successful_physical',0)} successful physical evaluation routes, then verified threshold provenance for {counts.get('inherited_aliases',0)} successful aliases. It used the saved calibration role and did not read test rows. The complete record, including per-route score rule, class order, threshold, vector, model and role hashes, is in `CALIBRATION_REPLAY_AUDIT.json`.\n\nA separate external supervisor verified the auditor process identity and monitored each calibration-scoring phase against the 600-second wall limit and 10-GiB sampled process-tree RSS limit, with a 30-second termination grace. The immutable q audit, sanitized supervision receipt, and separate qualification record preserve these distinct checks.\n")

def bind_case_index_after_review(root,runtime,report_info,expected_hashes):
 info=(report_info or {}).get('overall_case_index')
 root=Path(root).resolve();runtime=Path(runtime).resolve();rd=runtime/'reports'
 if info is None:
  if (runtime/'source'/'build_overall_case_index.py').is_file() or (runtime/'source'/'case_index_helpers.py').is_file():
   raise EvidenceError('reviewed report candidate lacks the installed overall case-index publication')
  return expected_hashes
 result=load(rd/'report_result.json')
 if result.get('overall_scientific_case_index')!=info:raise EvidenceError('reviewed report_result case-index binding differs')
 reviewed_csv=str((root/'runtime_20261025/reports/OVERALL_SCIENTIFIC_CASE_INDEX.csv').resolve())
 if not expected_hashes or expected_hashes.get(reviewed_csv)!=info.get('reviewed_table_sha256'):raise EvidenceError('report-review candidate did not bind the companion case-index table')
 report_result=str((rd/'report_result.json').resolve())
 if expected_hashes.get(report_result)!=sha_file(rd/'report_result.json'):raise EvidenceError('report-review candidate did not bind report_result.json with case-index provenance')
 for key in ('ready_path','current_path','csv_path','summary_path','builder_path','helper_path'):
  path=_inside(root/info[key],root/'runtime_20261025')
  if not path.is_file():raise EvidenceError('case-index bound file is missing: '+info[key])
  digest=sha_file(path)
  if digest!=info.get(key.replace('_path','_sha256')):raise EvidenceError('case-index bound file changed after review: '+info[key])
  expected_hashes[str(path)]=digest
 return expected_hashes

def _calibration_replay_requirements(runtime):
 reg=load(Path(runtime)/'registry.json');tasks={t.get('key'):t for t in reg.get('tasks',[]) if isinstance(t,dict) and t.get('key')}
 physical=set();aliases=set()
 for key,t in tasks.items():
  if str(t.get('experiment')) not in {'3','4','5','6'}:continue
  if t.get('status')!='validated_terminal' or _out(t)!='successful':continue
  if t.get('kind') in {'eval','ensemble'}:physical.add(key)
  elif t.get('kind')=='alias':aliases.add(key)
 def resolve(key,seen=None):
  seen=set() if seen is None else seen
  if key in seen or key not in tasks:raise EvidenceError('calibration replay alias source cycle or missing task: '+str(key))
  seen.add(key);t=tasks[key]
  if t.get('kind') in {'eval','ensemble'}:return key
  if t.get('kind')!='alias' or not t.get('source_key'):raise EvidenceError('calibration replay alias does not resolve to evaluation: '+str(key))
  return resolve(t['source_key'],seen)
 return tasks,physical,aliases,{key:resolve(key) for key in aliases}

def _validate_e6_native_calibration_records(runtime,audit,tasks,evidence):
 runtime=Path(runtime).resolve()
 v2_list=_current_e6_v2_tasks(runtime,list(tasks.values()))
 v2_tasks={t['key']:t for t in v2_list}
 if not v2_tasks:
  return {'e6_native_calibration_replay_applicable':False,
          'e6_native_calibration_replay_complete':True,
          'required_e6_member_calibration_records':0,
          'validated_e6_member_calibration_records':0,
          'required_e6_ensembles':0,'validated_e6_ensembles':0}
 member_rows=audit.get('e6_member_calibration_records')
 ensemble_rows=audit.get('e6_ensemble_calibration_records')
 if not isinstance(member_rows,list) or not isinstance(ensemble_rows,list):raise EvidenceError('E6-v2 native calibration replay records are missing')
 successful={k:t for k,t in v2_tasks.items() if _out(t)=='successful'}
 expected_pairs=set();docs={};evals={}
 order=('gmm','copula','arf','kde','chow_liu')
 for key,task in successful.items():
  ep=runtime/'artifacts'/key/'evaluation.json'
  if not ep.is_file():raise EvidenceError('successful E6 task lacks evaluation.json: '+key)
  ev=load(ep)
  rel=ev.get('member_comparisons_path')
  if rel!='member_comparisons.json':raise EvidenceError('E6 member-comparison path is not canonical: '+key)
  cp=runtime/'artifacts'/key/rel
  if not cp.is_file() or cp.is_symlink() or sha_file(cp)!=ev.get('member_comparisons_sha256'):raise EvidenceError('E6 member-comparison artifact hash mismatch: '+key)
  doc=load(cp)
  if doc.get('schema_version')!='lamost-e6-member-comparisons/1' or doc.get('protocol_version')!='E6-v2' or doc.get('comparison_source_task_key')!=key:raise EvidenceError('E6 member-comparison schema/task binding mismatch: '+key)
  if doc.get('weights_frozen_before_calibration_and_test') is not True or doc.get('member_order')!=list(order):raise EvidenceError('E6 weights/order were not frozen under the declared protocol: '+key)
  if doc.get('rep')!=task.get('rep') or doc.get('mode')!=task.get('mode'):raise EvidenceError('E6 comparison repetition/mode differs from registry: '+key)
  members=doc.get('members')
  if not isinstance(members,dict) or set(members)!=set(order):raise EvidenceError('E6 comparison is missing a canonical member: '+key)
  for name in order:expected_pairs.add((key,name))
  docs[key]=doc;evals[key]=(ev,cp,ep)
  for source in (ep,cp):
   rel_source=source.relative_to(runtime).as_posix()
   item={'path':rel_source,'sha256':sha_file(source),'bytes':source.stat().st_size}
   prior=[x for x in evidence if x.get('path')==rel_source]
   if prior and any(x.get('sha256')!=item['sha256'] or x.get('bytes')!=item['bytes'] for x in prior):raise EvidenceError('conflicting E6 comparison/evaluation source binding: '+rel_source)
   if not prior:evidence.append(item)
 member_map={}
 for row in member_rows:
  if not isinstance(row,dict):raise EvidenceError('E6 native member calibration row is malformed')
  pair=(row.get('task_key'),row.get('member'))
  if pair in member_map:raise EvidenceError('duplicate E6 native member calibration key')
  member_map[pair]=row
 if set(member_map)!=expected_pairs:raise EvidenceError(f'E6 native member calibration coverage mismatch: expected={len(expected_pairs)} observed={len(member_map)}')
 ensmap={}
 for row in ensemble_rows:
  if not isinstance(row,dict) or row.get('task_key') in ensmap:raise EvidenceError('duplicate or malformed E6 native ensemble calibration key')
  ensmap[row['task_key']]=row
 if set(ensmap)!=set(successful):raise EvidenceError('E6 native ensemble calibration coverage differs from successful ensemble tasks')
 summary=audit.get('summary',audit)
 summary_counts={'required_e6_member_calibration_records':len(expected_pairs),
                 'validated_e6_member_calibration_records':len(expected_pairs),
                 'required_e6_ensembles':len(successful),'validated_e6_ensembles':len(successful)}
 if any(summary.get(k)!=v for k,v in summary_counts.items()):raise EvidenceError('E6 native calibration replay summary counts differ from task records')
 if summary.get('e6_native_calibration_replay_complete',audit.get('e6_native_calibration_replay_complete')) is not True:raise EvidenceError('E6 native calibration replay is not marked complete')
 def digest_ok(x):return isinstance(x,str) and len(x)==64 and all(c in '0123456789abcdef' for c in x.lower())
 def native_file(rel,digest):
  if not isinstance(rel,str) or chr(92) in rel:raise EvidenceError('E6 native replay evidence path is invalid')
  q=PurePosixPath(rel)
  if q.is_absolute() or any(x in {'','.','..'} for x in q.parts) or q.parts[:3]!=('reports','calibration_replay','e6_member_native'):raise EvidenceError('E6 native replay path escapes its namespace')
  path=runtime.joinpath(*q.parts)
  if not path.is_file() or path.is_symlink() or not digest_ok(digest) or sha_file(path)!=digest:raise EvidenceError('E6 native replay evidence hash mismatch: '+rel)
  item={'path':rel,'sha256':digest,'bytes':path.stat().st_size}
  existing=[x for x in evidence if x.get('path')==rel]
  if existing and any(x.get('sha256')!=digest or x.get('bytes')!=item['bytes'] for x in existing):raise EvidenceError('conflicting E6 native replay evidence binding: '+rel)
  if not existing:evidence.append(item)
  return path
 from calibration_replay import load_replay
 for key,name in sorted(expected_pairs):
  row=member_map[(key,name)];doc=docs[key];comp=doc['members'][name]
  if row.get('status')!='validated' or row.get('validation_basis')!='fresh_native_calibration_scores':raise EvidenceError('E6 member native threshold was not independently recomputed: '+key+'/'+name)
  if row.get('fit_key')!=comp.get('fit_key') or row.get('pipeline_sha256')!=comp.get('pipeline_sha256'):raise EvidenceError('E6 member fit/pipeline binding differs: '+key+'/'+name)
  role_path=runtime/'cache/roles'/f'rep_{successful[key].get("rep")}.npz'
  if not role_path.is_file() or row.get('role_file_sha256')!=sha_file(role_path):raise EvidenceError('E6 member role-file hash differs from the current repetition roles: '+key+'/'+name)
  if not all(digest_ok(row.get(k)) for k in ('calibration_ids_sha256','X_cal_sha256','y_cal_sha256')):raise EvidenceError('E6 member native calibration row lacks calibration identity hashes: '+key+'/'+name)
  import numpy as np
  from calibration_replay import typed_sha
  try:
   with np.load(role_path,allow_pickle=False) as roles:
    role_values={k:np.asarray(roles[k]) for k in ('calibration_ids','X_cal','y_cal')}
  except Exception as exc:raise EvidenceError('E6 role file lacks readable calibration identities: '+key) from exc
  typed_fields={'calibration_ids_sha256':'calibration_ids','X_cal_sha256':'X_cal','y_cal_sha256':'y_cal'}
  for field,role_name in typed_fields.items():
   if row.get(field)!=typed_sha(role_values[role_name]):raise EvidenceError('E6 native calibration typed role hash mismatch: '+key+'/'+role_name)
  fingerprint=doc.get('posterior_fingerprint')
  if not isinstance(fingerprint,dict):raise EvidenceError('E6 member comparison lacks role fingerprint: '+key)
  for fp_field,role_name in (('calibration_ids_sha256','calibration_ids'),('X_cal_sha256','X_cal'),('y_cal_sha256','y_cal')):
   raw_hash=sha_bytes(np.ascontiguousarray(role_values[role_name]).tobytes())
   if fingerprint.get(fp_field)!=raw_hash:raise EvidenceError('E6 comparison calibration fingerprint differs from current roles: '+key+'/'+fp_field)
  for field,want in (('comparison_path','member_comparisons.json'),('comparison_sha256',sha_file(evals[key][1])),
                     ('fit_ids_sha256',comp.get('fit_ids_sha256')),
                     ('role_membership_sha256',comp.get('role_membership_sha256')),
                     ('selected_params_sha256',comp.get('selected_params_sha256')),
                     ('provenance_group',comp.get('provenance_group'))):
   if want is not None and row.get(field)!=want:raise EvidenceError('E6 member native calibration source mismatch for '+field+': '+key+'/'+name)
  if row.get('class_order')!=list(range(7)) or row.get('alpha')!=0.1 or row.get('score_kind')!=comp.get('score_kind') or row.get('nonconformity_rule')!='1-p_true':raise EvidenceError('E6 member native calibration score policy differs: '+key+'/'+name)
  if row.get('calibration_n')!=10000:raise EvidenceError('E6 member native calibration count is not 10,000: '+key+'/'+name)
  try:
   q=float(row['native_threshold']);saved=float(comp['calibration_threshold']);n=int(row['calibration_n']);rank=int(row['rank_k'])
  except Exception as exc:raise EvidenceError('E6 member native threshold metadata is invalid: '+key+'/'+name) from exc
  if not math.isfinite(q) or not math.isclose(q,saved,rel_tol=0,abs_tol=1e-10) or rank!=int(math.ceil((n+1)*(1-float(row['alpha'])))):raise EvidenceError('E6 member native threshold/rank mismatch: '+key+'/'+name)
  mr=native_file(row.get('native_replay_metadata_path'),row.get('native_replay_metadata_sha256'))
  vr=native_file(row.get('native_replay_vector_path'),row.get('native_replay_vector_file_sha256'))
  replay=load_replay(mr.parent,row.get('native_replay_identity'))
  if int(replay.get('metadata',{}).get('calibration_n',-1))!=n or int(replay.get('rank_k',-1))!=rank or not math.isclose(float(replay.get('metadata',{}).get('threshold',float('nan'))),q,rel_tol=0,abs_tol=1e-10):raise EvidenceError('E6 member native replay vector yields a different threshold: '+key+'/'+name)
  if row.get('native_replay_vector_sha256')!=replay.get('metadata',{}).get('nonconformity_sha256'):raise EvidenceError('E6 member native score-vector identity differs: '+key+'/'+name)
 for key,row in ensmap.items():
  doc=docs[key];ev=evals[key][0]
  if row.get('status')!='validated' or row.get('validation_basis')!='fresh_native_calibration_scores':raise EvidenceError('E6 ensemble native threshold was not independently recomputed: '+key)
  if row.get('mode')!=doc.get('mode') or row.get('member_order')!=list(order) or row.get('alpha')!=0.1 or row.get('calibration_n')!=10000:raise EvidenceError('E6 ensemble native calibration protocol differs: '+key)
  members=row.get('members')
  if not isinstance(members,list) or [m.get('member') for m in members]!=list(order):raise EvidenceError('E6 ensemble native member proof list is incomplete: '+key)
  for ref,name in zip(members,order):
   source=member_map[(key,name)]
   if ref.get('fit_key')!=source.get('fit_key') or ref.get('native_replay_identity')!=source.get('native_replay_identity') or ref.get('native_replay_metadata_sha256')!=source.get('native_replay_metadata_sha256') or ref.get('native_replay_vector_file_sha256')!=source.get('native_replay_vector_file_sha256'):raise EvidenceError('E6 ensemble does not bind its member native calibration proof: '+key+'/'+name)
  try:
   qnative=float(row['native_threshold']);qsaved=float(row['saved_threshold']);qprimary=float(row['primary_threshold']);qdoc=float(doc['ensemble_threshold']);qeval=float(ev.get('conformal_threshold',ev.get('threshold')))
  except Exception as exc:raise EvidenceError('E6 ensemble threshold fields are invalid: '+key) from exc
  if not all(math.isfinite(q) for q in (qnative,qsaved,qprimary,qdoc,qeval)) or not all(math.isclose(qnative,q,rel_tol=0,abs_tol=1e-10) for q in (qsaved,qprimary,qdoc,qeval)):raise EvidenceError('E6 native/saved/primary ensemble thresholds differ: '+key)
  if row.get('weights')!=doc.get('selected_weights') or row.get('comparison_sha256')!=sha_file(evals[key][1]):raise EvidenceError('E6 ensemble weights/comparison binding differs: '+key)
 return {'e6_native_calibration_replay_applicable':True,
         'required_e6_member_calibration_records':len(expected_pairs),'validated_e6_member_calibration_records':len(expected_pairs),
         'required_e6_ensembles':len(successful),'validated_e6_ensembles':len(successful),'e6_native_calibration_replay_complete':True}

def _calibration_replay_validation(runtime,expected=None):
 runtime=Path(runtime).resolve();report=runtime/'reports'/'CALIBRATION_REPLAY_AUDIT.json'
 if not report.is_file():raise EvidenceError('required independent calibration replay audit is missing')
 audit=load(report);regpath=runtime/'registry.json';tasks,required_physical,required_aliases,alias_sources=_calibration_replay_requirements(runtime)
 if audit.get('schema_version')!='lamost-calibration-replay-audit/1':raise EvidenceError('calibration replay audit schema is unsupported')
 if audit.get('registry_snapshot_sha256')!=sha_file(regpath):raise EvidenceError('calibration replay audit was produced from a different registry snapshot')
 policy=audit.get('policy',{});supervision=policy.get('supervision',{}) if isinstance(policy,dict) else {}
 if policy.get('alpha')!=0.1 or policy.get('class_order')!=list(range(7)) or policy.get('replay_reads_test_rows') is not False:raise EvidenceError('calibration replay policy must use alpha=0.1, fixed seven-class order, and no test rows')
 if supervision.get('wall_seconds')!=600 or supervision.get('rss_limit_bytes')!=10*1024**3 or supervision.get('external_supervision_required') is not True:raise EvidenceError('calibration replay must record its required external 600-second/10-GiB supervision policy')
 records=audit.get('records')
 if not isinstance(records,list):raise EvidenceError('calibration replay audit records are missing')
 physical_rows=[r for r in records if isinstance(r,dict) and r.get('status') in {'validated','mismatch','unavailable'} and 'fit_key' in r]
 alias_rows=[r for r in records if isinstance(r,dict) and r.get('status') in {'inherited','mismatch','unavailable'} and 'source_key' in r]
 pmap={};amap={}
 for r in physical_rows:
  k=r.get('task_key')
  if not isinstance(k,str) or k in pmap:raise EvidenceError('calibration replay physical record keys are invalid or duplicated')
  pmap[k]=r
 for r in alias_rows:
  k=r.get('task_key')
  if not isinstance(k,str) or k in amap:raise EvidenceError('calibration replay alias record keys are invalid or duplicated')
  amap[k]=r
 if set(pmap)!=required_physical:raise EvidenceError(f'calibration replay physical coverage differs from successful registry evaluations: expected={len(required_physical)} observed={len(pmap)}')
 if set(amap)!=required_aliases:raise EvidenceError(f'calibration replay alias coverage differs from successful registry aliases: expected={len(required_aliases)} observed={len(amap)}')
 pc=collections.Counter(r.get('status') for r in pmap.values());ac=collections.Counter(r.get('status') for r in amap.values())
 counts={'required_physical':len(required_physical),'successful_physical':pc['validated'],'mismatch_physical':pc['mismatch'],'unavailable_physical':pc['unavailable'],'required_aliases':len(required_aliases),'inherited_aliases':ac['inherited'],'mismatch_aliases':ac['mismatch'],'unavailable_aliases':ac['unavailable']}
 if any(audit.get(k)!=v for k,v in counts.items()):raise EvidenceError('calibration replay audit summary counts differ from task-level records')
 if audit.get('q_replay_coverage_complete') is not True or audit.get('independent_q_recomputed') is not True or pc['validated']!=len(required_physical) or ac['inherited']!=len(required_aliases) or pc['mismatch'] or pc['unavailable'] or ac['mismatch'] or ac['unavailable']:
  raise EvidenceError('calibration replay q coverage is incomplete or has mismatched/unavailable successful routes')
 if audit.get('complete') is not False or audit.get('complete_requires_external_supervision_receipt') is not True:
  raise EvidenceError('auditor report must remain immutable and unqualified until external supervision is verified')
 evidence=[];physical_projection=[];alias_projection=[]
 from calibration_replay import load_replay
 def hexsha(v):return isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v.lower())
 def evidence_path(rel):
  if not isinstance(rel,str) or not rel or chr(92) in rel:raise EvidenceError('calibration replay evidence path is not a normalized relative path')
  q=PurePosixPath(rel)
  if q.is_absolute() or any(x in {'','..'} for x in q.parts) or q.parts[0]!='artifacts':raise EvidenceError('calibration replay evidence path escapes artifacts')
  dest=runtime.joinpath(*q.parts)
  if not dest.is_file() or dest.is_symlink():raise EvidenceError('calibration replay evidence file is missing or unsafe: '+rel)
  return dest
 for key in sorted(required_physical):
  r=pmap[key];t=tasks[key]
  if r.get('status')!='validated' or r.get('fit_key')!=t.get('fit_key'):raise EvidenceError('calibration replay physical row is not tied to its registry fit: '+key)
  identity=r.get('identity')
  if not isinstance(identity,str) or not identity or '/' in identity or chr(92) in identity or identity in {'.','..'}:raise EvidenceError('calibration replay identity is unsafe: '+key)
  base=f'artifacts/calibration_replay/{identity}';mrel=r.get('metadata_path');vrel=r.get('nonconformity_path')
  if mrel!=base+'/metadata.json' or vrel!=base+'/nonconformity.npz':raise EvidenceError('calibration replay evidence paths do not match identity: '+key)
  mp=evidence_path(mrel);vp=evidence_path(vrel)
  for field,path in (('metadata_sha256',mp),('nonconformity_file_sha256',vp)):
   if not hexsha(r.get(field)) or sha_file(path)!=r[field]:raise EvidenceError('calibration replay evidence file hash mismatch: '+key+'/'+field)
  if not all(hexsha(r.get(f)) for f in ('pipeline_sha256','role_file_sha256','calibration_ids_sha256','X_cal_sha256','y_cal_sha256','nonconformity_sha256')):raise EvidenceError('calibration replay row lacks bound source/vector hashes: '+key)
  meta=load(mp)
  mapping={'identity':'identity','pipeline_sha256':'pipeline_sha256','role_file_sha256':'role_file_sha256','calibration_ids_sha256':'calibration_ids_sha256','X_cal_sha256':'X_cal_sha256','y_cal_sha256':'y_cal_sha256','score_kind':'score_kind','nonconformity_rule':'nonconformity_rule','alpha':'alpha','class_order':'class_order','calibration_n':'calibration_n','rank_k':'rank_k','nonconformity_sha256':'nonconformity_sha256','nonconformity_file_sha256':'nonconformity_file_sha256'}
  if any(meta.get(m)!=r.get(k) for k,m in mapping.items()):raise EvidenceError('calibration replay metadata identity/role/score/vector fields differ: '+key)
  if r.get('class_order')!=list(range(7)) or r.get('alpha')!=0.1 or r.get('score_kind') not in {'probability','margin'}:raise EvidenceError('calibration replay class order, alpha, or score kind is invalid: '+key)
  if r.get('class_order_source') not in {'frozen models_flexible._FlexibleModel class_models indexed 0..6','frozen ARFDensityModel CLASS_IDS order','frozen GaussianDensityModel CLASS_IDS order','frozen ClassifierModel estimator.classes_'}:raise EvidenceError('calibration replay class order lacks independent model evidence: '+key)
  if meta.get('rule')!=r.get('nonconformity_rule') or meta.get('rank')!='ceil((n+1)*(1-alpha)); partition(k-1)':raise EvidenceError('calibration replay identity rule/rank definition differs: '+key)
  identity_fields=('pipeline_sha256','role_file_sha256','calibration_ids_sha256','X_cal_sha256','y_cal_sha256','score_kind','rule','class_order','alpha','rank','helper_sha256','dependencies')
  if any(field not in meta for field in identity_fields):raise EvidenceError('calibration replay identity payload is incomplete: '+key)
  identity_payload={field:meta[field] for field in identity_fields}
  if hashlib.sha256(json.dumps(identity_payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=identity:raise EvidenceError('calibration replay identity does not bind its metadata payload: '+key)
  rep=t.get('rep');role_path=runtime/'cache'/'roles'/f'rep_{rep}.npz'
  if not role_path.is_file() or sha_file(role_path)!=r['role_file_sha256']:raise EvidenceError('calibration replay role file identity changed: '+key)
  eval_path=runtime/'artifacts'/key/'evaluation.json';eval_doc=load(eval_path) if eval_path.is_file() else None
  deps=meta.get('dependencies',{})
  if not isinstance(eval_doc,dict) or deps.get('source_evaluation_sha256')!=sha_file(eval_path):raise EvidenceError('calibration replay source evaluation identity is missing or changed: '+key)
  if eval_doc.get('fit_key')!=r.get('fit_key') or eval_doc.get('pipeline_sha256')!=r.get('pipeline_sha256'):raise EvidenceError('calibration replay selected fit/pipeline differs from its saved evaluation: '+key)
  saved_eval_threshold=eval_doc.get('threshold',eval_doc.get('conformal_threshold'))
  if saved_eval_threshold is None or not math.isclose(float(saved_eval_threshold),float(r.get('saved_threshold')),rel_tol=0,abs_tol=1e-10):raise EvidenceError('calibration replay saved threshold differs from evaluation.json: '+key)
  calibration_path=eval_path.with_name('calibration.json');cal_sha=sha_file(calibration_path) if calibration_path.is_file() else None
  if deps.get('calibration_json_sha256')!=cal_sha:raise EvidenceError('calibration replay calibration.json source identity is missing or changed: '+key)
  if cal_sha:
   cal_doc=load(calibration_path);cal_threshold=cal_doc.get('threshold',cal_doc.get('conformal_threshold'))
   if cal_doc.get('fit_key')!=r.get('fit_key') or cal_doc.get('pipeline_sha256')!=r.get('pipeline_sha256') or cal_doc.get('calibration_n')!=r.get('calibration_n') or cal_threshold is None or not math.isclose(float(cal_threshold),float(r.get('saved_threshold')),rel_tol=0,abs_tol=1e-10):raise EvidenceError('calibration replay saved calibration.json threshold/provenance differs: '+key)
  if r.get('nonconformity_rule')!=({'probability':'1-p_true','margin':'negative_margin'}[r['score_kind']]):raise EvidenceError('calibration replay nonconformity rule is invalid: '+key)
  try:
   n=int(r.get('calibration_n'));k=int(r.get('rank_k'));q_saved=float(r.get('saved_threshold'));q_recomputed=float(r.get('recomputed_threshold'));q_meta=float(meta.get('threshold'))
   expected_k=int(math.ceil((n+1)*(1-float(r.get('alpha')))))
  except Exception as e:raise EvidenceError('calibration replay quantile metadata is invalid: '+key) from e
  if n<=0 or k!=expected_k or not all(math.isfinite(q) for q in (q_saved,q_recomputed,q_meta)) or not math.isclose(q_saved,q_recomputed,rel_tol=0,abs_tol=1e-10) or not math.isclose(q_recomputed,q_meta,rel_tol=0,abs_tol=1e-10):raise EvidenceError('calibration replay saved/recomputed finite-sample threshold mismatch: '+key)
  loaded=load_replay(mp.parent,identity)
  if int(loaded['metadata']['calibration_n'])!=n or int(loaded['rank_k'])!=k or not math.isclose(float(loaded['metadata']['threshold']),q_recomputed,rel_tol=0,abs_tol=1e-10):raise EvidenceError('calibration replay vector independently recomputes a different threshold: '+key)
  evidence.append({'path':mrel,'sha256':r['metadata_sha256'],'bytes':mp.stat().st_size});evidence.append({'path':vrel,'sha256':r['nonconformity_file_sha256'],'bytes':vp.stat().st_size})
  physical_projection.append({'task_key':key,'fit_key':r['fit_key'],'identity':identity,'pipeline_sha256':r['pipeline_sha256'],'role_file_sha256':r['role_file_sha256'],'calibration_ids_sha256':r['calibration_ids_sha256'],'X_cal_sha256':r['X_cal_sha256'],'y_cal_sha256':r['y_cal_sha256'],'score_kind':r['score_kind'],'nonconformity_rule':r['nonconformity_rule'],'alpha':r['alpha'],'class_order':r['class_order'],'class_order_source':r.get('class_order_source'),'calibration_n':n,'rank_k':k,'saved_threshold':q_saved,'recomputed_threshold':q_recomputed,'nonconformity_sha256':r['nonconformity_sha256'],'metadata_path':mrel,'metadata_sha256':r['metadata_sha256'],'nonconformity_path':vrel,'nonconformity_file_sha256':r['nonconformity_file_sha256']})
 for key in sorted(required_aliases):
  r=amap[key];t=tasks[key];physical_key=alias_sources[key];source=pmap.get(physical_key)
  if r.get('status')!='inherited' or r.get('source_key')!=t.get('source_key') or r.get('physical_source_key')!=physical_key or r.get('source_identity')!=(source or {}).get('identity') or r.get('threshold_match') is not True or r.get('inherited_from_physical') is not True:raise EvidenceError('calibration replay alias provenance or threshold inheritance mismatch: '+key)
  if t.get('rep')!=tasks[physical_key].get('rep'):raise EvidenceError('calibration replay alias does not inherit the physical source repetition: '+key)
  alias_eval=runtime/'artifacts'/key/'evaluation.json';physical_eval=runtime/'artifacts'/physical_key/'evaluation.json'
  if not alias_eval.is_file() or not physical_eval.is_file():raise EvidenceError('calibration replay alias/source evaluation JSON is missing: '+key)
  adoc=load(alias_eval);pdoc=load(physical_eval)
  for field in ('fit_key','pipeline_sha256','calibration_n','score_kind','calibration_score_kind','prediction_rule','nonconformity_rule','class_order'):
   if adoc.get(field)!=pdoc.get(field):raise EvidenceError('calibration replay alias score/calibration provenance differs for '+field+': '+key)
  aq=adoc.get('threshold',adoc.get('conformal_threshold'));pq=pdoc.get('threshold',pdoc.get('conformal_threshold'))
  if aq is None or pq is None or not math.isclose(float(aq),float(pq),rel_tol=0,abs_tol=1e-10):raise EvidenceError('calibration replay alias saved threshold differs from physical source: '+key)
  alias_projection.append({'task_key':key,'source_key':r['source_key'],'physical_source_key':physical_key,'source_identity':r['source_identity'],'threshold_match':True,'inherited_from_physical':True,'same_repetition':True,'evaluation_provenance_fields':['fit_key','pipeline_sha256','calibration_n','score_kind','calibration_score_kind','prediction_rule','nonconformity_rule','class_order']})
 e6_native_counts=_validate_e6_native_calibration_records(runtime,audit,tasks,evidence)
 counts.update(e6_native_counts)
 replay_audit_sha=sha_file(report);receipt_path=runtime/'reports'/'CALIBRATION_REPLAY_SUPERVISION.json'
 if not receipt_path.is_file():raise EvidenceError('externally supervised calibration replay receipt is missing')
 receipt=load(receipt_path)
 ledger_rel=audit.get('phase_ledger_path')
 if not isinstance(ledger_rel,str) or not ledger_rel.startswith('logs/operational/calibration_replay_phase_ledger_') or not ledger_rel.endswith('.jsonl'):
  raise EvidenceError('calibration replay audit has an invalid private phase-ledger path')
 ledger_path=(runtime/ledger_rel).resolve()
 if runtime not in ledger_path.parents or not ledger_path.is_file() or ledger_path.is_symlink():raise EvidenceError('calibration replay private phase ledger is missing or unsafe')
 ledger_bytes=ledger_path.read_bytes()
 if sha_bytes(ledger_bytes)!=audit.get('phase_ledger_sha256'):raise EvidenceError('calibration replay phase-ledger SHA differs from audit')
 from calibration_replay import verify_supervision_receipt
 accepted_prior_map=_accepted_prior_receipts(runtime,audit)
 prior_index_sha=audit.get('accepted_prior_receipts_index_sha256')
 if prior_index_sha:
  prior_index=runtime/'reports'/f'CALIBRATION_REPLAY_ACCEPTED_PRIOR_RECEIPTS_{audit.get("replay_run_nonce")}.json'
  if not prior_index.is_file():raise EvidenceError('accepted prior receipt index is missing')
  canonical_prior=hashlib.sha256(json.dumps(load(prior_index),sort_keys=True,separators=(',',':')).encode()).hexdigest()
  if canonical_prior!=prior_index_sha:raise EvidenceError('accepted prior receipt index changed after audit')
  evidence.append({'path':prior_index.relative_to(runtime).as_posix(),'sha256':sha_file(prior_index),'bytes':prior_index.stat().st_size})
 verification=verify_supervision_receipt(audit,receipt,replay_audit_sha,accepted_prior_receipts=accepted_prior_map,phase_ledger=ledger_bytes)
 if not verification.get('valid') or not verification.get('qualified_complete'):
  raise EvidenceError('external calibration replay supervision is invalid: '+str(verification.get('reasons')))
 receipt_sha=sha_file(receipt_path)
 qualification={'schema_version':'lamost-calibration-replay-qualification/1','generated_utc':audit.get('generated_utc'),
  'audit_path':'reports/CALIBRATION_REPLAY_AUDIT.json','audit_sha256':replay_audit_sha,
  'supervision_receipt_path':'reports/CALIBRATION_REPLAY_SUPERVISION.json','supervision_receipt_sha256':receipt_sha,
  'phase_ledger_sha256':audit.get('phase_ledger_sha256'),'accepted_prior_receipts_index_sha256':prior_index_sha,'registry_snapshot_sha256':audit['registry_snapshot_sha256'],
  'run_nonce':audit.get('replay_run_nonce'),**verification}
 qualification_path=runtime/'reports'/'CALIBRATION_REPLAY_QUALIFICATION.json'
 if not qualification_path.is_file() or any(load(qualification_path).get(k)!=v for k,v in qualification.items()):atomic_json(qualification_path,qualification)
 evidence.append({'path':'reports/CALIBRATION_REPLAY_SUPERVISION.json','sha256':receipt_sha,'bytes':receipt_path.stat().st_size})
 evidence.append({'path':'reports/CALIBRATION_REPLAY_QUALIFICATION.json','sha256':sha_file(qualification_path),'bytes':qualification_path.stat().st_size})
 info={'schema_version':'lamost-calibration-replay-finalization/1','report_path':'reports/CALIBRATION_REPLAY_AUDIT.json','report_sha256':replay_audit_sha,
  'supervision_receipt_path':'reports/CALIBRATION_REPLAY_SUPERVISION.json','supervision_receipt_sha256':receipt_sha,
  'qualification_path':'reports/CALIBRATION_REPLAY_QUALIFICATION.json','qualification_sha256':sha_file(qualification_path),
  'registry_snapshot_sha256':audit['registry_snapshot_sha256'],'run_nonce':audit.get('replay_run_nonce'),'accepted_prior_receipts_index_sha256':prior_index_sha,'counts':counts,
  'complete':True,'independent_q_recomputed':True,'physical_records':physical_projection,'alias_records':alias_projection,
  'evidence_files':sorted(evidence,key=lambda x:x['path']),'external_supervision_policy':{'wall_seconds':600,'rss_bytes':10*1024**3,
  'termination_grace_seconds':30,'required':True,'enforced_by_external_supervisor':True,'enforced_by_auditor':False}}
 if expected is not None and info!=expected:raise EvidenceError('cached calibration replay proof differs from current audit, vectors, thresholds, supervision, or registry')
 return info

def _preserve_calibration_replay_attempt(runtime):
 runtime=Path(runtime);reports=runtime/'reports';audit_path=reports/'CALIBRATION_REPLAY_AUDIT.json'
 if not audit_path.is_file():return None
 audit=load(audit_path);nonce=audit.get('replay_run_nonce')
 if not isinstance(nonce,str) or not nonce:return None
 private=runtime/'logs'/'operational'/'calibration_replay_history'/nonce
 public=reports/'calibration_replay_history'/nonce
 private.mkdir(parents=True,exist_ok=True);public.mkdir(parents=True,exist_ok=True)
 sources=[(audit_path,public/'audit.json'),(reports/'CALIBRATION_REPLAY_SUPERVISION.json',public/'supervision.json'),
  (reports/'CALIBRATION_REPLAY_QUALIFICATION.json',public/'qualification.json')]
 ledger_rel=audit.get('phase_ledger_path')
 if isinstance(ledger_rel,str):
  lp=(runtime/ledger_rel).resolve()
  if runtime in lp.parents and lp.is_file() and not lp.is_symlink():sources.append((lp,private/'phase_ledger.jsonl'))
 index=reports/f'CALIBRATION_REPLAY_ACCEPTED_PRIOR_RECEIPTS_{nonce}.json'
 if index.is_file():sources.append((index,public/'accepted_prior_receipts.json'))
 for src,dest in sources:
  if not src.is_file() or src.is_symlink():continue
  if dest.exists():
   if sha_file(src)!=sha_file(dest):raise EvidenceError('preserved calibration replay attempt path has conflicting bytes')
   continue
  try:os.link(src,dest)
  except OSError:shutil.copy2(src,dest)
 return {'nonce':nonce,'public_dir':public,'private_dir':private}

def _accepted_prior_receipts(runtime,audit,seen=None,depth=0):
 runtime=Path(runtime).resolve();seen=set() if seen is None else seen
 nonce=audit.get('replay_run_nonce')
 index_sha=audit.get('accepted_prior_receipts_index_sha256')
 if not index_sha:return {}
 if depth>12 or nonce in seen:raise EvidenceError('accepted prior calibration receipt history has a cycle or excessive depth')
 seen.add(nonce)
 index_path=runtime/'reports'/f'CALIBRATION_REPLAY_ACCEPTED_PRIOR_RECEIPTS_{nonce}.json'
 if not index_path.is_file() or index_path.is_symlink():raise EvidenceError('accepted prior receipt index is missing or unsafe')
 doc=load(index_path);canonical=hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 if canonical!=index_sha or doc.get('schema_version')!='lamost-calibration-replay-accepted-prior-receipts/1' or not isinstance(doc.get('entries'),list):
  raise EvidenceError('accepted prior receipt index digest/schema mismatch')
 from calibration_replay import verify_supervision_receipt
 mapping={}
 for row in doc['entries']:
  if not isinstance(row,dict):raise EvidenceError('accepted prior receipt entry is malformed')
  ident=row.get('identity');receipt_sha=row.get('receipt_sha256');prior_nonce=row.get('source_run_nonce')
  if not all(isinstance(x,str) and x for x in (ident,receipt_sha,prior_nonce)):raise EvidenceError('accepted prior receipt entry lacks identity/receipt/run')
  pub=runtime/'reports'/'calibration_replay_history'/prior_nonce
  priv=runtime/'logs'/'operational'/'calibration_replay_history'/prior_nonce
  prior_audit_path=pub/'audit.json';prior_receipt_path=pub/'supervision.json';ledger_path=priv/'phase_ledger.jsonl'
  if not prior_audit_path.is_file() or not prior_receipt_path.is_file() or not ledger_path.is_file():raise EvidenceError('accepted prior receipt evidence is not retained')
  prior_audit=load(prior_audit_path);prior_receipt=load(prior_receipt_path);prior_ledger=ledger_path.read_bytes()
  if sha_file(prior_receipt_path)!=receipt_sha or sha_file(prior_audit_path)!=prior_receipt.get('audit_sha256') or hashlib.sha256(prior_ledger).hexdigest()!=prior_audit.get('phase_ledger_sha256'):
   raise EvidenceError('accepted prior receipt history hash chain is invalid')
  prior_mapping=_accepted_prior_receipts(runtime,prior_audit,seen=set(seen),depth=depth+1)
  checked=verify_supervision_receipt(prior_audit,prior_receipt,sha_file(prior_audit_path),accepted_prior_receipts=prior_mapping,phase_ledger=prior_ledger)
  if not checked.get('valid') or not checked.get('qualified_complete'):raise EvidenceError('accepted prior supervision receipt is not fully qualified')
  prior_rows={r.get('identity') for r in prior_audit.get('records',[]) if isinstance(r,dict) and r.get('status')=='validated' and r.get('identity')}
  if ident not in prior_rows:raise EvidenceError('accepted prior receipt does not cover requested q identity')
  mapping.setdefault(receipt_sha,set()).add(ident)
 return mapping

def _prepare_prior_calibration_receipts(runtime,run_nonce):
 runtime=Path(runtime).resolve();reports=runtime/'reports'
 _preserve_calibration_replay_attempt(runtime)
 audit_path=reports/'CALIBRATION_REPLAY_AUDIT.json'
 if not audit_path.is_file():return None
 try:proof=_calibration_replay_validation(runtime)
 except Exception:return None
 entries=[]
 receipt_sha=proof.get('supervision_receipt_sha256')
 for row in proof.get('physical_records',[]):
  entries.append({'identity':row['identity'],'receipt_sha256':receipt_sha,'source_run_nonce':proof['run_nonce']})
 if not entries:return None
 doc={'schema_version':'lamost-calibration-replay-accepted-prior-receipts/1','source_run_nonce':proof['run_nonce'],
  'source_receipt_sha256':receipt_sha,'entries':sorted(entries,key=lambda x:x['identity'])}
 path=reports/f'CALIBRATION_REPLAY_ACCEPTED_PRIOR_RECEIPTS_{run_nonce}.json';atomic_json(path,doc)
 return path

def _run_artifact_audit(runtime):
 py=Path('/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python3')
 p=runtime/'source/audit_artifacts.py'
 try:
  run_nonce=uuid.uuid4().hex
  accepted_prior=_prepare_prior_calibration_receipts(runtime,run_nonce)
  from calibration_replay_supervisor import run as supervise
  receipt=supervise(runtime,py,p,run_nonce=run_nonce,accepted_prior_index=accepted_prior)
 except Exception as exc:raise EvidenceError('externally supervised calibration audit failed: '+str(exc)) from exc
 result=load(runtime/'reports/INCREMENTAL_ARTIFACT_AUDIT.json')
 if int(result.get('issue_count',-1))!=0:raise EvidenceError(f"incremental artifact audit has {result.get('issue_count')} issues; see INCREMENTAL_ARTIFACT_ISSUES.csv")
 if result.get('calibration_replay_required') is not True or result.get('threshold_quantile_recomputed') is not True:raise EvidenceError('full artifact audit did not certify complete calibration replay q recomputation')
 replay=_calibration_replay_validation(runtime)
 return {'result':result,'report_sha256':sha_file(runtime/'reports/INCREMENTAL_ARTIFACT_AUDIT.json'),'issues_sha256':sha_file(runtime/'reports/INCREMENTAL_ARTIFACT_ISSUES.csv'),'calibration_replay':replay,'full_calibration_replay_pass':True,'supervision_receipt_sha256':sha_file(runtime/'reports'/'CALIBRATION_REPLAY_SUPERVISION.json')}

def write_full_archive(root,runtime,fullpath,evidence,review_proof,expected_hashes,registry_records,review_manifest,public=None):
 root=Path(root).resolve();runtime=Path(runtime).resolve();fullpath=Path(fullpath)
 manifest_path=runtime/'manifests'/'cold_model_store_manifest.json'
 public=public if public is not None else public_registry(runtime)
 if manifest_path.exists():
  # Manifest presence is an explicit cold-storage commitment; fail closed on broken configuration.
  from cold_finalizer_adapter import load_cold_api,recover_uncommitted_renames,append_full_archive
  recover_uncommitted_renames(__import__(__name__),root,runtime)
  cold_api=load_cold_api(runtime)
  cold_store=cold_api.ColdModelStore.from_runtime(root,runtime)
  building=Path(cold_store.archive)
  if not building.is_file() or building.parent.resolve()!=root/'packages' or 'BUILDING' not in building.name.upper() or building.suffix.lower()!='.zip':
   raise EvidenceError('cold-model manifest exists but does not resolve to a regular BUILDING ZIP under migration-root packages')
  cold_doc=load(cold_store.manifest)
  cold_sha,_,_=cold_store._check_archive_manifest(cold_doc)
  readme=package_readme(str(fullpath),evidence,cold_models=True)
  entries=collect_full(root,runtime,readme,public,review_proof,expected_hashes,cold_store=cold_store,registry_records=registry_records,review_manifest=review_manifest)
  omissions=['Credentials/private keys/authentication, Harbor, PIDs/start ticks, worker/controller request/result/log receipts, root attempts/logs, and operational cleanup receipts are excluded.','Private per-phase process state/result receipts are excluded; scientific trial ledgers/configs/errors/models/data/outcomes are retained.','Historical E1 fitted models/per-test-row prediction arrays omitted from compact migration remain unavailable.','E1 baseline/project, final tables, and curated stopped recovery artifacts are included directly from verified EC2 trees; original E1 ZIP remains on EC2 but is not embedded. Operations/migration receipts, process state, private watcher logs, credentials, raw queue logs, and temporary stop-copy files are omitted.','The exact final report review candidate, agent audit receipt, immutable master-index snapshot, and review proof are included.','Existing cold-model payloads remain as prior ZIP members in the same archive; logical runtime artifact paths are recorded as hash-checked aliases and restored on extraction.']
  result=append_full_archive(__import__(__name__),cold_store,building,fullpath,entries,[],omissions,registry_records,cold_sha,expected_hashes,review_proof)
  atomic_json(Path(result['path']+'.receipt.json'),result)
  return result
 readme=package_readme(str(fullpath),evidence,cold_models=False)
 entries=collect_full(root,runtime,readme,public,review_proof,expected_hashes)
 omissions=['Credentials/private keys/authentication, Harbor, PIDs/start ticks, worker/controller request/result/log receipts, root attempts/logs, and operational cleanup receipts are excluded.','Private per-phase process state/result receipts are excluded; scientific trial ledgers/configs/errors/models/data/outcomes are retained.','Historical E1 fitted models/per-test-row prediction arrays omitted from the compact migration remain unavailable.','E1 baseline/project, final tables, and curated stopped recovery artifacts are included directly from verified EC2 trees; original E1 ZIP remains on EC2 but is not embedded.','The exact final report review candidate, agent audit receipt, immutable master-index snapshot, and review proof are included.']
 result=zipwrite(fullpath,entries,[],omissions,expected_source_sha256=expected_hashes,review_proof=review_proof)
 atomic_json(Path(result['path']+'.receipt.json'),result)
 return result

def finalize(root=ROOT,runtime=R):
 root=Path(root).resolve();runtime=Path(runtime).resolve();PACKAGES=root/'packages';REPORTS=runtime/'reports';PACKAGES.mkdir(parents=True,exist_ok=True);REPORTS.mkdir(parents=True,exist_ok=True)
 lock=(runtime/'finalize.lock').open('a+')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:return {'status':'finalizer_already_running'}
 from final_review import quick_wait,verify_pass,write_candidate,mark_invalidated,ReviewInvalidated
 pending_path=runtime/'EC2_COMPLETE_DELIVERY_PENDING.json';old=_valid_pending(pending_path,runtime)
 if old:return {**old,'status':'validated_pending_delivery_reused'}
 wait=quick_wait(runtime)
 if wait:return {**wait,'status':'report_ready_for_internal_audit' if wait.get('status')=='waiting_for_internal_report_review' else wait.get('status'),'observed_utc':now(),'project_complete':False}
 ready_path=runtime/'REPORT_READY_FOR_AUDIT.json';review_proof=None;expected_hashes=None;prior_full=None
 if ready_path.is_file():
  try:review_proof,expected_hashes=verify_pass(root,runtime)
  except ReviewInvalidated as e:
   invalid=mark_invalidated(runtime,str(e));return {'status':'report_audit_invalidated_refresh_required','observed_utc':now(),'project_complete':False,**invalid}
  except Exception as e:
   ready=load(ready_path);return {'status':'waiting_for_internal_report_audit','observed_utc':now(),'project_complete':False,'candidate_id':ready.get('candidate_id'),'reason':f'{type(e).__name__}: {e}'}
  cached=_resume_reviewed_report_state(runtime,review_proof)
  if cached is None:
   invalid=mark_invalidated(runtime,'cached report lacks the validated E4/E5 condition-findings builder, inputs, or output hashes')
   return {'status':'report_audit_invalidated_refresh_required','observed_utc':now(),'project_complete':False,**invalid}
  active=_active_project_processes()
  if active:return {'status':'waiting_for_terminal_work','observed_utc':now(),'project_complete':False,'reason':f'project controller/worker processes still active: {active[:6]}'}
  try:terminal=verify_terminal(root,runtime)
  except Exception as e:
   invalid=mark_invalidated(runtime,f'terminal registry changed or invalid: {type(e).__name__}: {e}');return {'status':'report_audit_invalidated_refresh_required','observed_utc':now(),'project_complete':False,**invalid}
  prior_full=cached.get('full_archive');evidence=cached['frozen_evidence'];source_freeze=cached['runtime_source_freeze'];audit=cached['artifact_audit'];index_info=cached['master_index'];report_info=cached['report_validation']
  try:
   expected_hashes=bind_case_index_after_review(root,runtime,report_info,expected_hashes)
   expected_hashes=bind_condition_findings_after_review(runtime,report_info,expected_hashes)
   expected_hashes=_verify_portable_test_gate(root,runtime,report_info.get('portable_test_gate'),expected_hashes)
  except Exception as e:
   invalid=mark_invalidated(runtime,f'overall case-index or condition-findings review binding changed or is missing: {type(e).__name__}: {e}');return {'status':'report_audit_invalidated_refresh_required','observed_utc':now(),'project_complete':False,**invalid}
  final_report=Path(cached['final_report_path'])
  if not final_report.is_file() or sha_file(final_report)!=cached.get('final_report_sha256'):
   invalid=mark_invalidated(runtime,'cached final report changed after report-validation phase');return {'status':'report_audit_invalidated_refresh_required','observed_utc':now(),'project_complete':False,**invalid}
  package_snapshot=portable_bundle_snapshot(root,runtime);package_fingerprint,package_fingerprint_inputs=finalization_fingerprint(root,runtime,package_snapshot)
  package_latch=begin_finalization_attempt(runtime,package_fingerprint,package_fingerprint_inputs)
  if package_latch.get('status')!='started':
   result={**package_latch,'observed_utc':now(),'project_complete':False}
   if package_latch.get('status')=='FINALIZATION_REVIEW_REQUIRED':_write_review_required_marker(runtime,result)
   else:atomic_json(runtime/'FINALIZATION_RESOURCE_BACKOFF.json',result)
   return result
  package_attempt_id=package_latch['attempt_id']
 else:
  attempt_id=None;portable_snapshot=None;attempt_fingerprint=None
  try:
   active=_active_project_processes()
   if active:raise GatePending(f'project controller/worker processes still active: {active[:6]}')
   terminal=verify_terminal(root,runtime)
   portable_snapshot=portable_bundle_snapshot(root,runtime)
   attempt_fingerprint,fingerprint_inputs=finalization_fingerprint(root,runtime,portable_snapshot)
   latch=begin_finalization_attempt(runtime,attempt_fingerprint,fingerprint_inputs)
   if latch.get('status')!='started':
    result={**latch,'observed_utc':now(),'project_complete':False}
    if latch.get('status')=='FINALIZATION_REVIEW_REQUIRED':_write_review_required_marker(runtime,result)
    else:atomic_json(runtime/'FINALIZATION_RESOURCE_BACKOFF.json',result)
    return result
   attempt_id=latch['attempt_id']
   evidence=verify_frozen(root,runtime);source_freeze=_check_freeze(runtime)
  except GatePending as e:
   result={'status':'waiting_for_terminal_work','observed_utc':now(),'reason':str(e),'project_complete':False};atomic_json(runtime/'FINALIZATION_WAITING.json',result);return result
  except PortableBundleError as e:
   result={'status':'portable_test_bundle_blocked','observed_utc':now(),'reason':f'{type(e).__name__}: {e}','project_complete':False,'full_artifact_audit_started':False};atomic_json(runtime/'PORTABLE_TEST_BUNDLE_BLOCKED.json',result);return result
  except Exception as e:
   latch_result=None
   if attempt_id:
    kind='memory' if is_resource_backoff(e) else None
    latch_result=finish_finalization_attempt(runtime,attempt_id,'operational_backoff' if kind else 'failed',f'{type(e).__name__}: {e}',kind)
   if latch_result and latch_result.get('status')=='FINALIZATION_REVIEW_REQUIRED':
    result={'status':'FINALIZATION_REVIEW_REQUIRED','observed_utc':now(),'project_complete':False,'reason':f'{type(e).__name__}: {e}',**latch_result};_write_review_required_marker(runtime,result);return result
   if latch_result and latch_result.get('status')=='finalization_resource_backoff':
    result={'status':'finalization_resource_backoff','observed_utc':now(),'project_complete':False,'reason':f'{type(e).__name__}: {e}',**latch_result};atomic_json(runtime/'FINALIZATION_RESOURCE_BACKOFF.json',result);return result
   result={'status':'frozen_evidence_blocked','observed_utc':now(),'reason':f'{type(e).__name__}: {e}','project_complete':False};atomic_json(runtime/'FINALIZATION_BLOCKED.json',result);return result
  state={'status':'validating_final_artifacts','phase':'portable_test_suite','observed_utc':now(),'terminal':terminal,'frozen_evidence':evidence,'runtime_source_freeze':source_freeze,'finalization_attempt_id':attempt_id,'finalization_fingerprint_sha256':attempt_fingerprint};atomic_json(runtime/'finalizer_state.json',state)
  try:
   portable_gate=run_portable_test_bundle(root,runtime,portable_snapshot)
   portable_summary=_portable_test_gate_summary(runtime,portable_gate)
   audit=_run_artifact_audit(runtime)
   index_info=_export_master_index(runtime)
   report_info=prepare_report_phase(root,runtime,terminal)
   report_info['portable_test_gate']=portable_summary
   report_result_path=runtime/'reports'/'report_result.json';report_result_doc=load(report_result_path)
   report_result_doc['portable_test_gate']=portable_summary;atomic_json(report_result_path,report_result_doc)
   report_info['report_result']=report_result_doc;report_info['report_result_sha256']=sha_file(report_result_path)
   case_index_info=publish_overall_case_index(root,runtime)
   case_result_info=bind_overall_case_index_report(runtime,case_index_info)
   report_info['overall_case_index']=case_index_info;report_info['case_index_bound_report_result']=case_result_info
   final_report=make_final_report(root,runtime,terminal,evidence)
   append_overall_case_index_report(final_report,case_index_info);append_calibration_replay_report(final_report,audit['calibration_replay'])
   state.update({'phase':'reports_validated','observed_utc':now(),'artifact_audit':audit,'master_index':index_info,'report_validation':report_info,'portable_test_gate':portable_summary,'final_report_path':str(final_report),'final_report_sha256':sha_file(final_report)});atomic_json(runtime/'finalizer_state.json',state)
   ready,manifest=write_candidate(root,runtime)
   state.update({'status':'report_ready_for_internal_audit','phase':'awaiting_report_audit','observed_utc':now(),'review_candidate_id':ready['candidate_id'],'review_manifest_path':ready['manifest_path'],'review_manifest_sha256':ready['manifest_sha256']});atomic_json(runtime/'finalizer_state.json',state)
   finish_finalization_attempt(runtime,attempt_id,'passed',extra={'portable_test_receipt_sha256':portable_summary['receipt_sha256'],'review_candidate_id':ready['candidate_id']})
   return {'status':'report_ready_for_internal_audit','observed_utc':now(),'project_complete':False,'candidate_id':ready['candidate_id'],'manifest_path':ready['manifest_path'],'manifest_sha256':ready['manifest_sha256'],'review_receipt_path':str(runtime/'REPORT_AUDIT_RECEIPT.json'),'portable_test_gate':portable_summary}
  except Exception as e:
   kind=getattr(e,'resource_kind',None)
   resource_hold=is_resource_backoff(e)
   latch_result=finish_finalization_attempt(runtime,attempt_id,'operational_backoff' if resource_hold else 'failed',f'{type(e).__name__}: {e}',kind or ('resource' if resource_hold else None),extra={'portable_test_receipt_sha256':locals().get('portable_summary',{}).get('receipt_sha256')})
   if latch_result.get('status')=='FINALIZATION_REVIEW_REQUIRED':
    result={'status':'FINALIZATION_REVIEW_REQUIRED','observed_utc':now(),'project_complete':False,'reason':f'{type(e).__name__}: {e}',**latch_result};_write_review_required_marker(runtime,result);return result
   if latch_result.get('status')=='finalization_resource_backoff':
    result={'status':'finalization_resource_backoff','observed_utc':now(),'project_complete':False,'reason':f'{type(e).__name__}: {e}',**latch_result};atomic_json(runtime/'FINALIZATION_RESOURCE_BACKOFF.json',result);return result
   result={'status':'artifact_or_report_validation_blocked','observed_utc':now(),'reason':f'{type(e).__name__}: {e}','artifact_audit':locals().get('audit'),'project_complete':False,'finalization_failure_fingerprint_sha256':attempt_fingerprint};atomic_json(runtime/'FINALIZATION_BLOCKED.json',result);return result
 state={'status':'internal_report_review_passed_packaging','phase':'archive_packaging','observed_utc':now(),'terminal':terminal,'frozen_evidence':evidence,'runtime_source_freeze':source_freeze,'artifact_audit':audit,'master_index':index_info,'report_validation':report_info,'review_candidate_id':review_proof['candidate_id'],'report_review_proof':review_proof,'final_report_path':str(final_report),'final_report_sha256':sha_file(final_report),'full_archive':prior_full};atomic_json(runtime/'finalizer_state.json',state)
 full=_resume_full(runtime,review_proof);blocker=None;tag=stamp()
 package_error=None;package_resource_kind=None
 if full is None:
  fullpath=unique_path(PACKAGES,'LAMOST_ALL_EXPERIMENTS',tag,'.zip')
  try:
   actual_registry=load(runtime/'registry.json');registry_records={t.get('key'):t for t in actual_registry.get('tasks',[]) if t.get('key')}
   ready_doc=load(runtime/'REPORT_READY_FOR_AUDIT.json');review_manifest=load(ready_doc['manifest_path'])
   public=public_registry(runtime)
   full=write_full_archive(root,runtime,fullpath,evidence,review_proof,expected_hashes,registry_records,review_manifest,public)
  except InsufficientSpace as e:
   blocker=str(e);package_error=e;package_resource_kind='storage'
  except Exception as e:
   if isinstance(e,EvidenceError) and ('reviewed source changed' in str(e) or 'mutated during streaming' in str(e)):
    finish_finalization_attempt(runtime,package_attempt_id,'failed',f'{type(e).__name__}: {e}',extra={'phase':'full_archive'})
    invalid=mark_invalidated(runtime,str(e));return {'status':'report_audit_invalidated_refresh_required','observed_utc':now(),'project_complete':False,**invalid}
   blocker=f'{type(e).__name__}: {e}';package_error=e
   if is_resource_backoff(e):package_resource_kind='resource'
 smallpath=unique_path(PACKAGES,'LAMOST_FINAL_REPORTS_TABLES',tag,'.zip')
 try:
  remote='w7-ec2:'+str(smallpath);entries=_small_entries(root,runtime,full,blocker,remote,review_proof,expected_source_sha256=expected_hashes)
  manifest={'created_utc':now(),'files':[{'path':x.member,'bytes':size(x),'sha256':hashent(x),'category':x.category} for x in entries],'full_archive':full,'full_archive_blocker':blocker,'bootstrap':False,'report_review':review_proof}
  small=_small_zip(smallpath,entries,manifest,expected_hashes,review_proof);atomic_json(Path(small['path']+'.receipt.json'),small)
 except Exception as e:
  if isinstance(e,EvidenceError) and ('reviewed source changed' in str(e) or 'mutated during streaming' in str(e)):
   finish_finalization_attempt(runtime,package_attempt_id,'failed',f'{type(e).__name__}: {e}',extra={'phase':'small_archive'})
   invalid=mark_invalidated(runtime,str(e));return {'status':'report_audit_invalidated_refresh_required','observed_utc':now(),'project_complete':False,**invalid}
  package_error=e
  if is_resource_backoff(e):package_resource_kind=getattr(e,'resource_kind',None) or 'resource'
  latch_result=finish_finalization_attempt(runtime,package_attempt_id,'operational_backoff' if package_resource_kind else 'failed',f'{type(e).__name__}: {e}',package_resource_kind,extra={'phase':'small_archive','full_archive':full,'full_archive_blocker':blocker})
  if latch_result.get('status')=='FINALIZATION_REVIEW_REQUIRED':
   result={'status':'FINALIZATION_REVIEW_REQUIRED','observed_utc':now(),'project_complete':False,'reason':f'{type(e).__name__}: {e}',**latch_result};_write_review_required_marker(runtime,result);return result
  result={'status':'small_delivery_blocked','observed_utc':now(),'reason':f'{type(e).__name__}: {e}','full_archive':full,'full_archive_blocker':blocker,'project_complete':False,**latch_result};atomic_json(runtime/'FINALIZATION_BLOCKED.json',result);return result
 if full is not None:
  pending={'status':'delivery_pending_on_laptop','project_complete':False,'observed_utc':now(),'terminal_registry':terminal,'frozen_evidence':evidence,'runtime_source_freeze':source_freeze,'artifact_audit':audit,'master_index':index_info,'report_validation':report_info,'report_review':review_proof,'final_report':{'path':str(final_report),'bytes':final_report.stat().st_size,'sha256':sha_file(final_report)},'full_archive':full,'full_archive_blocker':None,'small_delivery_zip':small,'laptop_delivery_directory':r'D:\LAMOST_Overall_EC2_Handoff_20261023','laptop_copy_command':f'scp w7-ec2:{smallpath} "D:\\LAMOST_Overall_EC2_Handoff_20261023\\"','laptop_copy_verified':False,'project_complete_claim_permitted':False,'notes':['Verify byte size and SHA-256 after copying the compact ZIP to the existing laptop delivery directory.','Full archive includes verified E1 project and baseline files directly; original wrap-up ZIP is preserved on EC2 and checksum-verified, but not embedded because it contains excluded operational receipts.','Historical E1 fitted models and per-test-row prediction arrays omitted from migration remain unavailable.','Internal report audit receipt and review proof bind final report, main tables, figures, frozen plan/source, terminal outcomes, and artifact audit.']}
  atomic_json(pending_path,pending);atomic_json(runtime/'finalizer_state.json',{**state,'status':pending['status'],'phase':'delivery_pending_on_laptop','observed_utc':now(),'full_archive':full,'small_delivery_zip':small})
 else:
  pending={'status':'full_archive_blocked_small_zip_valid','project_complete':False,'observed_utc':now(),'report_review':review_proof,'full_archive':None,'full_archive_blocker':blocker,'small_delivery_zip':small,'laptop_delivery_directory':r'D:\\LAMOST_Overall_EC2_Handoff_20261023','laptop_copy_command':f'scp w7-ec2:{smallpath} "D:\\LAMOST_Overall_EC2_Handoff_20261023\\"','laptop_copy_verified':False,'project_complete_claim_permitted':False};atomic_json(pending_path,pending)
 package_status=('operational_backoff' if package_resource_kind else 'failed') if full is None else 'passed'
 package_reason=str(package_error) if package_error else None
 package_kind=package_resource_kind if package_status=='operational_backoff' else None
 package_latch_result=finish_finalization_attempt(runtime,package_attempt_id,package_status,package_reason,package_kind,
  extra={'full_archive':full,'small_delivery_zip':small,'full_archive_blocker':blocker})
 if package_latch_result.get('status')=='FINALIZATION_REVIEW_REQUIRED':
  required={'status':'FINALIZATION_REVIEW_REQUIRED','observed_utc':now(),'project_complete':False,'reason':package_reason or 'bounded operational packaging attempts exhausted',**package_latch_result}
  _write_review_required_marker(runtime,required);return required
 if package_status=='operational_backoff':
  pending.update({'status':'full_archive_blocked_small_zip_valid','project_complete':False,'finalization_resource_backoff':package_latch_result})
  atomic_json(pending_path,pending)
 return pending
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--self-test',action='store_true');ap.add_argument('--check-only',action='store_true');ap.add_argument('--clear-failure-latch',action='store_true');ap.add_argument('--reason');a=ap.parse_args()
 if a.clear_failure_latch:
  print(json.dumps(clear_finalization_latch(R,a.reason),indent=2));return 0
 if a.reason is not None:ap.error('--reason requires --clear-failure-latch')
 if a.self_test:print(json.dumps(self_test(),indent=2));return 0
 if a.check_only:
  print(json.dumps({'terminal':verify_terminal(),'frozen_evidence':verify_frozen(),'runtime_source_freeze':_check_freeze(R)},indent=2));return 0
 result=finalize();print(json.dumps(result,indent=2,default=str));return 0 if result.get('status') in {'delivery_pending_on_laptop','full_archive_blocked_small_zip_valid','validated_pending_delivery_reused','report_ready_for_internal_audit','report_audit_invalidated_refresh_required','waiting_for_internal_report_audit','waiting_for_terminal_work'} else 2
if __name__=='__main__':raise SystemExit(main())



