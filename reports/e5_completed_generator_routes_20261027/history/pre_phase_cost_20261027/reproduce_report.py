#!/usr/bin/env python3
"""Read-only descriptive E5 route comparison from registry and aggregate evaluation JSON."""
import csv, hashlib, json, math, statistics, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023')
RT=ROOT/'runtime_20261025'
OUT=RT/'reports'/'e5_completed_generator_routes_20261027'
SOURCE=RT/'source'/'reporting.py'
OUT.mkdir(parents=True,exist_ok=True)
FAMILIES=('gmm','copula','chow_liu')
LEARNERS=('logistic','hist_gb')
REPS=(1,2,3)
NOISE=(('feature_noise',0.05),('feature_noise',0.10),('feature_noise',0.20),
       ('missingness',0.05),('missingness',0.10),('missingness',0.20),
       ('label_noise',0.05),('label_noise',0.10),('label_noise',0.20))
LABELS=('A','F','G','K','M','GALAXY','QSO')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def write_csv(path,rows,fields=None):
    if fields is None:
        fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def num(x):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(float(x)): return None
    return float(x)

def stats(vals):
    x=[float(v) for v in vals if v is not None and math.isfinite(float(v))]
    return {'n':len(x),'mean':statistics.mean(x) if x else None,
            'sample_sd':statistics.stdev(x) if len(x)>1 else None}

def task_outcome(t):
    o=t.get('outcome')
    if isinstance(o,dict): return o.get('status') or o.get('outcome') or t.get('status')
    return o or t.get('status')

def direct_key(rep,family,condition):
    return f'e5/rep_{rep}/eval/direct/{family}/{condition}'

def synth_key(rep,family,learner,condition):
    if condition=='clean':
        return f'e5/rep_{rep}/eval/synthetic/{family}/{learner}/clean'
    return f'e5/rep_{rep}/eval/synthetic/{learner}/{condition}'

def condition_for(mechanism,rate,family=None):
    if mechanism=='clean': return 'clean'
    suffix=f'_{family}' if family is not None else ''
    return f'{mechanism}_{int(round(float(rate)*100)):02d}{suffix}'

def planned_key(route,rep,family,mechanism,rate,learner=None):
    if mechanism=='clean': cond='clean'
    else: cond=condition_for(mechanism,rate,family if route=='synthetic' else None)
    return direct_key(rep,family,cond) if route=='direct' else synth_key(rep,family,learner,cond)

regpath=RT/'registry.json'; reg=json.loads(regpath.read_text())
registry={str(t['key']):t for t in reg.get('tasks',[]) if isinstance(t,dict) and isinstance(t.get('key'),str)}
input_hashes={'registry.json':sha(regpath)}
planned=[]
for rep in REPS:
 for family in FAMILIES:
  for mechanism,rate in [('clean',None),*NOISE]:
   planned.append(('direct',rep,family,None,mechanism,rate))
   for learner in LEARNERS: planned.append(('synthetic',rep,family,learner,mechanism,rate))
assert len(planned)==270
metric_by_key={}; availability=[]; eval_path_by_key={}
for route,rep,family,learner,mechanism,rate in planned:
    key=planned_key(route,rep,family,mechanism,rate,learner)
    rec=registry.get(key)
    status='missing_registry_record'; reason='planned key absent from registry'; validation_sha=None
    eval_obj=None; eval_path=None
    if rec is not None:
        outcome=task_outcome(rec)
        status=str(outcome)
        reason=rec.get('reason') or rec.get('unavailability_reason') or rec.get('failure_raw_reason')
        result=rec.get('result') if isinstance(rec.get('result'),dict) else {}
        validation=result.get('validation') if isinstance(result.get('validation'),dict) else rec.get('validation')
        ev_path=(RT/'artifacts'/key/'evaluation.json').resolve()
        if RT.joinpath('artifacts').resolve() not in ev_path.parents:
            raise RuntimeError('artifact key escaped runtime artifacts root')
        eval_path=ev_path
        if status=='successful':
            if not isinstance(validation,dict) or validation.get('status')!='validated':
                status='invalid_validation_metadata'; reason='task outcome successful but no validated evaluation record'
            elif validation.get('task_key') not in (None,key):
                status='invalid_validation_identity'; reason='validation task key mismatch'
            elif not ev_path.is_file():
                status='missing_evaluation_json'; reason='validated evaluation JSON absent'
            else:
                expected=(validation.get('files') or {}).get('evaluation.json')
                actual=sha(ev_path)
                validation_sha=(expected==actual) if expected else None
                if expected and actual!=expected:
                    status='evaluation_sha_mismatch'; reason='saved evaluation JSON differs from registry validation hash'
                elif not expected:
                    status='evaluation_hash_unrecorded'; reason='no evaluation.json SHA in registry validation'
                else:
                    eval_obj=json.loads(ev_path.read_text())
                    if eval_obj.get('task_key')!=key:
                        status='evaluation_identity_mismatch'; reason='evaluation task key mismatch'
                    elif int(eval_obj.get('experiment',-1))!=5:
                        status='evaluation_experiment_mismatch'; reason='evaluation experiment is not E5'
                    else:
                        metric_by_key[key]=eval_obj
                        status='successful_validated'
                        reason=None
        if validation_sha is True and eval_path: input_hashes[str(eval_path.relative_to(RT))]=sha(eval_path)
    availability.append({'planned_route':route,'rep':rep,'generator_family':family,
      'downstream_learner':learner,'mechanism':mechanism,'rate':rate,'task_key':key,
      'registry_record_present':rec is not None,'registry_kind':rec.get('kind') if rec else None,
      'registry_status':rec.get('status') if rec else None,'registry_outcome':task_outcome(rec) if rec else None,
      'validation_state':rec.get('validation_state') if rec else None,'validation_sha_match':validation_sha,
      'evaluation_json':str(eval_path.relative_to(RT)) if eval_path else None,
      'availability_status':status,'unavailability_reason':reason})
write_csv(OUT/'planned_case_availability.csv',availability)
# Require route pairing keys to be enumerated even where one side is unavailable.
def metric(key,name):
    ev=metric_by_key.get(key)
    return num(ev.get(name)) if ev else None
def cls_metric(key,c,field):
    ev=metric_by_key.get(key)
    if not ev: return None
    v=(ev.get('per_class') or {}).get(str(c),{})
    return num(v.get(field)) if isinstance(v,dict) else None

comparisons=[]
class_comparisons=[]
for rep in REPS:
 for family in FAMILIES:
  for learner in LEARNERS:
   clean_d=direct_key(rep,family,'clean')
   clean_s=synth_key(rep,family,learner,'clean')
   for mechanism,rate in [('clean',None),*NOISE]:
    dkey=planned_key('direct',rep,family,mechanism,rate)
    skey=planned_key('synthetic',rep,family,mechanism,rate,learner)
    row={'rep':rep,'generator_family':family,'downstream_learner':learner,
      'mechanism':mechanism,'rate':rate,'direct_task_key':dkey,'synthetic_task_key':skey,
      'direct_status':next(a['availability_status'] for a in availability if a['task_key']==dkey),
      'synthetic_status':next(a['availability_status'] for a in availability if a['task_key']==skey),
      'direct_clean_task_key':clean_d,'synthetic_clean_task_key':clean_s,
      'direct_clean_status':next(a['availability_status'] for a in availability if a['task_key']==clean_d),
      'synthetic_clean_status':next(a['availability_status'] for a in availability if a['task_key']==clean_s)}
    for m in ('balanced_accuracy','coverage','set_size'):
      dv=metric(dkey,m); sv=metric(skey,m); dc=metric(clean_d,m); sc=metric(clean_s,m)
      row[f'direct_{m}']=dv; row[f'synthetic_{m}']=sv
      row[f'synthetic_minus_direct_{m}']=(sv-dv) if sv is not None and dv is not None else None
      if mechanism!='clean':
        row[f'direct_corruption_change_{m}']=(dv-dc) if dv is not None and dc is not None else None
        row[f'synthetic_corruption_change_{m}']=(sv-sc) if sv is not None and sc is not None else None
        row[f'synthetic_minus_direct_change_{m}']=(row[f'synthetic_corruption_change_{m}']-row[f'direct_corruption_change_{m}']) if row[f'direct_corruption_change_{m}'] is not None and row[f'synthetic_corruption_change_{m}'] is not None else None
      else:
        row[f'direct_corruption_change_{m}']=None
        row[f'synthetic_corruption_change_{m}']=None
        row[f'synthetic_minus_direct_change_{m}']=None
    comparisons.append(row)
    if mechanism!='clean':
     for c,label in enumerate(LABELS):
      cr={'rep':rep,'generator_family':family,'downstream_learner':learner,
          'mechanism':mechanism,'rate':rate,'class_id':c,'class_label':label,
          'direct_task_key':dkey,'synthetic_task_key':skey}
      for m in ('recall','coverage','set_size'):
       d=cls_metric(dkey,c,m); s=cls_metric(skey,c,m)
       d0=cls_metric(clean_d,c,m); s0=cls_metric(clean_s,c,m)
       cr[f'direct_corrupted_{m}']=d; cr[f'synthetic_corrupted_{m}']=s
       cr[f'synthetic_minus_direct_{m}']=(s-d) if s is not None and d is not None else None
       cr[f'direct_corruption_change_{m}']=(d-d0) if d is not None and d0 is not None else None
       cr[f'synthetic_corruption_change_{m}']=(s-s0) if s is not None and s0 is not None else None
       cr[f'synthetic_minus_direct_change_{m}']=(cr[f'synthetic_corruption_change_{m}']-cr[f'direct_corruption_change_{m}']) if cr[f'direct_corruption_change_{m}'] is not None and cr[f'synthetic_corruption_change_{m}'] is not None else None
      class_comparisons.append(cr)
write_csv(OUT/'matched_route_comparisons_by_repetition.csv',comparisons)
write_csv(OUT/'per_class_route_comparisons_by_repetition.csv',class_comparisons)

def summarize(records,groupfields,valuenames):
    groups=defaultdict(list)
    for r in records: groups[tuple(r.get(k) for k in groupfields)].append(r)
    out=[]
    for key,rows in sorted(groups.items(),key=lambda kv:tuple('' if x is None else str(x) for x in kv[0])):
        z=dict(zip(groupfields,key)); z['planned_repetitions']=3
        z['available_repetitions']=sum(any(r.get(v) is not None for v in valuenames) for r in rows)
        for v in valuenames:
            st=stats([r.get(v) for r in rows])
            z[v+'_n']=st['n']; z[v+'_mean']=st['mean']; z[v+'_sample_sd']=st['sample_sd']
        out.append(z)
    return out
corrupt_comps=[r for r in comparisons if r['mechanism']!='clean']
route_values=[]
for m in ('balanced_accuracy','coverage','set_size'):
 route_values.extend([f'direct_{m}',f'synthetic_{m}',f'synthetic_minus_direct_{m}',
     f'direct_corruption_change_{m}',f'synthetic_corruption_change_{m}',f'synthetic_minus_direct_change_{m}'])
route_summary=summarize(corrupt_comps,('generator_family','downstream_learner','mechanism','rate'),route_values)
write_csv(OUT/'matched_route_degradation_summary.csv',route_summary)
class_values=[]
for m in ('recall','coverage','set_size'):
 class_values.extend([f'direct_corrupted_{m}',f'synthetic_corrupted_{m}',f'synthetic_minus_direct_{m}',
     f'direct_corruption_change_{m}',f'synthetic_corruption_change_{m}',f'synthetic_minus_direct_change_{m}'])
class_summary=summarize(class_comparisons,('generator_family','downstream_learner','mechanism','rate','class_id','class_label'),class_values)
write_csv(OUT/'per_class_route_degradation_summary.csv',class_summary)

# Unique transitive dependency cost ledger. All elapsed values are wall-clock task spans; they are not attributed phase CPU or exclusive route costs.
selected_eval_keys={a['task_key'] for a in availability}
ancestor_counts=Counter()
closure=set()
for k in selected_eval_keys:
 stack=[k]; seen=set()
 while stack:
  x=stack.pop()
  if x in seen: continue
  seen.add(x); closure.add(x); ancestor_counts[x]+=1
  rec=registry.get(x)
  if rec:
   for d in rec.get('dependencies') or []: stack.append(str(d))
def phase_category(t):
    exp=t.get('experiment'); kind=t.get('kind'); route=t.get('route'); method=t.get('method')
    if exp==5 and kind=='fit' and route=='direct': return 'E5_generator_fit'
    if exp==5 and kind=='fit' and route=='synthetic': return 'E5_synthetic_downstream_fit'
    if exp==5 and kind=='generate': return 'E5_synthetic_generation'
    if exp==5 and kind in ('eval','ensemble'): return 'E5_evaluation_calibration_plus_test_inference'
    if kind=='alias' or ((t.get('result') or {}).get('result') or {}).get('compute_reused'): return 'shared_reused_evaluation_alias'
    if exp==3 and kind=='fit' and route=='synthetic': return 'shared_E3_synthetic_baseline_fit'
    if exp==3 and kind=='fit': return 'shared_E3_generator_fit'
    if exp==3 and kind=='generate': return 'shared_E3_generation'
    if exp==4 and kind in ('eval','alias'): return 'shared_E4_clean_control_evaluation'
    if exp==4 and kind=='fit': return 'shared_E4_control_fit'
    return f'other_dependency_exp{exp}_{kind}'
cost_rows=[]
for key in sorted(closure):
    t=registry.get(key)
    if not t: continue
    start=t.get('started_utc'); end=t.get('finished_utc')
    duration=None
    if start and end:
        from datetime import datetime
        try: duration=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()
        except Exception: pass
    result=t.get('result') if isinstance(t.get('result'),dict) else {}
    inner=result.get('result') if isinstance(result.get('result'),dict) else {}
    reused=inner.get('compute_reused')
    cost_rows.append({'task_key':key,'experiment':t.get('experiment'),'kind':t.get('kind'),
      'phase_category':phase_category(t),'route':t.get('route'),'method':t.get('method'),
      'generator':t.get('generator'),'rep':t.get('rep'),'condition':t.get('condition'),
      'status':t.get('status'),'outcome':task_outcome(t),'validation_state':t.get('validation_state'),
      'attempt_count':len(t.get('attempts') or []),'compute_reused':reused,
      'started_utc':start,'finished_utc':end,'elapsed_wall_seconds':duration,
      'timestamp_source':'registry task started_utc to finished_utc' if duration is not None else 'missing timestamps',
      'selected_evaluation_descendant_count':ancestor_counts[key],
      'shared_dependency':ancestor_counts[key]>1,
      'cost_interpretation':'unique task elapsed once; do not allocate shared task duration across consumers'})
write_csv(OUT/'dependency_cost_ledger.csv',cost_rows)
cost_groups=defaultdict(list)
for r in cost_rows: cost_groups[(r['phase_category'],r['experiment'],r['route'])].append(r)
cost_summary=[]
for (cat,exp,route),rs in sorted(cost_groups.items()):
 vals=[r['elapsed_wall_seconds'] for r in rs if r['elapsed_wall_seconds'] is not None]
 cost_summary.append({'phase_category':cat,'experiment':exp,'route':route,
  'unique_task_count':len(rs),'successful_task_count':sum(r['outcome']=='successful' for r in rs),
  'compute_reused_count':sum(r['compute_reused'] is True for r in rs),
  'measured_wall_span_count':len(vals),'missing_timestamp_count':len(rs)-len(vals),
  'unique_task_wall_seconds_sum':sum(vals) if vals else None,
  'mean_task_wall_seconds':statistics.mean(vals) if vals else None,
  'median_task_wall_seconds':statistics.median(vals) if vals else None,
  'interpretation':'task wall spans only; shared dependencies counted once; eval combines calibration and test inference; no phase CPU attribution'})
write_csv(OUT/'dependency_cost_summary.csv',cost_summary)

# At most three figures, all descriptive means over repetitions with n shown in tables.
figures=[]
try:
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 style={'direct':'-','logistic':'--','hist_gb':':'}
 colors={'gmm':'#2563eb','copula':'#e8790c','chow_liu':'#16834a'}
 for metric,title,ylabel,filename in [
   ('balanced_accuracy','Balanced accuracy change from each route?s clean control','corrupted ? clean','E5_balanced_accuracy_degradation.png'),
   ('coverage','Conformal coverage change from each route?s clean control','corrupted ? clean','E5_coverage_degradation.png'),
   ('set_size','Mean conformal set-size change from each route?s clean control','corrupted ? clean','E5_set_size_degradation.png')]:
  fig,axes=plt.subplots(1,3,figsize=(16,5),sharey=True)
  for ax,mechanism in zip(axes,('feature_noise','missingness','label_noise')):
   for family in FAMILIES:
    for learner in ('direct','logistic','hist_gb'):
     xs=[]; ys=[]
     for rate in (.05,.10,.20):
      row=next((x for x in route_summary if x['generator_family']==family and
       x['downstream_learner']==('logistic' if learner=='direct' else learner) and
       x['mechanism']==mechanism and math.isclose(float(x['rate']),rate)),None)
      # The direct values are duplicated by learner; draw direct only once to avoid double counting.
      if learner=='direct' and family and row is not None:
       field=f'direct_corruption_change_{metric}_mean'
      elif learner!='direct' and row is not None:
       field=f'synthetic_corruption_change_{metric}_mean'
      else: continue
      val=row.get(field)
      xs.append(int(rate*100)); ys.append(val)
     if xs:
      label=f'{family} {learner}'
      ax.plot(xs,ys,marker='o',linestyle=style[learner],color=colors[family],label=label)
   ax.axhline(0,color='black',linewidth=.7)
   ax.set_title(mechanism.replace('_',' '))
   ax.set_xticks([5,10,20]); ax.set_xlabel('Affected fitting rows (%)')
  axes[0].set_ylabel(ylabel)
  fig.suptitle(title)
  handles,labels=axes[-1].get_legend_handles_labels()
  fig.legend(handles,labels,loc='lower center',ncol=3,fontsize=8)
  fig.tight_layout(rect=[0,.18,1,.92])
  p=OUT/filename; fig.savefig(p,dpi=140); plt.close(fig); figures.append(p.name)
except Exception as exc:
    figures=[]; plot_error=f'{type(exc).__name__}: {exc}'
else:
    plot_error=None

counts=Counter(a['availability_status'] for a in availability)
if len(availability)!=270: raise RuntimeError('planned availability ledger does not have 270 rows')
summary_n=Counter(str(r.get('direct_corruption_change_balanced_accuracy_n')) for r in route_summary)
after=sha(RT/'source'/'reporting.py')
qa={'schema':'lamost-e5-completed-generator-route-report/1','observed_utc':datetime.now(timezone.utc).isoformat(),
 'scope':{'families':list(FAMILIES),'direct_route':'family-native generative classifier',
          'synthetic_route':'synthetic-only downstream logistic regression and histogram gradient boosting',
          'repetitions':list(REPS),'conditions':['clean']+[f'{m}_{int(r*100):02d}' for m,r in NOISE]},
 'planned_evaluations':270,'availability_status_counts':dict(counts),
 'registry_task_count':len(registry),'loaded_aggregate_evaluation_json_count':len(metric_by_key),
 'route_comparison_rows':len(comparisons),'corrupt_route_comparison_rows':len(corrupt_comps),
 'per_class_comparison_rows':len(class_comparisons),'route_summary_rows':len(route_summary),
 'per_class_summary_rows':len(class_summary),'route_summary_n_histogram':dict(summary_n),
 'dependency_cost_unique_task_rows':len(cost_rows),'cost_note':'Elapsed registry worker spans only; shared task durations counted once in ledger; no attribution to calibration vs test inference or to individual consumers.',
 'test_data_boundary':'Read registry metadata and validated aggregate evaluation.json only. No models, NPZ arrays, per-row predictions, refits, rescoring, recalibration, or test-driven selection.',
 'global_calibration_replay_validation':'pending; this report does not assert replay validity',
 'root_review':'pending',
 'reporting_source_sha256_before':sha(SOURCE),'reporting_source_sha256_after':after,
 'input_sha256':input_hashes,'figures':figures,'plot_error':plot_error,
 'outputs':{},'status':'complete_descriptive_subset' if sum(counts.values())==270 and len(metric_by_key)==270 else 'partial_descriptive_subset'}
for p in OUT.iterdir():
 if p.is_file() and p.name!='manifest.json': qa['outputs'][p.name]=sha(p)
(OUT/'manifest.json').write_text(json.dumps(qa,indent=2,sort_keys=True)+'\n')
# Update manifest to bind its own final output inventory without a self-hash.
print(json.dumps({'status':qa['status'],'availability':dict(counts),'loaded_evaluations':len(metric_by_key),
 'route_rows':len(comparisons),'per_class_rows':len(class_comparisons),'summaries':len(route_summary),
 'per_class_summaries':len(class_summary),'cost_rows':len(cost_rows),'figures':figures,
 'plot_error':plot_error,'output_dir':str(OUT)},indent=2))

